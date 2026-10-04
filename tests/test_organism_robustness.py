"""Stage 5B: perturbation model, shocks, cooldown persistence, determinism."""

import copy
import json
import math
import random

import pytest

from longevity.experiment.organism_runner import load_organism_config, run_organism_experiment
from longevity.model.intervention import PolicySet
from longevity.model.organism import (
    OrganismModel,
    SHOCK_TYPES,
    validate_organism_parameters,
    validate_perturbation,
    validate_stage_bounds,
    validate_organism_thresholds,
    DEFAULT_STAGE_BOUNDS,
    DEFAULT_ORGANISM_THRESHOLDS,
)

BOUNDS = validate_stage_bounds(dict(DEFAULT_STAGE_BOUNDS))
THRESHOLDS = validate_organism_thresholds(dict(DEFAULT_ORGANISM_THRESHOLDS))
NOISE = {"model": "parametric_noise", "aging_noise_scale": 0.2,
         "intervention_efficacy_noise_scale": 0.2, "repair_capacity_noise_scale": 0.2}


def _run(seed=42, perturbation=None, years=60.0, dt=0.5, policies=None):
    model = OrganismModel(seed=seed, perturbation=perturbation or {"model": "none"})
    return model.run(years, dt, BOUNDS, THRESHOLDS,
                     PolicySet(policies) if policies else None), model


def test_perturbation_none_is_bit_identical_to_5a():
    plain, _ = _run()
    explicit, _ = _run(perturbation={"model": "none"})
    assert [r["chronological_age"] for r in plain] == [r["chronological_age"] for r in explicit]
    assert plain[-1] == explicit[-1]


def test_perturbation_validation():
    assert validate_perturbation({})["model"] == "none"
    assert validate_perturbation(None)["model"] == "none"
    with pytest.raises(ValueError):
        validate_perturbation({"model": "chaos"})
    with pytest.raises(ValueError):
        validate_perturbation({"model": "none", "aging_noise_scale": -1.0})
    with pytest.raises(ValueError):
        validate_perturbation({"model": "parametric_noise", "shock_probability_per_step": 1.5})
    with pytest.raises(ValueError):
        validate_perturbation({"model": "parametric_noise", "shock_duration_steps": 0})
    with pytest.raises(ValueError):
        validate_perturbation({"model": "none", "telepathy": 1.0})
    with pytest.raises(ValueError):
        validate_perturbation({"model": "none", "shock_types": ["meteor"]})


def test_noise_zero_reproduces_none_and_scales_change_result():
    base, _ = _run(seed=7, perturbation={"model": "parametric_noise", "aging_noise_scale": 0.0,
                                         "intervention_efficacy_noise_scale": 0.0,
                                         "repair_capacity_noise_scale": 0.0})
    none, _ = _run(seed=7)
    assert base[-1] == none[-1]
    noisy, _ = _run(seed=7, perturbation=dict(NOISE))
    assert noisy[-1] != none[-1]
    rerun, _ = _run(seed=7, perturbation=dict(NOISE))
    assert rerun == noisy  # same seed + config => identical
    for row in noisy:
        for key, value in row.items():
            if isinstance(value, float):
                assert math.isfinite(value), key


def test_perturbed_values_stay_physical():
    trajectory, _ = _run(seed=11, perturbation=dict(NOISE, shock_probability_per_step=0.05,
                                                    shock_magnitude_scale=2.0), years=100.0)
    for row in trajectory:
        for name, info in row["systems"].items():
            assert 0.0 <= info["function"] <= 1.0, name
            assert info["reserve"] >= 0.0 and info["damage"] >= 0.0
        assert isinstance(row["active_shocks"], list) and isinstance(row["shock_history"], list)


def test_shock_probability_zero_creates_no_shocks():
    trajectory, _ = _run(seed=13, perturbation={"model": "parametric_noise",
                                                "shock_probability_per_step": 0.0,
                                                "shock_magnitude_scale": 5.0}, years=80.0)
    assert trajectory[-1]["shock_history"] == []
    assert trajectory[-1]["active_shocks"] == []


def test_shocks_fire_record_and_affect_state():
    trajectory, _ = _run(seed=17, perturbation={"model": "parametric_noise",
                                                "shock_probability_per_step": 0.3,
                                                "shock_magnitude_scale": 2.0,
                                                "shock_duration_steps": 2}, years=60.0)
    history = trajectory[-1]["shock_history"]
    assert len(history) > 0
    assert all(set(h) >= {"age", "type", "magnitude", "duration"} for h in history)
    assert all(h["type"] in SHOCK_TYPES for h in history)
    rerun, _ = _run(seed=17, perturbation={"model": "parametric_noise",
                                           "shock_probability_per_step": 0.3,
                                           "shock_magnitude_scale": 2.0,
                                           "shock_duration_steps": 2}, years=60.0)
    assert [h["type"] for h in rerun[-1]["shock_history"]] == [h["type"] for h in history]


def test_shock_types_subset_respected():
    perturbation = {"model": "parametric_noise", "shock_probability_per_step": 0.5,
                    "shock_magnitude_scale": 1.0, "shock_duration_steps": 1,
                    "shock_types": ["neural_stress"]}
    trajectory, _ = _run(seed=19, perturbation=perturbation, years=40.0)
    assert {h["type"] for h in trajectory[-1]["shock_history"]} <= {"neural_stress"}


def test_cooldown_persists_across_checkpoint_restore():
    from longevity.model.intervention import LongevityPolicy
    policies = [LongevityPolicy(policy_id="t", intervention_type="cellular_replacement",
                                trigger_type="threshold_based", interval=5.0,
                                biomarker="senescence_burden", biomarker_threshold=0.01).to_dict()]
    holder = PolicySet(policies)
    model = OrganismModel(seed=42)
    model.run(40.0, 0.5, BOUNDS, THRESHOLDS, holder)
    snapshot = model.to_checkpoint_dict(holder.to_state_dict())
    assert set(snapshot) >= {"policy_cooldown", "perturb_rng", "shock_rng", "perturbation"}
    assert snapshot["policy_cooldown"]["last_fired"], "threshold must have fired by age 40"
    revived = OrganismModel.from_checkpoint(json.loads(json.dumps(snapshot)))
    assert revived.step_count == model.step_count
    holder2 = PolicySet(policies)
    holder2.load_state_dict(snapshot["policy_cooldown"])
    model.run(20.0, 0.5, BOUNDS, THRESHOLDS, holder)
    revived.run(20.0, 0.5, BOUNDS, THRESHOLDS, holder2)
    assert revived.state.to_dict() == model.state.to_dict()
    # Legacy checkpoint without new keys restores cleanly.
    legacy = {k: v for k, v in snapshot.items()
              if k not in ("perturb_rng", "shock_rng", "perturbation", "policy_cooldown")}
    legacy_model = OrganismModel.from_checkpoint(legacy)
    assert legacy_model.state.to_dict()["systems"]["hepatic"]["function"] >= 0.0


def test_perturb_seed_follows_run_seed():
    # Regression: the runner must forward config.seed so per-seed
    # perturbation streams differ (a shared perturb_seed=0 once made all
    # noise runs identical).
    from longevity.experiment.organism_runner import OrganismExperimentConfig
    base = {"organism_id": "x", "seed": 42, "duration_years": 150.0, "dt": 0.5,
            "policies": [], "perturbation": dict(NOISE)}
    first = OrganismModel(seed=7, perturbation=dict(NOISE))
    second = OrganismModel(seed=99, perturbation=dict(NOISE))
    assert first.perturb_seed == 7 and second.perturb_seed == 99
    assert first.perturb_rng.getstate() != second.perturb_rng.getstate()
    cfg7 = OrganismExperimentConfig.from_config_dict({**base, "seed": 7})
    cfg99 = OrganismExperimentConfig.from_config_dict({**base, "seed": 99})
    assert cfg7.effective_perturbation()["model"] == "parametric_noise"


def test_global_random_untouched_with_perturbation():
    before = random.getstate()
    _run(seed=23, perturbation=dict(NOISE, shock_probability_per_step=0.05,
                                   shock_magnitude_scale=1.0))
    assert random.getstate() == before


def test_old_configs_still_load_and_match():
    result = run_organism_experiment(load_organism_config(
        "experiments/configs/organism_life_course_baseline.json"))
    assert result["summary"]["lifespan"] == pytest.approx(68.0)
    assert result["summary"]["primary_cause_of_death"] == "systemic_cascade"
