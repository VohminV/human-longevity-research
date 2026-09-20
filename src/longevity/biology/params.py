from __future__ import annotations

from typing import Any

DEFAULT_PARAMETERS: dict[str, Any] = {
    "doubling_time_mean": 10.8,
    "doubling_time_sd": 1.2,
}

TOP_LEVEL_KEYS = ("doubling_time_mean", "doubling_time_sd", "telomere", "dna_damage", "mortality")
TELOMERE_KEYS = ("length_start", "loss_per_division")
DNA_DAMAGE_KEYS = ("accrual_per_division", "threshold", "repair_per_division")
MORTALITY_KEYS = ("rate",)


def _require_number(value: Any, path: str, lo: float | None = None, hi: float | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number, got {value!r}")
    if lo is not None and value < lo:
        raise ValueError(f"{path} must be >= {lo}")
    if hi is not None and value > hi:
        raise ValueError(f"{path} must be <= {hi}")


def validate_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a parameter dict, filling data-derived defaults.

    `telomere` and `dna_damage` are OPTIONAL features: when the key is absent
    they are disabled; when present (even empty) the feature is on, and every
    sub-key has a documented default (MODEL defaults, not measurements).
    """
    params = dict(DEFAULT_PARAMETERS)
    params.update(parameters)

    unknown = set(params) - set(TOP_LEVEL_KEYS)
    if unknown:
        raise ValueError(f"unknown top-level parameters: {sorted(unknown)}")

    _require_number(params["doubling_time_mean"], "doubling_time_mean", lo=0.1)
    _require_number(params["doubling_time_sd"], "doubling_time_sd", lo=0.0)

    telomere = params.get("telomere")
    if telomere is not None:
        if not isinstance(telomere, dict):
            raise ValueError("telomere must be a dict")
        unknown_t = set(telomere) - set(TELOMERE_KEYS)
        if unknown_t:
            raise ValueError(f"unknown telomere parameters: {sorted(unknown_t)}")
        telomere.setdefault("length_start", 100.0)
        telomere.setdefault("loss_per_division", 5.0)
        _require_number(telomere["length_start"], "telomere.length_start", lo=0.1)
        _require_number(telomere["loss_per_division"], "telomere.loss_per_division", lo=0.0)

    dna_damage = params.get("dna_damage")
    if dna_damage is not None:
        if not isinstance(dna_damage, dict):
            raise ValueError("dna_damage must be a dict")
        unknown_d = set(dna_damage) - set(DNA_DAMAGE_KEYS)
        if unknown_d:
            raise ValueError(f"unknown dna_damage parameters: {sorted(unknown_d)}")
        dna_damage.setdefault("accrual_per_division", 0.2)
        dna_damage.setdefault("threshold", 5.0)
        dna_damage.setdefault("repair_per_division", 0.0)
        _require_number(dna_damage["accrual_per_division"], "dna_damage.accrual_per_division", lo=0.0)
        _require_number(dna_damage["threshold"], "dna_damage.threshold", lo=0.0)
        _require_number(dna_damage["repair_per_division"], "dna_damage.repair_per_division", lo=0.0)

    mortality = params.get("mortality")
    if mortality is not None:
        if not isinstance(mortality, dict):
            raise ValueError("mortality must be a dict")
        unknown_m = set(mortality) - set(MORTALITY_KEYS)
        if unknown_m:
            raise ValueError(f"unknown mortality parameters: {sorted(unknown_m)}")
        mortality.setdefault("rate", 0.0)
        _require_number(mortality["rate"], "mortality.rate", lo=0.0, hi=1.0)

    return params


def apply_interventions(parameters: dict[str, Any], interventions: list[dict[str, Any]]) -> dict[str, Any]:
    """Start from `parameters`, overlay each intervention, re-validate.

    An intervention is {"parameter": "dotted.path", "value": ...}. Nested
    feature dicts (e.g. `telomere.loss_per_division`) are created on demand so
    enabling a feature counts as an intervention of its own.
    """
    params = validate_parameters(parameters)
    for intervention in interventions:
        path = intervention["parameter"]
        value = intervention["value"]
        keys = path.split(".")
        if not keys[0]:
            raise ValueError(f"empty parameter path in intervention: {intervention!r}")
        if keys[0] not in TOP_LEVEL_KEYS:
            raise ValueError(f"unknown intervention parameter: {path}")
        target = params
        for key in keys[:-1]:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value
    return validate_parameters(params)