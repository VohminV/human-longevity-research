"""Organ-level replacement coordination (Stage 4A/4B/4C).

Pure planning adjustments on top of tissue :class:`ReplacementPolicy`
objects, which are never mutated here.

Stage 4A modes scale *how much* each tissue may replace. Stage 4B adds
*selective* modes that choose *which* plans execute, ranked by a
deterministic demand-relief score. Stage 4C adds *temporal* modes that
schedule plans in time (deferral) and rank by lookahead value under an
opt-in temporal relief model (immediate cost vs delayed relief). Scores
are OPERATIONAL model heuristics, not biological measures of benefit
(see docs/ORGAN_MODEL.md).
"""

from __future__ import annotations

import math

from dataclasses import dataclass
from typing import Any

# Canonical mode names. Older stage names are preserved verbatim.
COORDINATION_MODES = (
    "independent_tissue_policies",
    "resource_aware_scaling",
    "demand_relief_priority",
    "senescent_burden_priority",
    "immune_reserve_guard",
    "hybrid_demand_guard",
    "lookahead_priority",
    "deferral_scheduler",
    "hybrid_lookahead_deferral",
    "independent_all",
    "supply_demand_greedy",
    "lookahead_supply_demand",
    "deferral_supply_demand",
)

# Short aliases accepted anywhere a mode is configured; always normalized
# to the canonical name, so stored configs stay canonical.
COORDINATION_ALIASES = {
    "independent": "independent_tissue_policies",
    "proportional_scale": "resource_aware_scaling",
    "proportional": "resource_aware_scaling",
}

SCALE_MODES = ("independent_tissue_policies", "resource_aware_scaling")
SELECTION_MODES = (
    "demand_relief_priority",
    "senescent_burden_priority",
    "immune_reserve_guard",
    "hybrid_demand_guard",
)
DEFERRAL_MODES = ("deferral_scheduler", "hybrid_lookahead_deferral")
LOOKAHEAD_MODES = ("lookahead_priority", "hybrid_lookahead_deferral")
SUPPLY_MODES = (
    "independent_all",
    "supply_demand_greedy",
    "lookahead_supply_demand",
    "deferral_supply_demand",
)

# Stage 4D recovery targets (operational v0; niche_support reserved).
RECOVERY_TARGETS = ("vascular_capacity", "immune_capacity", "ecm_quality")

SCORE_WEIGHT_KEYS = ("alpha", "beta", "gamma", "delta", "epsilon", "w_vascular", "supply_beta")

DEFAULT_SCORE_WEIGHTS: dict[str, float] = {
    "alpha": 1.0,  # value per cleared senescent cell
    "beta": 0.5,  # value per cleared damaged cell
    "gamma": 1.0,  # penalty per expected cancer-risk unit
    "delta": 1.0,  # penalty per expected fibrosis unit
    "epsilon": 1.0,  # penalty per expected architecture-cost unit
    "w_vascular": 1.0,  # vascular cost weight inside the cost term
    "supply_beta": 1.0,  # Stage 4D: value per expected capacity unit restored
    "eps": 1e-6,  # cost denominator guard (must be > 0)
    "score_cutoff": 0.0,  # guard keeps plans with score >= cutoff
    "immune_guard_threshold": 0.6,  # guard engages below this predicted allocation
}


def validate_coordination(mode: Any) -> str:
    """Validate a mode name; aliases resolve to the canonical name."""
    if not isinstance(mode, str):
        raise ValueError(f"coordination must be one of {COORDINATION_MODES}, got {mode!r}")
    canonical = COORDINATION_ALIASES.get(mode, mode)
    if canonical not in COORDINATION_MODES:
        raise ValueError(f"coordination must be one of {COORDINATION_MODES}, got {mode!r}")
    return canonical


def validate_score_weights(weights: dict[str, Any]) -> dict[str, float]:
    """Validate the demand-relief score block (all weights >= 0, eps > 0)."""
    if not isinstance(weights, dict):
        raise ValueError("score weights must be a dict")
    merged = dict(DEFAULT_SCORE_WEIGHTS)
    merged.update(weights)
    unknown = set(merged) - set(DEFAULT_SCORE_WEIGHTS)
    if unknown:
        raise ValueError(f"unknown score weight keys: {sorted(unknown)}")
    validated: dict[str, float] = {}
    for key in SCORE_WEIGHT_KEYS:
        value = merged[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"score weight {key} must be a number, got {value!r}")
        numeric = float(value)
        if not math.isfinite(numeric) or numeric < 0.0:
            raise ValueError(f"score weight {key} must be finite and >= 0, got {value!r}")
        validated[key] = numeric
    eps = merged["eps"]
    if isinstance(eps, bool) or not isinstance(eps, (int, float)) or not math.isfinite(float(eps)) or float(eps) <= 0.0:
        raise ValueError(f"score weight eps must be finite and > 0, got {eps!r}")
    validated["eps"] = float(eps)
    cutoff = merged["score_cutoff"]
    if isinstance(cutoff, bool) or not isinstance(cutoff, (int, float)) or not math.isfinite(float(cutoff)):
        raise ValueError(f"score_cutoff must be finite, got {cutoff!r}")
    validated["score_cutoff"] = float(cutoff)
    threshold = merged["immune_guard_threshold"]
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or not math.isfinite(float(threshold))
        or not 0.0 <= float(threshold) <= 1.0
    ):
        raise ValueError(f"immune_guard_threshold must be in [0, 1], got {threshold!r}")
    validated["immune_guard_threshold"] = float(threshold)
    return validated


def coordination_scale_factor(
    total_vascular_demand: float,
    vascular_capacity: float,
    total_immune_demand: float,
    immune_capacity: float,
) -> float:
    """Shared-contention scale in [0, 1] (pure).

    ``1.0`` when both demands fit their capacities, otherwise the tightest
    ``capacity / demand`` ratio (proportional curtailment, documented
    assumption O-4). Zero demand never divides by zero.
    """
    ratios = [1.0]
    if total_vascular_demand > 0.0:
        ratios.append(min(1.0, float(vascular_capacity) / float(total_vascular_demand)) if vascular_capacity > 0 else 0.0)
    if total_immune_demand > 0.0:
        ratios.append(min(1.0, float(immune_capacity) / float(total_immune_demand)) if immune_capacity > 0 else 0.0)
    return max(0.0, min(1.0, min(ratios)))


def global_cap_scale_factor(planned_counts: list[float], cap: float | None) -> float:
    """Scale so the summed plan fits ``cap`` (pure; ``None`` = no cap)."""
    if cap is None:
        return 1.0
    total = sum(max(0.0, float(c)) for c in planned_counts)
    if total <= 0.0 or cap < 0.0:
        return 1.0
    return min(1.0, float(cap) / total)


def scaled_policy(policy: Any, scale: float, tag: str) -> Any:
    """Copy of ``policy`` with ``max_replacement_fraction`` scaled (pure)."""
    from longevity.model.policy import ReplacementPolicy  # deferred: avoid import cycle

    if not isinstance(policy, ReplacementPolicy):
        raise ValueError(f"expected ReplacementPolicy, got {type(policy)}")
    duplicate = ReplacementPolicy.from_dict(policy.to_dict())
    duplicate.max_replacement_fraction = max(0.0, min(1.0, float(policy.max_replacement_fraction) * float(scale)))
    duplicate.name = f"{policy.name}@{tag}x{float(scale):.3f}"
    return duplicate


def fraction_policy(policy: Any, count: float, pool: float, tag: str) -> Any:
    """Copy of ``policy`` sized for an exact cell count (pure).

    Sets ``max_replacement_fraction`` to ``count / pool`` (clamped to
    [0, 1]; 0 pool means a no-op fraction). TissueModel caps execution by
    physical availability on top, so stale counts stay safe.
    """
    from longevity.model.policy import ReplacementPolicy  # deferred: avoid import cycle

    if not isinstance(policy, ReplacementPolicy):
        raise ValueError(f"expected ReplacementPolicy, got {type(policy)}")
    duplicate = ReplacementPolicy.from_dict(policy.to_dict())
    if pool > 0.0:
        duplicate.max_replacement_fraction = max(0.0, min(1.0, float(count) / float(pool)))
    else:
        duplicate.max_replacement_fraction = 0.0
    duplicate.name = f"{policy.name}@{tag}n{float(count):.1f}"
    return duplicate


def disabled_policy(policy: Any, tag: str) -> Any:
    """Copy of ``policy`` with replacement disabled (pure; rejects a plan)."""
    from longevity.model.policy import ReplacementPolicy  # deferred: avoid import cycle

    if not isinstance(policy, ReplacementPolicy):
        raise ValueError(f"expected ReplacementPolicy, got {type(policy)}")
    duplicate = ReplacementPolicy.from_dict(policy.to_dict())
    duplicate.enabled = False
    duplicate.target = "none"
    duplicate.source = "none"
    duplicate.name = f"{policy.name}@{tag}xoff"
    return duplicate


def plan_relief_score(
    plan: Any,
    state: Any,
    demand: dict[str, float],
    weights: dict[str, float],
    relief_only: bool = False,
) -> dict[str, float]:
    """Demand-relief score of one replacement plan (pure, non-mutating).

    ``value`` rewards expected cleared cells (senescent/damaged pools cap the
    estimate) minus expected risk costs carried on the plan; ``cost`` is the
    plan's immediate replacement-driven resource demand; ``score`` is
    value per cost. ``relief_only`` ranks by cleared cells per cost (used by
    ``senescent_burden_priority``). Reads only; never mutates inputs.
    """
    target_count = max(0.0, float(plan.target_count))
    pool = 0.0
    relief_damaged = 0.0
    relief_senescent = 0.0
    if plan.target == "senescent":
        pool = float(getattr(state, "senescent_cells", 0.0))
        relief_senescent = min(target_count, max(0.0, pool))
    elif plan.target == "damaged":
        pool = float(getattr(state, "damaged_cells", 0.0))
        relief_damaged = min(target_count, max(0.0, pool))
    if relief_only:
        value = relief_senescent + relief_damaged
    else:
        value = (
            weights["alpha"] * relief_senescent
            + weights["beta"] * relief_damaged
            - weights["gamma"] * float(plan.expected_cancer_risk_delta)
            - weights["delta"] * float(plan.expected_fibrosis_delta)
            - weights["epsilon"] * float(plan.expected_architecture_cost)
        )
    cost = target_count * (
        float(demand["immune_per_replacement"])
        + weights["w_vascular"] * float(demand["vascular_per_replacement"])
    )
    eps = float(weights["eps"])
    return {
        "value": float(value),
        "cost": float(cost),
        "score": float(value) / (float(cost) + eps),
        "relief_cells": float(relief_senescent + relief_damaged),
    }


def rank_plan_scores(scores: dict[str, float]) -> list[str]:
    """Tissue ids by score descending, ties by tissue_id ascending (pure)."""
    return sorted(scores, key=lambda tid: (-float(scores[tid]), tid))


def _plan_activity_needs(
    count: float, demand: dict[str, float]
) -> tuple[float, float]:
    return (
        max(0.0, count) * float(demand["vascular_per_replacement"]),
        max(0.0, count) * float(demand["immune_per_replacement"]),
    )


def selective_policies_for_step(
    base_policies: list[Any],
    tissue_ids: list[str],
    states: list[Any],
    demands: list[dict[str, float]],
    requested_counts: list[float],
    requested_plans: list[Any],
    base_vascular_demand: float,
    vascular_capacity: float,
    base_immune_demand: float,
    immune_capacity: float,
    coordination: str,
    global_replacement_cap: float | None,
    weights: dict[str, float],
    rank_scores: dict[str, float] | None = None,
) -> tuple[list[Any], dict[str, Any]]:
    """Selective execution policies for one organ step (pure, non-mutating).

    Water-filling (``demand_relief_priority`` / ``senescent_burden_priority`` /
    ``lookahead_priority``) accepts plans in score order while predicted
    capacity lasts, partially executing the first plan that does not fit
    whole (via a scaled fraction — the architecture natively supports
    partial execution); a relief floor executes the top-scoring plan when
    nothing fits. ``immune_reserve_guard`` executes everything while
    predicted immune allocation holds, otherwise keeps only plans at/above
    ``score_cutoff`` (top-1 fallback when none pass). ``hybrid_demand_guard``
    applies the cutoff first, then water-fills the survivors. An optional
    ``rank_scores`` override replaces the ordering (used by lookahead
    ranking). Returns (policies, info) with per-tissue scales, scores
    and executed/rejected/partial lists.
    """
    mode = validate_coordination(coordination)
    if mode not in SELECTION_MODES + ("lookahead_priority",):
        raise ValueError(f"selective coordination needs a selection mode, got {coordination!r}")
    before = [p.to_dict() for p in base_policies]
    relief_only = mode == "senescent_burden_priority"
    cap_scale = global_cap_scale_factor(requested_counts, global_replacement_cap)
    # Pre-scaled requested counts: what each plan would execute unfiltered.
    scaled_counts = [max(0.0, float(c)) * cap_scale for c in requested_counts]
    scores: dict[str, float] = {}
    score_detail: dict[str, dict[str, float]] = {}
    for tid, plan, state, demand in zip(tissue_ids, requested_plans, states, demands):
        assessed = plan_relief_score(plan, state, demand, weights, relief_only=relief_only)
        scores[tid] = assessed["score"]
        score_detail[tid] = assessed
    order_scores = dict(rank_scores) if rank_scores is not None else scores
    for tid in tissue_ids:
        order_scores.setdefault(tid, scores[tid])
    nonempty = [tid for tid, count in zip(tissue_ids, scaled_counts) if count > 0.0]

    survivors: list[str] = list(nonempty)
    if mode in ("immune_reserve_guard", "hybrid_demand_guard"):
        total_immune = base_immune_demand + sum(
            _plan_activity_needs(count, demand)[1]
            for count, demand in zip(scaled_counts, demands)
        )
        predicted = min(1.0, float(immune_capacity) / total_immune) if total_immune > 0.0 else 1.0
        if predicted < float(weights["immune_guard_threshold"]):
            survivors = [tid for tid in nonempty if order_scores[tid] >= float(weights["score_cutoff"])]
            if not survivors and nonempty:
                survivors = rank_plan_scores({tid: order_scores[tid] for tid in nonempty})[:1]

    executed: list[str] = []
    rejected: list[str] = []
    partial: list[str] = []
    scales: dict[str, float] = {}
    if mode in ("demand_relief_priority", "senescent_burden_priority", "hybrid_demand_guard", "lookahead_priority"):
        remaining_v = float(vascular_capacity) - base_vascular_demand
        remaining_i = float(immune_capacity) - base_immune_demand
        pool = survivors if mode == "hybrid_demand_guard" else list(nonempty)
        for tid in rank_plan_scores({t: order_scores[t] for t in pool}):
            index = tissue_ids.index(tid)
            need_v, need_i = _plan_activity_needs(scaled_counts[index], demands[index])
            tolerance = 1e-9
            if need_v <= remaining_v + tolerance and need_i <= remaining_i + tolerance:
                executed.append(tid)
                scales[tid] = cap_scale
                remaining_v -= need_v
                remaining_i -= need_i
            else:
                fill = 1.0
                if need_v > 0.0:
                    fill = min(fill, remaining_v / need_v)
                if need_i > 0.0:
                    fill = min(fill, remaining_i / need_i)
                fill = max(0.0, min(1.0, fill))
                if fill > 0.0:
                    executed.append(tid)
                    partial.append(tid)
                    scales[tid] = cap_scale * fill
                    remaining_v -= need_v * fill
                    remaining_i -= need_i * fill
                else:
                    rejected.append(tid)
                    scales[tid] = 0.0
        for tid in nonempty:
            if tid not in executed and tid not in rejected:
                rejected.append(tid)
                scales[tid] = 0.0
        if not executed and nonempty:
            # Relief floor: never idle while relief-positive work exists.
            top = rank_plan_scores({t: order_scores[t] for t in nonempty})[0]
            rejected.remove(top)
            executed.append(top)
            scales[top] = cap_scale
    else:  # immune_reserve_guard: survivors execute whole, rest rejected.
        for tid in nonempty:
            if tid in survivors:
                executed.append(tid)
                scales[tid] = cap_scale
            else:
                rejected.append(tid)
                scales[tid] = 0.0

    policies: list[Any] = []
    for tid, policy in zip(tissue_ids, base_policies):
        if tid in executed and tid not in partial:
            policies.append(scaled_policy(policy, scales[tid], "organ"))
        elif tid in partial:
            policies.append(scaled_policy(policy, scales[tid], "organ"))
        elif tid in rejected:
            policies.append(disabled_policy(policy, "organ"))
        else:  # empty plan: scale is cosmetic; execution stays a no-op.
            policies.append(scaled_policy(policy, scales.get(tid, cap_scale), "organ"))
    assert [p.to_dict() for p in base_policies] == before, "coordination must not mutate base policies"
    n_requested = len(nonempty)
    info = {
        "mode": mode,
        "scale": (len(executed) / n_requested) if n_requested else 1.0,
        "executed_tissues": sorted(executed),
        "rejected_tissues": sorted(rejected),
        "partial_tissues": sorted(partial),
        "scales": {tid: float(scales.get(tid, cap_scale)) for tid in tissue_ids},
        "scores": {tid: float(order_scores[tid]) for tid in tissue_ids},
        "score_values": {tid: float(score_detail[tid]["value"]) for tid in tissue_ids},
        "score_costs": {tid: float(score_detail[tid]["cost"]) for tid in tissue_ids},
        "requested_tissues": sorted(nonempty),
    }
    return (policies, info)


def effective_policies_for_step(
    base_policies: list[Any],
    tissue_ids: list[str],
    total_vascular_demand: float,
    vascular_capacity: float,
    total_immune_demand: float,
    immune_capacity: float,
    coordination: str,
    global_replacement_cap: float | None,
    planned_counts: list[float],
) -> tuple[list[Any], float]:
    """Effective execution policies for one organ step (pure, non-mutating).

    Returns (policies, applied_scale). ``independent_tissue_policies``
    executes base policies unchanged (scale 1, cap still applies when set);
    ``resource_aware_scaling`` multiplies by the contention factor first.
    Selection/temporal modes (Stage 4B/4C) are NOT served here — they run
    through :func:`selective_policies_for_step`; passing one raises a clear
    error.
    """
    mode = validate_coordination(coordination)
    if mode not in SCALE_MODES:
        raise ValueError(
            f"{coordination!r} is not a scale mode: selection modes use selective_policies_for_step, "
            "deferral modes schedule through the organ step"
        )
    before = [p.to_dict() for p in base_policies]
    if mode == "independent_tissue_policies":
        scale = 1.0
    else:
        scale = coordination_scale_factor(
            total_vascular_demand, vascular_capacity, total_immune_demand, immune_capacity
        )
    cap_scale = global_cap_scale_factor(planned_counts, global_replacement_cap)
    applied = max(0.0, min(1.0, scale * cap_scale))
    effective = [scaled_policy(p, applied, "organ") for p in base_policies]
    assert [p.to_dict() for p in base_policies] == before, "coordination must not mutate base policies"
    return (effective, applied)


# ---------------------------------------------------------------------------
# Stage 4C: lookahead score + deferral planning (pure).
# ---------------------------------------------------------------------------

LOOKAHEAD_DEFAULTS: dict[str, float] = {
    "lookahead_discount": 0.95,  # per-step discount of future relief, in (0, 1]
}


def validate_lookahead_params(params: dict[str, Any]) -> dict[str, float]:
    """Validate lookahead extras (discount in (0, 1]; unknown keys reject)."""
    if not isinstance(params, dict):
        raise ValueError("lookahead params must be a dict")
    merged = dict(LOOKAHEAD_DEFAULTS)
    merged.update(params)
    unknown = set(merged) - set(LOOKAHEAD_DEFAULTS)
    if unknown:
        raise ValueError(f"unknown lookahead param keys: {sorted(unknown)}")
    discount = merged["lookahead_discount"]
    if (
        isinstance(discount, bool)
        or not isinstance(discount, (int, float))
        or not math.isfinite(float(discount))
        or not 0.0 < float(discount) <= 1.0
    ):
        raise ValueError(f"lookahead_discount must be in (0, 1], got {discount!r}")
    return {"lookahead_discount": float(discount)}


def lookahead_plan_score(
    plan: Any,
    state: Any,
    demand: dict[str, float],
    weights: dict[str, float],
    temporal: dict[str, float],
    discount: float = 0.95,
) -> dict[str, float]:
    """Lookahead value of one plan under the temporal model (pure).

    ``immediate_cost`` is the plan's same-step resource cost including the
    temporal spike; ``future_relief`` is the discounted delayed demand
    reduction the plan is expected to create. Ranks plans by benefit timing,
    not just myopic relief. Reads only; never mutates inputs.
    """
    assessed = plan_relief_score(plan, state, demand, weights)
    target_count = max(0.0, float(plan.target_count))
    spike = target_count * (
        float(temporal.get("immediate_immune_cost_multiplier", 0.0)) * float(demand["immune_per_replacement"])
        + float(weights.get("w_vascular", 1.0))
        * float(temporal.get("immediate_vascular_cost_multiplier", 0.0))
        * float(demand["vascular_per_replacement"])
    )
    immediate_cost = assessed["cost"] + spike
    delay = int(temporal.get("relief_delay_steps", 0))
    future_relief = (
        assessed["relief_cells"]
        * float(temporal.get("relief_magnitude_scale", 0.0))
        * (float(discount) ** delay)
    )
    risk_penalty = (
        weights["gamma"] * float(plan.expected_cancer_risk_delta)
        + weights["delta"] * float(plan.expected_fibrosis_delta)
        + weights["epsilon"] * float(plan.expected_architecture_cost)
    )
    eps = float(weights["eps"])
    return {
        "immediate_cost": float(immediate_cost),
        "future_relief": float(future_relief),
        "lookahead_value": float(future_relief - risk_penalty),
        "score": float(future_relief - risk_penalty) / (float(immediate_cost) + eps),
        "relief_cells": float(assessed["relief_cells"]),
    }


def deferral_candidates_for_step(
    tissue_ids: list[str],
    candidate_counts: dict[str, float],
    scores: dict[str, float],
    base_immune_demand: float,
    immune_capacity: float,
    activity_immune_need: dict[str, float],
    threshold: float,
    defer_steps: int,
    current_step: int,
) -> dict[str, Any]:
    """Decide execute-now vs defer-later per tissue (pure, non-mutating).

    Tissues rank by score (ties by tissue_id); accepted in order while the
    predicted immune allocation with accepted activity stays at/above
    ``threshold``. The remainder is deferred by ``defer_steps`` (never
    silently dropped here — expiry is the queue's job). Returns the
    execute/defer split with deterministic order.
    """
    if defer_steps < 0:
        raise ValueError(f"defer_steps must be >= 0, got {defer_steps!r}")
    ordered = rank_plan_scores({tid: scores[tid] for tid in candidate_counts if candidate_counts[tid] > 0.0})
    accepted: dict[str, float] = {}
    deferred: dict[str, float] = {}
    kept_immune = base_immune_demand
    for tid in ordered:
        need = max(0.0, float(activity_immune_need.get(tid, 0.0)))
        predicted_total = kept_immune + need
        predicted = min(1.0, float(immune_capacity) / predicted_total) if predicted_total > 0.0 else 1.0
        if predicted >= float(threshold):
            accepted[tid] = float(candidate_counts[tid])
            kept_immune += need
        else:
            deferred[tid] = float(candidate_counts[tid])
    # Tissues with no candidate count execute nothing and defer nothing.
    idle = sorted(set(tissue_ids) - set(ordered))
    return {
        "execute_now": {tid: accepted[tid] for tid in sorted(accepted)},
        "defer": {tid: {"count": deferred[tid], "defer_until_step": current_step + int(defer_steps)} for tid in sorted(deferred)},
        "idle": idle,
        "order": ordered,
    }


# ---------------------------------------------------------------------------
# Stage 4D: decoupled recovery actions + supply-demand joint selection.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RecoveryPolicy:
    """When and how strongly to schedule niche/supply recovery (Stage 4D).

    A per-tissue policy for a single recovery target. Planning is pure
    (see :func:`plan_recovery_action`); execution lives in ``OrganModel``.
    Unlike replacement, recovery removes no cells: it pays an immediate
    resource cost for a delayed capacity/ECM effect.
    """

    name: str = "recovery"
    enabled: bool = False
    target: str = "vascular_capacity"
    frequency: int = 10
    magnitude: float = 0.5
    delay_steps: int = 5
    immediate_immune_multiplier: float = 1.0
    immediate_vascular_multiplier: float = 1.0
    priority_hint: float = 1.0

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise ValueError("recovery policy name must be a non-empty string")
        if not isinstance(self.enabled, bool):
            raise ValueError("recovery policy enabled must be a bool")
        if self.target not in RECOVERY_TARGETS:
            raise ValueError(f"recovery target must be one of {RECOVERY_TARGETS}, got {self.target!r}")
        if isinstance(self.frequency, bool) or not isinstance(self.frequency, int) or self.frequency < 1:
            raise ValueError(f"recovery frequency must be an int >= 1, got {self.frequency!r}")
        for field_name in ("magnitude", "immediate_immune_multiplier", "immediate_vascular_multiplier",
                           "priority_hint"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"recovery {field_name} must be a number, got {value!r}")
            if not math.isfinite(float(value)) or float(value) < 0.0:
                raise ValueError(f"recovery {field_name} must be finite and >= 0, got {value!r}")
        if isinstance(self.delay_steps, bool) or not isinstance(self.delay_steps, int) or self.delay_steps < 0:
            raise ValueError(f"recovery delay_steps must be an int >= 0, got {self.delay_steps!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": bool(self.enabled),
            "target": self.target,
            "frequency": int(self.frequency),
            "magnitude": float(self.magnitude),
            "delay_steps": int(self.delay_steps),
            "immediate_immune_multiplier": float(self.immediate_immune_multiplier),
            "immediate_vascular_multiplier": float(self.immediate_vascular_multiplier),
            "priority_hint": float(self.priority_hint),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecoveryPolicy":
        if not isinstance(data, dict):
            raise ValueError(f"recovery policy must be a dict, got {data!r}")
        return cls(
            name=data.get("name", "recovery"),
            enabled=bool(data.get("enabled", False)),
            target=data.get("target", "vascular_capacity"),
            frequency=int(data.get("frequency", 10)),
            magnitude=float(data.get("magnitude", 0.5)),
            delay_steps=int(data.get("delay_steps", 5)),
            immediate_immune_multiplier=float(data.get("immediate_immune_multiplier", 1.0)),
            immediate_vascular_multiplier=float(data.get("immediate_vascular_multiplier", 1.0)),
            priority_hint=float(data.get("priority_hint", 1.0)),
        )

    def is_due(self, step_count: int) -> bool:
        """True when a recovery event is scheduled at this step counter."""
        if not self.enabled:
            return False
        return step_count % self.frequency == 0


@dataclass(frozen=True)
class RecoveryPlan:
    """One scheduled recovery action (pure planning output, Stage 4D)."""

    token: str = ""
    tissue_id: str = ""
    target: str = "vascular_capacity"
    magnitude: float = 0.0
    immediate_immune_cost: float = 0.0
    immediate_vascular_cost: float = 0.0
    delay_steps: int = 0
    expected_capacity_delta: float = 0.0

    def __post_init__(self) -> None:
        if self.target not in RECOVERY_TARGETS:
            raise ValueError(f"recovery plan target must be one of {RECOVERY_TARGETS}, got {self.target!r}")
        for field_name in ("magnitude", "immediate_immune_cost", "immediate_vascular_cost",
                           "expected_capacity_delta"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"recovery plan {field_name} must be a number, got {value!r}")
            if not math.isfinite(float(value)) or float(value) < 0.0:
                raise ValueError(f"recovery plan {field_name} must be finite and >= 0, got {value!r}")
        if isinstance(self.delay_steps, bool) or not isinstance(self.delay_steps, int) or self.delay_steps < 0:
            raise ValueError(f"recovery plan delay_steps must be an int >= 0, got {self.delay_steps!r}")

    @classmethod
    def empty(cls, tissue_id: str = "", target: str = "vascular_capacity") -> "RecoveryPlan":
        """The no-op recovery plan: disabled, off-schedule, or zero magnitude."""
        return cls(token="", tissue_id=tissue_id, target=target)

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "tissue_id": self.tissue_id,
            "target": self.target,
            "magnitude": float(self.magnitude),
            "immediate_immune_cost": float(self.immediate_immune_cost),
            "immediate_vascular_cost": float(self.immediate_vascular_cost),
            "delay_steps": int(self.delay_steps),
            "expected_capacity_delta": float(self.expected_capacity_delta),
        }


def plan_recovery_action(policy: Any, tissue_id: str, step_count: int) -> RecoveryPlan:
    """Compute one tissue's recovery action for this step WITHOUT mutating.

    Pure: reads the policy only. Returns :meth:`RecoveryPlan.empty` when
    disabled, off-schedule, or zero-magnitude.
    """
    if not isinstance(policy, RecoveryPolicy):
        raise ValueError(f"expected RecoveryPolicy, got {type(policy)}")
    if not policy.enabled or not policy.is_due(step_count):
        return RecoveryPlan.empty(tissue_id, policy.target)
    magnitude = max(0.0, float(policy.magnitude))
    if magnitude <= 0.0:
        return RecoveryPlan.empty(tissue_id, policy.target)
    return RecoveryPlan(
        token=f"{tissue_id}:{policy.target}:{int(step_count)}",
        tissue_id=tissue_id,
        target=policy.target,
        magnitude=magnitude,
        immediate_immune_cost=magnitude * float(policy.immediate_immune_multiplier),
        immediate_vascular_cost=magnitude * float(policy.immediate_vascular_multiplier),
        delay_steps=int(policy.delay_steps),
        expected_capacity_delta=magnitude,
    )


def joint_action_score(
    value: float,
    immediate_immune_cost: float,
    immediate_vascular_cost: float,
    weights: dict[str, float],
) -> dict[str, float]:
    """Combined supply-demand value per immediate cost (pure, Stage 4D).

    Shared ranker for replacement value (demand relief minus risks) and
    recovery value (expected supply restoration). Deterministic, zero-cost
    safe, negative values allowed.
    """
    cost = max(0.0, float(immediate_immune_cost)) + float(weights.get("w_vascular", 1.0)) * max(
        0.0, float(immediate_vascular_cost)
    )
    eps = float(weights.get("eps", 1e-6))
    return {
        "value": float(value),
        "cost": float(cost),
        "score": float(value) / (float(cost) + eps),
    }


def recovery_action_value(plan: RecoveryPlan, weights: dict[str, float]) -> float:
    """Expected supply value of a recovery plan (pure, Stage 4D)."""
    return float(weights.get("supply_beta", 1.0)) * max(0.0, float(plan.expected_capacity_delta))
