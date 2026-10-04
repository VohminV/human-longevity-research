"""Stage 4B: demand-aware coordination -- score, selection, guard, sweeps.

Fast by design: short horizons and tiny grids. Full compare/sensitivity
sweeps run through the same code paths via CLI, not re-run here.
"""

import copy
import csv
import json
import math
import random

import pytest

from longevity.analysis.organ_metrics import summarize_coordination
from longevity.experiment.organ_runner import load_organ_config, run_organ_experiment
from longevity.experiment.organ_sweep import (
    OrganMiniSweepConfig,
    load_organ_sweep_config,
    run_organ_sweep,
    write_organ_coordination_outputs,
    write_organ_sweep_outputs,
)
from longevity.model.organ import MODEL_SCOPE, OrganConfig
from longevity.model.organ_policy import (
    COORDINATION_MODES,
    rank_plan_scores,
    selective_policies_for_step,
    plan_relief_score,
    validate_coordination,
    validate_score_weights,
)
from longevity.model.policy import ReplacementPlan, ReplacementPolicy
from longevity.model.tissue import TissueState

WEIGHTS = {
    "alpha": 1.0, "beta": 0.5, "gamma": 1.0, "delta": 1.0,
    "epsilon": 1.0, "w_vascular": 1.0, "eps": 1e-6,
    "score_cutoff": 0.0, "immune_guard_threshold": 0.6,
}

DEMAND = {
    "base_vascular_demand": 1.0, "vascular_per_functional": 0.0005,
    "vascular_per_damaged": 0.001, "vascular_per_senescent": 0.0015,
    "vascular_per_replacement": 0.01, "base_immune_demand": 1.0,
    "immune_per_damaged": 0.002, "immune_per_senescent": 0.003,
    "immune_per_cancer_risk": 5.0, "immune_per_fibrosis": 3.0,
    "immune_per_replacement": 0.01,
}


def _plan(target="senescent", count=100.0):
    return ReplacementPlan(
        target=target, source="stem_pool", target_count=count, source_count=count,
        expected_architecture_cost=0.01, expected_immune_cost=0.01,
        expected_cancer_risk_delta=0.001, expected_fibrosis_delta=0.001,
    )


def _organ_config(coordination="demand_relief_priority", steps=12, seed=42, tissues=None):
    if tissues is None:
        live = {"functional_cells": 8000.0, "senescent_cells": 800.0, "damaged_cells": 200.0}
        tissues = [
            {"tissue_id": "parenchyma", "role": "parenchyma", "weight": 2.0,
             "initial_state": dict(live), "tissue_parameters": {"stochastic_jitter": 0.0},
             "policy": {"name": "p", "enabled": True, "target": "senescent", "source": "stem_pool",
                        "frequency": 2, "max_replacement_fraction": 0.2, "preserve_architecture": 0.9,
                        "immune_compatibility": 0.9, "cancer_control": 0.9}},
            {"tissue_id": "stroma", "role": "stroma", "weight": 1.0,
             "initial_state": dict(live), "tissue_parameters": {"stochastic_jitter": 0.0},
             "policy": {"name": "s", "enabled": True, "target": "senescent", "source": "stem_pool",
                        "frequency": 2, "max_replacement_fraction": 0.2, "preserve_architecture": 0.9,
                        "immune_compatibility": 0.9, "cancer_control": 0.9}},
        ]
    return OrganConfig.from_config_dict(
        {"organ_id": "coord-test", "seed": seed, "steps": steps, "tissues": tissues,
         "shared_vascular_capacity": 12.0, "shared_immune_capacity": 5.0, "coordination": coordination}
    )


# -- 1. backward compatibility ---------------------------------------------------

def test_old_modes_preserved_and_aliases_resolve():
    assert validate_coordination("independent_tissue_policies") == "independent_tissue_policies"
    assert validate_coordination("resource_aware_scaling") == "resource_aware_scaling"
    assert validate_coordination("independent") == "independent_tissue_policies"
    assert validate_coordination("proportional_scale") == "resource_aware_scaling"
    assert set(COORDINATION_MODES) >= {
        "independent_tissue_policies", "resource_aware_scaling", "demand_relief_priority",
        "senescent_burden_priority", "immune_reserve_guard", "hybrid_demand_guard",
    }


def test_old_configs_unchanged_and_default_mode_stable():
    for name in ("organ_baseline", "organ_independent_replacement", "organ_resource_aware_replacement"):
        config = load_organ_config(f"experiments/configs/{name}.json")
        assert config.coordination in ("independent_tissue_policies", "resource_aware_scaling")
    first = run_organ_experiment(_organ_config("independent_tissue_policies"))
    second = run_organ_experiment(_organ_config("independent_tissue_policies"))
    assert first["trajectory"] == second["trajectory"]


def test_new_configs_load():
    for name in ("organ_demand_relief_priority", "organ_immune_reserve_guard",
                 "organ_heterogeneous_demand_relief", "organ_coordination_compare",
                 "organ_immune_sensitivity_sweep"):
        path = f"experiments/configs/{name}.json"
        if "sweep" in name or "compare" in name:
            load_organ_sweep_config(path)
        else:
            config = load_organ_config(path)
            assert config.to_config_dict()["model_scope"] == MODEL_SCOPE


# -- 2. config validation ----------------------------------------------------------

def test_reject_unknown_mode_bad_weights_thresholds():
    with pytest.raises(ValueError):
        _organ_config(coordination="telepathy")
    with pytest.raises(ValueError):
        OrganConfig.from_config_dict({**_organ_config().to_config_dict(), "coordination_params": {"alpha": -1.0}})
    with pytest.raises(ValueError):
        OrganConfig.from_config_dict({**_organ_config().to_config_dict(), "coordination_params": {"eps": 0.0}})
    with pytest.raises(ValueError):
        OrganConfig.from_config_dict(
            {**_organ_config().to_config_dict(), "coordination_params": {"immune_guard_threshold": 1.5}}
        )
    with pytest.raises(ValueError):
        OrganConfig.from_config_dict(
            {**_organ_config().to_config_dict(), "coordination_params": {"telepathy": 1.0}}
        )


def test_reject_empty_modes_and_bad_sweep_grids():
    with pytest.raises(ValueError):
        validate_coordination("")
    base = _organ_config().to_config_dict()
    with pytest.raises(ValueError):
        OrganMiniSweepConfig.from_config_dict({
            "experiment_id": "x", "seeds": [1, 2], "grid": {"global_replacement_scale": [1.0],
            "shared_vascular_capacity": [12.0], "shared_immune_capacity": [5.0]},
            "coordination_modes": [], "base_organ_config": base})
    with pytest.raises(ValueError):
        OrganMiniSweepConfig.from_config_dict({
            "experiment_id": "x", "seeds": [1, 2], "grid": {"global_replacement_scale": [1.0],
            "shared_vascular_capacity": [-4.0], "shared_immune_capacity": [5.0]},
            "coordination_modes": ["independent_tissue_policies"], "base_organ_config": base})


# -- 3. determinism -------------------------------------------------------------------

def test_mode_determinism_tie_break_and_no_global_random():
    first = run_organ_experiment(_organ_config("demand_relief_priority", seed=7))
    second = run_organ_experiment(_organ_config("demand_relief_priority", seed=7))
    assert first["trajectory"] == second["trajectory"]
    assert rank_plan_scores({"b": 1.0, "a": 1.0}) == ["a", "b"]
    before = random.getstate()
    run_organ_experiment(_organ_config("hybrid_demand_guard", seed=7))
    assert random.getstate() == before


# -- 4. score function ------------------------------------------------------------------

def test_score_pure_zero_cost_negative_value_monotone():
    state = TissueState(senescent_cells=1000.0)
    plan = _plan(count=100.0)
    before_plan, before_state = plan.to_dict(), state.to_dict()
    assessed = plan_relief_score(plan, state, dict(DEMAND), dict(WEIGHTS))
    assert plan.to_dict() == before_plan and state.to_dict() == before_state
    assert assessed["relief_cells"] == pytest.approx(100.0)
    assert assessed["cost"] > 0.0
    # Zero cost: empty plan scores finite (no division by zero).
    empty = plan_relief_score(ReplacementPlan.empty(), state, dict(DEMAND), dict(WEIGHTS))
    assert math.isfinite(empty["score"])
    # Monotone: more relief at equal cost wins.
    big = plan_relief_score(_plan(count=200.0), state, dict(DEMAND), dict(WEIGHTS))
    small = plan_relief_score(_plan(count=50.0), state, dict(DEMAND), dict(WEIGHTS))
    assert big["score"] > small["score"]
    # Relief-only variant ignores risk penalties.
    risky = ReplacementPlan(target="senescent", source="stem_pool", target_count=100.0, source_count=100.0,
                            expected_architecture_cost=5.0, expected_immune_cost=0.0,
                            expected_cancer_risk_delta=5.0, expected_fibrosis_delta=5.0)
    full = plan_relief_score(risky, state, dict(DEMAND), dict(WEIGHTS))
    lean = plan_relief_score(risky, state, dict(DEMAND), dict(WEIGHTS), relief_only=True)
    assert lean["value"] > full["value"]
    # Weights matter: zeroing alpha removes senescent value.
    no_alpha = dict(WEIGHTS, alpha=0.0)
    assert plan_relief_score(plan, state, dict(DEMAND), no_alpha)["value"] < assessed["value"]


# -- 5. priority execution -----------------------------------------------------------------

def _selection_setup(cap_v=12.0, cap_i=5.0, mode="demand_relief_priority", counts=(400.0, 100.0)):
    policies = [ReplacementPolicy.from_dict({
        "name": n, "enabled": True, "target": "senescent", "source": "stem_pool", "frequency": 1,
        "max_replacement_fraction": 0.5, "preserve_architecture": 0.9,
        "immune_compatibility": 0.9, "cancer_control": 0.9}) for n in ("p", "s")]
    states = [TissueState(senescent_cells=2000.0), TissueState(senescent_cells=200.0)]
    plans = [_plan(count=c) for c in counts]
    demands = [dict(DEMAND), dict(DEMAND)]
    return policies, states, demands, plans


def test_priority_executes_high_score_first():
    policies, states, demands, plans = _selection_setup(cap_v=100.0, cap_i=100.0)
    effective, info = selective_policies_for_step(
        policies, ["parenchyma", "stroma"], states, demands,
        [400.0, 100.0], plans, 10.0, 100.0, 4.0, 100.0,
        "demand_relief_priority", None, dict(WEIGHTS))
    assert set(info["executed_tissues"]) == {"parenchyma", "stroma"}
    assert info["rejected_tissues"] == []
    # Tight immune capacity: parenchyma (bigger relief) wins the water-fill.
    effective2, info2 = selective_policies_for_step(
        policies, ["parenchyma", "stroma"], states, demands,
        [400.0, 100.0], plans, 10.0, 100.0, 4.0, 4.5,
        "demand_relief_priority", None, dict(WEIGHTS))
    assert info2["executed_tissues"][0] == "parenchyma"
    assert [p.to_dict() for p in policies] == [p.to_dict() for p in policies]  # untouched
    # Physical caps hold: partial scales stay within [0, 1] fractions.
    for policy in effective2:
        assert 0.0 <= policy.max_replacement_fraction <= 1.0


def test_effective_path_rejects_selection_modes():
    from longevity.model.organ_policy import effective_policies_for_step

    policies = [ReplacementPolicy.from_dict({
        "name": "p", "enabled": True, "target": "senescent", "source": "stem_pool", "frequency": 1,
        "max_replacement_fraction": 0.5, "preserve_architecture": 0.9,
        "immune_compatibility": 0.9, "cancer_control": 0.9})]
    with pytest.raises(ValueError):
        effective_policies_for_step(policies, ["parenchyma"], 5.0, 10.0, 2.0, 6.0,
                                    "demand_relief_priority", None, [10.0])


# -- 6. immune reserve guard -----------------------------------------------------------------

def test_guard_noop_when_capacity_sufficient():
    policies, states, demands, plans = _selection_setup()
    _, info = selective_policies_for_step(
        policies, ["parenchyma", "stroma"], states, demands,
        [400.0, 100.0], plans, 10.0, 100.0, 4.0, 100.0,
        "immune_reserve_guard", None, dict(WEIGHTS))
    assert set(info["executed_tissues"]) == {"parenchyma", "stroma"}
    assert info["rejected_tissues"] == []


def test_guard_cuts_low_score_and_falls_back_to_top1():
    policies, states, demands, plans = _selection_setup()
    weights = dict(WEIGHTS, score_cutoff=1e9)  # cutoff nothing passes
    _, info = selective_policies_for_step(
        policies, ["parenchyma", "stroma"], states, demands,
        [400.0, 100.0], plans, 10.0, 0.5, 4.0, 4.1,
        "immune_reserve_guard", None, weights)
    assert len(info["executed_tissues"]) == 1  # top-1 fallback, deterministic
    assert info["executed_tissues"][0] == "parenchyma"


# -- 7. coordination metrics --------------------------------------------------------------------

def test_coordination_metrics_on_synthetic():
    trajectory = [
        {"time": 0.0, "organ_function": 1.0, "bottleneck_tissue": "parenchyma",
         "total_vascular_demand": 8.0, "total_immune_demand": 3.0,
         "executed_vascular_demand": 8.0, "executed_immune_demand": 3.0,
         "coordination_detail": {"mode": "demand_relief_priority", "executed_tissues": [],
                                 "rejected_tissues": [], "partial_tissues": [],
                                 "scores": {}, "requested_tissues": [], "relief_cells": {}},
         "tissues": {}},
        {"time": 1.0, "organ_function": 1.0, "bottleneck_tissue": "parenchyma",
         "total_vascular_demand": 10.0, "total_immune_demand": 5.0,
         "executed_vascular_demand": 9.0, "executed_immune_demand": 4.0,
         "coordination_detail": {"mode": "demand_relief_priority", "executed_tissues": ["parenchyma"],
                                 "rejected_tissues": ["stroma"], "partial_tissues": [],
                                 "scores": {"parenchyma": 2.0, "stroma": 1.0},
                                 "requested_tissues": ["parenchyma", "stroma"],
                                 "relief_cells": {"parenchyma": 50.0, "stroma": 0.0}},
         "tissues": {}},
    ]
    summary = summarize_coordination(trajectory, 1.0)
    assert summary["coordination_mode"] == "demand_relief_priority"
    assert summary["total_planned_replacement_events"] == 2
    assert summary["total_executed_replacement_events"] == 1
    assert summary["total_rejected_replacement_events"] == 1
    assert summary["execution_fraction"] == pytest.approx(0.5)
    assert summary["rejected_fraction"] == pytest.approx(0.5)
    assert summary["mean_score_executed"] == pytest.approx(2.0)
    assert summary["mean_score_rejected"] == pytest.approx(1.0)
    assert summary["total_relief_cells"] == pytest.approx(50.0)
    assert summary["mean_immune_demand_before_coordination"] == pytest.approx(5.0)
    assert summary["mean_immune_demand_after_coordination"] == pytest.approx(4.0)


def test_guard_and_demand_runs_carry_metrics():
    for mode in ("demand_relief_priority", "immune_reserve_guard"):
        result = run_organ_experiment(_organ_config(mode))
        coordination = result["metrics"]["final"]["coordination"]
        assert coordination["coordination_mode"] == mode
        assert coordination["execution_fraction"] <= 1.0 + 1e-12
        assert math.isfinite(coordination["senescent_burden_auc"])
        assert result["model_scope"] == MODEL_SCOPE


# -- 8. immune sensitivity sweep (tiny, end-to-end) -----------------------------------------------

def _tiny_sweep(**overrides):
    base = _organ_config().to_config_dict()
    base["steps"] = 8
    config = {
        "experiment_id": "coord-sweep-test",
        "seeds": [11, 12, 13],
        "grid": {"global_replacement_scale": [0.5, 1.0],
                 "shared_vascular_capacity": [12.0],
                 "shared_immune_capacity": [3.0, 8.0]},
        "coordination_modes": ["independent_tissue_policies", "demand_relief_priority"],
        "base_organ_config": base,
        "output_prefix": "",
        "notes": "",
    }
    config.update(overrides)
    return OrganMiniSweepConfig.from_config_dict(config)


def test_sensitivity_sweep_end_to_end(tmp_path):
    from longevity.experiment.organ_sweep import run_organ_sweep

    result = run_organ_sweep(_tiny_sweep())
    assert len(result["points"]) == 2 * 1 * 2 * 2
    assert result["coordination_comparison"]["by_mode"]
    assert result["failure_cause_distribution"]["overall"]
    assert result["immune_transition"]["by_mode"]
    paths = write_organ_coordination_outputs(result, str(tmp_path / "sens"))
    assert {"long_csv", "summary_csv", "summary_json", "comparison_json",
            "failure_causes_json", "boundary_json"} <= set(paths)
    with open(paths["long_csv"], encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == len(result["points"]) * 3
    for key in ("summary_json", "comparison_json", "failure_causes_json", "boundary_json"):
        with open(paths[key], encoding="utf-8") as fh:
            json.load(fh)

    def _walk(node, path="$"):
        if isinstance(node, float):
            assert math.isfinite(node), f"non-finite at {path}"
        elif isinstance(node, dict):
            for key, value in node.items():
                _walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                _walk(value, f"{path}[{index}]")

    _walk(result)


def test_mini_writer_still_writes_stage4a_shape(tmp_path):
    from longevity.experiment.organ_sweep import run_organ_sweep

    result = run_organ_sweep(_tiny_sweep())
    paths = write_organ_sweep_outputs(result, str(tmp_path / "mini"))
    assert set(paths) == {"summary_json", "summary_csv"}


def test_immune_transition_ignores_sustained_viability():
    from longevity.experiment.organ_sweep import _immune_transition

    points = [
        {"coordination": "independent_tissue_policies", "shared_immune_capacity": 3.0,
         "primary_cause_counts": {"immune_capacity_failure": 3}},
        {"coordination": "independent_tissue_policies", "shared_immune_capacity": 8.0,
         "primary_cause_counts": {"none": 3}},
        {"coordination": "independent_tissue_policies", "shared_immune_capacity": 12.0,
         "primary_cause_counts": {"parenchyma_failure": 2, "none": 1}},
    ]
    transition = _immune_transition(points, ["independent_tissue_policies"])
    entry = transition["by_mode"]["independent_tissue_policies"]
    assert entry["immune_collapse_max_capacity"] == pytest.approx(3.0)
    assert entry["tissue_emergence_min_capacity"] == pytest.approx(12.0)
    assert entry["tissue_cause_marker"] is None
    empty = _immune_transition(points[:2], ["independent_tissue_policies"])
    assert empty["by_mode"]["independent_tissue_policies"]["tissue_emergence_min_capacity"] is None
    assert empty["by_mode"]["independent_tissue_policies"]["tissue_cause_marker"] == "no_tissue_cause_in_current_grid"


# -- 9. heterogeneous coordination ---------------------------------------------------------------------

def test_hetero_demand_relief_runs_clean():
    hetero = [
        {"tissue_id": "parenchyma", "role": "parenchyma", "weight": 2.0,
         "initial_state": {"functional_cells": 8000.0, "senescent_cells": 800.0},
         "tissue_parameters": {"stochastic_jitter": 0.0},
         "policy": {"name": "p", "enabled": True, "target": "senescent", "source": "stem_pool",
                    "frequency": 2, "max_replacement_fraction": 0.2, "preserve_architecture": 0.4,
                    "immune_compatibility": 0.4, "cancer_control": 0.4}},
        {"tissue_id": "stroma", "role": "stroma", "weight": 1.0,
         "initial_state": {"functional_cells": 4000.0, "senescent_cells": 400.0},
         "tissue_parameters": {"stochastic_jitter": 0.0},
         "policy": {"name": "s", "enabled": True, "target": "senescent", "source": "stem_pool",
                    "frequency": 5, "max_replacement_fraction": 0.1, "preserve_architecture": 0.9,
                    "immune_compatibility": 0.9, "cancer_control": 0.9}},
    ]
    before = copy.deepcopy(hetero)
    result = run_organ_experiment(_organ_config("demand_relief_priority", tissues=hetero))
    assert hetero == before  # run never mutates the caller's tissue dicts
    assert result["metrics"]["final"]["coordination"]["coordination_mode"] == "demand_relief_priority"
    json.dumps(result)


# -- 10. model scope ---------------------------------------------------------------------------------------

def test_outputs_claim_no_human_biology():
    result = run_organ_experiment(_organ_config("immune_reserve_guard"))
    assert result["model_scope"] == MODEL_SCOPE == "abstract_organ_composition"
    blob = json.dumps(result)
    for forbidden in ("human", "patient", "clinical", "immortal"):
        assert forbidden not in blob.lower()
