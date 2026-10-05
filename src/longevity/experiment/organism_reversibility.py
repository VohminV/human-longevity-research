"""EXPERIMENT ENGINE LAYER: reversibility coordination/sensitivity studies (Stage 6C).

Four config kinds (dispatched on the ``kind`` field):

- ``coordination_compare``: one reversibility base config run under each
  reversibility-aware coordination mode.
- ``repair_ceiling_sensitivity``: grid over ``repair_ceiling`` values.
- ``conversion_sensitivity``: grid over ``base_conversion_rate`` values.
- ``information_mutation_sensitivity``: grid over information / mutation /
  niche / entropy parameter values.

CLI::

    PYTHONPATH=src python -m longevity.experiment.organism_reversibility \\
        --config experiments/configs/organism_reversibility_coordination_compare.json \\
        --out-prefix experiments/output/organism_reversibility_coordination_compare
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

from longevity.analysis.reversibility_metrics import (
    reversibility_binding,
    robust_bounded_degradation_v5,
    validate_v5_criteria,
)
from longevity.experiment.organism_runner import OrganismExperimentConfig, run_organism_experiment
from longevity.model.reversibility import (
    REVERSIBILITY_SCOPE,
    validate_reversibility_params,
)

REVERSIBILITY_EXPERIMENT_VERSION = "1.0"
MIN_REVERSIBILITY_SEEDS = 2

REPAIR_CEILING_AXES = ("repair_ceiling",)
CONVERSION_AXES = ("base_conversion_rate",)
INFO_MUTATION_AXES = (
    "max_information_debt",
    "max_mutation_fixation",
    "max_niche_disorder",
    "repair_ceiling",
)


def _require_seeds(seeds: Any) -> tuple[int, ...]:
    if not isinstance(seeds, (list, tuple)) or len(seeds) == 0:
        raise ValueError("reversibility seeds must be a non-empty list")
    cleaned = []
    for seed in seeds:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError(f"reversibility seed must be an int, got {seed!r}")
        cleaned.append(seed)
    if len(set(cleaned)) != len(cleaned):
        raise ValueError("reversibility seeds must be unique")
    if len(cleaned) < MIN_REVERSIBILITY_SEEDS:
        raise ValueError(
            f"reversibility studies need at least {MIN_REVERSIBILITY_SEEDS} seeds, got {len(cleaned)}")
    return tuple(cleaned)


def _require_reversibility_base(base: dict[str, Any]) -> None:
    if not isinstance(base, dict) or not base:
        raise ValueError("base_organism_config must be a non-empty dict")
    if base.get("reversibility_model", "none") != "split_reversible_irreversible":
        raise ValueError("reversibility studies require base_organism_config with "
                         "reversibility_model=split_reversible_irreversible")
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
    binding = reversibility_binding(result["trajectory"], dict(criteria))
    return {"summary": summary, "binding": binding}


@dataclass(frozen=True)
class ReversibilityCoordinationCompareConfig:
    experiment_id: str
    seeds: tuple[int, ...] = ()
    coordination_modes: tuple[str, ...] = ()
    base_organism_config: dict[str, Any] = field(default_factory=dict)
    v5_criteria: dict[str, Any] = field(default_factory=dict)
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
        _require_reversibility_base(copy.deepcopy(self.base_organism_config))
        validate_v5_criteria(dict(self.v5_criteria))

    def to_config_dict(self) -> dict[str, Any]:
        return {
            "kind": "coordination_compare",
            "experiment_id": self.experiment_id,
            "seeds": list(self.seeds),
            "coordination_modes": list(self.coordination_modes),
            "base_organism_config": copy.deepcopy(self.base_organism_config),
            "v5_criteria": copy.deepcopy(dict(self.v5_criteria)),
            "output_prefix": self.output_prefix,
            "notes": self.notes,
        }

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "ReversibilityCoordinationCompareConfig":
        return cls(
            experiment_id=data["experiment_id"],
            seeds=tuple(data.get("seeds", ())),
            coordination_modes=tuple(data.get("coordination_modes", ())),
            base_organism_config=copy.deepcopy(data.get("base_organism_config", {})),
            v5_criteria=copy.deepcopy(data.get("v5_criteria", {})),
            output_prefix=data.get("output_prefix", ""),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True)
class ReversibilitySensitivityConfig:
    kind: str = "repair_ceiling_sensitivity"
    experiment_id: str = ""
    seeds: tuple[int, ...] = ()
    param_axes: dict[str, list] = field(default_factory=dict)
    base_organism_config: dict[str, Any] = field(default_factory=dict)
    v5_criteria: dict[str, Any] = field(default_factory=dict)
    output_prefix: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id must be non-empty")
        _require_seeds(list(self.seeds))
        if self.kind == "repair_ceiling_sensitivity":
            allowed = set(REPAIR_CEILING_AXES)
        elif self.kind == "conversion_sensitivity":
            allowed = set(CONVERSION_AXES)
        elif self.kind == "information_mutation_sensitivity":
            allowed = set(INFO_MUTATION_AXES)
        else:
            raise ValueError(f"unknown sensitivity kind {self.kind!r}")
        if not isinstance(self.param_axes, dict) or not self.param_axes:
            raise ValueError("param_axes must be a non-empty dict of param -> values")
        for param, values in self.param_axes.items():
            if param not in allowed:
                raise ValueError(f"param axis must be one of {sorted(allowed)}, got {param!r}")
            if not isinstance(values, list) or not values:
                raise ValueError(f"param_axes[{param!r}] must be a non-empty list")
            validate_reversibility_params({param: v for v in values} if values else {})
        _require_reversibility_base(copy.deepcopy(self.base_organism_config))
        validate_v5_criteria(dict(self.v5_criteria))

    def to_config_dict(self) -> dict[str, Any]:
        key = "repair_ceiling_axes" if self.kind == "repair_ceiling_sensitivity" \
            else "conversion_axes" if self.kind == "conversion_sensitivity" \
            else "info_mutation_axes"
        return {
            "kind": self.kind,
            "experiment_id": self.experiment_id,
            "seeds": list(self.seeds),
            key: copy.deepcopy(self.param_axes),
            "base_organism_config": copy.deepcopy(self.base_organism_config),
            "v5_criteria": copy.deepcopy(dict(self.v5_criteria)),
            "output_prefix": self.output_prefix,
            "notes": self.notes,
        }

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "ReversibilitySensitivityConfig":
        kind = data.get("kind", "")
        if kind == "repair_ceiling_sensitivity":
            axes = copy.deepcopy(data.get("repair_ceiling_axes", {}))
        elif kind == "conversion_sensitivity":
            axes = copy.deepcopy(data.get("conversion_axes", {}))
        elif kind == "information_mutation_sensitivity":
            axes = copy.deepcopy(data.get("info_mutation_axes", {}))
        else:
            raise ValueError(f"unknown sensitivity kind {kind!r}")
        return cls(
            kind=kind,
            experiment_id=data["experiment_id"],
            seeds=tuple(data.get("seeds", ())),
            param_axes=axes,
            base_organism_config=copy.deepcopy(data.get("base_organism_config", {})),
            v5_criteria=copy.deepcopy(data.get("v5_criteria", {})),
            output_prefix=data.get("output_prefix", ""),
            notes=data.get("notes", ""),
        )


def _config_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def run_coordination_compare(config: ReversibilityCoordinationCompareConfig) -> dict[str, Any]:
    wall_start = time.perf_counter()
    criteria = validate_v5_criteria(dict(config.v5_criteria))
    modes_block: dict[str, Any] = {}
    for mode in sorted(config.coordination_modes):
        seed_rows: dict[str, Any] = {}
        for seed in config.seeds:
            seed_rows[str(seed)] = _run_one(copy.deepcopy(config.base_organism_config), seed,
                                            {"coordination_mode": mode}, criteria)
        summaries = [row["summary"] for row in seed_rows.values()]
        v5 = robust_bounded_degradation_v5(summaries, dict(criteria))
        binding_votes: dict[str, int] = {}
        for row in seed_rows.values():
            key = row["binding"]["first_reversibility_constraint_violated"]
            binding_votes[key] = binding_votes.get(key, 0) + 1
        modes_block[mode] = {
            "n_seeds": len(config.seeds),
            "mean_lifespan": _mean([r["summary"]["lifespan"] for r in seed_rows.values()]),
            "mean_healthspan": _mean([r["summary"]["healthspan"] for r in seed_rows.values()]),
            "mean_irreversible_slope": _mean([
                r["summary"].get("reversibility", {}).get("worst_irreversible_slope", 0.0)
                for r in seed_rows.values()]),
            "robust_v5": v5,
            "binding_votes": binding_votes,
            "coordination_stats": {str(seed): row["summary"].get("reversibility_coordination_stats", {})
                                   for seed, row in seed_rows.items()},
            "seeds": seed_rows,
        }
    independent = modes_block.get("independent_reversibility", {})
    comparison = {}
    for mode, block in modes_block.items():
        if mode == "independent_reversibility" or not independent:
            comparison[mode] = {"lifespan_gain_vs_independent_reversibility": 0.0,
                                "healthspan_gain_vs_independent_reversibility": 0.0}
        else:
            comparison[mode] = {
                "lifespan_gain_vs_independent_reversibility":
                    block["mean_lifespan"] - independent["mean_lifespan"],
                "healthspan_gain_vs_independent_reversibility":
                    block["mean_healthspan"] - independent["mean_healthspan"],
            }
    wall_seconds = round(time.perf_counter() - wall_start, 4)
    return {
        "kind": "coordination_compare",
        "experiment_id": config.experiment_id,
        "format": REVERSIBILITY_EXPERIMENT_VERSION,
        "config": config.to_config_dict(),
        "config_hash": _config_hash(config.to_config_dict()),
        "model_scope": REVERSIBILITY_SCOPE,
        "immortality_status": "hypothesis_not_proven",
        "candidate_robust_bounded_degradation_v5_found": any(
            block["robust_v5"]["robust_bounded_degradation_v5"] for block in modes_block.values()),
        "seeds": list(config.seeds),
        "modes": modes_block,
        "comparison": comparison,
        "runtime": {"engine": "organism-reversibility/v0", "python": platform.python_version(),
                    "platform": platform.platform(), "wall_seconds": wall_seconds},
    }


def run_sensitivity(config: ReversibilitySensitivityConfig) -> dict[str, Any]:
    wall_start = time.perf_counter()
    criteria = validate_v5_criteria(dict(config.v5_criteria))
    axes = sorted(config.param_axes)
    points: list[dict[str, Any]] = []
    for values in itertools.product(*[config.param_axes[axis] for axis in axes]):
        combo = dict(zip(axes, values))
        seed_rows: dict[str, Any] = {}
        for seed in config.seeds:
            base = copy.deepcopy(config.base_organism_config)
            params = dict(base.get("reversibility_params", {}))
            params.update(combo)
            seed_rows[str(seed)] = _run_one(base, seed,
                                            {"reversibility_params": params}, criteria)
        summaries = [row["summary"] for row in seed_rows.values()]
        binding_votes: dict[str, int] = {}
        cause_votes: dict[str, int] = {}
        for row in seed_rows.values():
            binding = row["binding"]["first_reversibility_constraint_violated"]
            binding_votes[binding] = binding_votes.get(binding, 0) + 1
            cause = row["summary"]["primary_cause_of_death"]
            cause_votes[cause] = cause_votes.get(cause, 0) + 1
        v5 = robust_bounded_degradation_v5(summaries, dict(criteria))
        points.append({
            "combo": combo,
            "n_seeds": len(config.seeds),
            "mean_lifespan": _mean([r["summary"]["lifespan"] for r in seed_rows.values()]),
            "mean_healthspan": _mean([r["summary"]["healthspan"] for r in seed_rows.values()]),
            "mean_irreversible_slope": _mean([
                r["summary"].get("reversibility", {}).get("worst_irreversible_slope", 0.0)
                for r in seed_rows.values()]),
            "robust_v5": v5["robust_bounded_degradation_v5"],
            "binding_votes": binding_votes,
            "cause_votes": cause_votes,
            "seeds": seed_rows,
        })
    wall_seconds = round(time.perf_counter() - wall_start, 4)
    return {
        "kind": config.kind,
        "experiment_id": config.experiment_id,
        "format": REVERSIBILITY_EXPERIMENT_VERSION,
        "config": config.to_config_dict(),
        "config_hash": _config_hash(config.to_config_dict()),
        "model_scope": REVERSIBILITY_SCOPE,
        "immortality_status": "hypothesis_not_proven",
        "candidate_robust_bounded_degradation_v5_found": any(p["robust_v5"] for p in points),
        "seeds": list(config.seeds),
        "points": points,
        "runtime": {"engine": "organism-reversibility/v0", "python": platform.python_version(),
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
    binding_path = f"{out_prefix}_binding_reversibility.json"
    long_columns = ("mode", "seed", "lifespan", "healthspan", "primary_cause_of_death",
                    "first_reversibility_constraint", "dominant_binding_level",
                    "worst_irreversible_slope", "conversion_rate")
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
                    "first_reversibility_constraint":
                        row["binding"]["first_reversibility_constraint_violated"],
                    "dominant_binding_level": row["binding"]["dominant_binding_level"],
                    "worst_irreversible_slope": _round6(
                        row["summary"].get("reversibility", {}).get("worst_irreversible_slope", 0.0)),
                    "conversion_rate": _round6(
                        row["summary"].get("reversibility", {}).get("conversion_rate", 0.0)),
                })
    with open(summary_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["mode", "n_seeds", "mean_lifespan", "mean_healthspan",
                                                "mean_irreversible_slope", "robust_v5",
                                                "binding_votes"])
        writer.writeheader()
        for mode in sorted(result["modes"]):
            block = result["modes"][mode]
            writer.writerow({
                "mode": mode, "n_seeds": block["n_seeds"],
                "mean_lifespan": _round6(block["mean_lifespan"]),
                "mean_healthspan": _round6(block["mean_healthspan"]),
                "mean_irreversible_slope": _round6(block["mean_irreversible_slope"]),
                "robust_v5": block["robust_v5"]["robust_bounded_degradation_v5"],
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
            "comparison_json": comparison_path, "binding_reversibility_json": binding_path}


def write_sensitivity_outputs(result: dict[str, Any], out_prefix: str) -> dict[str, str]:
    parent = os.path.dirname(os.path.abspath(out_prefix))
    os.makedirs(parent, exist_ok=True)
    long_path = f"{out_prefix}_long.csv"
    summary_path = f"{out_prefix}_summary.csv"
    summary_json_path = f"{out_prefix}_summary.json"
    binding_path = f"{out_prefix}_binding_reversibility.json"
    with open(long_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["combo", "seed", "lifespan", "healthspan",
                                                "primary_cause_of_death",
                                                "first_reversibility_constraint",
                                                "worst_irreversible_slope"])
        writer.writeheader()
        for point in result["points"]:
            for seed in result["seeds"]:
                row = point["seeds"][str(seed)]
                writer.writerow({
                    "combo": json.dumps(point["combo"], sort_keys=True), "seed": seed,
                    "lifespan": _round6(row["summary"]["lifespan"]),
                    "healthspan": _round6(row["summary"]["healthspan"]),
                    "primary_cause_of_death": row["summary"]["primary_cause_of_death"],
                    "first_reversibility_constraint":
                        row["binding"]["first_reversibility_constraint_violated"],
                    "worst_irreversible_slope": _round6(row["summary"].get("reversibility", {})
                                                        .get("worst_irreversible_slope", 0.0)),
                })
    with open(summary_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["combo", "n_seeds", "mean_lifespan", "mean_healthspan",
                                                "mean_irreversible_slope", "robust_v5",
                                                "binding_votes", "cause_votes"])
        writer.writeheader()
        for point in result["points"]:
            writer.writerow({
                "combo": json.dumps(point["combo"], sort_keys=True), "n_seeds": point["n_seeds"],
                "mean_lifespan": _round6(point["mean_lifespan"]),
                "mean_healthspan": _round6(point["mean_healthspan"]),
                "mean_irreversible_slope": _round6(point["mean_irreversible_slope"]),
                "robust_v5": point["robust_v5"],
                "binding_votes": json.dumps(point["binding_votes"], sort_keys=True),
                "cause_votes": json.dumps(point["cause_votes"], sort_keys=True),
            })
    payload = _round6(result)
    with open(summary_json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, allow_nan=False)
    with open(binding_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": result["experiment_id"], "config_hash": result["config_hash"],
                   "binding": {json.dumps(p["combo"], sort_keys=True): p["binding_votes"]
                               for p in result["points"]}}, fh, ensure_ascii=False,
                  indent=2, allow_nan=False)
    for value in [p["mean_lifespan"] for p in result["points"]]:
        if not math.isfinite(float(value)):
            raise ValueError("non-finite sensitivity output")
    return {"long_csv": long_path, "summary_csv": summary_path, "summary_json": summary_json_path,
            "binding_reversibility_json": binding_path}


def load_reversibility_config(path: str) -> (ReversibilityCoordinationCompareConfig
                                             | ReversibilitySensitivityConfig):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    kind = data.get("kind", "")
    if kind == "coordination_compare":
        return ReversibilityCoordinationCompareConfig.from_config_dict(data)
    if kind in ("repair_ceiling_sensitivity", "conversion_sensitivity",
                "information_mutation_sensitivity"):
        return ReversibilitySensitivityConfig.from_config_dict(data)
    raise ValueError(f"reversibility config kind must be coordination_compare|repair_ceiling_sensitivity|"
                     f"conversion_sensitivity|information_mutation_sensitivity, got {kind!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Stage 6C reversibility study.")
    parser.add_argument("--config", required=True, help="Reversibility study config JSON")
    parser.add_argument("--out-prefix", default="", help="Output prefix (default: config output_prefix)")
    args = parser.parse_args()
    config = load_reversibility_config(args.config)
    out_prefix = args.out_prefix or config.output_prefix
    if not out_prefix:
        raise ValueError("no out-prefix: pass --out-prefix or set output_prefix in the config")
    if isinstance(config, ReversibilityCoordinationCompareConfig):
        result = run_coordination_compare(config)
        paths = write_coordination_outputs(result, out_prefix)
        print(f"[coordination {config.experiment_id}] {len(result['modes'])} modes x {len(config.seeds)} seeds")
    else:
        result = run_sensitivity(config)
        paths = write_sensitivity_outputs(result, out_prefix)
        print(f"[{config.kind} {config.experiment_id}] {len(result['points'])} points x {len(config.seeds)} seeds")
    for key, path in paths.items():
        print(f"[{key}] {path}")


if __name__ == "__main__":
    main()
