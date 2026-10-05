"""Stage 6B: organ-network model -- compat, determinism, mapping, checkpoint, scope."""

import copy
import json

import pytest

from longevity.experiment.organism_runner import load_organism_config, run_organism_experiment
from longevity.model.intervention import PolicySet
from longevity.model.organ_backed import ORGAN_PROXIES
from longevity.model.organ_network import (
    ORGAN_NETWORK_SCOPE,
    default_organ_network_state,
    validate_feedback_config,
    validate_hard_limits,
    validate_network_edges,
    validate_organ_network_model,
)
from longevity.model.organism import (
    DEFAULT_ORGANISM_THRESHOLDS,
    DEFAULT_STAGE_BOUNDS,
    MODEL_SCOPE,
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
              "organ_network_model": "reduced_network_feedback"}
    params.update(kwargs)
    model = OrganismModel(seed=seed, aging_model="mechanistic_drivers",
                          aging_drivers={}, **params)
    return model.run(years, dt, _bounds(), _thresholds(), None)


def test_none_mode_reproduces_stage6a():
    reference = run_organism_experiment(
        load_organism_config("experiments/configs/organism_organ_backed_baseline.json"))
    candidate_cfg = load_organism_config("experiments/configs/organism_organ_backed_baseline.json")
    d = candidate_cfg.to_config_dict()
    d["organism_id"] = "tmp_repro"
    d["organ_network_model"] = "none"
    from longevity.experiment.organism_runner import OrganismExperimentConfig
    candidate = run_organism_experiment(OrganismExperimentConfig.from_config_dict(d))
    for key in ("lifespan", "healthspan", "primary_cause_of_death",
                "biological_age_slope_after_adulthood", "final_biological_age"):
        assert candidate["metrics"]["final"][key] == reference["metrics"]["final"][key]
    assert candidate["trajectory"] == reference["trajectory"]


def test_legacy_none_reproduces_stage5c():
    reference = run_organism_experiment(
        load_organism_config("experiments/configs/organism_aging_mechanistic_baseline.json"))
    candidate = run_organism_experiment(
        load_organism_config("experiments/configs/organism_organ_network_legacy_none.json"))
    assert candidate["model_scope"] == MODEL_SCOPE == reference["model_scope"]
    for key in ("lifespan", "healthspan", "primary_cause_of_death"):
        assert candidate["metrics"]["final"][key] == reference["metrics"]["final"][key]
    assert candidate["trajectory"] == reference["trajectory"]


def test_network_determinism_and_no_global_random():
    import random
    before = random.getstate()
    first = _run(seed=7)
    second = _run(seed=7)
    assert first == second
    assert random.getstate() == before


def test_validation_rejects_bad_blocks():
    with pytest.raises(ValueError):
        validate_organ_network_model("full_body")
    with pytest.raises(ValueError):
        validate_network_edges([{"edge_id": "x"}])
    with pytest.raises(ValueError):
        validate_network_edges([{"edge_id": "a", "source": "nope",
                                 "target": "renal_proxy", "edge_type": "vascular_dependency",
                                 "weight": 0.1, "delay_steps": 1, "gain": 1.0,
                                 "failure_threshold": 0.6, "protection_sensitivity": 0.5}])
    with pytest.raises(ValueError):
        validate_feedback_config({"no_loop": {}})
    with pytest.raises(ValueError):
        validate_hard_limits({"no_limit": 1.0})
    assert default_organ_network_state()["energy_budget"] > 0


def test_state_validation_ranges_and_roundtrip():
    state = default_organ_network_state()
    from longevity.model.organ_network import validate_organ_network_state
    assert validate_organ_network_state(state) is state
    assert validate_organ_network_state(None) is None
    bad = copy.deepcopy(state)
    bad["cascade_risk"] = 2.0
    with pytest.raises(ValueError):
        validate_organ_network_state(bad)
    rt = json.loads(json.dumps(state))
    assert validate_organ_network_state(rt) is not None


def test_zero_weight_edges_no_effect():
    model = OrganismModel(seed=3, aging_model="mechanistic_drivers", aging_drivers={},
                          organ_backed_model="reduced_organ_proxies",
                          organ_network_model="reduced_network_feedback",
                          organ_network_edges=[])
    # empty list -> defaults; build explicit zero-weight variant
    from longevity.model.organ_network import DEFAULT_EDGES
    zero = [dict(e, weight=0.0) for e in DEFAULT_EDGES]
    calm = OrganismModel(seed=3, aging_model="mechanistic_drivers", aging_drivers={},
                         organ_backed_model="reduced_organ_proxies",
                         organ_network_model="reduced_network_feedback",
                         organ_network_edges=zero)
    assert calm.network_edges[0]["weight"] == 0.0
    # network object does not mutate input lists
    assert zero[0]["weight"] == 0.0


def test_checkpoint_restore_identical_continuation():
    model = OrganismModel(seed=5, aging_model="mechanistic_drivers", aging_drivers={},
                          organ_backed_model="reduced_organ_proxies",
                          organ_network_model="reduced_network_feedback")
    policy = PolicySet([])
    model.run(15.0, 0.5, _bounds(), _thresholds(), policy)
    checkpoint = model.to_checkpoint_dict(policy.to_state_dict())
    roundtripped = json.loads(json.dumps(checkpoint))
    restored = OrganismModel.from_checkpoint(roundtripped)
    assert restored.state.to_dict() == model.state.to_dict()
    assert restored.organ_network_model == "reduced_network_feedback"
    restored.run(15.0, 0.5, _bounds(), _thresholds(), policy)
    reference = OrganismModel(seed=5, aging_model="mechanistic_drivers", aging_drivers={},
                              organ_backed_model="reduced_organ_proxies",
                              organ_network_model="reduced_network_feedback")
    reference.run(30.0, 0.5, _bounds(), _thresholds(), PolicySet([]))
    assert restored.state.to_dict() == reference.state.to_dict()


def test_legacy_checkpoint_restores_without_network_block():
    model = OrganismModel(seed=5, aging_model="mechanistic_drivers", aging_drivers={},
                          organ_backed_model="reduced_organ_proxies",
                          organ_network_model="reduced_network_feedback")
    checkpoint = model.to_checkpoint_dict(None)
    for key in ("organ_network_model", "organ_network_edges", "organ_network_feedback",
                "organ_network_hard_limits", "irreversible_thresholds", "allow_sub_adult_network_age"):
        checkpoint.pop(key, None)
    checkpoint["state"]["organ_network"] = None
    restored = OrganismModel.from_checkpoint(checkpoint)
    assert restored.organ_network_model == "none"


def test_model_scope_metadata():
    result = run_organism_experiment(
        load_organism_config("experiments/configs/organism_organ_network_baseline.json"))
    assert result["model_scope"] == ORGAN_NETWORK_SCOPE
    assert result["immortality_status"] == "hypothesis_not_proven"
    assert result["organ_network_model"] == "reduced_network_feedback"
    assert "human" not in result["model_scope"].lower() or "abstract" in result["model_scope"].lower()
