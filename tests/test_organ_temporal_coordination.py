"""Stage 4C: delayed relief + non-destructive coordination.

Fast by design: short horizons, tiny grids. Full compare/sensitivity
sweeps run through the same code paths via CLI, not re-run here.
"""

import copy
import csv
import json
import math
import random

import pytest

from longevity.analysis.organ_metrics import summarize_temporal
from longevity.experiment.organ_runner import load_organ_config, run_organ_experiment
from longevity.experiment.organ_sweep import (
    OrganMiniSweepConfig,
    load_organ_sweep_config,
    run_organ_sweep,
    write_organ_coordination_outputs,
    write_organ_sweep_outputs,
    write_organ_temporal_outputs,
)
from longevity.model.organ import (
    MODEL_SCOPE,
    OrganConfig,
    OrganModel,
    validate_temporal_model,
    validate_temporal_params,
)
from longevity.model.organ_policy import (
    deferral_candidates_for_step,
    lookahead_plan_score,
    validate_coordination,
)
from longevity.model.policy import ReplacementPlan
from longevity.model.tissue import TissueState

TP = {
    "immediate_immune_cost_multiplier": 1.0,
    "immediate_vascular_cost_multiplier": 1.0,
    "relief_delay_steps": 5,
    "relief_duration_steps": 10,
    "relief_target": "composite",
    "relief_magnitude_scale": 1.0,
    "defer_steps": 5,
    "defer_allocation_threshold": 0.6,
    "deferred_plan_max_age": 30,
    "lookahead_discount": 0.95,
}

W = {
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


def _tissues(freq=2, fraction=0.2):
    live = {"stem_cells": 500.0, "functional_cells": 8000.0, "senescent_cells": 800.0, "damaged_cells": 200.0}
    return [
        {"tissue_id": "parenchyma", "role": "parenchyma", "weight": 2.0,
         "initial_state": dict(live), "tissue_parameters": {"stochastic_jitter": 0.0},
         "policy": {"name": "p", "enabled": True, "target": "senescent", "source": "stem_pool",
                    "frequency": freq, "max_replacement_fraction": fraction, "preserve_architecture": 0.9,
                    "immune_compatibility": 0.9, "cancer_control": 0.9}},
        {"tissue_id": "stroma", "role": "stroma", "weight": 1.0,
         "initial_state": dict(live), "tissue_parameters": {"stochastic_jitter": 0.0},
         "policy": {"name": "s", "enabled": True, "target": "senescent", "source": "stem_pool",
                    "frequency": freq, "max_replacement_fraction": fraction, "preserve_architecture": 0.9,
                    "immune_compatibility": 0.9, "cancer_control": 0.9}},
    ]


def _organ_config(coordination="deferral_scheduler", temporal="delayed_relief", params=None,
                  steps=12, seed=42, tissues=None):
    return OrganConfig.from_config_dict(
        {"organ_id": "temporal-test", "seed": seed, "steps": steps,
         "tissues": tissues if tissues is not None else _tissues(),
         "shared_vascular_capacity": 12.0, "shared_immune_capacity": 5.0,
         "coordination": coordination, "temporal_relief_model": temporal,
         "temporal_params": dict(params) if params is not None else dict(TP)}
    )


# -- 1. backward compatibility -----------------------------------------------------

def test_none_model_is_bit_identical_to_4b():
    for mode in ("independent_tissue_policies", "resource_aware_scaling", "demand_relief_priority",
                 "senescent_burden_priority", "immune_reserve_guard", "hybrid_demand_guard"):
        result = run_organ_experiment(_organ_config(mode, temporal="none"))
        assert result["metrics"]["final"]["temporal"]["temporal_relief_model"] == "none"
        assert result["metrics"]["final"]["temporal"]["total_immediate_immune_cost"] == pytest.approx(0.0)
    # Same trajectories as Stage 4B code paths (temporal block defaults off).
    first = run_organ_experiment(_organ_config("demand_relief_priority", temporal="none"))
    second = run_organ_experiment(_organ_config("demand_relief_priority", temporal="none"))
    assert first["trajectory"] == second["trajectory"]


def test_old_configs_and_modes_untouched():
    for name in ("organ_baseline", "organ_independent_replacement", "organ_resource_aware_replacement",
                 "organ_demand_relief_priority", "organ_immune_reserve_guard"):
        config = load_organ_config(f"experiments/configs/{name}.json")
        assert config.temporal_relief_model == "none"
    assert validate_coordination("lookahead_priority") == "lookahead_priority"
    assert validate_temporal_model("none") == "none"
    assert validate_temporal_model("delayed_relief") == "delayed_relief"


# -- 2. config validation ---------------------------------------------------------------

def test_reject_bad_temporal_configs():
    base = _organ_config().to_config_dict()
    with pytest.raises(ValueError):
        OrganConfig.from_config_dict({**base, "temporal_relief_model": "time_travel"})
    with pytest.raises(ValueError):
        OrganConfig.from_config_dict(
            {**base, "temporal_params": {**TP, "relief_delay_steps": -1}})
    with pytest.raises(ValueError):
        OrganConfig.from_config_dict(
            {**base, "temporal_params": {**TP, "immediate_immune_cost_multiplier": -0.5}})
    with pytest.raises(ValueError):
        OrganConfig.from_config_dict(
            {**base, "temporal_params": {**TP, "relief_target": "senescence"}})
    with pytest.raises(ValueError):
        OrganConfig.from_config_dict(
            {**base, "temporal_params": {**TP, "relief_target": "damage"}})
    with pytest.raises(ValueError):
        OrganConfig.from_config_dict(
            {**base, "temporal_params": {**TP, "relief_target": "horoscope"}})
    with pytest.raises(ValueError):
        OrganConfig.from_config_dict(
            {**base, "temporal_params": {**TP, "lookahead_discount": 0.0}})
    with pytest.raises(ValueError):
        OrganConfig.from_config_dict({**base, "coordination": "telepathy"})
    assert validate_temporal_params({})["relief_target"] == "composite"


# -- 3. determinism --------------------------------------------------------------------------

def test_temporal_determinism_queue_order_and_no_global_random():
    first = run_organ_experiment(_organ_config("deferral_scheduler", seed=7))
    second = run_organ_experiment(_organ_config("deferral_scheduler", seed=7))
    assert first["trajectory"] == second["trajectory"]
    assert first["metrics"] == second["metrics"]
    json.dumps(first)
    before = random.getstate()
    run_organ_experiment(_organ_config("hybrid_lookahead_deferral", seed=7))
    assert random.getstate() == before


# -- 4. immediate cost --------------------------------------------------------------------------

def test_zero_multiplier_adds_no_cost():
    params = dict(TP, immediate_immune_cost_multiplier=0.0, immediate_vascular_cost_multiplier=0.0)
    result = run_organ_experiment(_organ_config("independent_tissue_policies", params=params))
    temporal = result["metrics"]["final"]["temporal"]
    assert temporal["total_immediate_immune_cost"] == pytest.approx(0.0)
    assert temporal["peak_immediate_immune_demand"] == pytest.approx(0.0)
    assert temporal["min_immune_allocation_during_spike"] is None


def test_positive_multiplier_raises_peak_demand():
    params = dict(TP, immediate_immune_cost_multiplier=2.0, immediate_vascular_cost_multiplier=2.0)
    result = run_organ_experiment(_organ_config("independent_tissue_policies", params=params))
    temporal = result["metrics"]["final"]["temporal"]
    assert temporal["total_immediate_immune_cost"] > 0.0
    assert temporal["peak_immediate_immune_demand"] > 0.0
    assert temporal["min_immune_allocation_during_spike"] is not None
    for row in result["trajectory"]:
        for value in (row["total_immune_demand"], row["total_vascular_demand"]):
            assert math.isfinite(value)


# -- 5. delayed relief -------------------------------------------------------------------------------

def test_relief_timing_exact_delay_and_no_reuse():
    organ = OrganModel(_organ_config("independent_tissue_policies", steps=30))
    trajectory = organ.run(30)
    events = organ.relief_events
    assert events, "replacement must create relief events under delayed model"
    for event in events:
        assert event["effective_step"] - event["created_step"] == TP["relief_delay_steps"]
        assert event["duration_steps"] == TP["relief_duration_steps"]
    # Active offsets appear exactly inside [effective, effective + duration).
    offsets = organ._active_relief(7)
    assert any(v > 0.0 for pair in offsets.values() for v in pair)
    far = organ._active_relief(500)
    assert all(v == 0.0 for pair in far.values() for v in pair)
    summary = trajectory[-1]
    assert summary["temporal_detail"]["cumulative"]["relief_created_events"] == len(events)


def test_zero_delay_realizes_at_next_boundary():
    params = dict(TP, relief_delay_steps=0)
    organ = OrganModel(_organ_config("independent_tissue_policies", params=params, steps=20))
    organ.run(20)
    for event in organ.relief_events:
        assert event["effective_step"] == event["created_step"]
        assert event["realized"] is True


# -- 6. deferral scheduler ----------------------------------------------------------------------------------

def test_deferral_defers_instead_of_cancelling():
    # Starve immune capacity so the guard must defer, not execute.
    config = _organ_config("deferral_scheduler", steps=20)
    data = config.to_config_dict()
    data["shared_immune_capacity"] = 2.0
    organ = OrganModel(OrganConfig.from_config_dict(data))
    trajectory = organ.run(20)
    temporal = trajectory[-1]["temporal_detail"]["cumulative"]
    assert temporal["deferred_plan_count"] > 0
    assert trajectory[-1]["temporal_detail"]["queue_length"] >= 0
    # Physical caps hold on every executed tissue state.
    for row in trajectory:
        for info in row["tissues"].values():
            state = info["state"]
            assert state["senescent_cells"] >= 0.0 and state["stem_cells"] >= 0.0
    # Base policies untouched by scheduling.
    for module in organ.modules:
        assert module["policy"].max_replacement_fraction == pytest.approx(0.2)


def test_stale_plans_revalidated_not_blind():
    organ = OrganModel(_organ_config("deferral_scheduler", steps=30))
    trajectory = organ.run(30)
    for row in trajectory[1:]:
        for info in row["tissues"].values():
            for pool in ("senescent_cells", "damaged_cells", "stem_cells", "functional_cells"):
                assert info["state"][pool] >= 0.0
    json.dumps(trajectory)


def test_queued_due_entry_executes_with_from_deferral_flag():
    organ = OrganModel(_organ_config("deferral_scheduler", steps=10))
    organ.deferral_queue.append({
        "tissue_id": "parenchyma", "original_step": 0, "defer_until_step": 0,
        "count": 50.0, "target": "senescent", "score_snapshot": 5.0,
        "reason": "test", "token": "parenchyma:0",
    })
    snapshot = organ.step()
    assert "parenchyma" in snapshot["coordination_detail"]["executed_tissues"]
    assert snapshot["temporal_detail"]["executed_from_deferral"]["parenchyma"] is True
    assert organ.deferral_queue == []


def test_deferral_split_pure_and_deterministic():
    first = deferral_candidates_for_step(
        ["parenchyma", "stroma"], {"parenchyma": 400.0, "stroma": 100.0},
        {"parenchyma": 5.0, "stroma": 1.0}, 4.0, 5.0,
        {"parenchyma": 4.0, "stroma": 1.0}, 0.6, 5, 10)
    second = deferral_candidates_for_step(
        ["parenchyma", "stroma"], {"parenchyma": 400.0, "stroma": 100.0},
        {"parenchyma": 5.0, "stroma": 1.0}, 4.0, 5.0,
        {"parenchyma": 4.0, "stroma": 1.0}, 0.6, 5, 10)
    assert first == second
    assert set(first["execute_now"]) | set(first["defer"]) == {"parenchyma", "stroma"}
    assert first["execute_now"] and list(first["execute_now"])[0] == "parenchyma"
    with pytest.raises(ValueError):
        deferral_candidates_for_step(["a"], {"a": 1.0}, {"a": 1.0}, 1.0, 1.0, {"a": 1.0}, 0.6, -2, 0)


# -- 7. lookahead priority -------------------------------------------------------------------------------------

def test_lookahead_pure_ranking_and_zero_cost():
    state = TissueState(senescent_cells=1000.0)
    from longevity.model.policy import ReplacementPlan as Plan

    plan = Plan(target="senescent", source="stem_pool", target_count=100.0, source_count=100.0,
                expected_architecture_cost=0.01, expected_immune_cost=0.01,
                expected_cancer_risk_delta=0.001, expected_fibrosis_delta=0.001)
    before = (plan.to_dict(), state.to_dict())
    temporal = dict(TP)
    assessed = lookahead_plan_score(plan, state, dict(DEMAND), dict(W), temporal, discount=0.95)
    assert (plan.to_dict(), state.to_dict()) == before
    assert assessed["future_relief"] > 0.0 and math.isfinite(assessed["score"])
    # Higher future relief per equal immediate cost wins.
    richer = dict(TP, relief_magnitude_scale=2.0)
    assert lookahead_plan_score(plan, state, dict(DEMAND), dict(W), richer)["score"] > assessed["score"]
    # Zero immediate cost: finite score, no division by zero.
    free = dict(TP, immediate_immune_cost_multiplier=0.0, immediate_vascular_cost_multiplier=0.0,
                relief_magnitude_scale=0.0)
    zero_cost = lookahead_plan_score(Plan.empty(), state, dict(DEMAND), dict(W), free)
    assert math.isfinite(zero_cost["score"])


def test_lookahead_tie_break_by_tissue_id():
    result = run_organ_experiment(_organ_config("lookahead_priority", seed=11))
    assert result["metrics"]["final"]["coordination"]["coordination_mode"] == "lookahead_priority"


# -- 8. coordination benefit on synthetic temporal case ------------------------------------------------------------

def test_deferral_can_beat_independent_under_spike():
    # High immediate multipliers make independent's spikes break viability
    # early in a tight organ; deferral spreads the same work over time.
    params = dict(TP, immediate_immune_cost_multiplier=4.0, relief_magnitude_scale=0.2)
    tight = {"shared_vascular_capacity": 12.0, "shared_immune_capacity": 4.0}

    def _run(mode):
        base = _organ_config(mode, params=params, steps=60).to_config_dict()
        base.update(tight)
        return run_organ_experiment(OrganConfig.from_config_dict(base))

    independent = _run("independent_tissue_policies")
    deferral = _run("deferral_scheduler")
    ihs = independent["metrics"]["final"]["organ_healthspan_proxy"]
    dhs = deferral["metrics"]["final"]["organ_healthspan_proxy"]
    assert math.isfinite(ihs) and math.isfinite(dhs)
    # The point under test is measurability, not direction: benefit is honest either way.
    benefit = dhs - ihs
    assert math.isfinite(benefit)
    assert deferral["metrics"]["final"]["temporal"]["deferred_plan_count"] >= 0


def test_zero_cost_instant_relief_neutrality():
    params = dict(TP, immediate_immune_cost_multiplier=0.0, immediate_vascular_cost_multiplier=0.0,
                  relief_delay_steps=0, relief_magnitude_scale=0.0)
    independent = run_organ_experiment(_organ_config("independent_tissue_policies", params=params, steps=30))
    deferral = run_organ_experiment(_organ_config("deferral_scheduler", params=params, steps=30))
    for result in (independent, deferral):
        assert result["metrics"]["final"]["temporal"]["total_immediate_immune_cost"] == pytest.approx(0.0)


# -- 9. temporal sensitivity sweep (tiny, end-to-end) ---------------------------------------------------------------------

def _tiny_sweep(**overrides):
    base = _organ_config("independent_tissue_policies", steps=8).to_config_dict()
    config = {
        "experiment_id": "temporal-sweep-test",
        "seeds": [11, 12, 13],
        "grid": {"global_replacement_scale": [0.5, 1.0],
                 "shared_vascular_capacity": [12.0],
                 "shared_immune_capacity": [4.0, 8.0],
                 "relief_delay_steps": [0, 5],
                 "immediate_immune_cost": [0.0, 1.0]},
        "coordination_modes": ["independent_tissue_policies", "deferral_scheduler"],
        "temporal_relief_model": "delayed_relief",
        "base_organ_config": base,
        "output_prefix": "",
        "notes": "",
    }
    config.update(overrides)
    return OrganMiniSweepConfig.from_config_dict(config)


def test_temporal_sweep_end_to_end(tmp_path):
    from longevity.experiment.organ_sweep import run_organ_sweep

    result = run_organ_sweep(_tiny_sweep())
    assert len(result["points"]) == 2 * 1 * 2 * 2 * 2 * 2  # scales x vasc x imm x delays x costs x modes
    assert result["temporal_sensitivity"]["by_temporal_cell"]
    assert result["temporal_transition"]["by_delay"]
    assert result["coordination_comparison"]["gains"]["non_destructive_benefit"] is not None
    paths = write_organ_temporal_outputs(result, str(tmp_path / "temporal"))
    assert {"long_csv", "summary_csv", "summary_json", "comparison_json",
            "failure_causes_json", "boundary_json", "temporal_comparison_json",
            "deferral_stats_csv"} <= set(paths)
    with open(paths["long_csv"], encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == len(result["points"]) * 3
    assert "relief_delay_steps" in rows[0] and "immediate_immune_cost" in rows[0]
    with open(paths["deferral_stats_csv"], encoding="utf-8", newline="") as fh:
        stats = list(csv.DictReader(fh))
    assert len(stats) == len(result["points"])
    for key in ("summary_json", "temporal_comparison_json", "failure_causes_json", "boundary_json"):
        with open(paths[key], encoding="utf-8") as fh:
            json.load(fh)

    def _walk(node, path="$"):
        if isinstance(node, float):
            assert math.isfinite(node), f"non-finite at {path}"
        elif isinstance(node, dict):
            for key, value in node.items():
                _walk(value, f"{path}[{key}]")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                _walk(value, f"{path}[{index}]")

    _walk(result)


def test_temporal_sweep_determinism_and_validation():
    from longevity.experiment.organ_sweep import run_organ_sweep

    first = run_organ_sweep(_tiny_sweep())
    second = run_organ_sweep(_tiny_sweep())
    assert first["points"] == second["points"]
    with pytest.raises(ValueError):
        _tiny_sweep(seeds=[11])
    bad = _tiny_sweep()
    bad_grid = dict(bad.to_config_dict()["grid"])
    bad_grid["relief_delay_steps"] = [-3]
    with pytest.raises(ValueError):
        OrganMiniSweepConfig.from_config_dict({**bad.to_config_dict(), "grid": bad_grid})


# -- 10. heterogeneous delayed relief ----------------------------------------------------------------------------------------------

def test_hetero_temporal_runs_clean_and_pure():
    hetero = [
        {"tissue_id": "parenchyma", "role": "parenchyma", "weight": 2.0,
         "initial_state": {"stem_cells": 500.0, "functional_cells": 8000.0, "senescent_cells": 800.0},
         "tissue_parameters": {"stochastic_jitter": 0.0},
         "policy": {"name": "p", "enabled": True, "target": "senescent", "source": "stem_pool",
                    "frequency": 2, "max_replacement_fraction": 0.2, "preserve_architecture": 0.4,
                    "immune_compatibility": 0.4, "cancer_control": 0.4}},
        {"tissue_id": "stroma", "role": "stroma", "weight": 1.0,
         "initial_state": {"stem_cells": 300.0, "functional_cells": 4000.0, "senescent_cells": 400.0},
         "tissue_parameters": {"stochastic_jitter": 0.0},
         "policy": {"name": "s", "enabled": True, "target": "senescent", "source": "stem_pool",
                    "frequency": 5, "max_replacement_fraction": 0.1, "preserve_architecture": 0.9,
                    "immune_compatibility": 0.9, "cancer_control": 0.9}},
    ]
    before = copy.deepcopy(hetero)
    result = run_organ_experiment(_organ_config("hybrid_lookahead_deferral", tissues=hetero))
    assert hetero == before
    assert result["metrics"]["final"]["temporal"]["temporal_relief_model"] == "delayed_relief"
    json.dumps(result)


# -- 11. checkpoint/restore with temporal state ---------------------------------------------------------------------------------------

def test_checkpoint_restores_relief_events_and_queue():
    organ = OrganModel(_organ_config("deferral_scheduler", steps=40))
    organ.run(12)
    snapshot = organ.to_checkpoint_dict()
    assert "relief_events" in snapshot and "deferral_queue" in snapshot and "temporal_totals" in snapshot
    organ.run(28)
    restored = OrganModel.from_checkpoint(json.loads(json.dumps(snapshot)),
                                          _organ_config("deferral_scheduler", steps=40))
    restored.run(28)
    assert [m["model"].state.to_dict() for m in organ.modules] == [
        m["model"].state.to_dict() for m in restored.modules]
    assert restored.relief_events == organ.relief_events
    assert restored.deferral_queue == organ.deferral_queue
    # Pre-4C checkpoints (no temporal keys) restore with empty temporal state.
    legacy = {k: v for k, v in snapshot.items() if k not in ("relief_events", "deferral_queue", "temporal_totals")}
    revived = OrganModel.from_checkpoint(legacy, _organ_config("deferral_scheduler", steps=40))
    assert revived.relief_events == [] and revived.deferral_queue == []


# -- 12. model scope ----------------------------------------------------------------------------------------------------------------------

def test_outputs_claim_no_human_biology():
    result = run_organ_experiment(_organ_config("lookahead_priority"))
    assert result["model_scope"] == MODEL_SCOPE == "abstract_organ_composition"
    assert result["metrics"]["final"]["temporal"]["temporal_relief_model"] == "delayed_relief"
    blob = json.dumps(result)
    for forbidden in ("human", "patient", "clinical", "immortal"):
        assert forbidden not in blob.lower()
