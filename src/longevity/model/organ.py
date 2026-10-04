"""ORGAN MODEL LAYER: minimal abstract organ composition (Stage 4A).

An organ is a composition of tissue modules that reuse the Stage 3A
:class:`TissueModel` dynamics WITHOUT duplication, plus shared limited
resources (vascular / immune capacity). Locally sustainable tissue policies
can therefore contend for shared support, which is the organ-level question
of Stage 4A.

Scope (see docs/ORGAN_MODEL.md): abstract organ, 2-3 tissue roles, no
organism, no brain, no anatomy. All demand coefficients, aggregation rules
and viability thresholds are OPERATIONAL model choices, not measurements.
"""

from __future__ import annotations

import copy
import math

from dataclasses import dataclass, field
from typing import Any

from longevity.model.policy import ReplacementPolicy
from longevity.model.organ_policy import RecoveryPolicy
from longevity.model.tissue import (
    TissueModel,
    TissueState,
    TissueStepContext,
    assert_tissue_invariants,
    validate_tissue_parameters,
)
from longevity.sim.rng import Rng, state_from_json, state_to_json

ORGAN_MODEL_VERSION = "0.4.0"
MODEL_SCOPE = "abstract_organ_composition"

VALID_ROLES = ("parenchyma", "stroma", "vascular_interface")
VALID_AGGREGATIONS = ("weighted_sum", "min_normalized", "weighted_geometric")

# Stage 4C temporal relief models. "none" disables all temporal machinery
# (bit-identical Stage 4B behavior); "delayed_relief" adds an immediate
# intervention spike plus delayed demand-reduction events (O-10…O-12).
TEMPORAL_MODELS = ("none", "delayed_relief")
VALID_RELIEF_TARGETS = ("immune_demand", "vascular_demand", "composite")

DEFAULT_TEMPORAL_PARAMS: dict[str, Any] = {
    "immediate_immune_cost_multiplier": 0.0,
    "immediate_vascular_cost_multiplier": 0.0,
    "relief_delay_steps": 0,
    "relief_duration_steps": 10,
    "relief_target": "composite",
    "relief_magnitude_scale": 0.0,
    "defer_steps": 5,
    "defer_allocation_threshold": 0.6,
    "deferred_plan_max_age": 30,
    "lookahead_discount": 0.95,
}
_TEMPORAL_FLOAT_KEYS = (
    "immediate_immune_cost_multiplier",
    "immediate_vascular_cost_multiplier",
    "relief_magnitude_scale",
    "defer_allocation_threshold",
)
_TEMPORAL_INT_KEYS = (
    "relief_delay_steps",
    "relief_duration_steps",
    "defer_steps",
    "deferred_plan_max_age",
)


def validate_temporal_params(params: dict[str, Any]) -> dict[str, Any]:
    """Validate the Stage 4C temporal parameter block (operational, v0)."""
    if not isinstance(params, dict):
        raise ValueError("temporal params must be a dict")
    merged = dict(DEFAULT_TEMPORAL_PARAMS)
    merged.update(params)
    unknown = set(merged) - set(DEFAULT_TEMPORAL_PARAMS)
    if unknown:
        raise ValueError(f"unknown temporal param keys: {sorted(unknown)}")
    validated: dict[str, Any] = {}
    for key in _TEMPORAL_FLOAT_KEYS:
        validated[key] = _require_number(merged[key], f"temporal.{key}", lo=0.0)
    for key in _TEMPORAL_INT_KEYS:
        value = merged[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"temporal.{key} must be an int, got {value!r}")
        lo = 1 if key == "relief_duration_steps" else 0
        if value < lo:
            raise ValueError(f"temporal.{key} must be >= {lo}, got {value!r}")
        validated[key] = value
    target = merged["relief_target"]
    if target in ("senescence", "damage"):
        raise ValueError(
            f"temporal.relief_target={target!r} needs pool-level dynamics and is not supported in v0; "
            f"use one of {VALID_RELIEF_TARGETS}"
        )
    if target not in VALID_RELIEF_TARGETS:
        raise ValueError(f"temporal.relief_target must be one of {VALID_RELIEF_TARGETS}, got {target!r}")
    validated["relief_target"] = target
    if not 0.0 <= float(validated["defer_allocation_threshold"]) <= 1.0:
        raise ValueError("temporal.defer_allocation_threshold must be in [0, 1]")
    discount = merged["lookahead_discount"]
    if isinstance(discount, bool) or not isinstance(discount, (int, float)):
        raise ValueError(f"temporal.lookahead_discount must be a number, got {discount!r}")
    if not math.isfinite(float(discount)) or not 0.0 < float(discount) <= 1.0:
        raise ValueError(f"temporal.lookahead_discount must be in (0, 1], got {discount!r}")
    validated["lookahead_discount"] = float(discount)
    return validated


def validate_temporal_model(model: Any) -> str:
    """Validate a temporal relief model name."""
    if not isinstance(model, str) or model not in TEMPORAL_MODELS:
        raise ValueError(f"temporal_relief_model must be one of {TEMPORAL_MODELS}, got {model!r}")
    return model


def _fresh_temporal_totals() -> dict[str, Any]:
    return {
        "immediate_immune_cost_total": 0.0,
        "immediate_vascular_cost_total": 0.0,
        "peak_immediate_immune_demand": 0.0,
        "peak_immediate_vascular_demand": 0.0,
        "min_immune_allocation_during_spike": None,
        "min_vascular_allocation_during_spike": None,
        "relief_created_events": 0,
        "relief_created_amount": 0.0,
        "relief_realized_events": 0,
        "relief_realized_amount": 0.0,
        "relief_expired_events": 0,
        "relief_expired_amount": 0.0,
        "deferred_plan_count": 0,
        "executed_after_deferral_count": 0,
        "expired_deferred_plan_count": 0,
        "defer_delays_sum": 0.0,
        "defer_delays_count": 0,
        "max_defer_queue_length": 0,
    }


def _fresh_recovery_totals() -> dict[str, Any]:
    return {
        "recovery_planned_events": 0,
        "recovery_executed_events": 0,
        "recovery_deferred_events": 0,
        "recovery_expired_events": 0,
        "recovery_rejected_events": 0,
        "recovery_merged_effects": 0,
        "capacity_increase_created": 0.0,
        "capacity_increase_realized": 0.0,
        "capacity_increase_expired": 0,
        "recovery_immediate_immune_cost": 0.0,
        "recovery_immediate_vascular_cost": 0.0,
        "executed_after_deferral_recovery": 0,
        "expired_deferred_recovery": 0,
    }

# Operational resource-demand coefficients (model assumptions O-1..O-3, not
# measurements). Demand is in abstract "support units" per step; capacities
# in the same units. Stage 4C adds O-10…O-12 (temporal spike/relief) and
# O-13…O-15 (deferral mechanics); see docs/ORGAN_MODEL.md §8.
DEFAULT_DEMAND_COEFFICIENTS: dict[str, float] = {
    "base_vascular_demand": 1.0,
    "vascular_per_functional": 0.0005,
    "vascular_per_damaged": 0.001,
    "vascular_per_senescent": 0.0015,
    "vascular_per_replacement": 0.01,
    "base_immune_demand": 1.0,
    "immune_per_damaged": 0.002,
    "immune_per_senescent": 0.003,
    "immune_per_cancer_risk": 5.0,
    "immune_per_fibrosis": 3.0,
    "immune_per_replacement": 0.01,
}
_DEMAND_KEYS = tuple(DEFAULT_DEMAND_COEFFICIENTS)

DEFAULT_ORGAN_THRESHOLDS: dict[str, Any] = {
    "min_organ_function": 0.75,
    "min_vital_tissue_function": 0.60,
    "min_vascular_allocation_ratio": 0.60,
    "min_immune_allocation_ratio": 0.60,
    "max_organ_cancer_risk": 0.15,
    "max_organ_fibrosis_index": 0.30,
    # Stage 4D additions. Defaults are non-firing on legacy runs (static
    # capacities ratio 1.0, ECM floors above 0.3, pressures below 0.8,
    # zero backlog), so old configs recompute bit-identically.
    "min_capacity_fraction": 0.50,
    "min_vital_ecm_quality": 0.30,
    "max_mean_immune_pressure": 0.80,
    "max_recovery_backlog": 50,
}
_THRESHOLD_KEYS = tuple(DEFAULT_ORGAN_THRESHOLDS)
_THRESHOLD_FLOAT_KEYS = tuple(k for k in _THRESHOLD_KEYS if k != "max_recovery_backlog")

# Stage 4D recovery models. "none" disables all recovery machinery
# (bit-identical Stage 4C behavior).
RECOVERY_MODELS = ("none", "decoupled_niche_recovery")

DEFAULT_CAPACITY_DYNAMICS: dict[str, Any] = {
    "vascular_degradation_rate": 0.0,
    "vascular_senescent_rate": 0.0,
    "immune_degradation_rate": 0.0,
    "immune_senescent_rate": 0.0,
    "capacity_ceiling_multiplier": 2.0,
}
_CAPACITY_KEYS = tuple(DEFAULT_CAPACITY_DYNAMICS)

# Deterministic organ failure-cause vocabulary (Stage 4A base plus Stage 4D
# supply-side causes; canonical order below is the tie-break for sequences).
ORGAN_FAILURE_CAUSE_ORDER = (
    "vascular_capacity_failure",
    "immune_capacity_failure",
    "organ_cancer_risk",
    "organ_fibrosis",
    "capacity_exhaustion",
    "ecm_collapse",
    "recovery_debt",
    "chronic_inflammatory_overload",
    "parenchyma_failure",
    "stroma_failure",
    "vascular_interface_failure",
    "organ_function_failure",
)
ORGAN_PRIMARY_CAUSES = ORGAN_FAILURE_CAUSE_ORDER + ("multiple_simultaneous", "none")

_ROLE_TO_CAUSE = {
    "parenchyma": "parenchyma_failure",
    "stroma": "stroma_failure",
    "vascular_interface": "vascular_interface_failure",
}


def _require_number(value: Any, path: str, lo: float | None = None, hi: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number, got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{path} must be finite, got {value!r}")
    if lo is not None and result < lo:
        raise ValueError(f"{path} must be >= {lo}")
    if hi is not None and result > hi:
        raise ValueError(f"{path} must be <= {hi}")
    return result


def validate_demand_coefficients(coefficients: dict[str, Any]) -> dict[str, float]:
    """Validate per-module demand coefficients, filling operational defaults."""
    merged = dict(DEFAULT_DEMAND_COEFFICIENTS)
    merged.update(coefficients)
    unknown = set(merged) - set(_DEMAND_KEYS)
    if unknown:
        raise ValueError(f"unknown demand coefficients: {sorted(unknown)}")
    return {key: _require_number(merged[key], f"demand.{key}", lo=0.0) for key in _DEMAND_KEYS}


def validate_organ_thresholds(thresholds: dict[str, Any]) -> dict[str, Any]:
    """Validate the organ viability thresholds block.

    All Stage 4A keys are required and in [0, 1]; ``max_recovery_backlog``
    is an int >= 1. Unknown keys reject.
    """
    if not isinstance(thresholds, dict):
        raise ValueError("organ thresholds must be a dict")
    missing = set(_THRESHOLD_KEYS) - set(thresholds)
    if missing:
        raise ValueError(f"organ thresholds missing keys: {sorted(missing)}")
    unknown = set(thresholds) - set(_THRESHOLD_KEYS)
    if unknown:
        raise ValueError(f"organ thresholds unknown keys: {sorted(unknown)}")
    validated: dict[str, Any] = {}
    for key in _THRESHOLD_FLOAT_KEYS:
        validated[key] = _require_number(thresholds[key], f"organ_thresholds.{key}", lo=0.0, hi=1.0)
    backlog = thresholds["max_recovery_backlog"]
    if isinstance(backlog, bool) or not isinstance(backlog, int) or backlog < 1:
        raise ValueError(f"organ_thresholds.max_recovery_backlog must be an int >= 1, got {backlog!r}")
    validated["max_recovery_backlog"] = backlog
    return validated


def validate_capacity_dynamics(params: dict[str, Any]) -> dict[str, float]:
    """Validate the dynamic-capacity block, filling neutral defaults."""
    if not isinstance(params, dict):
        raise ValueError("capacity dynamics must be a dict")
    merged = dict(DEFAULT_CAPACITY_DYNAMICS)
    merged.update(params)
    unknown = set(merged) - set(_CAPACITY_KEYS)
    if unknown:
        raise ValueError(f"unknown capacity dynamics keys: {sorted(unknown)}")
    validated: dict[str, float] = {}
    for key in _CAPACITY_KEYS:
        lo = 1.0 if key == "capacity_ceiling_multiplier" else 0.0
        validated[key] = _require_number(merged[key], f"capacity.{key}", lo=lo)
    return validated


def validate_recovery_model(model: Any) -> str:
    """Validate a recovery model name."""
    if not isinstance(model, str) or model not in RECOVERY_MODELS:
        raise ValueError(f"recovery_model must be one of {RECOVERY_MODELS}, got {model!r}")
    return model


@dataclass(frozen=True)
class TissueModuleConfig:
    """One tissue module inside the abstract organ."""

    tissue_id: str = "parenchyma"
    role: str = "parenchyma"
    weight: float = 1.0
    is_vital: bool = True
    required_function: float = 1.0
    initial_state: dict[str, Any] = field(default_factory=dict)
    tissue_parameters: dict[str, Any] = field(default_factory=dict)
    policy: dict[str, Any] = field(default_factory=dict)
    demand_coefficients: dict[str, Any] = field(default_factory=dict)
    recovery: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        from longevity.model.organ_policy import RecoveryPolicy  # deferred: avoid import cycle

        if not self.tissue_id or not isinstance(self.tissue_id, str):
            raise ValueError("tissue_id must be a non-empty string")
        if self.role not in VALID_ROLES:
            raise ValueError(f"tissue role must be one of {VALID_ROLES}, got {self.role!r}")
        _require_number(self.weight, "tissue.weight", lo=1e-9)
        if not isinstance(self.is_vital, bool):
            raise ValueError("tissue.is_vital must be a bool")
        _require_number(self.required_function, "tissue.required_function", lo=1e-9)
        if not isinstance(self.initial_state, dict):
            raise ValueError("tissue.initial_state must be a dict")
        if not isinstance(self.tissue_parameters, dict):
            raise ValueError("tissue.tissue_parameters must be a dict")
        if not isinstance(self.policy, dict):
            raise ValueError("tissue.policy must be a dict")
        assert_tissue_invariants(TissueState.from_dict(self.initial_state))
        ReplacementPolicy.from_dict(self.policy)
        validate_demand_coefficients(dict(self.demand_coefficients))
        if not isinstance(self.recovery, dict):
            raise ValueError("tissue.recovery must be a dict")
        RecoveryPolicy.from_dict(self.recovery)


def tissue_function_value(state: dict[str, Any], initial_functional: float) -> float:
    """Normalized tissue function: functional pool vs its initial pool."""
    if initial_functional <= 0.0:
        return 1.0
    return max(0.0, float(state["functional_cells"]) / initial_functional)


def aggregate_organ_function(
    functions: dict[str, float],
    weights: dict[str, float],
    required: dict[str, float] | None = None,
    mode: str = "weighted_sum",
) -> float:
    """Aggregate normalized tissue functions into one organ function (pure)."""
    if mode not in VALID_AGGREGATIONS:
        raise ValueError(f"aggregation must be one of {VALID_AGGREGATIONS}, got {mode!r}")
    if not functions:
        raise ValueError("aggregate_organ_function of empty functions")
    if mode == "weighted_sum":
        total = sum(float(weights[tid]) for tid in functions)
        if total <= 0.0:
            raise ValueError("weights must sum to a positive value")
        return sum(float(functions[tid]) * float(weights[tid]) for tid in functions) / total
    if mode == "min_normalized":
        required = required or {}
        values = [float(functions[tid]) / float(required.get(tid, 1.0)) for tid in functions]
        return min(values)
    # weighted_geometric: zero in any member zeroes the organ (bottleneck).
    total = sum(float(weights[tid]) for tid in functions)
    if total <= 0.0:
        raise ValueError("weights must sum to a positive value")
    product = 1.0
    for tid in functions:
        product *= max(0.0, float(functions[tid])) ** (float(weights[tid]) / total)
    return product


def bottleneck_tissue(functions: dict[str, float]) -> str:
    """Id of the worst tissue; ties resolve by sorted tissue_id (pure)."""
    if not functions:
        raise ValueError("bottleneck_tissue of empty functions")
    return sorted(functions, key=lambda tid: (float(functions[tid]), tid))[0]


def evaluate_organ_snapshot(
    snapshot: dict[str, Any],
    thresholds: dict[str, float],
    vital_functions: dict[str, float],
) -> tuple[bool, list[str]]:
    """Check one organ snapshot against viability constraints (pure).

    Returns (viable, violations) with violation names from the organ cause
    vocabulary (e.g. ``"parenchyma_failure"``).
    """
    violations: list[str] = []
    if float(snapshot["organ_function"]) < thresholds["min_organ_function"]:
        violations.append("organ_function_failure")
    for tid, value in vital_functions.items():
        role = snapshot["tissue_roles"].get(tid, "")
        if float(value) < thresholds["min_vital_tissue_function"]:
            violations.append(_ROLE_TO_CAUSE.get(role, "organ_function_failure"))
    if float(snapshot["vascular_allocation_ratio"]) < thresholds["min_vascular_allocation_ratio"]:
        violations.append("vascular_capacity_failure")
    if float(snapshot["immune_allocation_ratio"]) < thresholds["min_immune_allocation_ratio"]:
        violations.append("immune_capacity_failure")
    if float(snapshot["organ_cancer_risk"]) > thresholds["max_organ_cancer_risk"]:
        violations.append("organ_cancer_risk")
    if float(snapshot["organ_fibrosis_index"]) > thresholds["max_organ_fibrosis_index"]:
        violations.append("organ_fibrosis")
    # Stage 4D supply-side checks. Defaults reproduce "no violation" on
    # snapshots that predate these fields (static capacities ratio 1.0,
    # healthy ECM, calm immunity, empty backlog).
    init_v = float(snapshot.get("initial_vascular_capacity", snapshot.get("current_vascular_capacity", 1.0)))
    init_i = float(snapshot.get("initial_immune_capacity", snapshot.get("current_immune_capacity", 1.0)))
    cur_v = float(snapshot.get("current_vascular_capacity", init_v))
    cur_i = float(snapshot.get("current_immune_capacity", init_i))
    capacity_ratio = min(
        cur_v / init_v if init_v > 0.0 else 1.0,
        cur_i / init_i if init_i > 0.0 else 1.0,
    )
    if capacity_ratio < thresholds["min_capacity_fraction"]:
        violations.append("capacity_exhaustion")
    if float(snapshot.get("min_vital_ecm_quality", 1.0)) < thresholds["min_vital_ecm_quality"]:
        violations.append("ecm_collapse")
    if int(snapshot.get("recovery_backlog", 0)) > thresholds["max_recovery_backlog"]:
        violations.append("recovery_debt")
    if float(snapshot.get("mean_vital_immune_pressure", 0.0)) > thresholds["max_mean_immune_pressure"]:
        violations.append("chronic_inflammatory_overload")
    # Deduplicate while preserving canonical cause order.
    ordered = [c for c in ORGAN_FAILURE_CAUSE_ORDER if c in violations]
    return (len(ordered) == 0, ordered)


def organ_failure_causality(
    trajectory: list[dict[str, Any]],
    thresholds: dict[str, float],
) -> dict[str, Any]:
    """First-violation causality over an organ trajectory (pure, non-mutating).

    Returns per-cause first times (``None`` when never violated),
    ``primary_organ_failure_cause`` (``"multiple_simultaneous"`` on ties,
    ``"none"`` when the organ stays viable) and the ordered
    ``organ_failure_cause_sequence``.
    """
    if not trajectory:
        raise ValueError("organ trajectory must be non-empty")
    first: dict[str, float | None] = {cause: None for cause in ORGAN_FAILURE_CAUSE_ORDER}
    for snapshot in trajectory:
        vital = {tid: info["tissue_function"] for tid, info in snapshot["tissues"].items() if info.get("is_vital")}
        _, violations = evaluate_organ_snapshot(snapshot, thresholds, vital)
        for cause in ORGAN_FAILURE_CAUSE_ORDER:
            if cause in violations and first[cause] is None:
                first[cause] = float(snapshot["time"])
    ordered = sorted(
        (c for c in ORGAN_FAILURE_CAUSE_ORDER if first[c] is not None),
        key=lambda c: (float(first[c]), ORGAN_FAILURE_CAUSE_ORDER.index(c)),  # type: ignore[arg-type]
    )
    if not ordered:
        primary = "none"
    elif len([c for c in ordered if float(first[c]) == float(first[ordered[0]])]) >= 2:  # type: ignore[arg-type]
        primary = "multiple_simultaneous"
    else:
        primary = ordered[0]
    result: dict[str, Any] = {
        "primary_organ_failure_cause": primary,
        "organ_failure_cause_sequence": list(ordered),
    }
    for cause in ORGAN_FAILURE_CAUSE_ORDER:
        result[f"first_{cause}_time"] = first[cause]
    return result


class OrganModel:
    """Executable composition of tissue modules with shared resources.

    Owns one :class:`TissueModel` per module (tissue dynamics are never
    reimplemented here), the shared capacities, and coordination. Determinism
    comes from per-module injected RNGs derived from the organ seed
    (``seed + module_index``); global random is never touched.
    """

    def __init__(self, config: "OrganConfig", seed: int | None = None):
        from longevity.model.organ_policy import (  # deferred: avoid import cycle
            RecoveryPolicy,
            validate_coordination,
            validate_score_weights,
        )

        self.config = config
        validate_coordination(config.coordination)
        self.seed = config.seed if seed is None else seed
        self.step_count = 0
        self.modules: list[dict[str, Any]] = []
        for index, module in enumerate(config.tissues):
            effective_params = dict(module.tissue_parameters)
            effective_params["dt"] = float(config.dt)
            model = TissueModel(
                state=TissueState.from_dict(module.initial_state),
                parameters=validate_tissue_parameters(effective_params),
                rng=Rng(self.seed + index),
            )
            self.modules.append(
                {
                    "config": module,
                    "model": model,
                    "policy": ReplacementPolicy.from_dict(module.policy),
                    "recovery_policy": RecoveryPolicy.from_dict(module.recovery),
                    "demand": validate_demand_coefficients(dict(module.demand_coefficients)),
                    "initial_functional": float(TissueState.from_dict(module.initial_state).functional_cells),
                }
            )
        self.thresholds = validate_organ_thresholds(dict(config.thresholds))
        self.score_weights = validate_score_weights(dict(config.coordination_params))
        self.temporal_model = validate_temporal_model(config.temporal_relief_model)
        self.temporal = validate_temporal_params(dict(config.temporal_params))
        self.recovery_model = validate_recovery_model(config.recovery_model)
        self.capacity = validate_capacity_dynamics(dict(config.capacity_dynamics))
        self.recovery_on = self.recovery_model == "decoupled_niche_recovery"
        self.current_vascular_capacity = float(config.shared_vascular_capacity)
        self.current_immune_capacity = float(config.shared_immune_capacity)
        self.relief_events: list[dict[str, Any]] = []
        self.capacity_events: list[dict[str, Any]] = []
        self.deferral_queue: list[dict[str, Any]] = []
        self.temporal_totals = _fresh_temporal_totals()
        self.recovery_totals = _fresh_recovery_totals()
        self.last_scale = 1.0

    # -- resource demand -------------------------------------------------
    @staticmethod
    def _module_demand(
        state: TissueState, demand: dict[str, float], replacement_activity: float
    ) -> tuple[float, float]:
        vascular = (
            demand["base_vascular_demand"]
            + state.functional_cells * demand["vascular_per_functional"]
            + state.damaged_cells * demand["vascular_per_damaged"]
            + state.senescent_cells * demand["vascular_per_senescent"]
            + max(0.0, replacement_activity) * demand["vascular_per_replacement"]
        )
        immune = (
            demand["base_immune_demand"]
            + state.damaged_cells * demand["immune_per_damaged"]
            + state.senescent_cells * demand["immune_per_senescent"]
            + state.cancer_risk * demand["immune_per_cancer_risk"]
            + state.fibrosis_index * demand["immune_per_fibrosis"]
            + max(0.0, replacement_activity) * demand["immune_per_replacement"]
        )
        return (vascular, immune)

    @staticmethod
    def _allocation_ratio(total_demand: float, capacity: float) -> float:
        if total_demand <= 0.0:
            return 1.0
        if capacity <= 0.0:
            return 0.0
        return min(1.0, capacity / total_demand)

    def _active_relief(self, step: int) -> dict[str, tuple[float, float]]:
        """Active (vascular, immune) demand offsets per tissue at ``step``."""
        offsets: dict[str, list[float]] = {entry["config"].tissue_id: [0.0, 0.0] for entry in self.modules}
        for event in self.relief_events:
            if event["effective_step"] <= step < event["effective_step"] + event["duration_steps"]:
                offsets[event["tissue_id"]][0] += float(event["vascular_relief"])
                offsets[event["tissue_id"]][1] += float(event["immune_relief"])
        return {tid: (pair[0], pair[1]) for tid, pair in offsets.items()}

    def _adjusted_demand(
        self,
        entry: dict[str, Any],
        state: TissueState,
        activity: float,
        offset: tuple[float, float],
    ) -> tuple[float, float]:
        raw_v, raw_i = self._module_demand(state, entry["demand"], activity)
        return (max(0.0, raw_v - offset[0]), max(0.0, raw_i - offset[1]))

    def _snapshot(
        self,
        time: float,
        demands: dict[str, tuple[float, float]],
        scale: float,
        detail: dict[str, Any] | None = None,
        executed_demands: dict[str, tuple[float, float]] | None = None,
        temporal_detail: dict[str, Any] | None = None,
        recovery_detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        functions: dict[str, float] = {}
        weights: dict[str, float] = {}
        required: dict[str, float] = {}
        tissues: dict[str, Any] = {}
        roles: dict[str, str] = {}
        for entry in self.modules:
            module = entry["config"]
            model = entry["model"]
            state = model.state.to_dict()
            functions[module.tissue_id] = tissue_function_value(state, entry["initial_functional"])
            weights[module.tissue_id] = float(module.weight)
            required[module.tissue_id] = float(module.required_function)
            roles[module.tissue_id] = module.role
            tissues[module.tissue_id] = {
                "role": module.role,
                "is_vital": bool(module.is_vital),
                "state": state,
                "tissue_function": functions[module.tissue_id],
                "replacement_events": model.replacement_events,
                "total_replaced_cells": float(model.total_replaced_cells),
            }
        organ_function = aggregate_organ_function(functions, weights, required, self.config.aggregation)
        total_vascular = sum(d[0] for d in demands.values())
        total_immune = sum(d[1] for d in demands.values())
        vascular_ratio = self._allocation_ratio(total_vascular, float(self.current_vascular_capacity))
        immune_ratio = self._allocation_ratio(total_immune, float(self.current_immune_capacity))
        executed = executed_demands or {}
        exec_vascular = sum(d[0] for d in executed.values())
        exec_immune = sum(d[1] for d in executed.values())
        if detail is None:
            from longevity.model.organ_policy import validate_coordination  # deferred: avoid import cycle

            detail = {
                "mode": validate_coordination(self.config.coordination),
                "scale": float(scale),
                "executed_tissues": [],
                "rejected_tissues": [],
                "partial_tissues": [],
                "scales": {},
                "scores": {},
                "score_values": {},
                "score_costs": {},
                "requested_tissues": [],
                "relief_cells": {},
            }
        snapshot = {
            "time": float(time),
            "organ_function": float(organ_function),
            "bottleneck_tissue": bottleneck_tissue(functions),
            "min_normalized_tissue_function": min(functions.values()),
            "organ_cancer_risk": max(float(m["model"].state.cancer_risk) for m in self.modules),
            "organ_fibrosis_index": max(float(m["model"].state.fibrosis_index) for m in self.modules),
            "total_vascular_demand": float(total_vascular),
            "total_immune_demand": float(total_immune),
            "executed_vascular_demand": float(exec_vascular),
            "executed_immune_demand": float(exec_immune),
            "vascular_allocation_ratio": float(vascular_ratio),
            "immune_allocation_ratio": float(immune_ratio),
            "vascular_shortfall": float(max(0.0, total_vascular - float(self.current_vascular_capacity))),
            "immune_shortfall": float(max(0.0, total_immune - float(self.current_immune_capacity))),
            "current_vascular_capacity": float(self.current_vascular_capacity),
            "current_immune_capacity": float(self.current_immune_capacity),
            "initial_vascular_capacity": float(self.config.shared_vascular_capacity),
            "initial_immune_capacity": float(self.config.shared_immune_capacity),
            "coordination_scale": float(scale),
            "coordination_detail": copy.deepcopy(detail),
            "temporal_detail": copy.deepcopy(temporal_detail) if temporal_detail is not None else self._empty_temporal_detail(),
            "recovery_detail": copy.deepcopy(recovery_detail) if recovery_detail is not None else self._empty_recovery_detail(),
            "tissue_roles": dict(roles),
            "tissues": tissues,
        }
        vital = {tid: info["tissue_function"] for tid, info in tissues.items() if info["is_vital"]}
        vital_ecm = [float(info["state"]["ecm_quality"]) for tid, info in tissues.items() if info["is_vital"]]
        vital_immune = [float(info["state"]["immune_pressure"]) for tid, info in tissues.items() if info["is_vital"]]
        snapshot["min_vital_ecm_quality"] = min(vital_ecm) if vital_ecm else 1.0
        snapshot["mean_vital_immune_pressure"] = (
            sum(vital_immune) / len(vital_immune) if vital_immune else 0.0
        )
        pending_recovery = sum(1 for e in self.capacity_events if not e.get("applied", False))
        queued_recovery = sum(1 for e in self.deferral_queue if e.get("kind", "replacement") == "recovery")
        snapshot["recovery_backlog"] = int(pending_recovery + queued_recovery)
        viable, violations = evaluate_organ_snapshot(snapshot, self.thresholds, vital)
        snapshot["organ_viable"] = bool(viable)
        snapshot["violations"] = list(violations)
        return snapshot

    def _apply_due_capacity_events(self, pre: int) -> None:
        """Apply matured capacity/ECM recovery events (Stage 4D)."""
        ceiling_v = float(self.config.shared_vascular_capacity) * float(self.capacity["capacity_ceiling_multiplier"])
        ceiling_i = float(self.config.shared_immune_capacity) * float(self.capacity["capacity_ceiling_multiplier"])
        for event in self.capacity_events:
            if event.get("applied", False) or int(event["effective_step"]) > pre:
                continue
            target = event["target"]
            magnitude = max(0.0, float(event["magnitude"]))
            if target == "vascular_capacity":
                headroom = max(0.0, ceiling_v - self.current_vascular_capacity)
                added = min(headroom, magnitude)
                self.current_vascular_capacity += added
                event["applied_amount"] = float(added)
            elif target == "immune_capacity":
                headroom = max(0.0, ceiling_i - self.current_immune_capacity)
                added = min(headroom, magnitude)
                self.current_immune_capacity += added
                event["applied_amount"] = float(added)
            elif target == "ecm_quality":
                tissue = next(m for m in self.modules if m["config"].tissue_id == event["tissue_id"])
                state = tissue["model"].state
                added = min(max(0.0, 1.0 - state.ecm_quality), magnitude)
                state.ecm_quality = max(0.0, min(1.0, state.ecm_quality + added))
                event["applied_amount"] = float(added)
                assert_tissue_invariants(state)
            else:  # pragma: no cover - validated at planning time
                raise ValueError(f"unknown recovery target {target!r}")
            event["applied"] = True
            self.recovery_totals["capacity_increase_realized"] += float(event["applied_amount"])

    def _create_capacity_event(
        self, tissue_id: str, target: str, magnitude: float, delay_steps: int, pre: int
    ) -> bool:
        """Create (or deterministically merge) a delayed capacity/ECM event.

        Returns True when merged into an existing pending event.
        """
        magnitude = max(0.0, float(magnitude))
        if magnitude <= 0.0:
            return False
        for pending in self.capacity_events:
            if (
                not pending.get("applied", False)
                and int(pending["effective_step"]) > pre
                and pending["tissue_id"] == tissue_id
                and pending["target"] == target
            ):
                pending["magnitude"] = float(pending["magnitude"]) + magnitude
                self.recovery_totals["recovery_merged_effects"] += 1
                self.recovery_totals["capacity_increase_created"] += magnitude
                return True
        self.capacity_events.append(
            {
                "tissue_id": tissue_id,
                "target": target,
                "created_step": pre,
                "effective_step": pre + int(delay_steps),
                "magnitude": magnitude,
                "applied": False,
                "applied_amount": 0.0,
                "token": f"{tissue_id}:{target}:{pre}",
            }
        )
        self.recovery_totals["capacity_increase_created"] += magnitude
        return False

    def _degrade_capacities(self, total_vascular: float, total_immune: float, total_senescent: float) -> None:
        """Erode dynamic capacities under load (Stage 4D; neutral when rates are 0)."""
        dt = float(self.config.dt)
        self.current_vascular_capacity = max(
            0.0,
            self.current_vascular_capacity
            - (float(self.capacity["vascular_degradation_rate"]) * total_vascular
               + float(self.capacity["vascular_senescent_rate"]) * total_senescent) * dt,
        )
        self.current_immune_capacity = max(
            0.0,
            self.current_immune_capacity
            - (float(self.capacity["immune_degradation_rate"]) * total_immune
               + float(self.capacity["immune_senescent_rate"]) * total_senescent) * dt,
        )

    def _recovery_headroom(self, tissue_id: str, target: str) -> float:
        """Usable headroom for a recovery effect (Stage 4D revalidation)."""
        if target == "vascular_capacity":
            ceiling = float(self.config.shared_vascular_capacity) * float(self.capacity["capacity_ceiling_multiplier"])
            return max(0.0, ceiling - self.current_vascular_capacity)
        if target == "immune_capacity":
            ceiling = float(self.config.shared_immune_capacity) * float(self.capacity["capacity_ceiling_multiplier"])
            return max(0.0, ceiling - self.current_immune_capacity)
        if target == "ecm_quality":
            tissue = next(m for m in self.modules if m["config"].tissue_id == tissue_id)
            return max(0.0, 1.0 - float(tissue["model"].state.ecm_quality))
        return 0.0

    @staticmethod
    def _empty_recovery_detail() -> dict[str, Any]:
        return {
            "recovery_model": "none",
            "recovery_planned": [],
            "recovery_executed": [],
            "recovery_executed_from_deferral": [],
            "recovery_deferred": [],
            "recovery_rejected": [],
            "recovery_expired": [],
            "recovery_merged": 0,
            "recovery_immediate_immune": 0.0,
            "recovery_immediate_vascular": 0.0,
        }

    @staticmethod
    def _empty_temporal_detail() -> dict[str, Any]:
        return {
            "temporal_model": "none",
            "spike_immune": 0.0,
            "spike_vascular": 0.0,
            "relief_created_immune": 0.0,
            "relief_created_vascular": 0.0,
            "relief_active_immune": 0.0,
            "relief_active_vascular": 0.0,
            "deferred_now": [],
            "executed_from_deferral": {},
            "defer_delays": {},
            "expired_now": [],
            "queue_length": 0,
        }

    # -- stepping ---------------------------------------------------------
    def step(self) -> dict[str, Any]:
        """Advance all modules by one organ step; returns the new snapshot."""
        from longevity.model.organ_policy import (  # deferred: avoid import cycle
            DEFERRAL_MODES,
            SELECTION_MODES,
            SUPPLY_MODES,
            deferral_candidates_for_step,
            disabled_policy,
            effective_policies_for_step,
            fraction_policy,
            global_cap_scale_factor,
            joint_action_score,
            lookahead_plan_score,
            plan_relief_score,
            selective_policies_for_step,
            validate_coordination,
        )

        mode = validate_coordination(self.config.coordination)
        pre = self.step_count
        temporal_on = self.temporal_model == "delayed_relief"
        recovery_on = self.recovery_on
        # 0. Mature relief events (realized/expired transitions at this step).
        for event in self.relief_events:
            if not event["realized"] and event["effective_step"] <= pre:
                event["realized"] = True
                self.temporal_totals["relief_realized_events"] += 1
                self.temporal_totals["relief_realized_amount"] += float(event["immune_relief"] + event["vascular_relief"])
            if not event["expired"] and event["effective_step"] + event["duration_steps"] <= pre:
                event["expired"] = True
                self.temporal_totals["relief_expired_events"] += 1
                self.temporal_totals["relief_expired_amount"] += float(event["immune_relief"] + event["vascular_relief"])
        # 0b. Mature capacity/ECM recovery events (Stage 4D only).
        if recovery_on:
            self._apply_due_capacity_events(pre)
        offsets = self._active_relief(pre) if temporal_on else {}
        # 1. Requested plans (pure). Organ-phase requests feed demands and the
        # Stage 4A scale modes (bit-identical 4A behavior); tissue-phase
        # requests match what TissueModel executes and feed selection.
        requested = [entry["policy"].plan(entry["model"].state, entry["model"].parameters, self.step_count) for entry in self.modules]
        phase = [entry["policy"].plan(entry["model"].state, entry["model"].parameters, self.step_count + 1) for entry in self.modules]
        tissue_ids = [entry["config"].tissue_id for entry in self.modules]
        # Recovery candidates use the tissue-phase counter, like replacement.
        recovery_plans: dict[str, Any] = {}
        if recovery_on:
            from longevity.model.organ_policy import plan_recovery_action  # deferred: avoid import cycle

            for entry in self.modules:
                tid = entry["config"].tissue_id
                plan = plan_recovery_action(entry["recovery_policy"], tid, self.step_count + 1)
                if float(plan.magnitude) > 0.0:
                    recovery_plans[tid] = plan
                    self.recovery_totals["recovery_planned_events"] += 1

        def _demand(entry: dict[str, Any], activity: float) -> tuple[float, float]:
            off = offsets.get(entry["config"].tissue_id, (0.0, 0.0))
            return self._adjusted_demand(entry, entry["model"].state, activity, off)

        demands = {entry["config"].tissue_id: _demand(entry, plan.target_count) for entry, plan in zip(self.modules, requested)}
        base_demands = {entry["config"].tissue_id: _demand(entry, 0.0) for entry in self.modules}
        total_vascular = sum(d[0] for d in demands.values())
        total_immune = sum(d[1] for d in demands.values())
        # 2. Coordination decides execution policies (never mutates base ones).
        # Scores and selection always use tissue-phase plans (what will run).
        scores = {
            entry["config"].tissue_id: plan_relief_score(
                plan, entry["model"].state, entry["demand"], self.score_weights
            )["score"]
            for entry, plan in zip(self.modules, phase)
        }
        from_deferral: dict[str, bool] = {}
        defer_delays: dict[str, float] = {}
        expired_now: list[str] = []
        deferred_now: list[str] = []
        rec_expired_step: list[str] = []
        rec_detail = self._empty_recovery_detail()
        rec_detail["recovery_model"] = self.recovery_model
        rec_imm_now = rec_vasc_now = 0.0
        accepted_recovery_imm: dict[str, float] = {}
        accepted_recovery_vasc: dict[str, float] = {}
        if mode in SUPPLY_MODES:
            # 2s. Joint supply-demand path (Stage 4D): rank replacement and
            # recovery actions together, then execute / prune / defer.
            from longevity.model.organ_policy import (  # deferred: avoid import cycle
                joint_action_score,
                lookahead_plan_score,
                plan_relief_score as _relief_score,
                rank_plan_scores,
            )

            # Due queue pop (both kinds; expiry counts per kind).
            due_repl: dict[str, list[dict[str, Any]]] = {tid: [] for tid in tissue_ids}
            due_rec: dict[str, list[dict[str, Any]]] = {tid: [] for tid in tissue_ids}
            kept_queue2: list[dict[str, Any]] = []
            for queued in self.deferral_queue:
                kind = queued.get("kind", "replacement")
                if queued["defer_until_step"] <= pre:
                    if pre - queued["original_step"] > int(self.temporal["deferred_plan_max_age"]):
                        expired_now.append(queued["tissue_id"])
                        if kind == "recovery":
                            self.recovery_totals["expired_deferred_recovery"] += 1
                            rec_expired_step.append(queued["tissue_id"])
                        else:
                            self.temporal_totals["expired_deferred_plan_count"] += 1
                    elif kind == "recovery":
                        due_rec[queued["tissue_id"]].append(queued)
                    else:
                        due_repl[queued["tissue_id"]].append(queued)
                else:
                    kept_queue2.append(queued)
            self.deferral_queue = kept_queue2
            # Replacement candidates: due merged + fresh, revalidated vs pool.
            repl_candidates: dict[str, float] = {}
            repl_pools: dict[str, float] = {}
            repl_due_originals: dict[str, list[int]] = {}
            for entry, plan in zip(self.modules, phase):
                tid = entry["config"].tissue_id
                pool_name = {"damaged": "damaged_cells", "senescent": "senescent_cells"}.get(entry["policy"].target)
                pool = float(getattr(entry["model"].state, pool_name, 0.0)) if pool_name else 0.0
                total = sum(float(e.get("count", 0.0)) for e in due_repl[tid]) + max(0.0, float(plan.target_count))
                if total > 0.0:
                    repl_candidates[tid] = min(total, pool) if pool > 0.0 else 0.0
                    repl_pools[tid] = pool
                    repl_due_originals[tid] = [int(e["original_step"]) for e in due_repl[tid]]
            cap_scale = global_cap_scale_factor([float(p.target_count) for p in phase], self.config.global_replacement_cap)
            for tid in repl_candidates:
                repl_candidates[tid] *= cap_scale
            # Recovery candidates: fresh due plans + due queue, merged by target.
            rec_candidates: dict[str, dict[str, Any]] = {}
            for entry in self.modules:
                tid = entry["config"].tissue_id
                if tid in recovery_plans:
                    plan = recovery_plans[tid]
                    rec_candidates[tid] = {
                        "target": plan.target, "magnitude": float(plan.magnitude),
                        "delay_steps": int(plan.delay_steps),
                        "imm_mult": float(entry["recovery_policy"].immediate_immune_multiplier),
                        "vasc_mult": float(entry["recovery_policy"].immediate_vascular_multiplier),
                        "due_originals": [],
                    }
            for tid, entries in due_rec.items():
                if not entries:
                    continue
                totals: dict[str, float] = {}
                originals: list[int] = []
                for e in entries:
                    totals[e["target"]] = totals.get(e["target"], 0.0) + float(e.get("magnitude", e.get("count", 0.0)))
                    originals.append(int(e["original_step"]))
                if tid in rec_candidates and rec_candidates[tid]["target"] in totals:
                    totals[rec_candidates[tid]["target"]] += rec_candidates[tid]["magnitude"]
                # One recovery action per tissue per step: keep the largest target pile.
                target = max(totals, key=lambda t: (totals[t], t))
                rec_candidates[tid] = {
                    "target": target, "magnitude": float(totals[target]),
                    "delay_steps": int(entries[0].get("delay_steps", 5)),
                    "imm_mult": float(entries[0].get("imm_mult", 1.0)),
                    "vasc_mult": float(entries[0].get("vasc_mult", 1.0)),
                    "due_originals": originals,
                }
            # Joint ranking.
            repl_scores: dict[str, float] = {}
            repl_values: dict[str, float] = {}
            for entry, plan in zip(self.modules, phase):
                tid = entry["config"].tissue_id
                if tid not in repl_candidates or repl_candidates[tid] <= 0.0:
                    continue
                if mode == "lookahead_supply_demand":
                    assessed = lookahead_plan_score(
                        plan, entry["model"].state, entry["demand"], self.score_weights, self.temporal,
                        discount=float(self.temporal["lookahead_discount"]),
                    )
                    repl_scores[tid] = assessed["score"]
                    repl_values[tid] = assessed["lookahead_value"]
                else:
                    assessed = _relief_score(plan, entry["model"].state, entry["demand"], self.score_weights)
                    repl_scores[tid] = assessed["score"]
                    repl_values[tid] = assessed["value"]
            rec_scores: dict[str, float] = {}
            rec_values: dict[str, float] = {}
            for tid, cand in rec_candidates.items():
                if mode == "lookahead_supply_demand":
                    future = float(cand["magnitude"]) * (float(self.temporal["lookahead_discount"]) ** int(cand["delay_steps"]))
                    value = future
                else:
                    value = float(self.score_weights.get("supply_beta", 1.0)) * float(cand["magnitude"])
                imm_need = float(cand["magnitude"]) * float(cand["imm_mult"])
                vasc_need = float(cand["magnitude"]) * float(cand["vasc_mult"])
                rec_scores[tid] = joint_action_score(value, imm_need, vasc_need, self.score_weights)["score"]
                rec_values[tid] = value
            joint_order = rank_plan_scores({
                **{f"replacement:{tid}": repl_scores[tid] for tid in repl_scores},
                **{f"recovery:{tid}": rec_scores[tid] for tid in rec_scores},
            })
            # Needs (immediate) per action.
            def _repl_needs(tid: str) -> tuple[float, float]:
                entry = next(e for e in self.modules if e["config"].tissue_id == tid)
                count = max(0.0, repl_candidates.get(tid, 0.0))
                v_need = count * entry["demand"]["vascular_per_replacement"]
                i_need = count * entry["demand"]["immune_per_replacement"]
                if temporal_on:
                    v_need += count * float(self.temporal["immediate_vascular_cost_multiplier"]) * entry["demand"]["vascular_per_replacement"]
                    i_need += count * float(self.temporal["immediate_immune_cost_multiplier"]) * entry["demand"]["immune_per_replacement"]
                return (v_need, i_need)

            def _rec_needs(tid: str) -> tuple[float, float]:
                cand = rec_candidates[tid]
                return (
                    float(cand["magnitude"]) * float(cand["vasc_mult"]),
                    float(cand["magnitude"]) * float(cand["imm_mult"]),
                )

            floor = float(self.temporal["defer_allocation_threshold"])
            kept_v = sum(d[0] for d in base_demands.values())
            kept_i = sum(d[1] for d in base_demands.values())
            exec_repl: dict[str, float] = {}
            exec_rec: dict[str, dict[str, Any]] = {}
            rej_repl: list[str] = []
            rej_rec: list[str] = []
            partial_repl: list[str] = []
            deferred_actions: list[tuple[str, str, float]] = []  # (kind, tid, count_or_magnitude)

            def _predicted_ok(v_need: float, i_need: float) -> bool:
                pred_v = min(1.0, self.current_vascular_capacity / (kept_v + v_need)) if kept_v + v_need > 0 else 1.0
                pred_i = min(1.0, self.current_immune_capacity / (kept_i + i_need)) if kept_i + i_need > 0 else 1.0
                return min(pred_v, pred_i) >= floor

            if mode == "independent_all":
                for tid in sorted(repl_candidates):
                    if repl_candidates[tid] > 0.0:
                        exec_repl[tid] = repl_candidates[tid]
                        kept_v += _repl_needs(tid)[0]
                        kept_i += _repl_needs(tid)[1]
                for tid in sorted(rec_candidates):
                    exec_rec[tid] = rec_candidates[tid]
            else:
                stopped = False
                for action in joint_order:
                    kind, tid = action.split(":", 1)
                    if kind == "replacement":
                        if tid not in repl_candidates or repl_candidates[tid] <= 0.0:
                            continue
                        v_need, i_need = _repl_needs(tid)
                        if _predicted_ok(v_need, i_need):
                            exec_repl[tid] = repl_candidates[tid]
                            kept_v += v_need
                            kept_i += i_need
                        elif mode == "deferral_supply_demand":
                            deferred_actions.append((kind, tid, repl_candidates[tid]))
                        else:
                            # Pruning modes: partial the first non-fitting
                            # replacement, reject the rest.
                            if not stopped:
                                fill_v = (self.current_vascular_capacity - kept_v) / v_need if v_need > 0 else 1.0
                                fill_i = (self.current_immune_capacity - kept_i) / i_need if i_need > 0 else 1.0
                                fill = max(0.0, min(1.0, fill_v, fill_i))
                                if fill > 0.0:
                                    exec_repl[tid] = repl_candidates[tid] * fill
                                    partial_repl.append(tid)
                                    kept_v += v_need * fill
                                    kept_i += i_need * fill
                                else:
                                    rej_repl.append(tid)
                                stopped = True
                            else:
                                rej_repl.append(tid)
                    else:
                        if tid not in rec_candidates:
                            continue
                        v_need, i_need = _rec_needs(tid)
                        if _predicted_ok(v_need, i_need):
                            exec_rec[tid] = rec_candidates[tid]
                            kept_v += v_need
                            kept_i += i_need
                        elif mode == "deferral_supply_demand":
                            deferred_actions.append((kind, tid, 0.0))
                        else:
                            rej_rec.append(tid)
                if mode in ("supply_demand_greedy", "lookahead_supply_demand") and not exec_repl and not exec_rec:
                    # Floor: top-ranked action executes (never fully idle).
                    top = joint_order[0] if joint_order else None
                    if top is not None:
                        kind, tid = top.split(":", 1)
                        if kind == "replacement" and tid in repl_candidates and repl_candidates[tid] > 0.0:
                            exec_repl[tid] = repl_candidates[tid]
                            if tid in rej_repl:
                                rej_repl.remove(tid)
                        elif kind == "recovery" and tid in rec_candidates:
                            exec_rec[tid] = rec_candidates[tid]
                            if tid in rej_rec:
                                rej_rec.remove(tid)
            # Build effective replacement policies.
            effective = []
            accepted_counts = {}
            for entry in self.modules:
                tid = entry["config"].tissue_id
                if tid in exec_repl:
                    count = exec_repl[tid]
                    pool_name = {"damaged": "damaged_cells", "senescent": "senescent_cells"}.get(entry["policy"].target)
                    pool = float(getattr(entry["model"].state, pool_name, 0.0)) if pool_name else 0.0
                    effective.append(fraction_policy(entry["policy"], count, pool, "organ"))
                    accepted_counts[tid] = count
                    if due_repl[tid]:
                        from_deferral[tid] = True
                        defer_delays[tid] = float(pre - min(
                            [int(e["original_step"]) for e in due_repl[tid]] + [pre]))
                        self.temporal_totals["executed_after_deferral_count"] += 1
                        self.temporal_totals["defer_delays_sum"] += defer_delays[tid]
                        self.temporal_totals["defer_delays_count"] += 1
                    else:
                        from_deferral[tid] = False
                else:
                    effective.append(disabled_policy(entry["policy"], "organ"))
                    accepted_counts[tid] = 0.0
                    from_deferral[tid] = False
            # Joint ranking scores for metrics (filled; attached to info below).
            joint_scores: dict[str, float] = {}
            for action in joint_order:
                akind, atid = action.split(":", 1)
                if akind == "replacement":
                    joint_scores[action] = float(repl_scores.get(atid, 0.0))
                else:
                    joint_scores[action] = float(rec_scores.get(atid, 0.0))
            for kind, tid, _count in deferred_actions:
                if kind == "replacement":
                    originals = repl_due_originals.get(tid, []) + [pre]
                    self.deferral_queue.append({
                        "kind": "replacement",
                        "tissue_id": tid,
                        "original_step": min(originals),
                        "defer_until_step": pre + int(self.temporal["defer_steps"]),
                        "count": float(repl_candidates.get(tid, 0.0)),
                        "target": str(next(e for e in self.modules if e["config"].tissue_id == tid)["policy"].target),
                        "score_snapshot": 0.0,
                        "reason": "supply_guard",
                        "token": f"{tid}:{pre}",
                    })
                    self.temporal_totals["deferred_plan_count"] += 1
                    deferred_now.append(tid)
                else:
                    cand = rec_candidates[tid]
                    due_entries = due_rec.get(tid, [])
                    originals = [int(e["original_step"]) for e in due_entries] + [pre]
                    self.deferral_queue.append({
                        "kind": "recovery",
                        "tissue_id": tid,
                        "original_step": min(originals),
                        "defer_until_step": pre + int(self.temporal["defer_steps"]),
                        "count": 0.0,
                        "magnitude": float(cand["magnitude"]),
                        "target": str(cand["target"]),
                        "delay_steps": int(cand["delay_steps"]),
                        "imm_mult": float(cand["imm_mult"]),
                        "vasc_mult": float(cand["vasc_mult"]),
                        "score_snapshot": 0.0,
                        "reason": "supply_guard",
                        "token": f"{tid}:rec:{pre}",
                    })
                    self.recovery_totals["recovery_deferred_events"] = int(self.recovery_totals.get("recovery_deferred_events", 0)) + 1
                    deferred_now.append(tid)
            self.deferral_queue.sort(key=lambda e: (int(e["defer_until_step"]), str(e["tissue_id"]), str(e["token"])))
            self.temporal_totals["max_defer_queue_length"] = max(
                self.temporal_totals["max_defer_queue_length"], len(self.deferral_queue)
            )
            # Execute accepted recovery actions now (immediate cost + event).
            # No headroom means the effect would be wasted: re-defer instead.
            rec_from_due: set[str] = set()
            rec_deferred_headroom: list[str] = []
            for tid, cand in exec_rec.items():
                if self._recovery_headroom(tid, str(cand["target"])) <= 0.0:
                    self.deferral_queue.append({
                        "kind": "recovery",
                        "tissue_id": tid,
                        "original_step": pre,
                        "defer_until_step": pre + int(self.temporal["defer_steps"]),
                        "count": 0.0,
                        "magnitude": float(cand["magnitude"]),
                        "target": str(cand["target"]),
                        "delay_steps": int(cand["delay_steps"]),
                        "imm_mult": float(cand["imm_mult"]),
                        "vasc_mult": float(cand["vasc_mult"]),
                        "score_snapshot": 0.0,
                        "reason": "no_headroom",
                        "token": f"{tid}:rec:{pre}",
                    })
                    self.recovery_totals["recovery_deferred_events"] = int(self.recovery_totals.get("recovery_deferred_events", 0)) + 1
                    rec_deferred_headroom.append(tid)
                    continue
                rec_imm_now = float(cand["magnitude"]) * float(cand["imm_mult"])
                rec_vasc_now = float(cand["magnitude"]) * float(cand["vasc_mult"])
                accepted_recovery_imm[tid] = rec_imm_now
                accepted_recovery_vasc[tid] = rec_vasc_now
                merged = self._create_capacity_event(tid, str(cand["target"]), float(cand["magnitude"]),
                                            int(cand["delay_steps"]), pre)
                rec_detail["recovery_merged"] = int(rec_detail["recovery_merged"]) + (1 if merged else 0)
                self.recovery_totals["recovery_executed_events"] += 1
                self.recovery_totals["recovery_immediate_immune_cost"] += rec_imm_now
                self.recovery_totals["recovery_immediate_vascular_cost"] += rec_vasc_now
                if due_rec.get(tid):
                    defer_delays[tid] = float(pre - min([int(e["original_step"]) for e in due_rec[tid]]))
                    self.recovery_totals["executed_after_deferral_recovery"] = int(
                        self.recovery_totals.get("executed_after_deferral_recovery", 0)) + 1
                    self.temporal_totals["defer_delays_sum"] += defer_delays[tid]
                    self.temporal_totals["defer_delays_count"] += 1
                    rec_from_due.add(tid)
                    self.temporal_totals["defer_delays_sum"] += defer_delays[tid]
                    self.temporal_totals["defer_delays_count"] += 1
            # Rejected recovery accounting.
            for tid in rej_rec:
                self.recovery_totals["recovery_rejected_events"] = int(self.recovery_totals.get("recovery_rejected_events", 0)) + 1
            for tid in rec_deferred_headroom:
                if tid in exec_rec:
                    del exec_rec[tid]
            # Headroom-aware due recovery is handled inline above via queue;
            # direct-execution headroom check trims to available headroom.
            requested_total = sum(max(0.0, float(p.target_count)) for p in phase)
            scale = 1.0
            partial_scales = {
                tid: (exec_repl[tid] / repl_candidates[tid] if repl_candidates.get(tid, 0.0) > 0.0 else 0.0)
                for tid in partial_repl
            }
            info = {
                "mode": mode,
                "scale": float(scale),
                "executed_tissues": sorted(exec_repl),
                "rejected_tissues": sorted(rej_repl),
                "partial_tissues": sorted(partial_repl),
                "scales": {tid: float(partial_scales.get(tid, 1.0 if tid in exec_repl else 0.0)) for tid in tissue_ids},
                "scores": {tid: float(repl_scores.get(tid, 0.0)) for tid in tissue_ids},
                "score_values": {},
                "score_costs": {},
                "requested_tissues": sorted(set(list(repl_candidates) + [t for t in rec_candidates])),
                "joint_scores": dict(joint_scores),
                "_supply_exec_rec": {tid: dict(c) for tid, c in exec_rec.items()},
                "_supply_rej_rec": list(rej_rec),
                "_supply_joint_order": list(joint_order),
            }
            rec_detail["recovery_planned"] = sorted(recovery_plans)
            rec_detail["recovery_executed"] = sorted(exec_rec)
            rec_detail["recovery_executed_from_deferral"] = sorted(rec_from_due)
            rec_detail["recovery_rejected"] = sorted(rej_rec)
            rec_detail["recovery_expired"] = sorted(rec_expired_step)
            rec_detail["recovery_immediate_immune"] = float(sum(accepted_recovery_imm.values()))
            rec_detail["recovery_immediate_vascular"] = float(sum(accepted_recovery_vasc.values()))
            rec_detail["recovery_deferred"] = sorted(
                {tid for kind, tid, _ in deferred_actions if kind == "recovery"} | set(rec_deferred_headroom))
        elif mode in DEFERRAL_MODES:
            # 2a. Non-destructive path: merge due-deferred with fresh plans,
            # revalidate against current pools, defer (never silently drop).
            due: dict[str, list[dict[str, Any]]] = {tid: [] for tid in tissue_ids}
            kept_queue: list[dict[str, Any]] = []
            for queued in self.deferral_queue:
                if queued.get("kind", "replacement") != "replacement":
                    # Recovery entries never belong to the 4C replacement-only
                    # path; keep them queued untouched.
                    kept_queue.append(queued)
                    continue
                if queued["defer_until_step"] <= pre:
                    if pre - queued["original_step"] > int(self.temporal["deferred_plan_max_age"]):
                        expired_now.append(queued["tissue_id"])
                        self.temporal_totals["expired_deferred_plan_count"] += 1
                    else:
                        due[queued["tissue_id"]].append(queued)
                else:
                    kept_queue.append(queued)
            self.deferral_queue = kept_queue
            candidates: dict[str, float] = {}
            candidate_pools: dict[str, float] = {}
            merged_originals: dict[str, list[int]] = {}
            for entry, plan in zip(self.modules, phase):
                tid = entry["config"].tissue_id
                # Pool follows the tissue's stable policy target (not the
                # transient fresh plan, which may be empty off-schedule).
                policy_target = entry["policy"].target
                pool_name = {"damaged": "damaged_cells", "senescent": "senescent_cells"}.get(policy_target)
                pool = float(getattr(entry["model"].state, pool_name, 0.0)) if pool_name else 0.0
                total = sum(float(e["count"]) for e in due[tid]) + max(0.0, float(plan.target_count))
                if total > 0.0:
                    candidates[tid] = min(total, pool) if pool > 0.0 else 0.0
                    candidate_pools[tid] = pool
                    merged_originals[tid] = [int(e["original_step"]) for e in due[tid]] + ([pre] if float(plan.target_count) > 0.0 else [])
            cap_scale = global_cap_scale_factor([float(p.target_count) for p in phase], self.config.global_replacement_cap)
            for tid in candidates:
                candidates[tid] *= cap_scale
            policy_targets = {entry["config"].tissue_id: str(entry["policy"].target) for entry in self.modules}
            ranker = "lookahead" if mode == "hybrid_lookahead_deferral" else "relief"
            rank_scores: dict[str, float] = {}
            for entry, plan in zip(self.modules, phase):
                tid = entry["config"].tissue_id
                if ranker == "lookahead":
                    rank_scores[tid] = lookahead_plan_score(
                        plan, entry["model"].state, entry["demand"], self.score_weights, self.temporal,
                        discount=float(self.temporal["lookahead_discount"]),
                    )["score"]
                else:
                    rank_scores[tid] = scores[tid]
            needs = {
                tid: max(0.0, candidates.get(tid, 0.0)) * entry["demand"]["immune_per_replacement"]
                for entry in self.modules
                for tid in [entry["config"].tissue_id]
            }
            split = deferral_candidates_for_step(
                tissue_ids,
                {tid: candidates.get(tid, 0.0) for tid in tissue_ids},
                rank_scores,
                sum(d[1] for d in base_demands.values()),
                float(self.current_immune_capacity),
                needs,
                float(self.temporal["defer_allocation_threshold"]),
                int(self.temporal["defer_steps"]),
                pre,
            )
            effective = []
            accepted_counts = {}
            for entry in self.modules:
                tid = entry["config"].tissue_id
                if tid in split["execute_now"]:
                    count = split["execute_now"][tid]
                    effective.append(fraction_policy(entry["policy"], count, candidate_pools.get(tid, 0.0), "organ"))
                    accepted_counts[tid] = count
                    if due[tid]:
                        from_deferral[tid] = True
                        defer_delays[tid] = float(pre - min(
                            [int(e["original_step"]) for e in due[tid]] + [pre]))
                        self.temporal_totals["executed_after_deferral_count"] += 1
                        self.temporal_totals["defer_delays_sum"] += defer_delays[tid]
                        self.temporal_totals["defer_delays_count"] += 1
                    else:
                        from_deferral[tid] = False
                else:
                    effective.append(disabled_policy(entry["policy"], "organ"))
                    accepted_counts[tid] = 0.0
                    from_deferral[tid] = False
            for tid, deferred in split["defer"].items():
                self.deferral_queue.append(
                    {
                        "tissue_id": tid,
                        "original_step": min(merged_originals.get(tid, [pre])),
                        "defer_until_step": int(deferred["defer_until_step"]),
                        "count": float(deferred["count"]),
                        "target": policy_targets[tid],
                        "score_snapshot": float(rank_scores.get(tid, 0.0)),
                        "reason": "capacity_guard",
                        "token": f"{tid}:{pre}",
                    }
                )
                self.temporal_totals["deferred_plan_count"] += 1
                deferred_now.append(tid)
            for entry in self.modules:
                # Due plans whose pool is temporarily empty are re-queued,
                # never silently dropped (senescence may regrow later).
                tid = entry["config"].tissue_id
                if due[tid] and candidates.get(tid, 0.0) <= 0.0:
                    self.deferral_queue.append(
                        {
                            "tissue_id": tid,
                            "original_step": min(merged_originals.get(tid, [pre])),
                            "defer_until_step": pre + int(self.temporal["defer_steps"]),
                            "count": sum(float(e["count"]) for e in due[tid]),
                            "target": policy_targets[tid],
                            "score_snapshot": float(rank_scores.get(tid, 0.0)),
                            "reason": "pool_empty",
                            "token": f"{tid}:{pre}",
                        }
                    )
                    self.temporal_totals["deferred_plan_count"] += 1
                    deferred_now.append(tid)
            # Re-sort queue deterministically.
            self.deferral_queue.sort(key=lambda e: (int(e["defer_until_step"]), str(e["tissue_id"]), str(e["token"])))
            self.temporal_totals["max_defer_queue_length"] = max(
                self.temporal_totals["max_defer_queue_length"], len(self.deferral_queue)
            )
            scale_counts = [accepted_counts.get(tid, 0.0) for tid in tissue_ids]
            requested_total = sum(max(0.0, float(p.target_count)) for p in phase)
            scale = (sum(scale_counts) / requested_total) if requested_total > 0.0 else 1.0
            info = {
                "mode": mode,
                "scale": float(scale),
                "executed_tissues": sorted(t for t in split["execute_now"]),
                "rejected_tissues": [],
                "partial_tissues": [],
                "scales": {tid: 1.0 if tid in split["execute_now"] else 0.0 for tid in tissue_ids},
                "scores": {tid: float(rank_scores.get(tid, scores[tid])) for tid in tissue_ids},
                "score_values": {},
                "score_costs": {},
                "requested_tissues": sorted(candidates),
            }
        elif mode in SELECTION_MODES or mode == "lookahead_priority":
            rank_override = None
            if mode == "lookahead_priority":
                rank_override = {
                    entry["config"].tissue_id: lookahead_plan_score(
                        plan, entry["model"].state, entry["demand"], self.score_weights, self.temporal,
                        discount=float(self.temporal["lookahead_discount"]),
                    )["score"]
                    for entry, plan in zip(self.modules, phase)
                }
            effective, info = selective_policies_for_step(
                [entry["policy"] for entry in self.modules],
                tissue_ids,
                [entry["model"].state for entry in self.modules],
                [entry["demand"] for entry in self.modules],
                [float(plan.target_count) for plan in phase],
                phase,
                sum(d[0] for d in base_demands.values()),
                float(self.current_vascular_capacity),
                sum(d[1] for d in base_demands.values()),
                float(self.current_immune_capacity),
                mode if mode in SELECTION_MODES else "demand_relief_priority",
                self.config.global_replacement_cap,
                self.score_weights,
                rank_scores=rank_override,
            )
            # selective() always reports its own mode; restore the true one.
            info = dict(info)
            info["mode"] = mode
            if rank_override is not None:
                info["scores"] = {tid: float(rank_override[tid]) for tid in tissue_ids}
            accepted_counts = {
                tid: (float(plan.target_count) * float(info["scales"].get(tid, 1.0)) if tid in set(info["executed_tissues"]) else 0.0)
                for tid, plan in zip(tissue_ids, phase)
            }
            scale = float(info["scale"])
            for tid in tissue_ids:
                from_deferral[tid] = False
        else:
            effective, scale = effective_policies_for_step(
                [entry["policy"] for entry in self.modules],
                tissue_ids,
                total_vascular,
                float(self.current_vascular_capacity),
                total_immune,
                float(self.current_immune_capacity),
                mode,
                self.config.global_replacement_cap,
                [float(plan.target_count) for plan in requested],
            )
            accepted_counts = {tid: float(plan.target_count) * scale for tid, plan in zip(tissue_ids, phase)}
            requested_tissues = sorted(tid for tid, plan in zip(tissue_ids, phase) if float(plan.target_count) > 0.0)
            executed_set = set(t for t in requested_tissues if scale > 0.0)
            info = {
                "mode": mode,
                "scale": float(scale),
                "executed_tissues": sorted(executed_set),
                "rejected_tissues": sorted(set(requested_tissues) - executed_set),
                "partial_tissues": sorted(t for t in executed_set if scale < 1.0 - 1e-12),
                "scales": {tid: float(scale) for tid in tissue_ids},
                "scores": {tid: float(scores[tid]) for tid in tissue_ids},
                "score_values": {},
                "score_costs": {},
                "requested_tissues": requested_tissues,
            }
            for tid in tissue_ids:
                from_deferral[tid] = False
        # 2b. Legacy modes coordinate replacement only; recovery (Stage 4D)
        # executes independently and in full when enabled.
        if recovery_on and mode not in SUPPLY_MODES:
            for tid, plan in recovery_plans.items():
                imm_now = float(plan.magnitude) * float(
                    next(e for e in self.modules if e["config"].tissue_id == tid)["recovery_policy"].immediate_immune_multiplier)
                vasc_now = float(plan.magnitude) * float(
                    next(e for e in self.modules if e["config"].tissue_id == tid)["recovery_policy"].immediate_vascular_multiplier)
                merged = self._create_capacity_event(tid, plan.target, float(plan.magnitude), int(plan.delay_steps), pre)
                if merged:
                    rec_detail["recovery_merged"] = int(rec_detail["recovery_merged"]) + 1
                self.recovery_totals["recovery_executed_events"] += 1
                self.recovery_totals["recovery_immediate_immune_cost"] += imm_now
                self.recovery_totals["recovery_immediate_vascular_cost"] += vasc_now
                accepted_recovery_imm[tid] = imm_now
                accepted_recovery_vasc[tid] = vasc_now
                rec_detail["recovery_executed"].append(tid)
                rec_detail["recovery_immediate_immune"] = float(rec_detail["recovery_immediate_immune"]) + imm_now
                rec_detail["recovery_immediate_vascular"] = float(rec_detail["recovery_immediate_vascular"]) + vasc_now
            rec_detail["recovery_planned"] = sorted(recovery_plans)
        self.last_scale = float(scale)
        # 3. Immediate costs ride on accepted activity: the temporal
        # replacement spike (temporal model only) plus recovery immediate
        # costs (intrinsic to decoupled recovery).
        # Per-tissue shares keep per-tissue demands consistent; organ
        # totals below add the same amounts exactly once.
        spike_by_tissue: dict[str, tuple[float, float]] = {}
        spike_v = spike_i = 0.0
        rec_imm_by_tissue: dict[str, float] = {}
        rec_vasc_by_tissue: dict[str, float] = {}
        if recovery_on:
            for tid in rec_detail["recovery_executed"]:
                entry = next(e for e in self.modules if e["config"].tissue_id == tid)
                plan = recovery_plans.get(tid)
                if plan is None:
                    continue
                rec_imm_by_tissue[tid] = float(plan.magnitude) * float(entry["recovery_policy"].immediate_immune_multiplier)
                rec_vasc_by_tissue[tid] = float(plan.magnitude) * float(entry["recovery_policy"].immediate_vascular_multiplier)
        if temporal_on:
            for entry in self.modules:
                tid = entry["config"].tissue_id
                activity = max(0.0, accepted_counts.get(tid, 0.0))
                share_v = activity * float(self.temporal["immediate_vascular_cost_multiplier"]) * entry["demand"]["vascular_per_replacement"]
                share_i = activity * float(self.temporal["immediate_immune_cost_multiplier"]) * entry["demand"]["immune_per_replacement"]
                spike_by_tissue[tid] = (share_v, share_i)
                spike_v += share_v
                spike_i += share_i
            self.temporal_totals["immediate_immune_cost_total"] += spike_i
            self.temporal_totals["immediate_vascular_cost_total"] += spike_v
            self.temporal_totals["peak_immediate_immune_demand"] = max(self.temporal_totals["peak_immediate_immune_demand"], spike_i)
            self.temporal_totals["peak_immediate_vascular_demand"] = max(self.temporal_totals["peak_immediate_vascular_demand"], spike_v)
        final_demands = {
            tid: (
                demands[tid][0] + spike_by_tissue.get(tid, (0.0, 0.0))[0] + accepted_recovery_vasc.get(tid, 0.0),
                demands[tid][1] + spike_by_tissue.get(tid, (0.0, 0.0))[1] + accepted_recovery_imm.get(tid, 0.0),
            )
            for tid in tissue_ids
        }
        total_vascular_final = sum(d[0] for d in final_demands.values())
        total_immune_final = sum(d[1] for d in final_demands.values())
        # 4. Shared support gates tissue dynamics via step contexts.
        # Ratios use CURRENT (possibly degraded) capacities.
        vascular_ratio = self._allocation_ratio(total_vascular_final, float(self.current_vascular_capacity))
        immune_ratio = self._allocation_ratio(total_immune_final, float(self.current_immune_capacity))
        if spike_i > 0.0 or spike_v > 0.0:
            current = self.temporal_totals["min_immune_allocation_during_spike"]
            self.temporal_totals["min_immune_allocation_during_spike"] = immune_ratio if current is None else min(current, immune_ratio)
            current_v = self.temporal_totals["min_vascular_allocation_during_spike"]
            self.temporal_totals["min_vascular_allocation_during_spike"] = vascular_ratio if current_v is None else min(current_v, vascular_ratio)
        worst = min(vascular_ratio, immune_ratio)
        systemic_modifier = (1.0 - worst) * float(self.config.systemic_damage_gain)
        counters_before = {entry["config"].tissue_id: float(entry["model"].total_replaced_cells) for entry in self.modules}
        for entry, policy in zip(self.modules, effective):
            context = TissueStepContext(
                effective_vascular_support=vascular_ratio,
                effective_immune_support=immune_ratio,
                systemic_damage_modifier=systemic_modifier,
            )
            entry["model"].step(policy, context)
        self.step_count += 1
        time = self.step_count * float(self.config.dt)
        # 5. Executed-demand view + realized relief (from exact counter deltas,
        # attributed by the tissue-phase plan that actually ran).
        executed_demands = {}
        relief_cells: dict[str, float] = {}
        for entry, plan in zip(self.modules, phase):
            tid = entry["config"].tissue_id
            base_v, base_i = base_demands[tid]
            activity = accepted_counts.get(tid, 0.0)
            spike_share = spike_by_tissue.get(tid, (0.0, 0.0))
            executed_demands[tid] = (
                base_v + max(0.0, activity) * entry["demand"]["vascular_per_replacement"]
                + spike_share[0] + accepted_recovery_vasc.get(tid, 0.0),
                base_i + max(0.0, activity) * entry["demand"]["immune_per_replacement"]
                + spike_share[1] + accepted_recovery_imm.get(tid, 0.0),
            )
            replaced = float(entry["model"].total_replaced_cells) - counters_before[tid]
            relief_cells[tid] = float(replaced) if plan.target in ("senescent", "damaged") else 0.0
        # 6. Create delayed relief events for accepted activity (temporal only).
        created_i = created_v = 0.0
        if temporal_on:
            magnitude = float(self.temporal["relief_magnitude_scale"])
            delay = int(self.temporal["relief_delay_steps"])
            duration = int(self.temporal["relief_duration_steps"])
            target = str(self.temporal["relief_target"])
            for entry in self.modules:
                tid = entry["config"].tissue_id
                activity = max(0.0, accepted_counts.get(tid, 0.0))
                if activity <= 0.0 or magnitude <= 0.0:
                    continue
                immune_part = activity * magnitude * entry["demand"]["immune_per_replacement"]
                vascular_part = activity * magnitude * entry["demand"]["vascular_per_replacement"]
                if target == "immune_demand":
                    vascular_part = 0.0
                elif target == "vascular_demand":
                    immune_part = 0.0
                else:  # composite splits the credit across both resources
                    immune_part *= 0.5
                    vascular_part *= 0.5
                if immune_part <= 0.0 and vascular_part <= 0.0:
                    continue
                self.relief_events.append(
                    {
                        "tissue_id": tid,
                        "created_step": pre,
                        "effective_step": pre + delay,
                        "duration_steps": duration,
                        "immune_relief": float(immune_part),
                        "vascular_relief": float(vascular_part),
                        "realized": False,
                        "expired": False,
                        "token": f"{tid}:{pre}",
                    }
                )
                created_i += immune_part
                created_v += vascular_part
                self.temporal_totals["relief_created_events"] += 1
                self.temporal_totals["relief_created_amount"] += float(immune_part + vascular_part)
        active = self._active_relief(pre) if temporal_on else {}
        detail = dict(info)
        detail["relief_cells"] = {tid: float(relief_cells.get(tid, 0.0)) for tid in tissue_ids}
        temporal_detail = {
            "temporal_model": self.temporal_model,
            "spike_immune": float(spike_i),
            "spike_vascular": float(spike_v),
            "relief_created_immune": float(created_i),
            "relief_created_vascular": float(created_v),
            "relief_active_immune": float(sum(v[1] for v in active.values())),
            "relief_active_vascular": float(sum(v[0] for v in active.values())),
            "deferred_now": sorted(deferred_now),
            "executed_from_deferral": {tid: bool(from_deferral.get(tid, False)) for tid in tissue_ids},
            "defer_delays": {tid: float(defer_delays[tid]) for tid in defer_delays},
            "expired_now": sorted(expired_now),
            "queue_length": len(self.deferral_queue),
            "cumulative": copy.deepcopy(self.temporal_totals),
        }
        # Snapshot demands carry requested + recovery-immediate costs (the
        # replacement temporal spike stays execution-only, as in Stage 4C).
        final_demands_snapshot = {
            tid: (
                demands[tid][0] + accepted_recovery_vasc.get(tid, 0.0),
                demands[tid][1] + accepted_recovery_imm.get(tid, 0.0),
            )
            for tid in tissue_ids
        }
        # 6b. Degrade dynamic capacities under load (Stage 4D; neutral at
        # default zero rates, so legacy runs are untouched).
        if recovery_on:
            total_senescent = sum(float(e["model"].state.senescent_cells) for e in self.modules)
            self._degrade_capacities(total_vascular_final, total_immune_final, total_senescent)
        rec_detail["cumulative"] = copy.deepcopy(self.recovery_totals)
        return self._snapshot(time, final_demands_snapshot, scale, detail, executed_demands, temporal_detail,
                              rec_detail)

    def run(self, steps: int) -> list[dict[str, Any]]:
        """Run ``steps`` organ steps; returns snapshots (t0 first)."""
        if steps < 0:
            raise ValueError("steps must be >= 0")
        zero_demands = {
            entry["config"].tissue_id: self._module_demand(entry["model"].state, entry["demand"], 0.0)
            for entry in self.modules
        }
        trajectory = [self._snapshot(0.0, zero_demands, 1.0)]
        for _ in range(steps):
            trajectory.append(self.step())
        return trajectory

    # -- checkpoint / restore ----------------------------------------------
    def to_checkpoint_dict(self) -> dict[str, Any]:
        _, _ = self.modules[0]["model"].rng.getstate()
        return {
            "model_version": ORGAN_MODEL_VERSION,
            "model_scope": MODEL_SCOPE,
            "organ_id": self.config.organ_id,
            "seed": self.seed,
            "step_count": self.step_count,
            "last_scale": self.last_scale,
            "relief_events": copy.deepcopy(self.relief_events),
            "capacity_events": copy.deepcopy(self.capacity_events),
            "deferral_queue": copy.deepcopy(self.deferral_queue),
            "temporal_totals": copy.deepcopy(self.temporal_totals),
            "recovery_totals": copy.deepcopy(self.recovery_totals),
            "current_vascular_capacity": float(self.current_vascular_capacity),
            "current_immune_capacity": float(self.current_immune_capacity),
            "modules": [
                {
                    "tissue_id": entry["config"].tissue_id,
                    "model": entry["model"].to_checkpoint_dict(),
                }
                for entry in self.modules
            ],
        }

    @classmethod
    def from_checkpoint(cls, data: dict[str, Any], config: "OrganConfig") -> "OrganModel":
        from longevity.model.organ_policy import validate_score_weights  # deferred: avoid import cycle

        organ = cls.__new__(cls)
        organ.config = config
        organ.seed = int(data.get("seed", config.seed))
        organ.step_count = int(data.get("step_count", 0))
        organ.last_scale = float(data.get("last_scale", 1.0))
        organ.thresholds = validate_organ_thresholds(dict(config.thresholds))
        organ.score_weights = validate_score_weights(dict(config.coordination_params))
        organ.temporal_model = validate_temporal_model(config.temporal_relief_model)
        organ.temporal = validate_temporal_params(dict(config.temporal_params))
        organ.recovery_model = validate_recovery_model(config.recovery_model)
        organ.capacity = validate_capacity_dynamics(dict(config.capacity_dynamics))
        organ.recovery_on = organ.recovery_model == "decoupled_niche_recovery"
        # Pre-4C checkpoints carry no temporal state: restore starts empty.
        organ.relief_events = copy.deepcopy(data.get("relief_events", []))
        organ.capacity_events = copy.deepcopy(data.get("capacity_events", []))
        organ.deferral_queue = copy.deepcopy(data.get("deferral_queue", []))
        organ.temporal_totals = copy.deepcopy(data.get("temporal_totals", _fresh_temporal_totals()))
        organ.recovery_totals = copy.deepcopy(data.get("recovery_totals", _fresh_recovery_totals()))
        organ.current_vascular_capacity = float(
            data.get("current_vascular_capacity", config.shared_vascular_capacity)
        )
        organ.current_immune_capacity = float(
            data.get("current_immune_capacity", config.shared_immune_capacity)
        )
        saved = {m["tissue_id"]: m["model"] for m in data.get("modules", [])}
        organ.modules = []
        for index, module in enumerate(config.tissues):
            if module.tissue_id not in saved:
                raise ValueError(f"checkpoint missing tissue {module.tissue_id!r}")
            effective_params = dict(module.tissue_parameters)
            effective_params["dt"] = float(config.dt)
            model = TissueModel.from_checkpoint(saved[module.tissue_id])
            model.parameters = validate_tissue_parameters(effective_params)
            organ.modules.append(
                {
                    "config": module,
                    "model": model,
                    "policy": ReplacementPolicy.from_dict(module.policy),
                    "recovery_policy": RecoveryPolicy.from_dict(module.recovery),
                    "demand": validate_demand_coefficients(dict(module.demand_coefficients)),
                    "initial_functional": float(TissueState.from_dict(module.initial_state).functional_cells),
                }
            )
        return organ


@dataclass(frozen=True)
class OrganConfig:
    """Complete, self-describing abstract-organ configuration (Stage 4A)."""

    organ_id: str = "abstract_organ"
    seed: int = 42
    steps: int = 200
    dt: float = 1.0
    tissues: tuple[TissueModuleConfig, ...] = ()
    shared_vascular_capacity: float = 14.0
    shared_immune_capacity: float = 6.0
    aggregation: str = "weighted_sum"
    coordination: str = "independent_tissue_policies"
    global_replacement_cap: float | None = None
    systemic_damage_gain: float = 0.5
    coordination_params: dict[str, Any] = field(default_factory=dict)
    temporal_relief_model: str = "none"
    temporal_params: dict[str, Any] = field(default_factory=dict)
    recovery_model: str = "none"
    capacity_dynamics: dict[str, Any] = field(default_factory=dict)
    thresholds: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_ORGAN_THRESHOLDS))
    model_version: str = ORGAN_MODEL_VERSION
    data_version: str = "0.1.0"
    notes: str = ""

    def __post_init__(self) -> None:
        from longevity.model.organ_policy import (  # deferred: avoid import cycle
            validate_coordination,
            validate_score_weights,
        )

        if not self.organ_id or not isinstance(self.organ_id, str):
            raise ValueError("organ_id must be a non-empty string")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("seed must be an int")
        if isinstance(self.steps, bool) or not isinstance(self.steps, int) or self.steps < 0:
            raise ValueError("steps must be a non-negative int")
        _require_number(self.dt, "organ.dt", lo=1e-9)
        if not isinstance(self.tissues, (list, tuple)) or not 1 <= len(self.tissues) <= 8:
            raise ValueError("organ must declare 1..8 tissue modules")
        modules = tuple(m if isinstance(m, TissueModuleConfig) else TissueModuleConfig(**dict(m)) for m in self.tissues)
        object.__setattr__(self, "tissues", modules)
        ids = [m.tissue_id for m in modules]
        if len(set(ids)) != len(ids):
            raise ValueError(f"tissue_id values must be unique, got {ids!r}")
        _require_number(self.shared_vascular_capacity, "organ.shared_vascular_capacity", lo=1e-9)
        _require_number(self.shared_immune_capacity, "organ.shared_immune_capacity", lo=1e-9)
        if self.aggregation not in VALID_AGGREGATIONS:
            raise ValueError(f"aggregation must be one of {VALID_AGGREGATIONS}, got {self.aggregation!r}")
        object.__setattr__(self, "coordination", validate_coordination(self.coordination))
        if self.global_replacement_cap is not None:
            _require_number(self.global_replacement_cap, "organ.global_replacement_cap", lo=0.0)
        _require_number(self.systemic_damage_gain, "organ.systemic_damage_gain", lo=0.0)
        object.__setattr__(
            self, "coordination_params", validate_score_weights(dict(self.coordination_params))
        )
        object.__setattr__(self, "temporal_relief_model", validate_temporal_model(self.temporal_relief_model))
        object.__setattr__(
            self, "temporal_params", validate_temporal_params(dict(self.temporal_params))
        )
        object.__setattr__(self, "recovery_model", validate_recovery_model(self.recovery_model))
        object.__setattr__(
            self, "capacity_dynamics", validate_capacity_dynamics(dict(self.capacity_dynamics))
        )
        validate_organ_thresholds(dict(self.thresholds))
        if not self.model_version or not isinstance(self.model_version, str):
            raise ValueError("model_version must be a non-empty string")

    def to_config_dict(self) -> dict[str, Any]:
        return {
            "organ_id": self.organ_id,
            "model_scope": MODEL_SCOPE,
            "model_version": self.model_version,
            "data_version": self.data_version,
            "seed": self.seed,
            "steps": self.steps,
            "dt": float(self.dt),
            "tissues": [
                {
                    "tissue_id": m.tissue_id,
                    "role": m.role,
                    "weight": float(m.weight),
                    "is_vital": bool(m.is_vital),
                    "required_function": float(m.required_function),
                    "initial_state": TissueState.from_dict(m.initial_state).to_dict(),
                    "tissue_parameters": validate_tissue_parameters(dict(m.tissue_parameters)),
                    "policy": ReplacementPolicy.from_dict(m.policy).to_dict(),
                    "demand_coefficients": validate_demand_coefficients(dict(m.demand_coefficients)),
                    "recovery": RecoveryPolicy.from_dict(m.recovery).to_dict(),
                }
                for m in self.tissues
            ],
            "shared_vascular_capacity": float(self.shared_vascular_capacity),
            "shared_immune_capacity": float(self.shared_immune_capacity),
            "aggregation": self.aggregation,
            "coordination": self.coordination,
            "coordination_params": {k: float(v) for k, v in self.coordination_params.items()},
            "temporal_relief_model": self.temporal_relief_model,
            "temporal_params": copy.deepcopy(self.temporal_params),
            "recovery_model": self.recovery_model,
            "capacity_dynamics": copy.deepcopy(self.capacity_dynamics),
            "global_replacement_cap": self.global_replacement_cap,
            "systemic_damage_gain": float(self.systemic_damage_gain),
            "thresholds": validate_organ_thresholds(dict(self.thresholds)),
            "notes": self.notes,
        }

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "OrganConfig":
        tissues = [TissueModuleConfig(**dict(m)) if not isinstance(m, TissueModuleConfig) else m for m in data.get("tissues", [])]
        # Backward compatibility: pre-4D configs lack the four supply-side
        # thresholds; fill them with non-firing defaults (old keys stay
        # required, so partial blocks still raise).
        thresholds = dict(data.get("thresholds", dict(DEFAULT_ORGAN_THRESHOLDS)))
        for key in ("min_capacity_fraction", "min_vital_ecm_quality",
                    "max_mean_immune_pressure", "max_recovery_backlog"):
            thresholds.setdefault(key, DEFAULT_ORGAN_THRESHOLDS[key])
        return cls(
            organ_id=data.get("organ_id", "abstract_organ"),
            seed=data.get("seed", 42),
            steps=data.get("steps", 200),
            dt=float(data.get("dt", 1.0)),
            tissues=tuple(tissues),
            shared_vascular_capacity=float(data.get("shared_vascular_capacity", 14.0)),
            shared_immune_capacity=float(data.get("shared_immune_capacity", 6.0)),
            aggregation=data.get("aggregation", "weighted_sum"),
            coordination=data.get("coordination", "independent_tissue_policies"),
            coordination_params=data.get("coordination_params", {}),
            temporal_relief_model=data.get("temporal_relief_model", "none"),
            temporal_params=data.get("temporal_params", {}),
            recovery_model=data.get("recovery_model", "none"),
            capacity_dynamics=data.get("capacity_dynamics", {}),
            global_replacement_cap=data.get("global_replacement_cap", None),
            systemic_damage_gain=float(data.get("systemic_damage_gain", 0.5)),
            thresholds=thresholds,
            model_version=data.get("model_version", ORGAN_MODEL_VERSION),
            data_version=data.get("data_version", "0.1.0"),
            notes=data.get("notes", ""),
        )
