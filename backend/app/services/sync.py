import re
import unicodedata
import httpx
from datetime import datetime, timezone
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.entities import Competition, Match, MatchStatus, Odd, Player, Prediction, Team, TeamStat
from app.providers.football_data import FootballDataProvider
from app.providers.odds_api import OddsApiProvider
from app.providers.api_futebol import ApiFutebolProvider
from app.services.models import ModelInput, ensemble
from app.services.strengths import StrengthService

# Mantém as últimas N capturas por (partida, casa, mercado, seleção, linha).
ODDS_RETENTION = 5

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

    async def sync_odds(self) -> dict:
        events = await OddsApiProvider().odds([])
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
            for book in event.get("bookmakers", []):
                for market in book.get("markets", []):
                    market_name = {
                        "h2h": "match_result",
                        "totals": "goals_2_5",
                        "btts": "btts",
                    }.get(market["key"], market["key"])
                    for outcome in market.get("outcomes", []):
                        if market["key"] == "h2h":
                            selection = (
                                "home"
                                if normalize(outcome["name"]) == h
                                else "away"
                                if normalize(outcome["name"]) == a
                                else "draw"
                            )
                        elif market["key"] == "totals":
                            selection = outcome["name"].lower()
                        elif market["key"] == "btts":
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
        await self.session.flush()
        pruned = await self._prune_odds(touched, keep=ODDS_RETENTION)
        await self.session.commit()
        return {
            "provider": "odds_api",
            "events": len(events),
            "inserted": inserted,
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
                latest.model_version = pred.get("version", "ensemble-1.3")
                latest.features = {**(latest.features or {}), **features}
                updated += 1
            else:
                self.session.add(
                    Prediction(
                        match_id=match.id,
                        model_version=pred.get("version", "ensemble-1.3"),
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
            metrics = stats.get(side) or {}
            existing = await self.session.scalar(
                select(TeamStat).where(TeamStat.team_id == team.id, TeamStat.match_id == match.id)
            )
            if existing:
                existing.metrics = metrics
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
                        player.start_probability = 1 if role == "titulares" else 0
                        player.stats = {**player.stats, **payload}
                    else:
                        self.session.add(
                            Player(
                                team_id=team.id,
                                name=name,
                                position=position or "N/D",
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
                .order_by(Match.kickoff)
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
