"""ANALYSIS LAYER: organ-backed cross-scale metrics (Stage 6A).

Pure functions over recorded organism trajectories carrying an
``organ_backed`` block. Organ summaries, systemic-resource summaries,
cross-scale binding constraints, and the strict
``robust_bounded_degradation_v3`` criterion. All descriptive and
model-internal; never biological claims.
"""

from __future__ import annotations

import math

from typing import Any

from longevity.model.organ_backed import ORGAN_PROXIES, SYSTEMIC_RESOURCES

try:
    from longevity.model.aging import AGING_DRIVERS, DEFAULT_DRIVER_PARAMS
except ImportError:  # pragma: no cover - aging layer always present in practice
    AGING_DRIVERS = ()
    DEFAULT_DRIVER_PARAMS = {}


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


def _adult_rows(trajectory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in trajectory[1:]
            if row["developmental_stage"] not in ("embryo", "fetal", "infancy", "childhood", "adolescence")]


def _has_organ_backed(trajectory: list[dict[str, Any]]) -> bool:
    return any((row.get("organ_backed") or {}).get("proxies") for row in trajectory[1:])


def _proxy_series(trajectory: list[dict[str, Any]], pid: str, key: str,
                  adult_only: bool = True) -> list[float]:
    rows = _adult_rows(trajectory) if adult_only else trajectory[1:]
    return [float(row["organ_backed"]["proxies"][pid].get(key, 0.0)) for row in rows
            if row.get("organ_backed") and pid in row["organ_backed"].get("proxies", {})]


def summarize_organs(trajectory: list[dict[str, Any]],
                     proxy_params: dict[str, dict[str, float]] | None = None) -> dict[str, Any]:
    """Per-proxy function/damage slopes, finals, failures (pure, Stage 6A).

    Trajectories without an organ-backed block yield neutral zeros with
    ``has_organs: False`` instead of an error (backward compatibility).
    """
    if not trajectory:
        raise ValueError("summarize_organs of empty trajectory")
    if not _has_organ_backed(trajectory):
        return {"has_organs": False, "organ_function_slope_by_organ": {},
                "final_function_by_organ": {}, "worst_organ_function_slope": 0.0,
                "dominant_binding_organ": "none", "failed_organ_ids": [],
                "organ_failure_sequence": []}
    from longevity.model.organ_backed import validate_proxy_params  # deferred

    params = proxy_params or validate_proxy_params(None)
    adult = _adult_rows(trajectory)
    times = [float(row["chronological_age"]) for row in adult]
    slopes, finals, mins = {}, {}, {}
    first_failure: dict[str, float] = {}
    for pid in ORGAN_PROXIES:
        series = _proxy_series(trajectory, pid, "function")
        slopes[pid] = _slope(times, series) if series else 0.0
        finals[pid] = series[-1] if series else 0.0
        mins[pid] = min(series) if series else 0.0
        threshold = float(params[pid]["failure_threshold"])
        for row in adult:
            proxies = (row.get("organ_backed") or {}).get("proxies", {})
            if pid in proxies and float(proxies[pid].get("function", 1.0)) < threshold:
                first_failure[pid] = float(row["chronological_age"])
                break
    worst_pid = sorted(slopes, key=lambda p: (slopes[p], p))[0] if slopes else "none"
    damage_final = {pid: (_proxy_series(trajectory, pid, "damage") or [0.0])[-1]
                    for pid in ORGAN_PROXIES}
    senescence_final = {pid: (_proxy_series(trajectory, pid, "senescence_burden") or [0.0])[-1]
                        for pid in ORGAN_PROXIES}
    fibrosis_final = {pid: (_proxy_series(trajectory, pid, "fibrosis") or [0.0])[-1]
                      for pid in ORGAN_PROXIES}
    cancer_final = {pid: (_proxy_series(trajectory, pid, "cancer_risk") or [0.0])[-1]
                    for pid in ORGAN_PROXIES}
    ecm_final = {pid: (_proxy_series(trajectory, pid, "ecm_quality") or [0.0])[-1]
                 for pid in ORGAN_PROXIES}
    vascular_final = {pid: (_proxy_series(trajectory, pid, "vascular_quality") or [0.0])[-1]
                      for pid in ORGAN_PROXIES}
    immune_final = {pid: (_proxy_series(trajectory, pid, "immune_pressure") or [0.0])[-1]
                    for pid in ORGAN_PROXIES}
    reserve_final = {pid: (_proxy_series(trajectory, pid, "reserve") or [0.0])[-1]
                     for pid in ORGAN_PROXIES}
    repair_final = {pid: (_proxy_series(trajectory, pid, "repair_capacity") or [0.0])[-1]
                    for pid in ORGAN_PROXIES}
    failed = sorted(first_failure, key=lambda p: (first_failure[p], p))
    brain_series = _proxy_series(trajectory, "brain_cns_proxy", "informational_continuity")
    return {
        "has_organs": True,
        "organ_function_slope_by_organ": {k: float(v) for k, v in slopes.items()},
        "final_function_by_organ": {k: float(v) for k, v in finals.items()},
        "min_function_by_organ": {k: float(v) for k, v in mins.items()},
        "worst_organ_function_slope": float(slopes[worst_pid]) if slopes else 0.0,
        "dominant_binding_organ": worst_pid,
        "failed_organ_ids": failed,
        "organ_failure_sequence": failed,
        "time_to_organ_failure_by_organ": {pid: first_failure.get(pid) for pid in ORGAN_PROXIES},
        "organ_damage_final_by_organ": {k: float(v) for k, v in damage_final.items()},
        "organ_senescence_final_by_organ": {k: float(v) for k, v in senescence_final.items()},
        "organ_fibrosis_final_by_organ": {k: float(v) for k, v in fibrosis_final.items()},
        "organ_cancer_risk_final_by_organ": {k: float(v) for k, v in cancer_final.items()},
        "organ_ecm_final_by_organ": {k: float(v) for k, v in ecm_final.items()},
        "organ_vascular_final_by_organ": {k: float(v) for k, v in vascular_final.items()},
        "organ_immune_final_by_organ": {k: float(v) for k, v in immune_final.items()},
        "organ_reserve_final_by_organ": {k: float(v) for k, v in reserve_final.items()},
        "organ_repair_capacity_final_by_organ": {k: float(v) for k, v in repair_final.items()},
        "informational_continuity_min": float(min(brain_series)) if brain_series else 1.0,
        "informational_continuity_final": float(brain_series[-1]) if brain_series else 1.0,
    }


def summarize_resources(trajectory: list[dict[str, Any]], dt: float) -> dict[str, Any]:
    """Systemic resource allocation/shortfall summary (pure, Stage 6A)."""
    if not trajectory:
        raise ValueError("summarize_resources of empty trajectory")
    _finite(dt, "dt")
    if not _has_organ_backed(trajectory):
        return {"has_resources": False, "mean_allocation_by_resource": {},
                "min_allocation_by_resource": {}, "shortfall_auc_by_resource": {},
                "worst_resource_slope": 0.0, "dominant_binding_resource": "none",
                "exhaustion_time_by_resource": {}}
    adult = _adult_rows(trajectory)
    times = [float(row["chronological_age"]) for row in adult]
    mean_alloc, min_alloc, auc, slopes, exhausted = {}, {}, {}, {}, {}
    for resource in SYSTEMIC_RESOURCES:
        series = [float((row.get("organ_backed") or {}).get("resources", {})
                        .get("allocation", {}).get(resource, 1.0)) for row in adult]
        shorts = [float((row.get("organ_backed") or {}).get("resources", {})
                         .get("shortfall", {}).get(resource, 0.0)) for row in adult]
        mean_alloc[resource] = sum(series) / len(series) if series else 1.0
        min_alloc[resource] = min(series) if series else 1.0
        auc[resource] = sum(shorts) * dt
        slopes[resource] = _slope(times, series) if series else 0.0
        exhausted[resource] = next((float(row["chronological_age"]) for row in adult
                                    if float((row.get("organ_backed") or {})
                                             .get("resources", {}).get("allocation", {})
                                             .get(resource, 1.0)) < 0.2), None)
    worst_resource = sorted(slopes, key=lambda r: (slopes[r], r))[0] if slopes else "none"
    budgets_final = ((trajectory[-1].get("organ_backed") or {}).get("resources", {})
                     .get("budgets", {}))
    return {
        "has_resources": True,
        "mean_allocation_by_resource": {k: float(v) for k, v in mean_alloc.items()},
        "min_allocation_by_resource": {k: float(v) for k, v in min_alloc.items()},
        "shortfall_auc_by_resource": {k: float(v) for k, v in auc.items()},
        "total_shortfall_auc": float(sum(auc.values())),
        "allocation_slope_by_resource": {k: float(v) for k, v in slopes.items()},
        "worst_resource_slope": float(slopes[worst_resource]) if slopes else 0.0,
        "dominant_binding_resource": worst_resource,
        "exhaustion_time_by_resource": dict(exhausted),
        "global_resource_exhaustion_time": min(
            (t for t in exhausted.values() if t is not None), default=None),
        "final_budgets": {r: float(budgets_final.get(r, 0.0)) for r in SYSTEMIC_RESOURCES},
    }


DEFAULT_V3_CRITERIA: dict[str, Any] = {
    "eps_bio": 0.05,
    "eps_driver": 0.005,
    "eps_organ": 0.005,
    "eps_bio_worst": 0.1,
    "eps_driver_worst": 0.01,
    "eps_organ_worst": 0.01,
    "min_success_rate": 0.8,
    "safety_margin": 0.05,
    "min_allocation": 0.5,
    "max_cancer_burden": 0.5,
    "max_inflammation": 0.5,
    "max_fibrosis": 0.5,
    "min_neural_continuity": 0.6,
    "min_organ_reserve": 0.05,
    "max_cumulative_interventions": 800.0,
}

CROSS_SCALE_CONSTRAINTS = (
    "biological_age_slope",
    "driver_slope",
    "organ_function_margin",
    "organ_reserve_exhaustion",
    "global_resource_shortage",
    "perfusion_budget",
    "immune_budget",
    "metabolic_budget",
    "repair_budget",
    "cancer_burden",
    "inflammation",
    "fibrosis",
    "neural_continuity",
    "intervention_cost",
    "multi_organ_cascade",
)

_CONSTRAINT_TO_LEVEL = {
    "biological_age_slope": "biological_age",
    "driver_slope": "aging_driver",
    "organ_function_margin": "organ_function",
    "organ_reserve_exhaustion": "reserve",
    "global_resource_shortage": "systemic_resource",
    "perfusion_budget": "systemic_resource",
    "immune_budget": "systemic_resource",
    "metabolic_budget": "systemic_resource",
    "repair_budget": "systemic_resource",
    "cancer_burden": "cancer",
    "inflammation": "systemic_cascade",
    "fibrosis": "organ_function",
    "neural_continuity": "neural_continuity",
    "intervention_cost": "intervention_cost",
    "multi_organ_cascade": "systemic_cascade",
}


def validate_v3_criteria(criteria: dict[str, Any] | None) -> dict[str, float]:
    """Validate organ-backed v3 criteria (all finite, rate in range)."""
    merged = dict(DEFAULT_V3_CRITERIA)
    merged.update(criteria or {})
    unknown = set(merged) - set(DEFAULT_V3_CRITERIA)
    if unknown:
        raise ValueError(f"unknown v3 criteria keys: {sorted(unknown)}")
    validated = {}
    for key, value in merged.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"v3 criteria.{key} must be finite, got {value!r}")
        if float(value) < 0.0 or (key == "min_success_rate" and float(value) > 1.0):
            raise ValueError(f"v3 criteria.{key} out of range, got {value!r}")
        validated[key] = float(value)
    return validated


def _weighted_driver_slopes(trajectory: list[dict[str, Any]]) -> dict[str, float]:
    """Contribution-weighted post-adulthood driver slopes (pure, Stage 6A)."""
    adult = _adult_rows(trajectory)
    times = [float(row["chronological_age"]) for row in adult]
    slopes = {}
    for name in AGING_DRIVERS:
        series = [float((row.get("aging") or {}).get("drivers", {}).get(name, {}).get("damage", 0.0))
                  for row in adult]
        raw = _slope(times, series) if series else 0.0
        contribution = float(DEFAULT_DRIVER_PARAMS.get(name, {}).get("contribution", 1.0))
        slopes[name] = contribution * raw
    return slopes


def _cross_scale_checks(trajectory: list[dict[str, Any]],
                        criteria: dict[str, float]) -> dict[str, bool]:
    """Per-constraint violation flags over one trajectory (pure)."""
    adult = _adult_rows(trajectory)
    times = [float(row["chronological_age"]) for row in adult]
    bio_slope = _slope(times, [float(r["biological_age"]) for r in adult]) if adult else 0.0
    driver_slopes = _weighted_driver_slopes(trajectory)
    organs = summarize_organs(trajectory)
    resources = summarize_resources(trajectory, 0.25)
    final = trajectory[-1]
    checks: dict[str, bool] = {}
    checks["biological_age_slope"] = bio_slope > criteria["eps_bio"]
    checks["driver_slope"] = bool(driver_slopes) and max(driver_slopes.values()) > criteria["eps_driver"]
    checks["organ_function_margin"] = False
    if organs.get("has_organs"):
        from longevity.model.organ_backed import validate_proxy_params  # deferred

        params = validate_proxy_params(None)
        for pid, value in organs["min_function_by_organ"].items():
            if value < float(params[pid]["failure_threshold"]) + criteria["safety_margin"]:
                checks["organ_function_margin"] = True
                break
    checks["organ_reserve_exhaustion"] = False
    if organs.get("has_organs"):
        if min(organs["organ_reserve_final_by_organ"].values()) < criteria["min_organ_reserve"]:
            checks["organ_reserve_exhaustion"] = True
    checks["global_resource_shortage"] = False
    if resources.get("has_resources"):
        if min(resources["min_allocation_by_resource"].values()) < criteria["min_allocation"]:
            checks["global_resource_shortage"] = True
    for constraint, resource in (("perfusion_budget", "perfusion"), ("immune_budget", "immune"),
                                 ("metabolic_budget", "metabolic"), ("repair_budget", "repair")):
        checks[constraint] = bool(resources.get("has_resources")) and \
            resources["min_allocation_by_resource"][resource] < criteria["min_allocation"]
    checks["cancer_burden"] = max(float(r["cancer_burden"]) for r in trajectory[1:]) > criteria["max_cancer_burden"]
    checks["inflammation"] = max(float(r["inflammation"]) for r in trajectory[1:]) > criteria["max_inflammation"]
    checks["fibrosis"] = max(float(r["fibrosis"]) for r in trajectory[1:]) > criteria["max_fibrosis"]
    brain_min = min(float(r["systems"]["brain_cns"].get("informational_continuity", 1.0))
                    for r in trajectory[1:])
    checks["neural_continuity"] = min(brain_min, float(
        organs.get("informational_continuity_min", 1.0))) < criteria["min_neural_continuity"]
    checks["intervention_cost"] = len(final.get("intervention_history", [])) > criteria["max_cumulative_interventions"]
    cascade = 0
    for row in adult:
        proxies = (row.get("organ_backed") or {}).get("proxies", {})
        below = sum(1 for p in proxies.values() if float(p.get("function", 1.0)) < 0.40)
        cascade = max(cascade, below)
    checks["multi_organ_cascade"] = bool(organs.get("has_organs")) and cascade >= 3
    return checks


def cross_scale_binding(trajectory: list[dict[str, Any]],
                        criteria: dict[str, Any] | None = None) -> dict[str, Any]:
    """First-violated cross-scale constraint + dominant level/organ/driver/resource.

    Pure and non-mutating; deterministic tie-breaking follows
    ``CROSS_SCALE_CONSTRAINTS`` order. ``"none"`` when the whole adult
    window holds.
    """
    criteria = validate_v3_criteria(criteria)
    if not trajectory or len(trajectory) < 2:
        raise ValueError("cross_scale_binding of empty trajectory")
    checks = _cross_scale_checks(trajectory, criteria)
    sequence = [c for c in CROSS_SCALE_CONSTRAINTS if checks[c]]
    first = sequence[0] if sequence else "none"
    time_to_first: float | None = None
    if first != "none":
        # Incremental scan: first adult age where the constraint trips.
        for end in range(2, len(trajectory)):
            if _cross_scale_checks(trajectory[:end + 1], criteria)[first]:
                time_to_first = float(trajectory[end]["chronological_age"])
                break
    organs = summarize_organs(trajectory)
    resources = summarize_resources(trajectory, 0.25)
    from longevity.analysis.aging_metrics import summarize_drivers  # local reuse

    drivers = summarize_drivers(trajectory)
    return {
        "first_cross_scale_constraint_violated": first,
        "cross_scale_binding_constraint_sequence": sequence,
        "time_to_first_cross_scale_constraint_violation": time_to_first,
        "dominant_binding_level": _CONSTRAINT_TO_LEVEL.get(first, "none") if first != "none" else "none",
        "dominant_binding_organ": organs.get("dominant_binding_organ", "none"),
        "dominant_binding_driver": drivers.get("dominant_binding_driver", "none"),
        "dominant_binding_resource": resources.get("dominant_binding_resource", "none"),
    }


def summarize_organ_backed_run(trajectory: list[dict[str, Any]], dt: float = 0.25,
                               criteria: dict[str, Any] | None = None) -> dict[str, Any]:
    """Full organ-backed per-run summary for runner merge (pure, Stage 6A)."""
    validated = validate_v3_criteria(criteria)
    organs = summarize_organs(trajectory)
    resources = summarize_resources(trajectory, dt)
    binding = cross_scale_binding(trajectory, validated)
    final = trajectory[-1]
    stats = ((final.get("organ_backed") or {}).get("coordination_stats", {}))
    return {"organs": organs, "systemic_resources": resources, "cross_scale": binding,
            "coordination_stats": {k: stats.get(k, 0) for k in
                                   ("executed", "scaled", "deferred", "rejected",
                                    "recovered_from_queue")}}


def robust_bounded_degradation_v3(summaries: list[dict[str, Any]],
                                  criteria: dict[str, Any] | None = None) -> dict[str, Any]:
    """Strict organ-backed v3 verdict across seeds (pure, Stage 6A).

    Each summary must carry ``organs`` / ``systemic_resources`` blocks (see
    :func:`summarize_organ_backed_run` via the runner merge); missing blocks
    count as failures, never as passes. Operational criterion only.
    """
    criteria = validate_v3_criteria(criteria)
    if not summaries:
        raise ValueError("robust_bounded_degradation_v3 of empty summaries")
    per_run = []
    for summary in summaries:
        organs = summary.get("organs", {})
        resources = summary.get("systemic_resources", {})
        if not organs.get("has_organs", False) or not resources.get("has_resources", False):
            per_run.append(False)
            continue
        checks = _checks_from_summary(summary, criteria)
        per_run.append(all(not v for v in checks.values())
                       and summary.get("terminal_decline_reached", False) is False)
    success_rate = sum(per_run) / len(per_run)
    worst_bio = max(float(s.get("biological_age_slope_after_adulthood", 9e9)) for s in summaries)
    worst_driver = max(float(s.get("drivers", {}).get("worst_driver_slope", 9e9)) for s in summaries)
    worst_organ = min(float(s.get("organs", {}).get("worst_organ_function_slope", 9e9))
                      for s in summaries)
    worst_resource = min(float(s.get("systemic_resources", {}).get("worst_resource_slope", 9e9))
                         for s in summaries)
    return {
        "robust_bounded_degradation_v3": bool(
            success_rate >= criteria["min_success_rate"]
            and worst_bio <= criteria["eps_bio_worst"]
            and worst_driver <= criteria["eps_driver_worst"]
            and worst_organ >= -criteria["eps_organ_worst"]
            and worst_resource >= -criteria["eps_organ_worst"]),
        "success_rate_bounded_v3": success_rate,
        "worst_case_biological_age_slope": worst_bio,
        "worst_case_driver_slope": worst_driver,
        "worst_case_organ_slope": worst_organ,
        "worst_case_resource_slope": worst_resource,
        "n_runs": len(summaries),
    }


def _checks_from_summary(summary: dict[str, Any], criteria: dict[str, float]) -> dict[str, bool]:
    """Recompute cross-scale checks from an aggregated per-run summary."""
    organs = summary.get("organs", {})
    resources = summary.get("systemic_resources", {})
    checks: dict[str, bool] = {}
    checks["biological_age_slope"] = float(
        summary.get("biological_age_slope_after_adulthood", 9e9)) > criteria["eps_bio"]
    checks["driver_slope"] = float(
        summary.get("drivers", {}).get("worst_driver_slope", 9e9)) > criteria["eps_driver"]
    checks["organ_function_margin"] = False
    from longevity.model.organ_backed import validate_proxy_params  # deferred

    params = validate_proxy_params(None)
    for pid, value in organs.get("min_function_by_organ", {}).items():
        if float(value) < float(params[pid]["failure_threshold"]) + criteria["safety_margin"]:
            checks["organ_function_margin"] = True
            break
    checks["organ_reserve_exhaustion"] = bool(organs.get("organ_reserve_final_by_organ")) and \
        min(float(v) for v in organs["organ_reserve_final_by_organ"].values()) < criteria["min_organ_reserve"]
    checks["global_resource_shortage"] = bool(resources.get("min_allocation_by_resource")) and \
        min(float(v) for v in resources["min_allocation_by_resource"].values()) < criteria["min_allocation"]
    for constraint, resource in (("perfusion_budget", "perfusion"), ("immune_budget", "immune"),
                                 ("metabolic_budget", "metabolic"), ("repair_budget", "repair")):
        checks[constraint] = bool(resources.get("min_allocation_by_resource")) and \
            float(resources["min_allocation_by_resource"].get(resource, 1.0)) < criteria["min_allocation"]
    lifespan = max(1.0, float(summary.get("lifespan", 1.0)))
    checks["cancer_burden"] = float(summary.get("cancer_auc", 9e9)) / lifespan > criteria["max_cancer_burden"]
    checks["inflammation"] = float(summary.get("inflammation_auc", 9e9)) / lifespan > criteria["max_inflammation"]
    checks["fibrosis"] = float(summary.get("fibrosis_auc", 9e9)) / lifespan > criteria["max_fibrosis"]
    checks["neural_continuity"] = min(
        float(summary.get("informational_continuity_min", 0.0)),
        float(organs.get("informational_continuity_min", 0.0))) < criteria["min_neural_continuity"]
    checks["intervention_cost"] = float(summary.get("n_interventions", 0)) > criteria["max_cumulative_interventions"]
    checks["multi_organ_cascade"] = len(organs.get("failed_organ_ids", [])) >= 3
    return checks
