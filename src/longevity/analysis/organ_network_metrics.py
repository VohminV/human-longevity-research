"""ANALYSIS LAYER: organ-network metrics + v4 + binding v3 (Stage 6B).

Pure functions over organism trajectories carrying an ``organ_network``
block. Network summaries, hard-limit summaries, network-aware binding
analysis, and the strict ``robust_bounded_degradation_v4`` criterion.
All descriptive and model-internal; never biological claims.
"""

from __future__ import annotations

import math

from typing import Any

from longevity.model.organ_backed import ORGAN_PROXIES, SYSTEMIC_RESOURCES
from longevity.model.organ_network import FEEDBACK_LOOPS

try:
    from longevity.model.aging import AGING_DRIVERS, DEFAULT_DRIVER_PARAMS
except ImportError:  # pragma: no cover
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


def _has_network(trajectory: list[dict[str, Any]]) -> bool:
    return any((row.get("organ_network") or {}).get("edges") is not None
               and row.get("organ_network") is not None for row in trajectory[1:])


def _network_series(trajectory: list[dict[str, Any]], key: str) -> list[float]:
    return [float((row.get("organ_network") or {}).get(key, 0.0)) for row in _adult_rows(trajectory)
            if row.get("organ_network") is not None]


def summarize_network(trajectory: list[dict[str, Any]], dt: float) -> dict[str, Any]:
    """Per-run organ-network summary (pure, Stage 6B)."""
    if not trajectory:
        raise ValueError("summarize_network of empty trajectory")
    _finite(dt, "dt")
    if not _has_network(trajectory):
        return {"has_network": False, "biological_age_network_slope": 0.0,
                "worst_feedback_gain": 0.0, "max_cascade_risk": 0.0,
                "dominant_binding_edge": "none", "dominant_binding_loop": "none"}
    adult = _adult_rows(trajectory)
    times = [float(row["chronological_age"]) for row in adult]
    bio_net = [float((row.get("organ_network") or {}).get("biological_age_network", 25.0))
               for row in adult]
    cascade = [float((row.get("organ_network") or {}).get("cascade_risk", 0.0)) for row in adult]
    energy = [float((row.get("organ_network") or {}).get("energy_budget", 0.0)) for row in adult]
    mutation = [float((row.get("organ_network") or {}).get("mutation_load", 0.0)) for row in adult]
    toxicity = [float((row.get("organ_network") or {}).get("intervention_toxicity", 0.0))
                for row in adult]
    info_loss = [float((row.get("organ_network") or {}).get("information_loss_risk", 0.0))
                 for row in adult]
    # Edge risks: max failure_risk per edge over the adult window.
    edge_max: dict[str, float] = {}
    edge_final: dict[str, float] = {}
    edge_util: dict[str, float] = {}
    for row in adult:
        for edge in (row.get("organ_network") or {}).get("edges", []):
            eid = str(edge.get("edge_id", ""))
            risk = max(0.0, min(1.0, float(edge.get("failure_risk", 0.0))))
            edge_max[eid] = max(edge_max.get(eid, 0.0), risk)
    final_edges = (trajectory[-1].get("organ_network") or {}).get("edges", [])
    for edge in final_edges:
        eid = str(edge.get("edge_id", ""))
        edge_final[eid] = max(0.0, min(1.0, float(edge.get("failure_risk", 0.0))))
        edge_util[eid] = max(0.0, float(edge.get("utilization", 0.0)))
    dominant_edge = sorted(edge_max, key=lambda e: (-edge_max[e], e))[0] if edge_max else "none"
    # Feedback gains: max per loop.
    loop_max: dict[str, float] = {}
    loop_final: dict[str, float] = {}
    for row in adult:
        feedback = (row.get("organ_network") or {}).get("feedback", {})
        for loop in FEEDBACK_LOOPS:
            gain = max(0.0, float(feedback.get(loop, {}).get("gain_value", 0.0)))
            loop_max[loop] = max(loop_max.get(loop, 0.0), gain)
    final_feedback = (trajectory[-1].get("organ_network") or {}).get("feedback", {})
    for loop in FEEDBACK_LOOPS:
        loop_final[loop] = max(0.0, float(final_feedback.get(loop, {}).get("gain_value", 0.0)))
    dominant_loop = sorted(loop_max, key=lambda l: (-loop_max[l], l))[0] if loop_max else "none"
    worst_gain = max(loop_max.values()) if loop_max else 0.0
    runaway = any(v > 0.8 for v in loop_max.values())
    final = trajectory[-1].get("organ_network") or {}
    # Node finals.
    node_function: dict[str, float] = {}
    if trajectory[-1].get("organ_backed"):
        for pid in ORGAN_PROXIES:
            node_function[pid] = float(trajectory[-1]["organ_backed"]["proxies"][pid].get("function", 0.0))
    return {
        "has_network": True,
        "organ_network_model": "reduced_network_feedback",
        "biological_age_network_final": float(bio_net[-1]) if bio_net else 25.0,
        "biological_age_network_slope": float(_slope(times, bio_net)) if bio_net else 0.0,
        "network_age_contribution_final": float(final.get("network_age_contribution", 0.0)),
        "cascade_risk_final": float(cascade[-1]) if cascade else 0.0,
        "max_cascade_risk": float(max(cascade)) if cascade else 0.0,
        "cascade_slope": float(_slope(times, cascade)) if cascade else 0.0,
        "energy_budget_final": float(energy[-1]) if energy else 0.0,
        "min_energy_budget": float(min(energy)) if energy else 0.0,
        "energy_slope": float(_slope(times, energy)) if energy else 0.0,
        "mutation_load_final": float(mutation[-1]) if mutation else 0.0,
        "max_mutation_load": float(max(mutation)) if mutation else 0.0,
        "mutation_slope": float(_slope(times, mutation)) if mutation else 0.0,
        "intervention_toxicity_final": float(toxicity[-1]) if toxicity else 0.0,
        "max_intervention_toxicity": float(max(toxicity)) if toxicity else 0.0,
        "information_loss_final": float(info_loss[-1]) if info_loss else 0.0,
        "max_information_loss": float(max(info_loss)) if info_loss else 0.0,
        "edge_failure_risk_final": dict(edge_final),
        "edge_utilization_final": dict(edge_util),
        "edge_max_risk": {k: float(v) for k, v in edge_max.items()},
        "dominant_binding_edge": dominant_edge,
        "feedback_gain_final_by_loop": {k: float(v) for k, v in loop_final.items()},
        "feedback_gain_max_by_loop": {k: float(v) for k, v in loop_max.items()},
        "max_feedback_gain": float(worst_gain),
        "worst_feedback_gain": float(worst_gain),
        "dominant_binding_loop": dominant_loop,
        "runaway_feedback_detected": bool(runaway),
        "node_function_final_by_organ": {k: float(v) for k, v in node_function.items()},
        "failed_edge_ids": list((trajectory[-1].get("organ_network") or {}).get("failed_edge_ids", [])),
        "failed_feedback_loop_ids": list(
            (trajectory[-1].get("organ_network") or {}).get("failed_feedback_loop_ids", [])),
        "failed_hard_limit_ids": list(
            (trajectory[-1].get("organ_network") or {}).get("failed_hard_limit_ids", [])),
        "network_failure_sequence": list(
            (trajectory[-1].get("organ_network") or {}).get("network_failure_sequence", [])),
    }


def summarize_hard_limits(trajectory: list[dict[str, Any]]) -> dict[str, Any]:
    """Hard-limit slack/violation summary (pure, Stage 6B)."""
    if not trajectory:
        raise ValueError("summarize_hard_limits of empty trajectory")
    if not _has_network(trajectory):
        return {"has_hard_limits": False, "hard_limit_violation_counts": {},
                "first_hard_limit_violated": "none"}
    counts: dict[str, int] = {}
    first: dict[str, float] = {}
    for row in trajectory[1:]:
        net = row.get("organ_network") or {}
        for limit_id in net.get("failed_hard_limit_ids", []):
            counts[limit_id] = counts.get(limit_id, 0) + 1
            if limit_id not in first:
                first[limit_id] = float(row["chronological_age"])
    ordered_first = sorted(first, key=lambda k: (first[k], k))[0] if first else "none"
    final = trajectory[-1].get("organ_network") or {}
    limits = final.get("hard_limits", {})
    energy_slack = max(0.0, float(final.get("energy_budget", 0.0)))
    mutation_slack = max(0.0, float(limits.get("max_mutation_load", 1.0))
                         - float(final.get("mutation_load", 0.0)))
    brain_cont = 1.0
    if trajectory[-1].get("organ_backed"):
        brain_cont = float(trajectory[-1]["organ_backed"]["proxies"]
                           ["brain_cns_proxy"].get("informational_continuity", 1.0))
    info_slack = max(0.0, brain_cont - float(limits.get("min_informational_continuity", 0.5)))
    cascade_slack = max(0.0, float(limits.get("max_cascade_risk", 0.6))
                        - float(final.get("cascade_risk", 0.0)))
    return {
        "has_hard_limits": True,
        "hard_limit_violation_counts": dict(counts),
        "first_hard_limit_violated": ordered_first,
        "time_to_first_hard_limit_violation": first.get(ordered_first),
        "energy_budget_final": float(final.get("energy_budget", 0.0)),
        "min_energy_budget": float(min(_network_series(trajectory, "energy_budget") or [0.0])),
        "mutation_load_final": float(final.get("mutation_load", 0.0)),
        "max_mutation_load_seen": float(max(_network_series(trajectory, "mutation_load") or [0.0])),
        "mutation_load_slack_min": float(mutation_slack),
        "information_loss_slack_min": float(info_slack),
        "energy_slack_min": float(energy_slack),
        "cascade_slack_min": float(cascade_slack),
        "intervention_toxicity_final": float(final.get("intervention_toxicity", 0.0)),
        "niche_disorder_final": float(final.get("niche_disorder", 0.0)),
        "failed_hard_limit_ids": list(final.get("failed_hard_limit_ids", [])),
    }


DEFAULT_V4_CRITERIA: dict[str, Any] = {
    "eps_bio": 0.05,
    "eps_bio_network": 0.05,
    "eps_driver": 0.005,
    "eps_organ": 0.005,
    "eps_bio_worst": 0.1,
    "eps_bio_network_worst": 0.1,
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
    "max_cascade_risk": 0.6,
    "max_mutation_load": 1.0,
    "max_feedback_gain": 0.8,
    "min_energy_budget": 1.0,
    "max_intervention_toxicity": 3.0,
}

NETWORK_BINDING_CONSTRAINTS = (
    "biological_age_slope",
    "biological_age_network_slope",
    "driver_slope",
    "organ_function_margin",
    "organ_reserve_exhaustion",
    "global_resource_shortage",
    "perfusion_budget",
    "immune_budget",
    "metabolic_budget",
    "repair_budget",
    "network_edge",
    "feedback_loop",
    "cascade_risk",
    "hard_limit",
    "energy_budget",
    "mutation_load",
    "information_continuity",
    "cancer_burden",
    "inflammation",
    "fibrosis",
    "intervention_cost",
    "systemic_cascade",
)

_CONSTRAINT_TO_LEVEL = {
    "biological_age_slope": "biological_age",
    "biological_age_network_slope": "biological_age_network",
    "driver_slope": "aging_driver",
    "organ_function_margin": "organ_function",
    "organ_reserve_exhaustion": "reserve",
    "global_resource_shortage": "systemic_resource",
    "perfusion_budget": "systemic_resource",
    "immune_budget": "systemic_resource",
    "metabolic_budget": "systemic_resource",
    "repair_budget": "systemic_resource",
    "network_edge": "network_edge",
    "feedback_loop": "feedback_loop",
    "cascade_risk": "cascade_risk",
    "hard_limit": "hard_limit",
    "energy_budget": "energy_budget",
    "mutation_load": "mutation_load",
    "information_continuity": "information_continuity",
    "cancer_burden": "cancer",
    "inflammation": "systemic_cascade",
    "fibrosis": "organ_function",
    "intervention_cost": "intervention_cost",
    "systemic_cascade": "systemic_cascade",
}


def validate_v4_criteria(criteria: dict[str, Any] | None) -> dict[str, float]:
    merged = dict(DEFAULT_V4_CRITERIA)
    merged.update(criteria or {})
    unknown = set(merged) - set(DEFAULT_V4_CRITERIA)
    if unknown:
        raise ValueError(f"unknown v4 criteria keys: {sorted(unknown)}")
    validated = {}
    for key, value in merged.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"v4 criteria.{key} must be finite, got {value!r}")
        if float(value) < 0.0 or (key == "min_success_rate" and float(value) > 1.0):
            raise ValueError(f"v4 criteria.{key} out of range, got {value!r}")
        validated[key] = float(value)
    return validated


def _network_checks(trajectory: list[dict[str, Any]], criteria: dict[str, float]) -> dict[str, bool]:
    from longevity.analysis.organ_backed_metrics import _cross_scale_checks  # reuse v3 checks

    checks: dict[str, bool] = {}
    base = _cross_scale_checks(trajectory, {k: criteria[k] for k in (
        "eps_bio", "eps_driver", "safety_margin", "min_allocation",
        "max_cancer_burden", "max_inflammation", "max_fibrosis",
        "min_neural_continuity", "min_organ_reserve", "max_cumulative_interventions")
        if k in criteria})
    checks.update(base)
    adult = _adult_rows(trajectory)
    times = [float(row["chronological_age"]) for row in adult]
    bio_net = [float((row.get("organ_network") or {}).get("biological_age_network", 25.0))
               for row in adult] if adult and adult[0].get("organ_network") else []
    checks["biological_age_network_slope"] = bool(bio_net) and \
        _slope(times, bio_net) > criteria["eps_bio_network"]
    checks["biological_age_slope"] = base.get("biological_age_slope", False)
    network = summarize_network(trajectory, 0.25)
    hard = summarize_hard_limits(trajectory)
    checks["driver_slope"] = base.get("driver_slope", False)
    checks["organ_function_margin"] = base.get("organ_function_margin", False)
    checks["organ_reserve_exhaustion"] = base.get("organ_reserve_exhaustion", False)
    checks["global_resource_shortage"] = base.get("global_resource_shortage", False)
    for constraint in ("perfusion_budget", "immune_budget", "metabolic_budget", "repair_budget"):
        checks[constraint] = base.get(constraint, False)
    checks["network_edge"] = bool(network.get("has_network")) and bool(network.get("failed_edge_ids"))
    checks["feedback_loop"] = bool(network.get("has_network")) and \
        (bool(network.get("runaway_feedback_detected")) or bool(network.get("failed_feedback_loop_ids")))
    checks["cascade_risk"] = bool(network.get("has_network")) and \
        float(network.get("max_cascade_risk", 0.0)) > criteria["max_cascade_risk"]
    checks["hard_limit"] = bool(hard.get("has_hard_limits")) and \
        bool(hard.get("failed_hard_limit_ids"))
    checks["energy_budget"] = bool(network.get("has_network")) and \
        float(network.get("min_energy_budget", 9e9)) < criteria["min_energy_budget"]
    checks["mutation_load"] = bool(network.get("has_network")) and \
        float(network.get("max_mutation_load", 0.0)) > criteria["max_mutation_load"]
    brain_min = 1.0
    if trajectory[-1].get("organ_backed"):
        series = [float(row["organ_backed"]["proxies"]["brain_cns_proxy"]
                         .get("informational_continuity", 1.0))
                  for row in adult if row.get("organ_backed")]
        brain_min = min(series) if series else 1.0
    else:
        brain_min = min(float(r["systems"]["brain_cns"].get("informational_continuity", 1.0))
                        for r in trajectory[1:])
    checks["information_continuity"] = brain_min < criteria["min_neural_continuity"]
    checks["cancer_burden"] = base.get("cancer_burden", False)
    checks["inflammation"] = base.get("inflammation", False)
    checks["fibrosis"] = base.get("fibrosis", False)
    checks["intervention_cost"] = base.get("intervention_cost", False)
    checks["systemic_cascade"] = base.get("multi_organ_cascade", False)
    # Canonical v3 name is multi_organ_cascade; expose systemic_cascade alias.
    return checks


def network_binding(trajectory: list[dict[str, Any]],
                    criteria: dict[str, Any] | None = None) -> dict[str, Any]:
    """Network-level binding analysis (pure, deterministic, non-mutating)."""
    criteria_v = validate_v4_criteria(criteria)
    if not trajectory or len(trajectory) < 2:
        raise ValueError("network_binding of empty trajectory")
    checks = _network_checks(trajectory, criteria_v)
    sequence = [c for c in NETWORK_BINDING_CONSTRAINTS if checks.get(c)]
    first = sequence[0] if sequence else "none"
    time_to_first: float | None = None
    if first != "none":
        for end in range(2, len(trajectory)):
            if _network_checks(trajectory[:end + 1], criteria_v).get(first):
                time_to_first = float(trajectory[end]["chronological_age"])
                break
    network = summarize_network(trajectory, 0.25)
    hard = summarize_hard_limits(trajectory)
    from longevity.analysis.organ_backed_metrics import cross_scale_binding  # reuse
    from longevity.analysis.aging_metrics import summarize_drivers

    try:
        legacy = cross_scale_binding(trajectory)
    except Exception:
        legacy = {}
    drivers = summarize_drivers(trajectory)
    resources = (trajectory[-1].get("organ_backed") or {}).get("resources", {})
    _ = resources
    return {
        "first_network_constraint_violated": first,
        "network_binding_constraint_sequence": sequence,
        "time_to_first_network_constraint_violation": time_to_first,
        "dominant_binding_level": _CONSTRAINT_TO_LEVEL.get(first, "none") if first != "none" else "none",
        "dominant_binding_organ": legacy.get("dominant_binding_organ", "none"),
        "dominant_binding_driver": drivers.get("dominant_binding_driver", "none"),
        "dominant_binding_resource": legacy.get("dominant_binding_resource", "none"),
        "dominant_binding_edge": network.get("dominant_binding_edge", "none"),
        "dominant_binding_loop": network.get("dominant_binding_loop", "none"),
        "dominant_binding_hard_limit": hard.get("first_hard_limit_violated", "none"),
    }


def summarize_organ_network_run(trajectory: list[dict[str, Any]], dt: float = 0.25,
                                criteria: dict[str, Any] | None = None) -> dict[str, Any]:
    """Full organ-network per-run summary for runner merge (pure)."""
    validated = validate_v4_criteria(criteria)
    network = summarize_network(trajectory, dt)
    hard = summarize_hard_limits(trajectory)
    binding = network_binding(trajectory, validated)
    final = trajectory[-1]
    net_stats = ((final.get("organ_network") or {}).get("coordination_stats", {}))
    coord = ((final.get("organ_backed") or {}).get("coordination_stats", {}))
    return {"organ_network": network, "hard_limits": hard, "network_binding": binding,
            "network_coordination_stats": {k: net_stats.get(k, 0) for k in (
                "cascade_guard_rejections", "bottleneck_priority_executions",
                "mutation_guard_rejections", "information_priority_executions")},
            "coordination_stats": {k: coord.get(k, 0) for k in (
                "executed", "scaled", "deferred", "rejected", "recovered_from_queue")}}


def robust_bounded_degradation_v4(summaries: list[dict[str, Any]],
                                  criteria: dict[str, Any] | None = None) -> dict[str, Any]:
    """Strict organ-network v4 verdict across seeds (pure).

    v3 conditions plus network/hard-limit discipline. Missing network
    blocks count as failures, never passes. Operational criterion only.
    """
    criteria_v = validate_v4_criteria(criteria)
    if not summaries:
        raise ValueError("robust_bounded_degradation_v4 of empty summaries")
    from longevity.analysis.organ_backed_metrics import robust_bounded_degradation_v3

    v3 = robust_bounded_degradation_v3(summaries)
    per_run = []
    for summary in summaries:
        network = summary.get("organ_network", {})
        hard = summary.get("hard_limits", {})
        if not network.get("has_network", False):
            per_run.append(False)
            continue
        bio_net_slope = float(summary.get("organ_network", {}).get(
            "biological_age_network_slope", 9e9))
        ok = (
            float(summary.get("biological_age_slope_after_adulthood", 9e9)) <= criteria_v["eps_bio"]
            and bio_net_slope <= criteria_v["eps_bio_network"]
            and float(network.get("max_cascade_risk", 9e9)) <= criteria_v["max_cascade_risk"]
            and float(network.get("max_mutation_load", 9e9)) <= criteria_v["max_mutation_load"]
            and float(network.get("worst_feedback_gain", 9e9)) <= criteria_v["max_feedback_gain"]
            and float(network.get("min_energy_budget", -9e9)) >= criteria_v["min_energy_budget"]
            and float(network.get("max_intervention_toxicity", 9e9))
            <= criteria_v["max_intervention_toxicity"]
            and not network.get("runaway_feedback_detected", True)
            and not network.get("failed_edge_ids", ["x"])
            and not hard.get("failed_hard_limit_ids", ["x"])
            and summary.get("terminal_decline_reached", True) is False
        )
        per_run.append(bool(ok))
    success_rate = sum(per_run) / len(per_run)
    worst_bio = max(float(s.get("biological_age_slope_after_adulthood", 9e9)) for s in summaries)
    worst_bio_net = max(float(s.get("organ_network", {}).get("biological_age_network_slope", 9e9))
                        for s in summaries)
    worst_driver = max(float(s.get("drivers", {}).get("worst_driver_slope", 9e9)) for s in summaries)
    worst_organ = min(float(s.get("organs", {}).get("worst_organ_function_slope", 9e9))
                      for s in summaries)
    worst_resource = min(float(s.get("systemic_resources", {}).get("worst_resource_slope", 9e9))
                         for s in summaries)
    worst_feedback = max(float(s.get("organ_network", {}).get("worst_feedback_gain", 9e9))
                         for s in summaries)
    worst_cascade = max(float(s.get("organ_network", {}).get("max_cascade_risk", 9e9))
                        for s in summaries)
    worst_mutation = max(float(s.get("organ_network", {}).get("max_mutation_load", 9e9))
                         for s in summaries)
    worst_info = min(float(s.get("informational_continuity_min", 9e9)) for s in summaries)
    indicator = bool(
        success_rate >= criteria_v["min_success_rate"]
        and v3["robust_bounded_degradation_v3"]
        and all(per_run)
        and worst_bio <= criteria_v["eps_bio_worst"]
        and worst_bio_net <= criteria_v["eps_bio_network_worst"]
        and worst_driver <= criteria_v["eps_driver_worst"]
        and worst_organ >= -criteria_v["eps_organ_worst"]
        and worst_resource >= -criteria_v["eps_organ_worst"])
    return {
        "robust_bounded_degradation_v4": indicator,
        "success_rate_bounded_v4": success_rate,
        "worst_case_biological_age_slope": worst_bio,
        "worst_case_biological_age_network_slope": worst_bio_net,
        "worst_case_driver_slope": worst_driver,
        "worst_case_organ_slope": worst_organ,
        "worst_case_resource_slope": worst_resource,
        "worst_case_feedback_gain": worst_feedback,
        "worst_case_cascade_risk": worst_cascade,
        "worst_case_mutation_load": worst_mutation,
        "worst_case_information_preservation": worst_info,
        "robust_v3": v3["robust_bounded_degradation_v3"],
        "n_runs": len(summaries),
    }
