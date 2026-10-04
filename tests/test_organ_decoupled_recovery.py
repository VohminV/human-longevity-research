"""Stage 4D: decoupled niche recovery + supply-demand coordination.

Fast by design: short horizons, tiny grids. Full compare/sensitivity
sweeps run through the same code paths via CLI, not re-run here.
"""

import copy
import csv
import json
import math
import random

import pytest

from longevity.analysis.organ_metrics import summarize_capacity, summarize_recovery
from longevity.experiment.organ_runner import load_organ_config, run_organ_experiment
from longevity.experiment.organ_sweep import (
    OrganMiniSweepConfig,
    load_organ_sweep_config,
    run_organ_sweep,
    write_organ_recovery_outputs,
    write_organ_sweep_outputs,
)
from longevity.model.organ import (
    MODEL_SCOPE,
    OrganConfig,
    OrganModel,
    validate_capacity_dynamics,
    validate_recovery_model,
)
from longevity.model.organ_policy import (
    RecoveryPlan,
    RecoveryPolicy,
    joint_action_score,
    plan_recovery_action,
    recovery_action_value,
    validate_coordination,
)
from longevity.model.tissue import TissueState

CAP = {
    "vascular_degradation_rate": 0.001,
    "vascular_senescent_rate": 0.00005,
    "immune_degradation_rate": 0.001,
    "immune_senescent_rate": 0.00005,
    "capacity_ceiling_multiplier": 2.0,
}

W = {
    "alpha": 1.0, "beta": 0.5, "gamma": 1.0, "delta": 1.0,
    "epsilon": 1.0, "w_vascular": 1.0, "supply_beta": 1.0, "eps": 1e-6,
    "score_cutoff": 0.0, "immune_guard_threshold": 0.6,
}


def _tissues(recovery=True, freq=5, magnitude=1.0):
    live = {"stem_cells": 500.0, "functional_cells": 8000.0,
            "senescent_cells": 800.0, "damaged_cells": 200.0}
    tissues = []
    for tid, role, tgt in (("parenchyma", "parenchyma", "immune_capacity"),
                           ("stroma", "stroma", "vascular_capacity")):
        tissues.append({
            "tissue_id": tid, "role": role, "weight": 2.0 if role == "parenchyma" else 1.0,
            "initial_state": dict(live), "tissue_parameters": {"stochastic_jitter": 0.0},
            "policy": {"name": "p", "enabled": True, "target": "senescent", "source": "stem_pool",
                       "frequency": 2, "max_replacement_fraction": 0.2, "preserve_architecture": 0.9,
                       "immune_compatibility": 0.9, "cancer_control": 0.9},
            "recovery": {"name": "r", "enabled": recovery, "target": tgt, "frequency": freq,
                         "magnitude": magnitude, "delay_steps": 2,
                         "immediate_immune_multiplier": 1.0, "immediate_vascular_multiplier": 1.0,
                         "priority_hint": 1.0},
        })
    return tissues


def _organ_config(coordination="independent_all", recovery_model="decoupled_niche_recovery",
                  steps=12, seed=42, tissues=None, capacity=None):
    return OrganConfig.from_config_dict(
        {"organ_id": "recovery-test", "seed": seed, "steps": steps,
         "tissues": tissues if tissues is not None else _tissues(),
         "shared_vascular_capacity": 12.0, "shared_immune_capacity": 5.0,
         "coordination": coordination, "recovery_model": recovery_model,
         "capacity_dynamics": dict(capacity) if capacity is not None else dict(CAP)}
    )


# -- 1. backward compatibility ------------------------------------------------------

def test_recovery_none_is_bit_identical_to_4c():
    for mode in ("independent_tissue_policies", "resource_aware_scaling", "demand_relief_priority",
                 "deferral_scheduler", "lookahead_priority"):
        result = run_organ_experiment(_organ_config(mode, recovery_model="none"))
        assert result["metrics"]["final"]["recovery"]["recovery_model"] in ("none", "unknown")
        assert result["metrics"]["final"]["recovery"]["total_recovery_executed"] == 0
        assert result["metrics"]["final"]["capacity"]["vascular_capacity_degradation_auc"] == pytest.approx(0.0)
    first = run_organ_experiment(_organ_config("independent_all", recovery_model="none"))
    second = run_organ_experiment(_organ_config("independent_all", recovery_model="none"))
    assert first["trajectory"] == second["trajectory"]


def test_old_configs_and_modes_untouched():
    for name in ("organ_baseline", "organ_independent_replacement", "organ_decoupled_recovery_independent",
                 "organ_delayed_relief_deferral"):
        config = load_organ_config(f"experiments/configs/{name}.json")
        assert config.to_config_dict()["model_scope"] == MODEL_SCOPE
    for mode in ("independent_all", "supply_demand_greedy", "lookahead_supply_demand", "deferral_supply_demand"):
        assert validate_coordination(mode) == mode
    assert validate_recovery_model("none") == "none"
    assert validate_capacity_dynamics({})["capacity_ceiling_multiplier"] == pytest.approx(2.0)


# -- 2. config validation ------------------------------------------------------------------

def test_reject_bad_recovery_configs():
    base = _organ_config().to_config_dict()
    with pytest.raises(ValueError):
        OrganConfig.from_config_dict({**base, "recovery_model": "fountain_of_youth"})
    with pytest.raises(ValueError):
        OrganConfig.from_config_dict({**base, "capacity_dynamics": {"vascular_degradation_rate": -0.1}})
    with pytest.raises(ValueError):
        OrganConfig.from_config_dict({**base, "capacity_dynamics": {"telepathy": 1.0}})
    bad_tissues = copy.deepcopy(base["tissues"])
    bad_tissues[0]["recovery"] = {"enabled": True, "target": "brain", "frequency": 5, "magnitude": 0.5}
    with pytest.raises(ValueError):
        OrganConfig.from_config_dict({**base, "tissues": bad_tissues})
    bad_tissues2 = copy.deepcopy(base["tissues"])
    bad_tissues2[0]["recovery"] = {"enabled": True, "target": "vascular_capacity", "frequency": 0, "magnitude": 0.5}
    with pytest.raises(ValueError):
        OrganConfig.from_config_dict({**base, "tissues": bad_tissues2})
    bad_tissues3 = copy.deepcopy(base["tissues"])
    bad_tissues3[0]["recovery"] = {"enabled": True, "target": "vascular_capacity", "frequency": 5, "magnitude": -2.0}
    with pytest.raises(ValueError):
        OrganConfig.from_config_dict({**base, "tissues": bad_tissues3})


def test_reject_bad_sweep_and_modes():
    with pytest.raises(ValueError):
        validate_coordination("telepathy")
    base = _organ_config().to_config_dict()
    with pytest.raises(ValueError):
        OrganMiniSweepConfig.from_config_dict({
            "experiment_id": "x", "seeds": [11], "grid": {"global_replacement_scale": [1.0],
            "shared_vascular_capacity": [12.0], "shared_immune_capacity": [5.0]},
            "coordination_modes": ["independent_all"], "base_organ_config": base})
    with pytest.raises(ValueError):
        OrganMiniSweepConfig.from_config_dict({
            "experiment_id": "x", "seeds": [11, 12], "grid": {"global_replacement_scale": [1.0],
            "shared_vascular_capacity": [12.0], "shared_immune_capacity": [5.0],
            "recovery_delay_steps": [-2]},
            "coordination_modes": ["independent_all"], "base_organ_config": base})
    with pytest.raises(ValueError):
        OrganMiniSweepConfig.from_config_dict({
            "experiment_id": "x", "seeds": [11, 12], "grid": {"global_replacement_scale": [1.0],
            "shared_vascular_capacity": [12.0], "shared_immune_capacity": [5.0],
            "recovery_magnitude": [-1.0]},
            "coordination_modes": ["independent_all"], "base_organ_config": base})


# -- 3. determinism --------------------------------------------------------------------------------

def test_supply_determinism_tie_break_and_no_global_random():
    first = run_organ_experiment(_organ_config("supply_demand_greedy", seed=7))
    second = run_organ_experiment(_organ_config("supply_demand_greedy", seed=7))
    assert first["trajectory"] == second["trajectory"]
    assert first["metrics"] == second["metrics"]
    json.dumps(first)
    before = random.getstate()
    run_organ_experiment(_organ_config("deferral_supply_demand", seed=7))
    assert random.getstate() == before


# -- 4. recovery plan purity -----------------------------------------------------------------------------

def test_recovery_planning_pure_and_serializable():
    policy = RecoveryPolicy.from_dict({"name": "r", "enabled": True, "target": "immune_capacity",
                                       "frequency": 5, "magnitude": 0.5, "delay_steps": 3})
    before = policy.to_dict()
    plan = plan_recovery_action(policy, "parenchyma", 10)
    assert policy.to_dict() == before
    assert plan.magnitude == pytest.approx(0.5)
    assert plan.immediate_immune_cost == pytest.approx(0.5)
    assert plan_recovery_action(policy, "parenchyma", 11).magnitude == pytest.approx(0.0)
    json.dumps(plan.to_dict())
    disabled = RecoveryPolicy.from_dict({"enabled": False})
    assert plan_recovery_action(disabled, "x", 10).magnitude == pytest.approx(0.0)


# -- 5. immediate recovery cost --------------------------------------------------------------------------------

def test_zero_multiplier_adds_no_recovery_cost():
    tissues = _tissues()
    for tissue in tissues:
        tissue["recovery"]["immediate_immune_multiplier"] = 0.0
        tissue["recovery"]["immediate_vascular_multiplier"] = 0.0
    result = run_organ_experiment(_organ_config("independent_all", tissues=tissues))
    recovery = result["metrics"]["final"]["recovery"]
    assert recovery["total_recovery_immediate_immune_cost"] == pytest.approx(0.0)
    assert recovery["total_recovery_immediate_vascular_cost"] == pytest.approx(0.0)
    assert recovery["total_recovery_executed"] > 0


def test_positive_multiplier_raises_peak_and_finite():
    result = run_organ_experiment(_organ_config("independent_all"))
    recovery = result["metrics"]["final"]["recovery"]
    assert recovery["total_recovery_immediate_immune_cost"] > 0.0
    for row in result["trajectory"]:
        for value in (row["total_immune_demand"], row["total_vascular_demand"],
                      row["current_vascular_capacity"], row["current_immune_capacity"]):
            assert math.isfinite(value)


# -- 6. delayed recovery effect -------------------------------------------------------------------------------------

def test_capacity_effect_exact_delay_and_no_reuse():
    config = _organ_config("independent_all", steps=30)
    expected_delay = config.tissues[0].recovery["delay_steps"]
    organ = OrganModel(config)
    organ.run(30)
    assert organ.capacity_events, "recovery must create capacity events"
    for event in organ.capacity_events:
        assert event["effective_step"] - event["created_step"] == expected_delay
    # Realized events applied exactly once (no double application).
    realized = [e for e in organ.capacity_events if e.get("applied")]
    assert realized
    totals = organ.recovery_totals
    assert totals["capacity_increase_realized"] <= totals["capacity_increase_created"] + 1e-9


def test_zero_delay_realizes_at_next_boundary():
    tissues = _tissues()
    for tissue in tissues:
        tissue["recovery"]["delay_steps"] = 0
    organ = OrganModel(_organ_config("independent_all", tissues=tissues, steps=20))
    organ.run(20)
    assert organ.capacity_events
    for event in organ.capacity_events:
        assert event["effective_step"] == event["created_step"]
    # Events created during the final step have no later boundary to mature on.
    matured = [e for e in organ.capacity_events if e["effective_step"] < 19]
    assert matured
    assert all(e["applied"] is True for e in matured)


def test_duplicate_pending_effects_merge():
    organ = OrganModel(_organ_config("independent_all", steps=6))
    organ._create_capacity_event("parenchyma", "immune_capacity", 0.4, 10, pre=0)
    organ._create_capacity_event("parenchyma", "immune_capacity", 0.3, 10, pre=0)
    matches = [e for e in organ.capacity_events if e["tissue_id"] == "parenchyma" and not e["applied"]]
    assert len(matches) == 1
    assert matches[0]["magnitude"] == pytest.approx(0.7)
    assert organ.recovery_totals["recovery_merged_effects"] == 1


# -- 7. dynamic capacity ---------------------------------------------------------------------------------------------------

def test_capacity_never_negative_degrades_and_recovers():
    organ = OrganModel(_organ_config("independent_all", steps=40))
    trajectory = organ.run(40)
    for row in trajectory:
        assert row["current_vascular_capacity"] >= 0.0
        assert row["current_immune_capacity"] >= 0.0
    # Ceiling is 2x initial (12.0 -> 24.0); degradation must pull below it.
    assert trajectory[-1]["current_vascular_capacity"] <= 24.0 + 1e-9
    # Allocation stays valid under zero demand.
    assert OrganModel._allocation_ratio(0.0, 10.0) == pytest.approx(1.0)
    assert OrganModel._allocation_ratio(5.0, 0.0) == pytest.approx(0.0)


# -- 8. deferral supply-demand -----------------------------------------------------------------------------------------------

def test_both_kinds_deferrable_and_revalidated():
    # Starve capacities so joint ranking must defer; pools must stay valid.
    config = _organ_config("deferral_supply_demand", steps=20)
    data = config.to_config_dict()
    data["shared_vascular_capacity"] = 2.0
    data["shared_immune_capacity"] = 2.0
    organ = OrganModel(OrganConfig.from_config_dict(data))
    trajectory = organ.run(20)
    for row in trajectory:
        for info in row["tissues"].values():
            for pool in ("senescent_cells", "stem_cells", "functional_cells"):
                assert info["state"][pool] >= 0.0
    summary = trajectory[-1]
    assert summary["temporal_detail"]["queue_length"] >= 0
    json.dumps(trajectory)


def test_stale_recovery_not_executed_blindly():
    # Static capacities isolate the headroom logic (no degradation noise).
    organ = OrganModel(_organ_config("deferral_supply_demand", steps=10, capacity={}))
    # Queue a recovery entry for a full-capacity organ: no headroom → re-defer, never applied.
    organ.current_immune_capacity = 24.0  # ceiling for 12.0 initial
    organ.deferral_queue.append({
        "kind": "recovery", "tissue_id": "parenchyma", "original_step": 0, "defer_until_step": 0,
        "count": 0.0, "magnitude": 0.5, "target": "immune_capacity", "delay_steps": 5,
        "imm_mult": 1.0, "vasc_mult": 1.0, "score_snapshot": 1.0, "reason": "test", "token": "parenchyma:rec:0",
    })
    before = organ.current_immune_capacity
    organ.step()
    assert organ.current_immune_capacity == pytest.approx(before)  # clamped headroom: nothing added
    assert organ.deferral_queue, "headroom-less recovery must wait, not vanish"


# -- 9. lookahead supply-demand ------------------------------------------------------------------------------------------------------

def test_joint_lookahead_ranking_and_tie_break():
    assert joint_action_score(2.0, 0.5, 0.5, dict(W))["score"] > joint_action_score(1.0, 0.5, 0.5, dict(W))["score"]
    assert joint_action_score(-1.0, 0.5, 0.5, dict(W))["score"] < 0.0
    assert math.isfinite(joint_action_score(1.0, 0.0, 0.0, dict(W))["score"])
    assert recovery_action_value(
        RecoveryPlan(token="t", tissue_id="p", target="vascular_capacity", magnitude=0.5,
                     immediate_immune_cost=0.5, immediate_vascular_cost=0.5, delay_steps=2,
                     expected_capacity_delta=0.5), dict(W)) == pytest.approx(0.5)
    result = run_organ_experiment(_organ_config("lookahead_supply_demand", seed=11))
    assert result["metrics"]["final"]["coordination"]["coordination_mode"] == "lookahead_supply_demand"


# -- 10. coordination benefit measurability -----------------------------------------------------------------------------------------------

def test_benefit_measurable_either_direction():
    def _run(mode):
        return run_organ_experiment(_organ_config(mode, steps=40))

    independent = _run("independent_all")["metrics"]["final"]
    greedy = _run("supply_demand_greedy")["metrics"]["final"]
    for summary in (independent, greedy):
        for key in ("organ_healthspan_proxy", "time_to_organ_viability_failure", "final_organ_function"):
            assert math.isfinite(summary[key])
    benefit = greedy["organ_healthspan_proxy"] - independent["organ_healthspan_proxy"]
    assert math.isfinite(benefit)


def test_zero_cost_neutrality():
    tissues = _tissues()
    for tissue in tissues:
        tissue["recovery"]["immediate_immune_multiplier"] = 0.0
        tissue["recovery"]["immediate_vascular_multiplier"] = 0.0
        tissue["recovery"]["magnitude"] = 0.0
    first = run_organ_experiment(_organ_config("supply_demand_greedy", tissues=tissues, steps=20))
    second = run_organ_experiment(_organ_config("supply_demand_greedy", tissues=tissues, steps=20))
    assert first["trajectory"] == second["trajectory"]


# -- 11. supply-demand sensitivity sweep (tiny, end-to-end) --------------------------------------------------------------------------------------

def _tiny_sweep(**overrides):
    base = _organ_config("independent_all", steps=8).to_config_dict()
    config = {
        "experiment_id": "supply-sweep-test",
        "seeds": [11, 12, 13],
        "grid": {"global_replacement_scale": [0.5, 1.0],
                 "shared_vascular_capacity": [12.0],
                 "shared_immune_capacity": [4.0, 8.0],
                 "recovery_delay_steps": [0, 5],
                 "recovery_magnitude": [0.5, 1.0]},
        "coordination_modes": ["independent_all", "supply_demand_greedy"],
        "recovery_model": "decoupled_niche_recovery",
        "base_organ_config": base,
        "output_prefix": "",
        "notes": "",
    }
    config.update(overrides)
    return OrganMiniSweepConfig.from_config_dict(config)


def test_supply_sweep_end_to_end(tmp_path):
    from longevity.experiment.organ_sweep import run_organ_sweep

    result = run_organ_sweep(_tiny_sweep())
    assert len(result["points"]) == 2 * 1 * 2 * 2 * 2 * 2  # scales x vasc x imm x rec-delays x rec-mags x modes
    assert result["supply_demand_comparison"]["by_mode"]
    assert result["capacity_transition"]["by_initial_capacity"]
    paths = write_organ_recovery_outputs(result, str(tmp_path / "supply"))
    assert {"long_csv", "summary_csv", "summary_json", "comparison_json",
            "failure_causes_json", "boundary_json", "temporal_comparison_json",
            "deferral_stats_csv", "recovery_stats_csv",
            "supply_demand_comparison_json"} <= set(paths)
    with open(paths["long_csv"], encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == len(result["points"]) * 3
    assert "recovery_delay_steps" in rows[0] and "recovery_magnitude" in rows[0]
    with open(paths["recovery_stats_csv"], encoding="utf-8", newline="") as fh:
        stats = list(csv.DictReader(fh))
    assert len(stats) == len(result["points"])
    for key in ("summary_json", "supply_demand_comparison_json", "failure_causes_json", "boundary_json"):
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


def test_supply_sweep_determinism():
    from longevity.experiment.organ_sweep import run_organ_sweep

    first = run_organ_sweep(_tiny_sweep())
    second = run_organ_sweep(_tiny_sweep())
    assert first["points"] == second["points"]
    assert first["supply_demand_comparison"] == second["supply_demand_comparison"]


def test_mini_writer_still_writes_stage4a_shape(tmp_path):
    from longevity.experiment.organ_sweep import run_organ_sweep

    result = run_organ_sweep(_tiny_sweep())
    paths = write_organ_sweep_outputs(result, str(tmp_path / "mini"))
    assert set(paths) == {"summary_json", "summary_csv"}


# -- 12. heterogeneous decoupled recovery ------------------------------------------------------------------------------------------------------------

def test_hetero_supply_runs_clean_and_pure():
    hetero = [
        {"tissue_id": "parenchyma", "role": "parenchyma", "weight": 2.0,
         "initial_state": {"stem_cells": 500.0, "functional_cells": 8000.0, "senescent_cells": 800.0},
         "tissue_parameters": {"stochastic_jitter": 0.0},
         "policy": {"name": "p", "enabled": True, "target": "senescent", "source": "stem_pool",
                    "frequency": 2, "max_replacement_fraction": 0.2, "preserve_architecture": 0.4,
                    "immune_compatibility": 0.4, "cancer_control": 0.4},
         "recovery": {"name": "r", "enabled": True, "target": "immune_capacity", "frequency": 5,
                      "magnitude": 0.5, "delay_steps": 2, "immediate_immune_multiplier": 1.0,
                      "immediate_vascular_multiplier": 1.0, "priority_hint": 1.0}},
        {"tissue_id": "stroma", "role": "stroma", "weight": 1.0,
         "initial_state": {"stem_cells": 300.0, "functional_cells": 4000.0, "senescent_cells": 400.0},
         "tissue_parameters": {"stochastic_jitter": 0.0},
         "policy": {"name": "s", "enabled": True, "target": "senescent", "source": "stem_pool",
                    "frequency": 5, "max_replacement_fraction": 0.1, "preserve_architecture": 0.9,
                    "immune_compatibility": 0.9, "cancer_control": 0.9},
         "recovery": {"name": "r", "enabled": True, "target": "vascular_capacity", "frequency": 5,
                      "magnitude": 0.5, "delay_steps": 2, "immediate_immune_multiplier": 1.0,
                      "immediate_vascular_multiplier": 1.0, "priority_hint": 1.0}},
    ]
    before = copy.deepcopy(hetero)
    result = run_organ_experiment(_organ_config("deferral_supply_demand", tissues=hetero))
    assert hetero == before
    assert result["metrics"]["final"]["recovery"]["recovery_model"] == "decoupled_niche_recovery"
    json.dumps(result)


# -- 13. checkpoint/restore with recovery state -----------------------------------------------------------------------------------------------------------------

def test_checkpoint_restores_capacities_events_and_queues():
    organ = OrganModel(_organ_config("independent_all", steps=40))
    organ.run(12)
    snapshot = organ.to_checkpoint_dict()
    assert {"capacity_events", "recovery_totals", "current_vascular_capacity",
            "current_immune_capacity"} <= set(snapshot)
    organ.run(28)
    restored = OrganModel.from_checkpoint(json.loads(json.dumps(snapshot)),
                                          _organ_config("independent_all", steps=40))
    restored.run(28)
    assert [m["model"].state.to_dict() for m in organ.modules] == [
        m["model"].state.to_dict() for m in restored.modules]
    assert restored.capacity_events == organ.capacity_events
    assert restored.deferral_queue == organ.deferral_queue
    assert restored.current_vascular_capacity == pytest.approx(organ.current_vascular_capacity)
    # Legacy checkpoint without 4D keys restores with static capacities.
    legacy = {k: v for k, v in snapshot.items()
              if k not in ("capacity_events", "recovery_totals", "current_vascular_capacity",
                           "current_immune_capacity")}
    revived = OrganModel.from_checkpoint(legacy, _organ_config("independent_all", steps=40))
    assert revived.capacity_events == []
    assert revived.current_vascular_capacity == pytest.approx(12.0)
    assert revived.current_immune_capacity == pytest.approx(5.0)


# -- 14. model scope ---------------------------------------------------------------------------------------------------------------------------------------------------

def test_outputs_claim_no_human_biology():
    result = run_organ_experiment(_organ_config("lookahead_supply_demand"))
    assert result["model_scope"] == MODEL_SCOPE == "abstract_organ_composition"
    assert result["config"]["recovery_model"] == "decoupled_niche_recovery"
    blob = json.dumps(result)
    for forbidden in ("human", "patient", "clinical", "immortal"):
        assert forbidden not in blob.lower()
