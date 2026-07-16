from types import SimpleNamespace
from datetime import datetime, timezone, timedelta
from app.services.models import (
    DIXON_COLES_RHO,
    ModelInput,
    ensemble,
    poisson_matrix,
    poisson_model,
)
from app.services.value import market_probability
from app.api.routes.matches import h2h_over25_rate, values_for


def test_poisson_1x2_sums_to_one_after_renormalize():
    p = poisson_model(ModelInput(1.1, 0.9, 0.95, 1.05, 1600, 1500))
    assert abs(p["home"] + p["draw"] + p["away"] - 1) < 1e-9


def test_dixon_coles_increases_00_when_rho_negative():
    h, a = 1.4, 1.1
    indep = poisson_matrix(h, a, rho=0.0)
    dc = poisson_matrix(h, a, rho=DIXON_COLES_RHO)
    assert dc[0, 0] > indep[0, 0]


def test_ensemble_13_exposes_extra_totals_lines():
    p = ensemble(ModelInput(1.1, 0.9, 0.95, 1.05, 1600, 1500))
    assert p["version"] == "ensemble-1.3"
    assert "over_1_5" in p and "over_3_5" in p
    assert abs(p["home"] + p["draw"] + p["away"] - 1) < 0.01


def test_market_probability_line_15():
    pred = ensemble(ModelInput(1.2, 0.95, 1.0, 1.05, 1550, 1480))
    assert market_probability(pred, "goals_2_5", "over", 1.5) == pred["over_1_5"]
    assert market_probability(pred, "goals_2_5", "under", 3.5) == pred["under_3_5"]


def test_values_for_consensus_penalizes_soft_odd():
    now = datetime.now(timezone.utc)
    pred = ensemble(ModelInput(1.3, 0.9, 0.9, 1.1, 1600, 1450))
    # Força over 2.5 com p alto via pred override
    pred = {**pred, "over_2_5": 0.62, "under_2_5": 0.38}
    match = SimpleNamespace(
        odds=[
            SimpleNamespace(
                bookmaker="A",
                market="goals_2_5",
                selection="over",
                line=2.5,
                price=2.05,
                captured_at=now,
            ),
            SimpleNamespace(
                bookmaker="B",
                market="goals_2_5",
                selection="over",
                line=2.5,
                price=2.10,
                captured_at=now,
            ),
            SimpleNamespace(
                bookmaker="Soft",
                market="goals_2_5",
                selection="over",
                line=2.5,
                price=2.60,
                captured_at=now,
            ),
            SimpleNamespace(
                bookmaker="A",
                market="goals_2_5",
                selection="under",
                line=2.5,
                price=1.80,
                captured_at=now,
            ),
            SimpleNamespace(
                bookmaker="B",
                market="goals_2_5",
                selection="under",
                line=2.5,
                price=1.78,
                captured_at=now,
            ),
            SimpleNamespace(
                bookmaker="Soft",
                market="goals_2_5",
                selection="under",
                line=2.5,
                price=1.55,
                captured_at=now,
            ),
        ]
    )
    values = values_for(match, pred)
    books = {v["bookmaker"] for v in values if v["selection"] == "over"}
    assert "Soft" not in books


def test_values_for_falling_odd_lowers_rank():
    now = datetime.now(timezone.utc)
    pred = {**ensemble(ModelInput(1.2, 0.95, 1.0, 1.0, 1550, 1500)), "over_2_5": 0.58, "under_2_5": 0.42}
    stable = [
        SimpleNamespace(
            bookmaker="A",
            market="goals_2_5",
            selection="over",
            line=2.5,
            price=2.20,
            captured_at=now - timedelta(hours=2),
        ),
        SimpleNamespace(
            bookmaker="A",
            market="goals_2_5",
            selection="over",
            line=2.5,
            price=2.18,
            captured_at=now,
        ),
        SimpleNamespace(
            bookmaker="A",
            market="goals_2_5",
            selection="under",
            line=2.5,
            price=1.70,
            captured_at=now,
        ),
    ]
    falling = [
        SimpleNamespace(
            bookmaker="B",
            market="goals_2_5",
            selection="over",
            line=2.5,
            price=2.40,
            captured_at=now - timedelta(hours=2),
        ),
        SimpleNamespace(
            bookmaker="B",
            market="goals_2_5",
            selection="over",
            line=2.5,
            price=2.10,
            captured_at=now,
        ),
        SimpleNamespace(
            bookmaker="B",
            market="goals_2_5",
            selection="under",
            line=2.5,
            price=1.75,
            captured_at=now,
        ),
    ]
    match = SimpleNamespace(odds=stable + falling)
    values = values_for(match, pred)
    by_book = {v["bookmaker"]: v for v in values if v["selection"] == "over"}
    if "A" in by_book and "B" in by_book:
        assert by_book["A"]["rank_score"] >= by_book["B"]["rank_score"]


def test_h2h_over25_rate():
    h2h = [
        {"total_goals": 3},
        {"total_goals": 4},
        {"total_goals": 1},
        {"total_goals": 5},
    ]
    assert h2h_over25_rate(h2h) == 0.75
    assert h2h_over25_rate(h2h[:2]) is None
