"""Stage 3B: tissue replacement sweep -- config, determinism, aggregation,
regime classification, boundary, and output artifacts.

Fast by design: tiny grids and short horizons. The full v0 sweep
(35 points x 3 seeds x 200 steps) is exercised only through the same code
paths, not re-run here.
"""

import copy
import csv
import json
import math
import random

import pytest

from longevity.analysis.tissue_sweep import (
    DEFAULT_THRESHOLDS,
    REGIME_LABELS,
    aggregate_point,
    aggregate_values,
    classify_regime,
    compute_boundary,
    evaluate_state,
    pareto_frontier,
    validate_thresholds,
)
from longevity.experiment.tissue_sweep import (
    PER_SEED_COLUMNS,
    TissueSweepConfig,
    config_hash,
    load_tissue_sweep_config,
    run_tissue_sweep,
    write_tissue_sweep_outputs,
)

DURATION = 200.0

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


def _tiny_config(**overrides) -> TissueSweepConfig:
    base = {
        "experiment_id": "sweep-test",
        "seeds": [11, 12, 13],
        "grid_fractions": [0.0, 0.05],
        "grid_frequencies": [5],
        "steps": 25,
        "dt": 1.0,
        "initial_state": {},
        "tissue_parameters": {"stochastic_jitter": 0.05},
        "policy_template": dict(TEMPLATE),
        "thresholds": dict(DEFAULT_THRESHOLDS),
        "metrics": ["healthspan_tissue", "regime_label"],
        "include_baseline": True,
        "output_prefix": "",
        "notes": "",
    }
    # Allow flat grid overrides for readability.
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
    )


def _clean_row(**overrides) -> dict:
    """A viable-through-horizon per-seed row (sustainable under defaults)."""
    row = {
        "initial_functional_cells": 8000.0,
        "initial_stem_cells": 500.0,
        "final_functional_cells": 7900.0,
        "final_senescent_cells": 200.0,
        "final_damaged_cells": 900.0,
        "final_dead_cells": 1000.0,
        "final_stem_cells": 400.0,
        "final_cancer_risk": 0.05,
        "final_senescent_fraction": 200.0 / 9000.0,
        "min_stem_cells": 380.0,
        "min_stem_fraction": 0.76,
        "area_under_senescent_curve": 40000.0,
        "area_under_damage_curve": 180000.0,
        "area_under_functional_curve": 1500000.0,
        "max_cancer_risk": 0.06,
        "final_fibrosis_index": 0.05,
        "final_ecm_quality": 0.85,
        "final_vascular_quality": 0.85,
        "final_immune_pressure": 0.15,
        "rejuvenation_delta": -100.0,
        "rejuvenation_delta_vs_baseline": 50.0,
        "senescence_reduction_vs_baseline": 300.0,
        "stem_depletion_delta_vs_baseline": 100.0,
        "replacement_events": 5,
        "total_replaced_cells": 500.0,
        "survival_time": DURATION,
        "healthspan_tissue": DURATION,
        "time_to_first_viability_failure": DURATION,
    }
    row.update(overrides)
    return row


# -- 1. determinism -------------------------------------------------------

def test_sweep_determinism_summary_and_boundary():
    first = run_tissue_sweep(_tiny_config())
    second = run_tissue_sweep(_tiny_config())
    assert first["points"] == second["points"]
    assert first["boundary"] == second["boundary"]
    assert first["config_hash"] == second["config_hash"] == config_hash(_tiny_config())
    json.dumps(first)  # result is JSON-serializable


def test_sweep_v0_config_loads_and_validates():
    config = load_tissue_sweep_config("experiments/configs/tissue_sweep_v0.json")
    assert len(config.seeds) >= 3
    assert config.steps >= 1
    assert config_hash(config) == config_hash(load_tissue_sweep_config("experiments/configs/tissue_sweep_v0.json"))


# -- 2. config validation -------------------------------------------------

def test_reject_negative_frequency():
    with pytest.raises(ValueError):
        _tiny_config(frequencies=[-5])


def test_reject_zero_frequency():
    with pytest.raises(ValueError):
        _tiny_config(frequencies=[0])


def test_reject_non_integer_frequency():
    with pytest.raises(ValueError):
        _tiny_config(frequencies=[2.5])


def test_reject_negative_fraction():
    with pytest.raises(ValueError):
        _tiny_config(fractions=[-0.1])


def test_reject_fraction_above_one():
    with pytest.raises(ValueError):
        _tiny_config(fractions=[1.5])


def test_reject_empty_grids():
    with pytest.raises(ValueError):
        _tiny_config(fractions=[])
    with pytest.raises(ValueError):
        _tiny_config(frequencies=[])


def test_reject_bad_seeds():
    with pytest.raises(ValueError):
        _tiny_config(seeds=[])
    with pytest.raises(ValueError):
        _tiny_config(seeds=[1, 2])
    with pytest.raises(ValueError):
        _tiny_config(seeds=[1, 1, 2])
    with pytest.raises(ValueError):
        _tiny_config(seeds=[1, 2, "3"])


def test_reject_unknown_target_or_source():
    bad_target = dict(TEMPLATE, target="brain")
    with pytest.raises(ValueError):
        _tiny_config(policy_template=bad_target)
    bad_source = dict(TEMPLATE, source="teleport")
    with pytest.raises(ValueError):
        _tiny_config(policy_template=bad_source)


def test_reject_disabled_template():
    with pytest.raises(ValueError):
        _tiny_config(policy_template=dict(TEMPLATE, enabled=False))


def test_reject_bad_thresholds():
    missing = dict(DEFAULT_THRESHOLDS)
    del missing["max_cancer_risk"]
    with pytest.raises(ValueError):
        _tiny_config(thresholds=missing)
    out_of_range = dict(DEFAULT_THRESHOLDS, min_functional_fraction=1.5)
    with pytest.raises(ValueError):
        _tiny_config(thresholds=out_of_range)
    unknown = dict(DEFAULT_THRESHOLDS, max_telepathy=0.1)
    with pytest.raises(ValueError):
        _tiny_config(thresholds=unknown)


def test_validate_thresholds_roundtrip():
    assert validate_thresholds(dict(DEFAULT_THRESHOLDS)) == dict(DEFAULT_THRESHOLDS)


# -- 3. aggregation --------------------------------------------------------

def test_aggregate_values_known_statistics():
    stats = aggregate_values([1.0, 2.0, 3.0, 4.0])
    assert stats["mean"] == pytest.approx(2.5)
    assert stats["std"] == pytest.approx(math.sqrt(1.25))
    assert stats["min"] == pytest.approx(1.0)
    assert stats["max"] == pytest.approx(4.0)
    assert stats["median"] == pytest.approx(2.5)
    assert stats["p25"] == pytest.approx(1.75)
    assert stats["p75"] == pytest.approx(3.25)
    assert stats["count"] == 4


def test_aggregate_values_single_seed():
    stats = aggregate_values([7.0])
    assert stats["mean"] == stats["median"] == stats["min"] == stats["max"] == pytest.approx(7.0)
    assert stats["std"] == pytest.approx(0.0)
    assert stats["count"] == 1


def test_aggregate_values_reject_empty_and_nonfinite():
    with pytest.raises(ValueError):
        aggregate_values([])
    with pytest.raises(ValueError):
        aggregate_values([1.0, float("nan")])


def test_aggregate_point_rates_and_counts():
    rows = []
    for label in ("sustainable", "sustainable", "collapsing"):
        row = _clean_row(time_to_first_viability_failure=DURATION if label == "sustainable" else 10.0)
        row["regime_label"] = label
        rows.append(row)
    aggregate = aggregate_point(rows)
    assert aggregate["n_seeds"] == 3
    assert aggregate["sustainable_rate"] == pytest.approx(2.0 / 3.0)
    assert aggregate["failure_rate"] == pytest.approx(1.0 / 3.0)
    counts = aggregate["regime_counts"]
    assert counts["sustainable_count"] == 2
    assert counts["collapsing_count"] == 1
    assert sum(counts.values()) == 3
    assert aggregate["mean_time_to_first_viability_failure"] == pytest.approx((200.0 + 200.0 + 10.0) / 3.0)
    assert aggregate["median_time_to_first_viability_failure"] == pytest.approx(200.0)


def test_aggregate_point_rejects_unknown_label():
    row = _clean_row()
    row["regime_label"] = "immortal"
    with pytest.raises(ValueError):
        aggregate_point([row])


# -- 4. regime classification ----------------------------------------------

def test_classify_baseline_like():
    row = _clean_row(time_to_first_viability_failure=50.0)
    before = copy.deepcopy(row)
    verdict = classify_regime(row, dict(DEFAULT_THRESHOLDS), DURATION, policy_off=True)
    assert verdict["label"] == "baseline_like"
    assert row == before  # classification never mutates its input


def test_classify_sustainable():
    verdict = classify_regime(_clean_row(), dict(DEFAULT_THRESHOLDS), DURATION, policy_off=False)
    assert verdict["label"] == "sustainable"


def test_classify_stem_depleting():
    row = _clean_row(final_stem_cells=100.0)  # 0.2 of initial 500 < 0.5 threshold
    verdict = classify_regime(row, dict(DEFAULT_THRESHOLDS), DURATION, policy_off=False)
    assert verdict["label"] == "stem_depleting"
    assert any("stem" in reason for reason in verdict["reasons"])


def test_classify_collapsing_early_failure():
    row = _clean_row(time_to_first_viability_failure=40.0)  # < 0.5 * duration
    verdict = classify_regime(row, dict(DEFAULT_THRESHOLDS), DURATION, policy_off=False)
    assert verdict["label"] == "collapsing"


def test_classify_collapsing_functional_loss():
    row = _clean_row(final_functional_cells=1000.0)  # < 0.75 * 8000
    verdict = classify_regime(row, dict(DEFAULT_THRESHOLDS), DURATION, policy_off=False)
    assert verdict["label"] == "collapsing"


def test_classify_risky_single_violation():
    row = _clean_row(final_immune_pressure=0.6)  # only violation (> 0.4)
    verdict = classify_regime(row, dict(DEFAULT_THRESHOLDS), DURATION, policy_off=False)
    assert verdict["label"] == "risky_but_functional"


def test_classify_transient_loss_recovered():
    row = _clean_row(time_to_first_viability_failure=150.0)  # in [0.5, 0.9) of duration
    verdict = classify_regime(row, dict(DEFAULT_THRESHOLDS), DURATION, policy_off=False)
    assert verdict["label"] == "risky_but_functional"


def test_classify_unstable_multiple_violations():
    row = _clean_row(max_cancer_risk=0.5, final_fibrosis_index=0.6)
    verdict = classify_regime(row, dict(DEFAULT_THRESHOLDS), DURATION, policy_off=False)
    assert verdict["label"] == "unstable_high_replacement"


def test_classify_all_labels_known():
    assert set(REGIME_LABELS) == {
        "baseline_like", "sustainable", "risky_but_functional",
        "stem_depleting", "collapsing", "unstable_high_replacement",
    }


def test_evaluate_state_pure_and_names_violations():
    state = {
        "functional_cells": 100.0, "damaged_cells": 0.0, "senescent_cells": 9000.0,
        "stem_cells": 0.0, "cancer_risk": 0.9, "fibrosis_index": 0.9,
        "ecm_quality": 0.0, "vascular_quality": 0.0, "immune_pressure": 1.0,
    }
    initial = {"functional_cells": 8000.0, "stem_cells": 500.0}
    before = copy.deepcopy(state)
    viable, violations = evaluate_state(state, initial, dict(DEFAULT_THRESHOLDS))
    assert viable is False
    assert state == before
    assert set(violations) >= {
        "functional_below_threshold", "senescent_fraction_exceeded", "stem_depleted",
        "cancer_risk_exceeded", "fibrosis_exceeded", "ecm_degraded",
        "vascular_degraded", "immune_pressure_exceeded",
    }


# -- 5. boundary ------------------------------------------------------------

def _boundary_point(frequency, fraction, rate, mean_ttf):
    return {
        "frequency": frequency,
        "max_replacement_fraction": fraction,
        "sustainable_rate": rate,
        "mean_time_to_first_viability_failure": mean_ttf,
    }


def test_boundary_all_sustainable_returns_max_fraction():
    points = [_boundary_point(5, f, 1.0, 200.0) for f in (0.01, 0.05, 0.1)]
    assert compute_boundary(points, 200.0, 2.0 / 3.0, 0.8) == {"5": 0.1}


def test_boundary_none_sustainable_returns_null():
    points = [_boundary_point(5, f, 0.0, 200.0) for f in (0.01, 0.05)]
    assert compute_boundary(points, 200.0, 2.0 / 3.0, 0.8) == {"5": None}


def test_boundary_ttf_gate_applies():
    points = [_boundary_point(5, 0.05, 1.0, 100.0)]  # rate ok, ttf 0.5 < 0.8 gate
    assert compute_boundary(points, 200.0, 2.0 / 3.0, 0.8) == {"5": None}


def test_boundary_grouped_by_frequency():
    points = [
        _boundary_point(5, 0.05, 1.0, 200.0),
        _boundary_point(5, 0.2, 0.0, 50.0),
        _boundary_point(25, 0.2, 1.0, 200.0),
    ]
    assert compute_boundary(points, 200.0, 2.0 / 3.0, 0.8) == {"5": 0.05, "25": 0.2}


def test_boundary_empty_points():
    assert compute_boundary([], 200.0, 2.0 / 3.0, 0.8) == {}


def test_pareto_frontier_dominance():
    points = [
        {"frequency": 1, "max_replacement_fraction": 0.01, "benefit": 10.0, "costs": [0.1, 0.1]},
        {"frequency": 1, "max_replacement_fraction": 0.05, "benefit": 20.0, "costs": [0.1, 0.1]},
        {"frequency": 1, "max_replacement_fraction": 0.2, "benefit": 15.0, "costs": [0.5, 0.5]},
    ]
    frontier = pareto_frontier(points)
    assert {"frequency": 1.0, "max_replacement_fraction": 0.05} in frontier
    assert {"frequency": 1.0, "max_replacement_fraction": 0.2} not in frontier


# -- 6. outputs --------------------------------------------------------------

def test_sweep_outputs_schema_and_roundtrip(tmp_path):
    result = run_tissue_sweep(_tiny_config())
    out_prefix = str(tmp_path / "sweep")
    paths = write_tissue_sweep_outputs(result, out_prefix)
    assert set(paths) == {"long_csv", "summary_csv", "summary_json", "boundary_json"}

    with open(paths["long_csv"], encoding="utf-8", newline="") as fh:
        long_rows = list(csv.DictReader(fh))
    assert set(PER_SEED_COLUMNS) <= set(long_rows[0].keys())
    n_baseline_rows = len(result["seeds"]) if result["baselines"] else 0
    assert len(long_rows) == len(result["points"]) * len(result["seeds"]) + n_baseline_rows
    if n_baseline_rows:
        assert long_rows[0]["regime_label"] == "baseline_like"
        assert long_rows[0]["policy_enabled"] == "False"
    for row in long_rows:
        for key, value in row.items():
            if key in ("regime_label", "regime_reasons", "policy_enabled"):
                continue
            assert math.isfinite(float(value)), f"non-finite {key}={value}"

    with open(paths["summary_csv"], encoding="utf-8", newline="") as fh:
        summary_rows = list(csv.DictReader(fh))
    assert len(summary_rows) == len(result["points"])
    header = summary_rows[0].keys()
    assert {"frequency", "max_replacement_fraction", "sustainable_rate", "failure_rate",
            "sustainable_count", "mean_healthspan_tissue"} <= set(header)

    with open(paths["summary_json"], encoding="utf-8") as fh:
        summary = json.load(fh)
    assert summary["config_hash"] == result["config_hash"]
    assert len(summary["points"]) == len(result["points"])
    # CSV/JSON round-trip on a key aggregate field.
    by_point = {(p["frequency"], p["max_replacement_fraction"]): p for p in summary["points"]}
    for csv_row in summary_rows:
        key = (int(csv_row["frequency"]), float(csv_row["max_replacement_fraction"]))
        assert float(csv_row["sustainable_rate"]) == pytest.approx(
            by_point[key]["aggregate"]["sustainable_rate"]
        )

    with open(paths["boundary_json"], encoding="utf-8") as fh:
        boundary = json.load(fh)
    assert boundary["config_hash"] == result["config_hash"]
    assert set(boundary["boundary_max_sustainable_fraction_by_frequency"]) == {
        str(q) for q in (5,)
    } | {str(q) for q in result["boundary"]}


# -- 7. Stage 3A integration ---------------------------------------------------

def test_sweep_leaves_global_random_untouched():
    before = random.getstate()
    run_tissue_sweep(_tiny_config())
    assert random.getstate() == before


def test_fraction_zero_matches_same_seed_baseline():
    result = run_tissue_sweep(_tiny_config())
    zero_point = next(p for p in result["points"] if p["max_replacement_fraction"] == 0.0)
    for seed in result["seeds"]:
        row = zero_point["seeds"][str(seed)]
        baseline = result["baselines"][str(seed)]
        assert row["final_functional_cells"] == pytest.approx(baseline["final_functional_cells"])
        assert row["regime_label"] == "baseline_like"
