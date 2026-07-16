from app.services.stat_markets import blend_rate, build_stat_markets, poisson_over_under, prob_key
from app.services.value import allowed_stat_line, market_probability


def test_poisson_over_under_sums_to_one():
    over, under = poisson_over_under(9.5, 9.5)
    assert abs(over + under - 1.0) < 1e-9
    assert 0.35 < over < 0.65


def test_higher_lambda_raises_over_probability():
    low, _ = poisson_over_under(8.0, 9.5)
    high, _ = poisson_over_under(12.0, 9.5)
    assert high > low


def test_build_stat_markets_exposes_corner_card_shot_lines():
    out = build_stat_markets(
        corners_lambda=10.0,
        cards_lambda=4.5,
        shots_lambda=24.0,
        corners_sample=5,
        cards_sample=5,
        shots_sample=4,
    )
    assert out["xc_total"] == 10.0
    assert out["corners_over_9_5"] == out[prob_key("corners", "over", 9.5)]
    assert "cards_under_4_5" in out
    assert "shots_over_24_5" in out
    assert out["stat_samples"]["corners"] == 5


def test_blend_rate_pulls_to_default_with_small_sample():
    assert abs(blend_rate(8.0, 0, 5.0) - 5.0) < 1e-9
    assert abs(blend_rate(8.0, 3, 5.0) - 8.0) < 1e-9
    mid = blend_rate(8.0, 1, 5.0)
    assert 5.0 < mid < 8.0


def test_recent_games_sample_is_ten():
    from app.services.stat_rates import RECENT_GAMES

    assert RECENT_GAMES == 10


def test_market_probability_stat_lines():
    pred = build_stat_markets(corners_lambda=11.0, cards_lambda=5.0, shots_lambda=25.0)
    assert market_probability(pred, "corners", "over", 9.5) == pred["corners_over_9_5"]
    assert market_probability(pred, "cards", "under", 4.5) == pred["cards_under_4_5"]
    assert market_probability(pred, "shots", "over", 24.5) == pred["shots_over_24_5"]
    assert market_probability(pred, "corners", "over", 7.5) is None
    assert allowed_stat_line("corners", 9.5)
    assert not allowed_stat_line("corners", 7.5)
