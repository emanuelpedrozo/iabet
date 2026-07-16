"""Mercados de escanteios, cartões e chutes a partir de médias do TeamStat."""
from __future__ import annotations

from math import exp, factorial, floor

# Linhas .5 mais comuns nas casas (quando a Odds API as oferece).
STAT_LINES: dict[str, tuple[float, ...]] = {
    "corners": (8.5, 9.5, 10.5),
    "cards": (3.5, 4.5, 5.5),
    "shots": (22.5, 24.5, 26.5),
}

# Médias de liga usadas quando a amostra do time é insuficiente.
DEFAULT_TEAM_RATE: dict[str, float] = {
    "corners": 5.0,
    "cards": 2.2,
    "shots": 12.0,
}

METRIC_BY_MARKET: dict[str, str] = {
    "corners": "corner_kicks",
    "cards": "yellow_cards",
    "shots": "total_shots",
}


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return exp(-lam) * lam**k / factorial(k)


def poisson_over_under(lam: float, line: float) -> tuple[float, float]:
    """P(X > line) e complemento para linha .5 (ex.: 9.5 → P(X >= 10))."""
    lam = max(0.05, float(lam))
    k_max = int(floor(line))
    under_or_eq = sum(poisson_pmf(k, lam) for k in range(k_max + 1))
    under = min(1.0, max(0.0, under_or_eq))
    over = 1.0 - under
    return over, under


def line_key(line: float) -> str:
    """9.5 → '9_5'."""
    text = f"{line:.1f}".replace(".", "_")
    return text


def prob_key(market: str, selection: str, line: float) -> str:
    return f"{market}_{selection}_{line_key(line)}"


def build_stat_markets(
    *,
    corners_lambda: float,
    cards_lambda: float,
    shots_lambda: float,
    corners_sample: int = 0,
    cards_sample: int = 0,
    shots_sample: int = 0,
) -> dict:
    """Gera over/under Poisson para escanteios, cartões (amarelos) e chutes."""
    out: dict = {
        "xc_total": round(corners_lambda, 2),
        "xy_total": round(cards_lambda, 2),
        "xs_total": round(shots_lambda, 2),
        "stat_samples": {
            "corners": corners_sample,
            "cards": cards_sample,
            "shots": shots_sample,
        },
    }
    for market, lam in (
        ("corners", corners_lambda),
        ("cards", cards_lambda),
        ("shots", shots_lambda),
    ):
        for line in STAT_LINES[market]:
            over, under = poisson_over_under(lam, line)
            out[prob_key(market, "over", line)] = round(over, 4)
            out[prob_key(market, "under", line)] = round(under, 4)
    return out


def blend_rate(team_avg: float | None, sample: int, default: float, min_sample: int = 3) -> float:
    """Com poucos jogos, puxa para a média de liga/default."""
    if team_avg is None or sample <= 0:
        return default
    if sample >= min_sample:
        return float(team_avg)
    w = sample / min_sample
    return w * float(team_avg) + (1 - w) * default
