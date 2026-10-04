"""Stage 4A: organ composition model -- validation, determinism, allocation,
aggregation, viability/causality. Fast: short horizons, no file I/O."""

import copy
import json
import math
import random

import pytest

from longevity.model.organ import (
    DEFAULT_ORGAN_THRESHOLDS,
    ORGAN_FAILURE_CAUSE_ORDER,
    OrganConfig,
    OrganModel,
    aggregate_organ_function,
    bottleneck_tissue,
    evaluate_organ_snapshot,
    organ_failure_causality,
    validate_demand_coefficients,
    validate_organ_thresholds,
)
from longevity.model.organ_policy import (
    COORDINATION_MODES,
    coordination_scale_factor,
    effective_policies_for_step,
    global_cap_scale_factor,
    scaled_policy,
    validate_coordination,
)
from longevity.model.policy import ReplacementPolicy
from longevity.model.tissue import TissueModel, TissueStepContext
from longevity.sim.rng import Rng

DISABLED = {
    "name": "off",
    "enabled": False,
    "target": "none",
    "source": "none",
    "frequency": 5,
    "max_replacement_fraction": 0.0,
    "preserve_architecture": 1.0,
    "immune_compatibility": 1.0,
    "cancer_control": 1.0,
}

ENABLED = {
    "name": "on",
    "enabled": True,
    "target": "senescent",
    "source": "stem_pool",
    "frequency": 5,
    "max_replacement_fraction": 0.1,
    "preserve_architecture": 0.9,
    "immune_compatibility": 0.9,
    "cancer_control": 0.9,
}


def _module(tissue_id="parenchyma", role="parenchyma", policy=None, **overrides):
    base = {
        "tissue_id": tissue_id,
        "role": role,
        "weight": 2.0 if role == "parenchyma" else 1.0,
        "initial_state": {},
        "tissue_parameters": {"stochastic_jitter": 0.0},
        "policy": dict(policy or DISABLED),
        "demand_coefficients": {},
    }
    base.update(overrides)
    return base


def _organ_config(modules=None, steps=15, seed=42, **overrides):
    base = {
        "organ_id": "test-organ",
        "seed": seed,
        "steps": steps,
        "tissues": modules if modules is not None else [_module("parenchyma", "parenchyma"), _module("stroma", "stroma")],
    }
    base.update(overrides)
    return OrganConfig.from_config_dict(base)


# -- 1. context default-identical (Stage 3A regression) ------------------------

def test_neutral_context_matches_default_step():
    policy = ReplacementPolicy.from_dict(ENABLED)
    neutral = TissueStepContext(1.0, 1.0, 0.0)
    first = TissueModel(rng=Rng(7))
    first.run(60, policy)
    second = TissueModel(rng=Rng(7))
    second.run(60, policy, neutral)
    assert first.state.to_dict() == second.state.to_dict()
    assert (first.step_count, first.replacement_events) == (second.step_count, second.replacement_events)


def test_context_validation():
    with pytest.raises(ValueError):
        TissueStepContext(1.5, 1.0, 0.0)
    with pytest.raises(ValueError):
        TissueStepContext(1.0, -0.1, 0.0)
    with pytest.raises(ValueError):
        TissueStepContext(1.0, 1.0, -1.0)


def test_context_effects_are_monotone():
    policy = ReplacementPolicy.from_dict(ENABLED)
    full = TissueModel(rng=Rng(3))
    full.run(80, policy, TissueStepContext(1.0, 1.0, 0.0))
    starved = TissueModel(rng=Rng(3))
    starved.run(80, policy, TissueStepContext(0.0, 0.0, 1.0))
    # No vascular support -> no regeneration; no immune support -> no clearance.
    assert starved.state.functional_cells <= full.state.functional_cells
    assert starved.state.senescent_cells >= full.state.senescent_cells


# -- 2. organ determinism + checkpoint -------------------------------------------

def test_organ_determinism_same_seed():
    first = OrganModel(_organ_config()).run(15)
    second = OrganModel(_organ_config()).run(15)
    assert first == second
    json.dumps(first)


def test_organ_checkpoint_restore_equivalence():
    config = _organ_config(steps=20)
    original = OrganModel(config)
    original.run(8)
    snapshot = original.to_checkpoint_dict()
    original.run(12)
    restored = OrganModel.from_checkpoint(json.loads(json.dumps(snapshot)), config)
    restored.run(12)
    assert [m["model"].state.to_dict() for m in original.modules] == [
        m["model"].state.to_dict() for m in restored.modules
    ]
    assert original.step_count == restored.step_count


def test_organ_leaves_global_random_untouched():
    before = random.getstate()
    OrganModel(_organ_config()).run(10)
    assert random.getstate() == before


# -- 3. validation ------------------------------------------------------------------

def test_organ_config_validation():
    with pytest.raises(ValueError):
        _organ_config(modules=[])
    with pytest.raises(ValueError):
        _organ_config(modules=[_module("same"), _module("same")])
    with pytest.raises(ValueError):
        _organ_config(modules=[_module("x", role="brain")])
    with pytest.raises(ValueError):
        _organ_config(shared_vascular_capacity=-1.0)
    with pytest.raises(ValueError):
        _organ_config(aggregation="median")
    with pytest.raises(ValueError):
        _organ_config(coordination="telepathy")
    with pytest.raises(ValueError):
        _organ_config(global_replacement_cap=-2.0)
    with pytest.raises(ValueError):
        _organ_config(modules=[_module("x", demand_coefficients={"telepathy": 1.0})])
    with pytest.raises(ValueError):
        _organ_config(thresholds={"min_organ_function": 0.5})
    with pytest.raises(ValueError):
        _organ_config(modules=[_module("t", weight=0.0)])
    with pytest.raises(ValueError):
        validate_coordination("unknown-mode")
    assert validate_coordination("independent_tissue_policies") == "independent_tissue_policies"


def test_thresholds_roundtrip():
    assert validate_organ_thresholds(dict(DEFAULT_ORGAN_THRESHOLDS)) == dict(DEFAULT_ORGAN_THRESHOLDS)
    assert validate_demand_coefficients({})["base_vascular_demand"] == pytest.approx(1.0)


# -- 4. allocation ---------------------------------------------------------------------

def test_allocation_ratios():
    assert OrganModel._allocation_ratio(5.0, 10.0) == pytest.approx(1.0)
    assert OrganModel._allocation_ratio(10.0, 10.0) == pytest.approx(1.0)
    assert OrganModel._allocation_ratio(20.0, 10.0) == pytest.approx(0.5)
    assert OrganModel._allocation_ratio(0.0, 10.0) == pytest.approx(1.0)
    assert OrganModel._allocation_ratio(5.0, 0.0) == pytest.approx(0.0)


def test_module_demand_grows_with_burden():
    from longevity.model.tissue import TissueState

    calm = TissueState()
    loaded = TissueState(senescent_cells=5000.0, damaged_cells=2000.0, cancer_risk=0.2, fibrosis_index=0.4)
    demand = validate_demand_coefficients({})
    calm_v, calm_i = OrganModel._module_demand(calm, demand, 0.0)
    loaded_v, loaded_i = OrganModel._module_demand(loaded, demand, 100.0)
    assert loaded_v > calm_v
    assert loaded_i > calm_i
    assert calm_v > 0.0 and calm_i > 0.0


def test_coordination_scale_and_cap():
    assert coordination_scale_factor(5.0, 10.0, 3.0, 6.0) == pytest.approx(1.0)
    assert coordination_scale_factor(20.0, 10.0, 3.0, 6.0) == pytest.approx(0.5)
    assert coordination_scale_factor(0.0, 10.0, 0.0, 6.0) == pytest.approx(1.0)
    assert global_cap_scale_factor([100.0, 100.0], None) == pytest.approx(1.0)
    assert global_cap_scale_factor([100.0, 100.0], 100.0) == pytest.approx(0.5)
    assert global_cap_scale_factor([0.0, 0.0], 10.0) == pytest.approx(1.0)


def test_effective_policies_do_not_mutate_inputs():
    base = [ReplacementPolicy.from_dict(ENABLED), ReplacementPolicy.from_dict(ENABLED)]
    before = [p.to_dict() for p in base]
    effective, scale = effective_policies_for_step(
        base, ["a", "b"], 30.0, 10.0, 3.0, 6.0, "resource_aware_scaling", None, [50.0, 50.0]
    )
    assert [p.to_dict() for p in base] == before
    assert scale == pytest.approx(1.0 / 3.0)
    assert effective[0].max_replacement_fraction == pytest.approx(0.1 / 3.0)
    independent, scale_free = effective_policies_for_step(
        base, ["a", "b"], 30.0, 10.0, 3.0, 6.0, "independent_tissue_policies", None, [50.0, 50.0]
    )
    assert scale_free == pytest.approx(1.0)
    assert independent[0].max_replacement_fraction == pytest.approx(0.1)
    assert scaled_policy(base[0], 1.0, "t").max_replacement_fraction == pytest.approx(0.1)


# -- 5. aggregation -----------------------------------------------------------------------

def test_weighted_sum_and_bottleneck():
    functions = {"parenchyma": 0.8, "stroma": 1.0}
    weights = {"parenchyma": 2.0, "stroma": 1.0}
    assert aggregate_organ_function(functions, weights, mode="weighted_sum") == pytest.approx((1.6 + 1.0) / 3.0)
    assert bottleneck_tissue(functions) == "parenchyma"


def test_min_normalized_and_geometric():
    functions = {"parenchyma": 0.8, "stroma": 1.0}
    weights = {"parenchyma": 1.0, "stroma": 1.0}
    assert aggregate_organ_function(functions, weights, mode="min_normalized") == pytest.approx(0.8)
    geometric = aggregate_organ_function(functions, weights, mode="weighted_geometric")
    assert geometric == pytest.approx(math.sqrt(0.8))
    assert aggregate_organ_function({"a": 0.0, "b": 1.0}, {"a": 1.0, "b": 1.0}, mode="weighted_geometric") == pytest.approx(0.0)


def test_bottleneck_ties_are_deterministic():
    assert bottleneck_tissue({"b": 0.5, "a": 0.5}) == "a"
    with pytest.raises(ValueError):
        aggregate_organ_function({}, {}, mode="weighted_sum")
    with pytest.raises(ValueError):
        aggregate_organ_function({"a": 0.5}, {"a": 1.0}, mode="median")
    with pytest.raises(ValueError):
        bottleneck_tissue({})


# -- 6. viability and causality ---------------------------------------------------------------

def _snapshot(time=10.0, organ_function=1.0, vasc=1.0, imm=1.0, cancer=0.0, fibrosis=0.0,
              vital=(("parenchyma", "parenchyma", 1.0), ("stroma", "stroma", 1.0))):
    tissues = {
        tid: {"role": role, "is_vital": True, "tissue_function": value,
              "replacement_events": 0, "total_replaced_cells": 0.0,
              "state": {"functional_cells": 8000.0 * value, "damaged_cells": 0.0, "senescent_cells": 0.0,
                        "stem_cells": 500.0, "dead_cells": 0.0, "ecm_quality": 0.9, "vascular_quality": 0.9,
                        "immune_pressure": 0.1, "cancer_risk": cancer, "fibrosis_index": fibrosis}}
        for tid, role, value in vital
    }
    return {
        "time": time, "organ_function": organ_function, "bottleneck_tissue": "parenchyma",
        "min_normalized_tissue_function": 1.0, "organ_cancer_risk": cancer, "organ_fibrosis_index": fibrosis,
        "total_vascular_demand": 5.0, "total_immune_demand": 2.0,
        "vascular_allocation_ratio": vasc, "immune_allocation_ratio": imm,
        "vascular_shortfall": 0.0, "immune_shortfall": 0.0, "coordination_scale": 1.0,
        "tissue_roles": {tid: role for tid, role, _ in vital}, "tissues": tissues,
    }


def test_healthy_organ_is_viable_with_none_cause():
    snapshot = _snapshot()
    vital = {"parenchyma": 1.0, "stroma": 1.0}
    viable, violations = evaluate_organ_snapshot(snapshot, dict(DEFAULT_ORGAN_THRESHOLDS), vital)
    assert viable and violations == []
    out = organ_failure_causality([_snapshot(time=0.0), _snapshot(time=10.0)], dict(DEFAULT_ORGAN_THRESHOLDS))
    assert out["primary_organ_failure_cause"] == "none"
    assert out["organ_failure_cause_sequence"] == []


def test_each_cause_detected():
    thresholds = dict(DEFAULT_ORGAN_THRESHOLDS)
    cases = [
        ({"vasc": 0.1}, "vascular_capacity_failure"),
        ({"imm": 0.1}, "immune_capacity_failure"),
        ({"cancer": 0.9}, "organ_cancer_risk"),
        ({"fibrosis": 0.9}, "organ_fibrosis"),
        ({"organ_function": 0.1}, "organ_function_failure"),
    ]
    for kwargs, expected in cases:
        snapshot = _snapshot(**kwargs)
        vital = {"parenchyma": 1.0, "stroma": 1.0}
        viable, violations = evaluate_organ_snapshot(snapshot, thresholds, vital)
        assert not viable and expected in violations
    parenchyma_bad = _snapshot(vital=(("parenchyma", "parenchyma", 0.1), ("stroma", "stroma", 1.0)))
    _, violations = evaluate_organ_snapshot(
        parenchyma_bad, thresholds, {"parenchyma": 0.1, "stroma": 1.0}
    )
    assert "parenchyma_failure" in violations


def test_simultaneous_causes_and_order():
    thresholds = dict(DEFAULT_ORGAN_THRESHOLDS)
    trajectory = [_snapshot(time=0.0), _snapshot(time=5.0, vasc=0.1, imm=0.1)]
    before = copy.deepcopy(trajectory)
    out = organ_failure_causality(trajectory, thresholds)
    assert trajectory == before
    assert out["primary_organ_failure_cause"] == "multiple_simultaneous"
    assert out["organ_failure_cause_sequence"] == ["vascular_capacity_failure", "immune_capacity_failure"]
    assert out["first_vascular_capacity_failure_time"] == pytest.approx(5.0)


def test_cause_vocabulary():
    assert set(ORGAN_FAILURE_CAUSE_ORDER) >= {
        "parenchyma_failure", "stroma_failure", "vascular_capacity_failure",
        "immune_capacity_failure", "organ_cancer_risk", "organ_fibrosis",
    }
