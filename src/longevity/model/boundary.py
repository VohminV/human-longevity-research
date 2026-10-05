"""BOUNDARY PROBE LAYER: diagnostic irreversibility ablations (Stage 6D).

Abstract, operational, non-calibrated. A diagnostic layer over the Stage 6C
reversibility ledger — NOT new biology. Global ablation scales, per-component
overrides, and explicit flags let experiments ask whether the
irreversible-accumulation wall is parametric (suppressible) or structural
(persists even at near-zero irreversible flux).

``none`` mode is behaviorally inert by construction. All helpers are pure;
ablation config lives in ``OrganismState.boundary`` (static snapshot).
"""

from __future__ import annotations

import hashlib
import json
import math

from typing import Any

BOUNDARY_PROBE_MODELS = ("none", "irreversibility_ablation")
BOUNDARY_SCOPE = "abstract_organ_network_reversibility_boundary_probe"

COMPONENT_TYPES = ("driver", "organ", "information", "mutation", "niche", "entropy", "global")

DEFAULT_BOUNDARY_PARAMS: dict[str, float] = {
    "conversion_scale": 1.0,
    "independent_accrual_scale": 1.0,
    "repair_ceiling_scale": 1.0,
    "low_conversion_threshold": 0.01,
    "low_independent_threshold": 0.01,
    "high_ceiling_threshold": 0.9,
}

BOUNDARY_FLAGS = (
    "disable_conversion",
    "disable_independent_accrual",
    "disable_irreversible_repair",
    "disable_repair_ceiling",
    "force_repair_ceiling_unlimited",
)


def _require_number(value: Any, path: str, lo: float | None = None,
                    hi: float | None = None) -> float:
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


def validate_boundary_probe_model(model: Any) -> str:
    if not isinstance(model, str) or model not in BOUNDARY_PROBE_MODELS:
        raise ValueError(
            f"boundary_probe_model must be one of {BOUNDARY_PROBE_MODELS}, got {model!r}")
    return model


def scope_for_boundary_model(mode: str) -> str:
    from longevity.model.reversibility import REVERSIBILITY_SCOPE  # deferred

    return BOUNDARY_SCOPE if validate_boundary_probe_model(mode) != "none" \
        else REVERSIBILITY_SCOPE


def validate_boundary_params(params: Any) -> dict[str, Any]:
    """Validate global ablation scales + flags + thresholds."""
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError(f"boundary_params must be a dict, got {params!r}")
    unknown = set(params) - set(DEFAULT_BOUNDARY_PARAMS) - set(BOUNDARY_FLAGS)
    if unknown:
        raise ValueError(f"unknown boundary param keys: {sorted(unknown)}")
    validated: dict[str, Any] = {}
    for key in DEFAULT_BOUNDARY_PARAMS:
        validated[key] = _require_number(params.get(key, DEFAULT_BOUNDARY_PARAMS[key]),
                                         f"boundary_params.{key}", lo=0.0)
    for flag in BOUNDARY_FLAGS:
        value = params.get(flag, False)
        if not isinstance(value, bool):
            raise ValueError(f"boundary_params.{flag} must be a bool, got {value!r}")
        validated[flag] = value
    return validated


def validate_component_overrides(overrides: Any) -> list[dict[str, Any]]:
    """Validate per-component ablation overrides (empty list by default)."""
    if overrides is None:
        overrides = []
    if not isinstance(overrides, list):
        raise ValueError(f"component_overrides must be a list, got {overrides!r}")
    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for i, item in enumerate(overrides):
        if not isinstance(item, dict):
            raise ValueError(f"component_overrides[{i}] must be a dict")
        cid = item.get("component_id", "")
        ctype = item.get("component_type", "")
        if not isinstance(cid, str) or not cid:
            raise ValueError(f"component_overrides[{i}].component_id must be non-empty string")
        if ctype not in COMPONENT_TYPES:
            raise ValueError(f"component_overrides[{i}].component_type must be one of "
                             f"{COMPONENT_TYPES}, got {ctype!r}")
        key = f"{ctype}:{cid}"
        if key in seen:
            raise ValueError(f"duplicate component override {key!r}")
        seen.add(key)
        record: dict[str, Any] = {"component_id": cid, "component_type": ctype,
                                  "enabled": True}
        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"component_overrides[{i}].enabled must be a bool")
        record["enabled"] = enabled
        for field in ("conversion_rate_override", "independent_accrual_override",
                      "repair_ceiling_override", "weight_override"):
            value = item.get(field, None)
            if value is None:
                record[field] = None
            else:
                record[field] = _require_number(value, f"component_overrides[{i}].{field}",
                                               lo=0.0)
        # Concrete ids are checked against the live catalogs (drivers /
        # proxies); global/info/mutation/niche/entropy ids are free-form
        # but must be non-empty (checked above).
        if record["enabled"] and ctype == "driver":
            from longevity.model.aging import AGING_DRIVERS  # deferred

            if cid not in AGING_DRIVERS:
                raise ValueError(f"component_overrides[{i}].component_id unknown driver {cid!r}")
        if record["enabled"] and ctype == "organ":
            from longevity.model.organ_backed import ORGAN_PROXIES  # deferred

            if cid not in ORGAN_PROXIES:
                raise ValueError(f"component_overrides[{i}].component_id unknown organ {cid!r}")
        validated.append(record)
    return validated


def default_boundary_state() -> dict[str, Any]:
    """Fresh neutral ablation snapshot (all scales 1.0, all flags false)."""
    return {
        "params": validate_boundary_params(None),
        "overrides": [],
        "exploratory": False,
        "ablation_flags_hash": _ablation_hash(validate_boundary_params(None), []),
    }


def _ablation_hash(params: dict[str, Any], overrides: list[dict[str, Any]]) -> str:
    canonical = json.dumps({"params": params, "overrides": overrides},
                           sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def validate_boundary_state(state: Any) -> dict[str, Any] | None:
    if state is None:
        return None
    if not isinstance(state, dict):
        raise ValueError(f"boundary state must be a dict or None, got {state!r}")
    validate_boundary_params(state.get("params", {}))
    validate_component_overrides(state.get("overrides", []))
    if not isinstance(state.get("exploratory"), bool):
        raise ValueError("boundary.exploratory must be a bool")
    if not isinstance(state.get("ablation_flags_hash", ""), str):
        raise ValueError("boundary.ablation_flags_hash must be a string")
    return state


def is_neutral_boundary(params: dict[str, Any], overrides: list[dict[str, Any]]) -> bool:
    """True when the ablation layer reproduces Stage 6C exactly."""
    return (params.get("conversion_scale", 1.0) == 1.0
            and params.get("independent_accrual_scale", 1.0) == 1.0
            and params.get("repair_ceiling_scale", 1.0) == 1.0
            and not any(params.get(flag, False) for flag in BOUNDARY_FLAGS)
            and len([o for o in overrides if o.get("enabled", True)]) == 0)


def effective_conversion_scale(params: dict[str, Any],
                               override: float | None = None) -> float:
    """Effective conversion multiplier for one component (pure)."""
    if params.get("disable_conversion", False):
        return 0.0
    scale = max(0.0, float(params.get("conversion_scale", 1.0)))
    if override is not None:
        scale *= max(0.0, float(override))
    return scale


def effective_independent_scale(params: dict[str, Any],
                                override: float | None = None) -> float:
    """Effective independent-accrual multiplier for one component (pure)."""
    if params.get("disable_independent_accrual", False):
        return 0.0
    scale = max(0.0, float(params.get("independent_accrual_scale", 1.0)))
    if override is not None:
        scale *= max(0.0, float(override))
    return scale


def effective_repair_ceiling(base_ceiling: float, params: dict[str, Any]) -> tuple[float, bool]:
    """Effective repair ceiling + exploratory flag (pure).

    Returns (ceiling, exploratory). Unlimited / disabled-ceiling modes
    return a large finite sentinel (1e6) and exploratory=True so metadata
    marks them as non-physiological diagnostic ablations.
    """
    if params.get("force_repair_ceiling_unlimited", False) \
            or params.get("disable_repair_ceiling", False):
        return (1e6, True)
    return (max(0.0, float(base_ceiling)) * max(0.0, float(params.get("repair_ceiling_scale", 1.0))),
            False)


def override_for(overrides: list[dict[str, Any]], ctype: str,
                 cid: str) -> dict[str, Any] | None:
    """Enabled override for one component, if any (pure, deterministic)."""
    for item in overrides:
        if item.get("component_type") == ctype and item.get("component_id") == cid \
                and item.get("enabled", True):
            return item
    return None
