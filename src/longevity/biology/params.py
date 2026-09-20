from __future__ import annotations

import copy
from typing import Any

DEFAULT_PARAMETERS: dict[str, Any] = {
    "doubling_time_mean": 10.8,
    "doubling_time_sd": 1.2,
}

TOP_LEVEL_KEYS = ("doubling_time_mean", "doubling_time_sd", "telomere", "dna_damage", "mortality", "cell_cycle")
TELOMERE_KEYS = ("length_start", "loss_per_division")
DNA_DAMAGE_KEYS = ("accrual_per_division", "threshold", "repair_per_division")
MORTALITY_KEYS = ("rate",)
CELL_CYCLE_KEYS = ("phases",)
PHASE_KEYS = ("threshold", "mean", "sd", "death_per_division")


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

    cell_cycle = params.get("cell_cycle")
    if cell_cycle is not None:
        _validate_cell_cycle(cell_cycle, params["doubling_time_sd"])

    return params


def _validate_cell_cycle(cell_cycle: Any, fallback_sd: float) -> None:
    """Validate the `cell_cycle` feature group.

    `cell_cycle` is an OPTIONAL feature like `mortality`: when absent (the
    default) the engine draws every division from the constant
    `doubling_time_mean`/`doubling_time_sd`. When present it carries an ordered
    list of phases, each selected by the embryo's living cell count at the
    moment a doubling time is drawn:

        {"phases": [{"threshold": 0, "mean": 26.0, "sd": 2.0}, ...]}

    Rules:
    - thresholds must be strictly increasing and the first must be 0;
    - the phase whose threshold is the largest value <= living count applies;
    - `mean` is the per-division cycle length of that phase (hours);
    - `sd` defaults to the top-level `doubling_time_sd`;
    - `death_per_division` (per-phase, default 0) is a per-division chance the
      dividing cell dies instead of producing daughters -- the stage-selective
      mortality mechanism (Model C), a documented blastocyst phenomenon
      (Hardy 1989) whose rate is an assumption.
    """
    if not isinstance(cell_cycle, dict):
        raise ValueError("cell_cycle must be a dict")
    unknown_top = set(cell_cycle) - set(CELL_CYCLE_KEYS)
    if unknown_top:
        raise ValueError(f"unknown cell_cycle parameters: {sorted(unknown_top)}")

    phases = cell_cycle.get("phases")
    if not isinstance(phases, list) or not phases:
        raise ValueError("cell_cycle.phases must be a non-empty list")

    prev_threshold: float | None = None
    for index, phase in enumerate(phases):
        path = f"cell_cycle.phases.{index}"
        if not isinstance(phase, dict):
            raise ValueError(f"{path} must be a dict")
        unknown = set(phase) - set(PHASE_KEYS)
        if unknown:
            raise ValueError(f"unknown {path} parameters: {sorted(unknown)}")

        threshold = phase.get("threshold")
        if threshold is None:
            raise ValueError(f"{path}.threshold is required")
        _require_number(threshold, f"{path}.threshold", lo=0.0)
        if index == 0 and threshold != 0:
            raise ValueError("cell_cycle.phases[0].threshold must be 0")
        if prev_threshold is not None and threshold <= prev_threshold:
            raise ValueError("cell_cycle phase thresholds must be strictly increasing")

        mean = phase.get("mean")
        if mean is None:
            raise ValueError(f"{path}.mean is required")
        _require_number(mean, f"{path}.mean", lo=0.1)

        phase.setdefault("sd", fallback_sd)
        _require_number(phase["sd"], f"{path}.sd", lo=0.0)

        phase.setdefault("death_per_division", 0.0)
        _require_number(phase["death_per_division"], f"{path}.death_per_division", lo=0.0, hi=1.0)

        prev_threshold = float(threshold)


def apply_interventions(parameters: dict[str, Any], interventions: list[dict[str, Any]]) -> dict[str, Any]:
    """Start from `parameters`, overlay each intervention, re-validate.

    An intervention is {"parameter": "dotted.path", "value": ...}. Nested
    feature dicts (e.g. `telomere.loss_per_division`) are created on demand so
    enabling a feature counts as an intervention of its own.
    """
    params = validate_parameters(copy.deepcopy(parameters))
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
            if isinstance(target, list):
                target = target[int(key)]
                continue
            current = target[key] if key in target else None
            if isinstance(current, (dict, list)):
                target = current
                continue
            target[key] = {}
            target = target[key]
        if isinstance(target, list):
            target[int(keys[-1])] = value
        else:
            target[keys[-1]] = value
    return validate_parameters(params)