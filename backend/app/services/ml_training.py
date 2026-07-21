from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
from sklearn.metrics import accuracy_score, log_loss
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ml_entities import MlMatch, MlModelRun, MlSeason, MlTeam, MlTeamMatchStat
from app.services.ml_features import (
    FEATURES,
    FORM_WINDOW,
    RollingState,
    canonical_club_name,
    fit_temperature,
    make_classifier,
    serialize_pipeline,
)
from app.services.ml_history import source_name


MARKETS = {
    "goals_over_2_5": {
        "label": "Mais de 2,5 gols",
        "line": 2.5,
        "minimum_train": 150,
        "minimum_test": 40,
    },
    "corners_over_9_5": {
        "label": "Mais de 9,5 escanteios",
        "line": 9.5,
        "minimum_train": 150,
        "minimum_test": 40,
    },
    "cards_over_4_5": {
        "label": "Mais de 4,5 cartões",
        "line": 4.5,
        "minimum_train": 150,
        "minimum_test": 40,
    },
}


def _number(value) -> float | None:
    try:
        return float(value) if value is not None and not isinstance(value, (dict, list)) else None
    except (TypeError, ValueError):
        return None


def historical_metric(metrics: dict, market: str) -> float | None:
    aliases = {
        "corners": {"corner_kicks", "corners", "escanteios", "corner"},
        "cards": {"yellow_cards", "cards", "cartoes", "cartoes_amarelos", "amarelos"},
    }[market]
    for key, value in (metrics or {}).items():
        normalized = source_name(str(key)).replace(" ", "_")
        if normalized in aliases:
            direct = _number(value)
            if direct is not None:
                return direct
            if isinstance(value, list):
                return float(len(value))
            if isinstance(value, dict):
                yellow = next(
                    (
                        _number(v)
                        for k, v in value.items()
                        if source_name(str(k)) in {"yellow", "amarelo", "amarelos"}
                    ),
                    None,
                )
                if yellow is not None:
                    return yellow
    return None


def serialize_binary_model(x_train, y_train, x_test, y_test, config: dict) -> tuple[dict | None, dict]:
    coverage = {"train_samples": len(x_train), "test_samples": len(x_test)}
    if (
        len(x_train) < config["minimum_train"]
        or len(x_test) < config["minimum_test"]
        or len(set(y_train)) < 2
        or len(set(y_test)) < 2
    ):
        return None, {**coverage, "available": False, "reason": "amostra histórica insuficiente"}

    x_train_arr = np.asarray(x_train, dtype=float)
    y_train_arr = np.asarray(y_train)
    # Calibração: últimos 15% do treino (já ordenado cronologicamente).
    cal_size = max(20, int(len(x_train_arr) * 0.15))
    if len(x_train_arr) - cal_size < config["minimum_train"] // 2:
        fit_x, fit_y = x_train_arr, y_train_arr
        cal_x, cal_y = x_train_arr[-cal_size:], y_train[-cal_size:]
    else:
        fit_x, fit_y = x_train_arr[:-cal_size], y_train_arr[:-cal_size]
        cal_x, cal_y = x_train_arr[-cal_size:], y_train[-cal_size:]

    pipeline = make_classifier(binary=True)
    pipeline.fit(fit_x, fit_y)
    temperature = fit_temperature(pipeline, cal_x, list(cal_y), pipeline[-1].classes_.tolist())
    # Refit no treino completo com a temperatura encontrada.
    pipeline.fit(x_train_arr, y_train_arr)

    from app.services.ml_features import binary_probabilities

    probs = binary_probabilities(pipeline, np.asarray(x_test, dtype=float), temperature)
    positive_index = pipeline[-1].classes_.tolist().index(1)
    positive = probs[:, positive_index]
    predictions = (positive >= 0.5).astype(int)
    prior = float(sum(y_train) / len(y_train))
    baseline = np.full(len(y_test), prior)
    brier = float(np.mean((positive - np.asarray(y_test)) ** 2))
    baseline_brier = float(np.mean((baseline - np.asarray(y_test)) ** 2))
    loss = float(log_loss(y_test, probs, labels=pipeline[-1].classes_))
    baseline_loss = float(
        log_loss(y_test, np.column_stack((1 - baseline, baseline)), labels=[0, 1])
    )
    metrics = {
        **coverage,
        "available": True,
        "accuracy": round(float(accuracy_score(y_test, predictions)), 4),
        "log_loss": round(loss, 4),
        "brier": round(brier, 4),
        "baseline_log_loss": round(baseline_loss, 4),
        "baseline_brier": round(baseline_brier, 4),
        "temperature": round(temperature, 3),
        "approved": loss < baseline_loss and brier < baseline_brier,
    }
    artifact = serialize_pipeline(
        pipeline,
        temperature=temperature,
        extra={"label": config["label"], "line": config["line"]},
    )
    return artifact, metrics


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
        rows = (
            await self.session.execute(
                select(MlMatch, MlTeam.normalized_name, MlTeam.id)
                .join(MlTeam, MlTeam.id == MlMatch.home_team_id)
                .where(MlMatch.season_id.in_(eligible_ids), MlMatch.quality_status == "valid")
                .order_by(MlMatch.kickoff, MlMatch.id)
            )
        ).all()
        away_names = dict(
            (await self.session.execute(select(MlTeam.id, MlTeam.normalized_name))).all()
        )
        stat_rows = list(
            await self.session.scalars(
                select(MlTeamMatchStat).where(
                    MlTeamMatchStat.match_id.in_([row[0].id for row in rows]),
                    MlTeamMatchStat.period == "full_time",
                )
            )
        )
        market_sides: dict[int, dict[str, dict[bool, float]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        for stat in stat_rows:
            for market in ("corners", "cards"):
                value = historical_metric(stat.metrics or {}, market)
                if value is not None:
                    market_sides[stat.match_id][market][stat.is_home] = value

        state = RollingState.empty()
        x_train, y_train, x_test, y_test = [], [], [], []
        market_sets = {
            key: {"x_train": [], "y_train": [], "x_test": [], "y_test": []} for key in MARKETS
        }
        market_samples: dict[str, list[tuple[datetime, list[float], int]]] = {
            key: [] for key in MARKETS
        }

        for match, home_name, _ in rows:
            home = canonical_club_name(home_name)
            away = canonical_club_name(away_names[match.away_team_id])
            features = state.features(home, away, match.round_number)
            result = (
                "home"
                if match.home_score > match.away_score
                else "away"
                if match.home_score < match.away_score
                else "draw"
            )
            target_x, target_y = (
                (x_train, y_train) if match.season_id in train_ids else (x_test, y_test)
            )
            target_x.append(features)
            target_y.append(result)

            corners = market_sides[match.id]["corners"]
            cards = market_sides[match.id]["cards"]
            corner_total = (
                corners.get(True, 0) + corners.get(False, 0) if len(corners) == 2 else None
            )
            card_total = cards.get(True, 0) + cards.get(False, 0) if len(cards) == 2 else None
            values = {
                "goals_over_2_5": float(match.home_score + match.away_score),
                "corners_over_9_5": corner_total,
                "cards_over_4_5": card_total,
            }
            split = "train" if match.season_id in train_ids else "test"
            for market, value in values.items():
                if value is None:
                    continue
                market_sets[market][f"x_{split}"].append(features)
                target = int(value > MARKETS[market]["line"])
                market_sets[market][f"y_{split}"].append(target)
                market_samples[market].append((match.kickoff, features, target))

            state.update(
                home,
                away,
                match.home_score,
                match.away_score,
                home_corners=corners.get(True),
                away_corners=corners.get(False),
                home_cards=cards.get(True),
                away_cards=cards.get(False),
            )

        if not x_train or not x_test:
            raise ValueError("Amostra de treino ou teste ficou vazia")

        x_train_arr = np.asarray(x_train, dtype=float)
        cal_size = max(30, int(len(x_train_arr) * 0.15))
        fit_x, fit_y = x_train_arr[:-cal_size], y_train[:-cal_size]
        cal_x, cal_y = x_train_arr[-cal_size:], y_train[-cal_size:]
        if len(fit_x) < 50:
            fit_x, fit_y = x_train_arr, y_train
            cal_x, cal_y = x_train_arr[-cal_size:], y_train[-cal_size:]

        pipeline = make_classifier()
        pipeline.fit(fit_x, fit_y)
        classes = pipeline[-1].classes_.tolist()
        temperature = fit_temperature(pipeline, cal_x, list(cal_y), classes)
        pipeline.fit(x_train_arr, y_train)

        from app.services.ml_features import _logits, _softmax

        probabilities = _softmax(
            _logits(pipeline, np.asarray(x_test, dtype=float)), temperature
        )
        predictions = [classes[int(i)] for i in np.argmax(probabilities, axis=1)]
        accuracy = float(accuracy_score(y_test, predictions))
        loss = float(log_loss(y_test, probabilities, labels=classes))
        brier = float(
            np.mean(
                np.sum(
                    (
                        probabilities
                        - np.eye(len(classes))[[classes.index(label) for label in y_test]]
                    )
                    ** 2,
                    axis=1,
                )
            )
        )
        majority = max(set(y_train), key=y_train.count)
        baseline_accuracy = float(sum(label == majority for label in y_test) / len(y_test))
        class_priors = np.asarray([y_train.count(label) / len(y_train) for label in classes])
        baseline_probabilities = np.tile(class_priors, (len(y_test), 1))
        baseline_loss = float(log_loss(y_test, baseline_probabilities, labels=classes))
        baseline_brier = float(
            np.mean(
                np.sum(
                    (
                        baseline_probabilities
                        - np.eye(len(classes))[[classes.index(label) for label in y_test]]
                    )
                    ** 2,
                    axis=1,
                )
            )
        )
        approved = loss < baseline_loss and brier < baseline_brier

        market_artifacts, market_metrics = {}, {}
        for market, dataset in market_sets.items():
            config = MARKETS[market]
            validation = "temporadas anteriores → temporada mais recente"
            if (
                len(dataset["x_train"]) < config["minimum_train"]
                or len(dataset["x_test"]) < config["minimum_test"]
            ):
                samples = sorted(market_samples[market], key=lambda item: item[0])
                minimum = config["minimum_train"] + config["minimum_test"]
                if len(samples) >= minimum:
                    cut = max(config["minimum_train"], int(len(samples) * 0.8))
                    cut = min(cut, len(samples) - config["minimum_test"])
                    dataset = {
                        "x_train": [item[1] for item in samples[:cut]],
                        "y_train": [item[2] for item in samples[:cut]],
                        "x_test": [item[1] for item in samples[cut:]],
                        "y_test": [item[2] for item in samples[cut:]],
                    }
                    validation = "divisão temporal 80/20 da amostra disponível"
            market_artifact, metrics = serialize_binary_model(
                dataset["x_train"],
                dataset["y_train"],
                dataset["x_test"],
                dataset["y_test"],
                config,
            )
            metrics["validation"] = validation
            market_metrics[market] = metrics
            if market_artifact:
                market_artifacts[market] = market_artifact

        version = f"result-logreg-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        run = MlModelRun(
            version=version,
            algorithm="multinomial_logistic_regression_v2",
            status="approved" if approved else "rejected",
            train_seasons=[s.year for s in eligible[:-1]],
            test_season=test_season.year,
            train_samples=len(x_train),
            test_samples=len(x_test),
            features=FEATURES,
            metrics={
                "accuracy": round(accuracy, 4),
                "log_loss": round(loss, 4),
                "brier": round(brier, 4),
                "majority_baseline_accuracy": round(baseline_accuracy, 4),
                "baseline_log_loss": round(baseline_loss, 4),
                "baseline_brier": round(baseline_brier, 4),
                "temperature": round(temperature, 3),
                "form_window": FORM_WINDOW,
                "approved": approved,
                "markets": market_metrics,
            },
            artifact={
                **serialize_pipeline(pipeline, temperature=temperature),
                "market_models": market_artifacts,
            },
        )
        self.session.add(run)
        await self.session.commit()
        return {
            "version": version,
            "train_seasons": run.train_seasons,
            "test_season": run.test_season,
            "train_samples": run.train_samples,
            "test_samples": run.test_samples,
            "status": run.status,
            "metrics": run.metrics,
            "markets": market_metrics,
        }
