"""EXPERIMENT ENGINE LAYER: irreversibility boundary probe studies (Stage 6D).

Four config kinds (dispatched on the ``kind`` field), all sweeping
``boundary_params`` over a reversibility base config:

- ``conversion_ultra_sweep``: grid over ``conversion_scale``.
- ``independent_ultra_sweep``: grid over ``independent_accrual_scale``.
- ``ceiling_ultra_sweep``: grid over ``repair_ceiling_scale`` (+ optional
  unlimited-ceiling ablation point).
- ``component_attribution``: single-point detailed decomposition runs
  (default + key ablations) with contribution reports.

CLI::

    PYTHONPATH=src python -m longevity.experiment.organism_boundary \\
        --config experiments/configs/organism_reversibility_boundary_conversion_ultra_sweep.json \\
        --out-prefix experiments/output/organism_reversibility_boundary_conversion_ultra_sweep
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

from longevity.analysis.boundary_metrics import (
    classify_wall,
    summarize_boundary_run,
)
from longevity.analysis.reversibility_metrics import (
    reversibility_binding,
    robust_bounded_degradation_v5,
    validate_v5_criteria,
)
from longevity.experiment.organism_runner import OrganismExperimentConfig, run_organism_experiment
from longevity.model.boundary import (
    BOUNDARY_SCOPE,
    validate_boundary_params,
)

BOUNDARY_EXPERIMENT_VERSION = "1.0"
MIN_BOUNDARY_SEEDS = 2

KIND_TO_PARAM = {
    "conversion_ultra_sweep": ("conversion_scale",),
    "independent_ultra_sweep": ("independent_accrual_scale",),
    "ceiling_ultra_sweep": ("repair_ceiling_scale",),
}


def _require_seeds(seeds: Any) -> tuple[int, ...]:
    if not isinstance(seeds, (list, tuple)) or len(seeds) == 0:
        raise ValueError("boundary seeds must be a non-empty list")
    cleaned = []
    for seed in seeds:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError(f"boundary seed must be an int, got {seed!r}")
        cleaned.append(seed)
    if len(set(cleaned)) != len(cleaned):
        raise ValueError("boundary seeds must be unique")
    if len(cleaned) < MIN_BOUNDARY_SEEDS:
        raise ValueError(
            f"boundary studies need at least {MIN_BOUNDARY_SEEDS} seeds, got {len(cleaned)}")
    return tuple(cleaned)


def _require_boundary_base(base: dict[str, Any]) -> None:
    if not isinstance(base, dict) or not base:
        raise ValueError("base_organism_config must be a non-empty dict")
    if base.get("reversibility_model", "none") != "split_reversible_irreversible":
        raise ValueError("boundary studies require base_organism_config with "
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
    # Boundary sweeps force the ablation layer on (neutral unless params differ).
    if data.get("boundary_probe_model", "none") == "none":
        data["boundary_probe_model"] = "irreversibility_ablation"
    experiment = OrganismExperimentConfig.from_config_dict(data)
    result = run_organism_experiment(experiment, out_path=None)
    summary = result["metrics"]["final"]
    binding = reversibility_binding(result["trajectory"], dict(criteria))
    boundary = summarize_boundary_run(result["trajectory"])
    return {"summary": summary, "binding": binding, "boundary": boundary}


@dataclass(frozen=True)
class BoundarySweepConfig:
    kind: str = "conversion_ultra_sweep"
    experiment_id: str = ""
    seeds: tuple[int, ...] = ()
    param_axes: dict[str, list] = field(default_factory=dict)
    extra_boundary_params: dict[str, Any] = field(default_factory=dict)
    base_organism_config: dict[str, Any] = field(default_factory=dict)
    v5_criteria: dict[str, Any] = field(default_factory=dict)
    output_prefix: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KIND_TO_PARAM:
            raise ValueError(f"boundary sweep kind must be one of {sorted(KIND_TO_PARAM)}, "
                             f"got {self.kind!r}")
        if not self.experiment_id:
            raise ValueError("experiment_id must be non-empty")
        _require_seeds(list(self.seeds))
        allowed = set(KIND_TO_PARAM[self.kind])
        if not isinstance(self.param_axes, dict) or not self.param_axes:
            raise ValueError("param_axes must be a non-empty dict of param -> values")
        for param, values in self.param_axes.items():
            if param not in allowed:
                raise ValueError(f"param axis must be one of {sorted(allowed)}, got {param!r}")
            if not isinstance(values, list) or not values:
                raise ValueError(f"param_axes[{param!r}] must be a non-empty list")
            validate_boundary_params({param: v for v in values} if values else {})
        validate_boundary_params(dict(self.extra_boundary_params or {}))
        _require_boundary_base(copy.deepcopy(self.base_organism_config))
        validate_v5_criteria(dict(self.v5_criteria))

    def to_config_dict(self) -> dict[str, Any]:
        key = {"conversion_ultra_sweep": "conversion_axes",
               "independent_ultra_sweep": "independent_axes",
               "ceiling_ultra_sweep": "ceiling_axes"}[self.kind]
        return {
            "kind": self.kind,
            "experiment_id": self.experiment_id,
            "seeds": list(self.seeds),
            key: copy.deepcopy(self.param_axes),
            "extra_boundary_params": copy.deepcopy(dict(self.extra_boundary_params)),
            "base_organism_config": copy.deepcopy(self.base_organism_config),
            "v5_criteria": copy.deepcopy(dict(self.v5_criteria)),
            "output_prefix": self.output_prefix,
            "notes": self.notes,
        }

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "BoundarySweepConfig":
        kind = data.get("kind", "")
        if kind not in KIND_TO_PARAM:
            raise ValueError(f"boundary sweep kind must be one of {sorted(KIND_TO_PARAM)}, "
                             f"got {kind!r}")
        key = {"conversion_ultra_sweep": "conversion_axes",
               "independent_ultra_sweep": "independent_axes",
               "ceiling_ultra_sweep": "ceiling_axes"}[kind]
        return cls(
            kind=kind,
            experiment_id=data["experiment_id"],
            seeds=tuple(data.get("seeds", ())),
            param_axes=copy.deepcopy(data.get(key, {})),
            extra_boundary_params=copy.deepcopy(data.get("extra_boundary_params", {})),
            base_organism_config=copy.deepcopy(data.get("base_organism_config", {})),
            v5_criteria=copy.deepcopy(data.get("v5_criteria", {})),
            output_prefix=data.get("output_prefix", ""),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True)
class ComponentAttributionConfig:
    experiment_id: str = ""
    seeds: tuple[int, ...] = ()
    ablations: dict[str, Any] = field(default_factory=dict)
    base_organism_config: dict[str, Any] = field(default_factory=dict)
    v5_criteria: dict[str, Any] = field(default_factory=dict)
    output_prefix: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id must be non-empty")
        _require_seeds(list(self.seeds))
        if not isinstance(self.ablations, dict) or not self.ablations:
            raise ValueError("ablations must be a non-empty dict of name -> boundary_params")
        for name, params in self.ablations.items():
            validate_boundary_params(dict(params))
        _require_boundary_base(copy.deepcopy(self.base_organism_config))
        validate_v5_criteria(dict(self.v5_criteria))

    def to_config_dict(self) -> dict[str, Any]:
        return {
            "kind": "component_attribution",
            "experiment_id": self.experiment_id,
            "seeds": list(self.seeds),
            "ablations": copy.deepcopy(self.ablations),
            "base_organism_config": copy.deepcopy(self.base_organism_config),
            "v5_criteria": copy.deepcopy(dict(self.v5_criteria)),
            "output_prefix": self.output_prefix,
            "notes": self.notes,
        }

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "ComponentAttributionConfig":
        if data.get("kind", "") != "component_attribution":
            raise ValueError(f"component attribution kind mismatch, got {data.get('kind')!r}")
        return cls(
            experiment_id=data["experiment_id"],
            seeds=tuple(data.get("seeds", ())),
            ablations=copy.deepcopy(data.get("ablations", {})),
            base_organism_config=copy.deepcopy(data.get("base_organism_config", {})),
            v5_criteria=copy.deepcopy(data.get("v5_criteria", {})),
            output_prefix=data.get("output_prefix", ""),
            notes=data.get("notes", ""),
        )


def _config_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def run_boundary_sweep(config: BoundarySweepConfig) -> dict[str, Any]:
    wall_start = time.perf_counter()
    criteria = validate_v5_criteria(dict(config.v5_criteria))
    axes = sorted(config.param_axes)
    points: list[dict[str, Any]] = []
    for values in itertools.product(*[config.param_axes[axis] for axis in axes]):
        combo = dict(zip(axes, values))
        seed_rows: dict[str, Any] = {}
        for seed in config.seeds:
            params = dict(config.extra_boundary_params)
            params.update(combo)
            seed_rows[str(seed)] = _run_one(copy.deepcopy(config.base_organism_config), seed,
                                            {"boundary_params": params}, criteria)
        summaries = [row["summary"] for row in seed_rows.values()]
        from longevity.analysis.reversibility_metrics import robust_bounded_degradation_v5

        v5 = robust_bounded_degradation_v5(summaries, dict(criteria))
        binding_votes: dict[str, int] = {}
        source_votes: dict[str, int] = {}
        for row in seed_rows.values():
            binding = row["binding"]["first_reversibility_constraint_violated"]
            binding_votes[binding] = binding_votes.get(binding, 0) + 1
            source = row["boundary"]["attribution"]["dominant_irreversibility_source"]
            source_votes[source] = source_votes.get(source, 0) + 1
        points.append({
            "combo": combo,
            "n_seeds": len(config.seeds),
            "mean_lifespan": _mean([r["summary"]["lifespan"] for r in seed_rows.values()]),
            "mean_healthspan": _mean([r["summary"]["healthspan"] for r in seed_rows.values()]),
            "mean_irreversible_slope": _mean([
                r["summary"].get("reversibility", {}).get("worst_irreversible_slope", 0.0)
                for r in seed_rows.values()]),
            "robust_v5": v5["robust_bounded_degradation_v5"],
            "success_rate_v5": v5["success_rate_bounded_v5"],
            "binding_votes": binding_votes,
            "source_votes": source_votes,
            "seeds": seed_rows,
        })
    # Threshold: first combo (ascending by first axis) where v5 turns true.
    first_axis = axes[0]
    ordered = sorted(points, key=lambda p: p["combo"][first_axis])
    threshold = next((p["combo"][first_axis] for p in ordered if p["robust_v5"]), None)
    wall_seconds = round(time.perf_counter() - wall_start, 4)
    return {
        "kind": config.kind,
        "experiment_id": config.experiment_id,
        "format": BOUNDARY_EXPERIMENT_VERSION,
        "config": config.to_config_dict(),
        "config_hash": _config_hash(config.to_config_dict()),
        "model_scope": BOUNDARY_SCOPE,
        "immortality_status": "hypothesis_not_proven",
        "candidate_robust_bounded_degradation_v5_found": any(p["robust_v5"] for p in points),
        "v5_threshold": threshold,
        "seeds": list(config.seeds),
        "points": points,
        "runtime": {"engine": "organism-boundary/v0", "python": platform.python_version(),
                    "platform": platform.platform(), "wall_seconds": wall_seconds},
    }


def run_component_attribution(config: ComponentAttributionConfig) -> dict[str, Any]:
    wall_start = time.perf_counter()
    criteria = validate_v5_criteria(dict(config.v5_criteria))
    entries: dict[str, Any] = {}
    for name in sorted(config.ablations):
        params = dict(config.ablations[name])
        seed_rows: dict[str, Any] = {}
        for seed in config.seeds:
            seed_rows[str(seed)] = _run_one(copy.deepcopy(config.base_organism_config), seed,
                                            {"boundary_params": params}, criteria)
        summaries = [row["summary"] for row in seed_rows.values()]
        from longevity.analysis.reversibility_metrics import robust_bounded_degradation_v5

        v5 = robust_bounded_degradation_v5(summaries, dict(criteria))
        entries[name] = {
            "n_seeds": len(config.seeds),
            "mean_lifespan": _mean([r["summary"]["lifespan"] for r in seed_rows.values()]),
            "mean_irreversible_slope": _mean([
                r["summary"].get("reversibility", {}).get("worst_irreversible_slope", 0.0)
                for r in seed_rows.values()]),
            "robust_v5": v5["robust_bounded_degradation_v5"],
            "dominant_components": {
                str(seed): row["boundary"]["contributions"].get(
                    "dominant_irreversibility_component", "none")
                for seed, row in seed_rows.items()},
            "dominant_sources": {
                str(seed): row["boundary"]["attribution"].get(
                    "dominant_irreversibility_source", "none")
                for seed, row in seed_rows.items()},
            "seeds": seed_rows,
        }
    # Wall classification across ablations.
    verdicts = {
        "conversion_zero": entries.get("conversion_zero", {}).get("robust_v5", False),
        "independent_zero": entries.get("independent_zero", {}).get("robust_v5", False),
        "both_suppressed": entries.get("both_suppressed", {}).get("robust_v5", False),
        "high_ceiling": entries.get("high_ceiling", {}).get("robust_v5", False),
        "unlimited_ceiling": entries.get("unlimited_ceiling", {}).get("robust_v5", False),
    }
    default_entry = entries.get("default", {})
    default_sources: dict[str, int] = {}
    for seed_row in default_entry.get("seeds", {}).values():
        src = seed_row["boundary"]["attribution"]["dominant_irreversibility_source"]
        default_sources[src] = default_sources.get(src, 0) + 1
    dominant_source = sorted(default_sources,
                             key=lambda k: (-default_sources[k], k))[0] if default_sources else "none"
    classification = classify_wall(
        any(entries[n].get("robust_v5", False) for n in ("default",) if n in entries),
        verdicts, dominant_source)
    wall_seconds = round(time.perf_counter() - wall_start, 4)
    return {
        "kind": "component_attribution",
        "experiment_id": config.experiment_id,
        "format": BOUNDARY_EXPERIMENT_VERSION,
        "config": config.to_config_dict(),
        "config_hash": _config_hash(config.to_config_dict()),
        "model_scope": BOUNDARY_SCOPE,
        "immortality_status": "hypothesis_not_proven",
        "candidate_robust_bounded_degradation_v5_found": any(
            e["robust_v5"] for e in entries.values()),
        "verdicts": verdicts,
        "wall_classification": classification,
        "seeds": list(config.seeds),
        "entries": entries,
        "runtime": {"engine": "organism-boundary/v0", "python": platform.python_version(),
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


def write_sweep_outputs(result: dict[str, Any], out_prefix: str) -> dict[str, str]:
    parent = os.path.dirname(os.path.abspath(out_prefix))
    os.makedirs(parent, exist_ok=True)
    long_path = f"{out_prefix}_long.csv"
    summary_path = f"{out_prefix}_summary.csv"
    summary_json_path = f"{out_prefix}_summary.json"
    report_path = f"{out_prefix}_report.json"
    with open(long_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["combo", "seed", "lifespan", "healthspan",
                                                "primary_cause_of_death",
                                                "first_reversibility_constraint",
                                                "dominant_source",
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
                    "dominant_source":
                        row["boundary"]["attribution"]["dominant_irreversibility_source"],
                    "worst_irreversible_slope": _round6(row["summary"].get("reversibility", {})
                                                        .get("worst_irreversible_slope", 0.0)),
                })
    with open(summary_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["combo", "n_seeds", "mean_lifespan", "mean_healthspan",
                                                "mean_irreversible_slope", "robust_v5",
                                                "binding_votes", "source_votes"])
        writer.writeheader()
        for point in result["points"]:
            writer.writerow({
                "combo": json.dumps(point["combo"], sort_keys=True), "n_seeds": point["n_seeds"],
                "mean_lifespan": _round6(point["mean_lifespan"]),
                "mean_healthspan": _round6(point["mean_healthspan"]),
                "mean_irreversible_slope": _round6(point["mean_irreversible_slope"]),
                "robust_v5": point["robust_v5"],
                "binding_votes": json.dumps(point["binding_votes"], sort_keys=True),
                "source_votes": json.dumps(point["source_votes"], sort_keys=True),
            })
    payload = _round6(result)
    with open(summary_json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, allow_nan=False)
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": result["experiment_id"], "config_hash": result["config_hash"],
                   "model_scope": result["model_scope"],
                   "immortality_status": result["immortality_status"],
                   "candidate_robust_bounded_degradation_v5_found":
                       result["candidate_robust_bounded_degradation_v5_found"],
                   "v5_threshold": result.get("v5_threshold")}, fh, ensure_ascii=False,
                  indent=2, allow_nan=False)
    for value in [p["mean_lifespan"] for p in result["points"]]:
        if not math.isfinite(float(value)):
            raise ValueError("non-finite boundary output")
    return {"long_csv": long_path, "summary_csv": summary_path, "summary_json": summary_json_path,
            "report_json": report_path}


def write_attribution_outputs(result: dict[str, Any], out_prefix: str) -> dict[str, str]:
    parent = os.path.dirname(os.path.abspath(out_prefix))
    os.makedirs(parent, exist_ok=True)
    summary_json_path = f"{out_prefix}_summary.json"
    attribution_path = f"{out_prefix}_component_attribution.json"
    wall_path = f"{out_prefix}_wall_classification.json"
    payload = _round6(result)
    with open(summary_json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, allow_nan=False)
    with open(attribution_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": result["experiment_id"], "config_hash": result["config_hash"],
                   "entries": {name: {
                       "mean_lifespan": _round6(e["mean_lifespan"]),
                       "mean_irreversible_slope": _round6(e["mean_irreversible_slope"]),
                       "robust_v5": e["robust_v5"],
                       "dominant_components": e["dominant_components"],
                       "dominant_sources": e["dominant_sources"]}
                       for name, e in result["entries"].items()}},
                  fh, ensure_ascii=False, indent=2, allow_nan=False)
    with open(wall_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": result["experiment_id"], "config_hash": result["config_hash"],
                   "model_scope": result["model_scope"],
                   "immortality_status": result["immortality_status"],
                   "verdicts": result["verdicts"],
                   "wall_classification": result["wall_classification"]},
                  fh, ensure_ascii=False, indent=2, allow_nan=False)
    return {"summary_json": summary_json_path, "component_attribution_json": attribution_path,
            "wall_classification_json": wall_path}


def load_boundary_config(path: str) -> BoundarySweepConfig | ComponentAttributionConfig:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    kind = data.get("kind", "")
    if kind in KIND_TO_PARAM:
        return BoundarySweepConfig.from_config_dict(data)
    if kind == "component_attribution":
        return ComponentAttributionConfig.from_config_dict(data)
    raise ValueError(f"boundary config kind must be one of {sorted(KIND_TO_PARAM) + ['component_attribution']}, "
                     f"got {kind!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Stage 6D boundary probe study.")
    parser.add_argument("--config", required=True, help="Boundary study config JSON")
    parser.add_argument("--out-prefix", default="", help="Output prefix (default: config output_prefix)")
    args = parser.parse_args()
    config = load_boundary_config(args.config)
    out_prefix = args.out_prefix or config.output_prefix
    if not out_prefix:
        raise ValueError("no out-prefix: pass --out-prefix or set output_prefix in the config")
    if isinstance(config, BoundarySweepConfig):
        result = run_boundary_sweep(config)
        paths = write_sweep_outputs(result, out_prefix)
        print(f"[{config.kind} {config.experiment_id}] {len(result['points'])} points x {len(config.seeds)} seeds")
    else:
        result = run_component_attribution(config)
        paths = write_attribution_outputs(result, out_prefix)
        print(f"[attribution {config.experiment_id}] {len(result['entries'])} ablations x {len(config.seeds)} seeds")
    for key, path in paths.items():
        print(f"[{key}] {path}")


if __name__ == "__main__":
    main()
