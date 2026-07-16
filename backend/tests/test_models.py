from app.services.models import ModelInput, ensemble, poisson_model
from app.services.value import evaluate
def test_probabilities_sum_to_one():
    p=ensemble(ModelInput(1.1,.9,.95,1.05,1600,1500)); assert abs(p["home"]+p["draw"]+p["away"]-1)<.01
def test_home_strength_increases_home_probability():
    weak=poisson_model(ModelInput(.8,1,1,1,1500,1500)); strong=poisson_model(ModelInput(1.3,1,1,1,1500,1500)); assert strong["home"]>weak["home"]
def test_value_math():
    v=evaluate("match_result","home",2.1,.52,"test"); assert v["is_value"] and v["expected_roi"]==.092

