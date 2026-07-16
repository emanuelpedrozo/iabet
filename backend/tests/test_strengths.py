from app.services.strengths import (
    DEFAULT_LEAGUE_AWAY,
    DEFAULT_LEAGUE_HOME,
    apply_elo_result,
    attack_defense_from_results,
    blend_strengths,
    form_attack_defense,
    league_averages_from_scores,
    team_profile,
)


def test_league_averages_uses_defaults_when_sample_small():
    assert league_averages_from_scores([(1, 0), (2, 1)]) == (
        DEFAULT_LEAGUE_HOME,
        DEFAULT_LEAGUE_AWAY,
    )


def test_league_averages_from_enough_matches():
    scores = [(2, 1), (1, 1), (3, 0), (2, 2), (1, 0)]
    home, away = league_averages_from_scores(scores)
    assert abs(home - 1.8) < 1e-9
    assert abs(away - 0.8) < 1e-9


def test_attack_strength_above_one_when_scoring_more_than_league():
    results = [(True, 3, 1)] * 5
    strengths = attack_defense_from_results(results, league_home=1.5, league_away=1.0)
    assert strengths is not None
    attack, defense = strengths
    assert attack > 1.0
    assert 0.5 <= defense <= 1.8


def test_form_weights_recent_games_more():
    # 5 jogos fracos + 3 fortes recentes → forma > temporada pura nos 8
    weak = [(True, 0, 2)] * 5
    strong = [(True, 3, 0)] * 3
    results = weak + strong
    season = attack_defense_from_results(results, 1.5, 1.0)
    form = form_attack_defense(results, 1.5, 1.0)
    assert season and form
    assert form[0] > season[0]


def test_blend_prefers_form():
    season = (1.0, 1.0)
    form = (1.5, 0.8)
    blended = blend_strengths(season, form)
    assert blended is not None
    assert blended[0] > 1.0
    assert blended[0] < 1.5


def test_team_profile_has_home_away_splits():
    results = [(True, 2, 1)] * 4 + [(False, 1, 2)] * 4
    profile = team_profile(results, 1.4, 1.1)
    assert profile["n_games"] == 8
    assert "attack_home" in profile and "attack_away" in profile


def test_strengths_none_with_few_matches():
    assert attack_defense_from_results([(True, 2, 1)], 1.4, 1.1) is None


def test_elo_winner_gains_rating():
    home_after, away_after = apply_elo_result(1500.0, 1500.0, 2, 0)
    assert home_after > 1500
    assert away_after < 1500


def test_elo_draw_moves_less_than_win():
    win_h, _ = apply_elo_result(1500, 1500, 1, 0)
    draw_h, _ = apply_elo_result(1500, 1500, 1, 1)
    assert abs(win_h - 1500) > abs(draw_h - 1500)
