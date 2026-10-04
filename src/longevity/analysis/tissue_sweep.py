"""ANALYSIS LAYER: tissue replacement sweep analysis (Stage 3B).

Pure functions over recorded trajectories and per-seed metric rows. No
simulation runs here, no I/O, no global state. All functions are deterministic
and never mutate their inputs.

Concepts (operational, model-internal -- see docs/TISSUE_MODEL.md § Stage 3B):

- *Viability*: a tissue state is viable when every constraint in the
  ``thresholds`` block holds (functional/stem reserves as fractions of their
  initial pools, senescent fraction of living cells, risk/niche bounds).
- ``time_to_first_viability_failure``: first trajectory time at which the
  state is not viable; the full duration when viability never breaks.
- ``healthspan_tissue``: cumulative viable time (sum of viable steps x dt).
  Differs from the failure time only when viability is lost and later regained.
- ``survival_time``: lifespan proxy for this sweep, equal to the failure time.
- *Regime labels* (:func:`classify_regime`): baseline_like, sustainable,
  risky_but_functional, stem_depleting, collapsing, unstable_high_replacement.
- Aggregation statistics are DESCRIPTIVE spread over a tiny seed sample
  (n=3 in sweep v0), never statistical significance.
"""

from __future__ import annotations

import copy
import math

from typing import Any

REGIME_LABELS = (
    "baseline_like",
    "sustainable",
    "risky_but_functional",
    "stem_depleting",
    "collapsing",
    "unstable_high_replacement",
)

# Operational viability/boundary thresholds. These are ANALYSIS choices for
# mapping model output to regime labels, not biological truths and not model
# parameters: changing them re-labels the same trajectories without re-running
# anything. Documented in docs/TISSUE_MODEL.md (Stage 3B).
DEFAULT_THRESHOLDS: dict[str, float] = {
    "min_functional_fraction": 0.75,  # functional >= 75% of initial functional.
    "max_senescent_fraction": 0.10,  # senescent/living <= 10%.
    "min_stem_fraction": 0.50,  # stem >= 50% of initial stem.
    "max_cancer_risk": 0.15,  # instantaneous cancer index bound.
    "max_fibrosis_index": 0.30,  # terminal fibrosis bound.
    "min_ecm_quality": 0.70,  # terminal ECM bound.
    "min_vascular_quality": 0.70,  # terminal vascular bound.
    "max_immune_pressure": 0.40,  # terminal immune bound.
    "viability_failure_time_fraction": 0.50,  # ttf below 50% duration -> collapsing.
    "sustainable_end_time_fraction": 0.90,  # ttf at/above 90% duration -> sustainable candidate.
    "boundary_sustainable_rate_min": 2.0 / 3.0,  # boundary needs >= 2/3 sustainable seeds.
    "boundary_ttf_fraction_min": 0.80,  # ... and mean ttf >= 80% duration.
}

_THRESHOLD_KEYS = tuple(DEFAULT_THRESHOLDS)
_FRACTION_THRESHOLD_KEYS = tuple(k for k in _THRESHOLD_KEYS if k != "max_cancer_risk") + ("max_cancer_risk",)


def validate_thresholds(thresholds: dict[str, Any]) -> dict[str, float]:
    """Validate a thresholds block; every key is required and in [0, 1]."""
    if not isinstance(thresholds, dict):
        raise ValueError("thresholds must be a dict")
    missing = set(_THRESHOLD_KEYS) - set(thresholds)
    if missing:
        raise ValueError(f"thresholds missing keys: {sorted(missing)}")
    unknown = set(thresholds) - set(_THRESHOLD_KEYS)
    if unknown:
        raise ValueError(f"thresholds unknown keys: {sorted(unknown)}")
    validated: dict[str, float] = {}
    for key in _THRESHOLD_KEYS:
        value = thresholds[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"thresholds.{key} must be a number, got {value!r}")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"thresholds.{key} must be finite, got {value!r}")
        if not 0.0 <= result <= 1.0:
            raise ValueError(f"thresholds.{key} must be in [0, 1], got {value!r}")
        validated[key] = result
    return validated


def senescent_fraction(state: dict[str, Any]) -> float:
    """Senescent share of living (functional + damaged + senescent) cells."""
    living = float(state["functional_cells"]) + float(state["damaged_cells"]) + float(state["senescent_cells"])
    if living <= 0.0:
        return 0.0
    return float(state["senescent_cells"]) / living


def evaluate_state(
    state: dict[str, Any],
    initial: dict[str, Any],
    thresholds: dict[str, float],
) -> tuple[bool, list[str]]:
    """Check one tissue state against all viability constraints.

    Pure: reads only. Returns (viable, violations) where violations names the
    failed constraints, e.g. ``"functional_below_threshold"``.
    """
    violations: list[str] = []
    initial_functional = float(initial["functional_cells"])
    initial_stem = float(initial["stem_cells"])

    if initial_functional > 0.0 and float(state["functional_cells"]) < thresholds["min_functional_fraction"] * initial_functional:
        violations.append("functional_below_threshold")
    if senescent_fraction(state) > thresholds["max_senescent_fraction"]:
        violations.append("senescent_fraction_exceeded")
    if initial_stem > 0.0 and float(state["stem_cells"]) < thresholds["min_stem_fraction"] * initial_stem:
        violations.append("stem_depleted")
    if float(state["cancer_risk"]) > thresholds["max_cancer_risk"]:
        violations.append("cancer_risk_exceeded")
    if float(state["fibrosis_index"]) > thresholds["max_fibrosis_index"]:
        violations.append("fibrosis_exceeded")
    if float(state["ecm_quality"]) < thresholds["min_ecm_quality"]:
        violations.append("ecm_degraded")
    if float(state["vascular_quality"]) < thresholds["min_vascular_quality"]:
        violations.append("vascular_degraded")
    if float(state["immune_pressure"]) > thresholds["max_immune_pressure"]:
        violations.append("immune_pressure_exceeded")

    living = float(state["functional_cells"]) + float(state["damaged_cells"]) + float(state["senescent_cells"])
    if living <= 0.0:
        violations.append("tissue_empty")
    return (len(violations) == 0, violations)


def trajectory_viability(
    trajectory: list[dict[str, Any]],
    initial: dict[str, Any],
    thresholds: dict[str, float],
    duration_time: float,
) -> dict[str, Any]:
    """Viability over a full trajectory (t0 first).

    Returns per-step flags plus ``time_to_first_viability_failure`` (first
    non-viable row time, or ``duration_time`` when viability never breaks),
    ``healthspan_tissue`` (cumulative viable time) and the first violation.
    """
    if not trajectory:
        raise ValueError("trajectory must be non-empty")
    flags: list[bool] = []
    first_time: float | None = None
    first_violations: list[str] = []
    for row in trajectory:
        viable, violations = evaluate_state(row, initial, thresholds)
        flags.append(viable)
        if not viable and first_time is None:
            first_time = float(row["time"])
            first_violations = list(violations)
    dt = duration_time / (len(trajectory) - 1) if len(trajectory) > 1 else duration_time
    return {
        "viable_flags": flags,
        "time_to_first_viability_failure": duration_time if first_time is None else first_time,
        "healthspan_tissue": sum(1 for flag in flags[1:] if flag) * dt,
        "first_violations": first_violations,
    }


def compute_seed_metrics(
    trajectory: list[dict[str, Any]],
    dt: float,
    replacement_events: int,
    total_replaced_cells: float,
    thresholds: dict[str, float],
    duration_time: float,
) -> dict[str, Any]:
    """Extended per-seed metric row for one sweep run.

    Extends the Stage 3A summary (final pools, burden integrals, peak cancer
    risk, niche finals, local rejuvenation delta, replacement counters) with
    the Stage 3B sweep metrics: stem finals/minima, functional integral,
    viability timing, and senescent fractions. Pure: never mutates inputs.
    """
    from longevity.analysis.tissue_metrics import compute_tissue_summary  # local: analysis-layer reuse

    if not trajectory:
        raise ValueError("trajectory must be non-empty")
    initial = dict(trajectory[0])
    final = dict(trajectory[-1])
    base = compute_tissue_summary(trajectory, dt, replacement_events, total_replaced_cells)
    viability = trajectory_viability(trajectory, initial, thresholds, duration_time)

    functional = [float(row["functional_cells"]) for row in trajectory]
    initial_stem = float(initial["stem_cells"])
    stem_fractions = [float(row["stem_cells"]) / initial_stem if initial_stem > 0.0 else 1.0 for row in trajectory]
    living_final = float(final["functional_cells"]) + float(final["damaged_cells"]) + float(final["senescent_cells"])

    row = dict(base)
    row.update(
        {
            "initial_functional_cells": float(initial["functional_cells"]),
            "initial_stem_cells": initial_stem,
            "final_stem_cells": float(final["stem_cells"]),
            "final_cancer_risk": float(final["cancer_risk"]),
            "final_senescent_fraction": (float(final["senescent_cells"]) / living_final if living_final > 0.0 else 0.0),
            "min_stem_cells": min(float(row_["stem_cells"]) for row_ in trajectory),
            "min_stem_fraction": min(stem_fractions),
            "area_under_functional_curve": sum(functional) * dt,
            "time_to_first_viability_failure": viability["time_to_first_viability_failure"],
            "healthspan_tissue": viability["healthspan_tissue"],
            "survival_time": viability["time_to_first_viability_failure"],
        }
    )
    return row


def classify_regime(
    row: dict[str, Any],
    thresholds: dict[str, float],
    duration_time: float,
    policy_off: bool,
) -> dict[str, Any]:
    """Classify one per-seed row into a regime label (pure, non-mutating).

    Priority, first match wins (documented in docs/TISSUE_MODEL.md):

    1. ``baseline_like`` -- replacement effectively off (reference arm).
    2. ``collapsing`` -- early viability loss, terminal functional loss, or
       senescent burden out of control at the end.
    3. ``stem_depleting`` -- terminal stem reserve below threshold.
    4. ``unstable_high_replacement`` -- two or more risk/niche violations
       (cancer peak, fibrosis, immune, ECM, vascular) at/after the run.
    5. ``risky_but_functional`` -- exactly one risk/niche violation, or a
       transient mid-run viability loss with a clean terminal state.
    6. ``sustainable`` -- viable through the horizon, clean terminal state.

    Returns ``{"label": ..., "reasons": [...]}``.
    """
    snapshot = copy.deepcopy(row)
    if policy_off:
        reasons = ["policy_effectively_off"]
        if snapshot["time_to_first_viability_failure"] < duration_time:
            reasons.append("baseline_viability_breaks_early")
        return {"label": "baseline_like", "reasons": reasons}

    fail_time_limit = thresholds["viability_failure_time_fraction"] * duration_time
    sustainable_limit = thresholds["sustainable_end_time_fraction"] * duration_time
    ttf = float(snapshot["time_to_first_viability_failure"])
    initial_functional = float(snapshot["initial_functional_cells"])
    initial_stem = float(snapshot["initial_stem_cells"])

    func_ok = initial_functional <= 0.0 or float(snapshot["final_functional_cells"]) >= thresholds["min_functional_fraction"] * initial_functional
    senescent_ok = float(snapshot["final_senescent_fraction"]) <= thresholds["max_senescent_fraction"]
    stem_ok = initial_stem <= 0.0 or float(snapshot["final_stem_cells"]) >= thresholds["min_stem_fraction"] * initial_stem

    risk_violations: list[str] = []
    if float(snapshot["max_cancer_risk"]) > thresholds["max_cancer_risk"]:
        risk_violations.append("cancer_risk_exceeded")
    if float(snapshot["final_fibrosis_index"]) > thresholds["max_fibrosis_index"]:
        risk_violations.append("fibrosis_exceeded")
    if float(snapshot["final_immune_pressure"]) > thresholds["max_immune_pressure"]:
        risk_violations.append("immune_pressure_exceeded")
    if float(snapshot["final_ecm_quality"]) < thresholds["min_ecm_quality"]:
        risk_violations.append("ecm_degraded")
    if float(snapshot["final_vascular_quality"]) < thresholds["min_vascular_quality"]:
        risk_violations.append("vascular_degraded")

    if ttf < fail_time_limit:
        return {"label": "collapsing", "reasons": [f"early_viability_failure_at_t={ttf}"] + risk_violations}
    if not func_ok:
        return {"label": "collapsing", "reasons": ["final_functional_below_threshold"] + risk_violations}
    if not senescent_ok:
        return {"label": "collapsing", "reasons": ["terminal_senescent_burden_uncontrolled"] + risk_violations}
    if not stem_ok:
        return {"label": "stem_depleting", "reasons": ["terminal_stem_below_threshold"] + risk_violations}
    if len(risk_violations) >= 2:
        return {"label": "unstable_high_replacement", "reasons": list(risk_violations)}
    if len(risk_violations) == 1:
        return {"label": "risky_but_functional", "reasons": list(risk_violations)}
    if ttf < sustainable_limit:
        return {"label": "risky_but_functional", "reasons": ["transient_viability_loss_recovered"]}
    return {"label": "sustainable", "reasons": ["viable_through_horizon"]}


def _percentile(sorted_values: list[float], fraction: float) -> float:
    """Linear-interpolation percentile (numpy 'linear' method equivalent)."""
    if not sorted_values:
        raise ValueError("percentile of empty data")
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = fraction * (len(sorted_values) - 1)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return sorted_values[low]
    weight = rank - low
    return sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight


def aggregate_values(values: list[float]) -> dict[str, Any]:
    """Descriptive 8-statistic summary of a seed sample (pure).

    ``std`` is the POPULATION standard deviation (divides by n): with n=3 this
    is a descriptive spread, never an inference. ``count`` is the sample size.
    """
    if not values:
        raise ValueError("aggregate_values of empty data")
    ordered = sorted(float(v) for v in values)
    for v in ordered:
        if not math.isfinite(v):
            raise ValueError(f"cannot aggregate non-finite value {v!r}")
    n = len(ordered)
    mean = sum(ordered) / n
    variance = sum((v - mean) ** 2 for v in ordered) / n
    return {
        "mean": mean,
        "std": math.sqrt(variance),
        "min": ordered[0],
        "max": ordered[-1],
        "median": _percentile(ordered, 0.5),
        "p25": _percentile(ordered, 0.25),
        "p75": _percentile(ordered, 0.75),
        "count": n,
    }


AGGREGATED_METRIC_NAMES = (
    "survival_time",
    "healthspan_tissue",
    "time_to_first_viability_failure",
    "final_functional_cells",
    "final_senescent_cells",
    "final_damaged_cells",
    "final_dead_cells",
    "final_stem_cells",
    "final_cancer_risk",
    "area_under_senescent_curve",
    "area_under_damage_curve",
    "area_under_functional_curve",
    "max_cancer_risk",
    "final_fibrosis_index",
    "final_ecm_quality",
    "final_vascular_quality",
    "final_immune_pressure",
    "rejuvenation_delta",
    "rejuvenation_delta_vs_baseline",
    "senescence_reduction_vs_baseline",
    "stem_depletion_delta_vs_baseline",
    "replacement_events",
    "total_replaced_cells",
)


def aggregate_point(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-seed rows of one grid point (pure).

    Returns per-metric 8-statistic summaries plus regime counts,
    ``sustainable_rate`` (sustainable seeds / n), ``failure_rate``
    (collapsing seeds / n), and mean/median failure-time aliases.
    """
    if not rows:
        raise ValueError("aggregate_point of empty rows")
    metrics = {name: aggregate_values([row[name] for row in rows]) for name in AGGREGATED_METRIC_NAMES}
    counts = {label: 0 for label in REGIME_LABELS}
    for row in rows:
        label = row["regime_label"]
        if label not in counts:
            raise ValueError(f"unknown regime label {label!r}")
        counts[label] += 1
    n = len(rows)
    ttf = metrics["time_to_first_viability_failure"]
    return {
        "n_seeds": n,
        "metrics": metrics,
        "regime_counts": {
            "sustainable_count": counts["sustainable"],
            "risky_count": counts["risky_but_functional"],
            "depleting_count": counts["stem_depleting"],
            "collapsing_count": counts["collapsing"],
            "unstable_count": counts["unstable_high_replacement"],
            "baseline_like_count": counts["baseline_like"],
        },
        "sustainable_rate": counts["sustainable"] / n,
        "failure_rate": counts["collapsing"] / n,
        "mean_time_to_first_viability_failure": ttf["mean"],
        "median_time_to_first_viability_failure": ttf["median"],
    }


def compute_boundary(
    points: list[dict[str, Any]],
    duration_time: float,
    rate_min: float,
    ttf_fraction_min: float,
) -> dict[str, float | None]:
    """Stability boundary per frequency (pure).

    For each frequency, the maximum ``max_replacement_fraction`` whose point
    satisfies ``sustainable_rate >= rate_min`` AND
    ``mean_time_to_first_viability_failure >= ttf_fraction_min * duration``.
    ``None`` when no fraction qualifies at that frequency. Keys are strings
    (JSON-safe); input points carry numeric ``frequency`` /
    ``max_replacement_fraction`` plus the two aggregate fields.
    """
    by_frequency: dict[float, list[dict[str, Any]]] = {}
    for point in points:
        by_frequency.setdefault(float(point["frequency"]), []).append(point)
    boundary: dict[str, float | None] = {}
    for frequency in sorted(by_frequency):
        qualifying = [
            float(p["max_replacement_fraction"])
            for p in by_frequency[frequency]
            if float(p["sustainable_rate"]) >= rate_min
            and float(p["mean_time_to_first_viability_failure"]) >= ttf_fraction_min * duration_time
        ]
        key = str(int(frequency)) if float(frequency).is_integer() else str(frequency)
        boundary[key] = max(qualifying) if qualifying else None
    return boundary


def pareto_frontier(points: list[dict[str, Any]]) -> list[dict[str, float]]:
    """Non-dominated grid points for benefit-vs-costs (pure).

    Each point: ``{"frequency", "max_replacement_fraction", "benefit",
    "costs": [...]}`` with higher benefit better and lower costs better.
    A point is dominated when another point is at least as good on every axis
    and strictly better on one. Returns ``{"frequency",
    "max_replacement_fraction"}`` ids sorted for determinism.
    """
    frontier: list[dict[str, float]] = []
    for candidate in points:
        dominated = False
        for other in points:
            if other is candidate:
                continue
            if float(other["benefit"]) >= float(candidate["benefit"]) and all(
                o <= c for o, c in zip(other["costs"], candidate["costs"])
            ) and (
                float(other["benefit"]) > float(candidate["benefit"])
                or any(o < c for o, c in zip(other["costs"], candidate["costs"]))
            ):
                dominated = True
                break
        if not dominated:
            frontier.append(
                {
                    "frequency": float(candidate["frequency"]),
                    "max_replacement_fraction": float(candidate["max_replacement_fraction"]),
                }
            )
    frontier.sort(key=lambda p: (p["frequency"], p["max_replacement_fraction"]))
    return frontier
