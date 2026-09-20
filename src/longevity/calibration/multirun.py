"""Multi-seed calibration runs over the existing engine.

Runs an experiment config over a list of seeds with milestone tracking on,
extracts the required analysis metrics, aggregates them into
mean/SD/distribution, and compares every key that has a reference target.

The reports produced contain model_version, data_version, the calibration
dataset version, effective parameters, seeds and error terms, so each report
is self-describing and reproducible.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from longevity.calibration.compare import ModelValue, compare_reference_targets, distribute
from longevity.calibration.reference import (
    ALL_REFERENCE_POINTS,
    CALIBRATION_DATASET_VERSION,
    parameter_status_table,
)
from longevity.experiment.config import ExperimentConfig
from longevity.experiment.runner import run_experiment

TIME_TO_TARGETS = (2, 4, 8)


def run_seed_calibration(config: ExperimentConfig, seed: int | None = None) -> dict[str, Any]:
    """Run one calibration seed with milestone tracking on, keep the raw result."""
    cfg = replace(config, seed=config.seed if seed is None else seed)
    return run_experiment(cfg, out_path=None, record_milestones=True)


def extract_calibration_metrics(result: dict[str, Any], cell_count_times: tuple[int, ...]) -> dict[str, float]:
    """Extract the required analysis metrics from one run's result.

    - time_to_2_cell / time_to_4_cell / time_to_8_cell: first milestone where
      the living count reached N (exact division-event times).
    - cell_count_at_<t>h: the series sample at exactly t (t must be a multiple
      of the config's sample_interval).
    """
    milestones = result["metrics"]["milestones"]
    if not milestones:
        raise ValueError("milestone tracking was disabled for this run")

    time_to: dict[str, float] = {}
    for target in TIME_TO_TARGETS:
        reached = next((m["sim_time"] for m in milestones if m["live_count"] >= target), None)
        time_to[f"time_to_{target}_cell"] = reached

    series = result["metrics"]["series"]
    counts: dict[str, float] = {}
    for t in cell_count_times:
        counts[f"cell_count_at_{t}h"] = _series_value_at(series, t)

    return {**time_to, **counts}


def _series_value_at(series: list[dict[str, Any]], t: float) -> float:
    for point in series:
        if point["sample_time"] == t:
            return point["cells_total"]
    raise ValueError(f"series has no sample at t={t}; sample_interval must divide {t}")


def run_multiseed_calibration(
    config: ExperimentConfig,
    seeds: tuple[int, ...],
    cell_count_times: tuple[int, ...] = (92, 116, 120, 144, 168),
) -> dict[str, Any]:
    """Run `config` over `seeds`, aggregate metrics and build the report.

    Returns a self-describing calibration report (JSON-serializable).
    """
    per_seed: dict[str, dict[str, float]] = {}
    for seed in seeds:
        result = run_seed_calibration(config, seed)
        per_seed[str(seed)] = extract_calibration_metrics(result, cell_count_times)

    keys = sorted({k for row in per_seed.values() for k in row})
    modelled_by_key: dict[str, ModelValue] = {}
    for key in keys:
        values = tuple(row[key] for row in per_seed.values() if key in row)
        if all(v is not None for v in values):
            modelled_by_key[key] = distribute(values)

    comparison_keys = sorted(set(modelled_by_key) & set(ALL_REFERENCE_POINTS), key=list(ALL_REFERENCE_POINTS).index)

    report: dict[str, Any] = {
        "experiment_id": config.experiment_id,
        "model_version": config.model_version,
        "data_version": config.data_version,
        "calibration_dataset": CALIBRATION_DATASET_VERSION,
        "parameters": config.effective_parameters(),
        "parameter_status": parameter_status_table(),
        "population": config.population,
        "duration_hours": config.duration,
        "sample_interval_hours": config.metrics_config.get("sample_interval"),
        "seeds": list(seeds),
        "n_seeds": len(seeds),
        "per_seed_metrics": per_seed,
        "modelled": {
            k: {
                "mean": round(v.mean, 4),
                "sd": round(v.sd, 4),
                "median": round(v.median, 4) if v.median is not None else None,
                "p05": round(v.p05, 4) if v.p05 is not None else None,
                "p95": round(v.p95, 4) if v.p95 is not None else None,
                "n_seeds": v.n_seeds,
                "values": v.values,
            }
            for k, v in modelled_by_key.items()
        },
        "comparisons": compare_reference_targets({k: modelled_by_key[k] for k in comparison_keys}),
    }
    return report