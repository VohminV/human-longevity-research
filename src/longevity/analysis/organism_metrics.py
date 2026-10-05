"""ANALYSIS LAYER: organism life-course metrics (Stage 5A).

Pure functions over recorded organism trajectories (state snapshots, t0
first). Lifespan/healthspan follow docs/LONGEVITY.md; bounded degradation
is a MODEL indicator with an explicit epsilon, never immortality proof.
"""

from __future__ import annotations

import copy
import math

from typing import Any


def _finite(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number, got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{path} must be finite, got {value!r}")
    return result


def _slope(times: list[float], values: list[float]) -> float:
    """Least-squares slope; 0.0 when degenerate (pure)."""
    n = len(times)
    if n < 2:
        return 0.0
    mean_t = sum(times) / n
    mean_v = sum(values) / n
    denom = sum((t - mean_t) ** 2 for t in times)
    if denom <= 0.0:
        return 0.0
    return sum((t - mean_t) * (v - mean_v) for t, v in zip(times, values)) / denom


def _describe(values: list[float]) -> dict[str, Any]:
    finite = [_finite(v, "metric") for v in values]
    if not finite:
        raise ValueError("cannot describe empty data")
    ordered = sorted(finite)
    n = len(ordered)
    mean = sum(ordered) / n
    variance = sum((v - mean) ** 2 for v in ordered) / n
    return {"mean": mean, "std": math.sqrt(variance), "min": ordered[0],
            "max": ordered[-1], "count": n}


def compute_organism_summary(
    trajectory: list[dict[str, Any]],
    dt: float,
    thresholds: dict[str, float],
    epsilon: float = 0.01,
) -> dict[str, Any]:
    """Terminal + cumulative life-course metrics for one organism run (pure)."""
    if not trajectory:
        raise ValueError("organism trajectory must be non-empty")
    _finite(dt, "dt")
    initial = copy.deepcopy(trajectory[0])
    final = copy.deepcopy(trajectory[-1])
    death_age = float(final["death_time"]) if final.get("death_time") is not None else float(final["chronological_age"])
    lifespan = death_age
    healthy = [row for row in trajectory[1:]
               if all(float(info["function"]) >= thresholds["min_health_function"]
                      for info in row["systems"].values())]
    healthspan = len(healthy) * dt

    def _auc(key: str) -> float:
        return sum(float(row[key]) for row in trajectory[1:]) * dt

    adult_rows = [row for row in trajectory[1:]
                  if row["developmental_stage"] not in ("embryo", "fetal", "infancy", "childhood", "adolescence")]
    adult_times = [float(row["chronological_age"]) for row in adult_rows]
    bio_slope = _slope(adult_times, [float(row["biological_age"]) for row in adult_rows])
    damage_slope = _slope(adult_times, [float(row["global_damage"]) for row in adult_rows])

    systems: dict[str, Any] = {}
    for name in final["systems"]:
        functions = [float(row["systems"][name]["function"]) for row in trajectory[1:]]
        systems[name] = {
            "final_function": functions[-1] if functions else 0.0,
            "min_function": min(functions) if functions else 0.0,
            "time_to_failure": next(
                (float(row["chronological_age"]) for row in trajectory[1:]
                 if float(row["systems"][name]["function"])
                 < float(row["systems"][name]["failure_threshold"])),
                None),
        }
    brain_rows = [float(row["systems"]["brain_cns"].get("informational_continuity", 1.0)) for row in trajectory]
    rejuvenations = [r for r in final.get("intervention_history", []) if float(r.get("bio_delta", 0.0)) < -1e-9]
    max_rejuv = min([float(r["bio_delta"]) for r in rejuvenations]) if rejuvenations else 0.0
    from longevity.analysis.aging_metrics import summarize_drivers  # local: analysis-layer reuse

    drivers = summarize_drivers(trajectory)

    critical_ok = all(
        float(final["systems"][name]["function"]) >= float(final["systems"][name]["failure_threshold"])
        for name in final["systems"] if final["systems"][name]["critical"])
    bounded = bool(
        final["alive"]
        and bio_slope <= epsilon
        and damage_slope <= epsilon
        and critical_ok
        and float(final["cancer_burden"]) <= 0.5
        and float(final["inflammation"]) <= 0.5
        and float(final["fibrosis"]) <= 0.5,
    )
    return {
        "lifespan": float(lifespan),
        "healthspan": float(healthspan),
        "healthspan_fraction": float(healthspan / lifespan) if lifespan > 0 else 0.0,
        "death_time": final.get("death_time"),
        "alive_at_end": bool(final["alive"]),
        "primary_cause_of_death": final.get("failure_cause", "none"),
        "final_biological_age": float(final["biological_age"]),
        "final_chronological_age": float(final["chronological_age"]),
        "biological_age_slope_after_adulthood": float(bio_slope),
        "damage_slope_after_adulthood": float(damage_slope),
        "bounded_degradation_indicator": bounded,
        "bounded_degradation_epsilon": float(epsilon),
        "functional_reserve_area": _auc("functional_reserve"),
        "vitality_auc": sum(float(row["vitality_index"]) for row in trajectory[1:]) * dt,
        "damage_auc": _auc("global_damage"),
        "senescence_auc": _auc("senescence_burden"),
        "inflammation_auc": _auc("inflammation"),
        "fibrosis_auc": _auc("fibrosis"),
        "cancer_auc": _auc("cancer_burden"),
        "epigenetic_drift_auc": _auc("epigenetic_drift"),
        "final_function_by_system": {name: info["final_function"] for name, info in systems.items()},
        "min_function_by_system": {name: info["min_function"] for name, info in systems.items()},
        "time_to_system_failure_by_system": {name: info["time_to_failure"] for name, info in systems.items()},
        "neural_identity_preservation": float(brain_rows[-1]) if brain_rows else 1.0,
        "informational_continuity_min": float(min(brain_rows)) if brain_rows else 1.0,
        "informational_continuity_final": float(brain_rows[-1]) if brain_rows else 1.0,
        "rejuvenation_events": int(final.get("rejuvenation_events", 0)),
        "max_rejuvenation_delta": float(max_rejuv),
        "n_interventions": len(final.get("intervention_history", [])),
        "n_snapshots": len(trajectory),
        "terminal_decline_reached": any(row["developmental_stage"] == "terminal_decline" for row in trajectory),
        "drivers": drivers,
    }


def compare_against_baseline(intervention_summary: dict[str, Any],
                             baseline_summary: dict[str, Any]) -> dict[str, Any]:
    """Same-seed baseline comparison (pure; LOCAL organism deltas)."""
    return {
        "lifespan_gain": float(intervention_summary["lifespan"]) - float(baseline_summary["lifespan"]),
        "healthspan_gain": float(intervention_summary["healthspan"]) - float(baseline_summary["healthspan"]),
        "damage_auc_delta": float(baseline_summary["damage_auc"]) - float(intervention_summary["damage_auc"]),
        "cancer_auc_delta": float(baseline_summary["cancer_auc"]) - float(intervention_summary["cancer_auc"]),
    }


DEFAULT_FITNESS_WEIGHTS: dict[str, float] = {
    "w_lifespan": 1.0,
    "w_healthspan": 2.0,
    "w_reserve": 0.5,
    "w_damage": 1.0,
    "w_cancer": 3.0,
    "w_inflammation": 1.0,
    "w_neural_loss": 5.0,
    "w_bounded_bonus": 10.0,
    "w_std_penalty": 0.0,
    "w_worst_penalty": 0.0,
    "w_driver_slope": 0.0,
    "w_bounded_v2_bonus": 0.0,
    "w_organ_slope": 0.0,
    "w_resource_shortfall": 0.0,
    "w_bounded_v3_bonus": 0.0,
    # Stage 6B network weights (all 0.0 by default: legacy fitness unchanged).
    "w_fibrosis": 0.0,
    "w_feedback_runaway": 0.0,
    "w_cascade_risk": 0.0,
    "w_mutation_load": 0.0,
    "w_energy_shortfall": 0.0,
    "w_bounded_v4_bonus": 0.0,
    # Stage 6C reversibility weights (all 0.0 by default: legacy fitness unchanged).
    "w_irreversible_slope": 0.0,
    "w_conversion_runaway": 0.0,
    "w_repair_ceiling_exhaustion": 0.0,
    "w_information_debt": 0.0,
    "w_niche_disorder": 0.0,
    "w_entropy_production": 0.0,
    "w_bounded_v5_bonus": 0.0,
}


def validate_fitness_weights(weights: dict[str, Any]) -> dict[str, float]:
    """Validate fitness weights (all finite, >= 0)."""
    if not isinstance(weights, dict):
        raise ValueError("fitness weights must be a dict")
    merged = dict(DEFAULT_FITNESS_WEIGHTS)
    merged.update(weights)
    unknown = set(merged) - set(DEFAULT_FITNESS_WEIGHTS)
    if unknown:
        raise ValueError(f"unknown fitness weight keys: {sorted(unknown)}")
    validated = {}
    for key in DEFAULT_FITNESS_WEIGHTS:
        value = merged[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"fitness weight {key} must be finite, got {value!r}")
        if float(value) < 0.0:
            raise ValueError(f"fitness weight {key} must be >= 0, got {value!r}")
        validated[key] = float(value)
    return validated


def fitness(summary: dict[str, Any], weights: dict[str, float]) -> float:
    """Multi-objective fitness: lifespan/healthspan gains minus burden costs."""
    w = validate_fitness_weights(dict(weights))
    network = summary.get("organ_network", {})
    base = (
        w["w_lifespan"] * float(summary["lifespan"])
        + w["w_healthspan"] * float(summary["healthspan"])
        + w["w_reserve"] * float(summary["functional_reserve_area"])
        - w["w_damage"] * float(summary["damage_auc"])
        - w["w_cancer"] * float(summary["cancer_auc"])
        - w["w_inflammation"] * float(summary["inflammation_auc"])
        - w["w_neural_loss"] * (1.0 - float(summary["neural_identity_preservation"]))
        + w["w_bounded_bonus"] * (1.0 if summary["bounded_degradation_indicator"] else 0.0)
    )
    if not network.get("has_network", False):
        return base
    reversibility = summary.get("reversibility", {})
    extra = (
        base
        - w["w_fibrosis"] * float(summary.get("fibrosis_auc", 0.0))
        - w["w_feedback_runaway"] * float(network.get("worst_feedback_gain", 0.0))
        - w["w_cascade_risk"] * float(network.get("max_cascade_risk", 0.0))
        - w["w_mutation_load"] * float(network.get("max_mutation_load", 0.0))
        - w["w_energy_shortfall"] * max(
            0.0, 30.0 - float(network.get("min_energy_budget", 30.0)))
        + w["w_bounded_v4_bonus"] * 0.0  # v4 bonus applied at search level (needs multi-seed)
    )
    if not reversibility.get("has_reversibility", False):
        return extra
    return (
        extra
        - w["w_irreversible_slope"] * float(reversibility.get("worst_irreversible_slope", 0.0))
        - w["w_conversion_runaway"] * float(reversibility.get("conversion_rate", 0.0))
        - w["w_repair_ceiling_exhaustion"] * max(
            0.0, float(reversibility.get("repair_ceiling", 0.0))
            - float(reversibility.get("repair_remaining_min", 0.0)))
        - w["w_information_debt"] * float(reversibility.get("information_debt_final", 0.0))
        - w["w_niche_disorder"] * float(reversibility.get("niche_disorder_final", 0.0))
        - w["w_entropy_production"] * float(reversibility.get("entropy_production_final", 0.0))
        + w["w_bounded_v5_bonus"] * 0.0  # v5 bonus applied at search level (needs multi-seed)
    )


def robust_fitness(seed_summaries: list[dict[str, Any]], weights: dict[str, float]) -> dict[str, Any]:
    """Robust fitness across seeds: mean minus variance/worst-case penalties.

    With default zero penalties this equals mean per-seed fitness, so plain
    Stage 5A searches are unaffected.
    """
    w = validate_fitness_weights(dict(weights))
    if not seed_summaries:
        raise ValueError("robust_fitness of empty summaries")
    values = [fitness(summary, w) for summary in seed_summaries]
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = math.sqrt(variance)
    worst = min(values)
    robust = mean - w["w_std_penalty"] * std - w["w_worst_penalty"] * max(0.0, mean - worst)
    return {"fitness_mean": mean, "fitness_std": std, "fitness_min": worst,
            "robust_fitness": robust}


def pareto_frontier(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Non-dominated candidates on (lifespan, healthspan, -cancer_auc) (pure)."""
    frontier = []
    for candidate in candidates:
        dominated = False
        for other in candidates:
            if other is candidate:
                continue
            if (other["lifespan"] >= candidate["lifespan"]
                    and other["healthspan"] >= candidate["healthspan"]
                    and other["cancer_auc"] <= candidate["cancer_auc"]
                    and (other["lifespan"] > candidate["lifespan"]
                         or other["healthspan"] > candidate["healthspan"]
                         or other["cancer_auc"] < candidate["cancer_auc"])):
                dominated = True
                break
        if not dominated:
            frontier.append(candidate)
    return frontier


def aggregate_summaries(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    """Descriptive aggregates over seed summaries (pure, no inference)."""
    if not summaries:
        raise ValueError("aggregate_summaries of empty data")
    numeric_keys = ("lifespan", "healthspan", "damage_auc", "cancer_auc",
                    "functional_reserve_area", "biological_age_slope_after_adulthood")
    aggregated = {key: _describe([float(s[key]) for s in summaries]) for key in numeric_keys}
    causes: dict[str, int] = {}
    for summary in summaries:
        causes[summary["primary_cause_of_death"]] = causes.get(summary["primary_cause_of_death"], 0) + 1
    aggregated["primary_cause_counts"] = causes
    aggregated["bounded_count"] = sum(1 for s in summaries if s["bounded_degradation_indicator"])
    aggregated["n_runs"] = len(summaries)
    return aggregated


# ---------------------------------------------------------------------------
# Stage 5B: rolling windows, robust bounded degradation, binding constraints.
# ---------------------------------------------------------------------------

def rolling_slopes(trajectory: list[dict[str, Any]], window_years: float) -> list[dict[str, Any]]:
    """Rolling-window slopes of bio-age/damage/cancer/inflammation (pure).

    Windows end at each snapshot with at least ``window_years`` of history;
    pre-adult rows are excluded so development never masks late divergence.
    """
    if not trajectory:
        raise ValueError("rolling_slopes of empty trajectory")
    adult = [row for row in trajectory[1:]
             if row["developmental_stage"] not in ("embryo", "fetal", "infancy", "childhood", "adolescence")]
    rows = []
    for index, row in enumerate(adult):
        end = float(row["chronological_age"])
        window = [r for r in adult[:index + 1] if end - float(r["chronological_age"]) <= window_years + 1e-9]
        if len(window) < 2:
            continue
        times = [float(r["chronological_age"]) for r in window]
        rows.append({
            "age": end,
            "biological_age_slope": _slope(times, [float(r["biological_age"]) for r in window]),
            "damage_slope": _slope(times, [float(r["global_damage"]) for r in window]),
            "cancer_burden": float(row["cancer_burden"]),
            "inflammation": float(row["inflammation"]),
            "fibrosis": float(row["fibrosis"]),
            "informational_continuity": float(row["systems"]["brain_cns"].get("informational_continuity", 1.0)),
            "min_critical_function": min(float(row["systems"][name]["function"]) for name in row["systems"]
                                         if row["systems"][name]["critical"]),
        })
    return rows


DEFAULT_ROBUST_CRITERIA: dict[str, Any] = {
    "burn_in_years": 5.0,
    "evaluation_window_years": 25.0,
    "eps_bio": 0.05,
    "eps_damage": 0.005,
    "safety_margin": 0.05,
    "max_cancer_burden": 0.5,
    "max_inflammation": 0.5,
    "max_fibrosis": 0.5,
    "min_neural_continuity": 0.6,
    "min_success_rate": 0.8,
    "eps_bio_worst": 0.1,
    "eps_damage_worst": 0.01,
}


def validate_robust_criteria(criteria: dict[str, Any] | None) -> dict[str, Any]:
    """Validate robust bounded-degradation criteria (all neutral by default)."""
    merged = dict(DEFAULT_ROBUST_CRITERIA)
    merged.update(criteria or {})
    unknown = set(merged) - set(DEFAULT_ROBUST_CRITERIA)
    if unknown:
        raise ValueError(f"unknown robust criteria keys: {sorted(unknown)}")
    validated: dict[str, Any] = {}
    for key, value in merged.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"robust criteria.{key} must be finite, got {value!r}")
        if float(value) < 0.0 or (key == "min_success_rate" and float(value) > 1.0):
            raise ValueError(f"robust criteria.{key} out of range, got {value!r}")
        validated[key] = float(value)
    return validated


def _robust_row_checks(row: dict[str, Any], criteria: dict[str, float]) -> list[str]:
    """Constraint violations of one window row, canonical order (pure)."""
    failed = []
    if row["biological_age_slope"] > criteria["eps_bio"]:
        failed.append("biological_age_slope")
    if row["damage_slope"] > criteria["eps_damage"]:
        failed.append("damage_slope")
    # Critical functions must hold failure_threshold (0.25) plus margin.
    if row["min_critical_function"] < 0.25 + criteria["safety_margin"]:
        failed.append("critical_function_margin")
    if row["cancer_burden"] > criteria["max_cancer_burden"]:
        failed.append("cancer_burden")
    if row["inflammation"] > criteria["max_inflammation"]:
        failed.append("inflammation")
    if row["fibrosis"] > criteria["max_fibrosis"]:
        failed.append("fibrosis")
    if row["informational_continuity"] < criteria["min_neural_continuity"]:
        failed.append("neural_continuity")
    return failed


def binding_constraints(trajectory: list[dict[str, Any]], criteria: dict[str, Any] | None = None) -> dict[str, Any]:
    """First-violated robust constraints over a trajectory (pure, non-mutating).

    Scans rolling 25-year windows after a burn-in past adulthood; returns
    the first violated constraint, the full ordered sequence, and timing.
    ``"none"`` when the whole evaluation window holds.
    """
    criteria = validate_robust_criteria(criteria)
    windows = rolling_slopes(trajectory, criteria["evaluation_window_years"])
    adult_start = next((float(r["chronological_age"]) for r in trajectory[1:]
                        if r["developmental_stage"] not in ("embryo", "fetal", "infancy", "childhood", "adolescence")),
                       0.0)
    sequence: list[str] = []
    first_time: float | None = None
    first_constraint = "none"
    for row in windows:
        if row["age"] < adult_start + criteria["burn_in_years"]:
            continue
        for constraint in _robust_row_checks(row, criteria):
            if constraint not in sequence:
                sequence.append(constraint)
            if first_time is None:
                first_time = row["age"]
                first_constraint = constraint
    return {
        "first_constraint_violated": first_constraint,
        "binding_constraint_sequence": sequence,
        "time_to_first_constraint_violation": first_time,
        "n_windows_evaluated": len([r for r in windows if r["age"] >= adult_start + criteria["burn_in_years"]]),
    }


def robust_bounded_degradation(summaries: list[dict[str, Any]], trajectories: list[list[dict[str, Any]]] | None = None,
                               criteria: dict[str, Any] | None = None) -> dict[str, Any]:
    """Robust bounded-degradation verdict across seeds (pure, Stage 5B).

    Requires per-run bounded flags at ``min_success_rate`` plus worst-case
    slope discipline; with trajectories, every run must additionally hold
    every robust window (no late divergence). Operational criterion only.
    """
    criteria = validate_robust_criteria(criteria)
    if not summaries:
        raise ValueError("robust_bounded_degradation of empty summaries")
    n = len(summaries)
    success_rate = sum(1 for s in summaries if s["bounded_degradation_indicator"]) / n
    worst_bio = max(float(s["biological_age_slope_after_adulthood"]) for s in summaries)
    worst_damage = max(float(s["damage_slope_after_adulthood"]) for s in summaries)
    worst_cancer = max(float(s.get("cancer_auc", 0.0)) / max(1.0, float(s.get("lifespan", 1.0))) for s in summaries)
    window_ok: bool | None = None
    if trajectories is not None:
        if len(trajectories) != n:
            raise ValueError("trajectories must match summaries one-to-one")
        window_ok = True
        for trajectory in trajectories:
            binding = binding_constraints(trajectory, criteria)
            if binding["first_constraint_violated"] != "none":
                window_ok = False
                break
    indicator = bool(
        success_rate >= criteria["min_success_rate"]
        and worst_bio <= criteria["eps_bio_worst"]
        and worst_damage <= criteria["eps_damage_worst"]
        and (window_ok is not False)
    )
    return {
        "robust_bounded_degradation_indicator": indicator,
        "success_rate_bounded": success_rate,
        "worst_case_biological_age_slope": worst_bio,
        "worst_case_damage_slope": worst_damage,
        "worst_case_mean_cancer_burden": worst_cancer,
        "window_check_passed": window_ok,
        "n_runs": n,
    }


def robust_aggregate(summaries: list[dict[str, Any]], trajectories: list[list[dict[str, Any]]] | None = None,
                     criteria: dict[str, Any] | None = None) -> dict[str, Any]:
    """Full robust aggregation per policy/scenario (pure, Stage 5B)."""
    base = aggregate_summaries(summaries)
    robust = robust_bounded_degradation(summaries, trajectories, criteria)
    base["robust"] = robust
    base["median_lifespan"] = sorted(float(s["lifespan"]) for s in summaries)[len(summaries) // 2]
    base["median_healthspan"] = sorted(float(s["healthspan"]) for s in summaries)[len(summaries) // 2]
    base["min_lifespan"] = min(float(s["lifespan"]) for s in summaries)
    base["max_lifespan"] = max(float(s["lifespan"]) for s in summaries)
    base["min_healthspan"] = min(float(s["healthspan"]) for s in summaries)
    base["max_healthspan"] = max(float(s["healthspan"]) for s in summaries)
    base["worst_case_biological_age_slope"] = robust["worst_case_biological_age_slope"]
    base["worst_case_damage_slope"] = robust["worst_case_damage_slope"]
    base["max_cancer_burden"] = max(float(s.get("cancer_auc", 0.0)) for s in summaries)
    base["min_informational_continuity"] = min(float(s.get("informational_continuity_min", 1.0)) for s in summaries)
    binding_counts: dict[str, int] = {}
    if trajectories is not None:
        for trajectory in trajectories:
            binding = binding_constraints(trajectory, criteria)
            key = binding["first_constraint_violated"]
            binding_counts[key] = binding_counts.get(key, 0) + 1
    base["binding_constraint_distribution"] = binding_counts
    return base
