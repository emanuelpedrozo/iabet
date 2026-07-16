import re
import unicodedata
import httpx
from datetime import datetime, timezone
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.entities import Competition, Match, MatchStatus, Odd, Player, PlayerMatchStat, Prediction, Team, TeamStat
from app.providers.api_sports import ApiSportsProvider
from app.providers.football_data import FootballDataProvider
from app.providers.odds_api import EVENT_STAT_MARKETS, OddsApiProvider
from app.providers.api_futebol import ApiFutebolProvider
from app.services.models import ModelInput, ensemble
from app.services.stat_rates import attach_stat_markets_to_prediction, match_stat_lambdas
from app.services.strengths import StrengthService
from app.services.team_metrics import enrich_api_futebol_metrics, merge_metrics

# Mantém as últimas N capturas por (partida, casa, mercado, seleção, linha).
ODDS_RETENTION = 5
# Limite de eventos para odds de escanteios/cartões (cada um consome cota).
EVENT_STAT_ODDS_LIMIT = 12

MARKET_KEY_MAP = {
    "h2h": "match_result",
    "totals": "goals_2_5",
    "btts": "btts",
    "alternate_totals_corners": "corners",
    "alternate_totals_cards": "cards",
}

ALIASES = {
    "red bull bragantino": "rb bragantino",
    "bragantino": "rb bragantino",
    "botafogo rj": "botafogo",
    "botafogo fr": "botafogo",
    "gremio fbpa": "gremio",
    "vasco da gama": "vasco",
    "cr vasco da gama": "vasco",
    "vitoria ba": "vitoria",
    "bahia ba": "bahia",
    "chapecoense af": "chapecoense",
    "atletico mineiro": "ca mineiro",
    "atletico mg": "ca mineiro",
    "atletico paranaense": "ca paranaense",
    "athletico paranaense": "ca paranaense",
    "athletico pr": "ca paranaense",
    "flamengo": "cr flamengo",
    "corinthians": "corinthians paulista",
    "sc corinthians paulista": "corinthians paulista",
    "internacional": "sc internacional",
    "palmeiras": "se palmeiras",
    "sao paulo": "sao paulo",
    "sao paulo fc": "sao paulo",
    "remo": "clube do remo",
    "coritiba": "coritiba fbc",
    "cruzeiro": "cruzeiro ec",
}


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    raw = re.sub(r"[^a-z0-9]+", " ", value).strip()
    # Botafogo-SP é outro clube; o sufixo estadual não pode ser descartado neste caso.
    if raw in {"botafogo sp", "botafogo sp fc", "botafogo futebol clube sp"}:
        return "botafogo sp"
    value = re.sub(r"\b(fc|sc|ec|saf|rj|sp|rs|ba)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value).strip()
    return ALIASES.get(value, value)


def status(value: str) -> MatchStatus:
    return {
        "SCHEDULED": MatchStatus.scheduled,
        "TIMED": MatchStatus.scheduled,
        "IN_PLAY": MatchStatus.live,
        "PAUSED": MatchStatus.live,
        "FINISHED": MatchStatus.finished,
        "POSTPONED": MatchStatus.postponed,
        "CANCELLED": MatchStatus.postponed,
    }.get(value, MatchStatus.scheduled)


def api_sports_status(value: str) -> MatchStatus:
    if value in {"FT", "AET", "PEN"}:
        return MatchStatus.finished
    if value in {"1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"}:
        return MatchStatus.live
    if value in {"PST", "CANC", "ABD", "AWD", "WO"}:
        return MatchStatus.postponed
    return MatchStatus.scheduled


def stat_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")


def as_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class DataSyncService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._teams_by_key: dict[str, Team] | None = None

    async def _load_teams(self) -> dict[str, Team]:
        if self._teams_by_key is None:
            teams = list(await self.session.scalars(select(Team)))
            self._teams_by_key = {normalize(t.name): t for t in teams}
        return self._teams_by_key

    async def _team(self, payload: dict) -> Team:
        name = payload.get("name") or "Desconhecido"
        key = normalize(name)
        cache = await self._load_teams()
        team = cache.get(key)
        if not team:
            team = Team(
                name=name,
                short_name=(payload.get("tla") or name[:3]).upper(),
                crest_url=payload.get("crest"),
            )
            self.session.add(team)
            await self.session.flush()
            cache[key] = team
        elif payload.get("crest") and not team.crest_url:
            team.crest_url = payload["crest"]
        return team

    async def _prune_odds(self, match_ids: set[int], keep: int = ODDS_RETENTION) -> int:
        """Remove odds antigas, mantendo as últimas `keep` por chave natural."""
        deleted = 0
        for match_id in match_ids:
            odds = list(
                await self.session.scalars(
                    select(Odd).where(Odd.match_id == match_id).order_by(Odd.captured_at.desc())
                )
            )
            groups: dict[tuple, list[Odd]] = {}
            for odd in odds:
                key = (odd.bookmaker, odd.market, odd.selection, odd.line)
                groups.setdefault(key, []).append(odd)
            for rows in groups.values():
                for old in rows[keep:]:
                    await self.session.delete(old)
                    deleted += 1
        return deleted

    async def sync_fixtures(self) -> dict:
        provider = FootballDataProvider()
        info = await provider.competition()
        rows = await provider.matches()
        season = str(info["currentSeason"]["startDate"][:4])
        comp = await self.session.scalar(
            select(Competition).where(
                Competition.name == "Brasileirão Série A", Competition.season == season
            )
        )
        if not comp:
            comp = Competition(name="Brasileirão Série A", country="Brasil", season=season)
            self.session.add(comp)
            await self.session.flush()
        created = updated = 0
        for row in rows:
            home = await self._team(row["homeTeam"])
            away = await self._team(row["awayTeam"])
            ext = str(row["id"])
            candidates = list(
                await self.session.scalars(
                    select(Match).where(
                        Match.home_team_id == home.id, Match.away_team_id == away.id
                    )
                )
            )
            match = next(
                (
                    m
                    for m in candidates
                    if str(m.metadata_.get("external_ids", {}).get("football_data")) == ext
                ),
                None,
            )
            if not match:
                kickoff = datetime.fromisoformat(row["utcDate"].replace("Z", "+00:00"))
                match = next(
                    (m for m in candidates if abs((m.kickoff - kickoff).total_seconds()) < 86400),
                    None,
                )
            meta = dict(match.metadata_) if match else {}
            ids = dict(meta.get("external_ids", {}))
            ids["football_data"] = ext
            meta["external_ids"] = ids
            meta["matchday"] = row.get("matchday")
            meta["last_synced_from"] = "football_data"
            score = row.get("score", {}).get("fullTime", {})
            if not match:
                match = Match(
                    competition_id=comp.id,
                    home_team_id=home.id,
                    away_team_id=away.id,
                    kickoff=datetime.fromisoformat(row["utcDate"].replace("Z", "+00:00")),
                    venue=row.get("venue"),
                    status=status(row["status"]),
                    home_score=score.get("home"),
                    away_score=score.get("away"),
                    metadata_=meta,
                )
                self.session.add(match)
                created += 1
            else:
                match.kickoff = datetime.fromisoformat(row["utcDate"].replace("Z", "+00:00"))
                match.status = status(row["status"])
                match.home_score = score.get("home")
                match.away_score = score.get("away")
                match.metadata_ = meta
                updated += 1
        await self.session.commit()
        strengths = await StrengthService(self.session).recalculate()
        predictions = await self.refresh_predictions()
        return {
            "provider": "football_data",
            "received": len(rows),
            "created": created,
            "updated": updated,
            "strengths": strengths,
            "predictions": predictions,
        }

    def _ingest_book_markets(
        self,
        match: Match,
        bookmakers: list,
        *,
        home_key: str,
        away_key: str,
        captured: datetime,
    ) -> int:
        inserted = 0
        for book in bookmakers:
            for market in book.get("markets", []):
                api_key = market["key"]
                market_name = MARKET_KEY_MAP.get(api_key, api_key)
                for outcome in market.get("outcomes", []):
                    if api_key == "h2h":
                        selection = (
                            "home"
                            if normalize(outcome["name"]) == home_key
                            else "away"
                            if normalize(outcome["name"]) == away_key
                            else "draw"
                        )
                    elif api_key in {
                        "totals",
                        "alternate_totals_corners",
                        "alternate_totals_cards",
                    }:
                        selection = outcome["name"].lower()
                    elif api_key == "btts":
                        name = outcome["name"].lower()
                        selection = (
                            "yes"
                            if name in ("yes", "sim")
                            else "no"
                            if name in ("no", "nao", "não")
                            else name
                        )
                    else:
                        selection = outcome["name"]
                    self.session.add(
                        Odd(
                            match_id=match.id,
                            bookmaker=book["title"],
                            market=market_name,
                            selection=selection,
                            line=outcome.get("point"),
                            price=float(outcome["price"]),
                            captured_at=captured,
                        )
                    )
                    inserted += 1
        return inserted

    async def sync_odds(self) -> dict:
        provider = OddsApiProvider()
        events = await provider.odds([])
        matches = list(
            (
                await self.session.scalars(
                    select(Match).options(
                        selectinload(Match.home_team), selectinload(Match.away_team)
                    )
                )
            ).unique()
        )
        inserted = 0
        unmatched: list[str] = []
        touched: set[int] = set()
        event_targets: list[tuple[Match, str]] = []
        captured = datetime.now(timezone.utc)
        for event in events:
            h, a = normalize(event["home_team"]), normalize(event["away_team"])
            match = next(
                (
                    m
                    for m in matches
                    if normalize(m.home_team.name) == h and normalize(m.away_team.name) == a
                ),
                None,
            )
            if not match:
                unmatched.append(f'{event["home_team"]} x {event["away_team"]}')
                continue
            touched.add(match.id)
            event_id = str(event.get("id") or "")
            if event_id:
                meta = dict(match.metadata_ or {})
                external_ids = dict(meta.get("external_ids") or {})
                external_ids["odds_api"] = event_id
                meta["external_ids"] = external_ids
                match.metadata_ = meta
                if len(event_targets) < EVENT_STAT_ODDS_LIMIT:
                    event_targets.append((match, event_id))
            inserted += self._ingest_book_markets(
                match,
                event.get("bookmakers") or [],
                home_key=h,
                away_key=a,
                captured=captured,
            )

        # Corners/cards: endpoint por evento (cota limitada).
        event_stat_inserted = 0
        event_stat_errors: list[dict] = []
        for match, event_id in event_targets:
            try:
                detail = await provider.event_odds(event_id, EVENT_STAT_MARKETS)
            except Exception as exc:
                event_stat_errors.append({"event_id": event_id, "error": str(exc)[:160]})
                continue
            h = normalize(match.home_team.name)
            a = normalize(match.away_team.name)
            n = self._ingest_book_markets(
                match,
                detail.get("bookmakers") or [],
                home_key=h,
                away_key=a,
                captured=captured,
            )
            event_stat_inserted += n
            inserted += n

        await self.session.flush()
        pruned = await self._prune_odds(touched, keep=ODDS_RETENTION)
        await self.session.commit()
        return {
            "provider": "odds_api",
            "events": len(events),
            "inserted": inserted,
            "event_stat_inserted": event_stat_inserted,
            "event_stat_events": len(event_targets),
            "event_stat_errors": event_stat_errors[:10],
            "pruned": pruned,
            "unmatched": unmatched,
        }

    async def refresh_predictions(self) -> dict:
        """Recalcula forças/ELO e materializa o ensemble para partidas agendadas ou ao vivo."""
        strength_svc = StrengthService(self.session)
        strengths = await strength_svc.recalculate()
        averages_cache: dict[int, tuple[float, float]] = {}
        matches = list(
            (
                await self.session.scalars(
                    select(Match)
                    .where(Match.status.in_([MatchStatus.scheduled, MatchStatus.live]))
                    .options(
                        selectinload(Match.home_team),
                        selectinload(Match.away_team),
                        selectinload(Match.predictions),
                    )
                )
            ).unique()
        )
        created = updated = 0
        for match in matches:
            if match.competition_id not in averages_cache:
                averages_cache[match.competition_id] = await strength_svc.league_averages_for(
                    match.competition_id
                )
            league_home, league_away = averages_cache[match.competition_id]
            ctx = await strength_svc.match_strengths(
                match.competition_id, match.home_team_id, match.away_team_id
            )
            inp = ModelInput(
                ctx["home_attack"],
                ctx["home_defense"],
                ctx["away_attack"],
                ctx["away_defense"],
                match.home_team.elo,
                match.away_team.elo,
                league_home_goals=league_home,
                league_away_goals=league_away,
            )
            pred = ensemble(inp)
            rates = await match_stat_lambdas(
                self.session,
                match.home_team_id,
                match.away_team_id,
                competition_id=match.competition_id,
                as_of=match.kickoff,
            )
            pred = attach_stat_markets_to_prediction(pred, rates)
            features = {
                "refreshed_at": datetime.now(timezone.utc).isoformat(),
                "league_home_goals": league_home,
                "league_away_goals": league_away,
                "home_n_games": ctx["home_n_games"],
                "away_n_games": ctx["away_n_games"],
                "home_form_games": ctx["home_form_games"],
                "away_form_games": ctx["away_form_games"],
                "home_attack": ctx["home_attack"],
                "home_defense": ctx["home_defense"],
                "away_attack": ctx["away_attack"],
                "away_defense": ctx["away_defense"],
                "stat_rates": pred.get("stat_rates"),
            }
            latest = (
                sorted(match.predictions, key=lambda x: x.created_at)[-1]
                if match.predictions
                else None
            )
            if latest:
                latest.probabilities = pred
                latest.expected_home_goals = pred["xg_home"]
                latest.expected_away_goals = pred["xg_away"]
                latest.score_mode = pred["score"]
                latest.model_version = pred.get("version", "ensemble-1.4")
                latest.features = {**(latest.features or {}), **features}
                updated += 1
            else:
                self.session.add(
                    Prediction(
                        match_id=match.id,
                        model_version=pred.get("version", "ensemble-1.4"),
                        probabilities=pred,
                        expected_home_goals=pred["xg_home"],
                        expected_away_goals=pred["xg_away"],
                        score_mode=pred["score"],
                        features={"source": "sync", **features},
                    )
                )
                created += 1
        await self.session.commit()
        return {
            "created": created,
            "updated": updated,
            "matches": len(matches),
            "strengths": strengths,
        }

    async def sync_api_futebol_index(self) -> dict:
        rows = await ApiFutebolProvider().matches()
        matches = list(
            (
                await self.session.scalars(
                    select(Match).options(
                        selectinload(Match.home_team), selectinload(Match.away_team)
                    )
                )
            ).unique()
        )
        linked = 0
        unmatched: list[str] = []
        for row in rows:
            h = normalize(row["time_mandante"]["nome_popular"])
            a = normalize(row["time_visitante"]["nome_popular"])
            candidates = [
                m
                for m in matches
                if normalize(m.home_team.name) == h and normalize(m.away_team.name) == a
            ]
            match = None
            if row.get("data_realizacao_iso"):
                kickoff = datetime.strptime(row["data_realizacao_iso"], "%Y-%m-%dT%H:%M:%S%z")
                match = next(
                    (m for m in candidates if abs((m.kickoff - kickoff).total_seconds()) < 86400),
                    None,
                )
            if not match and len(candidates) == 1:
                match = candidates[0]
            if not match:
                unmatched.append(
                    f'{row["time_mandante"]["nome_popular"]} x {row["time_visitante"]["nome_popular"]}'
                )
                continue
            meta = dict(match.metadata_)
            ids = dict(meta.get("external_ids", {}))
            ids["api_futebol"] = str(row["partida_id"])
            meta["external_ids"] = ids
            match.metadata_ = meta
            linked += 1
        await self.session.commit()
        return {
            "provider": "api_futebol",
            "received": len(rows),
            "linked": linked,
            "unmatched": unmatched[:20],
            "unmatched_count": len(unmatched),
        }

    async def sync_api_futebol_match(self, match_id: int) -> dict:
        match = await self.session.scalar(
            select(Match)
            .where(Match.id == match_id)
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
        )
        if not match:
            raise ValueError("Partida local não encontrada")
        external = match.metadata_.get("external_ids", {}).get("api_futebol")
        if not external:
            raise ValueError("Partida ainda não vinculada à API Futebol")
        data = await ApiFutebolProvider().match(int(external))
        stats = data.get("estatisticas") or {}
        lineups = data.get("escalacoes") or {}
        for side, team, is_home in (
            ("mandante", match.home_team, True),
            ("visitante", match.away_team, False),
        ):
            metrics = enrich_api_futebol_metrics(stats.get(side) or {})
            existing = await self.session.scalar(
                select(TeamStat).where(TeamStat.team_id == team.id, TeamStat.match_id == match.id)
            )
            if existing:
                existing.metrics = merge_metrics(existing.metrics, metrics)
                existing.is_home = is_home
            else:
                self.session.add(
                    TeamStat(team_id=team.id, match_id=match.id, is_home=is_home, metrics=metrics)
                )
            lineup = lineups.get(side) or {}
            for role in ("titulares", "reservas"):
                for item in lineup.get(role, []):
                    athlete = item.get("atleta", {})
                    external_player = str(athlete.get("atleta_id"))
                    name = athlete.get("nome_popular")
                    if not name:
                        continue
                    position_data = item.get("posicao") or {}
                    if isinstance(position_data, dict):
                        position = position_data.get("sigla")
                    elif (
                        isinstance(position_data, list)
                        and position_data
                        and isinstance(position_data[0], dict)
                    ):
                        position = position_data[0].get("sigla")
                    else:
                        position = "N/D"
                    player = await self.session.scalar(
                        select(Player).where(Player.team_id == team.id, Player.name == name)
                    )
                    payload = {
                        "api_futebol_id": external_player,
                        "shirt": item.get("camisa"),
                        "last_lineup_match": match.id,
                    }
                    if player:
                        player.position = position or player.position
                        player.status = "available"
                        player.start_probability = 1 if role == "titulares" else 0
                        player.stats = {**player.stats, **payload}
                    else:
                        self.session.add(
                            Player(
                                team_id=team.id,
                                name=name,
                                position=position or "N/D",
                                status="available",
                                start_probability=1 if role == "titulares" else 0,
                                stats=payload,
                            )
                        )
        meta = dict(match.metadata_)
        meta.update(
            {
                "api_futebol": {
                    "cards": data.get("cartoes"),
                    "goals": data.get("gols"),
                    "referees": data.get("arbitros"),
                    "lineups_available": bool(lineups),
                }
            }
        )
        match.metadata_ = meta
        await self.session.commit()
        return {
            "provider": "api_futebol",
            "match_id": match.id,
            "external_id": external,
            "statistics": bool(stats),
            "lineups": bool(lineups),
            "cards": bool(data.get("cartoes")),
        }

    async def import_api_futebol_history(self, limit: int = 80) -> dict:
        imported_ids = select(TeamStat.match_id)
        pending = list(
            await self.session.scalars(
                select(Match.id)
                .where(Match.status == MatchStatus.finished, ~Match.id.in_(imported_ids))
                # A escalação recente é mais útil para identificar o elenco atual.
                .order_by(Match.kickoff.desc())
                .limit(min(max(limit, 1), 80))
            )
        )
        imported: list[int] = []
        errors: list[dict] = []
        quota_exhausted = False
        for match_id in pending:
            try:
                await self.sync_api_futebol_match(match_id)
                imported.append(match_id)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    quota_exhausted = True
                    break
                errors.append({"match_id": match_id, "status": exc.response.status_code})
            except Exception as exc:
                errors.append({"match_id": match_id, "error": str(exc)[:160]})
        remaining = await self.session.scalar(
            select(func.count())
            .select_from(Match)
            .where(
                Match.status == MatchStatus.finished,
                ~Match.id.in_(select(TeamStat.match_id)),
            )
        )
        return {
            "provider": "api_futebol",
            "requested": len(pending),
            "imported": len(imported),
            "remaining": remaining,
            "errors": errors,
            "quota_exhausted": quota_exhausted,
        }

    async def api_sports_progress(self, season: int = 2024, division: str = "A") -> dict:
        division = division.upper()
        competition = await self.session.scalar(
            select(Competition).where(
                Competition.name == f"Brasileirão Série {division}",
                Competition.season == str(season),
            )
        )
        if not competition:
            return {"season": season, "division": division, "fixtures": 0, "imported": 0, "remaining": 0, "player_match_stats": 0}
        fixture_ids = select(Match.id).where(Match.competition_id == competition.id)
        fixtures = await self.session.scalar(
            select(func.count()).select_from(Match).where(Match.competition_id == competition.id)
        )
        matches = list(
            await self.session.scalars(select(Match).where(Match.competition_id == competition.id))
        )
        imported = sum(
            1
            for match in matches
            if ((match.metadata_ or {}).get("api_sports") or {}).get("detail_imported_at")
        )
        players = await self.session.scalar(
            select(func.count()).select_from(PlayerMatchStat).where(
                PlayerMatchStat.match_id.in_(fixture_ids)
            )
        )
        return {
            "season": season,
            "division": division,
            "fixtures": fixtures or 0,
            "imported": imported,
            "remaining": max((fixtures or 0) - imported, 0),
            "player_match_stats": players or 0,
        }

    async def import_api_sports_history(self, season: int = 2024, limit: int = 80, division: str = "A") -> dict:
        if season != 2024:
            raise ValueError("O plano gratuito da API-Sports está configurado para a temporada 2024")
        division = division.upper()
        if division not in {"A", "B"}:
            raise ValueError("Divisão deve ser A ou B")
        provider = ApiSportsProvider()
        rows = await provider.fixtures(season, division)
        competition = await self.session.scalar(
            select(Competition).where(
                Competition.name == f"Brasileirão Série {division}",
                Competition.season == str(season),
            )
        )
        if not competition:
            competition = Competition(
                name=f"Brasileirão Série {division}", country="Brasil", season=str(season), active=False
            )
            self.session.add(competition)
            await self.session.flush()
        local_matches = list(
            await self.session.scalars(
                select(Match)
                .where(Match.competition_id == competition.id)
                .options(selectinload(Match.home_team), selectinload(Match.away_team))
            )
        )
        by_external = {
            str(match.metadata_.get("external_ids", {}).get("api_sports")): match
            for match in local_matches
            if match.metadata_.get("external_ids", {}).get("api_sports")
        }
        indexed = 0
        for row in rows:
            fixture = row.get("fixture") or {}
            external_id = str(fixture.get("id"))
            teams = row.get("teams") or {}
            home_data = teams.get("home") or {}
            away_data = teams.get("away") or {}
            home = await self._team(
                {"name": home_data.get("name"), "tla": home_data.get("code"), "crest": home_data.get("logo")}
            )
            away = await self._team(
                {"name": away_data.get("name"), "tla": away_data.get("code"), "crest": away_data.get("logo")}
            )
            match = by_external.get(external_id)
            kickoff = datetime.fromisoformat(str(fixture.get("date")).replace("Z", "+00:00"))
            meta = dict(match.metadata_) if match else {}
            external_ids = dict(meta.get("external_ids", {}))
            external_ids["api_sports"] = external_id
            meta.update({"external_ids": external_ids, "api_sports_team_ids": {"home": home_data.get("id"), "away": away_data.get("id")}, "round": (row.get("league") or {}).get("round"), "last_synced_from": "api_sports"})
            score = row.get("goals") or {}
            status_data = fixture.get("status") or {}
            if not match:
                match = Match(
                    competition_id=competition.id,
                    home_team_id=home.id,
                    away_team_id=away.id,
                    kickoff=kickoff,
                    venue=(fixture.get("venue") or {}).get("name"),
                    status=api_sports_status(status_data.get("short", "NS")),
                    home_score=score.get("home"),
                    away_score=score.get("away"),
                    metadata_=meta,
                )
                self.session.add(match)
                await self.session.flush()
                by_external[external_id] = match
                indexed += 1
            else:
                match.home_team_id = home.id
                match.away_team_id = away.id
                match.home_team = home
                match.away_team = away
                match.kickoff = kickoff
                match.venue = (fixture.get("venue") or {}).get("name")
                match.status = api_sports_status(status_data.get("short", "NS"))
                match.home_score = score.get("home")
                match.away_score = score.get("away")
                match.metadata_ = meta
        await self.session.commit()

        # Concluído = detail_imported_at (não exige PlayerMatchStat: jogo sem minutos
        # de jogador ainda assim grava TeamStat e não deve reconsumir cota).
        candidates = list(
            await self.session.scalars(
                select(Match)
                .where(Match.competition_id == competition.id)
                .order_by(Match.kickoff)
                .options(selectinload(Match.home_team), selectinload(Match.away_team))
            )
        )
        pending = []
        for match in candidates:
            external_ids = (match.metadata_ or {}).get("external_ids") or {}
            if not external_ids.get("api_sports"):
                continue
            api_meta = (match.metadata_ or {}).get("api_sports") or {}
            if api_meta.get("detail_imported_at"):
                continue
            pending.append(match)
            if len(pending) >= min(max(limit, 1), 80):
                break
        imported = 0
        player_rows = 0
        errors: list[dict] = []
        quota_exhausted = False
        for match in pending:
            external_id = int(match.metadata_["external_ids"]["api_sports"])
            try:
                detail = await provider.fixture(external_id)
                player_rows += await self._ingest_api_sports_detail(match, detail)
                imported += 1
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in {429, 499}:
                    quota_exhausted = True
                    break
                errors.append({"fixture_id": external_id, "status": exc.response.status_code})
            except RuntimeError as exc:
                if "request" in str(exc).lower() or "limit" in str(exc).lower():
                    quota_exhausted = True
                    break
                errors.append({"fixture_id": external_id, "error": str(exc)[:180]})
            except Exception as exc:
                errors.append({"fixture_id": external_id, "error": str(exc)[:180]})
        final_progress = await self.api_sports_progress(season, division)
        return {
            "provider": "api_sports",
            "season": season,
            "division": division,
            "fixtures_received": len(rows),
            "fixtures_created": indexed,
            "requested": len(pending),
            "imported": imported,
            "player_match_stats_created": player_rows,
            "remaining": final_progress["remaining"],
            "quota_exhausted": quota_exhausted,
            "errors": errors,
        }

    async def _ingest_api_sports_detail(self, match: Match, detail: dict) -> int:
        api_teams = detail.get("teams") or {}
        home_external = (api_teams.get("home") or {}).get("id")
        team_map = {
            home_external: (match.home_team, True),
            (api_teams.get("away") or {}).get("id"): (match.away_team, False),
        }
        for block in detail.get("statistics") or []:
            external_team = (block.get("team") or {}).get("id")
            target = team_map.get(external_team)
            if not target:
                continue
            team, is_home = target
            metrics = {
                stat_key(item.get("type", "unknown")): item.get("value")
                for item in block.get("statistics") or []
            }
            metrics["source"] = "api_sports"
            existing = await self.session.scalar(
                select(TeamStat).where(TeamStat.team_id == team.id, TeamStat.match_id == match.id)
            )
            if existing:
                existing.metrics = merge_metrics(existing.metrics, metrics)
                existing.is_home = is_home
            else:
                self.session.add(
                    TeamStat(team_id=team.id, match_id=match.id, is_home=is_home, metrics=metrics)
                )

        created = 0
        for block in detail.get("players") or []:
            external_team = (block.get("team") or {}).get("id")
            target = team_map.get(external_team)
            if not target:
                continue
            team, is_home = target
            team_players = list(await self.session.scalars(select(Player).where(Player.team_id == team.id)))
            by_api_id = {str(p.stats.get("api_sports_id")): p for p in team_players if p.stats.get("api_sports_id")}
            by_name = {normalize(p.name): p for p in team_players}
            for item in block.get("players") or []:
                player_data = item.get("player") or {}
                stats_rows = item.get("statistics") or []
                if not stats_rows:
                    continue
                metrics = stats_rows[0]
                games = metrics.get("games") or {}
                minutes = games.get("minutes")
                if minutes is None:
                    continue
                external_player = str(player_data.get("id"))
                name = player_data.get("name") or "Jogador desconhecido"
                player = by_api_id.get(external_player) or by_name.get(normalize(name))
                payload = {
                    "api_sports_id": external_player,
                    "photo": player_data.get("photo"),
                    "last_lineup_match": match.id,
                }
                if not player:
                    player = Player(
                        team_id=team.id,
                        name=name,
                        position=games.get("position") or "N/D",
                        status="historical",
                        stats=payload,
                    )
                    self.session.add(player)
                    await self.session.flush()
                    by_api_id[external_player] = player
                    by_name[normalize(name)] = player
                else:
                    player.position = games.get("position") or player.position
                    player.stats = {**(player.stats or {}), **payload}
                    if not player.stats.get("api_futebol_id"):
                        player.status = "historical"
                existing = await self.session.scalar(
                    select(PlayerMatchStat).where(
                        PlayerMatchStat.player_id == player.id,
                        PlayerMatchStat.match_id == match.id,
                    )
                )
                stat_payload = {**metrics, "source": "api_sports"}
                values = {
                    "team_id": team.id,
                    "is_home": is_home,
                    "started": not bool(games.get("substitute")),
                    "minutes": int(minutes),
                    "position": games.get("position"),
                    "rating": as_float(games.get("rating")),
                    "metrics": stat_payload,
                }
                if existing:
                    for key, value in values.items():
                        setattr(existing, key, value)
                else:
                    self.session.add(PlayerMatchStat(player_id=player.id, match_id=match.id, **values))
                    created += 1
        meta = dict(match.metadata_)
        api_meta = dict(meta.get("api_sports", {}))
        api_meta.update({"events": detail.get("events") or [], "lineups": detail.get("lineups") or [], "detail_imported_at": datetime.now(timezone.utc).isoformat()})
        meta["api_sports"] = api_meta
        match.metadata_ = meta
        await self.session.commit()
        return created
