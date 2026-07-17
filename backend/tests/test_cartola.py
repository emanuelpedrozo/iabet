from app.providers.cartola import cartola_metrics


def test_cartola_metrics_maps_shots_tackles_cards_and_saves():
    metrics = cartola_metrics(
        {"G": 1, "FD": 2, "FF": 3, "FT": 1, "DS": 4, "FC": 2, "CA": 1, "DE": 5}
    )

    assert metrics["shots"] == {"total": 7.0, "on": 3.0, "off": 3.0, "woodwork": 1.0}
    assert metrics["tackles"]["total"] == 4.0
    assert metrics["fouls"]["committed"] == 2.0
    assert metrics["cards"]["yellow"] == 1.0
    assert metrics["goalkeeper"]["saves"] == 5.0
