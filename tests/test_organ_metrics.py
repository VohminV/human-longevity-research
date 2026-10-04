"""Stage 4A: organ metrics -- summaries, comparisons, mini sweep. Fast."""

import copy
import csv
import json
import math

import pytest

from longevity.analysis.organ_metrics import (
    compare_organ_against_baseline,
    compute_organ_summary,
    coordination_benefit,
)
from longevity.experiment.organ_sweep import (
    OrganMiniSweepConfig,
    load_organ_sweep_config,
    run_organ_sweep,
    write_organ_sweep_outputs,
)
from longevity.model.organ import DEFAULT_ORGAN_THRESHOLDS


def _tissue_state(function=1.0, stem=500.0, senescent=100.0):
    return {
        "functional_cells": 8000.0 * function, "damaged_cells": 200.0, "senescent_cells": senescent,
        "stem_cells": stem, "dead_cells": 0.0, "ecm_quality": 0.9, "vascular_quality": 0.9,
        "immune_pressure": 0.1, "cancer_risk": 0.0, "fibrosis_index": 0.0,
    }


def _snapshot(time, organ_function=1.0, bottleneck="parenchyma", viable=True, vasc=1.0, imm=1.0):
    tissues = {
        "parenchyma": {"role": "parenchyma", "is_vital": True, "tissue_function": organ_function,
                       "replacement_events": 2, "total_replaced_cells": 100.0, "state": _tissue_state(organ_function)},
        "stroma": {"role": "stroma", "is_vital": True, "tissue_function": 1.0,
                   "replacement_events": 1, "total_replaced_cells": 50.0, "state": _tissue_state(1.0)},
    }
    return {
        "time": float(time), "organ_function": organ_function, "bottleneck_tissue": bottleneck,
        "min_normalized_tissue_function": organ_function, "organ_cancer_risk": 0.0, "organ_fibrosis_index": 0.0,
        "total_vascular_demand": 8.0, "total_immune_demand": 3.0,
        "vascular_allocation_ratio": vasc, "immune_allocation_ratio": imm,
        "vascular_shortfall": 0.0, "immune_shortfall": 0.0, "coordination_scale": 1.0,
        "tissue_roles": {"parenchyma": "parenchyma", "stroma": "stroma"}, "tissues": tissues,
        "organ_viable": viable, "violations": [],
    }


def _base_organ_dict(steps=10):
    return {
        "organ_id": "sweep-base",
        "seed": 11,
        "steps": steps,
        "tissues": [
            {"tissue_id": "parenchyma", "role": "parenchyma", "weight": 2.0,
             "initial_state": {}, "tissue_parameters": {"stochastic_jitter": 0.0},
             "policy": {"name": "p", "enabled": True, "target": "senescent", "source": "stem_pool",
                        "frequency": 5, "max_replacement_fraction": 0.1, "preserve_architecture": 0.9,
                        "immune_compatibility": 0.9, "cancer_control": 0.9}},
            {"tissue_id": "stroma", "role": "stroma", "weight": 1.0,
             "initial_state": {}, "tissue_parameters": {"stochastic_jitter": 0.0},
             "policy": {"name": "s", "enabled": True, "target": "senescent", "source": "stem_pool",
                        "frequency": 10, "max_replacement_fraction": 0.05, "preserve_architecture": 0.9,
                        "immune_compatibility": 0.9, "cancer_control": 0.9}},
        ],
    }


# -- organ summaries ------------------------------------------------------------

def test_organ_summary_healthy_run():
    trajectory = [_snapshot(0.0), _snapshot(5.0), _snapshot(10.0)]
    before = copy.deepcopy(trajectory)
    summary = compute_organ_summary(trajectory, 5.0, 10.0, dict(DEFAULT_ORGAN_THRESHOLDS))
    assert trajectory == before
    assert summary["final_organ_function"] == pytest.approx(1.0)
    assert summary["organ_healthspan_proxy"] == pytest.approx(10.0)
    assert summary["time_to_organ_viability_failure"] == pytest.approx(10.0)
    assert summary["primary_organ_failure_cause"] == "none"
    assert summary["bottleneck_tissue_final"] == "parenchyma"
    assert summary["resource_contention_index"] == pytest.approx(0.0)
    assert summary["tissues"]["parenchyma"]["replacement_events"] == 2
    json.dumps(summary)


def test_organ_summary_failure_and_bottleneck_votes():
    trajectory = [_snapshot(0.0), _snapshot(5.0, organ_function=0.9, bottleneck="stroma"),
                  _snapshot(10.0, organ_function=0.5, bottleneck="stroma", viable=False,
                             vasc=0.3, imm=0.4)]
    summary = compute_organ_summary(trajectory, 5.0, 10.0, dict(DEFAULT_ORGAN_THRESHOLDS))
    assert summary["time_to_organ_viability_failure"] == pytest.approx(10.0)
    assert summary["organ_healthspan_proxy"] == pytest.approx(5.0)
    assert summary["primary_organ_failure_cause"] == "multiple_simultaneous"
    assert summary["bottleneck_tissue_most_frequent"] == "stroma"
    assert summary["resource_contention_index"] > 0.0
    with pytest.raises(ValueError):
        compute_organ_summary([], 1.0, 10.0, dict(DEFAULT_ORGAN_THRESHOLDS))


def test_organ_comparisons_on_synthetic():
    base = {"final_organ_function": 1.0, "organ_healthspan_proxy": 80.0, "time_to_organ_viability_failure": 80.0}
    better = {"final_organ_function": 1.1, "organ_healthspan_proxy": 100.0, "time_to_organ_viability_failure": 95.0}
    comparison = compare_organ_against_baseline(better, base)
    assert comparison["organ_rejuvenation_delta_vs_baseline"] == pytest.approx(0.1)
    assert comparison["organ_healthspan_gain_vs_baseline"] == pytest.approx(20.0)
    benefit = coordination_benefit(better, base)
    assert benefit["coordination_benefit_healthspan"] == pytest.approx(20.0)
    assert benefit["coordination_benefit_ttf"] == pytest.approx(15.0)


# -- mini sweep --------------------------------------------------------------------

def _sweep_config(**overrides):
    base = {
        "experiment_id": "organ-sweep-test",
        "seeds": [11, 12],
        "grid_scales": [0.0, 1.0],
        "grid_vascular": [12.0],
        "grid_immune": [5.0],
        "coordination_modes": ["independent_tissue_policies", "resource_aware_scaling"],
        "base_organ_config": _base_organ_dict(steps=10),
        "output_prefix": "",
        "notes": "",
    }
    base.update(overrides)
    return OrganMiniSweepConfig(
        experiment_id=base["experiment_id"], seeds=tuple(base["seeds"]),
        grid_scales=tuple(base["grid_scales"]), grid_vascular=tuple(base["grid_vascular"]),
        grid_immune=tuple(base["grid_immune"]), coordination_modes=tuple(base["coordination_modes"]),
        base_organ_config=base["base_organ_config"], output_prefix=base["output_prefix"], notes=base["notes"],
    )


def test_mini_sweep_end_to_end(tmp_path):
    result = run_organ_sweep(_sweep_config())
    assert len(result["points"]) == 2 * 1 * 1 * 2  # scales x vasc x imm x modes
    assert len(result["coordination_benefit"]) == 2  # one per scale with both modes
    paths = write_organ_sweep_outputs(result, str(tmp_path / "mini"))
    assert set(paths) == {"summary_json", "summary_csv"}
    with open(paths["summary_json"], encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["points"] and payload["coordination_benefit"]
    with open(paths["summary_csv"], encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == len(result["points"])

    def _walk(node, path="$"):
        if isinstance(node, float):
            assert math.isfinite(node), f"non-finite at {path}"
        elif isinstance(node, dict):
            for key, value in node.items():
                _walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                _walk(value, f"{path}[{index}]")

    _walk(payload)
    assert result["model_version"] == "0.4.0"
    assert payload["config"]["coordination_modes"] == ["independent_tissue_policies", "resource_aware_scaling"]


def test_mini_sweep_determinism():
    first = run_organ_sweep(_sweep_config())
    second = run_organ_sweep(_sweep_config())
    assert first["points"] == second["points"]
    assert first["coordination_benefit"] == second["coordination_benefit"]


def test_mini_sweep_validation():
    with pytest.raises(ValueError):
        _sweep_config(seeds=[11])
    with pytest.raises(ValueError):
        _sweep_config(grid_scales=[1.5])
    with pytest.raises(ValueError):
        _sweep_config(grid_vascular=[-3.0])
    with pytest.raises(ValueError):
        _sweep_config(coordination_modes=["telepathy"])
    with pytest.raises(ValueError):
        _sweep_config(base_organ_config={})


def test_real_mini_sweep_config_loads():
    config = load_organ_sweep_config("experiments/configs/organ_mini_sweep.json")
    assert len(config.seeds) >= 2
    assert len(config.coordination_modes) == 2
