"""ANALYSIS LAYER: Stage 9b constraint attribution (rollback residual slope).

Answers one question: what holds the biological-age slope up after a
successful epigenetic rollback? Three outcomes, no presumptions:

- ``single_driver_migration`` — one remaining driver dominates;
- ``distributed_residual`` — several drivers share the residual slope;
- ``aggregation_or_unresolved_residual`` — no single driver explains it
  (aggregation / setpoint / interactions / resources / unidentified).

Everything here is a sensitivity attribution, never a causal proof.
Thresholds (30%, 2x margin, 50% majority) are OPERATIONAL choices of this
experiment, not biological laws. Pure functions over run outputs; no
production semantics touched (ablations ride the config layer only).
"""

from __future__ import annotations

import copy
import json
import math
import os
import time

from typing import Any

CLASSIFICATIONS = (
    "single_driver_migration",
    "distributed_residual",
    "aggregation_or_unresolved_residual",
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
    """Rows at/after the adult reference age (pure)."""
    if not trajectory:
        return []
    for row in trajectory:
        backup = row.get("epigenetic_backup") or {}
        if backup.get("reference_age") is not None:
            setpoint = float(backup["reference_age"])
            break
    return [row for row in trajectory if float(row.get("chronological_age", 0.0)) >= setpoint]


def per_seed_attribution(trajectory: list[dict[str, Any]],
                         summary: dict[str, Any]) -> dict[str, Any]:
    """One run condensed to attribution inputs (pure, no mutation).

    Slopes come from the trajectory time series (adult rows); lifespan,
    healthspan and failure come from the runner summary.
    """
    from longevity.model.aging import AGING_DRIVERS, DEFAULT_DRIVER_PARAMS

    if not trajectory or len(trajectory) < 2:
        raise ValueError("per_seed_attribution of empty trajectory")
    adult = adult_rows(trajectory)
    times = [float(row["chronological_age"]) for row in adult]
    driver_slopes: dict[str, float] = {}
    driver_finals: dict[str, float] = {}
    contributions: dict[str, float] = {}
    for name in AGING_DRIVERS:
        series = [max(0.0, float((row.get("aging") or {}).get("drivers", {})
                                 .get(name, {}).get("damage", 0.0))) for row in adult]
        driver_slopes[name] = least_squares_slope(times, series) if len(times) >= 2 else 0.0
        final_damage = max(0.0, float((trajectory[-1].get("aging") or {}).get("drivers", {})
                                      .get(name, {}).get("damage", 0.0)))
        driver_finals[name] = final_damage
        weight = float(DEFAULT_DRIVER_PARAMS[name]["contribution"]) \
            / max(1e-9, float(DEFAULT_DRIVER_PARAMS[name]["adult_reference"]))
        contributions[name] = weight * final_damage
    entropy_series = [max(0.0, float((row.get("epigenetic_backup") or {})
                                     .get("epigenetic_entropy", 0.0))) for row in adult]
    backup_final = trajectory[-1].get("epigenetic_backup") or {}
    resources = ((trajectory[-1].get("organ_backed") or {}).get("resources") or {}).get("budgets", {})
    bio_slope = summary.get("biological_age_slope_after_adulthood", None)
    if bio_slope is None:
        bio_slope = least_squares_slope(times, [float(row.get("biological_age", 0.0))
                                                 for row in adult])
    return {
        "bio_slope": float(bio_slope),
        "h_epi_slope": least_squares_slope(times, entropy_series) if len(times) >= 2 else 0.0,
        "lifespan": float(summary.get("lifespan", 0.0)),
        "healthspan": float(summary.get("healthspan", 0.0)),
        "driver_slopes": driver_slopes,
        "driver_finals": driver_finals,
        "contributions": contributions,
        "epigenetic_entropy_final": max(0.0, float(backup_final.get("epigenetic_entropy", 0.0))),
        "rollback_events": int(backup_final.get("rollback_events", 0)),
        "apoptosis_events": int(backup_final.get("apoptosis_events", 0)),
        "failure": str(summary.get("primary_cause_of_death", "none")),
        "resources": {k: float(v) for k, v in dict(resources).items()},
    }


def _validate_per_seed(data: Any, path: str) -> dict[str, Any]:
    from longevity.model.aging import AGING_DRIVERS

    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a dict")
    for key in ("bio_slope", "h_epi_slope", "lifespan", "healthspan"):
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not math.isfinite(float(value)):
            raise ValueError(f"{path}.{key} must be finite, got {value!r}")
    for key in ("driver_slopes", "driver_finals", "contributions"):
        block = data.get(key)
        if not isinstance(block, dict):
            raise ValueError(f"{path}.{key} must be a dict")
        for name in AGING_DRIVERS:
            value = block.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(float(value)):
                raise ValueError(f"{path}.{key}.{name} must be finite, got {value!r}")
    return data


def analyze_constraint_migration(results: dict[str, Any]) -> dict[str, Any]:
    """Classify the residual slope holder (pure, deterministic).

    ``results``: {"baseline": {seed: per_seed}, "ablations": {driver: {seed: per_seed}},
    "interaction": {...} (optional), "thresholds": {"relative": 0.30, "margin": 2.0,
    "majority": 0.50} (optional)}.

    Never invents biology: with no decisive pattern the verdict is
    ``aggregation_or_unresolved_residual``.
    """
    from longevity.model.aging import AGING_DRIVERS

    if not isinstance(results, dict):
        raise ValueError("results must be a dict")
    baseline = results.get("baseline")
    ablations = results.get("ablations")
    if not isinstance(baseline, dict) or not baseline:
        raise ValueError("results.baseline must be a non-empty dict")
    if not isinstance(ablations, dict) or not ablations:
        raise ValueError("results.ablations must be a non-empty dict")
    thresholds = dict(results.get("thresholds") or {})
    rel_bar = float(thresholds.get("relative", 0.30))
    margin = float(thresholds.get("margin", 2.0))
    majority = float(thresholds.get("majority", 0.50))
    if not (0.0 < rel_bar < 1.0 and margin > 1.0 and 0.0 < majority <= 1.0):
        raise ValueError(f"invalid thresholds: {thresholds!r}")
    for seed, entry in baseline.items():
        _validate_per_seed(entry, f"baseline[{seed}]")
    for driver, per_seed in ablations.items():
        if driver not in AGING_DRIVERS:
            raise ValueError(f"unknown ablation driver {driver!r}")
        if not isinstance(per_seed, dict) or not per_seed:
            raise ValueError(f"ablations[{driver}] must be a non-empty dict")
        for seed, entry in per_seed.items():
            _validate_per_seed(entry, f"ablations[{driver}][{seed}]")
    base_slopes = {str(s): float(e["bio_slope"]) for s, e in baseline.items()}
    base_mean = _mean(list(base_slopes.values()))
    base_failures = {str(e["failure"]) for e in baseline.values()}
    ablation_results: dict[str, Any] = {}
    for driver in sorted(ablations):
        per_seed = ablations[driver]
        abl_slopes = {str(s): float(e["bio_slope"]) for s, e in per_seed.items()}
        abl_mean = _mean(list(abl_slopes.values()))
        per_seed_delta = {s: base_slopes[s] - abl_slopes[s] for s in abl_slopes if s in base_slopes}
        if set(per_seed_delta) != set(base_slopes):
            raise ValueError(f"ablations[{driver}] seeds {sorted(per_seed_delta)} "
                             f"do not match baseline seeds {sorted(base_slopes)}")
        deltas = list(per_seed_delta.values())
        delta_mean = _mean(deltas)
        relative = delta_mean / base_mean if base_mean > 0 else 0.0
        life = _mean([float(e["lifespan"]) - float(baseline[s]["lifespan"])
                      for s, e in per_seed.items()])
        health = _mean([float(e["healthspan"]) - float(baseline[s]["healthspan"])
                        for s, e in per_seed.items()])
        failures = {str(e["failure"]) for e in per_seed.values()}
        confounded = failures != base_failures and life < -5.0
        ablation_results[driver] = {
            "bio_slope_mean": abl_mean,
            "bio_slope_by_seed": abl_slopes,
            "slope_improvement_mean": delta_mean,
            "slope_improvement_by_seed": per_seed_delta,
            "relative_improvement_mean": relative,
            "slope_improvement_std": _std(deltas),
            "reproducible": bool(all(d > 0.0 for d in deltas)),
            "lifespan_delta": life,
            "healthspan_delta": health,
            "failure_causes": sorted(failures),
            "confounded": bool(confounded),
        }
    ranking = sorted(ablation_results,
                     key=lambda d: (-ablation_results[d]["slope_improvement_mean"], d))
    substantial = [d for d in ranking
                   if ablation_results[d]["reproducible"]
                   and ablation_results[d]["relative_improvement_mean"] > rel_bar
                   and not ablation_results[d]["confounded"]]
    candidate: str | None = None
    notes: list[str] = []
    if substantial:
        top = substantial[0]
        runner_up = ranking[1] if len(ranking) > 1 else None
        runner_effect = ablation_results[runner_up]["slope_improvement_mean"] \
            if runner_up else 0.0
        top_effect = ablation_results[top]["slope_improvement_mean"]
        has_margin = runner_effect <= 0.0 or (top_effect / max(1e-12, runner_effect)) >= margin
        removes_majority = ablation_results[top]["relative_improvement_mean"] >= majority
        if len(substantial) == 1 and has_margin:
            classification = "single_driver_migration"
            candidate = top
            confidence = "high"
        elif removes_majority and has_margin:
            classification = "single_driver_migration"
            candidate = top
            confidence = "medium"
            notes.append("majority removed but several drivers substantial: margin holds, "
                         "distributed component not excluded")
        elif len(substantial) == 1 and not has_margin:
            classification = "single_driver_migration"
            candidate = top
            confidence = "low"
            notes.append("margin below 2x: nearest rival too close for a clean single-driver claim")
        elif len(substantial) >= 2 and ablation_results[top]["relative_improvement_mean"] < majority:
            classification = "distributed_residual"
            confidence = "medium"
            notes.append("no single ablation removes the majority of the residual slope")
        else:
            classification = "distributed_residual"
            confidence = "low"
            notes.append("mixed pattern: several substantial drivers, majority removed by top; "
                         "single vs distributed not separable")
    else:
        classification = "aggregation_or_unresolved_residual"
        candidate = None
        confidence = "low"
        notes.append("no driver ablation reproducibly removes a substantial slope share; "
                     "see diagnostic decomposition (contributions / setpoint / resources / failures)")
    decomposition = _diagnostic_decomposition(baseline) if classification == \
        "aggregation_or_unresolved_residual" else {}
    interaction = results.get("interaction")
    interaction_analysis: dict[str, Any] = {}
    if interaction is not None:
        interaction_analysis = analyze_interaction(interaction, base_mean)
    return {
        "classification": classification,
        "baseline": {
            "bio_slope_mean": base_mean,
            "bio_slope_by_seed": base_slopes,
            "h_epi_slope_mean": _mean([float(e["h_epi_slope"]) for e in baseline.values()]),
            "driver_slopes": {d: _mean([float(e["driver_slopes"][d]) for e in baseline.values()])
                              for d in sorted(baseline[next(iter(baseline))]["driver_slopes"])},
        },
        "ablation_results": ablation_results,
        "ranking": ranking,
        "candidate_binding_driver": candidate,
        "interaction_analysis": interaction_analysis,
        "confidence": confidence,
        "notes": notes,
        "diagnostic_decomposition": decomposition,
        "deterministic": True,
    }


def _diagnostic_decomposition(baseline: dict[str, Any]) -> dict[str, Any]:
    """Decompose the unexplained slope without touching aggregation (pure)."""
    from longevity.model.aging import DEFAULT_DRIVER_PARAMS

    seeds = sorted(baseline)
    contrib_mean: dict[str, float] = {}
    names = sorted(baseline[seeds[0]]["contributions"])
    for name in names:
        contrib_mean[name] = _mean([float(baseline[s]["contributions"][name]) for s in seeds])
    total = sum(contrib_mean.values())
    shares = {n: (v / total if total > 0 else 0.0) for n, v in contrib_mean.items()}
    ref = float(DEFAULT_DRIVER_PARAMS[names[0]]["adult_reference"]) if names else 1.0
    return {
        "contribution_means": contrib_mean,
        "contribution_shares": shares,
        "largest_share_driver": max(shares, key=lambda n: (shares[n], n)) if shares else "none",
        "setpoint_note": "biological_age = adult_setpoint + sum(contribution_i * damage_i / "
                         "adult_reference_i) + entropy_term; setpoint is a constant offset, "
                         "not a slope source; slope comes from damage/entropy trends",
        "resource_note": "per-seed resource budgets and failure causes are stored in "
                         "ablation_results; a cause shift with lifespan loss marks confounded runs",
        "aggregation_formula_unchanged": True,
    }


def analyze_interaction(interaction: dict[str, Any], base_mean: float) -> dict[str, Any]:
    """Top-2 A/B/A+B additivity check (pure; model interaction, not biosynergy)."""
    if not isinstance(interaction, dict):
        raise ValueError("interaction must be a dict")
    for key in ("A", "B", "conditions"):
        if key not in interaction:
            raise ValueError(f"interaction missing {key!r}")
    conditions = interaction["conditions"]
    effects: dict[str, float] = {}
    for cond in ("A", "B", "AB"):
        per_seed = conditions.get(cond)
        if not isinstance(per_seed, dict) or not per_seed:
            raise ValueError(f"interaction.conditions[{cond}] must be a non-empty dict")
        for seed, entry in per_seed.items():
            _validate_per_seed(entry, f"interaction.conditions[{cond}][{seed}]")
        effects[cond] = base_mean - _mean([float(e["bio_slope"]) for e in per_seed.values()])
    additive = effects["A"] + effects["B"]
    gap = effects["AB"] - additive
    if abs(additive) < 1e-12:
        label = "no_effect_to_compare"
    elif abs(gap) <= 0.25 * abs(additive):
        label = "approximately_additive"
    elif gap > 0:
        label = "superadditive_model_interaction"
    else:
        label = "subadditive_model_interaction"
    return {"A": interaction["A"], "B": interaction["B"], "effects": effects,
            "additive_expectation": additive, "gap": gap, "label": label,
            "note": "non-additivity is a model interaction, not proof of biological synergy"}


def load_attribution_config(path: str) -> dict[str, Any]:
    """Read and validate a Stage 9b attribution config (pure)."""
    from longevity.model.aging import AGING_DRIVERS

    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("attribution config must be a dict")
    for key in ("experiment_id", "seeds", "base_organism_config", "drivers",
                "ablation_driver_scale", "output_artifact"):
        if key not in data:
            raise ValueError(f"attribution config missing {key!r}")
    seeds = data["seeds"]
    if not isinstance(seeds, (list, tuple)) or len(seeds) < 1:
        raise ValueError("seeds must be a non-empty list")
    drivers = data["drivers"]
    if sorted(drivers) != sorted(AGING_DRIVERS):
        raise ValueError(f"drivers must cover all 8 aging drivers, got {drivers!r}")
    scale = data["ablation_driver_scale"]
    if isinstance(scale, bool) or not isinstance(scale, (int, float)) \
            or not math.isfinite(float(scale)) or not 0.0 < float(scale) < 1.0:
        raise ValueError(f"ablation_driver_scale must be in (0, 1), got {scale!r}")
    for key in ("single_driver_relative_threshold", "single_driver_margin"):
        value = data.get(key, 0.3 if "relative" in key else 2.0)
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not math.isfinite(float(value)) or float(value) <= 0.0:
            raise ValueError(f"{key} must be positive, got {value!r}")
    return data


def run_attribution_study(config_path: str, out_path: str | None = None) -> dict[str, Any]:
    """Execute the attribution study (deterministic; reuses organism_runner).

    Baseline + one ablation per driver (base_aging_rate x scale, config
    layer only) on every seed; optional top-2 interaction when the main
    analysis finds two or more substantial drivers. Writes the artifact.
    """
    from longevity.experiment.organism_runner import (
        OrganismExperimentConfig,
        load_organism_config,
        run_organism_experiment,
    )
    from longevity.model.aging import DEFAULT_DRIVER_PARAMS

    wall_start = time.perf_counter()
    config = load_attribution_config(config_path)
    seeds = [int(s) for s in config["seeds"]]
    base_cfg = load_organism_config(config["base_organism_config"]).to_config_dict()
    rollback = dict(config.get("rollback_policy_overrides", {}) or {})
    apoptosis = dict(config.get("apoptosis_policy_overrides", {}) or {})
    r_idx = int(rollback.get("policy_index", 6))
    a_idx = int(apoptosis.get("policy_index", 7))
    base_cfg["policies"][r_idx]["biomarker_threshold"] = float(rollback.get("biomarker_threshold", 0.03))
    base_cfg["policies"][r_idx]["intensity"] = float(rollback.get("intensity", 1.0))
    base_cfg["policies"][r_idx]["interval"] = float(rollback.get("interval", 1.0))
    base_cfg["policies"][a_idx]["interval"] = float(apoptosis.get("interval", 10.0))

    def _run_one(aging_overrides: dict[str, dict[str, float]], tag: str, seed: int):
        data = copy.deepcopy(base_cfg)
        data["organism_id"] = f"{config['experiment_id']}_{tag}_s{seed}"
        data["seed"] = seed
        drivers = dict(data.get("aging_drivers", {}) or {})
        for driver, params in aging_overrides.items():
            merged = dict(drivers.get(driver, {}))
            merged.update(params)
            drivers[driver] = merged
        data["aging_drivers"] = drivers
        result = run_organism_experiment(OrganismExperimentConfig.from_config_dict(data))
        return result["trajectory"], result["metrics"]["final"]

    baseline: dict[str, Any] = {}
    for seed in seeds:
        traj, summary = _run_one({}, "baseline", seed)
        baseline[str(seed)] = per_seed_attribution(traj, summary)
    ablations: dict[str, Any] = {}
    scale = float(config["ablation_driver_scale"])
    for driver in config["drivers"]:
        default_rate = float(DEFAULT_DRIVER_PARAMS[driver]["base_aging_rate"])
        per_seed: dict[str, Any] = {}
        for seed in seeds:
            traj, summary = _run_one({driver: {"base_aging_rate": default_rate * scale}},
                                     f"ablate_{driver}", seed)
            per_seed[str(seed)] = per_seed_attribution(traj, summary)
        ablations[driver] = per_seed
    verdict = analyze_constraint_migration({
        "baseline": baseline, "ablations": ablations,
        "thresholds": {"relative": float(config.get("single_driver_relative_threshold", 0.30)),
                       "margin": float(config.get("single_driver_margin", 2.0))},
    })
    substantial = [d for d in verdict["ranking"]
                   if verdict["ablation_results"][d]["reproducible"]
                   and verdict["ablation_results"][d]["relative_improvement_mean"]
                   > float(config.get("single_driver_relative_threshold", 0.30))]
    if len(substantial) >= 2:
        top2 = verdict["ranking"][:2]
        conditions: dict[str, Any] = {}
        for cond, over in (("A", {top2[0]: scale}), ("B", {top2[1]: scale}),
                           ("AB", {top2[0]: scale, top2[1]: scale})):
            per_seed_c: dict[str, Any] = {}
            for seed in seeds:
                ov = {d: {"base_aging_rate": float(DEFAULT_DRIVER_PARAMS[d]["base_aging_rate"]) * s}
                      for d, s in over.items()}
                traj, summary = _run_one(ov, f"interact_{cond}", seed)
                per_seed_c[str(seed)] = per_seed_attribution(traj, summary)
            conditions[cond] = per_seed_c
        verdict = analyze_constraint_migration({
            "baseline": baseline, "ablations": ablations,
            "interaction": {"A": top2[0], "B": top2[1], "conditions": conditions},
            "thresholds": {"relative": float(config.get("single_driver_relative_threshold", 0.30)),
                           "margin": float(config.get("single_driver_margin", 2.0))},
        })
    artifact = {
        "experiment_id": config["experiment_id"],
        "stage": config.get("stage", "9b"),
        "model_version": "0.5.0",
        "experiment_version": "rollback-attribution/v1",
        "seeds": seeds,
        "configuration": {"rollback_policy": {k: v for k, v in rollback.items() if k != "policy_index"},
                          "apoptosis_interval": float(apoptosis.get("interval", 10.0)),
                          "ablation_driver_scale": scale,
                          "base_organism_config": config["base_organism_config"]},
        "baseline": verdict["baseline"],
        "ablations": verdict["ablation_results"],
        "ranking": verdict["ranking"],
        "classification": verdict["classification"],
        "candidate_binding_driver": verdict["candidate_binding_driver"],
        "confidence": verdict["confidence"],
        "notes": verdict["notes"],
        "interaction": verdict["interaction_analysis"],
        "diagnostic_decomposition": verdict["diagnostic_decomposition"],
        "unresolved_questions": [
            "driver ablation scales accumulation only; repair-side coupling is not ablated",
            "entropy meta-driver is not ablated here (rollback already suppresses it)",
            "thresholds (30%, 2x, 50%) are operational, not biological laws",
            "n = 3 seeds: descriptive spread, not significance",
        ],
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
