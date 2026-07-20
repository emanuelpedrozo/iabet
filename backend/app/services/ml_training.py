from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ml_entities import MlMatch, MlModelRun, MlSeason, MlTeam
from app.services.ml_history import source_name


FEATURES = [
    "elo_diff", "home_ppg_5", "away_ppg_5", "home_gf_5", "home_ga_5",
    "away_gf_5", "away_ga_5", "home_sample", "away_sample", "round",
]
ALIASES = {
    "se palmeiras": "palmeiras", "cr flamengo": "flamengo",
    "ca mineiro": "atletico mineiro", "atletico mg": "atletico mineiro",
    "ca paranaense": "athletico paranaense", "athletico": "athletico paranaense",
    "sc internacional": "internacional", "coritiba fbc": "coritiba",
    "cr vasco da gama": "vasco da gama", "rb bragantino": "red bull bragantino",
    "gremio fbpa": "gremio", "gremio porto alegre": "gremio",
    "sao paulo fc": "sao paulo", "botafogo fr": "botafogo",
}


def canonical_club_name(value: str) -> str:
    normalized = source_name(value)
    return ALIASES.get(normalized, normalized)


class MlTrainingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def train_result_baseline(self) -> dict:
        seasons = list(await self.session.scalars(select(MlSeason).order_by(MlSeason.year)))
        eligible = [s for s in seasons if (s.quality_summary or {}).get("eligible_for_training")]
        if len(eligible) < 2:
            raise ValueError("Importe e valide pelo menos duas temporadas antes do treinamento")
        test_season = eligible[-1]
        train_ids = {s.id for s in eligible[:-1]}
        eligible_ids = train_ids | {test_season.id}
        rows = (await self.session.execute(
            select(MlMatch, MlTeam.normalized_name, MlTeam.id)
            .join(MlTeam, MlTeam.id == MlMatch.home_team_id)
            .where(MlMatch.season_id.in_(eligible_ids), MlMatch.quality_status == "valid")
            .order_by(MlMatch.kickoff, MlMatch.id)
        )).all()
        away_names = dict((await self.session.execute(select(MlTeam.id, MlTeam.normalized_name))).all())

        ratings: dict[str, float] = defaultdict(lambda: 1500.0)
        history: dict[str, deque] = defaultdict(lambda: deque(maxlen=5))
        x_train, y_train, x_test, y_test = [], [], [], []
        for match, home_name, _ in rows:
            home_name = canonical_club_name(home_name)
            away_name = canonical_club_name(away_names[match.away_team_id])
            home_hist, away_hist = history[home_name], history[away_name]

            def avg(hist, index):
                return sum(item[index] for item in hist) / len(hist) if hist else 0.0

            features = [
                ratings[home_name] + 65.0 - ratings[away_name],
                avg(home_hist, 0), avg(away_hist, 0),
                avg(home_hist, 1), avg(home_hist, 2),
                avg(away_hist, 1), avg(away_hist, 2),
                len(home_hist) / 5.0, len(away_hist) / 5.0,
                float(match.round_number or 0) / 38.0,
            ]
            result = "home" if match.home_score > match.away_score else (
                "away" if match.home_score < match.away_score else "draw"
            )
            target_x, target_y = ((x_train, y_train) if match.season_id in train_ids
                                  else (x_test, y_test))
            target_x.append(features)
            target_y.append(result)

            home_points = 3 if result == "home" else 1 if result == "draw" else 0
            away_points = 3 if result == "away" else 1 if result == "draw" else 0
            home_hist.append((home_points, match.home_score, match.away_score))
            away_hist.append((away_points, match.away_score, match.home_score))
            expected = 1 / (1 + 10 ** ((ratings[away_name] - ratings[home_name] - 65) / 400))
            actual = 1.0 if result == "home" else 0.5 if result == "draw" else 0.0
            delta = 20 * (actual - expected)
            ratings[home_name] += delta
            ratings[away_name] -= delta

        if not x_train or not x_test:
            raise ValueError("Amostra de treino ou teste ficou vazia")
        pipeline = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=0.8))
        pipeline.fit(np.asarray(x_train), np.asarray(y_train))
        probabilities = pipeline.predict_proba(np.asarray(x_test))
        predictions = pipeline.predict(np.asarray(x_test))
        classes = pipeline[-1].classes_.tolist()
        accuracy = float(accuracy_score(y_test, predictions))
        loss = float(log_loss(y_test, probabilities, labels=classes))
        brier = float(np.mean(np.sum((probabilities - np.eye(len(classes))[
            [classes.index(label) for label in y_test]
        ]) ** 2, axis=1)))
        majority = max(set(y_train), key=y_train.count)
        baseline_accuracy = float(sum(label == majority for label in y_test) / len(y_test))
        class_priors = np.asarray([y_train.count(label) / len(y_train) for label in classes])
        baseline_probabilities = np.tile(class_priors, (len(y_test), 1))
        baseline_loss = float(log_loss(y_test, baseline_probabilities, labels=classes))
        baseline_brier = float(np.mean(np.sum((baseline_probabilities - np.eye(len(classes))[
            [classes.index(label) for label in y_test]
        ]) ** 2, axis=1)))
        # Em apostas interessa a probabilidade calibrada, não apenas acertar a classe
        # mais frequente. O candidato só passa se superar as duas métricas probabilísticas.
        approved = loss < baseline_loss and brier < baseline_brier
        scaler, classifier = pipeline[0], pipeline[-1]
        version = f"result-logreg-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        run = MlModelRun(
            version=version,
            algorithm="multinomial_logistic_regression",
            status="approved" if approved else "rejected",
            train_seasons=[s.year for s in eligible[:-1]],
            test_season=test_season.year,
            train_samples=len(x_train),
            test_samples=len(x_test),
            features=FEATURES,
            metrics={
                "accuracy": round(accuracy, 4), "log_loss": round(loss, 4),
                "brier": round(brier, 4), "majority_baseline_accuracy": round(baseline_accuracy, 4),
                "baseline_log_loss": round(baseline_loss, 4),
                "baseline_brier": round(baseline_brier, 4),
                "approved": approved,
            },
            artifact={
                "classes": classes, "scaler_mean": scaler.mean_.tolist(),
                "scaler_scale": scaler.scale_.tolist(), "coefficients": classifier.coef_.tolist(),
                "intercept": classifier.intercept_.tolist(),
            },
        )
        self.session.add(run)
        await self.session.commit()
        return {
            "version": version, "train_seasons": run.train_seasons,
            "test_season": run.test_season, "train_samples": run.train_samples,
            "test_samples": run.test_samples, "status": run.status, "metrics": run.metrics,
        }
