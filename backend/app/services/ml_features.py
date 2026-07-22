"""Features e inferência do ML em modo sombra (não afeta ensemble/value).

Forma alinhada ao produto: últimos FORM_WINDOW jogos.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.services.ml_history import source_name

FORM_WINDOW = 10
HOME_ADVANTAGE = 65.0
ELO_K = 20.0

FEATURES = [
    "elo_diff",
    "home_ppg",
    "away_ppg",
    "home_gf",
    "home_ga",
    "away_gf",
    "away_ga",
    "home_sample",
    "away_sample",
    "round",
    "home_corners",
    "away_corners",
    "home_cards",
    "away_cards",
    "exp_goals",
    "exp_corners",
    "exp_cards",
]

ALIASES = {
    "se palmeiras": "palmeiras",
    "cr flamengo": "flamengo",
    "ca mineiro": "atletico mineiro",
    "atletico mg": "atletico mineiro",
    "ca paranaense": "athletico paranaense",
    "athletico": "athletico paranaense",
    "sc internacional": "internacional",
    "coritiba fbc": "coritiba",
    "cr vasco da gama": "vasco da gama",
    "rb bragantino": "red bull bragantino",
    "gremio fbpa": "gremio",
    "gremio porto alegre": "gremio",
    "sao paulo fc": "sao paulo",
    "botafogo fr": "botafogo",
}

DEFAULT_CORNERS = 5.0
DEFAULT_CARDS = 2.2


def canonical_club_name(value: str) -> str:
    normalized = source_name(value)
    return ALIASES.get(normalized, normalized)


def _avg(hist: deque, index: int, default: float = 0.0) -> float:
    values = [item[index] for item in hist if item[index] is not None]
    if not values:
        return default
    return sum(values) / len(values)


@dataclass
class RollingState:
    """ELO + forma dos últimos FORM_WINDOW jogos por clube."""

    ratings: dict
    history: dict

    @classmethod
    def empty(cls) -> RollingState:
        return cls(
            ratings=defaultdict(lambda: 1500.0),
            history=defaultdict(lambda: deque(maxlen=FORM_WINDOW)),
        )

    def features(self, home: str, away: str, round_number: int | None) -> list[float]:
        home_hist = self.history[home]
        away_hist = self.history[away]
        home_gf = _avg(home_hist, 1)
        home_ga = _avg(home_hist, 2)
        away_gf = _avg(away_hist, 1)
        away_ga = _avg(away_hist, 2)
        home_corners = _avg(home_hist, 3, DEFAULT_CORNERS)
        away_corners = _avg(away_hist, 3, DEFAULT_CORNERS)
        home_cards = _avg(home_hist, 4, DEFAULT_CARDS)
        away_cards = _avg(away_hist, 4, DEFAULT_CARDS)
        return [
            self.ratings[home] + HOME_ADVANTAGE - self.ratings[away],
            _avg(home_hist, 0),
            _avg(away_hist, 0),
            home_gf,
            home_ga,
            away_gf,
            away_ga,
            len(home_hist) / float(FORM_WINDOW),
            len(away_hist) / float(FORM_WINDOW),
            float(round_number or 0) / 38.0,
            home_corners,
            away_corners,
            home_cards,
            away_cards,
            home_gf + away_gf,
            home_corners + away_corners,
            home_cards + away_cards,
        ]

    def update(
        self,
        home: str,
        away: str,
        home_score: int,
        away_score: int,
        *,
        home_corners: float | None = None,
        away_corners: float | None = None,
        home_cards: float | None = None,
        away_cards: float | None = None,
    ) -> str:
        result = (
            "home"
            if home_score > away_score
            else "away"
            if home_score < away_score
            else "draw"
        )
        home_points = 3 if result == "home" else 1 if result == "draw" else 0
        away_points = 3 if result == "away" else 1 if result == "draw" else 0
        self.history[home].append(
            (home_points, home_score, away_score, home_corners, home_cards)
        )
        self.history[away].append(
            (away_points, away_score, home_score, away_corners, away_cards)
        )
        expected = 1 / (
            1 + 10 ** ((self.ratings[away] - self.ratings[home] - HOME_ADVANTAGE) / 400)
        )
        actual = 1.0 if result == "home" else 0.5 if result == "draw" else 0.0
        delta = ELO_K * (actual - expected)
        self.ratings[home] += delta
        self.ratings[away] -= delta
        return result


def make_classifier(binary: bool = False):
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=2000, C=0.8),
    )


def _logits(pipeline, x: np.ndarray) -> np.ndarray:
    scaler, clf = pipeline[0], pipeline[1]
    standardized = scaler.transform(x)
    return standardized @ clf.coef_.T + clf.intercept_


def _softmax(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    scaled = logits / max(temperature, 1e-3)
    scaled = scaled - scaled.max(axis=1, keepdims=True)
    exp = np.exp(scaled)
    return exp / exp.sum(axis=1, keepdims=True)


def apply_class_bias(
    probabilities: np.ndarray, classes: list, class_bias: dict[str, float] | None
) -> np.ndarray:
    """Aplica calibração por classe e renormaliza as probabilidades."""
    adjusted = np.asarray(probabilities, dtype=float).copy()
    bias = class_bias or {}
    for index, label in enumerate(classes):
        adjusted[:, index] *= max(float(bias.get(str(label), 1.0)), 1e-6)
    totals = adjusted.sum(axis=1, keepdims=True)
    return adjusted / np.where(totals == 0, 1.0, totals)


def fit_draw_bias(
    pipeline, x_cal: np.ndarray, y_cal: list, classes: list, temperature: float
) -> dict[str, float]:
    """Calibra empate usando somente a fatia cronológica de validação."""
    if "draw" not in classes or len(x_cal) < 30 or "draw" not in y_cal:
        return {}
    base = _softmax(_logits(pipeline, np.asarray(x_cal, dtype=float)), temperature)
    best_factor, best_loss = 1.0, float(log_loss(y_cal, base, labels=classes))
    for factor in (0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.35, 1.5, 1.7):
        candidate = apply_class_bias(base, classes, {"draw": factor})
        loss = float(log_loss(y_cal, candidate, labels=classes))
        if loss < best_loss:
            best_factor, best_loss = factor, loss
    return {"draw": best_factor}


def fit_temperature(pipeline, x_cal: np.ndarray, y_cal: list, classes: list) -> float:
    """Temperatura que minimiza log loss na fatia de calibração (só treino)."""
    if len(x_cal) < 20 or len(set(y_cal)) < 2:
        return 1.0
    best_t, best_loss = 1.0, float("inf")
    binary = len(classes) == 2 and getattr(pipeline[-1], "coef_", np.zeros((1,))).shape[0] == 1
    for temperature in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5):
        try:
            if binary:
                probs = binary_probabilities(pipeline, np.asarray(x_cal, dtype=float), temperature)
            else:
                probs = _softmax(_logits(pipeline, np.asarray(x_cal, dtype=float)), temperature)
            loss = float(log_loss(y_cal, probs, labels=classes))
        except ValueError:
            continue
        if loss < best_loss:
            best_t, best_loss = temperature, loss
    return best_t


def serialize_pipeline(
    pipeline,
    *,
    temperature: float = 1.0,
    class_bias: dict[str, float] | None = None,
    extra: dict | None = None,
) -> dict:
    scaler, clf = pipeline[0], pipeline[1]
    payload = {
        "classes": clf.classes_.tolist(),
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "coefficients": clf.coef_.tolist(),
        "intercept": clf.intercept_.tolist(),
        "temperature": float(temperature),
        "class_bias": class_bias or {},
        "feature_names": FEATURES,
        "form_window": FORM_WINDOW,
    }
    if extra:
        payload.update(extra)
    return payload


def binary_probabilities(pipeline, x: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    """Retorna matriz (n, 2) com P(classe0), P(classe1) na ordem de classes_."""
    logits = _logits(pipeline, np.asarray(x, dtype=float))
    if logits.ndim == 1:
        logits = logits.reshape(-1, 1)
    if logits.shape[1] == 1:
        z = logits[:, 0] / max(temperature, 1e-3)
        positive = 1 / (1 + np.exp(-z))
        # coef binário do sklearn aponta para classes_[1]
        return np.column_stack((1 - positive, positive))
    return _softmax(logits, temperature)


def predict_proba_from_artifact(values: list[float], artifact: dict) -> dict[str, float]:
    mean = np.asarray(artifact["scaler_mean"], dtype=float)
    scale = np.asarray(artifact["scaler_scale"], dtype=float)
    coefficients = np.asarray(artifact["coefficients"], dtype=float)
    intercept = np.asarray(artifact["intercept"], dtype=float)
    classes = artifact["classes"]
    temperature = float(artifact.get("temperature") or 1.0)
    standardized = (np.asarray(values, dtype=float) - mean) / np.where(scale == 0, 1, scale)
    logits = coefficients @ standardized + intercept
    logits = np.asarray(logits, dtype=float).ravel() / max(temperature, 1e-3)
    logits = logits - logits.max()
    exp = np.exp(logits)
    vector = exp / exp.sum()
    vector = apply_class_bias(
        vector.reshape(1, -1), classes, artifact.get("class_bias")
    )[0]
    return {label: round(float(vector[i]), 4) for i, label in enumerate(classes)}


def predict_binary_from_artifact(values: list[float], artifact: dict) -> float:
    mean = np.asarray(artifact["scaler_mean"], dtype=float)
    scale = np.asarray(artifact["scaler_scale"], dtype=float)
    coefficients = np.asarray(artifact["coefficients"], dtype=float)
    intercept = np.asarray(artifact["intercept"], dtype=float)
    temperature = float(artifact.get("temperature") or 1.0)
    classes = list(artifact.get("classes") or [0, 1])
    standardized = (np.asarray(values, dtype=float) - mean) / np.where(scale == 0, 1, scale)
    logits = coefficients @ standardized + intercept
    logits = np.asarray(logits, dtype=float).ravel() / max(temperature, 1e-3)
    if len(logits) == 1:
        # Binary LR: logit da classes_[1]
        positive = float(1 / (1 + np.exp(-logits[0])))
        if classes[-1] != 1 and 1 in classes and classes.index(1) == 0:
            positive = 1.0 - positive
        return round(min(1.0, max(0.0, positive)), 4)
    logits = logits - logits.max()
    exp = np.exp(logits)
    vector = exp / exp.sum()
    pos_idx = classes.index(1) if 1 in classes else -1
    return round(float(vector[pos_idx]), 4)
