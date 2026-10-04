"""ANALYSIS LAYER: mechanistic aging driver metrics (Stage 5C).

Pure functions over recorded organism trajectories with driver state.
Dominant binding driver, reversal efficiency, cost attribution, and the
strict robust_bounded_degradation_v2 criterion. All descriptive and
model-internal; never biological claims.
"""

from __future__ import annotations

import copy
import math

from typing import Any

from longevity.model.aging import AGING_DRIVERS


def _finite(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number, got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{path} must be finite, got {value!r}")
    return result


def _slope(times: list[float], values: list[float]) -> float:
    n = len(times)
    if n < 2:
        return 0.0
    mean_t = sum(times) / n
    mean_v = sum(values) / n
    denom = sum((t - mean_t) ** 2 for t in times)
    if denom <= 0.0:
        return 0.0
    return sum((t - mean_t) * (v - mean_v) for t, v in zip(times, values)) / denom


def _driver_damages(row: dict[str, Any]) -> dict[str, float]:
    aging = row.get("aging") or {}
    drivers = aging.get("drivers", {})
    return {name: float(drivers.get(name, {}).get("damage", 0.0)) for name in AGING_DRIVERS}


def _adult_rows(trajectory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in trajectory[1:]
            if row["developmental_stage"] not in ("embryo", "fetal", "infancy", "childhood", "adolescence")]


def summarize_drivers(trajectory: list[dict[str, Any]],
                      contributions: dict[str, float] | None = None) -> dict[str, Any]:
    """Per-driver slopes, finals, dominant binding driver (pure, Stage 5C).

    Dominant = max contribution-weighted post-adulthood slope, tie-break by
    sorted driver name. Trajectories without driver state yield neutral
    zeros with ``has_drivers: False`` instead of an error.
    """
    if not trajectory:
        raise ValueError("summarize_drivers of empty trajectory")
    has_drivers = any((row.get("aging") or {}).get("drivers") for row in trajectory[1:])
    if not has_drivers:
        return {"has_drivers": False, "driver_slope_after_adulthood_by_driver": {},
                "driver_damage_final_by_driver": {}, "worst_driver_slope": 0.0,
                "worst_raw_driver_slope": 0.0, "dominant_binding_driver": "none",
                "binding_driver_sequence": [], "biological_age_component_contributions": {}}
    adult = _adult_rows(trajectory)
    times = [float(row["chronological_age"]) for row in adult]
    slopes = {}
    finals = {}
    for name in AGING_DRIVERS:
        series = [_driver_damages(row)[name] for row in adult]
        slopes[name] = _slope(times, series)
        finals[name] = series[-1] if series else 0.0
    contributions = contributions or {name: 1.0 for name in AGING_DRIVERS}
    weighted = {name: float(contributions.get(name, 1.0)) * slopes[name] for name in AGING_DRIVERS}
    positive = {name: value for name, value in weighted.items() if value > 0.0}
    dominant = sorted(positive, key=lambda n: (-positive[n], n))[0] if positive else "none"
    sequence = sorted(positive, key=lambda n: (-positive[n], n))
    final_row = trajectory[-1]
    aging = final_row.get("aging") or {}
    events = aging.get("age_reversal_events", [])
    reversal_by_driver: dict[str, float] = {}
    for event in events:
        reversal_by_driver[event["driver"]] = reversal_by_driver.get(event["driver"], 0.0) + abs(float(event["delta"]))
    return {
        "has_drivers": True,
        "driver_slope_after_adulthood_by_driver": {k: float(v) for k, v in slopes.items()},
        "driver_damage_final_by_driver": {k: float(v) for k, v in finals.items()},
        "worst_driver_slope": float(max(weighted.values())) if weighted else 0.0,
        "worst_raw_driver_slope": float(max(slopes.values())) if slopes else 0.0,
        "dominant_binding_driver": dominant,
        "binding_driver_sequence": sequence,
        "biological_age_component_contributions": {k: float(v) for k, v in contributions.items()},
        "age_reversal_events": len(events),
        "total_age_reversal_delta": float(sum(abs(float(e["delta"])) for e in events)),
        "reversal_applied_by_driver": {k: float(v) for k, v in reversal_by_driver.items()},
    }


DEFAULT_V2_CRITERIA: dict[str, Any] = {
    "eps_bio": 0.05,
    "eps_driver": 0.005,
    "eps_bio_worst": 0.1,
    "eps_driver_worst": 0.01,
    "min_success_rate": 0.8,
    "safety_margin": 0.05,
    "max_cancer_burden": 0.5,
    "max_inflammation": 0.5,
    "max_fibrosis": 0.5,
    "min_neural_continuity": 0.6,
}


def validate_v2_criteria(criteria: dict[str, Any] | None) -> dict[str, float]:
    """Validate robust v2 criteria (all finite, rates in range)."""
    merged = dict(DEFAULT_V2_CRITERIA)
    merged.update(criteria or {})
    unknown = set(merged) - set(DEFAULT_V2_CRITERIA)
    if unknown:
        raise ValueError(f"unknown v2 criteria keys: {sorted(unknown)}")
    validated = {}
    for key, value in merged.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"v2 criteria.{key} must be finite, got {value!r}")
        if float(value) < 0.0 or (key == "min_success_rate" and float(value) > 1.0):
            raise ValueError(f"v2 criteria.{key} out of range, got {value!r}")
        validated[key] = float(value)
    return validated


def robust_bounded_degradation_v2(summaries: list[dict[str, Any]],
                                 criteria: dict[str, Any] | None = None) -> dict[str, Any]:
    """Strict v2 verdict across seeds (pure, Stage 5C).

    Each summary must carry a ``drivers`` block (see :func:`summarize_drivers`
    via ``compute_organism_summary``); missing blocks count as failures, never
    as passes. Operational criterion only, not immortality proof.
    """
    criteria = validate_v2_criteria(criteria)
    if not summaries:
        raise ValueError("robust_bounded_degradation_v2 of empty summaries")
    per_run = []
    for summary in summaries:
        drivers = summary.get("drivers", {})
        if not drivers.get("has_drivers", False):
            per_run.append(False)
            continue
        per_run.append(bool(
            float(summary.get("biological_age_slope_after_adulthood", 9e9)) <= criteria["eps_bio"]
            and float(drivers.get("worst_driver_slope", 9e9)) <= criteria["eps_driver"]
            and _systems_hold(summary, criteria)
            and _burdens_hold(summary, criteria)
            and summary.get("terminal_decline_reached", False) is False
        ))
    success_rate = sum(per_run) / len(per_run)
    worst_bio = max(float(s.get("biological_age_slope_after_adulthood", 9e9)) for s in summaries)
    worst_driver = max(float(s.get("drivers", {}).get("worst_driver_slope", 9e9)) for s in summaries)
    return {
        "robust_bounded_degradation_v2": bool(
            success_rate >= criteria["min_success_rate"]
            and worst_bio <= criteria["eps_bio_worst"]
            and worst_driver <= criteria["eps_driver_worst"]),
        "success_rate_bounded_v2": success_rate,
        "worst_case_biological_age_slope": worst_bio,
        "worst_case_driver_slope": worst_driver,
        "n_runs": len(summaries),
    }


def _systems_hold(summary: dict[str, Any], criteria: dict[str, float]) -> bool:
    functions = summary.get("final_function_by_system", {})
    if not functions:
        return False
    return all(float(v) >= 0.25 + criteria["safety_margin"] for v in functions.values())


def _burdens_hold(summary: dict[str, Any], criteria: dict[str, float]) -> bool:
    trajectory_cancer = float(summary.get("cancer_auc", 9e9))
    lifespan = max(1.0, float(summary.get("lifespan", 1.0)))
    return (
        trajectory_cancer / lifespan <= criteria["max_cancer_burden"]
        and float(summary.get("inflammation_auc", 9e9)) / lifespan <= criteria["max_inflammation"]
        and float(summary.get("fibrosis_auc", 9e9)) / lifespan <= criteria["max_fibrosis"]
        and float(summary.get("neural_identity_preservation", 0.0)) >= criteria["min_neural_continuity"]
    )


def reversal_efficiency(trajectory: list[dict[str, Any]]) -> dict[str, Any]:
    """Reversal applied per driver vs firings targeting it (pure, Stage 5C)."""
    if not trajectory:
        raise ValueError("reversal_efficiency of empty trajectory")
    applied: dict[str, float] = {}
    for row in trajectory[1:]:
        aging = row.get("aging") or {}
        for event in aging.get("age_reversal_events", []):
            applied[event["driver"]] = applied.get(event["driver"], 0.0) + abs(float(event["delta"]))
    # intervention_history is cumulative: read firings once from the final row.
    firings: dict[str, int] = {}
    for record in trajectory[-1].get("intervention_history", []):
        for driver in record.get("target_drivers", []):
            firings[driver] = firings.get(driver, 0) + 1
    return {
        "reversal_applied_by_driver": {k: float(v) for k, v in applied.items()},
        "firings_by_driver": dict(firings),
        "reversal_efficiency_by_driver": {
            driver: (applied.get(driver, 0.0) / count if count else 0.0)
            for driver, count in firings.items()},
    }
