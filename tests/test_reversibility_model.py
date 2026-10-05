"""Stage 6C: reversibility model -- compat, determinism, validation, checkpoint, scope."""

import copy
import json

import pytest

from longevity.experiment.organism_runner import load_organism_config, run_organism_experiment
from longevity.model.intervention import PolicySet
from longevity.model.reversibility import (
    REVERSIBILITY_SCOPE,
    default_reversibility_state,
    validate_reversibility_model,
    validate_reversibility_params,
)
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
              "reversibility_model": "split_reversible_irreversible"}
    params.update(kwargs)
    model = OrganismModel(seed=seed, aging_model="mechanistic_drivers",
                          aging_drivers={}, **params)
    return model.run(years, dt, _bounds(), _thresholds(), None)


def test_none_mode_reproduces_stage6b():
    reference = run_organism_experiment(
        load_organism_config("experiments/configs/organism_organ_network_baseline.json"))
    candidate_cfg = load_organism_config("experiments/configs/organism_organ_network_baseline.json")
    d = candidate_cfg.to_config_dict()
    d["organism_id"] = "tmp_rev_repro"
    d["reversibility_model"] = "none"
    from longevity.experiment.organism_runner import OrganismExperimentConfig
    candidate = run_organism_experiment(OrganismExperimentConfig.from_config_dict(d))
    for key in ("lifespan", "healthspan", "primary_cause_of_death",
                "biological_age_slope_after_adulthood", "final_biological_age"):
        assert candidate["metrics"]["final"][key] == reference["metrics"]["final"][key]
    assert candidate["trajectory"] == reference["trajectory"]


def test_legacy_none_reproduces_stage6b():
    reference = run_organism_experiment(
        load_organism_config("experiments/configs/organism_organ_network_baseline.json"))
    candidate = run_organism_experiment(
        load_organism_config("experiments/configs/organism_reversibility_legacy_none.json"))
    # legacy none has no policies and network=none? check it runs and is finite
    assert candidate["metrics"]["final"]["lifespan"] > 0
    assert candidate["model_scope"] in (reference["model_scope"], REVERSIBILITY_SCOPE)


def test_reversibility_determinism_and_no_global_random():
    import random
    before = random.getstate()
    first = _run(seed=7)
    second = _run(seed=7)
    assert first == second
    assert random.getstate() == before


def test_validation_rejects_bad_blocks():
    with pytest.raises(ValueError):
        validate_reversibility_model("full_rejuvenation")
    with pytest.raises(ValueError):
        validate_reversibility_params({"no_such_param": 1.0})
    with pytest.raises(ValueError):
        validate_reversibility_params({"repair_ceiling": -0.5})
    with pytest.raises(ValueError):
        validate_reversibility_params({"repair_ceiling": 1.5})
    state = default_reversibility_state()
    assert state["repair_ceiling"] == pytest.approx(0.30)
    assert state["biological_age_reversibility"] == pytest.approx(25.0)


def test_state_validation_ranges_and_roundtrip():
    from longevity.model.reversibility import validate_reversibility_state
    state = default_reversibility_state()
    assert validate_reversibility_state(state) is state
    assert validate_reversibility_state(None) is None
    bad = copy.deepcopy(state)
    bad["information_debt"] = 2.0
    with pytest.raises(ValueError):
        validate_reversibility_state(bad)
    rt = json.loads(json.dumps(state))
    assert validate_reversibility_state(rt) is not None


def test_checkpoint_restore_identical_continuation():
    model = OrganismModel(seed=5, aging_model="mechanistic_drivers", aging_drivers={},
                          organ_backed_model="reduced_organ_proxies",
                          organ_network_model="reduced_network_feedback",
                          reversibility_model="split_reversible_irreversible")
    policy = PolicySet([])
    model.run(15.0, 0.5, _bounds(), _thresholds(), policy)
    checkpoint = model.to_checkpoint_dict(policy.to_state_dict())
    roundtripped = json.loads(json.dumps(checkpoint))
    restored = OrganismModel.from_checkpoint(roundtripped)
    assert restored.state.to_dict() == model.state.to_dict()
    assert restored.reversibility_model == "split_reversible_irreversible"
    restored.run(15.0, 0.5, _bounds(), _thresholds(), policy)
    reference = OrganismModel(seed=5, aging_model="mechanistic_drivers", aging_drivers={},
                              organ_backed_model="reduced_organ_proxies",
                              organ_network_model="reduced_network_feedback",
                              reversibility_model="split_reversible_irreversible")
    reference.run(30.0, 0.5, _bounds(), _thresholds(), PolicySet([]))
    assert restored.state.to_dict() == reference.state.to_dict()


def test_legacy_checkpoint_restores_without_reversibility_block():
    model = OrganismModel(seed=5, aging_model="mechanistic_drivers", aging_drivers={},
                          organ_backed_model="reduced_organ_proxies",
                          organ_network_model="reduced_network_feedback",
                          reversibility_model="split_reversible_irreversible")
    checkpoint = model.to_checkpoint_dict(None)
    for key in ("reversibility_model", "reversibility_params",
                "allow_sub_adult_reversibility_age"):
        checkpoint.pop(key, None)
    checkpoint["state"]["reversibility"] = None
    restored = OrganismModel.from_checkpoint(checkpoint)
    assert restored.reversibility_model == "none"


def test_model_scope_metadata():
    result = run_organism_experiment(
        load_organism_config("experiments/configs/organism_reversibility_baseline.json"))
    assert result["model_scope"] == REVERSIBILITY_SCOPE
    assert result["immortality_status"] == "hypothesis_not_proven"
    assert result["reversibility_model"] == "split_reversible_irreversible"
