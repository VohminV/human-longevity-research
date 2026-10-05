"""ANALYSIS LAYER: reversibility metrics + v5 + binding v4 (Stage 6C).

Pure functions over organism trajectories carrying a ``reversibility``
block. Reversible / irreversible summaries, conversion / ceiling /
information / mutation / niche / entropy summaries, reversibility-aware
binding analysis, and the strict ``robust_bounded_degradation_v5``
criterion. All descriptive and model-internal; never biological claims.
"""

from __future__ import annotations

import math

from typing import Any

from longevity.model.aging import AGING_DRIVERS
from longevity.model.organ_backed import ORGAN_PROXIES


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


def _has_reversibility(trajectory: list[dict[str, Any]]) -> bool:
    return any(row.get("reversibility") is not None for row in trajectory[1:])


def _rev_series(trajectory: list[dict[str, Any]], key: str) -> list[float]:
    return [float((row.get("reversibility") or {}).get(key, 0.0)) for row in _adult_rows(trajectory)
            if row.get("reversibility") is not None]


DEFAULT_V5_CRITERIA: dict[str, Any] = {
    "eps_bio": 0.05,
    "eps_bio_network": 0.05,
    "eps_bio_rev": 0.05,
    "eps_driver": 0.005,
    "eps_organ": 0.005,
    "eps_reversible": 0.004,
    "eps_irreversible": 0.004,
    "eps_information": 0.004,
    "eps_mutation": 0.004,
    "eps_niche": 0.004,
    "eps_bio_worst": 0.1,
    "eps_bio_network_worst": 0.1,
    "eps_bio_rev_worst": 0.1,
    "eps_driver_worst": 0.01,
    "eps_organ_worst": 0.01,
    "eps_irreversible_worst": 0.008,
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
    "max_conversion_rate": 0.05,
    "min_repair_remaining": 0.02,
    "max_information_debt": 0.6,
    "max_mutation_fixation": 0.6,
    "max_niche_disorder": 0.7,
}

REVERSIBILITY_BINDING_CONSTRAINTS = (
    "biological_age_slope",
    "biological_age_network_slope",
    "biological_age_reversibility_slope",
    "driver_slope",
    "reversible_burden",
    "irreversible_accumulation",
    "conversion_runaway",
    "repair_ceiling_exhaustion",
    "information_debt",
    "mutation_fixation",
    "niche_disorder",
    "entropy_production",
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
    "cancer_burden",
    "inflammation",
    "fibrosis",
    "intervention_cost",
    "systemic_cascade",
)

_CONSTRAINT_TO_LEVEL = {
    "biological_age_slope": "biological_age",
    "biological_age_network_slope": "biological_age_network",
    "biological_age_reversibility_slope": "biological_age_reversibility",
    "driver_slope": "aging_driver",
    "reversible_burden": "reversible_burden",
    "irreversible_accumulation": "irreversible_accumulation",
    "conversion_runaway": "conversion_runaway",
    "repair_ceiling_exhaustion": "repair_ceiling_exhaustion",
    "information_debt": "information_debt",
    "mutation_fixation": "mutation_fixation",
    "niche_disorder": "niche_disorder",
    "entropy_production": "entropy_production",
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
    "cancer_burden": "cancer",
    "inflammation": "systemic_cascade",
    "fibrosis": "organ_function",
    "intervention_cost": "intervention_cost",
    "systemic_cascade": "systemic_cascade",
}


def validate_v5_criteria(criteria: dict[str, Any] | None) -> dict[str, float]:
    merged = dict(DEFAULT_V5_CRITERIA)
    merged.update(criteria or {})
    unknown = set(merged) - set(DEFAULT_V5_CRITERIA)
    if unknown:
        raise ValueError(f"unknown v5 criteria keys: {sorted(unknown)}")
    validated = {}
    for key, value in merged.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"v5 criteria.{key} must be finite, got {value!r}")
        if float(value) < 0.0 or (key == "min_success_rate" and float(value) > 1.0):
            raise ValueError(f"v5 criteria.{key} out of range, got {value!r}")
        validated[key] = float(value)
    return validated


def summarize_reversibility(trajectory: list[dict[str, Any]], dt: float) -> dict[str, Any]:
    """Per-run reversibility summary (pure, Stage 6C)."""
    if not trajectory:
        raise ValueError("summarize_reversibility of empty trajectory")
    _finite(dt, "dt")
    if not _has_reversibility(trajectory):
        return {"has_reversibility": False, "worst_reversible_slope": 0.0,
                "worst_irreversible_slope": 0.0,
                "dominant_reversibility_wall": "none"}
    adult = _adult_rows(trajectory)
    times = [float(row["chronological_age"]) for row in adult]
    rev_burden = _rev_series(trajectory, "reversible_burden")
    irr_burden = _rev_series(trajectory, "irreversible_burden")
    info = _rev_series(trajectory, "information_debt")
    mut = _rev_series(trajectory, "mutation_fixation")
    niche = _rev_series(trajectory, "niche_disorder")
    entropy = _rev_series(trajectory, "entropy_production")
    bio_rev = _rev_series(trajectory, "biological_age_reversibility")
    floor = _rev_series(trajectory, "biological_age_floor_dynamic")
    flux = _rev_series(trajectory, "total_conversion_flux")
    remaining = _rev_series(trajectory, "repair_remaining")
    # Per-driver slopes from ledger (final states carry full history only
    # via burdens; per-component slopes use burden proxies + finals).
    final = trajectory[-1].get("reversibility") or {}
    rev_by_driver = {n: float(final.get("drivers", {}).get(n, {}).get("reversible", 0.0))
                     for n in AGING_DRIVERS}
    irr_by_driver = {n: float(final.get("drivers", {}).get(n, {}).get("irreversible", 0.0))
                     for n in AGING_DRIVERS}
    conv_by_driver = {n: float(final.get("drivers", {}).get(n, {}).get("conversion_rate", 0.0))
                      for n in AGING_DRIVERS}
    rev_by_organ = {p: float(final.get("organs", {}).get(p, {}).get("reversible", 0.0))
                    for p in ORGAN_PROXIES}
    irr_by_organ = {p: float(final.get("organs", {}).get(p, {}).get("irreversible", 0.0))
                    for p in ORGAN_PROXIES}
    worst_rev = float(_slope(times, rev_burden)) if rev_burden else 0.0
    worst_irr = float(_slope(times, irr_burden)) if irr_burden else 0.0
    info_slope = float(_slope(times, info)) if info else 0.0
    mut_slope = float(_slope(times, mut)) if mut else 0.0
    niche_slope = float(_slope(times, niche)) if niche else 0.0
    entropy_slope = float(_slope(times, entropy)) if entropy else 0.0
    bio_rev_slope = float(_slope(times, bio_rev)) if bio_rev else 0.0
    conv_rate = 0.0
    if len(times) >= 2 and flux:
        span = max(1e-9, times[-1] - times[0])
        conv_rate = max(0.0, (flux[-1] - flux[0]) / span)
    candidates = {
        "reversible_burden": max(0.0, worst_rev),
        "irreversible_accumulation": max(0.0, worst_irr),
        "information_debt": max(0.0, info_slope),
        "mutation_fixation": max(0.0, mut_slope),
        "niche_disorder": max(0.0, niche_slope),
    }
    wall = sorted(candidates, key=lambda k: (-candidates[k], k))[0]
    if max(candidates.values()) <= 0.0:
        wall = "none"
    return {
        "has_reversibility": True,
        "reversibility_model": "split_reversible_irreversible",
        "reversible_damage_final_by_component": {**rev_by_driver, **rev_by_organ},
        "irreversible_damage_final_by_component": {**irr_by_driver, **irr_by_organ},
        "reversible_damage_final": float(rev_burden[-1]) if rev_burden else 0.0,
        "irreversible_damage_final": float(irr_burden[-1]) if irr_burden else 0.0,
        "reversible_slope_after_adulthood": worst_rev,
        "irreversible_slope_after_adulthood": worst_irr,
        "worst_reversible_slope": worst_rev,
        "worst_irreversible_slope": worst_irr,
        "conversion_rate_by_component": conv_by_driver,
        "total_conversion_flux": float(flux[-1]) if flux else 0.0,
        "conversion_rate": float(conv_rate),
        "conversion_runaway_flag": bool(final.get("conversion_runaway", False)),
        "time_to_first_conversion_threshold": final.get("time_to_first_conversion_threshold"),
        "repair_ceiling": float(final.get("repair_ceiling", 0.0)),
        "repair_used_global": float(final.get("repair_used_global", 0.0)),
        "repair_remaining_min": float(min(remaining)) if remaining else 0.0,
        "repair_ceiling_usage_final": float(final.get("repair_used_global", 0.0)),
        "repair_ceiling_exhaustion_time": final.get("repair_ceiling_exhaustion_time"),
        "repair_cost_auc": float(final.get("repair_cost_auc", 0.0)),
        "repair_risk_auc": float(final.get("repair_risk_auc", 0.0)),
        "information_debt_final": float(info[-1]) if info else 0.0,
        "information_debt_slope": info_slope,
        "informational_continuity_min": float(min(
            float(r["systems"]["brain_cns"].get("informational_continuity", 1.0))
            for r in trajectory[1:])),
        "mutation_fixation_final": float(mut[-1]) if mut else 0.0,
        "mutation_fixation_slope": mut_slope,
        "mutation_ceiling_slack_min": float(max(
            0.0, 0.6 - (max(mut) if mut else 0.0))),
        "niche_disorder_final": float(niche[-1]) if niche else 0.0,
        "niche_disorder_slope": niche_slope,
        "entropy_production_final": float(entropy[-1]) if entropy else 0.0,
        "entropy_production_slope": entropy_slope,
        "entropy_production_auc": float(final.get("entropy_auc", 0.0)),
        "biological_age_reversibility": float(bio_rev[-1]) if bio_rev else 25.0,
        "biological_age_reversibility_slope": bio_rev_slope,
        "biological_age_floor_dynamic": float(floor[-1]) if floor else 25.0,
        "reversible_age_contribution": float(final.get("reversible_age_contribution", 0.0)),
        "irreversible_age_contribution": float(final.get("irreversible_age_contribution", 0.0)),
        "dominant_reversibility_wall": wall,
        "failed_ids": list(final.get("failed_ids", [])),
    }


def _reversibility_checks(trajectory: list[dict[str, Any]],
                          criteria: dict[str, float]) -> dict[str, bool]:
    from longevity.analysis.organ_network_metrics import validate_v4_criteria

    v4keys = ("eps_bio", "eps_bio_network", "eps_driver", "safety_margin", "min_allocation",
              "max_cancer_burden", "max_inflammation", "max_fibrosis", "min_neural_continuity",
              "min_organ_reserve", "max_cumulative_interventions")
    v4criteria = {k: criteria[k] for k in v4keys if k in criteria}
    validated_v4 = validate_v4_criteria(v4criteria)
    from longevity.analysis.organ_network_metrics import _network_checks  # reuse

    checks: dict[str, bool] = {}
    base = _network_checks(trajectory, validated_v4)
    # Map v4 network check names onto the v5 canonical set.
    rename = {"biological_age_network_slope": "biological_age_network_slope",
              "biological_age_slope": "biological_age_slope",
              "driver_slope": "driver_slope",
              "organ_function_margin": "organ_function_margin",
              "organ_reserve_exhaustion": "organ_reserve_exhaustion",
              "global_resource_shortage": "global_resource_shortage",
              "perfusion_budget": "perfusion_budget", "immune_budget": "immune_budget",
              "metabolic_budget": "metabolic_budget", "repair_budget": "repair_budget",
              "network_edge": "network_edge", "feedback_loop": "feedback_loop",
              "cascade_risk": "cascade_risk", "hard_limit": "hard_limit",
              "energy_budget": "energy_budget", "mutation_load": "mutation_fixation",
              "information_continuity": "information_debt",
              "cancer_burden": "cancer_burden", "inflammation": "inflammation",
              "fibrosis": "fibrosis", "intervention_cost": "intervention_cost",
              "systemic_cascade": "systemic_cascade"}
    for src, dst in rename.items():
        checks[dst] = base.get(src, False)
    summary = summarize_reversibility(trajectory, 0.25)
    if not summary.get("has_reversibility"):
        checks["biological_age_reversibility_slope"] = False
        checks["reversible_burden"] = False
        checks["irreversible_accumulation"] = True
        checks["conversion_runaway"] = False
        checks["repair_ceiling_exhaustion"] = True
        checks["information_debt"] = checks.get("information_debt", False)
        checks["mutation_fixation"] = checks.get("mutation_fixation", False)
        checks["niche_disorder"] = False
        checks["entropy_production"] = False
        return checks
    checks["biological_age_reversibility_slope"] = \
        summary["biological_age_reversibility_slope"] > criteria["eps_bio_rev"]
    checks["reversible_burden"] = summary["worst_reversible_slope"] > criteria["eps_reversible"]
    checks["irreversible_accumulation"] = summary["worst_irreversible_slope"] > criteria["eps_irreversible"]
    checks["conversion_runaway"] = bool(summary["conversion_runaway_flag"]) or \
        summary["conversion_rate"] > criteria["max_conversion_rate"]
    checks["repair_ceiling_exhaustion"] = summary["repair_remaining_min"] < criteria["min_repair_remaining"]
    checks["information_debt"] = summary["information_debt_slope"] > criteria["eps_information"] or \
        summary["information_debt_final"] > criteria["max_information_debt"]
    checks["mutation_fixation"] = summary["mutation_fixation_slope"] > criteria["eps_mutation"] or \
        summary["mutation_fixation_final"] > criteria["max_mutation_fixation"]
    checks["niche_disorder"] = summary["niche_disorder_slope"] > criteria["eps_niche"] or \
        summary["niche_disorder_final"] > criteria["max_niche_disorder"]
    adult = _adult_rows(trajectory)
    entropy = [float((row.get("reversibility") or {}).get("entropy_production", 0.0)) for row in adult
               if row.get("reversibility") is not None]
    checks["entropy_production"] = bool(entropy) and max(entropy) > 0.2
    return checks


def reversibility_binding(trajectory: list[dict[str, Any]],
                          criteria: dict[str, Any] | None = None) -> dict[str, Any]:
    """Reversibility binding analysis (pure, deterministic, non-mutating)."""
    criteria_v = validate_v5_criteria(criteria)
    if not trajectory or len(trajectory) < 2:
        raise ValueError("reversibility_binding of empty trajectory")
    checks = _reversibility_checks(trajectory, criteria_v)
    sequence = [c for c in REVERSIBILITY_BINDING_CONSTRAINTS if checks.get(c)]
    first = sequence[0] if sequence else "none"
    time_to_first: float | None = None
    if first != "none":
        for end in range(2, len(trajectory)):
            if _reversibility_checks(trajectory[:end + 1], criteria_v).get(first):
                time_to_first = float(trajectory[end]["chronological_age"])
                break
    summary = summarize_reversibility(trajectory, 0.25)
    from longevity.analysis.organ_network_metrics import network_binding

    try:
        legacy = network_binding(trajectory)
    except Exception:
        legacy = {}
    return {
        "first_reversibility_constraint_violated": first,
        "reversibility_binding_constraint_sequence": sequence,
        "time_to_first_reversibility_constraint_violation": time_to_first,
        "dominant_reversibility_wall": summary.get("dominant_reversibility_wall", "none"),
        "dominant_binding_level": _CONSTRAINT_TO_LEVEL.get(first, "none") if first != "none" else "none",
        "dominant_binding_organ": legacy.get("dominant_binding_organ", "none"),
        "dominant_binding_driver": legacy.get("dominant_binding_driver", "none"),
        "dominant_binding_resource": legacy.get("dominant_binding_resource", "none"),
        "dominant_binding_edge": legacy.get("dominant_binding_edge", "none"),
        "dominant_binding_loop": legacy.get("dominant_binding_loop", "none"),
        "dominant_binding_hard_limit": legacy.get("dominant_binding_hard_limit", "none"),
    }


def summarize_reversibility_run(trajectory: list[dict[str, Any]], dt: float = 0.25,
                                criteria: dict[str, Any] | None = None) -> dict[str, Any]:
    """Full reversibility per-run summary for runner merge (pure)."""
    validated = validate_v5_criteria(criteria)
    summary = summarize_reversibility(trajectory, dt)
    binding = reversibility_binding(trajectory, validated)
    final = trajectory[-1]
    rev_stats = ((final.get("reversibility") or {}).get("coordination_stats", {}))
    return {"reversibility": summary, "reversibility_binding": binding,
            "reversibility_coordination_stats": {k: rev_stats.get(k, 0) for k in (
                "preventive_priority_executions", "repair_ceiling_guard_rejections",
                "information_guard_rejections", "mutation_guard_rejections")}}


def robust_bounded_degradation_v5(summaries: list[dict[str, Any]],
                                  criteria: dict[str, Any] | None = None) -> dict[str, Any]:
    """Strict reversibility v5 verdict across seeds (pure).

    v4 conditions plus reversibility discipline. Missing reversibility
    blocks count as failures, never passes. Operational criterion only.
    """
    criteria_v = validate_v5_criteria(criteria)
    if not summaries:
        raise ValueError("robust_bounded_degradation_v5 of empty summaries")
    from longevity.analysis.organ_network_metrics import robust_bounded_degradation_v4

    v4 = robust_bounded_degradation_v4(summaries)
    per_run = []
    for summary in summaries:
        rev = summary.get("reversibility", {})
        if not rev.get("has_reversibility", False):
            per_run.append(False)
            continue
        ok = (
            float(summary.get("biological_age_slope_after_adulthood", 9e9)) <= criteria_v["eps_bio"]
            and float(summary.get("organ_network", {}).get("biological_age_network_slope", 9e9))
            <= criteria_v["eps_bio_network"]
            and float(rev.get("biological_age_reversibility_slope", 9e9)) <= criteria_v["eps_bio_rev"]
            and float(rev.get("worst_reversible_slope", 9e9)) <= criteria_v["eps_reversible"]
            and float(rev.get("worst_irreversible_slope", 9e9)) <= criteria_v["eps_irreversible"]
            and float(rev.get("information_debt_slope", 9e9)) <= criteria_v["eps_information"]
            and float(rev.get("mutation_fixation_slope", 9e9)) <= criteria_v["eps_mutation"]
            and float(rev.get("niche_disorder_slope", 9e9)) <= criteria_v["eps_niche"]
            and not rev.get("conversion_runaway_flag", True)
            and float(rev.get("conversion_rate", 9e9)) <= criteria_v["max_conversion_rate"]
            and float(rev.get("repair_remaining_min", -9e9)) >= criteria_v["min_repair_remaining"]
            and float(rev.get("information_debt_final", 9e9)) <= criteria_v["max_information_debt"]
            and float(rev.get("mutation_fixation_final", 9e9)) <= criteria_v["max_mutation_fixation"]
            and float(rev.get("niche_disorder_final", 9e9)) <= criteria_v["max_niche_disorder"]
            and summary.get("terminal_decline_reached", True) is False
        )
        per_run.append(bool(ok))
    success_rate = sum(per_run) / len(per_run)
    worst_bio = max(float(s.get("biological_age_slope_after_adulthood", 9e9)) for s in summaries)
    worst_bio_net = max(float(s.get("organ_network", {}).get("biological_age_network_slope", 9e9))
                         for s in summaries)
    worst_bio_rev = max(float(s.get("reversibility", {}).get("biological_age_reversibility_slope", 9e9))
                        for s in summaries)
    worst_rev = max(float(s.get("reversibility", {}).get("worst_reversible_slope", 9e9))
                    for s in summaries)
    worst_irr = max(float(s.get("reversibility", {}).get("worst_irreversible_slope", 9e9))
                    for s in summaries)
    worst_conv = max(float(s.get("reversibility", {}).get("conversion_rate", 9e9)) for s in summaries)
    worst_remaining = min(float(s.get("reversibility", {}).get("repair_remaining_min", 9e9))
                          for s in summaries)
    worst_info = max(float(s.get("reversibility", {}).get("information_debt_slope", 9e9))
                     for s in summaries)
    worst_mut = max(float(s.get("reversibility", {}).get("mutation_fixation_slope", 9e9))
                    for s in summaries)
    worst_niche = max(float(s.get("reversibility", {}).get("niche_disorder_slope", 9e9))
                      for s in summaries)
    worst_entropy = max(float(s.get("reversibility", {}).get("entropy_production_slope", 9e9))
                        for s in summaries)
    indicator = bool(
        success_rate >= criteria_v["min_success_rate"]
        and v4["robust_bounded_degradation_v4"]
        and all(per_run)
        and worst_bio <= criteria_v["eps_bio_worst"]
        and worst_bio_net <= criteria_v["eps_bio_network_worst"]
        and worst_bio_rev <= criteria_v["eps_bio_rev_worst"]
        and worst_irr <= criteria_v["eps_irreversible_worst"])
    return {
        "robust_bounded_degradation_v5": indicator,
        "success_rate_bounded_v5": success_rate,
        "worst_case_biological_age_slope": worst_bio,
        "worst_case_biological_age_network_slope": worst_bio_net,
        "worst_case_biological_age_reversibility_slope": worst_bio_rev,
        "worst_case_reversible_slope": worst_rev,
        "worst_case_irreversible_slope": worst_irr,
        "worst_case_conversion_rate": worst_conv,
        "worst_case_repair_ceiling_remaining": worst_remaining,
        "worst_case_information_debt_slope": worst_info,
        "worst_case_mutation_fixation_slope": worst_mut,
        "worst_case_niche_disorder_slope": worst_niche,
        "worst_case_entropy_production_slope": worst_entropy,
        "robust_v4": v4["robust_bounded_degradation_v4"],
        "n_runs": len(summaries),
    }
