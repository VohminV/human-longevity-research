"""EXPERIMENT ENGINE LAYER: organ-network coordination/resource/hard-limit studies (Stage 6B).

Three config kinds (dispatched on the ``kind`` field):

- ``coordination_compare``: one organ-network base config run under each
  network-aware coordination mode.
- ``resource_sensitivity``: grid over systemic resource budgets reusing
  :func:`run_organism_experiment`.
- ``hard_limit_sensitivity``: grid over hard-limit values reusing
  :func:`run_organism_experiment`.

CLI::

    PYTHONPATH=src python -m longevity.experiment.organism_organ_network \\
        --config experiments/configs/organism_organ_network_coordination_compare.json \\
        --out-prefix experiments/output/organism_organ_network_coordination_compare
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import itertools
import json
import math
import os
import platform
import time

from dataclasses import dataclass, field
from typing import Any

from longevity.analysis.organ_network_metrics import (
    network_binding,
    robust_bounded_degradation_v4,
    validate_v4_criteria,
)
from longevity.experiment.organism_runner import OrganismExperimentConfig, run_organism_experiment
from longevity.model.organ_backed import SYSTEMIC_RESOURCES, validate_resource_budgets
from longevity.model.organ_network import ORGAN_NETWORK_SCOPE, validate_hard_limits

ORGAN_NETWORK_EXPERIMENT_VERSION = "1.0"
MIN_ORGAN_NETWORK_SEEDS = 2

NETWORK_MODES_FOR_COMPARE = (
    "independent_network",
    "global_resource_aware_scaling",
    "network_bottleneck_priority",
    "cascade_guard",
    "information_preservation_priority",
    "mutation_load_guard",
    "lookahead_network",
    "deferral_network",
)

HARD_LIMIT_AXES = tuple(sorted([
    "max_mutation_load",
    "min_informational_continuity",
    "max_cascade_risk",
    "energy_budget_initial",
    "max_intervention_toxicity",
    "max_feedback_gain",
]))


def _require_seeds(seeds: Any) -> tuple[int, ...]:
    if not isinstance(seeds, (list, tuple)) or len(seeds) == 0:
        raise ValueError("organ-network seeds must be a non-empty list")
    cleaned = []
    for seed in seeds:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError(f"organ-network seed must be an int, got {seed!r}")
        cleaned.append(seed)
    if len(set(cleaned)) != len(cleaned):
        raise ValueError("organ-network seeds must be unique")
    if len(cleaned) < MIN_ORGAN_NETWORK_SEEDS:
        raise ValueError(
            f"organ-network studies need at least {MIN_ORGAN_NETWORK_SEEDS} seeds, got {len(cleaned)}")
    return tuple(cleaned)


def _require_network_base(base: dict[str, Any]) -> None:
    if not isinstance(base, dict) or not base:
        raise ValueError("base_organism_config must be a non-empty dict")
    if base.get("organ_network_model", "none") != "reduced_network_feedback":
        raise ValueError("organ-network studies require base_organism_config with "
                         "organ_network_model=reduced_network_feedback")
    if base.get("organ_backed_model", "none") != "reduced_organ_proxies":
        raise ValueError("organ-network studies require base_organism_config with "
                         "organ_backed_model=reduced_organ_proxies")
    OrganismExperimentConfig.from_config_dict(copy.deepcopy(base))


def _mean(values: list[float]) -> float:
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        raise ValueError("cannot average empty/non-finite data")
    return sum(finite) / len(finite)


def _run_one(base: dict[str, Any], seed: int, overrides: dict[str, Any],
             criteria: dict[str, float]) -> dict[str, Any]:
    data = copy.deepcopy(base)
    data["seed"] = seed
    data.update(copy.deepcopy(overrides))
    experiment = OrganismExperimentConfig.from_config_dict(data)
    result = run_organism_experiment(experiment, out_path=None)
    summary = result["metrics"]["final"]
    binding = network_binding(result["trajectory"], dict(criteria))
    return {"summary": summary, "binding": binding}


@dataclass(frozen=True)
class NetworkCoordinationCompareConfig:
    experiment_id: str
    seeds: tuple[int, ...] = ()
    coordination_modes: tuple[str, ...] = ()
    base_organism_config: dict[str, Any] = field(default_factory=dict)
    v4_criteria: dict[str, Any] = field(default_factory=dict)
    output_prefix: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id must be non-empty")
        _require_seeds(list(self.seeds))
        if not self.coordination_modes:
            raise ValueError("coordination_modes must be non-empty")
        from longevity.model.organ_backed import validate_coordination_mode

        for mode in self.coordination_modes:
            validate_coordination_mode(mode)
        _require_network_base(copy.deepcopy(self.base_organism_config))
        validate_v4_criteria(dict(self.v4_criteria))

    def to_config_dict(self) -> dict[str, Any]:
        return {
            "kind": "coordination_compare",
            "experiment_id": self.experiment_id,
            "seeds": list(self.seeds),
            "coordination_modes": list(self.coordination_modes),
            "base_organism_config": copy.deepcopy(self.base_organism_config),
            "v4_criteria": copy.deepcopy(dict(self.v4_criteria)),
            "output_prefix": self.output_prefix,
            "notes": self.notes,
        }

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "NetworkCoordinationCompareConfig":
        return cls(
            experiment_id=data["experiment_id"],
            seeds=tuple(data.get("seeds", ())),
            coordination_modes=tuple(data.get("coordination_modes", ())),
            base_organism_config=copy.deepcopy(data.get("base_organism_config", {})),
            v4_criteria=copy.deepcopy(data.get("v4_criteria", {})),
            output_prefix=data.get("output_prefix", ""),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True)
class NetworkResourceSensitivityConfig:
    experiment_id: str
    seeds: tuple[int, ...] = ()
    resource_axes: dict[str, list] = field(default_factory=dict)
    base_organism_config: dict[str, Any] = field(default_factory=dict)
    v4_criteria: dict[str, Any] = field(default_factory=dict)
    output_prefix: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id must be non-empty")
        _require_seeds(list(self.seeds))
        if not isinstance(self.resource_axes, dict) or not self.resource_axes:
            raise ValueError("resource_axes must be a non-empty dict of resource -> budgets")
        for resource, values in self.resource_axes.items():
            if resource not in SYSTEMIC_RESOURCES and resource != "energy_budget_initial":
                raise ValueError(
                    f"resource axis must be one of {tuple(SYSTEMIC_RESOURCES) + ('energy_budget_initial',)}, "
                    f"got {resource!r}")
            if not isinstance(values, list) or not values:
                raise ValueError(f"resource_axes[{resource!r}] must be a non-empty list")
            if resource in SYSTEMIC_RESOURCES:
                validate_resource_budgets({resource: v for v in values} if values else {})
        _require_network_base(copy.deepcopy(self.base_organism_config))
        validate_v4_criteria(dict(self.v4_criteria))

    def to_config_dict(self) -> dict[str, Any]:
        return {
            "kind": "resource_sensitivity",
            "experiment_id": self.experiment_id,
            "seeds": list(self.seeds),
            "resource_axes": copy.deepcopy(self.resource_axes),
            "base_organism_config": copy.deepcopy(self.base_organism_config),
            "v4_criteria": copy.deepcopy(dict(self.v4_criteria)),
            "output_prefix": self.output_prefix,
            "notes": self.notes,
        }

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "NetworkResourceSensitivityConfig":
        return cls(
            experiment_id=data["experiment_id"],
            seeds=tuple(data.get("seeds", ())),
            resource_axes=copy.deepcopy(data.get("resource_axes", {})),
            base_organism_config=copy.deepcopy(data.get("base_organism_config", {})),
            v4_criteria=copy.deepcopy(data.get("v4_criteria", {})),
            output_prefix=data.get("output_prefix", ""),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True)
class HardLimitSensitivityConfig:
    experiment_id: str
    seeds: tuple[int, ...] = ()
    hard_limit_axes: dict[str, list] = field(default_factory=dict)
    base_organism_config: dict[str, Any] = field(default_factory=dict)
    v4_criteria: dict[str, Any] = field(default_factory=dict)
    output_prefix: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id must be non-empty")
        _require_seeds(list(self.seeds))
        if not isinstance(self.hard_limit_axes, dict) or not self.hard_limit_axes:
            raise ValueError("hard_limit_axes must be a non-empty dict of limit -> values")
        for limit, values in self.hard_limit_axes.items():
            if limit not in HARD_LIMIT_AXES:
                raise ValueError(f"hard limit axis must be one of {HARD_LIMIT_AXES}, got {limit!r}")
            if not isinstance(values, list) or not values:
                raise ValueError(f"hard_limit_axes[{limit!r}] must be a non-empty list")
            validate_hard_limits({limit: v for v in values} if values else {})
        _require_network_base(copy.deepcopy(self.base_organism_config))
        validate_v4_criteria(dict(self.v4_criteria))

    def to_config_dict(self) -> dict[str, Any]:
        return {
            "kind": "hard_limit_sensitivity",
            "experiment_id": self.experiment_id,
            "seeds": list(self.seeds),
            "hard_limit_axes": copy.deepcopy(self.hard_limit_axes),
            "base_organism_config": copy.deepcopy(self.base_organism_config),
            "v4_criteria": copy.deepcopy(dict(self.v4_criteria)),
            "output_prefix": self.output_prefix,
            "notes": self.notes,
        }

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "HardLimitSensitivityConfig":
        return cls(
            experiment_id=data["experiment_id"],
            seeds=tuple(data.get("seeds", ())),
            hard_limit_axes=copy.deepcopy(data.get("hard_limit_axes", {})),
            base_organism_config=copy.deepcopy(data.get("base_organism_config", {})),
            v4_criteria=copy.deepcopy(data.get("v4_criteria", {})),
            output_prefix=data.get("output_prefix", ""),
            notes=data.get("notes", ""),
        )


def _config_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def run_coordination_compare(config: NetworkCoordinationCompareConfig) -> dict[str, Any]:
    wall_start = time.perf_counter()
    criteria = validate_v4_criteria(dict(config.v4_criteria))
    modes_block: dict[str, Any] = {}
    for mode in sorted(config.coordination_modes):
        seed_rows: dict[str, Any] = {}
        for seed in config.seeds:
            seed_rows[str(seed)] = _run_one(copy.deepcopy(config.base_organism_config), seed,
                                            {"coordination_mode": mode}, criteria)
        summaries = [row["summary"] for row in seed_rows.values()]
        v4 = robust_bounded_degradation_v4(summaries, dict(criteria))
        binding_votes: dict[str, int] = {}
        for row in seed_rows.values():
            key = row["binding"]["first_network_constraint_violated"]
            binding_votes[key] = binding_votes.get(key, 0) + 1
        modes_block[mode] = {
            "n_seeds": len(config.seeds),
            "mean_lifespan": _mean([r["summary"]["lifespan"] for r in seed_rows.values()]),
            "mean_healthspan": _mean([r["summary"]["healthspan"] for r in seed_rows.values()]),
            "mean_max_cascade": _mean([
                r["summary"].get("organ_network", {}).get("max_cascade_risk", 0.0)
                for r in seed_rows.values()]),
            "robust_v4": v4,
            "binding_votes": binding_votes,
            "coordination_stats": {str(seed): row["summary"].get("network_coordination_stats", {})
                                   for seed, row in seed_rows.items()},
            "seeds": seed_rows,
        }
    independent = modes_block.get("independent_network", {})
    comparison = {}
    for mode, block in modes_block.items():
        if mode == "independent_network" or not independent:
            comparison[mode] = {"lifespan_gain_vs_independent_network": 0.0,
                                "healthspan_gain_vs_independent_network": 0.0,
                                "cascade_delta_vs_independent_network": 0.0}
        else:
            comparison[mode] = {
                "lifespan_gain_vs_independent_network": block["mean_lifespan"] - independent["mean_lifespan"],
                "healthspan_gain_vs_independent_network": block["mean_healthspan"] - independent["mean_healthspan"],
                "cascade_delta_vs_independent_network": block["mean_max_cascade"] - independent["mean_max_cascade"],
            }
    wall_seconds = round(time.perf_counter() - wall_start, 4)
    return {
        "kind": "coordination_compare",
        "experiment_id": config.experiment_id,
        "format": ORGAN_NETWORK_EXPERIMENT_VERSION,
        "config": config.to_config_dict(),
        "config_hash": _config_hash(config.to_config_dict()),
        "model_scope": ORGAN_NETWORK_SCOPE,
        "immortality_status": "hypothesis_not_proven",
        "candidate_robust_bounded_degradation_v4_found": any(
            block["robust_v4"]["robust_bounded_degradation_v4"] for block in modes_block.values()),
        "seeds": list(config.seeds),
        "modes": modes_block,
        "comparison": comparison,
        "runtime": {"engine": "organism-organ-network/v0", "python": platform.python_version(),
                    "platform": platform.platform(), "wall_seconds": wall_seconds},
    }


def run_resource_sensitivity(config: NetworkResourceSensitivityConfig) -> dict[str, Any]:
    wall_start = time.perf_counter()
    criteria = validate_v4_criteria(dict(config.v4_criteria))
    axes = sorted(config.resource_axes)
    points: list[dict[str, Any]] = []
    for values in itertools.product(*[config.resource_axes[axis] for axis in axes]):
        combo = dict(zip(axes, values))
        seed_rows: dict[str, Any] = {}
        for seed in config.seeds:
            base = copy.deepcopy(config.base_organism_config)
            budgets = dict(base.get("systemic_resources", {}))
            hard_limits = dict(base.get("organ_network_hard_limits", {}))
            overrides: dict[str, Any] = {}
            for axis_name, value in combo.items():
                if axis_name in SYSTEMIC_RESOURCES:
                    budgets[axis_name] = value
                elif axis_name == "energy_budget_initial":
                    hard_limits[axis_name] = value
            if any(k in SYSTEMIC_RESOURCES for k in combo):
                overrides["systemic_resources"] = budgets
            if "energy_budget_initial" in combo:
                overrides["organ_network_hard_limits"] = hard_limits
            seed_rows[str(seed)] = _run_one(base, seed, overrides, criteria)
        summaries = [row["summary"] for row in seed_rows.values()]
        binding_votes: dict[str, int] = {}
        cause_votes: dict[str, int] = {}
        for row in seed_rows.values():
            binding = row["binding"]["first_network_constraint_violated"]
            binding_votes[binding] = binding_votes.get(binding, 0) + 1
            cause = row["summary"]["primary_cause_of_death"]
            cause_votes[cause] = cause_votes.get(cause, 0) + 1
        points.append({
            "combo": combo,
            "n_seeds": len(config.seeds),
            "mean_lifespan": _mean([r["summary"]["lifespan"] for r in seed_rows.values()]),
            "mean_healthspan": _mean([r["summary"]["healthspan"] for r in seed_rows.values()]),
            "mean_max_cascade": _mean([r["summary"].get("organ_network", {}).get("max_cascade_risk", 0.0)
                                       for r in seed_rows.values()]),
            "binding_votes": binding_votes,
            "cause_votes": cause_votes,
            "seeds": seed_rows,
        })
    boundary: dict[str, Any] = {}
    for axis in axes:
        ordered = sorted(points, key=lambda p: p["combo"][axis])
        reference = max(p["mean_lifespan"] for p in ordered)
        transition = next((p["combo"][axis] for p in ordered
                           if p["mean_lifespan"] < 0.9 * reference), None)
        boundary[axis] = {"reference_mean_lifespan": reference, "transition_budget": transition}
    wall_seconds = round(time.perf_counter() - wall_start, 4)
    return {
        "kind": "resource_sensitivity",
        "experiment_id": config.experiment_id,
        "format": ORGAN_NETWORK_EXPERIMENT_VERSION,
        "config": config.to_config_dict(),
        "config_hash": _config_hash(config.to_config_dict()),
        "model_scope": ORGAN_NETWORK_SCOPE,
        "immortality_status": "hypothesis_not_proven",
        "candidate_robust_bounded_degradation_v4_found": False,
        "seeds": list(config.seeds),
        "points": points,
        "boundary": boundary,
        "runtime": {"engine": "organism-organ-network/v0", "python": platform.python_version(),
                    "platform": platform.platform(), "wall_seconds": wall_seconds},
    }


def run_hard_limit_sensitivity(config: HardLimitSensitivityConfig) -> dict[str, Any]:
    wall_start = time.perf_counter()
    criteria = validate_v4_criteria(dict(config.v4_criteria))
    axes = sorted(config.hard_limit_axes)
    points: list[dict[str, Any]] = []
    for values in itertools.product(*[config.hard_limit_axes[axis] for axis in axes]):
        combo = dict(zip(axes, values))
        seed_rows: dict[str, Any] = {}
        for seed in config.seeds:
            base = copy.deepcopy(config.base_organism_config)
            hard_limits = dict(base.get("organ_network_hard_limits", {}))
            hard_limits.update(combo)
            seed_rows[str(seed)] = _run_one(base, seed,
                                            {"organ_network_hard_limits": hard_limits}, criteria)
        summaries = [row["summary"] for row in seed_rows.values()]
        binding_votes: dict[str, int] = {}
        violation_votes: dict[str, int] = {}
        for row in seed_rows.values():
            binding = row["binding"]["first_network_constraint_violated"]
            binding_votes[binding] = binding_votes.get(binding, 0) + 1
            for limit_id in row["summary"].get("hard_limits", {}).get("failed_hard_limit_ids", []):
                violation_votes[limit_id] = violation_votes.get(limit_id, 0) + 1
        v4 = robust_bounded_degradation_v4(summaries, dict(criteria))
        points.append({
            "combo": combo,
            "n_seeds": len(config.seeds),
            "mean_lifespan": _mean([r["summary"]["lifespan"] for r in seed_rows.values()]),
            "mean_healthspan": _mean([r["summary"]["healthspan"] for r in seed_rows.values()]),
            "robust_v4": v4["robust_bounded_degradation_v4"],
            "binding_votes": binding_votes,
            "violation_votes": violation_votes,
            "seeds": seed_rows,
        })
    wall_seconds = round(time.perf_counter() - wall_start, 4)
    return {
        "kind": "hard_limit_sensitivity",
        "experiment_id": config.experiment_id,
        "format": ORGAN_NETWORK_EXPERIMENT_VERSION,
        "config": config.to_config_dict(),
        "config_hash": _config_hash(config.to_config_dict()),
        "model_scope": ORGAN_NETWORK_SCOPE,
        "immortality_status": "hypothesis_not_proven",
        "candidate_robust_bounded_degradation_v4_found": any(p["robust_v4"] for p in points),
        "seeds": list(config.seeds),
        "points": points,
        "runtime": {"engine": "organism-organ-network/v0", "python": platform.python_version(),
                    "platform": platform.platform(), "wall_seconds": wall_seconds},
    }


def _round6(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, list):
        return [_round6(v) for v in value]
    if isinstance(value, dict):
        return {k: _round6(v) for k, v in value.items()}
    return value


def write_coordination_outputs(result: dict[str, Any], out_prefix: str) -> dict[str, str]:
    parent = os.path.dirname(os.path.abspath(out_prefix))
    os.makedirs(parent, exist_ok=True)
    long_path = f"{out_prefix}_long.csv"
    summary_path = f"{out_prefix}_summary.csv"
    summary_json_path = f"{out_prefix}_summary.json"
    comparison_path = f"{out_prefix}_comparison.json"
    binding_path = f"{out_prefix}_binding_constraints.json"
    long_columns = ("mode", "seed", "lifespan", "healthspan", "primary_cause_of_death",
                    "first_network_constraint", "dominant_binding_level",
                    "max_cascade_risk", "max_mutation_load")
    with open(long_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(long_columns))
        writer.writeheader()
        for mode in sorted(result["modes"]):
            for seed in result["seeds"]:
                row = result["modes"][mode]["seeds"][str(seed)]
                writer.writerow({
                    "mode": mode, "seed": seed,
                    "lifespan": _round6(row["summary"]["lifespan"]),
                    "healthspan": _round6(row["summary"]["healthspan"]),
                    "primary_cause_of_death": row["summary"]["primary_cause_of_death"],
                    "first_network_constraint": row["binding"]["first_network_constraint_violated"],
                    "dominant_binding_level": row["binding"]["dominant_binding_level"],
                    "max_cascade_risk": _round6(
                        row["summary"].get("organ_network", {}).get("max_cascade_risk", 0.0)),
                    "max_mutation_load": _round6(
                        row["summary"].get("organ_network", {}).get("max_mutation_load", 0.0)),
                })
    with open(summary_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["mode", "n_seeds", "mean_lifespan", "mean_healthspan",
                                                "mean_max_cascade", "robust_v4", "binding_votes"])
        writer.writeheader()
        for mode in sorted(result["modes"]):
            block = result["modes"][mode]
            writer.writerow({
                "mode": mode, "n_seeds": block["n_seeds"],
                "mean_lifespan": _round6(block["mean_lifespan"]),
                "mean_healthspan": _round6(block["mean_healthspan"]),
                "mean_max_cascade": _round6(block["mean_max_cascade"]),
                "robust_v4": block["robust_v4"]["robust_bounded_degradation_v4"],
                "binding_votes": json.dumps(block["binding_votes"], sort_keys=True),
            })
    payload = _round6(result)
    with open(summary_json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, allow_nan=False)
    with open(comparison_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": result["experiment_id"], "config_hash": result["config_hash"],
                   "model_scope": result["model_scope"],
                   "immortality_status": result["immortality_status"],
                   "comparison": _round6(result["comparison"])}, fh, ensure_ascii=False,
                  indent=2, allow_nan=False)
    with open(binding_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": result["experiment_id"], "config_hash": result["config_hash"],
                   "binding": {mode: block["binding_votes"] for mode, block in result["modes"].items()}},
                  fh, ensure_ascii=False, indent=2, allow_nan=False)
    for value in [block["mean_lifespan"] for block in result["modes"].values()]:
        if not math.isfinite(float(value)):
            raise ValueError("non-finite coordination output")
    return {"long_csv": long_path, "summary_csv": summary_path, "summary_json": summary_json_path,
            "comparison_json": comparison_path, "binding_constraints_json": binding_path}


def write_sensitivity_outputs(result: dict[str, Any], out_prefix: str) -> dict[str, str]:
    parent = os.path.dirname(os.path.abspath(out_prefix))
    os.makedirs(parent, exist_ok=True)
    long_path = f"{out_prefix}_long.csv"
    summary_path = f"{out_prefix}_summary.csv"
    summary_json_path = f"{out_prefix}_summary.json"
    boundary_path = f"{out_prefix}_boundary.json"
    binding_path = f"{out_prefix}_binding_constraints.json"
    with open(long_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["combo", "seed", "lifespan", "healthspan",
                                                "primary_cause_of_death",
                                                "first_network_constraint",
                                                "max_cascade_risk"])
        writer.writeheader()
        for point in result["points"]:
            for seed in result["seeds"]:
                row = point["seeds"][str(seed)]
                writer.writerow({
                    "combo": json.dumps(point["combo"], sort_keys=True), "seed": seed,
                    "lifespan": _round6(row["summary"]["lifespan"]),
                    "healthspan": _round6(row["summary"]["healthspan"]),
                    "primary_cause_of_death": row["summary"]["primary_cause_of_death"],
                    "first_network_constraint": row["binding"]["first_network_constraint_violated"],
                    "max_cascade_risk": _round6(row["summary"].get("organ_network", {})
                                                .get("max_cascade_risk", 0.0)),
                })
    with open(summary_path, "w", encoding="utf-8", newline="") as fh:
        fieldnames = ["combo", "n_seeds", "mean_lifespan", "mean_healthspan",
                      "binding_votes", "cause_votes"]
        if result["kind"] == "hard_limit_sensitivity":
            fieldnames = ["combo", "n_seeds", "mean_lifespan", "mean_healthspan",
                          "robust_v4", "binding_votes", "violation_votes"]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for point in result["points"]:
            row: dict[str, Any] = {
                "combo": json.dumps(point["combo"], sort_keys=True), "n_seeds": point["n_seeds"],
                "mean_lifespan": _round6(point["mean_lifespan"]),
                "mean_healthspan": _round6(point["mean_healthspan"]),
                "binding_votes": json.dumps(point["binding_votes"], sort_keys=True),
            }
            if result["kind"] == "hard_limit_sensitivity":
                row["robust_v4"] = point["robust_v4"]
                row["violation_votes"] = json.dumps(point.get("violation_votes", {}), sort_keys=True)
            else:
                row["cause_votes"] = json.dumps(point.get("cause_votes", {}), sort_keys=True)
            writer.writerow(row)
    payload = _round6(result)
    with open(summary_json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, allow_nan=False)
    with open(boundary_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": result["experiment_id"], "config_hash": result["config_hash"],
                   "boundary": _round6(result.get("boundary", {}))}, fh, ensure_ascii=False,
                  indent=2, allow_nan=False)
    with open(binding_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": result["experiment_id"], "config_hash": result["config_hash"],
                   "binding": {json.dumps(p["combo"], sort_keys=True): p["binding_votes"]
                               for p in result["points"]}}, fh, ensure_ascii=False,
                  indent=2, allow_nan=False)
    for value in [p["mean_lifespan"] for p in result["points"]]:
        if not math.isfinite(float(value)):
            raise ValueError("non-finite sensitivity output")
    return {"long_csv": long_path, "summary_csv": summary_path, "summary_json": summary_json_path,
            "boundary_json": boundary_path, "binding_constraints_json": binding_path}


def load_organ_network_config(path: str) -> (NetworkCoordinationCompareConfig
                                             | NetworkResourceSensitivityConfig
                                             | HardLimitSensitivityConfig):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    kind = data.get("kind", "")
    if kind == "coordination_compare":
        return NetworkCoordinationCompareConfig.from_config_dict(data)
    if kind == "resource_sensitivity":
        return NetworkResourceSensitivityConfig.from_config_dict(data)
    if kind == "hard_limit_sensitivity":
        return HardLimitSensitivityConfig.from_config_dict(data)
    raise ValueError(f"organ-network config kind must be coordination_compare|resource_sensitivity|"
                     f"hard_limit_sensitivity, got {kind!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Stage 6B organ-network study.")
    parser.add_argument("--config", required=True, help="Organ-network study config JSON")
    parser.add_argument("--out-prefix", default="", help="Output prefix (default: config output_prefix)")
    args = parser.parse_args()
    config = load_organ_network_config(args.config)
    out_prefix = args.out_prefix or config.output_prefix
    if not out_prefix:
        raise ValueError("no out-prefix: pass --out-prefix or set output_prefix in the config")
    if isinstance(config, NetworkCoordinationCompareConfig):
        result = run_coordination_compare(config)
        paths = write_coordination_outputs(result, out_prefix)
        print(f"[coordination {config.experiment_id}] {len(result['modes'])} modes x {len(config.seeds)} seeds")
    elif isinstance(config, NetworkResourceSensitivityConfig):
        result = run_resource_sensitivity(config)
        paths = write_sensitivity_outputs(result, out_prefix)
        print(f"[sensitivity {config.experiment_id}] {len(result['points'])} points x {len(config.seeds)} seeds")
    else:
        result = run_hard_limit_sensitivity(config)
        paths = write_sensitivity_outputs(result, out_prefix)
        print(f"[hard-limit {config.experiment_id}] {len(result['points'])} points x {len(config.seeds)} seeds")
    for key, path in paths.items():
        print(f"[{key}] {path}")


if __name__ == "__main__":
    main()
