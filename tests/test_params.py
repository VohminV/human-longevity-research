import pytest

from longevity.biology.params import apply_interventions, validate_parameters


def test_defaults_filled():
    params = validate_parameters({})
    assert params["doubling_time_mean"] == 10.8
    assert params["doubling_time_sd"] == 1.2


def test_features_off_by_default():
    params = validate_parameters({})
    assert "telomere" not in params
    assert "dna_damage" not in params
    assert "mortality" not in params


def test_unknown_top_level_rejected():
    with pytest.raises(ValueError):
        validate_parameters({"bogus": 1})


def test_doubling_time_bounds():
    with pytest.raises(ValueError):
        validate_parameters({"doubling_time_mean": 0.0})
    with pytest.raises(ValueError):
        validate_parameters({"doubling_time_sd": -1.0})


def test_feature_validation():
    with pytest.raises(ValueError):
        validate_parameters({"telomere": {"wibble": 1}})
    with pytest.raises(ValueError):
        validate_parameters({"telomere": {"loss_per_division": -1.0}})
    with pytest.raises(ValueError):
        validate_parameters({"dna_damage": {"accrual_per_division": "many"}})
    with pytest.raises(ValueError):
        validate_parameters({"dna_damage": {"threshold": True}})
    with pytest.raises(ValueError):
        validate_parameters({"mortality": {"rate": 1.5}})
    with pytest.raises(ValueError):
        validate_parameters({"mortality": {"rate": -0.1}})


def test_feature_enabled_with_empty_dict():
    params = validate_parameters({"telomere": {}})
    assert params["telomere"]["length_start"] == 100.0
    assert params["telomere"]["loss_per_division"] == 5.0


def test_intervention_enables_feature():
    params = apply_interventions({}, [{"parameter": "telomere.loss_per_division", "value": 3}])
    assert params["telomere"]["loss_per_division"] == 3
    assert params["telomere"]["length_start"] == 100.0


def test_intervention_bad_path_rejected():
    with pytest.raises(ValueError):
        apply_interventions({}, [{"parameter": "nope.value", "value": 1}])
    with pytest.raises(ValueError):
        apply_interventions({}, [{"parameter": "", "value": 1}])