"""EXPERIMENT ENGINE LAYER: robust multi-seed + stress evaluation (Stage 5B).

Runs named organism configurations across seeds and stress scenarios,
aggregating robust statistics, binding constraints, and failure-cause
distributions. Deterministic throughout: same config + seeds give
identical artifacts; global random is never touched.

CLI::

    PYTHONPATH=src python -m longevity.experiment.organism_robust \\
        --config experiments/configs/organism_stress_suite.json \\
        --out-prefix experiments/output/organism_stress_suite
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import os
import platform
import time

from dataclasses import dataclass, field
from typing import Any

from longevity.analysis.organism_metrics import (
    binding_constraints,
    robust_aggregate,
    robust_bounded_degradation,
    validate_robust_criteria,
)
from longevity.experiment.organism_runner import OrganismExperimentConfig, run_organism_experiment
from longevity.model.organism import MODEL_SCOPE, ORGANISM_MODEL_VERSION

ROBUST_FORMAT_VERSION = "1.0"
MIN_ROBUST_SEEDS = 2

# Named stress-scenario presets (operational, documented in ORGANISM_MODEL.md).
STRESS_SCENARIOS: dict[str, dict[str, Any]] = {
    "nominal": {"perturbation": {"model": "none"}, "organism_parameters": {}},
    "parametric_noise": {"perturbation": {"model": "parametric_noise", "aging_noise_scale": 0.15,
                                          "intervention_efficacy_noise_scale": 0.15,
                                          "repair_capacity_noise_scale": 0.15},
                         "organism_parameters": {}},
    "shocks_only": {"perturbation": {"model": "parametric_noise", "shock_probability_per_step": 0.02,
                                     "shock_magnitude_scale": 1.0, "shock_duration_steps": 2},
                    "organism_parameters": {}},
    "noise_and_shocks": {"perturbation": {"model": "parametric_noise", "aging_noise_scale": 0.15,
                                          "intervention_efficacy_noise_scale": 0.15,
                                          "repair_capacity_noise_scale": 0.15,
                                          "shock_probability_per_step": 0.02,
                                          "shock_magnitude_scale": 1.0, "shock_duration_steps": 2},
                         "organism_parameters": {}},
    "high_cancer_risk": {"perturbation": {"model": "none"}, "organism_parameters": {"cancer_rate": 0.0036}},
    "high_inflammation": {"perturbation": {"model": "none"}, "organism_parameters": {"inflammation_rate": 0.012}},
    "low_reserve": {"perturbation": {"model": "none"}, "organism_parameters": {"repair_reserve_cost": 1.2},
                    "initial_reserve_scale": 0.3},
    "neural_stress": {"perturbation": {"model": "parametric_noise", "shock_probability_per_step": 0.03,
                                       "shock_magnitude_scale": 1.5, "shock_duration_steps": 2,
                                       "shock_types": ["neural_stress"]},
                      "organism_parameters": {}},
    "intervention_toxicity": {"perturbation": {"model": "parametric_noise", "efficacy_scale": 0.5},
                              "organism_parameters": {}},
    "global_resource_shock": {"perturbation": {"model": "parametric_noise", "shock_probability_per_step": 0.03,
                                              "shock_magnitude_scale": 1.5, "shock_duration_steps": 2},
                              "organism_parameters": {}, "systemic_resource_scale": 0.5},
}


def _require_seeds(seeds: Any) -> tuple[int, ...]:
    if not isinstance(seeds, (list, tuple)) or len(seeds) == 0:
        raise ValueError("robust seeds must be a non-empty list")
    cleaned = []
    for seed in seeds:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError(f"robust seed must be an int, got {seed!r}")
        cleaned.append(seed)
    if len(set(cleaned)) != len(cleaned):
        raise ValueError("robust seeds must be unique")
    if len(cleaned) < MIN_ROBUST_SEEDS:
        raise ValueError(f"robust evaluation needs at least {MIN_ROBUST_SEEDS} seeds, got {len(cleaned)}")
    return tuple(cleaned)


def _validate_scenario(name: str, scenario: dict[str, Any]) -> dict[str, Any]:
    """Validate a stress-scenario block."""
    if not isinstance(scenario, dict):
        raise ValueError(f"scenario {name!r} must be a dict")
    from longevity.model.organism import validate_perturbation
    perturbation = validate_perturbation(dict(scenario.get("perturbation", {"model": "none"})))
    shock_types = scenario.get("shock_types", None)
    if shock_types is not None:
        from longevity.model.organism import SHOCK_TYPES
        if not isinstance(shock_types, list) or not shock_types or any(t not in SHOCK_TYPES for t in shock_types):
            raise ValueError(f"scenario {name!r} shock_types must be a non-empty subset of {SHOCK_TYPES}")
    parameters = scenario.get("organism_parameters", {})
    if not isinstance(parameters, dict):
        raise ValueError(f"scenario {name!r} organism_parameters must be a dict")
    from longevity.model.organism import validate_organism_parameters
    validate_organism_parameters(parameters)
    reserve_scale = scenario.get("initial_reserve_scale", 1.0)
    if isinstance(reserve_scale, bool) or not isinstance(reserve_scale, (int, float)) \
            or not math.isfinite(float(reserve_scale)) or float(reserve_scale) < 0.0:
        raise ValueError(f"scenario {name!r} initial_reserve_scale must be finite and >= 0")
    resource_scale = scenario.get("systemic_resource_scale", 1.0)
    if isinstance(resource_scale, bool) or not isinstance(resource_scale, (int, float)) \
            or not math.isfinite(float(resource_scale)) or float(resource_scale) < 0.0:
        raise ValueError(f"scenario {name!r} systemic_resource_scale must be finite and >= 0")
    return {"name": name, "perturbation": perturbation,
            "organism_parameters": dict(parameters),
            "shock_types": list(shock_types) if shock_types else [],
            "initial_reserve_scale": float(reserve_scale),
            "systemic_resource_scale": float(resource_scale)}


@dataclass(frozen=True)
class OrganismRobustConfig:
    """Complete, self-describing robust evaluation configuration."""

    experiment_id: str
    seeds: tuple[int, ...] = ()
    scenarios: tuple[str, ...] = ()
    runs: dict[str, Any] = field(default_factory=dict)
    scenario_overrides: dict[str, Any] = field(default_factory=dict)
    robust_criteria: dict[str, Any] = field(default_factory=dict)
    output_prefix: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id must be non-empty")
        _require_seeds(list(self.seeds))
        if not isinstance(self.scenarios, (list, tuple)) or not self.scenarios:
            raise ValueError("scenarios must be a non-empty list")
        known = set(STRESS_SCENARIOS) | set(self.scenario_overrides)
        for name in self.scenarios:
            if name not in known:
                raise ValueError(f"unknown scenario {name!r}; known: {sorted(known)}")
        if not isinstance(self.runs, dict) or not self.runs:
            raise ValueError("runs must be a non-empty dict of run_id -> organism config")
        for run_id, base in self.runs.items():
            OrganismExperimentConfig.from_config_dict(copy.deepcopy(base))
        for name, override in dict(self.scenario_overrides).items():
            _validate_scenario(name, override)
        from longevity.analysis.organism_metrics import validate_robust_criteria
        validate_robust_criteria(dict(self.robust_criteria))

    def effective_scenario(self, name: str) -> dict[str, Any]:
        if name in self.scenario_overrides:
            return _validate_scenario(name, copy.deepcopy(self.scenario_overrides[name]))
        return _validate_scenario(name, copy.deepcopy(STRESS_SCENARIOS[name]))

    def to_config_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "seeds": list(self.seeds),
            "scenarios": list(self.scenarios),
            "runs": copy.deepcopy(self.runs),
            "scenario_overrides": copy.deepcopy(self.scenario_overrides),
            "robust_criteria": copy.deepcopy(self.robust_criteria),
            "output_prefix": self.output_prefix,
            "notes": self.notes,
        }

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "OrganismRobustConfig":
        return cls(
            experiment_id=data["experiment_id"],
            seeds=tuple(data.get("seeds", ())),
            scenarios=tuple(data.get("scenarios", ())),
            runs=copy.deepcopy(data.get("runs", {})),
            scenario_overrides=copy.deepcopy(data.get("scenario_overrides", {})),
            robust_criteria=copy.deepcopy(data.get("robust_criteria", {})),
            output_prefix=data.get("output_prefix", ""),
            notes=data.get("notes", ""),
        )


def robust_config_hash(config: OrganismRobustConfig) -> str:
    canonical = json.dumps(config.to_config_dict(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _apply_scenario(base: dict[str, Any], scenario: dict[str, Any], seed: int) -> OrganismExperimentConfig:
    """Merge a scenario into a base organism config for one seed (pure)."""
    from longevity.model.organism import validate_perturbation
    data = copy.deepcopy(base)
    data["seed"] = seed
    params = dict(data.get("organism_parameters", {}))
    params.update(scenario["organism_parameters"])
    data["organism_parameters"] = params
    base_perturb = validate_perturbation(dict(data.get("perturbation", {})))
    scenario_perturb = dict(scenario["perturbation"])
    if scenario_perturb.get("model", "none") != "none":
        base_perturb.update(scenario_perturb)
        base_perturb["model"] = scenario_perturb["model"]
    if scenario.get("shock_types"):
        base_perturb["shock_types"] = list(scenario["shock_types"])
    data["perturbation"] = validate_perturbation(base_perturb)
    reserve_scale = scenario["initial_reserve_scale"]
    if reserve_scale != 1.0 and data.get("initial_state"):
        for info in data["initial_state"].get("systems", {}).values():
            if "reserve" in info:
                info["reserve"] = float(info["reserve"]) * reserve_scale
    resource_scale = scenario.get("systemic_resource_scale", 1.0)
    if resource_scale != 1.0:
        from longevity.model.organ_backed import validate_resource_budgets  # deferred

        budgets = validate_resource_budgets(dict(data.get("systemic_resources", {})))
        data["systemic_resources"] = {r: b * resource_scale for r, b in budgets.items()}
    return OrganismExperimentConfig.from_config_dict(data)


def run_robust_evaluation(config: OrganismRobustConfig) -> dict[str, Any]:
    """Run runs x seeds x scenarios; returns a JSON-serializable result."""
    from longevity.analysis.organism_metrics import validate_robust_criteria
    wall_start = time.perf_counter()
    criteria = validate_robust_criteria(dict(config.robust_criteria))
    cells: list[dict[str, Any]] = []
    for run_id in sorted(config.runs):
        for scenario_name in config.scenarios:
            scenario = config.effective_scenario(scenario_name)
            seed_summaries: dict[str, Any] = {}
            seed_trajectories: dict[str, Any] = {}
            for seed in config.seeds:
                experiment = _apply_scenario(config.runs[run_id], scenario, seed)
                result = run_organism_experiment(experiment, out_path=None)
                summary = result["metrics"]["final"]
                trajectory = result["trajectory"]
                summary["binding"] = binding_constraints(trajectory, criteria)
                summary["shock_count"] = len(trajectory[-1].get("shock_history", []))
                summary["max_cancer_burden_proxy"] = max(float(r["cancer_burden"]) for r in trajectory[1:])
                seed_summaries[str(seed)] = summary
                seed_trajectories[str(seed)] = trajectory
            aggregate = robust_aggregate(list(seed_summaries.values()),
                                         [seed_trajectories[str(seed)] for seed in config.seeds],
                                         criteria)
            cells.append({
                "run_id": run_id,
                "scenario": scenario_name,
                "n_seeds": len(config.seeds),
                "aggregate": aggregate,
                "seeds": seed_summaries,
            })
    by_run: dict[str, Any] = {}
    for run_id in sorted(config.runs):
        owned = [c for c in cells if c["run_id"] == run_id]
        by_run[run_id] = {
            "mean_lifespan": sum(c["aggregate"]["lifespan"]["mean"] for c in owned) / len(owned),
            "mean_healthspan": sum(c["aggregate"]["healthspan"]["mean"] for c in owned) / len(owned),
            "robust_success_any": any(c["aggregate"]["robust"]["robust_bounded_degradation_indicator"] for c in owned),
            "scenarios": {c["scenario"]: c["aggregate"]["robust"]["robust_bounded_degradation_indicator"] for c in owned},
        }
    wall_seconds = round(time.perf_counter() - wall_start, 4)
    return {
        "experiment_id": config.experiment_id,
        "format": ROBUST_FORMAT_VERSION,
        "config": config.to_config_dict(),
        "config_hash": robust_config_hash(config),
        "model_version": ORGANISM_MODEL_VERSION,
        "model_scope": MODEL_SCOPE,
        "immortality_status": "hypothesis_not_proven",
        "seeds": list(config.seeds),
        "cells": cells,
        "by_run": by_run,
        "runtime": {
            "engine": "organism-robust/v0",
            "python": platform.python_version(),
            "platform": platform.platform(),
            "wall_seconds": wall_seconds,
        },
    }


def _round6(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, list):
        return [_round6(v) for v in value]
    if isinstance(value, dict):
        return {k: _round6(v) for k, v in value.items()}
    return value


LONG_COLUMNS = (
    "run_id", "scenario", "seed", "lifespan", "healthspan",
    "primary_cause_of_death", "bounded_degradation_indicator",
    "biological_age_slope_after_adulthood", "damage_slope_after_adulthood",
    "cancer_auc", "max_cancer_burden_proxy", "min_informational_continuity",
    "first_constraint_violated", "shock_count",
)

def write_robust_outputs(result: dict[str, Any], out_prefix: str) -> dict[str, str]:
    """Write long CSV, summary CSV/JSON, comparison, binding, stress artifacts."""
    parent = os.path.dirname(os.path.abspath(out_prefix))
    os.makedirs(parent, exist_ok=True)
    long_path = f"{out_prefix}_long.csv"
    summary_path = f"{out_prefix}_summary.csv"
    summary_json_path = f"{out_prefix}_summary.json"
    comparison_path = f"{out_prefix}_robust_comparison.json"
    binding_path = f"{out_prefix}_binding_constraints.json"
    stress_path = f"{out_prefix}_stress_suite.json"

    long_rows: list[dict[str, Any]] = []
    for cell in result["cells"]:
        for seed in result["seeds"]:
            row = cell["seeds"][str(seed)]
            binding = row.get("binding", {})
            long_rows.append({
                "run_id": cell["run_id"],
                "scenario": cell["scenario"],
                "seed": seed,
                "lifespan": _round6(row["lifespan"]),
                "healthspan": _round6(row["healthspan"]),
                "primary_cause_of_death": row["primary_cause_of_death"],
                "bounded_degradation_indicator": row["bounded_degradation_indicator"],
                "biological_age_slope_after_adulthood": _round6(row["biological_age_slope_after_adulthood"]),
                "damage_slope_after_adulthood": _round6(row["damage_slope_after_adulthood"]),
                "cancer_auc": _round6(row["cancer_auc"]),
                "max_cancer_burden_proxy": _round6(row.get("max_cancer_burden_proxy", 0.0)),
                "min_informational_continuity": _round6(row.get("informational_continuity_min", 1.0)),
                "first_constraint_violated": binding.get("first_constraint_violated", ""),
                "shock_count": row.get("shock_count", 0),
            })
    with open(long_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(LONG_COLUMNS))
        writer.writeheader()
        writer.writerows(long_rows)

    summary_fieldnames = ["run_id", "scenario", "n_seeds", "mean_lifespan", "std_lifespan",
                          "min_lifespan", "max_lifespan", "mean_healthspan", "std_healthspan",
                          "success_rate_bounded", "robust_bounded", "death_rate",
                          "primary_cause_counts", "binding_constraint_distribution",
                          "worst_bio_slope", "worst_damage_slope", "mean_cancer_auc"]
    with open(summary_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=summary_fieldnames)
        writer.writeheader()
        for cell in result["cells"]:
            aggregate = cell["aggregate"]
            writer.writerow({
                "run_id": cell["run_id"], "scenario": cell["scenario"], "n_seeds": cell["n_seeds"],
                "mean_lifespan": _round6(aggregate["lifespan"]["mean"]),
                "std_lifespan": _round6(aggregate["lifespan"]["std"]),
                "min_lifespan": _round6(aggregate["lifespan"]["min"]),
                "max_lifespan": _round6(aggregate["lifespan"]["max"]),
                "mean_healthspan": _round6(aggregate["healthspan"]["mean"]),
                "std_healthspan": _round6(aggregate["healthspan"]["std"]),
                "success_rate_bounded": _round6(aggregate["robust"]["success_rate_bounded"]),
                "robust_bounded": aggregate["robust"]["robust_bounded_degradation_indicator"],
                "death_rate": _round6(sum(1 for s in cell["seeds"].values()
                                          if s["primary_cause_of_death"] != "none") / cell["n_seeds"]),
                "primary_cause_counts": json.dumps(aggregate["primary_cause_counts"], sort_keys=True),
                "binding_constraint_distribution": json.dumps(aggregate["binding_constraint_distribution"], sort_keys=True),
                "worst_bio_slope": _round6(aggregate["worst_case_biological_age_slope"]),
                "worst_damage_slope": _round6(aggregate["worst_case_damage_slope"]),
                "mean_cancer_auc": _round6(aggregate["cancer_auc"]["mean"]),
            })
    with open(summary_json_path, "w", encoding="utf-8") as fh:
        json.dump(_round6(result), fh, ensure_ascii=False, indent=2, allow_nan=False)
    with open(comparison_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": result["experiment_id"], "config_hash": result["config_hash"],
                   "by_run": _round6(result["by_run"])}, fh, ensure_ascii=False, indent=2, allow_nan=False)
    binding_all: dict[str, Any] = {}
    for cell in result["cells"]:
        binding_all[f"{cell['run_id']}@{cell['scenario']}"] = cell["aggregate"]["binding_constraint_distribution"]
    with open(binding_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": result["experiment_id"], "config_hash": result["config_hash"],
                   "binding_constraints": binding_all}, fh, ensure_ascii=False, indent=2, allow_nan=False)
    with open(stress_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": result["experiment_id"], "config_hash": result["config_hash"],
                   "model_scope": result["model_scope"], "immortality_status": result["immortality_status"],
                   "stress_cells": [
                       {"run_id": c["run_id"], "scenario": c["scenario"],
                        "mean_lifespan": _round6(c["aggregate"]["lifespan"]["mean"]),
                        "mean_healthspan": _round6(c["aggregate"]["healthspan"]["mean"]),
                        "robust_bounded": c["aggregate"]["robust"]["robust_bounded_degradation_indicator"],
                        "primary_cause_counts": c["aggregate"]["primary_cause_counts"]}
                       for c in result["cells"]]},
                  fh, ensure_ascii=False, indent=2, allow_nan=False)
    for value in [row["lifespan"] for row in long_rows]:
        if not math.isfinite(float(value)):
            raise ValueError("non-finite robust output")
    return {"long_csv": long_path, "summary_csv": summary_path, "summary_json": summary_json_path,
            "robust_comparison_json": comparison_path, "binding_constraints_json": binding_path,
            "stress_suite_json": stress_path}


def load_robust_config(path: str) -> OrganismRobustConfig:
    """Read a robust evaluation JSON file into a validated config."""
    with open(path, encoding="utf-8") as fh:
        return OrganismRobustConfig.from_config_dict(json.load(fh))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Stage 5B robust organism evaluation.")
    parser.add_argument("--config", required=True, help="Robust config JSON")
    parser.add_argument("--out-prefix", default="", help="Output prefix (default: config output_prefix)")
    args = parser.parse_args()
    config = load_robust_config(args.config)
    out_prefix = args.out_prefix or config.output_prefix
    if not out_prefix:
        raise ValueError("no out-prefix: pass --out-prefix or set output_prefix in the config")
    result = run_robust_evaluation(config)
    paths = write_robust_outputs(result, out_prefix)
    print(f"[robust {config.experiment_id}] {len(result['cells'])} cells x {len(config.seeds)} seeds")
    for run_id, summary in result["by_run"].items():
        print(f"[run {run_id}] mean_lifespan={summary['mean_lifespan']:.1f} "
              f"robust_bounded_any={summary['robust_success_any']}")
    for key, path in paths.items():
        print(f"[{key}] {path}")


if __name__ == "__main__":
    main()
