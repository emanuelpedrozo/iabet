from app.services.ml_features import (
    FEATURES,
    FORM_WINDOW,
    RollingState,
    apply_class_bias,
    canonical_club_name,
    predict_binary_from_artifact,
    predict_proba_from_artifact,
    serialize_pipeline,
    make_classifier,
)
import numpy as np


def test_form_window_is_ten():
    assert FORM_WINDOW == 10
    assert "exp_corners" in FEATURES
    assert "home_corners" in FEATURES


def test_rolling_state_features_length_matches_feature_names():
    state = RollingState.empty()
    state.update("a", "b", 2, 1, home_corners=6.0, away_corners=4.0, home_cards=2.0, away_cards=3.0)
    values = state.features("a", "b", 10)
    assert len(values) == len(FEATURES)


def test_canonical_aliases_do_not_merge_mineiro_clubs():
    assert canonical_club_name("América Mineiro") != canonical_club_name("Atlético Mineiro")


def test_predict_proba_from_artifact_sums_to_one():
    pipeline = make_classifier()
    x = np.random.default_rng(0).normal(size=(40, len(FEATURES)))
    y = ["home", "draw", "away"] * 13 + ["home"]
    pipeline.fit(x, y[:40])
    artifact = serialize_pipeline(pipeline, temperature=1.2)
    probs = predict_proba_from_artifact(list(x[0]), artifact)
    assert set(probs) == {"home", "draw", "away"}
    assert abs(sum(probs.values()) - 1.0) < 1e-6


def test_predict_binary_from_artifact_in_unit_interval():
    pipeline = make_classifier(binary=True)
    rng = np.random.default_rng(1)
    x = rng.normal(size=(60, len(FEATURES)))
    y = (x[:, 0] > 0).astype(int)
    pipeline.fit(x, y)
    artifact = serialize_pipeline(pipeline, temperature=1.0, extra={"label": "t", "line": 2.5})
    p = predict_binary_from_artifact(list(x[0]), artifact)
    assert 0.0 <= p <= 1.0


def test_draw_bias_increases_draw_probability_and_keeps_sum_one():
    probabilities = np.asarray([[0.40, 0.25, 0.35]])
    adjusted = apply_class_bias(
        probabilities, ["home", "draw", "away"], {"draw": 1.5}
    )
    assert adjusted[0, 1] > probabilities[0, 1]
    assert abs(float(adjusted.sum()) - 1.0) < 1e-9
