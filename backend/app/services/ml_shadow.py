from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from math import log

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Competition, Match, MatchStatus, Prediction, Team
from app.models.ml_entities import MlMatch, MlModelRun, MlSeason, MlShadowPrediction, MlTeam
from app.services.ml_training import FEATURES, canonical_club_name


class MlShadowService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def round_number(match: Match) -> int | None:
        metadata = match.metadata_ or {}
        values = [
            metadata.get("matchday"), metadata.get("round"),
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
        candidates = list(await self.session.scalars(
            select(Match)
            .join(Competition, Competition.id == Match.competition_id)
            .where(
                Competition.active.is_(True),
                Competition.name.ilike("%Série A%"),
                Match.status == MatchStatus.scheduled,
                Match.kickoff >= now - timedelta(hours=6),
            )
            .order_by(Match.kickoff)
        ))
        return next(
            (number for match in candidates if (number := self.round_number(match)) is not None),
            None,
        )

    async def materialize(self) -> dict:
        model = await self.session.scalar(select(MlModelRun).where(
            MlModelRun.status.in_(["approved", "rejected"])
        ).order_by(MlModelRun.created_at.desc()))
        if not model:
            raise ValueError("Nenhum modelo treinado para executar em modo sombra")

        eligible_seasons = list(await self.session.scalars(select(MlSeason).where(
            MlSeason.quality_summary["eligible_for_training"].as_boolean().is_(True)
        )))
        season_ids = {season.id for season in eligible_seasons}
        historical = (await self.session.execute(
            select(MlMatch, MlTeam.normalized_name)
            .join(MlTeam, MlTeam.id == MlMatch.home_team_id)
            .where(MlMatch.season_id.in_(season_ids), MlMatch.quality_status == "valid")
            .order_by(MlMatch.kickoff, MlMatch.id)
        )).all()
        team_names = dict((await self.session.execute(
            select(MlTeam.id, MlTeam.normalized_name)
        )).all())
        ratings: dict[str, float] = defaultdict(lambda: 1500.0)
        history: dict[str, deque] = defaultdict(lambda: deque(maxlen=5))
        for match, raw_home_name in historical:
            home = canonical_club_name(raw_home_name)
            away = canonical_club_name(team_names[match.away_team_id])
            result = "home" if match.home_score > match.away_score else (
                "away" if match.home_score < match.away_score else "draw"
            )
            home_points = 3 if result == "home" else 1 if result == "draw" else 0
            away_points = 3 if result == "away" else 1 if result == "draw" else 0
            history[home].append((home_points, match.home_score, match.away_score))
            history[away].append((away_points, match.away_score, match.home_score))
            expected = 1 / (1 + 10 ** ((ratings[away] - ratings[home] - 65) / 400))
            actual = 1.0 if result == "home" else 0.5 if result == "draw" else 0.0
            delta = 20 * (actual - expected)
            ratings[home] += delta
            ratings[away] -= delta

        current_team_names = dict((await self.session.execute(select(Team.id, Team.name))).all())
        artifact = model.artifact or {}
        mean = np.asarray(artifact["scaler_mean"], dtype=float)
        scale = np.asarray(artifact["scaler_scale"], dtype=float)
        coefficients = np.asarray(artifact["coefficients"], dtype=float)
        intercept = np.asarray(artifact["intercept"], dtype=float)
        classes = artifact["classes"]
        created = updated = 0

        def feature_values(match: Match, home: str, away: str) -> list[float]:
            home_hist, away_hist = history[home], history[away]
            def avg(hist, index):
                return sum(item[index] for item in hist) / len(hist) if hist else 0.0
            return [
                ratings[home] + 65.0 - ratings[away],
                avg(home_hist, 0), avg(away_hist, 0), avg(home_hist, 1), avg(home_hist, 2),
                avg(away_hist, 1), avg(away_hist, 2), len(home_hist) / 5.0,
                len(away_hist) / 5.0, float(self.round_number(match) or 0) / 38.0,
            ]

        def predict(values: list[float]) -> dict:
            standardized = (np.asarray(values) - mean) / np.where(scale == 0, 1, scale)
            logits = coefficients @ standardized + intercept
            exp_logits = np.exp(logits - np.max(logits))
            vector = exp_logits / exp_logits.sum()
            return {label: round(float(vector[i]), 4) for i, label in enumerate(classes)}

        def update_state(home: str, away: str, home_score: int, away_score: int) -> str:
            result = "home" if home_score > away_score else "away" if home_score < away_score else "draw"
            home_points = 3 if result == "home" else 1 if result == "draw" else 0
            away_points = 3 if result == "away" else 1 if result == "draw" else 0
            history[home].append((home_points, home_score, away_score))
            history[away].append((away_points, away_score, home_score))
            expected = 1 / (1 + 10 ** ((ratings[away] - ratings[home] - 65) / 400))
            actual = 1.0 if result == "home" else 0.5 if result == "draw" else 0.0
            delta = 20 * (actual - expected)
            ratings[home] += delta
            ratings[away] -= delta
            return result

        async def save_prediction(
            match: Match, home: str, away: str, values: list[float],
            probabilities: dict, outcome: str | None = None,
        ) -> None:
            nonlocal created, updated
            active = await self.session.scalar(select(Prediction).where(
                Prediction.match_id == match.id
            ).order_by(Prediction.created_at.desc()))
            active_probs = (active.probabilities or {}) if active else {}
            active_pick = max(("home", "draw", "away"), key=lambda key: active_probs.get(key, 0))
            shadow_pick = max(("home", "draw", "away"), key=lambda key: probabilities.get(key, 0))
            comparison = {
                "active_model": active.model_version if active else None,
                "active_probabilities": {key: active_probs.get(key) for key in ("home", "draw", "away")},
                "active_pick": active_pick if active else None, "shadow_pick": shadow_pick,
                "same_pick": bool(active and active_pick == shadow_pick),
                "max_probability_delta": round(max(
                    abs(probabilities.get(key, 0) - float(active_probs.get(key) or 0))
                    for key in ("home", "draw", "away")
                ), 4) if active else None,
            }
            if outcome:
                comparison.update({
                    "outcome": outcome,
                    "active_correct": bool(active and active_pick == outcome),
                    "shadow_correct": shadow_pick == outcome,
                    "active_log_loss": round(-log(max(float(active_probs.get(outcome) or 0), 1e-6)), 4)
                    if active else None,
                    "shadow_log_loss": round(-log(max(float(probabilities.get(outcome) or 0), 1e-6)), 4),
                    "mode": "backtest",
                })
            else:
                comparison["mode"] = "upcoming"
            record = await self.session.scalar(select(MlShadowPrediction).where(
                MlShadowPrediction.match_id == match.id,
                MlShadowPrediction.model_run_id == model.id,
            ))
            payload_features = dict(zip(FEATURES, [round(float(value), 4) for value in values]))
            payload_features.update({"home_key": home, "away_key": away})
            if record:
                record.probabilities = probabilities
                record.features = payload_features
                record.comparison = comparison
                updated += 1
            else:
                self.session.add(MlShadowPrediction(
                    match_id=match.id, model_run_id=model.id, probabilities=probabilities,
                    features=payload_features, comparison=comparison,
                ))
                created += 1

        now = datetime.now(timezone.utc)
        next_round = await self.next_round_number(now)
        season_start = datetime(now.year, 1, 1, tzinfo=timezone.utc)
        recent_cutoff = now - timedelta(days=7)
        finished = (await self.session.execute(
            select(Match, Team.name).join(Team, Team.id == Match.home_team_id).where(
                Match.status == MatchStatus.finished,
                Match.kickoff >= season_start,
                Match.home_score.is_not(None), Match.away_score.is_not(None),
            ).order_by(Match.kickoff, Match.id)
        )).all()
        backtested = 0
        for match, raw_home_name in finished:
            home = canonical_club_name(raw_home_name)
            away = canonical_club_name(current_team_names[match.away_team_id])
            values = feature_values(match, home, away)
            probabilities = predict(values)
            outcome = "home" if match.home_score > match.away_score else (
                "away" if match.home_score < match.away_score else "draw"
            )
            if match.kickoff >= recent_cutoff:
                await save_prediction(match, home, away, values, probabilities, outcome)
                backtested += 1
            update_state(home, away, match.home_score, match.away_score)

        current_candidates = (await self.session.execute(
            select(Match, Team.name)
            .join(Team, Team.id == Match.home_team_id)
            .join(Competition, Competition.id == Match.competition_id)
            .where(
                Competition.active.is_(True),
                Competition.name.ilike("%Série A%"),
                Match.status == MatchStatus.scheduled,
                Match.kickoff >= now,
            ).order_by(Match.kickoff)
        )).all()
        current = [
            row for row in current_candidates
            if self.round_number(row[0]) == next_round
        ]
        for match, raw_home_name in current:
            home = canonical_club_name(raw_home_name)
            away = canonical_club_name(current_team_names[match.away_team_id])
            values = feature_values(match, home, away)
            await save_prediction(match, home, away, values, predict(values))
        await self.session.commit()
        return {"model": model.version, "round": next_round, "matches": len(current), "backtested": backtested,
                "created": created, "updated": updated}

    async def overview(self) -> dict:
        model = await self.session.scalar(select(MlModelRun).where(
            MlModelRun.status.in_(["approved", "rejected"])
        ).order_by(MlModelRun.created_at.desc()))
        if not model:
            return {"active": False, "predictions": 0, "comparisons": []}
        rows = list(await self.session.scalars(select(MlShadowPrediction).where(
            MlShadowPrediction.model_run_id == model.id
        ).order_by(MlShadowPrediction.updated_at.desc())))
        match_ids = [row.match_id for row in rows]
        match_rows = (await self.session.execute(
            select(Match, Team.name)
            .join(Team, Team.id == Match.home_team_id)
            .where(Match.id.in_(match_ids))
        )).all() if match_ids else []
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
        next_round = await self.next_round_number(datetime.now(timezone.utc))
        round_rows = [
            row for row in rows
            if match_context.get(row.match_id, {}).get("round") == next_round
        ]
        comparable = [row for row in round_rows if row.comparison.get("active_pick")]
        backtest = [row for row in rows if row.comparison.get("mode") == "backtest"]
        active_backtest = [row for row in backtest if row.comparison.get("active_log_loss") is not None]
        ordered = sorted(
            rows,
            key=lambda row: float(row.comparison.get("max_probability_delta") or 0),
            reverse=True,
        )
        return {
            "active": True, "model": model.version, "model_status": model.status,
            "round": next_round,
            "predictions": len(round_rows),
            "agreement_rate": round(sum(row.comparison.get("same_pick", False) for row in comparable)
                                    / len(comparable), 4) if comparable else None,
            "comparisons": [{
                "match_id": row.match_id, "probabilities": row.probabilities,
                "comparison": row.comparison, "updated_at": row.updated_at,
                **match_context.get(row.match_id, {}),
            } for row in ordered if row in round_rows],
            "backtest": {
                "games": len(backtest),
                "shadow_accuracy": round(sum(row.comparison.get("shadow_correct", False) for row in backtest)
                                         / len(backtest), 4) if backtest else None,
                "active_accuracy": round(sum(row.comparison.get("active_correct", False) for row in active_backtest)
                                         / len(active_backtest), 4) if active_backtest else None,
                "shadow_log_loss": round(sum(float(row.comparison["shadow_log_loss"]) for row in backtest)
                                         / len(backtest), 4) if backtest else None,
                "active_log_loss": round(sum(float(row.comparison["active_log_loss"]) for row in active_backtest)
                                         / len(active_backtest), 4) if active_backtest else None,
                "matches": [{
                    "match_id": row.match_id, "probabilities": row.probabilities,
                    "comparison": row.comparison, **match_context.get(row.match_id, {}),
                } for row in sorted(backtest, key=lambda item: match_context.get(item.match_id, {}).get("kickoff") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)],
            },
        }
