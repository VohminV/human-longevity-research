"""Stage 3C: boundary closure + control sensitivity + failure causality.

Fast by design: tiny grids and short horizons. Full v1 sweeps
(12 x 5 x 3 seeds x 2 profiles x 200 steps) run through the same code paths
via CLI, not re-run here.
"""

import copy
import csv
import json
import math
import random

import pytest

from longevity.analysis.tissue_sweep import (
    DEFAULT_THRESHOLDS,
    FAILURE_CAUSE_ORDER,
    PRIMARY_FAILURE_CAUSES,
    REGIME_LABELS,
    build_regime_coverage,
    compare_control_profiles,
    compute_boundary_closure,
    failure_causality,
    summarize_failure_causes,
)
from longevity.experiment.tissue_sweep import (
    PER_SEED_COLUMNS,
    PER_SEED_COLUMNS_V1,
    TissueSweepConfig,
    config_hash,
    load_tissue_sweep_config,
    run_tissue_sweep,
    write_tissue_sweep_outputs,
)
from longevity.model.policy import ReplacementPolicy

DURATION = 20.0

TEMPLATE = {
    "name": "test-template",
    "enabled": True,
    "target": "senescent",
    "source": "stem_pool",
    "frequency": 5,
    "max_replacement_fraction": 0.02,
    "preserve_architecture": 0.9,
    "immune_compatibility": 0.9,
    "cancer_control": 0.9,
}

STRONG = {"preserve_architecture": 0.9, "immune_compatibility": 0.9, "cancer_control": 0.9}
WEAK = {"preserve_architecture": 0.4, "immune_compatibility": 0.4, "cancer_control": 0.4}


def _tiny_config(profiles=None, **overrides):
    base = {
        "experiment_id": "sweep-v1-test",
        "seeds": [11, 12, 13],
        "grid_fractions": [0.0, 0.5],
        "grid_frequencies": [5],
        "steps": 10,
        "dt": 1.0,
        "initial_state": {},
        "tissue_parameters": {"stochastic_jitter": 0.0},
        "policy_template": dict(TEMPLATE),
        "thresholds": dict(DEFAULT_THRESHOLDS),
        "metrics": ["healthspan_tissue", "regime_label"],
        "include_baseline": True,
        "output_prefix": "",
        "notes": "",
        "control_profiles": profiles,
    }
    if "fractions" in overrides:
        base["grid_fractions"] = overrides.pop("fractions")
    if "frequencies" in overrides:
        base["grid_frequencies"] = overrides.pop("frequencies")
    base.update(overrides)
    return TissueSweepConfig(
        experiment_id=base["experiment_id"],
        seeds=tuple(base["seeds"]),
        grid_fractions=tuple(base["grid_fractions"]),
        grid_frequencies=tuple(base["grid_frequencies"]),
        steps=base["steps"],
        dt=base["dt"],
        initial_state=base["initial_state"],
        tissue_parameters=base["tissue_parameters"],
        policy_template=base["policy_template"],
        thresholds=base["thresholds"],
        metrics=base["metrics"],
        include_baseline=base["include_baseline"],
        output_prefix=base["output_prefix"],
        notes=base["notes"],
        control_profiles=base["control_profiles"],
    )


def _state(time, stem=500.0, functional=8000.0, damaged=200.0, senescent=100.0,
           cancer=0.0, fibrosis=0.0, ecm=0.9, vascular=0.9, immune=0.1):
    return {
        "time": float(time),
        "stem_cells": stem,
        "functional_cells": functional,
        "damaged_cells": damaged,
        "senescent_cells": senescent,
        "dead_cells": 0.0,
        "ecm_quality": ecm,
        "vascular_quality": vascular,
        "immune_pressure": immune,
        "cancer_risk": cancer,
        "fibrosis_index": fibrosis,
    }


def _closure_point(frequency, fraction, profile, rate, mean_ttf):
    return {
        "frequency": frequency,
        "max_replacement_fraction": fraction,
        "control_profile": profile,
        "sustainable_rate": rate,
        "mean_time_to_first_viability_failure": mean_ttf,
        "regime_counts": {"sustainable_count": 3 if rate >= 2.0 / 3.0 else 0},
    }


# -- 1. backward compatibility ----------------------------------------------

def test_v0_config_has_no_profiles_and_legacy_shape():
    config = load_tissue_sweep_config("experiments/configs/tissue_sweep_v0.json")
    assert config.control_profiles is None
    result = run_tissue_sweep(_tiny_config(profiles=None))
    assert "control_profiles" not in result
    for point in result["points"]:
        assert "control_profile" not in point


def test_legacy_writer_returns_exactly_four_paths(tmp_path):
    result = run_tissue_sweep(_tiny_config(profiles=None))
    paths = write_tissue_sweep_outputs(result, str(tmp_path / "legacy"))
    assert set(paths) == {"long_csv", "summary_csv", "summary_json", "boundary_json"}


# -- 2. config validation ----------------------------------------------------

def test_v1_configs_load_and_validate():
    for path in (
        "experiments/configs/tissue_sweep_v1_boundary_closure.json",
        "experiments/configs/tissue_sweep_v1_weak_controls.json",
    ):
        config = load_tissue_sweep_config(path)
        assert config.control_profiles
        assert len(config.seeds) >= 3
        assert max(config.grid_fractions) > 0.2  # extended beyond the v0 edge


def test_reject_fraction_grids():
    with pytest.raises(ValueError):
        _tiny_config(fractions=[1.5])
    with pytest.raises(ValueError):
        _tiny_config(fractions=[-0.1])


def test_reject_bad_frequency():
    with pytest.raises(ValueError):
        _tiny_config(frequencies=[0])
    with pytest.raises(ValueError):
        _tiny_config(frequencies=[-3])


def test_reject_unknown_control_profile():
    with pytest.raises(ValueError):
        _tiny_config(profiles=["ultra_weak"])
    with pytest.raises(ValueError):
        _tiny_config(profiles={"mystery": {"preserve_architecture": 9.9}})


def test_reject_empty_control_profiles():
    with pytest.raises(ValueError):
        _tiny_config(profiles=[])
    with pytest.raises(ValueError):
        _tiny_config(profiles={})


def test_reject_bad_override_keys_and_ranges():
    with pytest.raises(ValueError):
        _tiny_config(profiles={"weak_controls": {"telepathy": 0.5}})
    with pytest.raises(ValueError):
        _tiny_config(profiles={"weak_controls": {"preserve_architecture": 1.5}})
    with pytest.raises(ValueError):
        _tiny_config(profiles={"weak_controls": {"cancer_control": -0.1}})


def test_cli_unknown_profile_rejected():
    config = _tiny_config(profiles={"strong_controls": dict(STRONG)})
    with pytest.raises(ValueError):
        run_tissue_sweep(config, control_profile="weak_controls")


# -- 3. control profile behavior ----------------------------------------------

def test_strong_profile_matches_legacy_behavior():
    legacy = run_tissue_sweep(_tiny_config(profiles=None))
    strong = run_tissue_sweep(_tiny_config(profiles={"strong_controls": dict(STRONG)}))
    assert len(legacy["points"]) == len(strong["points"])
    for legacy_point, strong_point in zip(legacy["points"], strong["points"]):
        assert strong_point["control_profile"] == "strong_controls"
        assert legacy_point["frequency"] == strong_point["frequency"]
        assert legacy_point["max_replacement_fraction"] == strong_point["max_replacement_fraction"]
        for seed in legacy["seeds"]:
            legacy_row = legacy_point["seeds"][str(seed)]
            strong_row = strong_point["seeds"][str(seed)]
            # Same dynamics: identical metrics ignoring the profile tag.
            for key, value in legacy_row.items():
                assert strong_row[key] == pytest.approx(value) if isinstance(value, float) else strong_row[key] == value


def test_weak_profile_changes_policy_and_stays_pure():
    from longevity.model.tissue import TissueModel
    from longevity.sim.rng import Rng

    template = dict(TEMPLATE)
    before = copy.deepcopy(template)
    weak_policy = ReplacementPolicy.from_dict({**template, **WEAK, "name": "weak"})
    assert weak_policy.preserve_architecture == pytest.approx(0.4)
    assert weak_policy.cancer_control == pytest.approx(0.4)
    assert template == before  # overrides never mutate the template
    model = TissueModel(rng=Rng(3))
    model.run(7, None)
    snapshot = model.state.to_dict()
    weak_policy.plan(model.state, model.parameters, model.step_count)
    assert model.state.to_dict() == snapshot


# -- 4. boundary closure -------------------------------------------------------

def test_closure_all_sustainable_open():
    points = [_closure_point(5, f, "strong_controls", 1.0, 20.0) for f in (0.05, 0.2, 0.5)]
    out = compute_boundary_closure(points, 20.0, 2.0 / 3.0, 0.8)
    entry = out["boundary_by_frequency"]["5"]["strong_controls"]
    assert entry["max_sustainable_fraction"] == pytest.approx(0.5)
    assert entry["first_unsustainable_fraction"] is None
    assert entry["boundary_open"] is True
    assert out["open_boundaries"] == [{"frequency": "5", "control_profile": "strong_controls"}]
    assert out["closed_boundaries"] == []


def test_closure_first_unsustainable_found():
    points = [
        _closure_point(1, 0.05, "strong_controls", 1.0, 20.0),
        _closure_point(1, 0.2, "strong_controls", 0.0, 5.0),
        _closure_point(1, 0.5, "strong_controls", 0.0, 4.0),
    ]
    out = compute_boundary_closure(points, 20.0, 2.0 / 3.0, 0.8)
    entry = out["boundary_by_frequency"]["1"]["strong_controls"]
    assert entry["max_sustainable_fraction"] == pytest.approx(0.05)
    assert entry["first_unsustainable_fraction"] == pytest.approx(0.2)
    assert entry["boundary_open"] is False


def test_closure_none_sustainable_null():
    points = [_closure_point(5, f, "weak_controls", 0.0, 5.0) for f in (0.05, 0.2)]
    out = compute_boundary_closure(points, 20.0, 2.0 / 3.0, 0.8)
    entry = out["boundary_by_frequency"]["5"]["weak_controls"]
    assert entry["max_sustainable_fraction"] is None
    assert entry["first_unsustainable_fraction"] == pytest.approx(0.05)
    assert entry["boundary_open"] is False


def test_closure_separate_per_profile_and_deterministic():
    points = [
        _closure_point(5, 0.1, "strong_controls", 1.0, 20.0),
        _closure_point(5, 0.5, "strong_controls", 1.0, 20.0),
        _closure_point(5, 0.1, "weak_controls", 1.0, 20.0),
        _closure_point(5, 0.5, "weak_controls", 0.0, 5.0),
    ]
    first = compute_boundary_closure(points, 20.0, 2.0 / 3.0, 0.8)
    second = compute_boundary_closure(list(reversed(points)), 20.0, 2.0 / 3.0, 0.8)
    assert first == second
    assert first["boundary_by_frequency"]["5"]["strong_controls"]["boundary_open"] is True
    assert first["boundary_by_frequency"]["5"]["weak_controls"]["boundary_open"] is False


# -- 5. regime coverage ----------------------------------------------------------

def _coverage_point(profile, frequency, fraction, label_by_seed):
    seeds = {str(seed): {"regime_label": label} for seed, label in label_by_seed.items()}
    return {
        "control_profile": profile,
        "frequency": frequency,
        "max_replacement_fraction": fraction,
        "aggregate": {"regime_counts": {}},
        "seeds": seeds,
    }


def test_coverage_all_labels_and_counts():
    points = [
        _coverage_point("strong_controls", 5, 0.05, {11: "sustainable", 12: "sustainable", 13: "risky_but_functional"}),
        _coverage_point("weak_controls", 1, 0.5, {11: "collapsing", 12: "stem_depleting", 13: "unstable_high_replacement"}),
        _coverage_point("weak_controls", 5, 0.0, {11: "baseline_like", 12: "baseline_like", 13: "baseline_like"}),
    ]
    coverage = build_regime_coverage(points)
    assert set(coverage["visited"]) == set(REGIME_LABELS)
    assert coverage["not_visited"] == []
    assert coverage["total_runs"] == 9
    assert coverage["labels"]["sustainable"]["run_count"] == 2
    assert coverage["labels"]["baseline_like"]["run_count"] == 3
    assert sum(entry["run_count"] for entry in coverage["labels"].values()) == 9


def test_coverage_marks_not_visited():
    points = [_coverage_point("strong_controls", 5, 0.05, {11: "sustainable", 12: "sustainable", 13: "sustainable"})]
    coverage = build_regime_coverage(points)
    assert "sustainable" in coverage["visited"]
    assert "collapsing" in coverage["not_visited"]
    assert coverage["not_visited_marker"] == "regime_not_visited_in_current_grid"


# -- 6. failure causality ----------------------------------------------------------

def test_causality_none_when_clean():
    initial = _state(0.0)
    trajectory = [_state(t) for t in (0.0, 1.0, 2.0)]
    before = copy.deepcopy(trajectory)
    out = failure_causality(trajectory, initial, dict(DEFAULT_THRESHOLDS))
    assert trajectory == before
    assert out["primary_failure_cause"] == "none"
    assert out["failure_cause_sequence"] == []
    assert all(out[f] is None for f in (
        "first_stem_depletion_time", "first_functional_collapse_time",
        "first_senescence_blowout_time", "first_cancer_threshold_time",
        "first_fibrosis_threshold_time", "first_ecm_collapse_time",
        "first_vascular_collapse_time", "first_immune_overload_time"))


def test_causality_order_and_simultaneous():
    initial = _state(0.0)
    # Stem breaks at t=5, functional at t=10: stem is primary.
    trajectory = [_state(0.0), _state(5.0, stem=100.0), _state(10.0, stem=100.0, functional=1000.0)]
    out = failure_causality(trajectory, initial, dict(DEFAULT_THRESHOLDS))
    assert out["primary_failure_cause"] == "stem_depletion"
    assert out["failure_cause_sequence"] == ["stem_depletion", "functional_collapse"]
    assert out["first_stem_depletion_time"] == pytest.approx(5.0)
    assert out["first_functional_collapse_time"] == pytest.approx(10.0)
    # Both at t=5: simultaneous, canonical order in the sequence.
    trajectory2 = [_state(0.0), _state(5.0, stem=100.0, functional=1000.0)]
    out2 = failure_causality(trajectory2, initial, dict(DEFAULT_THRESHOLDS))
    assert out2["primary_failure_cause"] == "multiple_simultaneous"
    assert out2["failure_cause_sequence"] == ["stem_depletion", "functional_collapse"]


def test_causality_vocabulary():
    assert set(PRIMARY_FAILURE_CAUSES) >= set(FAILURE_CAUSE_ORDER) | {"multiple_simultaneous", "none"}


def test_failure_summary_counts_and_means():
    rows = [
        {"primary_failure_cause": "stem_depletion", "failure_cause_sequence": ["stem_depletion"],
         "control_profile": "strong_controls", "max_replacement_fraction": 0.5,
         "first_stem_depletion_time": 10.0, "first_functional_collapse_time": None,
         "first_senescence_blowout_time": None, "first_cancer_threshold_time": None,
         "first_fibrosis_threshold_time": None, "first_ecm_collapse_time": None,
         "first_vascular_collapse_time": None, "first_immune_overload_time": None},
        {"primary_failure_cause": "none", "failure_cause_sequence": [],
         "control_profile": "strong_controls", "max_replacement_fraction": 0.05,
         "first_stem_depletion_time": None, "first_functional_collapse_time": None,
         "first_senescence_blowout_time": None, "first_cancer_threshold_time": None,
         "first_fibrosis_threshold_time": None, "first_ecm_collapse_time": None,
         "first_vascular_collapse_time": None, "first_immune_overload_time": None},
    ]
    summary = summarize_failure_causes(rows)
    assert summary["primary_cause_counts"]["stem_depletion"] == 1
    assert summary["primary_cause_counts"]["none"] == 1
    assert summary["mean_time_to_cause"]["stem_depletion"] == pytest.approx(10.0)
    assert summary["total_runs"] == 2
    with pytest.raises(ValueError):
        summarize_failure_causes([{**rows[0], "primary_failure_cause": "immortal"}])


# -- 7. control comparison -----------------------------------------------------------

def test_control_comparison_aggregates():
    def _point(profile, label_counts, health=20.0):
        total = sum(label_counts.values())
        metrics = {
            "healthspan_tissue": {"mean": health},
            "time_to_first_viability_failure": {"mean": health},
            "senescence_reduction_vs_baseline": {"mean": 100.0},
            "stem_depletion_delta_vs_baseline": {"mean": 50.0},
            "max_cancer_risk": {"mean": 0.05},
            "final_fibrosis_index": {"mean": 0.05},
        }
        return {"control_profile": profile, "aggregate": {
            "regime_counts": {
                "sustainable_count": label_counts.get("sustainable", 0),
                "risky_count": label_counts.get("risky_but_functional", 0),
                "depleting_count": label_counts.get("stem_depleting", 0),
                "collapsing_count": label_counts.get("collapsing", 0),
                "unstable_count": label_counts.get("unstable_high_replacement", 0),
                "baseline_like_count": label_counts.get("baseline_like", 0),
            },
            "n_seeds": total,
            "metrics": metrics,
        }}

    points = [
        _point("strong_controls", {"sustainable": 3}, health=20.0),
        _point("weak_controls", {"collapsing": 2, "sustainable": 1}, health=10.0),
    ]
    comparison = compare_control_profiles(points, seed_rows=[])
    assert set(comparison["profiles"]) == {"strong_controls", "weak_controls"}
    assert comparison["regime_mix"]["strong_controls"]["rates"]["sustainable"] == pytest.approx(1.0)
    assert comparison["healthspan"]["weak_controls"]["mean_healthspan_tissue"] == pytest.approx(10.0)
    for section in (comparison["healthspan"], comparison["senescence_vs_cost"]):
        for profile_values in section.values():
            for value in profile_values.values():
                if isinstance(value, float):
                    assert math.isfinite(value)


def test_control_comparison_single_profile_ok():
    points = [{
        "control_profile": "strong_controls",
        "aggregate": {
            "regime_counts": {"sustainable_count": 3, "risky_count": 0, "depleting_count": 0,
                              "collapsing_count": 0, "unstable_count": 0, "baseline_like_count": 0},
            "n_seeds": 3,
            "metrics": {name: {"mean": 1.0} for name in (
                "healthspan_tissue", "time_to_first_viability_failure",
                "senescence_reduction_vs_baseline", "stem_depletion_delta_vs_baseline",
                "max_cancer_risk", "final_fibrosis_index")},
        },
    }]
    comparison = compare_control_profiles(points)
    assert comparison["profiles"] == ["strong_controls"]


# -- 8. outputs -----------------------------------------------------------------------

def test_v1_outputs_schema_and_serialization(tmp_path):
    result = run_tissue_sweep(_tiny_config(
        profiles={"strong_controls": dict(STRONG), "weak_controls": dict(WEAK)}))
    out_prefix = str(tmp_path / "sweep_v1")
    paths = write_tissue_sweep_outputs(result, out_prefix)
    assert {"long_csv", "summary_csv", "summary_json", "boundary_json",
            "boundary_closure_json", "regime_coverage_json", "regime_coverage_csv",
            "failure_causes_json", "failure_causes_csv", "control_comparison_json"} <= set(paths)

    with open(paths["long_csv"], encoding="utf-8", newline="") as fh:
        long_rows = list(csv.DictReader(fh))
    assert set(PER_SEED_COLUMNS) <= set(long_rows[0].keys())
    assert set(PER_SEED_COLUMNS_V1) <= set(long_rows[0].keys())
    for row in long_rows:
        for key, value in row.items():
            if key in ("regime_label", "regime_reasons", "policy_enabled", "control_profile",
                        "primary_failure_cause", "failure_cause_sequence"):
                continue
            if value in ("", None):
                continue  # never-violated first_*_time cells are empty
            assert math.isfinite(float(value)), f"non-finite {key}={value}"

    with open(paths["summary_csv"], encoding="utf-8", newline="") as fh:
        summary_rows = list(csv.DictReader(fh))
    assert "control_profile" in summary_rows[0]
    assert len(summary_rows) == len(result["points"])

    for key in ("summary_json", "boundary_closure_json", "regime_coverage_json",
                "failure_causes_json", "control_comparison_json"):
        with open(paths[key], encoding="utf-8") as fh:
            json.load(fh)  # must parse; NaN/inf would have failed on write

    with open(paths["summary_json"], encoding="utf-8") as fh:
        summary = json.load(fh)
    assert summary["control_profiles"] == ["strong_controls", "weak_controls"]
    assert set(summary["boundary_closure"]) >= {"boundary_by_frequency", "open_boundaries", "closed_boundaries"}


# -- 9. determinism ----------------------------------------------------------------------

def test_v1_determinism_and_no_global_random():
    config = _tiny_config(profiles={"strong_controls": dict(STRONG), "weak_controls": dict(WEAK)})
    before = random.getstate()
    first = run_tissue_sweep(config)
    second = run_tissue_sweep(config)
    assert random.getstate() == before
    assert first["points"] == second["points"]
    assert first["boundary_closure"] == second["boundary_closure"]
    assert first["failure_causes"] == second["failure_causes"]
    assert first["control_comparison"] == second["control_comparison"]
    json.dumps(first)


# -- 10. small integration ------------------------------------------------------------------

def test_small_end_to_end_grid():
    config = _tiny_config(
        profiles={"strong_controls": dict(STRONG), "weak_controls": dict(WEAK)},
        fractions=[0.0, 0.2, 0.5],
        frequencies=[1, 5],
        steps=10,
    )
    result = run_tissue_sweep(config)
    assert len(result["points"]) == 2 * 3 * 2  # profiles x fractions x frequencies
    assert result["regime_coverage"]["total_runs"] == len(result["points"]) * len(result["seeds"])
    paths = write_tissue_sweep_outputs(result, "/tmp/pytest_v1_integration_sweep")
    assert paths["boundary_closure_json"].endswith("_boundary_closure.json")
