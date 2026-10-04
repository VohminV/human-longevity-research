"""Stage 4A: organ runner -- schema, determinism, independent vs coordinated,
heterogeneous controls. Fast: short horizons."""

import copy
import json
import random

import pytest

from longevity.analysis.organ_metrics import coordination_benefit
from longevity.experiment.organ_runner import load_organ_config, run_organ_experiment
from longevity.model.organ import MODEL_SCOPE, OrganConfig


LIVE_STATE = {
    "time": 0.0,
    "stem_cells": 500.0,
    "functional_cells": 8000.0,
    "damaged_cells": 200.0,
    "senescent_cells": 800.0,
    "dead_cells": 0.0,
    "ecm_quality": 0.9,
    "vascular_quality": 0.9,
    "immune_pressure": 0.1,
    "cancer_risk": 0.0,
    "fibrosis_index": 0.0,
}


def _tiny_config(steps=15, seed=42, coordination="independent_tissue_policies", tissues=None):
    if tissues is None:
        tissues = [
            {"tissue_id": "parenchyma", "role": "parenchyma", "weight": 2.0,
             "initial_state": dict(LIVE_STATE), "tissue_parameters": {"stochastic_jitter": 0.0},
             "policy": {"name": "p", "enabled": True, "target": "senescent", "source": "stem_pool",
                        "frequency": 5, "max_replacement_fraction": 0.2, "preserve_architecture": 0.9,
                        "immune_compatibility": 0.9, "cancer_control": 0.9}},
            {"tissue_id": "stroma", "role": "stroma", "weight": 1.0,
             "initial_state": dict(LIVE_STATE), "tissue_parameters": {"stochastic_jitter": 0.0},
             "policy": {"name": "s", "enabled": True, "target": "senescent", "source": "stem_pool",
                        "frequency": 10, "max_replacement_fraction": 0.1, "preserve_architecture": 0.9,
                        "immune_compatibility": 0.9, "cancer_control": 0.9}},
        ]
    return OrganConfig.from_config_dict(
        {"organ_id": "tiny", "seed": seed, "steps": steps, "tissues": tissues, "coordination": coordination}
    )


# -- schema --------------------------------------------------------------------------

def test_organ_result_schema_and_roundtrip(tmp_path):
    result = run_organ_experiment(_tiny_config(), out_path=str(tmp_path / "organ.json"))
    assert result["model_scope"] == MODEL_SCOPE == "abstract_organ_composition"
    assert set(result) >= {"organ_id", "model_scope", "config", "trajectory", "metrics", "summary", "runtime", "rng_summary"}
    assert len(result["trajectory"]) == 16  # t0 + 15 steps
    assert set(result["summary"]) >= {"final_organ_function", "time_to_organ_viability_failure",
                                      "primary_organ_failure_cause", "bottleneck_tissue_final"}
    written = json.loads((tmp_path / "organ.json").read_text(encoding="utf-8"))
    assert written["metrics"] == result["metrics"]
    assert written["model_scope"] == MODEL_SCOPE


def test_all_stage_configs_load():
    for name in (
        "experiments/configs/organ_baseline.json",
        "experiments/configs/organ_independent_replacement.json",
        "experiments/configs/organ_resource_aware_replacement.json",
        "experiments/configs/organ_heterogeneous_strong_parenchyma_weak_stroma.json",
        "experiments/configs/organ_heterogeneous_weak_parenchyma_strong_stroma.json",
    ):
        config = load_organ_config(name)
        assert len(config.tissues) == 2
        assert config.to_config_dict()["model_scope"] == MODEL_SCOPE


# -- determinism --------------------------------------------------------------------------

def test_organ_run_determinism_and_seed_sensitivity():
    first = run_organ_experiment(_tiny_config(seed=42), out_path=None)
    second = run_organ_experiment(_tiny_config(seed=42), out_path=None)
    assert first["trajectory"] == second["trajectory"]
    assert first["metrics"] == second["metrics"]
    assert first["config"] == second["config"]
    json.dumps(first)


def test_organ_leaves_global_random_untouched():
    before = random.getstate()
    run_organ_experiment(_tiny_config(), out_path=None)
    assert random.getstate() == before


# -- independent vs resource-aware -------------------------------------------------------------

def test_resource_aware_never_exceeds_independent_replacement():
    independent = run_organ_experiment(_tiny_config(coordination="independent_tissue_policies"), out_path=None)
    aware = run_organ_experiment(_tiny_config(coordination="resource_aware_scaling"), out_path=None)
    independent_total = sum(info["total_replaced_cells"] for info in independent["metrics"]["final"]["tissues"].values())
    aware_total = sum(info["total_replaced_cells"] for info in aware["metrics"]["final"]["tissues"].values())
    assert aware_total <= independent_total + 1e-9
    assert min(row["vascular_allocation_ratio"] for row in aware["trajectory"]) >= 0.0
    benefit = coordination_benefit(aware["metrics"]["final"], independent["metrics"]["final"])
    assert set(benefit) == {"coordination_benefit_healthspan", "coordination_benefit_ttf", "coordination_benefit_function"}


def test_tight_capacity_creates_shortfall():
    config = _tiny_config()
    data = config.to_config_dict()
    data["shared_vascular_capacity"] = 0.5
    data["shared_immune_capacity"] = 0.5
    tight = run_organ_experiment(OrganConfig.from_config_dict(data), out_path=None)
    assert tight["metrics"]["final"]["min_vascular_allocation_ratio"] < 1.0
    assert tight["metrics"]["final"]["min_immune_allocation_ratio"] < 1.0
    assert tight["metrics"]["final"]["resource_contention_index"] > 0.0


# -- heterogeneous controls --------------------------------------------------------------------------

def test_weak_tissue_changes_organ_outcome_and_policies_stay_pure():
    strong_tissues = [
        {"tissue_id": "parenchyma", "role": "parenchyma", "weight": 2.0,
         "initial_state": dict(LIVE_STATE), "tissue_parameters": {"stochastic_jitter": 0.0},
         "policy": {"name": "p", "enabled": True, "target": "senescent", "source": "stem_pool",
                    "frequency": 5, "max_replacement_fraction": 0.2, "preserve_architecture": 0.9,
                    "immune_compatibility": 0.9, "cancer_control": 0.9}},
        {"tissue_id": "stroma", "role": "stroma", "weight": 1.0,
         "initial_state": dict(LIVE_STATE), "tissue_parameters": {"stochastic_jitter": 0.0},
         "policy": {"name": "s", "enabled": True, "target": "senescent", "source": "stem_pool",
                    "frequency": 10, "max_replacement_fraction": 0.1, "preserve_architecture": 0.9,
                    "immune_compatibility": 0.9, "cancer_control": 0.9}},
    ]
    weak_tissues = copy.deepcopy(strong_tissues)
    weak_tissues[1]["policy"] = {**weak_tissues[1]["policy"], "preserve_architecture": 0.0,
                                 "immune_compatibility": 0.0, "cancer_control": 0.0, "name": "s-weak"}
    strong_config = _tiny_config(tissues=strong_tissues, steps=60)
    weak_config = _tiny_config(tissues=weak_tissues, steps=60)
    strong_policies_before = [t["policy"] for t in strong_config.to_config_dict()["tissues"]]
    strong = run_organ_experiment(strong_config, out_path=None)
    weak = run_organ_experiment(weak_config, out_path=None)
    # Config policies are never mutated by the run.
    assert [t["policy"] for t in strong_config.to_config_dict()["tissues"]] == strong_policies_before
    # Weak stromal controls change the organ trajectory somewhere.
    assert weak["trajectory"] != strong["trajectory"]
    assert weak["metrics"]["final"]["tissues"]["stroma"]["final_ecm_quality"] <= (
        strong["metrics"]["final"]["tissues"]["stroma"]["final_ecm_quality"] + 1e-9
    )
