from __future__ import annotations

import re
import unicodedata
import zlib
from collections import Counter, defaultdict
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ml_entities import (
    MlMatch,
    MlPlayer,
    MlPlayerMatchStat,
    MlSeason,
    MlTeam,
    MlTeamMatchStat,
)
from app.providers.bzzoiro import BzzoiroProvider
from app.providers.football_data import FootballDataProvider


BZZOIRO_SERIE_A_LEAGUE_ID = 9


def source_name(value: str | None) -> str:
    """Normaliza para busca sem aplicar aliases entre clubes distintos."""
    raw = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", raw).strip()


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def source_team_identity(value: int | None, name: str) -> tuple[int, bool]:
    if value is not None:
        return int(value), False
    # Negativo e estável entre processos; nunca colide com IDs normais do provedor.
    return -int(zlib.crc32(source_name(name).encode("utf-8")) or 1), True


class MlHistoryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.provider = BzzoiroProvider()
        self.football_data = FootballDataProvider()

    async def import_football_data_serie_a(self, year: int) -> dict:
        payload = await self.football_data.season_matches(year)
        events = payload.get("matches") or []
        if not events:
            raise ValueError(f"Temporada {year} não disponível na Football-Data")
        remote_season = events[0].get("season") or {}
        source_season_id = int(remote_season.get("id") or year)
        season = await self.session.scalar(select(MlSeason).where(
            MlSeason.source == "football_data",
            MlSeason.source_season_id == source_season_id,
        ))
        if not season:
            season = MlSeason(
                source="football_data", source_league_id=2013,
                source_season_id=source_season_id, competition="Brasileirão Série A",
                year=year, import_status="importing", raw=remote_season,
            )
            self.session.add(season)
            await self.session.flush()

        imported: list[MlMatch] = []
        created = updated = 0
        for row in events:
            home_raw, away_raw = row.get("homeTeam") or {}, row.get("awayTeam") or {}
            home_name = str(home_raw.get("shortName") or home_raw.get("name") or "")
            away_name = str(away_raw.get("shortName") or away_raw.get("name") or "")
            home = await self._team(int(home_raw["id"]), home_name, False, "football_data")
            away = await self._team(int(away_raw["id"]), away_name, False, "football_data")
            event_id = int(row["id"])
            match = await self.session.scalar(select(MlMatch).where(
                MlMatch.source == "football_data", MlMatch.source_event_id == event_id,
            ))
            score = row.get("score") or {}
            full_time, half_time = score.get("fullTime") or {}, score.get("halfTime") or {}
            values = {
                "season_id": season.id, "home_team_id": home.id, "away_team_id": away.id,
                "kickoff": parse_datetime(row["utcDate"]), "status": str(row.get("status") or ""),
                "round_number": row.get("matchday"), "home_score": full_time.get("home"),
                "away_score": full_time.get("away"), "home_score_ht": half_time.get("home"),
                "away_score_ht": half_time.get("away"), "raw": row,
            }
            if match:
                for key, value in values.items():
                    setattr(match, key, value)
                updated += 1
            else:
                match = MlMatch(source="football_data", source_event_id=event_id, **values)
                self.session.add(match)
                await self.session.flush()
                created += 1
            imported.append(match)
        quality = self._validate(imported, year)
        quality.update({"rejected_rows": 0, "rejected_sample": []})
        season.quality_summary = quality
        season.import_status = "completed" if quality["eligible_for_training"] else "completed_with_warnings"
        await self.session.commit()
        return {
            "provider": "football_data", "year": year, "received": len(events),
            "created": created, "updated": updated, "quality": quality,
        }

    async def import_bzzoiro_serie_a(self, year: int, include_details: bool = False) -> dict:
        if not self.provider.configured:
            raise RuntimeError("BZZOIRO_API_KEY não configurada")
        seasons = await self.provider.league_seasons(BZZOIRO_SERIE_A_LEAGUE_ID)
        remote_season = next((row for row in seasons if int(row.get("year") or 0) == year), None)
        if not remote_season:
            raise ValueError(f"Temporada {year} da Série A não encontrada na Bzzoiro")

        season = await self.session.scalar(
            select(MlSeason).where(
                MlSeason.source == "bzzoiro",
                MlSeason.source_season_id == int(remote_season["id"]),
            )
        )
        if not season:
            season = MlSeason(
                source="bzzoiro",
                source_league_id=BZZOIRO_SERIE_A_LEAGUE_ID,
                source_season_id=int(remote_season["id"]),
                competition="Brasileirão Série A",
                year=year,
                import_status="importing",
                raw=remote_season,
            )
            self.session.add(season)
            await self.session.flush()
        else:
            season.import_status = "importing"
            season.raw = remote_season

        events: list[dict] = []
        offset = 0
        while True:
            page = await self.provider.season_events(
                season.source_season_id, limit=200, offset=offset, status="finished"
            )
            rows = page if isinstance(page, list) else page.get("results") or page.get("events") or []
            events.extend(rows)
            if len(rows) < 200:
                break
            offset += len(rows)

        created = updated = detailed = detail_errors = 0
        rejected: list[dict] = []
        imported_matches: list[MlMatch] = []
        for row in events:
            if not row.get("id"):
                rejected.append({
                    "event_id": row.get("id"),
                    "code": "missing_event_identity",
                })
                continue
            if not row.get("event_date"):
                rejected.append({"event_id": row.get("id"), "code": "missing_event_date"})
                continue
            home_name, away_name = str(row.get("home_team") or ""), str(row.get("away_team") or "")
            home_source_id, home_inferred = source_team_identity(row.get("home_team_id"), home_name)
            away_source_id, away_inferred = source_team_identity(row.get("away_team_id"), away_name)
            home = await self._team(home_source_id, home_name, home_inferred)
            away = await self._team(away_source_id, away_name, away_inferred)
            event_id = int(row["id"])
            match = await self.session.scalar(
                select(MlMatch).where(
                    MlMatch.source == "bzzoiro", MlMatch.source_event_id == event_id
                )
            )
            values = {
                "season_id": season.id,
                "home_team_id": home.id,
                "away_team_id": away.id,
                "kickoff": parse_datetime(row["event_date"]),
                "status": str(row.get("status") or "unknown"),
                "round_number": row.get("round_number"),
                "home_score": row.get("home_score"),
                "away_score": row.get("away_score"),
                "home_score_ht": row.get("home_score_ht"),
                "away_score_ht": row.get("away_score_ht"),
                "raw": row,
            }
            if match:
                for key, value in values.items():
                    setattr(match, key, value)
                updated += 1
            else:
                match = MlMatch(source="bzzoiro", source_event_id=event_id, **values)
                self.session.add(match)
                await self.session.flush()
                created += 1
            identity_issues = []
            if home_inferred:
                identity_issues.append({"code": "inferred_home_team_id", "team": home_name})
            if away_inferred:
                identity_issues.append({"code": "inferred_away_team_id", "team": away_name})
            if identity_issues:
                match.quality_issues = identity_issues
                match.quality_status = "review"
            imported_matches.append(match)

            if include_details:
                try:
                    await self._details(match, row, home, away)
                    match.details_imported = True
                    detailed += 1
                except Exception as exc:
                    issues = list(match.quality_issues or [])
                    issues.append({"code": "detail_import_failed", "message": str(exc)[:240]})
                    match.quality_issues = issues
                    match.quality_status = "review"
                    detail_errors += 1
            if (created + updated) % 25 == 0:
                await self.session.commit()

        quality = self._validate(imported_matches, year)
        quality["rejected_rows"] = len(rejected)
        quality["rejected_sample"] = rejected[:20]
        if rejected:
            quality["eligible_for_training"] = False
        season.quality_summary = quality
        season.import_status = "completed_with_warnings" if quality["review_matches"] else "completed"
        await self.session.commit()
        return {
            "provider": "bzzoiro",
            "competition": "Brasileirão Série A",
            "year": year,
            "received": len(events),
            "created": created,
            "updated": updated,
            "details_imported": detailed,
            "detail_errors": detail_errors,
            "rejected": len(rejected),
            "quality": quality,
        }

    async def _team(
        self, source_id: int, name: str, inferred: bool = False, source: str = "bzzoiro"
    ) -> MlTeam:
        normalized = source_name(name)
        team = await self.session.scalar(
            select(MlTeam).where(
                MlTeam.source == source,
                MlTeam.source_team_id == source_id,
                MlTeam.normalized_name == normalized,
            )
        )
        if not team:
            team = MlTeam(
                source=source,
                source_team_id=source_id,
                name=name,
                normalized_name=normalized,
                raw={"source_name": name, "source_id_inferred": inferred},
            )
            self.session.add(team)
            await self.session.flush()
        return team

    async def _details(self, match: MlMatch, event: dict, home: MlTeam, away: MlTeam) -> None:
        stats = await self.provider.event_stats(match.source_event_id)
        lineups = await self.provider.lineups(match.source_event_id)
        player_payload = await self.provider.player_stats(match.source_event_id)
        periods = {
            "full_time": stats.get("stats") or {},
            "first_half": (stats.get("stats") or {}).get("first_half") or {},
            "second_half": (stats.get("stats") or {}).get("second_half") or {},
        }
        for period, values in periods.items():
            base = values if period == "full_time" else values
            for side, team in (("home", home), ("away", away)):
                metrics = base.get(side) or {}
                if not metrics:
                    continue
                record = await self.session.scalar(
                    select(MlTeamMatchStat).where(
                        MlTeamMatchStat.match_id == match.id,
                        MlTeamMatchStat.team_id == team.id,
                        MlTeamMatchStat.period == period,
                    )
                )
                if record:
                    record.metrics = metrics
                else:
                    self.session.add(MlTeamMatchStat(
                        match_id=match.id, team_id=team.id, is_home=side == "home",
                        period=period, metrics=metrics,
                    ))

        names: dict[int, dict] = {}
        for side in ("home", "away"):
            lineup = ((lineups.get("lineups") or {}).get(side) or {})
            for started, rows in ((True, lineup.get("players") or []), (False, lineup.get("substitutes") or [])):
                for player in rows:
                    if player.get("id") is not None:
                        names[int(player["id"])] = {**player, "started": started, "side": side}
        rows = player_payload.get("player_stats") if isinstance(player_payload, dict) else player_payload
        for metrics in rows or []:
            player_id = int(metrics["player_id"])
            identity = names.get(player_id) or {}
            name = str(identity.get("name") or identity.get("short_name") or f"Jogador {player_id}")
            player = await self.session.scalar(
                select(MlPlayer).where(
                    MlPlayer.source == "bzzoiro", MlPlayer.source_player_id == player_id
                )
            )
            if not player:
                player = MlPlayer(source="bzzoiro", source_player_id=player_id,
                                  name=name, normalized_name=source_name(name), raw=identity)
                self.session.add(player)
                await self.session.flush()
            team = home if int(metrics.get("team_id") or 0) == int(event["home_team_id"]) else away
            record = await self.session.scalar(
                select(MlPlayerMatchStat).where(
                    MlPlayerMatchStat.match_id == match.id,
                    MlPlayerMatchStat.player_id == player.id,
                )
            )
            values = {
                "team_id": team.id,
                "is_home": team.id == home.id,
                "started": bool(identity.get("started")),
                "minutes": metrics.get("minutes_played"),
                "position": identity.get("position"),
                "rating": metrics.get("rating"),
                "metrics": metrics,
            }
            if record:
                for key, value in values.items(): setattr(record, key, value)
            else:
                self.session.add(MlPlayerMatchStat(match_id=match.id, player_id=player.id, **values))

        raw = dict(match.raw or {})
        raw["bzzoiro_enrichment"] = {
            "lineup_status": lineups.get("lineup_status"),
            "shotmap": stats.get("shotmap") or [],
            "momentum": stats.get("momentum") or [],
            "average_positions": stats.get("average_positions") or {},
            "xg_per_minute": stats.get("xg_per_minute") or {},
        }
        match.raw = raw

    def _validate(self, matches: list[MlMatch], year: int) -> dict:
        # Mantém o payload bruto, mas exclui cópias conhecíveis do conjunto de treino.
        # A Bzzoiro já devolveu uma segunda identidade para o mesmo clube e também
        # eventos repetidos com IDs diferentes; não podemos deixar isso vazar no ML.
        by_team: dict[int, list[MlMatch]] = defaultdict(list)
        for match in matches:
            by_team[match.home_team_id].append(match)
            by_team[match.away_team_id].append(match)

        def fingerprint(match: MlMatch, team_id: int) -> tuple:
            if match.home_team_id == team_id:
                return (match.round_number, "home", match.away_team_id,
                        match.home_score, match.away_score)
            return (match.round_number, "away", match.home_team_id,
                    match.away_score, match.home_score)

        duplicate_identities: dict[int, int] = {}
        team_ids = list(by_team)
        for index, left_id in enumerate(team_ids):
            left = by_team[left_id]
            if len(left) < 30:
                continue
            left_fp = {fingerprint(match, left_id) for match in left}
            for right_id in team_ids[index + 1:]:
                right = by_team[right_id]
                if len(right) < 30:
                    continue
                right_fp = {fingerprint(match, right_id) for match in right}
                similarity = len(left_fp & right_fp) / max(1, min(len(left_fp), len(right_fp)))
                if similarity < 0.90:
                    continue
                # A cópia espúria costuma ser uma carga posterior com event IDs altos.
                left_median = sorted(m.source_event_id for m in left)[len(left) // 2]
                right_median = sorted(m.source_event_id for m in right)[len(right) // 2]
                loser, winner = ((left_id, right_id) if left_median > right_median
                                 else (right_id, left_id))
                duplicate_identities[loser] = winner

        excluded: set[int] = set()
        for duplicate_id, canonical_id in duplicate_identities.items():
            for match in by_team[duplicate_id]:
                match.quality_status = "excluded"
                match.quality_issues = [{
                    "code": "duplicate_team_identity",
                    "duplicate_team_id": duplicate_id,
                    "canonical_team_id": canonical_id,
                }]
                excluded.add(match.id)

        fixture_groups: dict[tuple, list[MlMatch]] = defaultdict(list)
        for match in matches:
            if match.id in excluded:
                continue
            fixture_groups[(match.round_number, match.home_team_id, match.away_team_id)].append(match)
        duplicate_event_rows = 0
        for group in fixture_groups.values():
            if len(group) < 2:
                continue
            ordered = sorted(group, key=lambda item: item.source_event_id)
            for duplicate in ordered[1:]:
                duplicate.quality_status = "excluded"
                duplicate.quality_issues = [{
                    "code": "duplicate_event",
                    "canonical_event_id": ordered[0].source_event_id,
                }]
                excluded.add(duplicate.id)
                duplicate_event_rows += 1

        appearances: Counter = Counter()
        for match in matches:
            if match.id in excluded:
                continue
            issues = [
                x for x in (match.quality_issues or [])
                if x.get("code") == "detail_import_failed"
            ]
            appearances[match.home_team_id] += 1
            appearances[match.away_team_id] += 1
            if match.home_team_id == match.away_team_id:
                issues.append({"code": "same_team_both_sides"})
            if match.home_score is None or match.away_score is None:
                issues.append({"code": "missing_final_score"})
            match.quality_issues = issues
            match.quality_status = "review" if issues else "valid"

        # Uma Série A de pontos corridos tem 20 clubes e 38 jogos por clube.
        roster_issues = []
        if year < datetime.now().year:
            for team_id, count in appearances.items():
                if count != 38:
                    roster_issues.append({"team_id": team_id, "matches": count, "expected": 38})
        return {
            "matches": len(matches),
            "usable_matches": len(matches) - len(excluded),
            "valid_matches": sum(m.quality_status == "valid" for m in matches),
            "review_matches": sum(m.quality_status == "review" for m in matches),
            "excluded_matches": len(excluded),
            "teams": len(appearances),
            "expected_teams": 20,
            "duplicate_event_rows": duplicate_event_rows,
            "duplicate_team_identities": [
                {"duplicate_team_id": duplicate, "canonical_team_id": canonical}
                for duplicate, canonical in duplicate_identities.items()
            ],
            "roster_issues": roster_issues,
            "eligible_for_training": (
                not roster_issues
                and len(matches) - len(excluded) == 380
                and len(appearances) == 20
                and not any(m.quality_status == "review" for m in matches)
            ),
        }

    async def overview(self) -> dict:
        async def count(model):
            return int(await self.session.scalar(select(func.count()).select_from(model)) or 0)
        seasons = list(await self.session.scalars(select(MlSeason).order_by(MlSeason.year.desc())))
        return {
            "seasons": [{"year": x.year, "source": x.source, "status": x.import_status,
                         "quality": x.quality_summary} for x in seasons],
            "matches": await count(MlMatch),
            "team_stats": await count(MlTeamMatchStat),
            "player_stats": await count(MlPlayerMatchStat),
        }
