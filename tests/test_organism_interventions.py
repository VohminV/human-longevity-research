"""Stage 5A: intervention classes, policies, trade-offs, neural identity."""

import copy
import math

import pytest

from longevity.experiment.organism_runner import load_organism_config, run_organism_experiment
from longevity.model.intervention import (
    INTERVENTION_TYPES,
    LongevityPolicy,
    PolicySet,
    build_effect,
    validate_effect,
)
from longevity.model.organism import (
    OrganismModel,
    validate_organism_thresholds,
    validate_stage_bounds,
    DEFAULT_ORGANISM_THRESHOLDS,
    DEFAULT_STAGE_BOUNDS,
)

BOUNDS = validate_stage_bounds(dict(DEFAULT_STAGE_BOUNDS))
THRESHOLDS = validate_organism_thresholds(dict(DEFAULT_ORGANISM_THRESHOLDS))


def _run(policies, seed=42, years=80.0, dt=0.5):
    model = OrganismModel(seed=seed)
    trajectory = model.run(years, dt, BOUNDS, THRESHOLDS, PolicySet(policies))
    return model, trajectory


def test_all_intervention_types_build_and_validate():
    assert set(INTERVENTION_TYPES) >= {
        "molecular_repair", "cellular_replacement", "tissue_organ_maintenance",
        "systemic_modulation", "regenerative_boost", "neural_protection",
        "cancer_surveillance", "recovery_support",
    }
    for name in INTERVENTION_TYPES:
        effect = build_effect(name, intensity=1.0, source="test")
        assert validate_effect(effect)["intervention_type"] == name
    with pytest.raises(ValueError):
        build_effect("telepathy")
    with pytest.raises(ValueError):
        build_effect("molecular_repair", intensity=-1.0)
    with pytest.raises(ValueError):
        validate_effect({"intervention_type": "molecular_repair", "delta_damage": float("nan")})
    with pytest.raises(ValueError):
        LongevityPolicy(policy_id="x", intervention_type="molecular_repair",
                        trigger_type="threshold_based", biomarker="")


def test_each_class_moves_its_biomarker():
    cases = [
        ("molecular_repair", "global_damage", -1),
        ("cellular_replacement", "senescence_burden", -1),
        ("systemic_modulation", "inflammation", -1),
        ("tissue_organ_maintenance", "fibrosis", -1),
        ("cancer_surveillance", "cancer_burden", -1),
        ("recovery_support", "functional_reserve", 1),
    ]
    for itype, key, direction in cases:
        model = OrganismModel(seed=5)
        model.run(30.0, 0.5, BOUNDS, THRESHOLDS, None)
        before = dict(model.state.to_dict())
        model.apply_effect(build_effect(itype, intensity=1.0, source="test"), "test")
        after = model.state.to_dict()
        if direction < 0:
            assert after[key] <= before[key] + 1e-12, (itype, key)
        else:
            assert after[key] >= before[key] - 1e-12, (itype, key)


def test_neural_protection_preserves_continuity():
    model = OrganismModel(seed=5)
    model.run(50.0, 0.5, BOUNDS, THRESHOLDS, None)
    before = model.state.systems["brain_cns"]["informational_continuity"]
    model.apply_effect(build_effect("neural_protection", intensity=2.0,
                                    target_systems=["brain_cns"], source="test"), "test")
    after = model.state.systems["brain_cns"]["informational_continuity"]
    assert after >= before - 1e-12
    # Unrestricted aggressive replacement costs reserve and adds cancer risk.
    model2 = OrganismModel(seed=5)
    model2.run(50.0, 0.5, BOUNDS, THRESHOLDS, None)
    snapshot = model2.state.to_dict()
    model2.apply_effect(build_effect("cellular_replacement", intensity=3.0, source="test"), "test")
    assert model2.state.cancer_burden >= snapshot["cancer_burden"] - 1e-12


def test_regenerative_boost_tradeoff():
    model = OrganismModel(seed=5)
    model.run(40.0, 0.5, BOUNDS, THRESHOLDS, None)
    before = model.state.to_dict()
    model.apply_effect(build_effect("regenerative_boost", intensity=2.0, source="test"), "test")
    after = model.state.to_dict()
    assert after["functional_reserve"] >= before["functional_reserve"] - 1e-12
    assert after["cancer_burden"] >= before["cancer_burden"] - 1e-12


def test_interventions_never_create_invalid_state():
    model = OrganismModel(seed=5)
    model.run(60.0, 0.5, BOUNDS, THRESHOLDS, None)
    for itype in INTERVENTION_TYPES:
        state_before = copy.deepcopy(model.state.to_dict())
        model.apply_effect(build_effect(itype, intensity=5.0, source="test"), "test")
        for key, value in model.state.to_dict().items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                assert math.isfinite(float(value)), (itype, key)
        assert model.state.to_dict()["rejuvenation_events"] >= state_before["rejuvenation_events"]


def test_threshold_policy_cooldown_and_constraints():
    policy = LongevityPolicy(policy_id="t", intervention_type="cellular_replacement",
                             trigger_type="threshold_based", interval=2.0,
                             biomarker="senescence_burden", biomarker_threshold=0.05)
    states = {"senescence_burden": 0.2, "cancer_burden": 0.0, "systems": {"a": {"reserve": 1.0}}}
    assert policy.is_due(30.0, states) is True
    assert policy.is_due(30.0, {"senescence_burden": 0.01, "cancer_burden": 0.0,
                                "systems": {"a": {"reserve": 1.0}}}) is False
    assert policy.allows({"cancer_burden": 0.0, "systems": {"a": {"reserve": 1.0}}}) is True
    strict = LongevityPolicy(policy_id="s", intervention_type="cellular_replacement",
                             trigger_type="threshold_based", interval=1.0,
                             biomarker="senescence_burden", biomarker_threshold=0.05,
                             max_cancer_allowed=0.1)
    assert strict.allows({"cancer_burden": 0.5, "systems": {}}) is False
    # Cooldown: PolicySet fires at most once per interval.
    holder = PolicySet([policy.to_dict()])
    first = holder.effects_for_age(30.0, states)
    second = holder.effects_for_age(30.5, states)
    third = holder.effects_for_age(32.0, states)
    assert len(first) == 1 and len(second) == 0 and len(third) == 1


def test_all_stage_configs_load_and_run_short():
    for name in ("organism_life_course_baseline", "organism_life_course_senolytic",
                 "organism_life_course_molecular_repair", "organism_life_course_combined_maintenance",
                 "organism_life_course_adaptive_threshold", "organism_life_course_neural_preserving",
                 "organism_life_course_organ_inspired"):
        config = load_organism_config(f"experiments/configs/{name}.json")
        assert config.to_config_dict()["model_scope"] == "abstract_organism_life_course"
    result = run_organism_experiment(load_organism_config(
        "experiments/configs/organism_life_course_combined_maintenance.json"))
    assert result["model_scope"] == "abstract_organism_life_course"
    assert result["immortality_status"] == "hypothesis_not_proven"
    assert result["summary"]["healthspan"] <= result["summary"]["lifespan"] + 1e-9
