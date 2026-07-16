from app.services.sync import normalize


def test_normalize_strips_accents_and_aliases():
    assert normalize("Flamengo") == "cr flamengo"
    assert normalize("São Paulo FC") == "sao paulo"
    assert normalize("Atlético Mineiro") == "ca mineiro"
    assert normalize("RB Bragantino") == "rb bragantino"
