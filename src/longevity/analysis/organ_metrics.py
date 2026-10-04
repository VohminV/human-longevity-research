"""ANALYSIS LAYER: abstract-organ experiment metrics (Stage 4A).

Pure functions over recorded organ trajectories (lists of organ snapshots,
t0 first). No simulation here, no I/O, no global state. All functions are
deterministic and never mutate their inputs. Every number is a LOCAL
model-internal proxy (see docs/ORGAN_MODEL.md), never a biological claim.
"""

from __future__ import annotations

import copy
import math

from typing import Any


def _require_finite(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number, got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{path} must be finite, got {value!r}")
    return result


def compute_organ_summary(
    trajectory: list[dict[str, Any]],
    dt: float,
    duration_time: float,
    thresholds: dict[str, float],
) -> dict[str, Any]:
    """Terminal + cumulative metrics for one organ run (pure).

    Covers organ vitals, per-tissue finals, resource allocation stats and
    organ failure causality (via
    :func:`longevity.model.organ.organ_failure_causality`, trajectory-only).
    """
    from longevity.model.organ import organ_failure_causality  # local: model-layer reuse

    if not trajectory:
        raise ValueError("organ trajectory must be non-empty")
    _require_finite(dt, "dt")
    initial = copy.deepcopy(trajectory[0])
    final = copy.deepcopy(trajectory[-1])

    causality = organ_failure_causality(trajectory, dict(thresholds))
    # First organ viability break (duration when the organ never breaks).
    first_failure = duration_time
    for snapshot in trajectory:
        if not snapshot.get("organ_viable", True):
            first_failure = float(snapshot["time"])
            break
    n_post = max(0, len(trajectory) - 1)
    healthspan = sum(1 for row in trajectory[1:] if row.get("organ_viable", True)) * dt

    vascular_ratios = [_require_finite(row["vascular_allocation_ratio"], "vascular_allocation_ratio") for row in trajectory]
    immune_ratios = [_require_finite(row["immune_allocation_ratio"], "immune_allocation_ratio") for row in trajectory]
    worst = [min(v, i) for v, i in zip(vascular_ratios, immune_ratios)]

    tissues: dict[str, Any] = {}
    for tid, info in final["tissues"].items():
        state = info["state"]
        living = float(state["functional_cells"]) + float(state["damaged_cells"]) + float(state["senescent_cells"])
        tissues[tid] = {
            "role": info["role"],
            "is_vital": bool(info["is_vital"]),
            "tissue_function": _require_finite(info["tissue_function"], f"tissues.{tid}.tissue_function"),
            "final_functional_cells": float(state["functional_cells"]),
            "final_senescent_cells": float(state["senescent_cells"]),
            "senescent_fraction": (float(state["senescent_cells"]) / living if living > 0.0 else 0.0),
            "stem_fraction": None,  # filled below when the initial pool is known
            "final_stem_cells": float(state["stem_cells"]),
            "final_ecm_quality": float(state["ecm_quality"]),
            "final_vascular_quality": float(state["vascular_quality"]),
            "final_immune_pressure": float(state["immune_pressure"]),
            "final_cancer_risk": float(state["cancer_risk"]),
            "final_fibrosis_index": float(state["fibrosis_index"]),
            "replacement_events": int(info["replacement_events"]),
            "total_replaced_cells": float(info["total_replaced_cells"]),
        }
        initial_state = initial["tissues"][tid]["state"]
        initial_stem = float(initial_state["stem_cells"])
        tissues[tid]["initial_stem_cells"] = initial_stem
        tissues[tid]["stem_fraction"] = (float(state["stem_cells"]) / initial_stem if initial_stem > 0.0 else 1.0)

    # Most frequent bottleneck over the run (post-t0 snapshots).
    bottleneck_votes: dict[str, int] = {}
    for row in trajectory[1:]:
        name = str(row["bottleneck_tissue"])
        bottleneck_votes[name] = bottleneck_votes.get(name, 0) + 1
    most_frequent = None
    if bottleneck_votes:
        most_frequent = sorted(bottleneck_votes, key=lambda tid: (-bottleneck_votes[tid], tid))[0]

    summary: dict[str, Any] = {
        "final_organ_function": _require_finite(final["organ_function"], "organ_function"),
        "initial_organ_function": _require_finite(initial["organ_function"], "organ_function"),
        "organ_rejuvenation_delta": float(final["organ_function"]) - float(initial["organ_function"]),
        "time_to_organ_viability_failure": float(first_failure),
        "organ_healthspan_proxy": float(healthspan),
        "organ_survival_time": float(first_failure),
        "bottleneck_tissue_final": str(final["bottleneck_tissue"]),
        "bottleneck_tissue_most_frequent": most_frequent,
        "final_organ_cancer_risk": float(final["organ_cancer_risk"]),
        "final_organ_fibrosis_index": float(final["organ_fibrosis_index"]),
        "mean_vascular_allocation_ratio": sum(vascular_ratios) / len(vascular_ratios),
        "min_vascular_allocation_ratio": min(vascular_ratios),
        "mean_immune_allocation_ratio": sum(immune_ratios) / len(immune_ratios),
        "min_immune_allocation_ratio": min(immune_ratios),
        "vascular_shortfall_auc": sum(float(row["vascular_shortfall"]) for row in trajectory) * dt,
        "immune_shortfall_auc": sum(float(row["immune_shortfall"]) for row in trajectory) * dt,
        "mean_min_allocation_ratio": sum(worst) / len(worst),
        "resource_contention_index": 1.0 - sum(worst) / len(worst),
        "tissues": tissues,
        "n_snapshots": len(trajectory),
        "n_steps": n_post,
    }
    summary.update(
        {
            "primary_organ_failure_cause": causality["primary_organ_failure_cause"],
            "organ_failure_cause_sequence": list(causality["organ_failure_cause_sequence"]),
            **{k: v for k, v in causality.items() if k.startswith("first_")},
        }
    )
    coordination = summarize_coordination(trajectory, dt)
    total_executed_cells = sum(float(info["total_replaced_cells"]) for info in tissues.values())
    coordination["total_executed_replaced_cells"] = float(total_executed_cells)
    coordination["demand_relief_per_executed_replacement"] = (
        coordination["total_relief_cells"] / total_executed_cells if total_executed_cells > 0.0 else 0.0
    )
    summary["coordination"] = coordination
    summary["temporal"] = summarize_temporal(trajectory)
    summary["recovery"] = summarize_recovery(trajectory, dt)
    summary["capacity"] = summarize_capacity(trajectory, dt)
    return summary


def _recovery_detail(row: dict[str, Any]) -> dict[str, Any]:
    """Per-step recovery detail (tolerates pre-4D trajectories)."""
    detail = row.get("recovery_detail") or {}
    return {
        "model": str(detail.get("recovery_model", "unknown")),
        "planned": list(detail.get("recovery_planned", [])),
        "executed": list(detail.get("recovery_executed", [])),
        "from_deferral": list(detail.get("recovery_executed_from_deferral", [])),
        "deferred": list(detail.get("recovery_deferred", [])),
        "rejected": list(detail.get("recovery_rejected", [])),
        "expired": list(detail.get("recovery_expired", [])),
        "merged": int(detail.get("recovery_merged", 0)),
        "immediate_immune": float(detail.get("recovery_immediate_immune", 0.0)),
        "immediate_vascular": float(detail.get("recovery_immediate_vascular", 0.0)),
    }


def summarize_recovery(trajectory: list[dict[str, Any]], dt: float) -> dict[str, Any]:
    """Recovery execution stats over an organ trajectory (pure, Stage 4D).

    Pre-4D trajectories yield neutral zeros with model ``"unknown"``.
    """
    if not trajectory:
        raise ValueError("organ trajectory must be non-empty")
    models = {_recovery_detail(row)["model"] for row in trajectory[1:]}
    models.discard("unknown")
    model = sorted(models)[0] if len(models) == 1 else ("mixed" if models else "unknown")
    planned = sum(len(_recovery_detail(row)["planned"]) for row in trajectory[1:])
    executed = sum(len(_recovery_detail(row)["executed"]) for row in trajectory[1:])
    from_deferral = sum(len(_recovery_detail(row)["from_deferral"]) for row in trajectory[1:])
    deferred = sum(len(_recovery_detail(row)["deferred"]) for row in trajectory[1:])
    rejected = sum(len(_recovery_detail(row)["rejected"]) for row in trajectory[1:])
    expired = sum(len(_recovery_detail(row)["expired"]) for row in trajectory[1:])
    merged = sum(_recovery_detail(row)["merged"] for row in trajectory[1:])
    immediate_immune = sum(_recovery_detail(row)["immediate_immune"] for row in trajectory[1:])
    immediate_vascular = sum(_recovery_detail(row)["immediate_vascular"] for row in trajectory[1:])
    cumulative = ((trajectory[-1].get("recovery_detail") or {}).get("cumulative") or {})
    created = float(cumulative.get("capacity_increase_created", 0.0))
    realized = float(cumulative.get("capacity_increase_realized", 0.0))
    return {
        "recovery_model": model,
        "total_recovery_planned": int(planned),
        "total_recovery_executed": int(executed),
        "total_recovery_deferred": int(deferred),
        "total_recovery_expired": int(expired),
        "total_recovery_rejected": int(rejected),
        "total_recovery_merged": int(merged),
        "executed_after_deferral_recovery": int(from_deferral),
        "total_recovery_immediate_immune_cost": float(immediate_immune),
        "total_recovery_immediate_vascular_cost": float(immediate_vascular),
        "execution_fraction_recovery": (executed / planned) if planned else 1.0,
        "total_capacity_increase_created": created,
        "total_capacity_increase_realized": realized,
        "capacity_increase_realization_ratio": (realized / created) if created > 0.0 else 0.0,
    }


def summarize_capacity(trajectory: list[dict[str, Any]], dt: float) -> dict[str, Any]:
    """Dynamic-capacity stats over an organ trajectory (pure, Stage 4D).

    Static-capacity (pre-4D) trajectories report flat series with zero
    degradation AUCs.
    """
    if not trajectory:
        raise ValueError("organ trajectory must be non-empty")
    vascular = [float(row.get("current_vascular_capacity", row.get("initial_vascular_capacity", 0.0))) for row in trajectory]
    immune = [float(row.get("current_immune_capacity", row.get("initial_immune_capacity", 0.0))) for row in trajectory]
    initial_v = vascular[0] if vascular else 0.0
    initial_i = immune[0] if immune else 0.0
    return {
        "initial_vascular_capacity": float(initial_v),
        "initial_immune_capacity": float(initial_i),
        "final_vascular_capacity": float(vascular[-1]) if vascular else 0.0,
        "final_immune_capacity": float(immune[-1]) if immune else 0.0,
        "min_vascular_capacity": float(min(vascular)) if vascular else 0.0,
        "min_immune_capacity": float(min(immune)) if immune else 0.0,
        "mean_vascular_capacity": float(sum(vascular) / len(vascular)) if vascular else 0.0,
        "mean_immune_capacity": float(sum(immune) / len(immune)) if immune else 0.0,
        "vascular_capacity_degradation_auc": float(sum(max(0.0, initial_v - v) for v in vascular)) * float(dt),
        "immune_capacity_degradation_auc": float(sum(max(0.0, initial_i - v) for v in immune)) * float(dt),
    }


def _temporal_detail(row: dict[str, Any]) -> dict[str, Any]:
    """Per-step temporal detail (tolerates pre-4C trajectories)."""
    detail = row.get("temporal_detail") or {}
    return {
        "model": str(detail.get("temporal_model", "unknown")),
        "spike_immune": float(detail.get("spike_immune", 0.0)),
        "spike_vascular": float(detail.get("spike_vascular", 0.0)),
        "relief_created": float(detail.get("relief_created_immune", 0.0))
        + float(detail.get("relief_created_vascular", 0.0)),
        "relief_active": float(detail.get("relief_active_immune", 0.0))
        + float(detail.get("relief_active_vascular", 0.0)),
        "deferred": list(detail.get("deferred_now", [])),
        "from_deferral": dict(detail.get("executed_from_deferral", {})),
        "delays": dict(detail.get("defer_delays", {})),
        "expired": list(detail.get("expired_now", [])),
        "queue_length": int(detail.get("queue_length", 0)),
    }


def summarize_temporal(trajectory: list[dict[str, Any]]) -> dict[str, Any]:
    """Immediate-cost / delayed-relief / deferral stats (pure, Stage 4C).

    Aggregates per-step temporal records plus the cumulative model totals
    carried on the final snapshot. Pre-4C trajectories yield neutral zeros
    with model ``"unknown"`` instead of an error.
    """
    if not trajectory:
        raise ValueError("organ trajectory must be non-empty")
    models = {_temporal_detail(row)["model"] for row in trajectory[1:]}
    models.discard("unknown")
    model = sorted(models)[0] if len(models) == 1 else ("mixed" if models else "unknown")
    spike_i = [_temporal_detail(row)["spike_immune"] for row in trajectory[1:]]
    spike_v = [_temporal_detail(row)["spike_vascular"] for row in trajectory[1:]]
    spike_steps = [i for i, (a, b) in enumerate(zip(spike_i, spike_v)) if a > 0.0 or b > 0.0]
    immune_ratios = [float(row["immune_allocation_ratio"]) for row in trajectory[1:]]
    vascular_ratios = [float(row["vascular_allocation_ratio"]) for row in trajectory[1:]]
    # Cumulative event totals ride on the final snapshot (written by the
    # model each step); per-step series give peaks, AUCs and deferral means.
    cumulative = ((trajectory[-1].get("temporal_detail") or {}).get("cumulative") or {})
    created_events = int(cumulative.get("relief_created_events", 0))
    created_amount = float(cumulative.get("relief_created_amount", 0.0))
    realized_events = int(cumulative.get("relief_realized_events", 0))
    realized_amount = float(cumulative.get("relief_realized_amount", 0.0))
    expired_events = int(cumulative.get("relief_expired_events", 0))
    expired_amount = float(cumulative.get("relief_expired_amount", 0.0))
    deferred_total = sum(len(_temporal_detail(row)["deferred"]) for row in trajectory[1:])
    expired_total = sum(len(_temporal_detail(row)["expired"]) for row in trajectory[1:])
    from_deferral_total = sum(
        1 for row in trajectory[1:] for flag in _temporal_detail(row)["from_deferral"].values() if flag
    )
    delays = [float(v) for row in trajectory[1:] for v in _temporal_detail(row)["delays"].values()]
    max_queue = max([_temporal_detail(row)["queue_length"] for row in trajectory] + [0])
    active_last = _temporal_detail(trajectory[-1])["relief_active"]
    return {
        "temporal_relief_model": model,
        "total_immediate_immune_cost": float(sum(spike_i)),
        "total_immediate_vascular_cost": float(sum(spike_v)),
        "peak_immediate_immune_demand": float(max(spike_i)) if spike_i else 0.0,
        "peak_immediate_vascular_demand": float(max(spike_v)) if spike_v else 0.0,
        "min_immune_allocation_during_spike": (
            float(min(immune_ratios[i] for i in spike_steps)) if spike_steps else None
        ),
        "min_vascular_allocation_during_spike": (
            float(min(vascular_ratios[i] for i in spike_steps)) if spike_steps else None
        ),
        "total_delayed_relief_created_events": int(created_events),
        "total_delayed_relief_created": float(created_amount),
        "total_delayed_relief_realized_events": int(realized_events),
        "total_delayed_relief_realized": float(realized_amount),
        "total_delayed_relief_expired_events": int(expired_events),
        "total_delayed_relief_expired": float(expired_amount),
        "relief_realization_ratio": (realized_amount / created_amount) if created_amount > 0.0 else 0.0,
        "relief_active_at_end": float(active_last),
        "deferred_plan_count": int(deferred_total),
        "executed_after_deferral_count": int(from_deferral_total),
        "expired_deferred_plan_count": int(expired_total),
        "rejected_after_deferral_count": 0,
        "mean_defer_steps": (sum(delays) / len(delays)) if delays else None,
        "max_defer_queue_length": int(max_queue),
    }


def _detail(row: dict[str, Any]) -> dict[str, Any]:
    """Per-step coordination detail (tolerates Stage 4A trajectories)."""
    detail = row.get("coordination_detail") or {}
    return {
        "mode": str(detail.get("mode", "unknown")),
        "executed": list(detail.get("executed_tissues", [])),
        "rejected": list(detail.get("rejected_tissues", [])),
        "partial": list(detail.get("partial_tissues", [])),
        "scores": dict(detail.get("scores", {})),
        "requested": list(detail.get("requested_tissues", [])),
        "relief": {tid: float(v) for tid, v in dict(detail.get("relief_cells", {})).items()},
    }


def summarize_coordination(trajectory: list[dict[str, Any]], dt: float) -> dict[str, Any]:
    """Coordination execution stats over an organ trajectory (pure, Stage 4B).

    Counts plan-level events (requested/executed/rejected/partial), score
    means, realized demand relief and before/after demand means. Stage 4A
    trajectories without ``coordination_detail`` yield neutral zeros with
    mode ``"unknown"`` instead of an error.
    """
    if not trajectory:
        raise ValueError("organ trajectory must be non-empty")
    modes = {_detail(row)["mode"] for row in trajectory[1:]}
    modes.discard("unknown")
    mode = sorted(modes)[0] if len(modes) == 1 else ("mixed" if modes else "unknown")
    planned = executed = rejected = partial = 0
    score_exec: list[float] = []
    score_rej: list[float] = []
    relief_total = 0.0
    demand_before_v: list[float] = []
    demand_before_i: list[float] = []
    demand_after_v: list[float] = []
    demand_after_i: list[float] = []
    senescent_burden = damaged_burden = functional_mass = 0.0
    for row in trajectory[1:]:
        info = _detail(row)
        planned += len(info["requested"])
        executed += len(info["executed"])
        rejected += len(info["rejected"])
        partial += len(info["partial"])
        for tid in info["executed"]:
            if tid in info["scores"]:
                score_exec.append(float(info["scores"][tid]))
        for tid in info["rejected"]:
            if tid in info["scores"]:
                score_rej.append(float(info["scores"][tid]))
        relief_total += sum(info["relief"].values())
        demand_before_v.append(float(row["total_vascular_demand"]))
        demand_before_i.append(float(row["total_immune_demand"]))
        demand_after_v.append(float(row.get("executed_vascular_demand", row["total_vascular_demand"])))
        demand_after_i.append(float(row.get("executed_immune_demand", row["total_immune_demand"])))
        for tissue in row["tissues"].values():
            state = tissue["state"]
            senescent_burden += float(state["senescent_cells"])
            damaged_burden += float(state["damaged_cells"])
            functional_mass += float(state["functional_cells"])
    return {
        "coordination_mode": mode,
        "total_planned_replacement_events": int(planned),
        "total_executed_replacement_events": int(executed),
        "total_rejected_replacement_events": int(rejected),
        "total_partial_executions": int(partial),
        "execution_fraction": (executed / planned) if planned else 1.0,
        "rejected_fraction": (rejected / planned) if planned else 0.0,
        "mean_score_executed": (sum(score_exec) / len(score_exec)) if score_exec else None,
        "mean_score_rejected": (sum(score_rej) / len(score_rej)) if score_rej else None,
        "total_relief_cells": float(relief_total),
        "demand_relief_per_executed_replacement": None,  # needs executed cells; filled in compute_organ_summary
        "mean_immune_demand_before_coordination": (sum(demand_before_i) / len(demand_before_i)) if demand_before_i else 0.0,
        "mean_immune_demand_after_coordination": (sum(demand_after_i) / len(demand_after_i)) if demand_after_i else 0.0,
        "mean_vascular_demand_before_coordination": (sum(demand_before_v) / len(demand_before_v)) if demand_before_v else 0.0,
        "mean_vascular_demand_after_coordination": (sum(demand_after_v) / len(demand_after_v)) if demand_after_v else 0.0,
        "senescent_burden_auc": float(senescent_burden) * float(dt),
        "damage_burden_auc": float(damaged_burden) * float(dt),
        "functional_mass_auc": float(functional_mass) * float(dt),
    }


def compare_organ_against_baseline(
    intervention_summary: dict[str, Any],
    baseline_summary: dict[str, Any],
) -> dict[str, Any]:
    """Organ baseline-vs-intervention comparison at equal seed (pure).

    Positive ``organ_rejuvenation_delta_vs_baseline`` means the intervention
    ends with higher organ function; both are LOCAL organ proxies, not
    organism rejuvenation.
    """
    return {
        "organ_rejuvenation_delta_vs_baseline": (
            float(intervention_summary["final_organ_function"]) - float(baseline_summary["final_organ_function"])
        ),
        "organ_healthspan_gain_vs_baseline": (
            float(intervention_summary["organ_healthspan_proxy"]) - float(baseline_summary["organ_healthspan_proxy"])
        ),
        "organ_ttf_gain_vs_baseline": (
            float(intervention_summary["time_to_organ_viability_failure"])
            - float(baseline_summary["time_to_organ_viability_failure"])
        ),
    }


def coordination_benefit(
    resource_aware_summary: dict[str, Any],
    independent_summary: dict[str, Any],
) -> dict[str, Any]:
    """Benefit of organ coordination over independent tissue policies (pure)."""
    return {
        "coordination_benefit_healthspan": (
            float(resource_aware_summary["organ_healthspan_proxy"]) - float(independent_summary["organ_healthspan_proxy"])
        ),
        "coordination_benefit_ttf": (
            float(resource_aware_summary["time_to_organ_viability_failure"])
            - float(independent_summary["time_to_organ_viability_failure"])
        ),
        "coordination_benefit_function": (
            float(resource_aware_summary["final_organ_function"]) - float(independent_summary["final_organ_function"])
        ),
    }
