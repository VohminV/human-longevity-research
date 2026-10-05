"""REVERSIBILITY MODEL LAYER: reversible / irreversible split (Stage 6C).

Abstract, operational, non-calibrated. Adds an opt-in ledger over the
Stage 6B organ-network organism:

- per-driver reversible / irreversible damage split (8 mechanistic
  drivers; conversion reclassifies mass without changing total damage);
- per-organ-proxy reversible / irreversible split (8 reduced proxies);
- global irreversible pools: information_debt, mutation_fixation,
  niche_disorder, entropy_production;
- conversion reversible -> irreversible with inflammation / energy /
  repair / network / niche / toxicity modifiers;
- repair ceiling for irreversible damage with cost / risk /
  diminishing returns and a hard floor;
- reversibility-derived biological age with a dynamic irreversible floor.

``none`` mode is behaviorally inert by construction: no state, no
dynamics, no coordination change. All helpers are pure; state lives in
``OrganismState.reversibility``.
"""

from __future__ import annotations

import math

from typing import Any

REVERSIBILITY_MODELS = ("none", "split_reversible_irreversible")
REVERSIBILITY_SCOPE = "abstract_organ_network_reversibility_organism_life_course"

REVERSIBILITY_DEATH_CAUSES = (
    "irreversible_accumulation_failure",
    "repair_ceiling_exhaustion",
    "conversion_runaway",
    "information_debt_failure",
    "mutation_fixation_failure",
    "niche_disorder_failure",
    "entropy_production_failure",
    "biological_age_floor_erosion",
    "unknown_reversibility_collapse",
)

REVERSIBILITY_COORDINATION_MODES = (
    "independent_reversibility",
    "preventive_priority",
    "repair_ceiling_guard",
    "information_guard",
    "mutation_guard",
    "entropy_budget_scheduler",
    "lookahead_reversibility",
)

REVERSIBILITY_SHOCK_TYPES = (
    "conversion_spike",
    "repair_ceiling_shock",
)

DEFAULT_REVERSIBILITY_PARAMS: dict[str, float] = {
    "base_conversion_rate": 0.02,
    "inflammation_coupling": 1.0,
    "energy_coupling": 1.0,
    "repair_coupling": 1.0,
    "network_coupling": 0.8,
    "niche_coupling": 1.0,
    "toxicity_coupling": 0.5,
    "independent_irreversible_rate": 0.0008,
    "repair_ceiling": 0.30,
    "repair_cost_per_unit": 0.6,
    "repair_risk_per_unit": 0.4,
    "repair_diminishing": 0.6,
    "conversion_runaway_threshold": 0.05,
    "max_irreversible_slope": 0.004,
    "max_reversible_slope": 0.004,
    "max_information_debt": 0.6,
    "max_mutation_fixation": 0.6,
    "max_niche_disorder": 0.7,
    "max_entropy_rate": 0.05,
    "w_reversible": 10.0,
    "w_irreversible": 22.0,
    "w_information": 10.0,
    "w_mutation": 8.0,
    "w_niche": 6.0,
    "prevention_relief": 0.5,
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


def validate_reversibility_model(model: Any) -> str:
    if not isinstance(model, str) or model not in REVERSIBILITY_MODELS:
        raise ValueError(
            f"reversibility_model must be one of {REVERSIBILITY_MODELS}, got {model!r}")
    return model


def scope_for_reversibility_model(mode: str) -> str:
    from longevity.model.organ_network import ORGAN_NETWORK_SCOPE  # deferred

    return REVERSIBILITY_SCOPE if validate_reversibility_model(mode) != "none" \
        else ORGAN_NETWORK_SCOPE


def validate_reversibility_params(params: Any) -> dict[str, float]:
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError(f"reversibility_params must be a dict, got {params!r}")
    unknown = set(params) - set(DEFAULT_REVERSIBILITY_PARAMS)
    if unknown:
        raise ValueError(f"unknown reversibility param keys: {sorted(unknown)}")
    merged = dict(DEFAULT_REVERSIBILITY_PARAMS)
    merged.update(params)
    validated: dict[str, float] = {}
    for key, value in merged.items():
        hi = None
        if key in ("repair_ceiling", "max_information_debt", "max_mutation_fixation",
                   "max_niche_disorder", "repair_diminishing", "prevention_relief"):
            hi = 1.0
        validated[key] = _require_number(value, f"reversibility_params.{key}", lo=0.0, hi=hi)
    return validated


def default_reversibility_state() -> dict[str, Any]:
    from longevity.model.aging import AGING_DRIVERS  # deferred
    from longevity.model.organ_backed import ORGAN_PROXIES  # deferred

    params = validate_reversibility_params(None)
    return {
        "drivers": {
            name: {"reversible": 0.0, "irreversible": 0.0, "conversion_rate": 0.0,
                   "repair_used": 0.0}
            for name in AGING_DRIVERS
        },
        "organs": {
            pid: {"reversible": 0.0, "irreversible": 0.0, "conversion_rate": 0.0,
                  "repair_used": 0.0}
            for pid in ORGAN_PROXIES
        },
        "reversible_burden": 0.0,
        "irreversible_burden": 0.0,
        "total_conversion_flux": 0.0,
        "conversion_runaway": False,
        "time_to_first_conversion_threshold": None,
        "repair_ceiling": float(params["repair_ceiling"]),
        "repair_used_global": 0.0,
        "repair_remaining": float(params["repair_ceiling"]),
        "repair_cost_auc": 0.0,
        "repair_risk_auc": 0.0,
        "repair_ceiling_exhaustion_time": None,
        "information_debt": 0.0,
        "mutation_fixation": 0.0,
        "niche_disorder": 0.0,
        "entropy_production": 0.0,
        "entropy_auc": 0.0,
        "prevention_pending": 0.0,
        "biological_age_reversibility": 25.0,
        "biological_age_floor_dynamic": 25.0,
        "reversible_age_contribution": 0.0,
        "irreversible_age_contribution": 0.0,
        "network_failure_sequence": [],
        "failed_ids": [],
        "coordination_stats": {"preventive_priority_executions": 0,
                              "repair_ceiling_guard_rejections": 0,
                              "information_guard_rejections": 0,
                              "mutation_guard_rejections": 0},
    }


def validate_reversibility_state(state: Any) -> dict[str, Any] | None:
    if state is None:
        return None
    if not isinstance(state, dict):
        raise ValueError(f"reversibility state must be a dict or None, got {state!r}")
    for section in ("drivers", "organs"):
        block = state.get(section, {})
        if not isinstance(block, dict):
            raise ValueError(f"reversibility.{section} must be a dict")
        for name, comp in block.items():
            for key in ("reversible", "irreversible", "conversion_rate", "repair_used"):
                _require_number(comp.get(key), f"reversibility.{section}.{name}.{key}", lo=0.0)
            if not 0.0 <= float(comp.get("reversible", 0.0)) <= 1.0:
                raise ValueError(f"reversibility.{section}.{name}.reversible out of [0, 1]")
            if not 0.0 <= float(comp.get("irreversible", 0.0)) <= 1.0:
                raise ValueError(f"reversibility.{section}.{name}.irreversible out of [0, 1]")
    for key in ("reversible_burden", "irreversible_burden", "total_conversion_flux",
                "repair_ceiling", "repair_used_global", "repair_remaining",
                "repair_cost_auc", "repair_risk_auc", "information_debt",
                "mutation_fixation", "niche_disorder", "entropy_production",
                "entropy_auc", "prevention_pending", "biological_age_reversibility",
                "biological_age_floor_dynamic", "reversible_age_contribution",
                "irreversible_age_contribution"):
        _require_number(state.get(key), f"reversibility.{key}", lo=0.0)
    for key in ("information_debt", "mutation_fixation", "niche_disorder"):
        if not 0.0 <= float(state.get(key, 0.0)) <= 1.0:
            raise ValueError(f"reversibility.{key} out of [0, 1]")
    if not isinstance(state.get("conversion_runaway"), bool):
        raise ValueError("reversibility.conversion_runaway must be a bool")
    if state.get("time_to_first_conversion_threshold") is not None:
        _require_number(state["time_to_first_conversion_threshold"],
                        "reversibility.time_to_first_conversion_threshold", lo=0.0)
    if state.get("repair_ceiling_exhaustion_time") is not None:
        _require_number(state["repair_ceiling_exhaustion_time"],
                        "reversibility.repair_ceiling_exhaustion_time", lo=0.0)
    for key in ("network_failure_sequence", "failed_ids"):
        if not isinstance(state.get(key), list):
            raise ValueError(f"reversibility.{key} must be a list")
    stats = state.get("coordination_stats", {})
    for key in ("preventive_priority_executions", "repair_ceiling_guard_rejections",
                "information_guard_rejections", "mutation_guard_rejections"):
        value = stats.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"reversibility.coordination_stats.{key} must be int >= 0")
    return state


def conversion_modifiers(inflammation: float, energy_shortfall: float,
                         repair_shortfall: float, cascade_risk: float,
                         niche_disorder: float, toxicity: float,
                         params: dict[str, float]) -> float:
    """Multiplicative conversion modifier >= 1 (pure, deterministic)."""
    modifier = (1.0 + float(params["inflammation_coupling"]) * max(0.0, min(1.0, inflammation))
                + float(params["energy_coupling"]) * max(0.0, min(1.0, energy_shortfall))
                + float(params["repair_coupling"]) * max(0.0, min(1.0, repair_shortfall))
                + float(params["network_coupling"]) * max(0.0, min(1.0, cascade_risk))
                + float(params["niche_coupling"]) * max(0.0, min(1.0, niche_disorder))
                + float(params["toxicity_coupling"]) * max(0.0, min(1.0, toxicity)))
    return max(1.0, modifier)


def compute_reversibility_age(adult_setpoint: float, reversible: float,
                              irreversible: float, information: float,
                              mutation: float, niche: float,
                              params: dict[str, float],
                              allow_sub_adult: bool = False) -> tuple[float, float, float, float]:
    """Reversibility biological age (pure).

    Returns (bio_total, floor_dynamic, rev_contrib, irr_contrib).
    Floor = setpoint + irreversible-family contributions; never below
    setpoint unless sub-adult exploration is explicitly allowed.
    """
    rev = float(params["w_reversible"]) * max(0.0, reversible)
    irr = float(params["w_irreversible"]) * max(0.0, irreversible)
    info = float(params["w_information"]) * max(0.0, min(1.0, information))
    mut = float(params["w_mutation"]) * max(0.0, min(1.0, mutation))
    niche_c = float(params["w_niche"]) * max(0.0, min(1.0, niche))
    floor = float(adult_setpoint) + irr + info + mut + niche_c
    total = float(adult_setpoint) + rev + irr + info + mut + niche_c
    if not allow_sub_adult:
        total = max(total, floor)
        floor = max(float(adult_setpoint), floor)
    return (max(0.0, total), max(0.0, floor), max(0.0, rev), max(0.0, irr))


def coordinate_reversibility_effects(effects: list[dict[str, Any]],
                                     reversibility: dict[str, Any] | None,
                                     mode: str,
                                     queue: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Reversibility-aware coordination (pure, deterministic, non-mutating)."""
    queue = [dict(entry) for entry in (queue or [])]
    rev = dict(reversibility or {})
    remaining = max(0.0, float(rev.get("repair_remaining",
                                       DEFAULT_REVERSIBILITY_PARAMS["repair_ceiling"])))
    ceiling = max(1e-9, float(rev.get("repair_ceiling",
                                      DEFAULT_REVERSIBILITY_PARAMS["repair_ceiling"])))
    info_debt = max(0.0, min(1.0, float(rev.get("information_debt", 0.0))))
    mut_fix = max(0.0, min(1.0, float(rev.get("mutation_fixation", 0.0))))
    entropy = max(0.0, float(rev.get("entropy_production", 0.0)))
    executed: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    pending = queue + [{"effect": dict(effect), "retries": 0} for effect in effects]
    detail: dict[str, Any] = {"mode": mode, "n_pending": len(pending)}

    def _kind(effect: dict[str, Any]) -> str:
        return str(effect.get("intervention_type", ""))

    def _score(effect: dict[str, Any]) -> float:
        value = (max(0.0, float(effect.get("rev_clearance", 0.0)))
                 + max(0.0, float(effect.get("rev_prevention", 0.0))) * 0.8
                 + max(0.0, float(effect.get("rev_conversion_suppression", 0.0))) * 0.6
                 + max(0.0, float(effect.get("rev_irreversible_repair", 0.0))) * 0.5
                 + max(0.0, float(effect.get("rev_information_repair", 0.0))) * 0.4
                 + max(0.0, float(effect.get("rev_mutation_repair", 0.0))) * 0.4
                 + max(0.0, float(effect.get("rev_niche_repair", 0.0))) * 0.3)
        cost = (max(0.0, float(effect.get("rev_irreversible_repair", 0.0))) * 1.5
                + mut_fix * (1.0 if "reprogramming" in _kind(effect) or "stem" in _kind(effect)
                             or "telomere" in _kind(effect) else 0.0)
                + info_debt * (1.0 if "reprogramming" in _kind(effect) else 0.0)
                + entropy * 0.1)
        return value - 0.7 * cost

    for entry in pending:
        effect = dict(entry["effect"])
        kind = _kind(effect)
        needs_irr = max(0.0, float(effect.get("rev_irreversible_repair", 0.0)))
        risky_info = kind in ("epigenetic_reprogramming_pulse", "reversible_epigenetic_reset",
                              "stem_niche_restoration", "telomere_maintenance")
        risky_mut = kind in ("epigenetic_reprogramming_pulse", "stem_niche_restoration",
                              "telomere_maintenance", "regenerative_boost",
                              "irreversible_repair_pulse")
        if mode == "independent_reversibility":
            executed.append(effect)
            continue
        if mode == "preventive_priority":
            preventive = (max(0.0, float(effect.get("rev_prevention", 0.0)))
                          + max(0.0, float(effect.get("rev_conversion_suppression", 0.0))))
            if preventive > 0.0 or needs_irr <= 0.0:
                executed.append(effect)
            elif int(entry.get("retries", 0)) >= 4:
                rejected.append(effect)
            else:
                deferred.append(entry)
            continue
        if mode == "repair_ceiling_guard":
            if needs_irr > remaining + 1e-12:
                if int(entry.get("retries", 0)) >= 4:
                    rejected.append(effect)
                else:
                    deferred.append(entry)
            else:
                executed.append(effect)
            continue
        if mode == "information_guard":
            if risky_info and info_debt >= 0.4:
                if int(entry.get("retries", 0)) >= 4:
                    rejected.append(effect)
                else:
                    deferred.append(entry)
            else:
                executed.append(effect)
            continue
        if mode == "mutation_guard":
            if risky_mut and mut_fix >= 0.4:
                if int(entry.get("retries", 0)) >= 4:
                    rejected.append(effect)
                else:
                    deferred.append(entry)
            else:
                executed.append(effect)
            continue
        if mode == "entropy_budget_scheduler":
            if entropy > 0.08 and needs_irr > 0.0:
                if int(entry.get("retries", 0)) >= 4:
                    rejected.append(effect)
                else:
                    deferred.append(entry)
            else:
                executed.append(effect)
            continue
        if mode == "lookahead_reversibility":
            score = _score(effect)
            entry["reversibility_score"] = score
            if score >= 0.002 or remaining / ceiling > 0.5:
                executed.append(effect)
            elif int(entry.get("retries", 0)) >= 4:
                rejected.append(effect)
            else:
                deferred.append(entry)
            continue
        raise ValueError(f"unknown reversibility coordination mode {mode!r}")
    new_queue = []
    for entry in deferred:
        record: dict[str, Any] = {"effect": entry["effect"],
                                  "age": entry.get("age", 0.0),
                                  "retries": int(entry.get("retries", 0)) + 1}
        if "reversibility_score" in entry:
            record["reversibility_score"] = entry["reversibility_score"]
        new_queue.append(record)
    detail.update({"n_executed": len(executed), "n_deferred": len(new_queue),
                   "n_rejected": len(rejected)})
    return {"executed": executed, "deferred": [d["effect"] for d in deferred],
            "rejected": rejected, "queue": new_queue, "detail": detail}
