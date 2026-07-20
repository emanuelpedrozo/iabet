from app.services.team_metrics import enrich_api_futebol_metrics, merge_metrics, team_metric


def test_merge_preserves_api_futebol_nested_when_api_sports_arrives():
    base = merge_metrics(
        None,
        enrich_api_futebol_metrics(
            {"finalizacao": {"total": 12, "no_gol": 4}, "escanteios": 5, "faltas": 14}
        ),
    )
    incoming = {
        "total_shots": 13,
        "shots_on_goal": 5,
        "corner_kicks": 6,
        "yellow_cards": 3,
        "source": "api_sports",
    }
    merged = merge_metrics(base, incoming)
    assert merged["finalizacao"]["total"] == 12
    assert merged["escanteios"] == 5
    assert merged["total_shots"] == 13
    assert merged["yellow_cards"] == 3
    assert merged["sources"] == ["api_futebol", "api_sports"]


def test_merge_api_futebol_after_api_sports_keeps_sports_flat():
    base = {"total_shots": 10, "corner_kicks": 4, "yellow_cards": 2, "source": "api_sports"}
    incoming = enrich_api_futebol_metrics(
        {"finalizacao": {"total": 11, "no_gol": 3}, "escanteios": 5, "faltas": 12}
    )
    merged = merge_metrics(base, incoming)
    assert merged["total_shots"] == 10
    assert merged["corner_kicks"] == 4
    assert merged["finalizacao"]["total"] == 11
    assert merged["faltas"] == 12
    assert merged["yellow_cards"] == 2
    assert merged["sources"] == ["api_futebol", "api_sports"]


def test_api_futebol_alone_fills_flat_aliases():
    alone = merge_metrics(
        None,
        enrich_api_futebol_metrics(
            {"finalizacao": {"total": 11, "no_gol": 3}, "escanteios": 5, "faltas": 12}
        ),
    )
    assert alone["total_shots"] == 11
    assert alone["shots_on_goal"] == 3
    assert alone["corner_kicks"] == 5
    assert alone["fouls"] == 12


def test_team_metric_reads_flat_and_nested():
    flat = {"total_shots": 14, "corner_kicks": 7, "yellow_cards": 2}
    assert team_metric(flat, None, "total_shots", is_home=True) == 14.0
    nested = {"finalizacao": {"total": 9, "no_gol": 3}, "escanteios": 4}
    assert team_metric(nested, None, "total_shots", is_home=True) == 9.0
    assert team_metric(nested, None, "shots_on_goal", is_home=False) == 3.0
    assert team_metric(nested, None, "corner_kicks", is_home=True) == 4.0


def test_team_metric_yellow_from_api_futebol_cards_metadata():
    meta = {
        "api_futebol": {
            "cards": {
                "amarelo": {"mandante": [{}, {}], "visitante": [{}]},
                "vermelho": {"mandante": [{}], "visitante": []},
            }
        }
    }
    assert team_metric({}, meta, "yellow_cards", is_home=True) == 2.0
    assert team_metric({}, meta, "yellow_cards", is_home=False) == 1.0
    assert team_metric({}, meta, "red_cards", is_home=True) == 1.0


def test_team_metric_prefers_flat_yellow_over_metadata():
    meta = {"api_futebol": {"cards": {"amarelo": {"mandante": [{}, {}, {}]}}}}
    assert team_metric({"yellow_cards": 1}, meta, "yellow_cards", is_home=True) == 1.0
