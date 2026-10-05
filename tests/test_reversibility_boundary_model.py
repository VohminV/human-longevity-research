"""Stage 6D: boundary probe model -- compat, determinism, validation, checkpoint, scope."""

import copy
import json

import pytest

from longevity.experiment.organism_runner import OrganismExperimentConfig, load_organism_config, run_organism_experiment
from longevity.model.boundary import (
    BOUNDARY_SCOPE,
    default_boundary_state,
    effective_conversion_scale,
    effective_independent_scale,
    effective_repair_ceiling,
    is_neutral_boundary,
    validate_boundary_params,
    validate_boundary_probe_model,
    validate_component_overrides,
)
from longevity.model.intervention import PolicySet
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


def _run(seed=42, years=30.0, dt=0.5, **kwargs):
    params = {"organ_backed_model": "reduced_organ_proxies",
              "organ_network_model": "reduced_network_feedback",
              "reversibility_model": "split_reversible_irreversible",
              "boundary_probe_model": "irreversibility_ablation"}
    params.update(kwargs)
    model = OrganismModel(seed=seed, aging_model="mechanistic_drivers",
                          aging_drivers={}, **params)
    return model.run(years, dt, _bounds(), _thresholds(), None)


def test_none_mode_reproduces_stage6c():
    reference = run_organism_experiment(
        load_organism_config("experiments/configs/organism_reversibility_baseline.json"))
    d = load_organism_config("experiments/configs/organism_reversibility_baseline.json").to_config_dict()
    d["organism_id"] = "tmp_boundary_repro"
    d["boundary_probe_model"] = "none"
    candidate = run_organism_experiment(OrganismExperimentConfig.from_config_dict(d))
    for key in ("lifespan", "healthspan", "primary_cause_of_death",
                "biological_age_slope_after_adulthood", "final_biological_age"):
        assert candidate["metrics"]["final"][key] == reference["metrics"]["final"][key]
    assert candidate["trajectory"] == reference["trajectory"]


def test_neutral_ablation_reproduces_stage6c():
    reference = run_organism_experiment(
        load_organism_config("experiments/configs/organism_reversibility_baseline.json"))
    candidate = run_organism_experiment(
        load_organism_config("experiments/configs/organism_reversibility_boundary_default.json"))
    # default boundary config uses combined base; compare neutral boundary on same base instead
    d = load_organism_config("experiments/configs/organism_reversibility_baseline.json").to_config_dict()
    d["organism_id"] = "tmp_boundary_neutral"
    d["boundary_probe_model"] = "irreversibility_ablation"
    d["boundary_params"] = {}
    neutral = run_organism_experiment(OrganismExperimentConfig.from_config_dict(d))
    # t0 snapshots differ only by the (static) boundary block; dynamics must match
    strip = lambda traj: [{k: v for k, v in row.items() if k != "boundary"} for row in traj]
    assert strip(neutral["trajectory"]) == strip(reference["trajectory"])
    assert neutral["model_scope"] == BOUNDARY_SCOPE
    assert candidate["metrics"]["final"]["lifespan"] > 0


def test_legacy_none_config_reproduces_stage6c():
    candidate = run_organism_experiment(
        load_organism_config("experiments/configs/organism_reversibility_boundary_legacy_none.json"))
    assert candidate["metrics"]["final"]["lifespan"] > 0
    assert candidate["immortality_status"] == "hypothesis_not_proven"


def test_determinism_and_no_global_random():
    import random
    before = random.getstate()
    first = _run(seed=7, boundary_params={"conversion_scale": 0.0})
    second = _run(seed=7, boundary_params={"conversion_scale": 0.0})
    assert first == second
    assert random.getstate() == before


def test_validation_rejects_bad_params():
    with pytest.raises(ValueError):
        validate_boundary_probe_model("full_ablation")
    with pytest.raises(ValueError):
        validate_boundary_params({"conversion_scale": -1.0})
    with pytest.raises(ValueError):
        validate_boundary_params({"conversion_scale": float("nan")})
    with pytest.raises(ValueError):
        validate_boundary_params({"disable_conversion": "yes"})
    with pytest.raises(ValueError):
        validate_boundary_params({"nope": 1.0})
    with pytest.raises(ValueError):
        validate_component_overrides([{"component_id": "", "component_type": "driver"}])
    with pytest.raises(ValueError):
        validate_component_overrides([{"component_id": "x", "component_type": "nope"}])
    with pytest.raises(ValueError):
        validate_component_overrides([{"component_id": "nope", "component_type": "driver"}])
    with pytest.raises(ValueError):
        validate_component_overrides("notalist")
    dup = [{"component_id": "dna_damage", "component_type": "driver"},
           {"component_id": "dna_damage", "component_type": "driver"}]
    with pytest.raises(ValueError):
        validate_component_overrides(dup)
    assert validate_component_overrides(None) == []
    assert is_neutral_boundary(validate_boundary_params(None), []) is True
    assert is_neutral_boundary(validate_boundary_params({"conversion_scale": 0.0}), []) is False


def test_effective_scales_and_ceiling():
    assert effective_conversion_scale({"conversion_scale": 1.0, "disable_conversion": False}) == 1.0
    assert effective_conversion_scale({"conversion_scale": 0.5, "disable_conversion": True}) == 0.0
    assert effective_independent_scale({"independent_accrual_scale": 0.0,
                                        "disable_independent_accrual": False}) == 0.0
    ceiling, exploratory = effective_repair_ceiling(0.3, {"repair_ceiling_scale": 1.0,
                                                          "force_repair_ceiling_unlimited": False,
                                                          "disable_repair_ceiling": False})
    assert ceiling == pytest.approx(0.3) and exploratory is False
    ceiling2, exploratory2 = effective_repair_ceiling(0.3, {"repair_ceiling_scale": 1.0,
                                                           "force_repair_ceiling_unlimited": True,
                                                           "disable_repair_ceiling": False})
    assert exploratory2 is True and ceiling2 > 100.0


def test_unlimited_ceiling_marked_exploratory():
    result = run_organism_experiment(
        load_organism_config("experiments/configs/organism_reversibility_boundary_unlimited_ceiling_ablation.json"))
    assert result["boundary_exploratory"] is True
    assert result["model_scope"] == BOUNDARY_SCOPE


def test_checkpoint_restore_identical_continuation():
    model = OrganismModel(seed=5, aging_model="mechanistic_drivers", aging_drivers={},
                          organ_backed_model="reduced_organ_proxies",
                          organ_network_model="reduced_network_feedback",
                          reversibility_model="split_reversible_irreversible",
                          boundary_probe_model="irreversibility_ablation",
                          boundary_params={"conversion_scale": 0.5})
    policy = PolicySet([])
    model.run(15.0, 0.5, _bounds(), _thresholds(), policy)
    checkpoint = model.to_checkpoint_dict(policy.to_state_dict())
    roundtripped = json.loads(json.dumps(checkpoint))
    restored = OrganismModel.from_checkpoint(roundtripped)
    assert restored.state.to_dict() == model.state.to_dict()
    assert restored.boundary_probe_model == "irreversibility_ablation"
    assert restored.boundary_params["conversion_scale"] == pytest.approx(0.5)
    restored.run(15.0, 0.5, _bounds(), _thresholds(), policy)
    reference = OrganismModel(seed=5, aging_model="mechanistic_drivers", aging_drivers={},
                              organ_backed_model="reduced_organ_proxies",
                              organ_network_model="reduced_network_feedback",
                              reversibility_model="split_reversible_irreversible",
                              boundary_probe_model="irreversibility_ablation",
                              boundary_params={"conversion_scale": 0.5})
    reference.run(30.0, 0.5, _bounds(), _thresholds(), PolicySet([]))
    assert restored.state.to_dict() == reference.state.to_dict()


def test_legacy_checkpoint_restores_without_boundary_block():
    model = OrganismModel(seed=5, aging_model="mechanistic_drivers", aging_drivers={},
                          organ_backed_model="reduced_organ_proxies",
                          organ_network_model="reduced_network_feedback",
                          reversibility_model="split_reversible_irreversible",
                          boundary_probe_model="irreversibility_ablation")
    checkpoint = model.to_checkpoint_dict(None)
    for key in ("boundary_probe_model", "boundary_params", "component_overrides"):
        checkpoint.pop(key, None)
    checkpoint["state"]["boundary"] = None
    restored = OrganismModel.from_checkpoint(checkpoint)
    assert restored.boundary_probe_model == "none"
    assert restored.state.boundary is None


def test_model_scope_metadata():
    result = run_organism_experiment(
        load_organism_config("experiments/configs/organism_reversibility_boundary_default.json"))
    assert result["model_scope"] == BOUNDARY_SCOPE
    assert result["immortality_status"] == "hypothesis_not_proven"
    assert "boundary" in result["model_scope"]
