"""ORGAN-BACKED MODEL LAYER: reduced-order organ proxies (Stage 6A).

Vital systems stop being flat placeholders: each maps to a compact organ
proxy with its own damage / senescence / fibrosis / cancer / ECM /
vascular / immune state (ideas and lessons inherited from Stage 4, not a
full cell-level simulation). Proxies compete for systemic resources
(perfusion / immune / metabolic / repair); organism-level coordination
modes decide how intervention plans are scaled, prioritized, or deferred
under contention.

Scope (see docs/ORGAN_BACKED_ORGANISM_MODEL.md): abstract years, ordinal
rates, no human anatomy and no calibrated biology. All numbers are
OPERATIONAL model choices. Pure validation + math helpers; state lives in
``OrganismState.organ_backed``. The ``none`` mode is behaviorally inert
by construction.
"""

from __future__ import annotations

import math

from typing import Any

ORGAN_BACKED_MODELS = ("none", "reduced_organ_proxies")
ORGAN_BACKED_SCOPE = "abstract_organ_backed_organism_life_course"

# One proxy per vital system (1:1 keeps the mapping explicit; the
# architecture allows fewer proxies via mapped_vital_systems, but the v0
# grid uses the full set).
ORGAN_PROXIES = (
    "brain_cns_proxy",
    "cardiovascular_proxy",
    "respiratory_proxy",
    "hepatic_proxy",
    "renal_proxy",
    "immune_proxy",
    "metabolic_proxy",
    "musculoskeletal_proxy",
)

PROXY_TO_SYSTEMS: dict[str, list[str]] = {
    "brain_cns_proxy": ["brain_cns"],
    "cardiovascular_proxy": ["cardiovascular"],
    "respiratory_proxy": ["respiratory"],
    "hepatic_proxy": ["hepatic"],
    "renal_proxy": ["renal"],
    "immune_proxy": ["immune"],
    "metabolic_proxy": ["metabolic"],
    "musculoskeletal_proxy": ["musculoskeletal"],
}

SYSTEM_TO_PROXY: dict[str, str] = {
    system: proxy for proxy, systems in PROXY_TO_SYSTEMS.items() for system in systems
}

SYSTEMIC_RESOURCES = ("perfusion", "immune", "metabolic", "repair")

ORGAN_COORDINATION_MODES = (
    "independent_organ_policies",
    "global_resource_aware_scaling",
    "vital_organ_priority",
    "lookahead_organ_resource",
    "deferral_organ_resource",
    # Stage 6B network-aware modes (additive; legacy modes unchanged).
    "independent_network",
    "network_bottleneck_priority",
    "cascade_guard",
    "information_preservation_priority",
    "mutation_load_guard",
    "lookahead_network",
    "deferral_network",
    # Stage 6C reversibility-aware modes (additive; legacy modes unchanged).
    "independent_reversibility",
    "preventive_priority",
    "repair_ceiling_guard",
    "information_guard",
    "mutation_guard",
    "entropy_budget_scheduler",
    "lookahead_reversibility",
)

# Operational per-proxy dynamics (O-6A-1…; not measurements). Rates are
# function/damage drift per abstract year at stage multiplier 1.0.
DEFAULT_PROXY_PARAMS: dict[str, dict[str, float]] = {
    "brain_cns_proxy": {"base_damage_rate": 0.004, "base_senescence_rate": 0.003,
                        "base_fibrosis_rate": 0.001, "base_cancer_rate": 0.001,
                        "ecm_decay": 0.002, "repair_capacity": 0.004,
                        "recovery_efficiency": 0.5, "turnover_rate": 0.002,
                        "replacement_tolerance": 0.6, "failure_threshold": 0.25,
                        "warning_threshold": 0.40, "critical": 1.0, "growth_rate": 0.35},
    "cardiovascular_proxy": {"base_damage_rate": 0.006, "base_senescence_rate": 0.003,
                             "base_fibrosis_rate": 0.002, "base_cancer_rate": 0.001,
                             "ecm_decay": 0.002, "repair_capacity": 0.005,
                             "recovery_efficiency": 0.5, "turnover_rate": 0.003,
                             "replacement_tolerance": 0.6, "failure_threshold": 0.25,
                             "warning_threshold": 0.40, "critical": 1.0, "growth_rate": 0.45},
    "respiratory_proxy": {"base_damage_rate": 0.005, "base_senescence_rate": 0.003,
                          "base_fibrosis_rate": 0.002, "base_cancer_rate": 0.0015,
                          "ecm_decay": 0.002, "repair_capacity": 0.005,
                          "recovery_efficiency": 0.5, "turnover_rate": 0.003,
                          "replacement_tolerance": 0.6, "failure_threshold": 0.25,
                          "warning_threshold": 0.40, "critical": 1.0, "growth_rate": 0.45},
    "hepatic_proxy": {"base_damage_rate": 0.005, "base_senescence_rate": 0.003,
                      "base_fibrosis_rate": 0.002, "base_cancer_rate": 0.002,
                      "ecm_decay": 0.002, "repair_capacity": 0.008,
                      "recovery_efficiency": 0.6, "turnover_rate": 0.004,
                      "replacement_tolerance": 0.7, "failure_threshold": 0.25,
                      "warning_threshold": 0.40, "critical": 1.0, "growth_rate": 0.45},
    "renal_proxy": {"base_damage_rate": 0.006, "base_senescence_rate": 0.003,
                    "base_fibrosis_rate": 0.002, "base_cancer_rate": 0.001,
                    "ecm_decay": 0.002, "repair_capacity": 0.004,
                    "recovery_efficiency": 0.5, "turnover_rate": 0.002,
                    "replacement_tolerance": 0.6, "failure_threshold": 0.25,
                    "warning_threshold": 0.40, "critical": 1.0, "growth_rate": 0.45},
    "immune_proxy": {"base_damage_rate": 0.006, "base_senescence_rate": 0.004,
                     "base_fibrosis_rate": 0.001, "base_cancer_rate": 0.0015,
                     "ecm_decay": 0.001, "repair_capacity": 0.007,
                     "recovery_efficiency": 0.6, "turnover_rate": 0.005,
                     "replacement_tolerance": 0.7, "failure_threshold": 0.25,
                     "warning_threshold": 0.40, "critical": 1.0, "growth_rate": 0.40},
    "metabolic_proxy": {"base_damage_rate": 0.005, "base_senescence_rate": 0.003,
                        "base_fibrosis_rate": 0.001, "base_cancer_rate": 0.0015,
                        "ecm_decay": 0.002, "repair_capacity": 0.006,
                        "recovery_efficiency": 0.5, "turnover_rate": 0.003,
                        "replacement_tolerance": 0.6, "failure_threshold": 0.25,
                        "warning_threshold": 0.40, "critical": 1.0, "growth_rate": 0.45},
    "musculoskeletal_proxy": {"base_damage_rate": 0.007, "base_senescence_rate": 0.003,
                              "base_fibrosis_rate": 0.002, "base_cancer_rate": 0.001,
                              "ecm_decay": 0.003, "repair_capacity": 0.005,
                              "recovery_efficiency": 0.5, "turnover_rate": 0.003,
                              "replacement_tolerance": 0.6, "failure_threshold": 0.20,
                              "warning_threshold": 0.35, "critical": 0.0, "growth_rate": 0.50},
}

_PROXY_PARAM_KEYS = ("base_damage_rate", "base_senescence_rate", "base_fibrosis_rate",
                     "base_cancer_rate", "ecm_decay", "repair_capacity",
                     "recovery_efficiency", "turnover_rate", "replacement_tolerance",
                     "failure_threshold", "warning_threshold", "critical", "growth_rate")

DEFAULT_RESOURCE_BUDGETS: dict[str, float] = {
    "perfusion": 8.0,
    "immune": 8.0,
    "metabolic": 8.0,
    "repair": 8.0,
}

# Per-proxy demand coefficients (operational): demand = base + f*function
# + d*damage + s*senescence + a*recent_activity.
DEFAULT_DEMAND_COEFFICIENTS: dict[str, dict[str, float]] = {
    resource: {"base": 0.55, "function": 0.25, "damage": 0.6,
               "senescence": 0.5, "activity": 0.4}
    for resource in SYSTEMIC_RESOURCES
}

# Which aging drivers become (partially) emergent from proxy states, and
# with what blend weight. 0.0 keeps the Stage 5C phenomenological track.
DEFAULT_EMERGENT_WEIGHTS: dict[str, float] = {
    "dna_damage": 0.0,
    "epigenetic_drift": 0.0,
    "proteostasis_loss": 0.2,
    "mitochondrial_dysfunction": 0.2,
    "cellular_senescence": 0.5,
    "stem_exhaustion": 0.3,
    "chronic_inflammation": 0.5,
    "cancer_prone": 0.3,
}

# Burden weights mapping proxy components onto function in [0, 1].
_FUNCTION_BURDEN_WEIGHTS = {"damage": 0.35, "senescence": 0.25, "fibrosis": 0.15,
                            "ecm_loss": 0.15, "cancer": 0.10}

# Organ-backed shock types (Stage 6A). Kept OUT of the Stage 5B SHOCK_TYPES
# so legacy shock streams stay bit-identical.
ORGAN_BACKED_SHOCK_TYPES = ("resource_shock",)


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


def validate_organ_backed_model(model: Any) -> str:
    """Validate an organ-backed model name."""
    if not isinstance(model, str) or model not in ORGAN_BACKED_MODELS:
        raise ValueError(f"organ_backed_model must be one of {ORGAN_BACKED_MODELS}, got {model!r}")
    return model


def validate_coordination_mode(mode: Any) -> str:
    """Validate an organism-level coordination mode name."""
    if not isinstance(mode, str) or mode not in ORGAN_COORDINATION_MODES:
        raise ValueError(f"coordination_mode must be one of {ORGAN_COORDINATION_MODES}, got {mode!r}")
    return mode


def validate_proxy_params(proxies: dict[str, Any] | None) -> dict[str, dict[str, float]]:
    """Validate per-proxy dynamics blocks (missing proxies get defaults)."""
    if proxies is None:
        proxies = {}
    if not isinstance(proxies, dict):
        raise ValueError(f"organ_proxies must be a dict, got {proxies!r}")
    unknown = [name for name in proxies if name not in ORGAN_PROXIES]
    if unknown:
        raise ValueError(f"unknown organ proxies: {sorted(unknown)}")
    validated: dict[str, dict[str, float]] = {}
    for name in ORGAN_PROXIES:
        merged = dict(DEFAULT_PROXY_PARAMS[name])
        merged.update(proxies.get(name, {}))
        extra = set(merged) - set(_PROXY_PARAM_KEYS)
        if extra:
            raise ValueError(f"proxy {name!r} unknown keys: {sorted(extra)}")
        block: dict[str, float] = {}
        for key in _PROXY_PARAM_KEYS:
            if key == "critical":
                value = merged[key]
                if isinstance(value, bool):
                    block[key] = 1.0 if value else 0.0
                else:
                    block[key] = _require_number(value, f"proxies.{name}.{key}", lo=0.0, hi=1.0)
                continue
            lo, hi = 0.0, None
            if key in ("recovery_efficiency", "replacement_tolerance",
                       "failure_threshold", "warning_threshold"):
                hi = 1.0
            block[key] = _require_number(merged[key], f"proxies.{name}.{key}", lo=lo, hi=hi)
        if not block["failure_threshold"] < block["warning_threshold"]:
            raise ValueError(f"proxy {name!r} failure_threshold must be < warning_threshold")
        validated[name] = block
    return validated


def validate_resource_budgets(budgets: dict[str, Any] | None) -> dict[str, float]:
    """Validate systemic resource budgets (all >= 0, finite)."""
    if budgets is None:
        budgets = {}
    if not isinstance(budgets, dict):
        raise ValueError(f"systemic_resources must be a dict, got {budgets!r}")
    unknown = set(budgets) - set(SYSTEMIC_RESOURCES)
    if unknown:
        raise ValueError(f"unknown systemic resources: {sorted(unknown)}")
    merged = dict(DEFAULT_RESOURCE_BUDGETS)
    merged.update(budgets)
    return {name: _require_number(merged[name], f"systemic_resources.{name}", lo=0.0)
            for name in SYSTEMIC_RESOURCES}


def validate_emergent_weights(weights: dict[str, Any] | None) -> dict[str, float]:
    """Validate emergent-driver blend weights (each in [0, 1])."""
    from longevity.model.aging import AGING_DRIVERS  # deferred: avoid import cycle

    if weights is None:
        weights = {}
    if not isinstance(weights, dict):
        raise ValueError(f"emergent_weights must be a dict, got {weights!r}")
    unknown = set(weights) - set(AGING_DRIVERS)
    if unknown:
        raise ValueError(f"unknown emergent weight drivers: {sorted(unknown)}")
    merged = dict(DEFAULT_EMERGENT_WEIGHTS)
    merged.update(weights)
    return {name: _require_number(merged[name], f"emergent_weights.{name}", lo=0.0, hi=1.0)
            for name in AGING_DRIVERS}


def scope_for_model(mode: str) -> str:
    """Effective model scope string for an organ-backed mode."""
    from longevity.model.organism import MODEL_SCOPE  # deferred: avoid import cycle

    return ORGAN_BACKED_SCOPE if validate_organ_backed_model(mode) != "none" else MODEL_SCOPE


def default_organ_backed_state() -> dict[str, Any]:
    """Fresh organ-backed state: healthy proxies, full budgets, empty queue."""
    proxies = {}
    for name in ORGAN_PROXIES:
        params = DEFAULT_PROXY_PARAMS[name]
        proxies[name] = {
            "organ_id": name,
            "mapped_vital_systems": list(PROXY_TO_SYSTEMS[name]),
            "function": 0.6,
            "reserve": 0.2,
            "damage": 0.0,
            "senescence_burden": 0.0,
            "fibrosis": 0.0,
            "cancer_risk": 0.0,
            "ecm_quality": 0.6,
            "vascular_quality": 0.6,
            "immune_pressure": 0.02,
            "vascular_capacity": 1.0,
            "immune_capacity": 1.0,
            "repair_capacity": float(params["repair_capacity"]),
            "recovery_pending": 0.0,
            "recent_activity": 0.0,
            "recovery_efficiency": float(params["recovery_efficiency"]),
            "turnover_rate": float(params["turnover_rate"]),
            "replacement_tolerance": float(params["replacement_tolerance"]),
            "critical": bool(float(params["critical"]) > 0.5),
            "informational_continuity": 1.0 if name == "brain_cns_proxy" else None,
        }
    return {
        "proxies": proxies,
        "resources": {
            "budgets": dict(DEFAULT_RESOURCE_BUDGETS),
            "allocation": {name: 1.0 for name in SYSTEMIC_RESOURCES},
            "demand": {name: 0.0 for name in SYSTEMIC_RESOURCES},
            "shortfall": {name: 0.0 for name in SYSTEMIC_RESOURCES},
        },
        "coordination_queue": [],
        "coordination_stats": {"executed": 0, "scaled": 0, "deferred": 0,
                              "rejected": 0, "recovered_from_queue": 0},
    }


def proxy_function_from_components(proxy: dict[str, Any]) -> float:
    """Operational function from proxy burdens (pure, deterministic)."""
    burden = (
        _FUNCTION_BURDEN_WEIGHTS["damage"] * max(0.0, float(proxy.get("damage", 0.0)))
        + _FUNCTION_BURDEN_WEIGHTS["senescence"] * max(0.0, min(1.0, float(proxy.get("senescence_burden", 0.0))))
        + _FUNCTION_BURDEN_WEIGHTS["fibrosis"] * max(0.0, min(1.0, float(proxy.get("fibrosis", 0.0))))
        + _FUNCTION_BURDEN_WEIGHTS["ecm_loss"] * (1.0 - max(0.0, min(1.0, float(proxy.get("ecm_quality", 1.0)))))
        + _FUNCTION_BURDEN_WEIGHTS["cancer"] * max(0.0, min(1.0, float(proxy.get("cancer_risk", 0.0))))
    )
    return max(0.0, min(1.0, 1.0 - burden))


def compute_demands(proxies: dict[str, Any],
                    coefficients: dict[str, dict[str, float]] | None = None) -> dict[str, float]:
    """Total systemic demand per resource from all proxies (pure)."""
    coefficients = coefficients or DEFAULT_DEMAND_COEFFICIENTS
    totals = {name: 0.0 for name in SYSTEMIC_RESOURCES}
    for proxy in proxies.values():
        function = max(0.0, min(1.0, float(proxy.get("function", 0.0))))
        damage = max(0.0, float(proxy.get("damage", 0.0)))
        senescence = max(0.0, min(1.0, float(proxy.get("senescence_burden", 0.0))))
        activity = max(0.0, float(proxy.get("recent_activity", 0.0)))
        for resource in SYSTEMIC_RESOURCES:
            coef = coefficients[resource]
            totals[resource] += (float(coef["base"]) + float(coef["function"]) * function
                                 + float(coef["damage"]) * damage
                                 + float(coef["senescence"]) * senescence
                                 + float(coef["activity"]) * activity)
    return totals


def compute_allocation(budgets: dict[str, float],
                       demands: dict[str, float]) -> dict[str, float]:
    """Allocation ratio per resource in [0, 1] (pure; zero demand -> 1.0)."""
    allocation = {}
    for resource in SYSTEMIC_RESOURCES:
        demand = max(0.0, float(demands.get(resource, 0.0)))
        budget = max(0.0, float(budgets.get(resource, 0.0)))
        if demand <= 0.0:
            allocation[resource] = 1.0
        elif budget <= 0.0:
            allocation[resource] = 0.0
        else:
            allocation[resource] = max(0.0, min(1.0, budget / demand))
    return allocation


def emergent_driver_levels(proxies: dict[str, Any]) -> dict[str, float]:
    """Organ-aggregated driver levels in [0, 1] (pure, Stage 6A mapping).

    cellular_senescence <- mean proxy senescence; chronic_inflammation <-
    mean immune pressure; cancer_prone <- mean cancer risk; stem_exhaustion
    <- damage + depleted reserves; mitochondrial_dysfunction <- damage of
    metabolic-group proxies; proteostasis_loss <- damage under low repair;
    dna_damage / epigenetic_drift stay phenomenological (0.0 contribution
    here; documented in ORGAN_BACKED_ORGANISM_MODEL.md).
    """
    from longevity.model.aging import AGING_DRIVERS  # deferred: avoid import cycle

    listed = list(proxies.values())
    n = max(1, len(listed))

    def _mean(key: str) -> float:
        return sum(max(0.0, min(1.0, float(p.get(key, 0.0)))) for p in listed) / n

    metabolic_group = [p for pid, p in proxies.items()
                       if pid in ("metabolic_proxy", "hepatic_proxy", "renal_proxy",
                                  "musculoskeletal_proxy")]
    mito = (sum(max(0.0, float(p.get("damage", 0.0))) for p in metabolic_group)
            / max(1, len(metabolic_group)))
    reserve_frac = sum(max(0.0, min(1.0, float(p.get("reserve", 0.0))))
                       for p in listed) / n
    damage_mean = sum(max(0.0, float(p.get("damage", 0.0))) for p in listed) / n
    repair_mean = sum(max(0.0, float(p.get("repair_capacity", 0.0))) for p in listed) / n
    levels = {
        "cellular_senescence": _mean("senescence_burden"),
        "chronic_inflammation": _mean("immune_pressure"),
        "cancer_prone": _mean("cancer_risk"),
        "stem_exhaustion": max(0.0, min(1.0, 0.5 * damage_mean + 0.5 * (1.0 - reserve_frac))),
        "mitochondrial_dysfunction": max(0.0, min(1.0, mito)),
        "proteostasis_loss": max(0.0, min(1.0, damage_mean * (1.0 + max(0.0, 0.01 - repair_mean) * 50.0))),
        "dna_damage": 0.0,
        "epigenetic_drift": 0.0,
    }
    return {name: levels[name] for name in AGING_DRIVERS}


def coordinate_organ_effects(
    effects: list[dict[str, Any]],
    proxies: dict[str, Any],
    allocation: dict[str, float],
    mode: str,
    queue: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Organism-level coordination of organ-targeted effects (pure).

    Returns ``{"executed": [...], "deferred": [...], "rejected": [...],
    "queue": [...], "detail": {...}}``. Never mutates inputs or policy
    objects: scaled effects are copies. Tie-breaking is deterministic
    (sorted proxy id, stable effect order).
    """
    validate_coordination_mode(mode)
    # Stage 6B: network-aware modes delegate to the organ-network layer
    # with a neutral (empty) network context when none is supplied, so
    # legacy callers keep deterministic behavior.
    from longevity.model.organ_network import NETWORK_COORDINATION_MODES  # deferred

    if mode in NETWORK_COORDINATION_MODES:
        from longevity.model.organ_network import coordinate_network_effects  # deferred

        return coordinate_network_effects(effects, proxies, allocation, mode, queue, None)
    queue = [dict(entry) for entry in (queue or [])]
    executed: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    # Queued plans are retried first (FIFO) when resources allow headroom.
    pending = queue + [{"effect": dict(effect), "retries": 0} for effect in effects]
    detail: dict[str, Any] = {"mode": mode, "n_pending": len(pending)}
    min_alloc = min(float(allocation.get(r, 1.0)) for r in SYSTEMIC_RESOURCES)
    for entry in pending:
        effect = dict(entry["effect"])
        targets = effect.get("target_organ_ids") or sorted(proxies)
        if mode == "independent_organ_policies":
            executed.append(effect)
            continue
        if mode == "global_resource_aware_scaling":
            scaled = dict(effect)
            scaled["_coord_scale"] = min_alloc
            for key, value in list(scaled.items()):
                if key.startswith("organ_delta_") and isinstance(value, (int, float)):
                    scaled[key] = float(value) * min_alloc
            executed.append(scaled)
            continue
        if mode == "vital_organ_priority":
            critical_targets = [t for t in targets
                                if t in proxies and _proxy_critical(proxies[t])]
            if critical_targets or min_alloc >= 0.5:
                scaled = dict(effect)
                factor = 1.0 if critical_targets else min_alloc
                scaled["_coord_scale"] = factor
                for key, value in list(scaled.items()):
                    if key.startswith("organ_delta_") and isinstance(value, (int, float)):
                        scaled[key] = float(value) * factor
                executed.append(scaled)
            elif entry.get("retries", 0) >= 4:
                rejected.append(effect)
            else:
                deferred.append(entry)
            continue
        if mode == "lookahead_organ_resource":
            # Rank by relief-per-cost: senescence/fibrosis/damage repair vs
            # resource cost. Below-median plans defer under contention.
            score = _plan_relief_score(effect)
            entry["relief_score"] = score
            if min_alloc >= 0.7 or score >= 0.01:
                executed.append(effect)
            elif entry.get("retries", 0) >= 4:
                rejected.append(effect)
            else:
                deferred.append(entry)
            continue
        if mode == "deferral_organ_resource":
            if min_alloc >= 0.5:
                executed.append(effect)
            elif entry.get("retries", 0) >= 4:
                rejected.append(effect)
            else:
                deferred.append(entry)
            continue
    new_queue = []
    for entry in deferred:
        record = {"effect": entry["effect"], "age": entry.get("age", 0.0),
                  "retries": int(entry.get("retries", 0)) + 1}
        if "relief_score" in entry:
            record["relief_score"] = entry["relief_score"]
        new_queue.append(record)
    detail.update({"n_executed": len(executed), "n_deferred": len(new_queue),
                   "n_rejected": len(rejected), "min_allocation": min_alloc})
    return {"executed": executed, "deferred": [d["effect"] for d in deferred],
            "rejected": rejected, "queue": new_queue, "detail": detail}


def _proxy_critical(proxy: dict[str, Any]) -> bool:
    return bool(proxy.get("critical", True))


def _plan_relief_score(effect: dict[str, Any]) -> float:
    """Relief proxy for lookahead ranking (pure, deterministic)."""
    relief = 0.0
    for key in ("organ_delta_damage", "organ_delta_senescence", "organ_delta_fibrosis",
                "organ_delta_cancer_risk"):
        relief += max(0.0, -float(effect.get(key, 0.0)))
    relief += max(0.0, float(effect.get("organ_delta_recovery", 0.0)))
    relief += max(0.0, float(effect.get("organ_delta_ecm", 0.0)))
    relief += max(0.0, float(effect.get("organ_delta_vascular", 0.0)))
    cost = 0.0
    resource_cost = effect.get("organ_resource_cost") or {}
    if isinstance(resource_cost, dict):
        cost = sum(max(0.0, float(v)) for v in resource_cost.values())
    return relief - 0.5 * cost


def validate_organ_backed_state(state: Any) -> dict[str, Any] | None:
    """Validate an organ-backed state block (None passes through)."""
    if state is None:
        return None
    if not isinstance(state, dict):
        raise ValueError(f"organ_backed state must be a dict or None, got {state!r}")
    proxies = state.get("proxies", {})
    if set(proxies) != set(ORGAN_PROXIES):
        raise ValueError(f"organ_backed proxies must be exactly {ORGAN_PROXIES}")
    for pid, proxy in proxies.items():
        for key in ("function", "senescence_burden", "fibrosis", "cancer_risk",
                    "ecm_quality", "vascular_quality", "immune_pressure",
                    "recovery_efficiency", "turnover_rate", "replacement_tolerance"):
            _require_number(proxy.get(key), f"organ_backed.{pid}.{key}", lo=0.0, hi=1.0)
        if not isinstance(proxy.get("critical"), bool):
            raise ValueError(f"organ_backed.{pid}.critical must be a bool")
        for key in ("reserve", "damage", "vascular_capacity", "immune_capacity",
                    "repair_capacity", "recovery_pending", "recent_activity"):
            _require_number(proxy.get(key), f"organ_backed.{pid}.{key}", lo=0.0)
        continuity = proxy.get("informational_continuity")
        if pid == "brain_cns_proxy":
            _require_number(continuity, f"organ_backed.{pid}.informational_continuity",
                            lo=0.0, hi=1.0)
        elif continuity is not None:
            raise ValueError(f"organ_backed.{pid}.informational_continuity must be None")
    resources = state.get("resources", {})
    for key in ("budgets", "allocation", "demand", "shortfall"):
        block = resources.get(key, {})
        for name in SYSTEMIC_RESOURCES:
            _require_number(block.get(name), f"organ_backed.resources.{key}.{name}", lo=0.0)
    for name in SYSTEMIC_RESOURCES:
        if not 0.0 <= float(resources["allocation"][name]) <= 1.0:
            raise ValueError(f"organ_backed.resources.allocation.{name} out of [0, 1]")
    queue = state.get("coordination_queue", [])
    if not isinstance(queue, list):
        raise ValueError("organ_backed.coordination_queue must be a list")
    stats = state.get("coordination_stats", {})
    for key in ("executed", "scaled", "deferred", "rejected", "recovered_from_queue"):
        value = stats.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"organ_backed.coordination_stats.{key} must be an int >= 0")
    return state
