"""AGING MODEL LAYER: mechanistic aging drivers (Stage 5C).

Decomposes biological age into damage-driven components with their own
accumulation, repair, reversibility, and diminishing returns. All numbers
are OPERATIONAL model choices, not biological measurements (see
docs/AGING_MODEL.md). Pure validation + math helpers; state lives in
``OrganismState.aging``.
"""

from __future__ import annotations

import math

from typing import Any

AGING_MECHANISM_MODELS = ("none", "mechanistic_drivers")

# v0 driver set (brief §3). telomere_attrition is proxied through
# stem_exhaustion; altered_intercellular_communication and fibrosis_prone
# are reserved extensions (rejected explicitly by validation).
AGING_DRIVERS = (
    "dna_damage",
    "epigenetic_drift",
    "proteostasis_loss",
    "mitochondrial_dysfunction",
    "cellular_senescence",
    "stem_exhaustion",
    "chronic_inflammation",
    "cancer_prone",
)

RESERVED_DRIVERS = ("telomere_attrition", "altered_intercellular_communication", "fibrosis_prone")

DEFAULT_DRIVER_PARAMS: dict[str, dict[str, float]] = {
    "dna_damage": {"base_aging_rate": 0.006, "repair_capacity": 0.004, "reversibility": 0.7,
                   "contribution": 25.0, "reversal_saturation": 0.8, "floor": 0.0, "adult_reference": 1.0},
    "epigenetic_drift": {"base_aging_rate": 0.005, "repair_capacity": 0.002, "reversibility": 0.8,
                         "contribution": 25.0, "reversal_saturation": 0.8, "floor": 0.0, "adult_reference": 1.0},
    "proteostasis_loss": {"base_aging_rate": 0.004, "repair_capacity": 0.003, "reversibility": 0.6,
                          "contribution": 20.0, "reversal_saturation": 0.8, "floor": 0.0, "adult_reference": 1.0},
    "mitochondrial_dysfunction": {"base_aging_rate": 0.004, "repair_capacity": 0.003, "reversibility": 0.6,
                                  "contribution": 20.0, "reversal_saturation": 0.8, "floor": 0.0, "adult_reference": 1.0},
    "cellular_senescence": {"base_aging_rate": 0.005, "repair_capacity": 0.002, "reversibility": 0.9,
                            "contribution": 30.0, "reversal_saturation": 0.8, "floor": 0.0, "adult_reference": 1.0},
    "stem_exhaustion": {"base_aging_rate": 0.004, "repair_capacity": 0.002, "reversibility": 0.5,
                        "contribution": 25.0, "reversal_saturation": 0.8, "floor": 0.0, "adult_reference": 1.0},
    "chronic_inflammation": {"base_aging_rate": 0.005, "repair_capacity": 0.003, "reversibility": 0.7,
                             "contribution": 25.0, "reversal_saturation": 0.8, "floor": 0.0, "adult_reference": 1.0},
    "cancer_prone": {"base_aging_rate": 0.003, "repair_capacity": 0.002, "reversibility": 0.4,
                     "contribution": 20.0, "reversal_saturation": 0.8, "floor": 0.0, "adult_reference": 1.0},
}

_DRIVER_PARAM_KEYS = ("base_aging_rate", "repair_capacity", "reversibility", "contribution",
                      "reversal_saturation", "floor", "adult_reference")


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


def validate_aging_model(model: Any) -> str:
    """Validate an aging mechanism model name."""
    if not isinstance(model, str) or model not in AGING_MECHANISM_MODELS:
        raise ValueError(f"aging_mechanism_model must be one of {AGING_MECHANISM_MODELS}, got {model!r}")
    return model


def validate_driver_params(name: str, params: dict[str, Any]) -> dict[str, float]:
    """Validate one driver's parameter block."""
    if name in RESERVED_DRIVERS:
        raise ValueError(f"driver {name!r} is a reserved extension, not implemented in v0")
    if name not in AGING_DRIVERS:
        raise ValueError(f"unknown aging driver {name!r}; known: {list(AGING_DRIVERS)}")
    if not isinstance(params, dict):
        raise ValueError(f"driver {name!r} params must be a dict")
    merged = dict(DEFAULT_DRIVER_PARAMS[name])
    merged.update(params)
    unknown = set(merged) - set(_DRIVER_PARAM_KEYS)
    if unknown:
        raise ValueError(f"driver {name!r} unknown keys: {sorted(unknown)}")
    validated: dict[str, float] = {}
    for key in _DRIVER_PARAM_KEYS:
        lo, hi = 0.0, None
        if key in ("reversibility", "floor"):
            hi = 1.0
        validated[key] = _require_number(merged[key], f"drivers.{name}.{key}", lo=lo, hi=hi)
    if validated["floor"] > 1.0:
        raise ValueError(f"drivers.{name}.floor must be <= 1")
    return validated


def validate_aging_drivers(drivers: dict[str, Any] | None) -> dict[str, dict[str, float]]:
    """Validate the full driver parameter block (missing drivers get defaults)."""
    if drivers is None:
        drivers = {}
    if not isinstance(drivers, dict):
        raise ValueError(f"aging_drivers must be a dict, got {drivers!r}")
    unknown = [name for name in drivers if name not in AGING_DRIVERS and name not in RESERVED_DRIVERS]
    if unknown:
        raise ValueError(f"unknown aging drivers: {sorted(unknown)}")
    reserved = [name for name in drivers if name in RESERVED_DRIVERS]
    if reserved:
        raise ValueError(f"drivers {sorted(reserved)} are reserved extensions, not implemented in v0")
    return {name: validate_driver_params(name, dict(drivers.get(name, {}))) for name in AGING_DRIVERS}


def default_driver_state() -> dict[str, Any]:
    """Fresh driver state: zero damage, empty reversal ledger."""
    return {"drivers": {name: {"damage": 0.0, "reversal_applied_total": 0.0} for name in AGING_DRIVERS},
            "age_reversal_events": []}


def aggregate_biological_age(driver_damages: dict[str, float], driver_params: dict[str, dict[str, float]],
                             adult_setpoint: float, allow_sub_adult: bool = False) -> tuple[float, dict[str, float]]:
    """Weighted bio-age aggregation with adult floor (pure).

    Returns (biological_age, per-driver contributions). Damage is normalized
    by adult_reference; the sum is floored at adult_setpoint unless
    sub-adult exploration is explicitly allowed.
    """
    contributions = {}
    for name in AGING_DRIVERS:
        reference = max(1e-9, float(driver_params[name]["adult_reference"]))
        contributions[name] = float(driver_params[name]["contribution"]) * max(0.0, float(driver_damages[name])) / reference
    total = float(adult_setpoint) + sum(contributions.values())
    floor = 0.0 if allow_sub_adult else float(adult_setpoint)
    return (max(floor, total), contributions)


def effective_reversal(requested: float, damage: float, reversibility: float, saturation: float) -> float:
    """Diminishing-returns reversal gate (pure, deterministic).

    Full effect near zero damage, linearly vanishing at saturation: the same
    intensity cannot push one driver to its floor for free.
    """
    if requested <= 0.0:
        return 0.0
    saturation = max(1e-9, float(saturation))
    gate = max(0.0, 1.0 - max(0.0, float(damage)) / saturation)
    return max(0.0, float(requested)) * max(0.0, min(1.0, float(reversibility))) * gate
