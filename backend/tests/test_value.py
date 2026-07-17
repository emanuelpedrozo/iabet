from app.services.value import (
    MIN_EV,
    classify,
    confidence_score,
    evaluate,
    kelly,
    market_probability,
    median_odd,
    multiplicative_devig,
    odds_move_pct,
    rank_score,
)


def test_kelly_positive_and_capped_fraction():
    assert kelly(0.55, 2.1) > 0
    assert kelly(0.4, 2.0) == 0


def test_multiplicative_devig_removes_overround():
    fair = multiplicative_devig({"home": 2.0, "draw": 3.5, "away": 3.8})
    assert abs(sum(fair.values()) - 1) < 1e-9
    assert fair["home"] < 1 / 2.0


def test_median_and_move():
    assert median_odd([2.0, 2.1, 2.4]) == 2.1
    assert abs(odds_move_pct(2.0, 1.9) - (-0.05)) < 1e-9


def test_evaluate_marks_value_when_above_thresholds():
    item = evaluate("match_result", "home", 2.5, 0.5, "Demo")
    assert item["is_value"] is True
    assert item["expected_roi"] >= MIN_EV
    assert item["confidence"] > 0
    assert item["recommended"] is True
    assert classify(0.12) == "muito forte"


def test_low_probability_value_is_speculative_not_recommended():
    item = evaluate("match_result", "draw", 5.0, 0.2342, "Demo")
    assert item["is_value"] is True
    assert item["recommended"] is False
    assert item["risk_profile"] == "especulativa"


def test_result_against_model_favorite_is_never_the_main_recommendation():
    item = evaluate(
        "match_result",
        "away",
        4.15,
        0.31,
        "Demo",
        pred={"home": 0.42, "draw": 0.27, "away": 0.31},
    )
    assert item["is_value"] is True
    assert item["aligned_with_model"] is False
    assert item["recommended"] is False


def test_evaluate_rejects_soft_consensus():
    item = evaluate(
        "match_result",
        "home",
        2.8,
        0.5,
        "Soft",
        consensus_odd=2.2,
    )
    assert item["is_value"] is False


def test_falling_odd_reduces_confidence():
    base = evaluate("match_result", "home", 2.5, 0.5, "A")
    falling = evaluate(
        "match_result",
        "home",
        2.5,
        0.5,
        "A",
        odds_move_pct_value=-0.08,
    )
    assert falling["confidence"] < base["confidence"]


def test_small_sample_reduces_confidence():
    high = confidence_score({}, "goals_2_5", "over", 0.08, 0.04, home_n_games=10, away_n_games=10)
    low = confidence_score({}, "goals_2_5", "over", 0.08, 0.04, home_n_games=2, away_n_games=2)
    assert high > low


def test_rank_score_prefers_confident_ev():
    assert rank_score(0.10, 0.9) > rank_score(0.10, 0.2)


def test_market_probability_mapping():
    pred = {"home": 0.4, "over_2_5": 0.55, "over_1_5": 0.72, "btts_yes": 0.6}
    assert market_probability(pred, "match_result", "home") == 0.4
    assert market_probability(pred, "goals_2_5", "over", 1.5) == 0.72
    assert market_probability(pred, "unknown", "x") is None
