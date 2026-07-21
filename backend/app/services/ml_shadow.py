from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import log

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.entities import Competition, Match, MatchStatus, Prediction, Team, TeamStat
from app.models.ml_entities import MlMatch, MlModelRun, MlSeason, MlShadowPrediction, MlTeam
from app.services.ml_features import (
    FEATURES,
    RollingState,
    canonical_club_name,
    predict_binary_from_artifact,
    predict_proba_from_artifact,
)
from app.services.ml_training import historical_metric
from app.services.stat_rates import attach_stat_markets_to_prediction, match_stat_lambdas
from app.services.team_metrics import team_metric

# Backtest sombra: janela maior só para diagnóstico (não afeta produção).
BACKTEST_DAYS = 30


class MlShadowService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def round_number(match: Match) -> int | None:
        metadata = match.metadata_ or {}
        values = [
            metadata.get("matchday"),
            metadata.get("round"),
            (metadata.get("league") or {}).get("round"),
            (metadata.get("fixture") or {}).get("round"),
        ]
        for value in values:
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                numbers = "".join(char if char.isdigit() else " " for char in value).split()
                if numbers:
                    return int(numbers[-1])
        return None

    async def next_round_number(self, now: datetime) -> int | None:
        candidates = list(
            await self.session.scalars(
                select(Match)
                .join(Competition, Competition.id == Match.competition_id)
                .where(
                    Competition.active.is_(True),
                    Competition.name.ilike("%Série A%"),
                    Match.status == MatchStatus.scheduled,
                    Match.kickoff >= now - timedelta(hours=6),
                )
                .order_by(Match.kickoff)
            )
        )
        return next(
            (number for match in candidates if (number := self.round_number(match)) is not None),
            None,
        )

    async def _latest_approved_model(self) -> MlModelRun | None:
        return await self.session.scalar(
            select(MlModelRun)
            .where(MlModelRun.status == "approved")
            .order_by(MlModelRun.created_at.desc())
        )

    async def _match_side_stats(self, match: Match) -> dict:
        """Corners/cartões do TeamStat de produção (só para features da sombra)."""
        rows = list(
            await self.session.scalars(select(TeamStat).where(TeamStat.match_id == match.id))
        )
        out: dict[str, float | None] = {
            "home_corners": None,
            "away_corners": None,
            "home_cards": None,
            "away_cards": None,
        }
        for stat in rows:
            is_home = stat.is_home
            corners = team_metric(
                stat.metrics, match.metadata_, "corner_kicks", is_home=is_home
            )
            cards = team_metric(
                stat.metrics, match.metadata_, "yellow_cards", is_home=is_home
            )
            prefix = "home" if is_home else "away"
            out[f"{prefix}_corners"] = corners
            out[f"{prefix}_cards"] = cards
        return out

    async def _enrich_active_probabilities(self, match: Match, active_probs: dict) -> dict:
        """Garante gols/escanteios/cartões na comparação sombra (não altera Prediction)."""
        probs = dict(active_probs or {})
        if probs.get("over_2_5") is None and probs.get("goals_over_2_5") is not None:
            probs["over_2_5"] = probs["goals_over_2_5"]
        if probs.get("over_2_5") is not None:
            probs.setdefault("goals_over_2_5", probs["over_2_5"])
        if any(probs.get(key) is None for key in ("corners_over_9_5", "cards_over_4_5")):
            rates = await match_stat_lambdas(
                self.session,
                match.home_team_id,
                match.away_team_id,
                competition_id=match.competition_id,
                as_of=match.kickoff,
            )
            filled = attach_stat_markets_to_prediction(dict(probs), rates)
            for key in ("corners_over_9_5", "cards_over_4_5"):
                if probs.get(key) is None and filled.get(key) is not None:
                    probs[key] = filled[key]
        return {
            key: probs.get(key)
            for key in (
                "home",
                "draw",
                "away",
                "over_2_5",
                "goals_over_2_5",
                "corners_over_9_5",
                "cards_over_4_5",
            )
        }

    async def materialize(self) -> dict:
        model = await self._latest_approved_model()
        if not model:
            raise ValueError(
                "Nenhum modelo ML aprovado. Treine novamente; runs rejeitados não entram na sombra."
            )

        eligible_seasons = list(
            await self.session.scalars(
                select(MlSeason).where(
                    MlSeason.quality_summary["eligible_for_training"].as_boolean().is_(True)
                )
            )
        )
        season_ids = {season.id for season in eligible_seasons}
        historical = (
            await self.session.execute(
                select(MlMatch, MlTeam.normalized_name)
                .join(MlTeam, MlTeam.id == MlMatch.home_team_id)
                .where(MlMatch.season_id.in_(season_ids), MlMatch.quality_status == "valid")
                .order_by(MlMatch.kickoff, MlMatch.id)
            )
        ).all()
        team_names = dict(
            (await self.session.execute(select(MlTeam.id, MlTeam.normalized_name))).all()
        )

        # Stats ML para corners/cards no histórico de treino.
        from app.models.ml_entities import MlTeamMatchStat

        hist_match_ids = [match.id for match, _ in historical]
        stat_rows = list(
            await self.session.scalars(
                select(MlTeamMatchStat).where(
                    MlTeamMatchStat.match_id.in_(hist_match_ids),
                    MlTeamMatchStat.period == "full_time",
                )
            )
        ) if hist_match_ids else []
        side_stats: dict[int, dict[str, dict[bool, float]]] = {}
        for stat in stat_rows:
            bucket = side_stats.setdefault(stat.match_id, {"corners": {}, "cards": {}})
            for market in ("corners", "cards"):
                value = historical_metric(stat.metrics or {}, market)
                if value is not None:
                    bucket[market][stat.is_home] = value

        state = RollingState.empty()
        for match, raw_home_name in historical:
            home = canonical_club_name(raw_home_name)
            away = canonical_club_name(team_names[match.away_team_id])
            sides = side_stats.get(match.id) or {"corners": {}, "cards": {}}
            state.update(
                home,
                away,
                match.home_score,
                match.away_score,
                home_corners=sides["corners"].get(True),
                away_corners=sides["corners"].get(False),
                home_cards=sides["cards"].get(True),
                away_cards=sides["cards"].get(False),
            )

        current_team_names = dict((await self.session.execute(select(Team.id, Team.name))).all())
        artifact = model.artifact or {}
        created = updated = 0

        def predict(values: list[float]) -> dict:
            probabilities = predict_proba_from_artifact(values, artifact)
            for market, candidate in (artifact.get("market_models") or {}).items():
                probabilities[market] = predict_binary_from_artifact(values, candidate)
            return probabilities

        async def save_prediction(
            match: Match,
            home: str,
            away: str,
            values: list[float],
            probabilities: dict,
            outcome: str | None = None,
        ) -> None:
            nonlocal created, updated
            active = await self.session.scalar(
                select(Prediction)
                .where(Prediction.match_id == match.id)
                .order_by(Prediction.created_at.desc())
            )
            active_probs = await self._enrich_active_probabilities(
                match, (active.probabilities or {}) if active else {}
            )
            active_pick = max(("home", "draw", "away"), key=lambda key: active_probs.get(key) or 0)
            shadow_pick = max(("home", "draw", "away"), key=lambda key: probabilities.get(key, 0))
            comparison = {
                "active_model": active.model_version if active else None,
                "active_probabilities": active_probs,
                "active_pick": active_pick if active else None,
                "shadow_pick": shadow_pick,
                "same_pick": bool(active and active_pick == shadow_pick),
                "max_probability_delta": round(
                    max(
                        abs(probabilities.get(key, 0) - float(active_probs.get(key) or 0))
                        for key in ("home", "draw", "away")
                    ),
                    4,
                )
                if active
                else None,
            }
            if outcome:
                comparison.update(
                    {
                        "outcome": outcome,
                        "active_correct": bool(active and active_pick == outcome),
                        "shadow_correct": shadow_pick == outcome,
                        "active_log_loss": round(
                            -log(max(float(active_probs.get(outcome) or 0), 1e-6)), 4
                        )
                        if active
                        else None,
                        "shadow_log_loss": round(
                            -log(max(float(probabilities.get(outcome) or 0), 1e-6)), 4
                        ),
                        "mode": "backtest",
                    }
                )
                if probabilities.get("goals_over_2_5") is not None:
                    goals_outcome = (match.home_score or 0) + (match.away_score or 0) > 2
                    goals_pick = probabilities["goals_over_2_5"] >= 0.5
                    comparison.update(
                        {
                            "goals_over_2_5_outcome": goals_outcome,
                            "goals_over_2_5_correct": goals_pick == goals_outcome,
                        }
                    )
            else:
                comparison["mode"] = "upcoming"
            record = await self.session.scalar(
                select(MlShadowPrediction).where(
                    MlShadowPrediction.match_id == match.id,
                    MlShadowPrediction.model_run_id == model.id,
                )
            )
            payload_features = dict(zip(FEATURES, [round(float(value), 4) for value in values]))
            payload_features.update({"home_key": home, "away_key": away})
            if record:
                record.probabilities = probabilities
                record.features = payload_features
                record.comparison = comparison
                # JSON no SQLAlchemy só persiste se marcado como modificado.
                flag_modified(record, "probabilities")
                flag_modified(record, "features")
                flag_modified(record, "comparison")
                updated += 1
            else:
                self.session.add(
                    MlShadowPrediction(
                        match_id=match.id,
                        model_run_id=model.id,
                        probabilities=probabilities,
                        features=payload_features,
                        comparison=comparison,
                    )
                )
                created += 1

        now = datetime.now(timezone.utc)
        next_round = await self.next_round_number(now)
        season_start = datetime(now.year, 1, 1, tzinfo=timezone.utc)
        recent_cutoff = now - timedelta(days=BACKTEST_DAYS)
        finished = (
            await self.session.execute(
                select(Match, Team.name)
                .join(Team, Team.id == Match.home_team_id)
                .where(
                    Match.status == MatchStatus.finished,
                    Match.kickoff >= season_start,
                    Match.home_score.is_not(None),
                    Match.away_score.is_not(None),
                )
                .order_by(Match.kickoff, Match.id)
            )
        ).all()
        backtested = 0
        for match, raw_home_name in finished:
            home = canonical_club_name(raw_home_name)
            away = canonical_club_name(current_team_names[match.away_team_id])
            values = state.features(home, away, self.round_number(match))
            probabilities = predict(values)
            outcome = (
                "home"
                if match.home_score > match.away_score
                else "away"
                if match.home_score < match.away_score
                else "draw"
            )
            if match.kickoff >= recent_cutoff:
                await save_prediction(match, home, away, values, probabilities, outcome)
                backtested += 1
            side = await self._match_side_stats(match)
            state.update(
                home,
                away,
                match.home_score,
                match.away_score,
                home_corners=side["home_corners"],
                away_corners=side["away_corners"],
                home_cards=side["home_cards"],
                away_cards=side["away_cards"],
            )

        current_candidates = (
            await self.session.execute(
                select(Match, Team.name)
                .join(Team, Team.id == Match.home_team_id)
                .join(Competition, Competition.id == Match.competition_id)
                .where(
                    Competition.active.is_(True),
                    Competition.name.ilike("%Série A%"),
                    Match.status == MatchStatus.scheduled,
                    Match.kickoff >= now,
                )
                .order_by(Match.kickoff)
            )
        ).all()
        current = [
            row for row in current_candidates if self.round_number(row[0]) == next_round
        ]
        for match, raw_home_name in current:
            home = canonical_club_name(raw_home_name)
            away = canonical_club_name(current_team_names[match.away_team_id])
            values = state.features(home, away, self.round_number(match))
            await save_prediction(match, home, away, values, predict(values))
        await self.session.commit()
        return {
            "model": model.version,
            "model_status": model.status,
            "round": next_round,
            "matches": len(current),
            "backtested": backtested,
            "backtest_days": BACKTEST_DAYS,
            "created": created,
            "updated": updated,
        }

    async def overview(self) -> dict:
        model = await self._latest_approved_model()
        if not model:
            latest_any = await self.session.scalar(
                select(MlModelRun).order_by(MlModelRun.created_at.desc())
            )
            return {
                "active": False,
                "predictions": 0,
                "comparisons": [],
                "reason": "Sem modelo aprovado para sombra",
                "latest_run_status": latest_any.status if latest_any else None,
            }
        rows = list(
            await self.session.scalars(
                select(MlShadowPrediction)
                .where(MlShadowPrediction.model_run_id == model.id)
                .order_by(MlShadowPrediction.updated_at.desc())
            )
        )
        match_ids = [row.match_id for row in rows]
        match_rows = (
            (
                await self.session.execute(
                    select(Match, Team.name)
                    .join(Team, Team.id == Match.home_team_id)
                    .where(Match.id.in_(match_ids))
                )
            ).all()
            if match_ids
            else []
        )
        current_names = dict((await self.session.execute(select(Team.id, Team.name))).all())
        match_context = {
            match.id: {
                "home_team": home_name,
                "away_team": current_names.get(match.away_team_id, ""),
                "kickoff": match.kickoff,
                "home_score": match.home_score,
                "away_score": match.away_score,
                "status": match.status.value,
                "round": self.round_number(match),
            }
            for match, home_name in match_rows
        }
        match_by_id = {match.id: match for match, _ in match_rows}
        next_round = await self.next_round_number(datetime.now(timezone.utc))
        round_rows = [
            row
            for row in rows
            if match_context.get(row.match_id, {}).get("round") == next_round
            and match_context.get(row.match_id, {}).get("status") == MatchStatus.scheduled.value
        ]
        comparable = [row for row in round_rows if row.comparison.get("active_pick")]
        backtest = [row for row in rows if row.comparison.get("mode") == "backtest"]
        active_backtest = [
            row for row in backtest if row.comparison.get("active_log_loss") is not None
        ]
        ordered = sorted(
            rows,
            key=lambda row: float(row.comparison.get("max_probability_delta") or 0),
            reverse=True,
        )

        comparisons = []
        dirty = False
        for row in ordered:
            if row not in round_rows:
                continue
            comparison = dict(row.comparison or {})
            active_probs = dict(comparison.get("active_probabilities") or {})
            missing_markets = any(
                active_probs.get(key) is None
                for key in ("over_2_5", "corners_over_9_5", "cards_over_4_5")
            )
            match = match_by_id.get(row.match_id)
            if match and missing_markets:
                prediction = await self.session.scalar(
                    select(Prediction)
                    .where(Prediction.match_id == match.id)
                    .order_by(Prediction.created_at.desc())
                )
                base = (prediction.probabilities or {}) if prediction else active_probs
                enriched = await self._enrich_active_probabilities(match, base)
                comparison["active_probabilities"] = enriched
                row.comparison = {**comparison}
                flag_modified(row, "comparison")
                dirty = True
            comparisons.append(
                {
                    "match_id": row.match_id,
                    "probabilities": row.probabilities,
                    "comparison": comparison,
                    "updated_at": row.updated_at,
                    **match_context.get(row.match_id, {}),
                }
            )
        if dirty:
            await self.session.commit()

        return {
            "active": True,
            "model": model.version,
            "model_status": model.status,
            "form_window": (model.artifact or {}).get("form_window"),
            "temperature": (model.artifact or {}).get("temperature"),
            "round": next_round,
            "predictions": len(round_rows),
            "agreement_rate": round(
                sum(row.comparison.get("same_pick", False) for row in comparable)
                / len(comparable),
                4,
            )
            if comparable
            else None,
            "comparisons": comparisons,
            "backtest": {
                "games": len(backtest),
                "window_days": BACKTEST_DAYS,
                "shadow_accuracy": round(
                    sum(row.comparison.get("shadow_correct", False) for row in backtest)
                    / len(backtest),
                    4,
                )
                if backtest
                else None,
                "active_accuracy": round(
                    sum(row.comparison.get("active_correct", False) for row in active_backtest)
                    / len(active_backtest),
                    4,
                )
                if active_backtest
                else None,
                "shadow_log_loss": round(
                    sum(float(row.comparison["shadow_log_loss"]) for row in backtest)
                    / len(backtest),
                    4,
                )
                if backtest
                else None,
                "active_log_loss": round(
                    sum(float(row.comparison["active_log_loss"]) for row in active_backtest)
                    / len(active_backtest),
                    4,
                )
                if active_backtest
                else None,
                "beats_active": (
                    (
                        sum(float(row.comparison["shadow_log_loss"]) for row in active_backtest)
                        / len(active_backtest)
                    )
                    < (
                        sum(float(row.comparison["active_log_loss"]) for row in active_backtest)
                        / len(active_backtest)
                    )
                )
                if active_backtest
                else None,
                "matches": [
                    {
                        "match_id": row.match_id,
                        "probabilities": row.probabilities,
                        "comparison": row.comparison,
                        **match_context.get(row.match_id, {}),
                    }
                    for row in sorted(
                        backtest,
                        key=lambda item: match_context.get(item.match_id, {}).get("kickoff")
                        or datetime.min.replace(tzinfo=timezone.utc),
                        reverse=True,
                    )
                ],
            },
        }
