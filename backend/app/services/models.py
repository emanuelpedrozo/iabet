from dataclasses import dataclass
from math import exp, factorial
import numpy as np

DIXON_COLES_RHO = -0.10


@dataclass(frozen=True)
class ModelInput:
    home_attack: float
    home_defense: float
    away_attack: float
    away_defense: float
    home_elo: float
    away_elo: float
    league_home_goals: float = 1.42
    league_away_goals: float = 1.08
    dixon_coles_rho: float = DIXON_COLES_RHO


def poisson_pmf(k: int, lam: float) -> float:
    return exp(-lam) * lam**k / factorial(k)


def expected_goals(x: ModelInput) -> tuple[float, float]:
    return (
        max(0.2, x.league_home_goals * x.home_attack * x.away_defense),
        max(0.2, x.league_away_goals * x.away_attack * x.home_defense),
    )


def dixon_coles_tau(home_goals: int, away_goals: int, lam_h: float, lam_a: float, rho: float) -> float:
    if home_goals == 0 and away_goals == 0:
        return 1 - lam_h * lam_a * rho
    if home_goals == 0 and away_goals == 1:
        return 1 + lam_h * rho
    if home_goals == 1 and away_goals == 0:
        return 1 + lam_a * rho
    if home_goals == 1 and away_goals == 1:
        return 1 - rho
    return 1.0


def poisson_matrix(
    h: float,
    a: float,
    max_goals: int = 8,
    rho: float = DIXON_COLES_RHO,
) -> np.ndarray:
    m = np.zeros((max_goals + 1, max_goals + 1))
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            tau = dixon_coles_tau(i, j, h, a, rho)
            m[i, j] = max(0.0, tau) * poisson_pmf(i, h) * poisson_pmf(j, a)
    total = float(m.sum())
    if total > 0:
        m = m / total
    return m


def _over_under(m: np.ndarray, line: float) -> tuple[float, float]:
    """P(gols > line) e complemento (linha .5 clássica)."""
    over = float(sum(m[i, j] for i in range(m.shape[0]) for j in range(m.shape[1]) if i + j > line))
    return over, 1.0 - over


def poisson_model(x: ModelInput) -> dict:
    h, a = expected_goals(x)
    m = poisson_matrix(h, a, rho=x.dixon_coles_rho)
    home = float(np.tril(m, -1).sum())
    draw = float(np.trace(m))
    away = float(np.triu(m, 1).sum())
    over15, under15 = _over_under(m, 1.5)
    over25, under25 = _over_under(m, 2.5)
    over35, under35 = _over_under(m, 3.5)
    btts = float(sum(m[i, j] for i in range(1, m.shape[0]) for j in range(1, m.shape[1])))
    score = np.unravel_index(np.argmax(m), m.shape)
    return {
        "home": home,
        "draw": draw,
        "away": away,
        "over_1_5": over15,
        "under_1_5": under15,
        "over_2_5": over25,
        "under_2_5": under25,
        "over_3_5": over35,
        "under_3_5": under35,
        "btts_yes": btts,
        "btts_no": 1 - btts,
        "xg_home": h,
        "xg_away": a,
        "score": f"{score[0]}-{score[1]}",
        "dixon_coles_rho": x.dixon_coles_rho,
    }


def elo_model(x: ModelInput) -> dict:
    expected = 1 / (1 + 10 ** (-((x.home_elo + 70) - x.away_elo) / 400))
    draw = 0.25 * exp(-abs(x.home_elo - x.away_elo) / 500)
    return {
        "home": expected * (1 - draw),
        "draw": draw,
        "away": 1 - expected * (1 - draw) - draw,
    }


def monte_carlo(x: ModelInput, n: int = 30000, seed: int = 42) -> dict:
    h, a = expected_goals(x)
    rng = np.random.default_rng(seed)
    hs = rng.poisson(h, n)
    aw = rng.poisson(a, n)
    return {
        "home": float(np.mean(hs > aw)),
        "draw": float(np.mean(hs == aw)),
        "away": float(np.mean(hs < aw)),
        "over_2_5": float(np.mean(hs + aw > 2)),
        "btts_yes": float(np.mean((hs > 0) & (aw > 0))),
    }


def ensemble(x: ModelInput) -> dict:
    """Ensemble 1.4: Poisson+Dixon–Coles + ELO; totals de gols; base para stats."""
    p = poisson_model(x)
    e = elo_model(x)
    result = {k: round(0.70 * p[k] + 0.30 * e[k], 4) for k in ("home", "draw", "away")}
    total = result["home"] + result["draw"] + result["away"]
    if total > 0:
        result = {k: round(result[k] / total, 4) for k in result}
    for key in (
        "over_1_5",
        "under_1_5",
        "over_2_5",
        "under_2_5",
        "over_3_5",
        "under_3_5",
        "btts_yes",
        "btts_no",
    ):
        result[key] = round(p[key], 4)
    result.update(
        {
            "xg_home": round(p["xg_home"], 2),
            "xg_away": round(p["xg_away"], 2),
            "score": p["score"],
            "models": {"poisson": p, "elo": e},
            "version": "ensemble-1.4",
        }
    )
    return result
