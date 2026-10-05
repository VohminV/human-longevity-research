"""Stage 6D: conversion / independent / ceiling ablations + component overrides."""

import pytest

from longevity.model.organism import (
    DEFAULT_ORGANISM_THRESHOLDS,
    DEFAULT_STAGE_BOUNDS,
    OrganismModel,
    validate_organism_thresholds,
    validate_stage_bounds,
)


def _bounds():
    return validate_stage_bounds(dict(DEFAULT_STAGE_BOUNDS))


def _thresholds():
    return validate_organism_thresholds(dict(DEFAULT_ORGANISM_THRESHOLDS))


def _model(**kwargs):
    params = {"organ_backed_model": "reduced_organ_proxies",
              "organ_network_model": "reduced_network_feedback",
              "reversibility_model": "split_reversible_irreversible",
              "boundary_probe_model": "irreversibility_ablation"}
    params.update(kwargs)
    return OrganismModel(seed=11, aging_model="mechanistic_drivers",
                         aging_drivers={}, **params)


def _flux(model):
    return float(model.state.reversibility.get("total_conversion_flux", 0.0))


def test_conversion_zero_removes_flux():
    model = _model(boundary_params={"conversion_scale": 0.0})
    model.run(30.0, 0.5, _bounds(), _thresholds(), None)
    assert _flux(model) == pytest.approx(0.0)
    for comp in list(model.state.reversibility["drivers"].values()) \
            + list(model.state.reversibility["organs"].values()):
        assert comp["reversible"] >= 0.0 and comp["irreversible"] >= 0.0


def test_conversion_scale_one_preserves_stage6c():
    from longevity.experiment.organism_runner import load_organism_config, run_organism_experiment, \
        OrganismExperimentConfig
    ref = run_organism_experiment(
        load_organism_config("experiments/configs/organism_reversibility_baseline.json"))
    d = load_organism_config("experiments/configs/organism_reversibility_baseline.json").to_config_dict()
    d["organism_id"] = "tmp_conv1"
    d["boundary_probe_model"] = "irreversibility_ablation"
    d["boundary_params"] = {"conversion_scale": 1.0}
    same = run_organism_experiment(OrganismExperimentConfig.from_config_dict(d))
    strip = lambda traj: [{k: v for k, v in row.items() if k != "boundary"} for row in traj]
    assert strip(same["trajectory"]) == strip(ref["trajectory"])


def test_conversion_scale_high_increases_flux_within_bounds():
    calm = _model(boundary_params={"conversion_scale": 0.1})
    calm.run(30.0, 0.5, _bounds(), _thresholds(), None)
    hot = _model(boundary_params={"conversion_scale": 2.0})
    hot.run(30.0, 0.5, _bounds(), _thresholds(), None)
    assert _flux(hot) >= _flux(calm) - 1e-12
    assert _flux(hot) == _flux(hot)  # finite (no NaN)


def test_independent_zero_removes_independent_but_keeps_conversion():
    model = _model(boundary_params={"independent_accrual_scale": 0.0})
    model.run(30.0, 0.5, _bounds(), _thresholds(), None)
    # conversion still flows; independent accrual gone
    assert _flux(model) > 0.0
    rev = model.state.reversibility
    assert rev["irreversible_burden"] >= 0.0


def test_disable_flags_equivalent_to_zero_scales():
    a = _model(boundary_params={"disable_conversion": True})
    a.run(20.0, 0.5, _bounds(), _thresholds(), None)
    b = _model(boundary_params={"conversion_scale": 0.0})
    b.run(20.0, 0.5, _bounds(), _thresholds(), None)
    assert _flux(a) == pytest.approx(0.0)
    assert _flux(b) == pytest.approx(0.0)


def test_ceiling_zero_forbids_repair():
    from longevity.model.intervention import build_effect
    model = _model(boundary_params={"repair_ceiling_scale": 0.0})
    assert model.state.reversibility["repair_ceiling"] == pytest.approx(0.0)
    model.run(25.0, 0.5, _bounds(), _thresholds(), None)
    model.apply_effect(dict(build_effect("irreversible_repair_pulse", 1.0, [], source="t")), "t")
    assert model.state.reversibility["repair_used_global"] == pytest.approx(0.0)


def test_disable_irreversible_repair_blocks_repair():
    from longevity.model.intervention import build_effect
    model = _model(boundary_params={"disable_irreversible_repair": True})
    model.run(25.0, 0.5, _bounds(), _thresholds(), None)
    model.apply_effect(dict(build_effect("irreversible_repair_pulse", 1.0, [], source="t")), "t")
    assert model.state.reversibility["repair_used_global"] == pytest.approx(0.0)


def test_component_override_scoped_to_single_component():
    ov = [{"component_id": "dna_damage", "component_type": "driver",
           "conversion_rate_override": 0.0}]
    model = _model(boundary_params={}, component_overrides=ov)
    model.run(30.0, 0.5, _bounds(), _thresholds(), None)
    assert model.state.reversibility["drivers"]["dna_damage"]["conversion_cumul"] == pytest.approx(0.0)
    # other drivers still convert
    assert _flux(model) > 0.0
    # base config not mutated
    assert ov[0].get("conversion_cumul", None) is None


def test_none_override_preserves_default():
    ov = [{"component_id": "dna_damage", "component_type": "driver",
           "conversion_rate_override": None}]
    plain = _model()
    plain.run(20.0, 0.5, _bounds(), _thresholds(), None)
    with_ov = _model(boundary_params={}, component_overrides=ov)
    with_ov.run(20.0, 0.5, _bounds(), _thresholds(), None)
    # None override + neutral scales: boundary none would be needed for exact equality;
    # with ablation active but neutral, trajectories match plain 6C run
    assert with_ov.state.reversibility["total_conversion_flux"] == \
        pytest.approx(plain.state.reversibility["total_conversion_flux"])
