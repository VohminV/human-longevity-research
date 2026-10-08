"""EPIGENETIC BACKUP LAYER: information-preservation model (Stage 9 prototype).

Shifts the frame from a "Repair Model" (scrub damage after it lands) to an
"Information Preservation Model": the organism carries a frozen
``reference_epigenome`` (captured at ``adult_age_setpoint``) and a
read/restore channel that can roll Shannon epigenetic entropy back toward
that reference without touching cell identity.

All numbers are OPERATIONAL model choices, not biological measurements.
Opt-in only: ``epigenetic_backup_model="none"`` reproduces legacy dynamics
bit-for-bit. Deterministic: no RNG draws inside this module; the caller
applies jitter. State is JSON-serializable and checkpoint-covered.
"""

from __future__ import annotations

import math

from typing import Any

EPIGENETIC_BACKUP_MODELS = ("none", "reference_restore")

EPIGENETIC_BACKUP_SCOPE = "abstract_epigenetic_backup_organism_life_course"

# Operational defaults (O-9-1...; ordinal rates, not measurements).
DEFAULT_EPIGENETIC_BACKUP_PARAMS: dict[str, Any] = {
    # Entropy generation: baseline noise + TE proxy + metabolic byproducts.
    "noise_generation_base": 0.004,
    "te_coupling": 0.6,
    "metabolic_coupling": 0.4,
    # Endogenous repair of epigenetic noise (maintenance methylation etc.).
    "repair_capacity": 0.002,
    # Restore channel efficiency per rollback event (fraction of the gap
    # between current entropy and the reference minimum that one full-
    # intensity pulse closes).
    "backup_restore_efficiency": 0.85,
    # Safety gate: rollback fires ONLY while cancer_prone driver damage is
    # strictly below this threshold (fail-closed).
    "rollback_cancer_gate": 0.15,
    # Synthetic apoptosis: mutation burden strictly above this forces a
    # clearance event BEFORE any rollback may occur.
    "apoptosis_mutation_threshold": 0.35,
    "apoptosis_clearance": 0.05,
    # Rollback repair magnitudes at intensity 1.0.
    "rollback_entropy_reset_fraction": 0.9,
    "rollback_drift_repair": 0.05,
    "rollback_information_repair": 0.05,
    # Rollback price (no free lunch): small cancer + reserve cost.
    "rollback_cancer_cost": 0.002,
    "rollback_reserve_cost": 0.01,
    # Meta-driver weight: entropy contribution to biological age.
    "entropy_bio_weight": 8.0,
    # Extra epigenetic_drift accumulation per unit of entropy (noise echo).
    "drift_noise_coupling": 0.15,
    # Sanitized genome (no retrotransposons): residual factor applied to
    # dna_damage accumulation and mutation fixation (0.1 = 90% drop).
    "genome_sanitized": False,
    "sanitized_dna_factor": 0.1,
    # Backup-drive readability wall.
    "max_entropy": 1.0,
    "wall_read_threshold": 0.8,
    "min_read_fidelity": 0.2,
}

_PARAM_BOUNDS: dict[str, tuple[float | None, float | None]] = {
    "noise_generation_base": (0.0, None),
    "te_coupling": (0.0, None),
    "metabolic_coupling": (0.0, None),
    "repair_capacity": (0.0, None),
    "backup_restore_efficiency": (0.0, 1.0),
    "rollback_cancer_gate": (0.0, 1.0),
    "apoptosis_mutation_threshold": (0.0, 1.0),
    "apoptosis_clearance": (0.0, 1.0),
    "rollback_entropy_reset_fraction": (0.0, 1.0),
    "rollback_drift_repair": (0.0, 1.0),
    "rollback_information_repair": (0.0, 1.0),
    "rollback_cancer_cost": (0.0, None),
    "rollback_reserve_cost": (0.0, None),
    "entropy_bio_weight": (0.0, None),
    "drift_noise_coupling": (0.0, None),
    "sanitized_dna_factor": (0.0, 1.0),
    "max_entropy": (0.0, None),
    "wall_read_threshold": (0.0, None),
    "min_read_fidelity": (0.0, 1.0),
}


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


def validate_epigenetic_backup_model(model: Any) -> str:
    """Validate the epigenetic backup model name."""
    if not isinstance(model, str) or model not in EPIGENETIC_BACKUP_MODELS:
        raise ValueError(
            f"epigenetic_backup_model must be one of {EPIGENETIC_BACKUP_MODELS}, got {model!r}")
    return model


def scope_for_epigenetic_backup_model(mode: str) -> str:
    """Model scope string for the backup mode (appends to 6C scope chain)."""
    from longevity.model.reversibility import REVERSIBILITY_SCOPE  # deferred

    return EPIGENETIC_BACKUP_SCOPE if validate_epigenetic_backup_model(mode) != "none" \
        else REVERSIBILITY_SCOPE


def validate_epigenetic_backup_params(params: Any) -> dict[str, Any]:
    """Validate the backup parameter block (missing keys get defaults)."""
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError(f"epigenetic_backup_params must be a dict, got {params!r}")
    unknown = set(params) - set(DEFAULT_EPIGENETIC_BACKUP_PARAMS)
    if unknown:
        raise ValueError(f"unknown epigenetic backup param keys: {sorted(unknown)}")
    merged = dict(DEFAULT_EPIGENETIC_BACKUP_PARAMS)
    merged.update(params)
    validated: dict[str, Any] = {}
    for key, value in merged.items():
        if key == "genome_sanitized":
            if not isinstance(value, bool):
                raise ValueError(f"epigenetic_backup_params.{key} must be a bool, got {value!r}")
            validated[key] = bool(value)
            continue
        lo, hi = _PARAM_BOUNDS[key]
        validated[key] = _require_number(value, f"epigenetic_backup_params.{key}", lo=lo, hi=hi)
    if validated["wall_read_threshold"] > validated["max_entropy"]:
        raise ValueError("epigenetic_backup_params.wall_read_threshold must be <= max_entropy")
    return validated


def default_epigenetic_backup_state() -> dict[str, Any]:
    """Fresh backup state: clean drive, reference not yet captured."""
    params = validate_epigenetic_backup_params(None)
    return {
        "epigenetic_entropy": 0.0,
        "reference_captured": False,
        "reference_age": None,
        "reference_entropy": 0.0,
        "reference_drift": 0.0,
        "backup_read_fidelity": 1.0,
        "cumulative_restored": 0.0,
        "rollback_events": 0,
        "rollback_blocked": 0,
        "apoptosis_events": 0,
        "noise_auc": 0.0,
        "restore_auc": 0.0,
        "genome_sanitized": bool(params["genome_sanitized"]),
    }


def validate_epigenetic_backup_state(state: Any) -> dict[str, Any] | None:
    """Validate a backup sub-state (None passes through for legacy states)."""
    if state is None:
        return None
    if not isinstance(state, dict):
        raise ValueError(f"epigenetic_backup state must be a dict or None, got {state!r}")
    for key in ("epigenetic_entropy", "reference_entropy", "reference_drift",
                "backup_read_fidelity", "cumulative_restored", "noise_auc", "restore_auc"):
        _require_number(state.get(key), f"epigenetic_backup.{key}", lo=0.0)
    if not 0.0 <= float(state.get("backup_read_fidelity", 1.0)) <= 1.0:
        raise ValueError("epigenetic_backup.backup_read_fidelity out of [0, 1]")
    if not isinstance(state.get("reference_captured"), bool):
        raise ValueError("epigenetic_backup.reference_captured must be a bool")
    if state.get("reference_age") is not None:
        _require_number(state["reference_age"], "epigenetic_backup.reference_age", lo=0.0)
    for key in ("rollback_events", "rollback_blocked", "apoptosis_events"):
        value = state.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"epigenetic_backup.{key} must be int >= 0")
    if not isinstance(state.get("genome_sanitized"), bool):
        raise ValueError("epigenetic_backup.genome_sanitized must be a bool")
    return state


def sanitization_factor(params: dict[str, Any]) -> float:
    """Residual aging factor for sanitized genomes (0.1 = 90% drop)."""
    if bool(params.get("genome_sanitized", False)):
        return max(0.0, min(1.0, float(params.get("sanitized_dna_factor", 0.1))))
    return 1.0


def entropy_noise_rate(epigenetic_drift_damage: float, mitochondrial_damage: float,
                       inflammation: float, params: dict[str, Any]) -> dict[str, float]:
    """Split Shannon noise generation into named sources (pure).

    TE proxy (LINE-1/Alu reactivation): derepression follows accumulated
    epigenetic drift plus inflammatory signalling. Metabolic byproducts:
    follow mitochondrial dysfunction. Returns per-source rates and total.
    """
    drift = max(0.0, min(1.0, float(epigenetic_drift_damage)))
    mito = max(0.0, min(1.0, float(mitochondrial_damage)))
    infl = max(0.0, min(1.0, float(inflammation)))
    base = max(0.0, float(params.get("noise_generation_base", 0.0)))
    te_rate = base * max(0.0, float(params.get("te_coupling", 0.0))) * (0.5 * drift + 0.5 * infl)
    metabolic_rate = base * max(0.0, float(params.get("metabolic_coupling", 0.0))) * mito
    return {"base": base, "te_rate": te_rate, "metabolic_rate": metabolic_rate,
            "total": base + te_rate + metabolic_rate}


def entropy_step(backup: dict[str, Any], dt: float, mult: float,
                 epigenetic_drift_damage: float, mitochondrial_damage: float,
                 inflammation: float, params: dict[str, Any]) -> dict[str, float]:
    """Advance Shannon epigenetic entropy one step (mutates ``backup``).

    dH_epi/dt = Noise_Generation - Repair_Capacity - Backup_Restore_Rate,
    where the restore term is event-driven (rollback pulses) and therefore
    zero here; this step handles generation minus endogenous repair only.
    Fidelity decays as entropy approaches the readability wall.

    Returns the applied flux breakdown (all >= 0, finite, deterministic).
    """
    noise = entropy_noise_rate(epigenetic_drift_damage, mitochondrial_damage,
                               inflammation, params)
    generation = noise["total"] * mult * dt
    repair = min(float(backup.get("epigenetic_entropy", 0.0)),
                 max(0.0, float(params.get("repair_capacity", 0.0))) * mult * dt)
    entropy = max(0.0, min(float(params.get("max_entropy", 1.0)),
                            float(backup.get("epigenetic_entropy", 0.0)) + generation - repair))
    backup["epigenetic_entropy"] = entropy
    backup["noise_auc"] = max(0.0, float(backup.get("noise_auc", 0.0)) + generation)
    threshold = max(1e-9, float(params.get("wall_read_threshold", 0.8)))
    fidelity = max(float(params.get("min_read_fidelity", 0.2)),
                   1.0 - (1.0 - float(params.get("min_read_fidelity", 0.2))) * entropy / threshold)
    backup["backup_read_fidelity"] = max(0.0, min(1.0, fidelity))
    return {"generation": generation, "repair": repair, "te_rate": noise["te_rate"] * mult * dt,
            "metabolic_rate": noise["metabolic_rate"] * mult * dt, "entropy": entropy}


def capture_reference(backup: dict[str, Any], chronological_age: float,
                      epigenetic_drift_damage: float) -> bool:
    """Freeze the reference epigenome once (idempotent, returns True if new)."""
    if bool(backup.get("reference_captured", False)):
        return False
    backup["reference_captured"] = True
    backup["reference_age"] = float(chronological_age)
    backup["reference_entropy"] = float(backup.get("epigenetic_entropy", 0.0))
    backup["reference_drift"] = max(0.0, float(epigenetic_drift_damage))
    return True


def mutation_burden(reversibility: dict[str, Any] | None,
                    driver_damages: dict[str, float]) -> float:
    """Operational mutation burden: fixed mutations + dna damage (pure)."""
    fixed = 0.0
    if reversibility is not None:
        fixed = max(0.0, min(1.0, float(reversibility.get("mutation_fixation", 0.0))))
    dna = max(0.0, min(1.0, float(driver_damages.get("dna_damage", 0.0))))
    return max(0.0, min(1.0, 0.6 * fixed + 0.4 * dna))


def apply_rollback(backup: dict[str, Any], reversibility: dict[str, Any] | None,
                   drivers: dict[str, dict[str, float]], driver_params: dict[str, dict[str, float]],
                   cancer_prone_damage: float, intensity: float,
                   params: dict[str, Any]) -> dict[str, Any]:
    """Attempt one rollback pulse against the reference (mutates state).

    Fail-closed ordering (deterministic, no RNG):
    1. If mutation burden exceeds ``apoptosis_mutation_threshold``,
       synthetic apoptosis fires INSTEAD: burden is cleared by
       ``apoptosis_clearance`` and the rollback is deferred (blocked).
    2. Else if ``cancer_prone`` damage is at/above ``rollback_cancer_gate``,
       the pulse is blocked (rolling back a mutated epigenome would fix a
       malignant program in place).
    3. Else the pulse restores entropy toward the reference minimum,
       repairs ``epigenetic_drift`` driver damage (bounded by floor), and
       clears part of ``information_debt`` — without touching cell
       identity (no neural-continuity delta, unlike reprogramming).

    Returns a JSON-safe event record.
    """
    from longevity.model.aging import effective_reversal  # deferred: avoid import cycle

    intensity = max(0.0, float(intensity))
    burden = mutation_burden(reversibility, {n: float(c.get("damage", 0.0)) for n, c in drivers.items()})
    event: dict[str, Any] = {"fired": False, "blocked_reason": "none",
                             "apoptosis_first": False, "restored": 0.0,
                             "intensity": intensity}
    if intensity <= 0.0:
        event["blocked_reason"] = "zero_intensity"
        backup["rollback_blocked"] = int(backup.get("rollback_blocked", 0)) + 1
        return event
    if burden > float(params.get("apoptosis_mutation_threshold", 0.35)):
        # Synthetic apoptosis first: purge mutation-bearing burden.
        clearance = max(0.0, min(1.0, float(params.get("apoptosis_clearance", 0.05)))) * intensity
        if "dna_damage" in drivers:
            cell = drivers["dna_damage"]
            floor = float(driver_params.get("dna_damage", {}).get("floor", 0.0))
            cell["damage"] = max(floor, float(cell.get("damage", 0.0)) - clearance)
        if reversibility is not None:
            reversibility["mutation_fixation"] = max(
                0.0, min(1.0, float(reversibility.get("mutation_fixation", 0.0)) - clearance))
        backup["apoptosis_events"] = int(backup.get("apoptosis_events", 0)) + 1
        backup["rollback_blocked"] = int(backup.get("rollback_blocked", 0)) + 1
        event["apoptosis_first"] = True
        event["blocked_reason"] = "mutation_burden_apoptosis_first"
        event["apoptosis_clearance"] = clearance
        return event
    if float(cancer_prone_damage) >= float(params.get("rollback_cancer_gate", 0.15)):
        backup["rollback_blocked"] = int(backup.get("rollback_blocked", 0)) + 1
        event["blocked_reason"] = "cancer_gate"
        event["cancer_prone_damage"] = float(cancer_prone_damage)
        return event
    # Precise restore toward the reference minimum.
    efficiency = max(0.0, min(1.0, float(params.get("backup_restore_efficiency", 0.85))))
    fidelity = max(0.0, min(1.0, float(backup.get("backup_read_fidelity", 1.0))))
    reset_fraction = max(0.0, min(1.0, float(params.get("rollback_entropy_reset_fraction", 0.9))))
    floor_entropy = float(backup.get("reference_entropy", 0.0)) if backup.get("reference_captured") else 0.0
    gap = max(0.0, float(backup.get("epigenetic_entropy", 0.0)) - floor_entropy)
    restored = gap * reset_fraction * efficiency * fidelity * min(1.0, intensity)
    backup["epigenetic_entropy"] = max(floor_entropy, float(backup.get("epigenetic_entropy", 0.0)) - restored)
    backup["cumulative_restored"] = max(0.0, float(backup.get("cumulative_restored", 0.0)) + restored)
    backup["restore_auc"] = max(0.0, float(backup.get("restore_auc", 0.0)) + restored)
    if "epigenetic_drift" in drivers:
        requested = max(0.0, float(params.get("rollback_drift_repair", 0.05))) * intensity
        cell = drivers["epigenetic_drift"]
        realized = effective_reversal(
            requested, float(cell.get("damage", 0.0)),
            float(driver_params.get("epigenetic_drift", {}).get("reversibility", 0.8)),
            float(driver_params.get("epigenetic_drift", {}).get("reversal_saturation", 0.8)))
        floor = float(driver_params.get("epigenetic_drift", {}).get("floor", 0.0))
        cell["damage"] = max(floor, float(cell.get("damage", 0.0)) - realized)
        event["drift_repaired"] = realized
    if reversibility is not None:
        info_repair = max(0.0, float(params.get("rollback_information_repair", 0.05))) * intensity
        reversibility["information_debt"] = max(
            0.0, min(1.0, float(reversibility.get("information_debt", 0.0)) - info_repair))
        event["information_repaired"] = info_repair
    backup["rollback_events"] = int(backup.get("rollback_events", 0)) + 1
    event["fired"] = True
    event["restored"] = restored
    return event


def entropy_bio_contribution(epigenetic_entropy: float, params: dict[str, Any]) -> float:
    """Meta-driver contribution of Shannon entropy to biological age (pure)."""
    return max(0.0, float(params.get("entropy_bio_weight", 8.0))) * max(0.0, float(epigenetic_entropy))


def information_wall_proximity(backup: dict[str, Any] | None,
                               params: dict[str, Any] | None = None) -> dict[str, Any]:
    """How close the organism is to losing the Backup Drive (pure).

    Proximity in [0, 1]: 0 = clean readable drive, 1 = wall reached.
    ``readable`` is False once entropy passes ``wall_read_threshold``
    (the drive can no longer template a faithful restore).
    """
    params = validate_epigenetic_backup_params(params)
    if backup is None:
        return {"has_backup": False, "proximity": 0.0, "readable": True,
                "epigenetic_entropy": 0.0, "backup_read_fidelity": 1.0,
                "deterministic": True}
    entropy = max(0.0, float(backup.get("epigenetic_entropy", 0.0)))
    threshold = max(1e-9, float(params.get("wall_read_threshold", 0.8)))
    proximity = max(0.0, min(1.0, entropy / threshold))
    return {"has_backup": True, "proximity": proximity,
            "readable": bool(entropy < float(params.get("wall_read_threshold", 0.8))),
            "epigenetic_entropy": entropy,
            "backup_read_fidelity": max(0.0, min(1.0, float(backup.get("backup_read_fidelity", 1.0)))),
            "rollback_events": int(backup.get("rollback_events", 0)),
            "rollback_blocked": int(backup.get("rollback_blocked", 0)),
            "apoptosis_events": int(backup.get("apoptosis_events", 0)),
            "deterministic": True}


def information_wall_proximity_ru(proximity: float, readable: bool) -> str:
    """Russian human-readable wall proximity label (pure)."""
    if not readable:
        return "стенка чтения достигнута"
    if proximity >= 0.75:
        return "близко к стенке чтения"
    if proximity >= 0.4:
        return "умеренная близость к стенке"
    return "драйв читаем"
