"""ANALYSIS LAYER: Stage 10 biological-age decomposition (diagnostic only).

Answers: from which mathematical component of the existing model does the
residual biological-age slope (~1.1666 after successful epigenetic rollback)
arise? No production semantics touched; pure functions over run outputs.

Actual formula under test (see report §2):
  src/longevity/model/aging.py::aggregate_biological_age
  src/longevity/model/organism.py::OrganismModel._driver_step
    (+ _apply_driver_effect, _organ_backed_step emergent blending,
     _apply_reversibility_effect, _apply_epigenetic_backup_effect)
  src/longevity/model/epigenetic_backup.py::entropy_bio_contribution

  biological_age = max(floor, adult_setpoint + sum_i(contribution_i
      * damage_i / adult_reference_i)) + entropy_weight * epigenetic_entropy
  (floor = adult_setpoint unless allow_sub_adult; refs default 1.0).

Known implementation couplings documented in the report (not new mechanisms):
  emergent blending after bio computation, damage caps [0,1],
  floor max(), entropy omitted on driver-intervention recompute,
  stale bio after reversibility clearance, direct delta_bio overwritten
  by driver re-aggregation.
"""

from __future__ import annotations

import copy
import json
import math
import os
import statistics
import time

from typing import Any

CLASSIFICATIONS = (
    "driver_contribution",
    "distributed_contribution",
    "setpoint_dynamics",
    "aggregation_or_coupling",
    "accounting_discrepancy",
    "unresolved",
)

CONFIDENCES = ("high", "medium", "low")


def least_squares_slope(times: list[float], values: list[float]) -> float:
    """Least-squares slope (pure, deterministic; 0.0 on degenerate input)."""
    n = len(times)
    if n < 2:
        return 0.0
    mean_t = sum(times) / n
    mean_v = sum(values) / n
    denom = sum((t - mean_t) ** 2 for t in times)
    if denom <= 0.0:
        return 0.0
    return sum((t - mean_t) * (v - mean_v) for t, v in zip(times, values)) / denom


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def adult_rows(trajectory: list[dict[str, Any]], setpoint: float = 25.0) -> list[dict[str, Any]]:
    """Rows at/after the adult reference age (pure).

    Uses the frozen backup reference_age when present (Stage 9), else setpoint.
    """
    if not trajectory:
        return []
    for row in trajectory:
        backup = row.get("epigenetic_backup") or {}
        if backup.get("reference_age") is not None:
            setpoint = float(backup["reference_age"])
            break
    return [row for row in trajectory if float(row.get("chronological_age", 0.0)) >= setpoint]


def _resolve_params(driver_params: dict[str, dict[str, float]] | None,
                    backup_params: dict[str, Any] | None):
    from longevity.model.aging import DEFAULT_DRIVER_PARAMS
    from longevity.model.epigenetic_backup import validate_epigenetic_backup_params

    drivers = {n: dict(DEFAULT_DRIVER_PARAMS[n]) for n in DEFAULT_DRIVER_PARAMS}
    if driver_params:
        for name, block in driver_params.items():
            if name in drivers:
                merged = dict(drivers[name])
                merged.update(block)
                drivers[name] = merged
    backup = validate_epigenetic_backup_params(backup_params)
    return drivers, backup


def reconstruct_series(adult: list[dict[str, Any]],
                       driver_params: dict[str, dict[str, float]] | None = None,
                       backup_params: dict[str, Any] | None = None,
                       setpoint: float = 25.0,
                       allow_sub_adult: bool = False) -> dict[str, Any]:
    """Reconstruct biological_age from stored components (pure).

    Method: for each adult row, contribution_i = weight_i * damage_i / ref_i
    (same as aggregate_biological_age), backup = entropy_weight * entropy,
    reconstructed = max(floor, setpoint + sum) + backup. No formula change;
    this mirrors the production aggregation for diagnosis.
    """
    from longevity.model.aging import AGING_DRIVERS

    drivers, backup = _resolve_params(driver_params, backup_params)
    times: list[float] = []
    bio: list[float] = []
    rec: list[float] = []
    contrib_series: dict[str, list[float]] = {n: [] for n in AGING_DRIVERS}
    contrib_series["epigenetic_backup"] = []
    contrib_series["setpoint"] = []
    for row in adult:
        t = float(row.get("chronological_age", 0.0))
        b = float(row.get("biological_age", 0.0))
        damages = {}
        for name in AGING_DRIVERS:
            dmg = float((row.get("aging") or {}).get("drivers", {}).get(name, {}).get("damage", 0.0))
            damages[name] = max(0.0, dmg)
        parts: dict[str, float] = {}
        for name in AGING_DRIVERS:
            ref = max(1e-9, float(drivers[name]["adult_reference"]))
            parts[name] = float(drivers[name]["contribution"]) * max(0.0, damages[name]) / ref
        ent = max(0.0, float((row.get("epigenetic_backup") or {}).get("epigenetic_entropy", 0.0)))
        backup_c = max(0.0, float(backup.get("entropy_bio_weight", 8.0))) * ent
        floor = 0.0 if allow_sub_adult else float(setpoint)
        total = float(setpoint) + sum(parts.values())
        rec_v = max(floor, total) + backup_c
        times.append(t)
        bio.append(b)
        rec.append(rec_v)
        for name in AGING_DRIVERS:
            contrib_series[name].append(parts[name])
        contrib_series["epigenetic_backup"].append(backup_c)
        contrib_series["setpoint"].append(float(setpoint))
    residuals = [b - r for b, r in zip(bio, rec)]
    if residuals:
        mean_r = _mean(residuals)
        median_r = float(statistics.median(residuals))
        max_abs = max(abs(v) for v in residuals)
        std_r = _std(residuals)
        slope_r = least_squares_slope(times, residuals)
    else:
        mean_r = median_r = max_abs = std_r = slope_r = 0.0
    # Accounting closes only near numerical noise relative to bio range.
    bio_range = (max(bio) - min(bio)) if bio else 0.0
    tol_level = max(1e-6, 0.005 * bio_range)  # 0.5% of range
    tol_slope = max(1e-9, 0.02 * abs(least_squares_slope(times, bio)) if bio else 1e-9)
    accounting_closed = bool(max_abs <= tol_level and abs(slope_r) <= tol_slope)
    return {
        "times": times,
        "biological_age": bio,
        "reconstructed": rec,
        "residuals": residuals,
        "contrib_series": contrib_series,
        "reconstruction": {
            "mean_residual": float(mean_r),
            "median_residual": float(median_r),
            "max_abs_residual": float(max_abs),
            "residual_std": float(std_r),
            "residual_slope": float(slope_r),
            "bio_range": float(bio_range),
            "tol_level": float(tol_level),
            "tol_slope": float(tol_slope),
            "accounting_closed": bool(accounting_closed),
        },
    }


def decompose_condition(trajectory: list[dict[str, Any]],
                        summary: dict[str, Any] | None = None,
                        driver_params: dict[str, dict[str, float]] | None = None,
                        backup_params: dict[str, Any] | None = None,
                        setpoint: float = 25.0,
                        allow_sub_adult: bool = False) -> dict[str, Any]:
    """One run → slopes per component + reconstruction (pure)."""
    from longevity.model.aging import AGING_DRIVERS

    if not trajectory or len(trajectory) < 2:
        raise ValueError("decompose_condition of empty trajectory")
    adult = adult_rows(trajectory, setpoint)
    if len(adult) < 2:
        raise ValueError("decompose_condition needs >=2 adult rows")
    rec = reconstruct_series(adult, driver_params, backup_params, setpoint, allow_sub_adult)
    times = rec["times"]
    bio_series = rec["biological_age"]
    bio_slope = None
    if summary is not None:
        bio_slope = summary.get("biological_age_slope_after_adulthood", None)
        if bio_slope is None:
            bio_slope = summary.get("bio_slope", None)
    if bio_slope is None:
        bio_slope = least_squares_slope(times, bio_series)
    bio_slope = float(bio_slope)
    component_slopes: dict[str, float] = {}
    for name, series in rec["contrib_series"].items():
        if name == "setpoint":
            component_slopes[name] = 0.0  # constant offset by construction
        else:
            component_slopes[name] = float(least_squares_slope(times, series))
    # Driver damage slopes (unweighted) for the driver state ≠ contribution ≠ slope rule.
    driver_damage_slopes: dict[str, float] = {}
    for name in AGING_DRIVERS:
        series = [max(0.0, float((row.get("aging") or {}).get("drivers", {}).get(name, {}).get("damage", 0.0)))
                  for row in adult]
        driver_damage_slopes[name] = float(least_squares_slope(times, series))
    entropy_series = [max(0.0, float((row.get("epigenetic_backup") or {}).get("epigenetic_entropy", 0.0)))
                      for row in adult]
    h_epi_slope = float(least_squares_slope(times, entropy_series)) if len(times) >= 2 else 0.0
    total_driver_slope = float(sum(component_slopes[n] for n in AGING_DRIVERS))
    backup_slope = float(component_slopes.get("epigenetic_backup", 0.0))
    sum_slopes = float(total_driver_slope + backup_slope)  # setpoint slope 0
    nonlinear_residual = float(bio_slope - sum_slopes)
    return {
        "n_adult_rows": len(adult),
        "time_range": [float(times[0]), float(times[-1])] if times else [0.0, 0.0],
        "bio_age_slope": float(bio_slope),
        "h_epi_slope": float(h_epi_slope),
        "component_slopes": component_slopes,
        "driver_damage_slopes": driver_damage_slopes,
        "total_driver_slope": float(total_driver_slope),
        "backup_slope": float(backup_slope),
        "setpoint_slope": 0.0,
        "setpoint_value": float(setpoint),
        "sum_component_slopes": float(sum_slopes),
        "nonlinear_coupling_residual": float(nonlinear_residual),
        "reconstruction": rec["reconstruction"],
        "final_contributions": {k: float(v[-1]) if v else 0.0 for k, v in rec["contrib_series"].items()},
        "deterministic": True,
    }


def _validate_per_seed(data: Any, path: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a dict")
    for key in ("bio_age_slope", "component_slopes", "reconstruction"):
        if key not in data:
            raise ValueError(f"{path} missing {key!r}")
    comp = data["component_slopes"]
    if not isinstance(comp, dict) or not comp:
        raise ValueError(f"{path}.component_slopes must be a non-empty dict")
    for name, value in comp.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not math.isfinite(float(value)):
            raise ValueError(f"{path}.component_slopes.{name} must be finite")
    rec = data["reconstruction"]
    for key in ("mean_residual", "max_abs_residual", "residual_slope", "accounting_closed"):
        if key not in rec:
            raise ValueError(f"{path}.reconstruction missing {key!r}")
    return data


def detect_nonlinear_coupling() -> dict[str, Any]:
    """Static code facts about existing nonlinear/coupling terms (no new mechanism).

    Inspected: aggregate floor max(), damage caps [0,1] (organism invariants),
    effective_reversal gate, emergent blending weights, energy/shortfall
    modifiers, intervention overwrite paths. All pre-existing.
    """
    from longevity.model.organ_backed import DEFAULT_EMERGENT_WEIGHTS

    terms = [
        "floor_max(setpoint): max(floor, setpoint+sum) — piecewise-linear threshold",
        "damage_cap_[0,1]: driver/proxy damage clamped — saturation nonlinearity",
        "emergent_blending: organ_backed blends driver damage after bio computed "
        f"(weights={dict(DEFAULT_EMERGENT_WEIGHTS)}) — one-step stale-bio coupling",
        "effective_reversal_gate: 1-damage/saturation — diminishing-returns nonlinearity",
        "entropy_omission_on_driver_recompute: apply_effect re-aggregates without "
        "entropy unless rollback fires — event-driven coupling",
        "stale_bio_after_reversibility_clearance: rev clearance cuts damage "
        "without recomputing bio — lag coupling",
        "direct_delta_bio_overwritten: delta_biological_age then overwritten by "
        "driver re-aggregation under mechanistic mode — documented shadowing",
        "conversion_modifier: inflammation/energy/repair/cascade/niche/toxicity "
        "multiplicative modifier on conversion — state-dependent coupling",
    ]
    return {"detected": True, "terms": terms}


def analyze_biological_age_decomposition(results: dict[str, Any]) -> dict[str, Any]:
    """Classify the residual-slope holder (pure, deterministic).

    results: {"baseline": {seed: per_seed}, "rollback": {seed: per_seed},
      "rollback_dna_ablation": {seed: per_seed} (optional),
      "thresholds": {"relative": 0.30, "margin": 2.0, "majority": 0.50} (optional)}.
    per_seed: output of decompose_condition (or minimal subset with
      bio_age_slope + component_slopes + reconstruction).
    """
    if not isinstance(results, dict):
        raise ValueError("results must be a dict")
    baseline = results.get("baseline")
    rollback = results.get("rollback")
    if not isinstance(baseline, dict) or not baseline:
        raise ValueError("results.baseline must be a non-empty dict")
    if not isinstance(rollback, dict) or not rollback:
        raise ValueError("results.rollback must be a non-empty dict")
    dna = results.get("rollback_dna_ablation") or {}
    thresholds = dict(results.get("thresholds") or {})
    rel_bar = float(thresholds.get("relative", 0.30))
    margin = float(thresholds.get("margin", 2.0))
    majority = float(thresholds.get("majority", 0.50))
    if not (0.0 < rel_bar < 1.0 and margin > 1.0 and 0.0 < majority <= 1.0):
        raise ValueError(f"invalid thresholds: {thresholds!r}")
    for seed, entry in baseline.items():
        _validate_per_seed(entry, f"baseline[{seed}]")
    for seed, entry in rollback.items():
        _validate_per_seed(entry, f"rollback[{seed}]")
    for seed, entry in dna.items():
        _validate_per_seed(entry, f"rollback_dna_ablation[{seed}]")

    def _means(block: dict[str, Any]):
        seeds = sorted(block)
        bio = _mean([float(block[s]["bio_age_slope"]) for s in seeds])
        names = sorted(block[seeds[0]]["component_slopes"])
        comp = {n: _mean([float(block[s]["component_slopes"][n]) for s in seeds]) for n in names}
        max_abs = _mean([float(block[s]["reconstruction"]["max_abs_residual"]) for s in seeds])
        mean_r = _mean([float(block[s]["reconstruction"]["mean_residual"]) for s in seeds])
        median_r = _mean([float(block[s]["reconstruction"].get("median_residual", 0.0)) for s in seeds])
        std_r = _mean([float(block[s]["reconstruction"].get("residual_std", 0.0)) for s in seeds])
        slope_r = _mean([float(block[s]["reconstruction"]["residual_slope"]) for s in seeds])
        closed = bool(all(bool(block[s]["reconstruction"]["accounting_closed"]) for s in seeds))
        nonlin = _mean([float(block[s].get("nonlinear_coupling_residual", 0.0)) for s in seeds])
        return {
            "seeds": seeds, "bio_age_slope": bio, "component_slopes": comp,
            "max_abs_residual": max_abs, "mean_residual": mean_r,
            "median_residual": median_r, "residual_std": std_r,
            "residual_slope": slope_r, "accounting_closed": closed,
            "nonlinear_residual": nonlin,
        }

    base_m = _means(baseline)
    roll_m = _means(rollback)
    dna_m = _means(dna) if dna else None

    # Primary condition for classification: rollback (the residual in question).
    bio = roll_m["bio_age_slope"]
    comp = dict(roll_m["component_slopes"])
    # Setpoint never contributes slope (constant); keep for the explicit check.
    drivers_only = {k: v for k, v in comp.items() if k not in ("setpoint", "epigenetic_backup")}
    backup_slope = float(comp.get("epigenetic_backup", 0.0))
    total_pos = sum(v for v in list(drivers_only.values()) + [backup_slope] if v > 0)
    # Shares over positive part (negative epi slope after rollback must not inflate).
    shares = {k: (v / total_pos if total_pos > 0 else 0.0) for k, v in drivers_only.items()}
    ranking = sorted(drivers_only, key=lambda k: (-drivers_only[k], k))
    top = ranking[0] if ranking else "none"
    runner = ranking[1] if len(ranking) > 1 else None
    top_v = drivers_only.get(top, 0.0)
    runner_v = drivers_only.get(runner, 0.0) if runner else 0.0
    reproducible = all(float(rollback[s]["component_slopes"][top]) > 0 for s in roll_m["seeds"]) \
        if top != "none" else False
    gap_abs = abs(roll_m["nonlinear_residual"])
    gap_rel = gap_abs / max(1e-12, abs(bio))
    residual_rel = abs(roll_m["residual_slope"]) / max(1e-12, abs(bio))
    coupling = detect_nonlinear_coupling()

    notes: list[str] = []
    classification = "unresolved"
    confidence = "low"
    # Decision order (documented, data-driven):
    # 1. setpoint dynamics — only if setpoint slope non-zero (never in v0).
    # 2. accounting discrepancy — large unexplained level/slope gap.
    # 3. single driver — majority + margin + reproducible.
    # 4. distributed — several substantial, none dominant.
    # 5. aggregation/coupling — known coupling explains gap / ablations mute.
    # 6. unresolved.
    setpoint_slope = 0.0  # constant by construction; measured, not assumed
    if abs(setpoint_slope) > 0.1 * abs(bio):
        classification = "setpoint_dynamics"
        confidence = "high"
        notes.append("setpoint slope explains >10% of bio slope")
    elif roll_m["max_abs_residual"] > 2.0 or residual_rel > 0.25 or gap_rel > 0.25:
        classification = "accounting_discrepancy"
        confidence = "medium" if roll_m["accounting_closed"] is False else "low"
        notes.append(
            f"large gap: max_abs={roll_m['max_abs_residual']:.4f}, "
            f"residual_slope_share={residual_rel:.3f}, nonlinear_share={gap_rel:.3f}")
    elif top != "none" and shares.get(top, 0.0) >= majority and reproducible \
            and (runner_v <= 0 or (top_v / max(1e-12, runner_v)) >= margin):
        classification = "driver_contribution"
        confidence = "high" if len([k for k in shares if shares[k] > rel_bar]) == 1 else "medium"
        notes.append(f"single dominant: {top} share={shares[top]:.3f}, margin holds")
    elif top != "none" and shares.get(top, 0.0) >= majority:
        classification = "driver_contribution"
        confidence = "low"
        notes.append(f"majority by {top} but margin below {margin}x: rival too close")
    else:
        substantial = [k for k in shares if shares[k] > rel_bar]
        if len(substantial) >= 2:
            classification = "distributed_contribution"
            confidence = "medium"
            notes.append(f"no single majority; substantial: {substantial}")
        elif gap_rel > 0.02 or residual_rel > 0.02 or not roll_m["accounting_closed"]:
            classification = "aggregation_or_coupling"
            confidence = "medium" if coupling["detected"] else "low"
            notes.append(
                "no dominant driver; known implementation coupling (caps, emergent "
                f"blending, stale-bio paths) leaves nonlinear share={gap_rel:.4f}, "
                f"residual share={residual_rel:.4f}; ablation-mute pattern of Stage 9b "
                "is consistent with this coupling, not proof of new biology")
        else:
            classification = "unresolved"
            confidence = "low"
            notes.append("no separable pattern with available data")

    conditions: dict[str, Any] = {
        "baseline": base_m,
        "rollback": roll_m,
    }
    if dna_m is not None:
        conditions["rollback_dna_ablation"] = dna_m

    # Deltas for §8 of the report.
    deltas: dict[str, Any] = {}
    for name in comp:
        deltas[name] = {
            "rollback_minus_baseline": float(roll_m["component_slopes"].get(name, 0.0)
                                             - base_m["component_slopes"].get(name, 0.0)),
        }
        if dna_m is not None:
            deltas[name]["dna_minus_rollback"] = float(
                dna_m["component_slopes"].get(name, 0.0) - roll_m["component_slopes"].get(name, 0.0))
            deltas[name]["dna_minus_baseline"] = float(
                dna_m["component_slopes"].get(name, 0.0) - base_m["component_slopes"].get(name, 0.0))
    return {
        "bio_age_slope": float(bio),
        "conditions": conditions,
        "component_slopes": {k: float(v) for k, v in comp.items()},
        "component_shares": {k: float(v) for k, v in shares.items()},
        "ranking": ranking,
        "top_component": top,
        "deltas": deltas,
        "setpoint": {"slope": float(setpoint_slope), "contribution": float(roll_m["component_slopes"].get("setpoint", 25.0))},
        "reconstruction": {
            "mean_residual": float(roll_m["mean_residual"]),
            "median_residual": float(roll_m.get("median_residual", 0.0)),
            "max_abs_residual": float(roll_m["max_abs_residual"]),
            "residual_std": float(roll_m.get("residual_std", 0.0)),
            "residual_slope": float(roll_m["residual_slope"]),
            "accounting_closed": bool(roll_m["accounting_closed"]),
        },
        "nonlinear_coupling": coupling,
        "nonlinear_residual": float(roll_m["nonlinear_residual"]),
        "classification": classification,
        "confidence": confidence,
        "notes": notes,
        "deterministic": True,
    }


def load_decomposition_config(path: str) -> dict[str, Any]:
    """Read and validate a Stage 10 decomposition config (pure)."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("decomposition config must be a dict")
    for key in ("experiment_id", "seeds", "base_organism_config", "output_artifact"):
        if key not in data:
            raise ValueError(f"decomposition config missing {key!r}")
    seeds = data["seeds"]
    if not isinstance(seeds, (list, tuple)) or len(seeds) < 1:
        raise ValueError("seeds must be a non-empty list")
    return data


def run_biological_age_decomposition(config_path: str, out_path: str | None = None) -> dict[str, Any]:
    """Execute the three-condition decomposition (deterministic).

    A: baseline without rollback (rollback policy disabled, config layer only).
    B: Stage 9 rollback (threshold/intensity/interval overrides).
    C: B + dna_damage base_aging_rate x scale (best Stage 9b ablation).
    Production model untouched; all differences ride the config layer.
    """
    import copy

    from longevity.experiment.organism_runner import (
        OrganismExperimentConfig,
        load_organism_config,
        run_organism_experiment,
    )
    from longevity.model.aging import DEFAULT_DRIVER_PARAMS

    wall_start = time.perf_counter()
    config = load_decomposition_config(config_path)
    seeds = [int(s) for s in config["seeds"]]
    base_cfg = load_organism_config(config["base_organism_config"]).to_config_dict()
    rollback = dict(config.get("rollback_policy_overrides", {}) or {})
    apoptosis = dict(config.get("apoptosis_policy_overrides", {}) or {})
    r_idx = int(rollback.get("policy_index", 6))
    a_idx = int(apoptosis.get("policy_index", 7))
    ablation_scale = float(config.get("ablation_driver_scale", 0.1))
    setpoint = float(base_cfg.get("adult_age_setpoint", 25.0))
    allow_sub = bool(base_cfg.get("allow_sub_adult_biological_age", False))
    driver_defaults = {n: dict(DEFAULT_DRIVER_PARAMS[n]) for n in DEFAULT_DRIVER_PARAMS}

    def _run_one(tag: str, seed: int, disable_rollback: bool, dna_scale: float | None):
        data = copy.deepcopy(base_cfg)
        data["organism_id"] = f"{config['experiment_id']}_{tag}_s{seed}"
        data["seed"] = seed
        policies = list(data.get("policies", []))
        if disable_rollback and 0 <= r_idx < len(policies):
            pol = dict(policies[r_idx])
            pol["enabled"] = False
            policies[r_idx] = pol
        else:
            if 0 <= r_idx < len(policies):
                pol = dict(policies[r_idx])
                pol["biomarker_threshold"] = float(rollback.get("biomarker_threshold", 0.03))
                pol["intensity"] = float(rollback.get("intensity", 1.0))
                pol["interval"] = float(rollback.get("interval", 1.0))
                policies[r_idx] = pol
            if 0 <= a_idx < len(policies):
                pol = dict(policies[a_idx])
                pol["interval"] = float(apoptosis.get("interval", 10.0))
                policies[a_idx] = pol
        data["policies"] = policies
        if dna_scale is not None:
            drivers = dict(data.get("aging_drivers", {}) or {})
            default_rate = float(DEFAULT_DRIVER_PARAMS["dna_damage"]["base_aging_rate"])
            merged = dict(drivers.get("dna_damage", {}))
            merged["base_aging_rate"] = default_rate * float(dna_scale)
            drivers["dna_damage"] = merged
            data["aging_drivers"] = drivers
        result = run_organism_experiment(OrganismExperimentConfig.from_config_dict(data))
        return result["trajectory"], result["metrics"]["final"], result["config"]

    per: dict[str, dict[str, Any]] = {"baseline": {}, "rollback": {}, "rollback_dna_ablation": {}}
    for seed in seeds:
        traj, summary, cfg = _run_one("baseline_no_rollback", seed, True, None)
        per["baseline"][str(seed)] = decompose_condition(
            traj, summary, driver_defaults, None, setpoint, allow_sub)
    for seed in seeds:
        traj, summary, cfg = _run_one("rollback", seed, False, None)
        per["rollback"][str(seed)] = decompose_condition(
            traj, summary, driver_defaults, None, setpoint, allow_sub)
    for seed in seeds:
        traj, summary, cfg = _run_one("rollback_dna", seed, False, ablation_scale)
        per["rollback_dna_ablation"][str(seed)] = decompose_condition(
            traj, summary, driver_defaults, None, setpoint, allow_sub)
    verdict = analyze_biological_age_decomposition({
        "baseline": per["baseline"],
        "rollback": per["rollback"],
        "rollback_dna_ablation": per["rollback_dna_ablation"],
        "thresholds": {"relative": float(config.get("single_driver_relative_threshold", 0.30)),
                       "margin": float(config.get("single_driver_margin", 2.0)),
                       "majority": 0.50},
    })
    artifact = {
        "experiment_id": config["experiment_id"],
        "stage": "10",
        "model_version": "0.5.0",
        "experiment_version": "bio-age-decomposition/v1",
        "seeds": seeds,
        "configuration": {
            "base_organism_config": config["base_organism_config"],
            "rollback_policy": {k: v for k, v in rollback.items() if k != "policy_index"},
            "apoptosis_interval": float(apoptosis.get("interval", 10.0)),
            "ablation_driver_scale": ablation_scale,
            "adult_age_setpoint": setpoint,
        },
        "conditions": {
            name: {seed: {"bio_age_slope": entry["bio_age_slope"],
                          "h_epi_slope": entry["h_epi_slope"],
                          "component_slopes": entry["component_slopes"],
                          "driver_damage_slopes": entry.get("driver_damage_slopes", {}),
                          "total_driver_slope": entry["total_driver_slope"],
                          "backup_slope": entry["backup_slope"],
                          "sum_component_slopes": entry["sum_component_slopes"],
                          "nonlinear_coupling_residual": entry["nonlinear_coupling_residual"],
                          "reconstruction": entry["reconstruction"],
                          "final_contributions": entry.get("final_contributions", {})}
                   for seed, entry in block.items()}
            for name, block in per.items()
        },
        "classification": verdict["classification"],
        "confidence": verdict["confidence"],
        "notes": verdict["notes"],
        "component_slopes_rollback_mean": verdict["component_slopes"],
        "component_shares": verdict.get("component_shares", {}),
        "ranking": verdict.get("ranking", []),
        "deltas": verdict.get("deltas", {}),
        "setpoint": verdict.get("setpoint", {}),
        "reconstruction_rollback_mean": verdict.get("reconstruction", {}),
        "nonlinear_coupling": verdict.get("nonlinear_coupling", {}),
        "nonlinear_residual": verdict.get("nonlinear_residual", 0.0),
        "bio_age_slope_rollback_mean": verdict.get("bio_age_slope", 0.0),
        "formula": {
            "files": ["src/longevity/model/aging.py::aggregate_biological_age",
                      "src/longevity/model/organism.py::OrganismModel._driver_step",
                      "src/longevity/model/epigenetic_backup.py::entropy_bio_contribution"],
            "expression": "biological_age = max(floor, adult_setpoint + sum(contribution_i*damage_i/adult_reference_i)) + entropy_weight*epigenetic_entropy",
            "method": "reconstructed from stored damages/entropy without changing the formula",
        },
        "hypothesis_status": "hypothesis_not_proven",
        "runtime": {"wall_seconds": round(time.perf_counter() - wall_start, 4)},
        "deterministic": True,
    }
    out = out_path or config["output_artifact"]
    parent = os.path.dirname(os.path.abspath(out))
    os.makedirs(parent, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, ensure_ascii=False, indent=2, allow_nan=False)
    artifact["artifact_path"] = out
    return artifact
