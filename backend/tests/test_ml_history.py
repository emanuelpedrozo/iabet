from app.services.ml_history import source_name, source_team_identity


def test_mineiro_clubs_are_never_normalized_to_same_identity():
    assert source_name("América Mineiro") == "america mineiro"
    assert source_name("Atlético Mineiro") == "atletico mineiro"
    assert source_name("América Mineiro") != source_name("Atlético Mineiro")


def test_missing_provider_team_id_gets_stable_negative_identity():
    first, inferred = source_team_identity(None, "Athletico Paranaense")
    second, inferred_again = source_team_identity(None, "Athletico Paranaense")
    assert inferred and inferred_again
    assert first == second
    assert first < 0


def test_real_provider_team_id_is_preserved():
    identity, inferred = source_team_identity(155, "Atlético Mineiro")
    assert identity == 155
    assert inferred is False
