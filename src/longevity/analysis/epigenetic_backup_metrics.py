"""ANALYSIS LAYER: epigenetic backup metrics + v6 criterion (Stage 9).

Pure functions over organism trajectories carrying an ``epigenetic_backup``
block: Shannon entropy slope after adulthood, Backup-Drive readability
(``Information_Wall_Proximity``), rollback/apoptosis accounting, and the
strict ``robust_bounded_degradation_v6`` verdict (v5 conditions PLUS
entropy discipline). Operational criterion only.
"""

from __future__ import annotations

import math

from typing import Any

from longevity.model.epigenetic_backup import (
    information_wall_proximity,
    information_wall_proximity_ru,
    validate_epigenetic_backup_params,
)

DEFAULT_V6_CRITERIA: dict[str, Any] = {
    "eps_entropy": 0.004,
    "eps_entropy_worst": 0.008,
    "max_wall_proximity": 0.8,
    "min_success_rate": 0.8,
}


def validate_v6_criteria(criteria: dict[str, Any] | None) -> dict[str, float]:
    """Validate the v6 criterion block (missing keys get defaults)."""
    merged = dict(DEFAULT_V6_CRITERIA)
    if criteria:
        if not isinstance(criteria, dict):
            raise ValueError(f"v6 criteria must be a dict, got {criteria!r}")
        unknown = set(criteria) - set(DEFAULT_V6_CRITERIA)
        if unknown:
            raise ValueError(f"unknown v6 criteria keys: {sorted(unknown)}")
        merged.update(criteria)
    validated: dict[str, float] = {}
    for key, value in merged.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not math.isfinite(float(value)):
            raise ValueError(f"v6 criteria.{key} must be finite, got {value!r}")
        if float(value) < 0.0 or (key == "min_success_rate" and float(value) > 1.0) \
                or (key == "max_wall_proximity" and float(value) > 1.0):
            raise ValueError(f"v6 criteria.{key} out of range, got {value!r}")
        validated[key] = float(value)
    return validated


def _least_squares_slope(times: list[float], values: list[float]) -> float:
    """Least-squares slope (pure, deterministic; 0.0 on degenerate input)."""
    n = len(times)
    if n < 2:
        return 0.0
    mean_t = sum(times) / n
    mean_v = sum(values) / n
    denom = sum((t - mean_t) ** 2 for t in times)
    if denom <= 0.0:
        return 0.0
    return sum((t - mean_t) * (v - mean_v) for t, v in zip(times, values)) / denom


def _adult_rows(trajectory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows at/after the adult reference age (pure)."""
    if not trajectory:
        return []
    setpoint = 25.0
    for row in trajectory:
        backup = row.get("epigenetic_backup") or {}
        if backup.get("reference_age") is not None:
            setpoint = float(backup["reference_age"])
            break
    return [row for row in trajectory if float(row.get("chronological_age", 0.0)) >= setpoint]


def summarize_backup_run(trajectory: list[dict[str, Any]], dt: float = 0.25,
                         backup_params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Full backup per-run summary for runner merge (pure)."""
    _ = dt
    params = validate_epigenetic_backup_params(dict(backup_params or {}))
    has_backup = bool(trajectory) and any(row.get("epigenetic_backup") is not None
                                          for row in trajectory[1:])
    if not has_backup:
        return {"epigenetic_backup": {"has_backup": False},
                "backup_binding": {"backup_binding_constraint": "no_backup"}}
    adult = _adult_rows(trajectory)
    times = [float(row["chronological_age"]) for row in adult]
    entropy_series = [max(0.0, float((row.get("epigenetic_backup") or {})
                                     .get("epigenetic_entropy", 0.0))) for row in adult]
    slope = _least_squares_slope(times, entropy_series)
    final = trajectory[-1].get("epigenetic_backup") or {}
    wall = information_wall_proximity(final, params)
    summary = {
        "has_backup": True,
        "epigenetic_entropy_slope": slope,
        "epigenetic_entropy_final": max(0.0, float(final.get("epigenetic_entropy", 0.0))),
        "wall_proximity_final": float(wall["proximity"]),
        "wall_readable_final": bool(wall["readable"]),
        "wall_proximity_ru": information_wall_proximity_ru(float(wall["proximity"]),
                                                           bool(wall["readable"])),
        "backup_read_fidelity_final": float(wall["backup_read_fidelity"]),
        "reference_captured": bool(final.get("reference_captured", False)),
        "reference_age": final.get("reference_age"),
        "rollback_events": int(final.get("rollback_events", 0)),
        "rollback_blocked": int(final.get("rollback_blocked", 0)),
        "apoptosis_events": int(final.get("apoptosis_events", 0)),
        "cumulative_restored": max(0.0, float(final.get("cumulative_restored", 0.0))),
        "genome_sanitized": bool(final.get("genome_sanitized", False)),
    }
    binding = "none"
    if slope > validate_v6_criteria(None)["eps_entropy"]:
        binding = "epigenetic_entropy_slope"
    elif not wall["readable"]:
        binding = "information_wall_unreadable"
    return {"epigenetic_backup": summary,
            "backup_binding": {"backup_binding_constraint": binding}}


def robust_bounded_degradation_v6(summaries: list[dict[str, Any]],
                                 criteria: dict[str, Any] | None = None) -> dict[str, Any]:
    """Strict Stage 9 v6 verdict across seeds (pure).

    v5 conditions (which already require the reversibility ledger) PLUS
    entropy discipline: per-run entropy slope within eps, Backup Drive
    still readable at the end, worst-case slope within the worst gate.
    Missing backup blocks count as failures, never passes. Operational
    criterion only.
    """
    criteria_v = validate_v6_criteria(criteria)
    if not summaries:
        raise ValueError("robust_bounded_degradation_v6 of empty summaries")
    from longevity.analysis.reversibility_metrics import robust_bounded_degradation_v5

    v5 = robust_bounded_degradation_v5(summaries)
    per_run = []
    for summary in summaries:
        backup = summary.get("epigenetic_backup", {})
        if not backup.get("has_backup", False):
            per_run.append(False)
            continue
        ok = (
            float(backup.get("epigenetic_entropy_slope", 9e9)) <= criteria_v["eps_entropy"]
            and float(backup.get("wall_proximity_final", 9e9)) <= criteria_v["max_wall_proximity"]
            and bool(backup.get("wall_readable_final", False))
        )
        per_run.append(bool(ok))
    success_rate = sum(per_run) / len(per_run)
    worst_entropy = max(float(s.get("epigenetic_backup", {}).get("epigenetic_entropy_slope", 9e9))
                        for s in summaries)
    worst_proximity = max(float(s.get("epigenetic_backup", {}).get("wall_proximity_final", 9e9))
                          for s in summaries)
    indicator = bool(
        success_rate >= criteria_v["min_success_rate"]
        and v5["robust_bounded_degradation_v5"]
        and all(per_run)
        and worst_entropy <= criteria_v["eps_entropy_worst"])
    return {
        "robust_bounded_degradation_v6": indicator,
        "success_rate_bounded_v6": success_rate,
        "worst_case_epigenetic_entropy_slope": worst_entropy,
        "worst_case_wall_proximity": worst_proximity,
        "robust_v5": v5["robust_bounded_degradation_v5"],
        "n_runs": len(summaries),
    }
