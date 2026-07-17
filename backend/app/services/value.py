"""Value bets: de-vig, limiares, consenso, movimento e confiança."""
from __future__ import annotations

import statistics

from app.services.stat_markets import STAT_LINES, prob_key

MIN_EV = 0.03
MIN_KELLY = 0.005
MIN_EDGE = 0.02
SOFT_ODD_PREMIUM = 1.08  # odd > 8% acima da mediana → value fofo
MOVE_DROP_THRESHOLD = -0.03  # queda de 3%+ na odd
SAMPLE_GAMES_SOFT = 5
MIN_RECOMMENDED_PROBABILITY = 0.30
MIN_RECOMMENDED_CONFIDENCE = 0.55
MAX_RECOMMENDED_ODD = 4.50
STAT_MARKETS = frozenset({"corners", "cards", "shots"})

MARKET_KEYS = {
    ("match_result", "home"): "home",
    ("match_result", "draw"): "draw",
    ("match_result", "away"): "away",
    ("goals_2_5", "over"): "over_2_5",
    ("goals_2_5", "under"): "under_2_5",
    ("btts", "yes"): "btts_yes",
    ("btts", "no"): "btts_no",
}


def kelly(probability: float, odd: float, fraction: float = 0.25) -> float:
    b = odd - 1
    raw = (probability * odd - 1) / b if b else 0
    return max(0, raw) * fraction


def classify(edge: float) -> str:
    return (
        "muito forte"
        if edge >= 0.10
        else "forte"
        if edge >= 0.06
        else "moderada"
        if edge >= 0.03
        else "fraca"
    )


def multiplicative_devig(prices: dict[str, float]) -> dict[str, float]:
    implied = {k: 1.0 / v for k, v in prices.items() if v and v > 1}
    total = sum(implied.values())
    if total <= 0:
        return implied
    return {k: v / total for k, v in implied.items()}


def median_odd(prices: list[float]) -> float | None:
    clean = [p for p in prices if p and p > 1]
    if not clean:
        return None
    return float(statistics.median(clean))


def odds_move_pct(oldest: float, newest: float) -> float | None:
    if not oldest or oldest <= 1 or not newest:
        return None
    return (newest - oldest) / oldest


def totals_prob_key(selection: str, line: float | None) -> str | None:
    sel = selection.lower()
    if sel not in ("over", "under"):
        return None
    if line is None or abs(line - 2.5) < 1e-6:
        return f"{sel}_2_5"
    if abs(line - 1.5) < 1e-6:
        return f"{sel}_1_5"
    if abs(line - 3.5) < 1e-6:
        return f"{sel}_3_5"
    return None


def allowed_totals_line(line: float | None) -> bool:
    if line is None:
        return True
    return any(abs(line - x) < 1e-6 for x in (1.5, 2.5, 3.5))


def allowed_stat_line(market: str, line: float | None) -> bool:
    if market not in STAT_MARKETS or line is None:
        return False
    return any(abs(line - x) < 1e-6 for x in STAT_LINES[market])


def confidence_score(
    pred: dict,
    market: str,
    selection: str,
    edge: float,
    kelly_fraction: float,
    *,
    home_n_games: int | None = None,
    away_n_games: int | None = None,
    has_team_stats: bool = False,
    soft_vs_consensus: bool = False,
    odds_falling: bool = False,
    h2h_over_boost: bool = False,
) -> float:
    key = MARKET_KEYS.get((market, selection))
    if key is None and market == "goals_2_5":
        key = totals_prob_key(selection, 2.5)
    models = pred.get("models") or {}
    poisson = models.get("poisson") or {}
    elo = models.get("elo") or {}
    if key and key in ("home", "draw", "away") and key in poisson and key in elo:
        gap = abs(float(poisson[key]) - float(elo[key]))
        agreement = max(0.0, 1.0 - gap / 0.2)
    elif market in STAT_MARKETS:
        # Sem cruzamento ELO; amostra de TeamStat define o teto de confiança.
        sample = ((pred.get("stat_samples") or {}).get(market)) or 0
        agreement = 0.45 + 0.05 * min(sample, 6)
    else:
        agreement = 0.65
    edge_score = min(1.0, max(0.0, edge) / 0.10)
    kelly_score = min(1.0, max(0.0, kelly_fraction) / 0.05)
    conf = 0.45 * agreement + 0.35 * edge_score + 0.20 * kelly_score

    if home_n_games is not None and away_n_games is not None:
        if home_n_games < SAMPLE_GAMES_SOFT or away_n_games < SAMPLE_GAMES_SOFT:
            conf *= 0.85

    if has_team_stats and (
        market in STAT_MARKETS
        or market == "goals_2_5"
        or selection in ("over", "under", "yes", "no")
    ):
        conf = min(1.0, conf + 0.05)

    if h2h_over_boost and market == "goals_2_5" and selection == "over":
        conf = min(1.0, conf + 0.04)

    if soft_vs_consensus:
        conf *= 0.75
    if odds_falling:
        conf *= 0.70
    return round(max(0.0, min(1.0, conf)), 4)


def rank_score(expected_roi: float, confidence: float) -> float:
    return round(expected_roi * (0.5 + 0.5 * confidence), 4)


def evaluate(
    market: str,
    selection: str,
    odd: float,
    probability: float,
    bookmaker: str,
    *,
    fair_implied: float | None = None,
    pred: dict | None = None,
    consensus_odd: float | None = None,
    odds_move_pct_value: float | None = None,
    books_covering: int = 1,
    home_n_games: int | None = None,
    away_n_games: int | None = None,
    has_team_stats: bool = False,
    h2h_over_boost: bool = False,
    line: float | None = None,
) -> dict:
    raw_implied = 1.0 / odd if odd else 0.0
    implied = fair_implied if fair_implied is not None else raw_implied
    edge = probability - implied
    ev = probability * odd - 1
    k = kelly(probability, odd)
    soft = bool(consensus_odd and odd > consensus_odd * SOFT_ODD_PREMIUM)
    falling = bool(
        odds_move_pct_value is not None and odds_move_pct_value <= MOVE_DROP_THRESHOLD
    )
    is_value = ev >= MIN_EV and k >= MIN_KELLY and edge >= MIN_EDGE and not soft
    conf = confidence_score(
        pred or {},
        market,
        selection,
        edge,
        k,
        home_n_games=home_n_games,
        away_n_games=away_n_games,
        has_team_stats=has_team_stats,
        soft_vs_consensus=soft,
        odds_falling=falling,
        h2h_over_boost=h2h_over_boost,
    )
    recommended = bool(
        is_value
        and probability >= MIN_RECOMMENDED_PROBABILITY
        and conf >= MIN_RECOMMENDED_CONFIDENCE
        and odd <= MAX_RECOMMENDED_ODD
    )
    score = rank_score(ev, conf)
    return {
        "market": market,
        "selection": selection,
        "line": line,
        "bookmaker": bookmaker,
        "odd": odd,
        "estimated_probability": round(probability, 4),
        "implied_probability": round(implied, 4),
        "raw_implied_probability": round(raw_implied, 4),
        "devigged": fair_implied is not None,
        "edge": round(edge, 4),
        "expected_roi": round(ev, 4),
        "is_value": is_value,
        "kelly_fraction": round(k, 4),
        "suggested_stake_units": round(min(k * 10, 0.75), 2),
        "strength": classify(edge),
        "confidence": conf,
        "recommended": recommended,
        "risk_profile": "conservadora" if recommended else "especulativa",
        "rank_score": score,
        "decision_score": round(score * (0.5 + probability), 4),
        "consensus_odd": round(consensus_odd, 3) if consensus_odd else None,
        "odds_move_pct": round(odds_move_pct_value, 4) if odds_move_pct_value is not None else None,
        "books_covering": books_covering,
    }


def market_probability(
    pred: dict, market: str, selection: str, line: float | None = None
) -> float | None:
    if market == "goals_2_5" or market == "totals":
        key = totals_prob_key(selection, line)
        return pred.get(key) if key else None
    if market in STAT_MARKETS:
        sel = selection.lower()
        if sel not in ("over", "under") or line is None:
            return None
        if not allowed_stat_line(market, line):
            return None
        return pred.get(prob_key(market, sel, line))
    key = MARKET_KEYS.get((market, selection))
    return pred.get(key) if key else None
