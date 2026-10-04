"""EXPERIMENT ENGINE LAYER: mechanistic binding-driver sweep (Stage 5C).

Grid over aging-driver parameters (base rates, reversibility,
contributions, couplings) reusing :func:`run_organism_experiment` (no
dynamics duplicated). Finds which driver binds under which parameters;
small deterministic grids, never a full stability map.

CLI::

    PYTHONPATH=src python -m longevity.experiment.organism_aging \\
        --config experiments/configs/organism_aging_binding_driver_sweep.json \\
        --out-prefix experiments/output/organism_aging_binding_driver_sweep
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

from longevity.analysis.aging_metrics import (
    reversal_efficiency,
    summarize_drivers,
    validate_v2_criteria,
)
from longevity.experiment.organism_runner import OrganismExperimentConfig, run_organism_experiment
from longevity.model.aging import AGING_DRIVERS, validate_aging_drivers
from longevity.model.organism import MODEL_SCOPE, ORGANISM_MODEL_VERSION

AGING_SWEEP_FORMAT_VERSION = "1.0"
MIN_AGING_SEEDS = 2


def _require_seeds(seeds: Any) -> tuple[int, ...]:
    if not isinstance(seeds, (list, tuple)) or len(seeds) == 0:
        raise ValueError("aging sweep seeds must be a non-empty list")
    cleaned = []
    for seed in seeds:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError(f"aging sweep seed must be an int, got {seed!r}")
        cleaned.append(seed)
    if len(set(cleaned)) != len(cleaned):
        raise ValueError("aging sweep seeds must be unique")
    if len(cleaned) < MIN_AGING_SEEDS:
        raise ValueError(f"aging sweep needs at least {MIN_AGING_SEEDS} seeds, got {len(cleaned)}")
    return tuple(cleaned)


@dataclass(frozen=True)
class AgingDriverSweepConfig:
    """Complete, self-describing binding-driver sweep configuration."""

    experiment_id: str
    seeds: tuple[int, ...] = ()
    driver_axes: dict[str, list] = field(default_factory=dict)
    base_organism_config: dict[str, Any] = field(default_factory=dict)
    output_prefix: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id must be non-empty")
        _require_seeds(list(self.seeds))
        if not isinstance(self.driver_axes, dict) or not self.driver_axes:
            raise ValueError("driver_axes must be a non-empty dict of driver.param -> values")
        for axis, values in self.driver_axes.items():
            parts = axis.split(".")
            if len(parts) != 2 or parts[0] not in AGING_DRIVERS:
                raise ValueError(f"driver axis must be '<driver>.<param>' with known driver, got {axis!r}")
            validate_aging_drivers({parts[0]: {parts[1]: v} for v in values} if values else {parts[0]: {}})
            if not isinstance(values, list) or not values:
                raise ValueError(f"driver_axes[{axis!r}] must be a non-empty list")
        if not isinstance(self.base_organism_config, dict) or not self.base_organism_config:
            raise ValueError("base_organism_config must be a non-empty dict")
        base = copy.deepcopy(self.base_organism_config)
        base.setdefault("aging_mechanism_model", "mechanistic_drivers")
        OrganismExperimentConfig.from_config_dict(base)

    def to_config_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "seeds": list(self.seeds),
            "driver_axes": copy.deepcopy(self.driver_axes),
            "base_organism_config": copy.deepcopy(self.base_organism_config),
            "output_prefix": self.output_prefix,
            "notes": self.notes,
        }

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "AgingDriverSweepConfig":
        return cls(
            experiment_id=data["experiment_id"],
            seeds=tuple(data.get("seeds", ())),
            driver_axes=copy.deepcopy(data.get("driver_axes", {})),
            base_organism_config=copy.deepcopy(data.get("base_organism_config", {})),
            output_prefix=data.get("output_prefix", ""),
            notes=data.get("notes", ""),
        )


def aging_sweep_config_hash(config: AgingDriverSweepConfig) -> str:
    canonical = json.dumps(config.to_config_dict(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _mean(values: list[float]) -> float:
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        raise ValueError("cannot average empty/non-finite data")
    return sum(finite) / len(finite)


def run_aging_sweep(config: AgingDriverSweepConfig) -> dict[str, Any]:
    """Run the driver-parameter grid over all seeds (deterministic)."""
    wall_start = time.perf_counter()
    axes = sorted(config.driver_axes)
    points: list[dict[str, Any]] = []
    for values in itertools.product(*[config.driver_axes[axis] for axis in axes]):
        combo = dict(zip(axes, values))
        seed_rows: dict[str, Any] = {}
        for seed in config.seeds:
            data = copy.deepcopy(config.base_organism_config)
            data["seed"] = seed
            data.setdefault("aging_mechanism_model", "mechanistic_drivers")
            drivers = dict(data.get("aging_drivers", {}))
            for axis, value in combo.items():
                driver, param = axis.split(".", 1)
                entry = dict(drivers.get(driver, {}))
                entry[param] = value
                drivers[driver] = entry
            data["aging_drivers"] = drivers
            experiment = OrganismExperimentConfig.from_config_dict(data)
            result = run_organism_experiment(experiment, out_path=None)
            summary = result["metrics"]["final"]
            driver_block = summarize_drivers(
                result["trajectory"],
                summary.get("drivers", {}).get("biological_age_component_contributions"))
            reversal = reversal_efficiency(result["trajectory"])
            seed_rows[str(seed)] = {"summary": summary, "drivers": driver_block, "reversal": reversal}
        dominant_votes: dict[str, int] = {}
        for row in seed_rows.values():
            dominant = row["drivers"]["dominant_binding_driver"]
            dominant_votes[dominant] = dominant_votes.get(dominant, 0) + 1
        points.append({
            "combo": combo,
            "n_seeds": len(config.seeds),
            "mean_lifespan": _mean([r["summary"]["lifespan"] for r in seed_rows.values()]),
            "mean_healthspan": _mean([r["summary"]["healthspan"] for r in seed_rows.values()]),
            "mean_worst_driver_slope": _mean([r["drivers"]["worst_driver_slope"] for r in seed_rows.values()]),
            "dominant_binding_driver": sorted(dominant_votes, key=lambda d: (-dominant_votes[d], d))[0],
            "dominant_votes": dominant_votes,
            "mean_reversal_events": _mean([r["drivers"]["age_reversal_events"] for r in seed_rows.values()]),
            "seeds": seed_rows,
        })
    wall_seconds = round(time.perf_counter() - wall_start, 4)
    return {
        "experiment_id": config.experiment_id,
        "format": AGING_SWEEP_FORMAT_VERSION,
        "config": config.to_config_dict(),
        "config_hash": aging_sweep_config_hash(config),
        "model_scope": MODEL_SCOPE,
        "immortality_status": "hypothesis_not_proven",
        "seeds": list(config.seeds),
        "points": points,
        "runtime": {
            "engine": "organism-aging-sweep/v0",
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
    "seed", "combo", "lifespan", "healthspan", "primary_cause_of_death",
    "dominant_binding_driver", "worst_driver_slope", "age_reversal_events",
    "total_age_reversal_delta",
)


def write_aging_sweep_outputs(result: dict[str, Any], out_prefix: str) -> dict[str, str]:
    """Write long CSV, summary CSV/JSON, binding drivers, reversal, top-K JSON."""
    parent = os.path.dirname(os.path.abspath(out_prefix))
    os.makedirs(parent, exist_ok=True)
    long_path = f"{out_prefix}_long.csv"
    summary_path = f"{out_prefix}_summary.csv"
    summary_json_path = f"{out_prefix}_summary.json"
    binding_path = f"{out_prefix}_binding_drivers.json"
    reversal_path = f"{out_prefix}_reversal_efficiency.json"
    top_k_path = f"{out_prefix}_top_k.json"
    pareto_path = f"{out_prefix}_pareto_front.json"

    long_rows = []
    for point in result["points"]:
        for seed in result["seeds"]:
            row = point["seeds"][str(seed)]
            long_rows.append({
                "seed": seed,
                "combo": json.dumps(point["combo"], sort_keys=True),
                "lifespan": _round6(row["summary"]["lifespan"]),
                "healthspan": _round6(row["summary"]["healthspan"]),
                "primary_cause_of_death": row["summary"]["primary_cause_of_death"],
                "dominant_binding_driver": row["drivers"]["dominant_binding_driver"],
                "worst_driver_slope": _round6(row["drivers"]["worst_driver_slope"]),
                "age_reversal_events": row["drivers"]["age_reversal_events"],
                "total_age_reversal_delta": _round6(row["drivers"]["total_age_reversal_delta"]),
            })
    with open(long_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(LONG_COLUMNS))
        writer.writeheader()
        writer.writerows(long_rows)

    summary_fieldnames = ["combo", "n_seeds", "mean_lifespan", "mean_healthspan",
                          "mean_worst_driver_slope", "dominant_binding_driver",
                          "dominant_votes", "mean_reversal_events"]
    with open(summary_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=summary_fieldnames)
        writer.writeheader()
        for point in result["points"]:
            writer.writerow({
                "combo": json.dumps(point["combo"], sort_keys=True),
                "n_seeds": point["n_seeds"],
                "mean_lifespan": _round6(point["mean_lifespan"]),
                "mean_healthspan": _round6(point["mean_healthspan"]),
                "mean_worst_driver_slope": _round6(point["mean_worst_driver_slope"]),
                "dominant_binding_driver": point["dominant_binding_driver"],
                "dominant_votes": json.dumps(point["dominant_votes"], sort_keys=True),
                "mean_reversal_events": _round6(point["mean_reversal_events"]),
            })
    with open(summary_json_path, "w", encoding="utf-8") as fh:
        json.dump(_round6(result), fh, ensure_ascii=False, indent=2, allow_nan=False)
    binding_all: dict[str, Any] = {}
    for point in result["points"]:
        binding_all[json.dumps(point["combo"], sort_keys=True)] = {
            "dominant_binding_driver": point["dominant_binding_driver"],
            "dominant_votes": point["dominant_votes"],
        }
    with open(binding_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": result["experiment_id"], "config_hash": result["config_hash"],
                   "binding_drivers": binding_all}, fh, ensure_ascii=False, indent=2, allow_nan=False)
    reversal_all: dict[str, Any] = {}
    for point in result["points"]:
        per_seed = {}
        for seed in result["seeds"]:
            per_seed[str(seed)] = point["seeds"][str(seed)]["reversal"]
        reversal_all[json.dumps(point["combo"], sort_keys=True)] = per_seed
    with open(reversal_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": result["experiment_id"], "config_hash": result["config_hash"],
                   "reversal_efficiency": _round6(reversal_all)}, fh, ensure_ascii=False, indent=2, allow_nan=False)
    ranked = sorted(result["points"],
                    key=lambda p: (-p["mean_healthspan"], -p["mean_lifespan"],
                                   json.dumps(p["combo"], sort_keys=True)))
    with open(top_k_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": result["experiment_id"], "config_hash": result["config_hash"],
                   "top_k": _round6([{k: p[k] for k in ("combo", "mean_lifespan", "mean_healthspan",
                                                        "mean_worst_driver_slope", "dominant_binding_driver")}
                                     for p in ranked[:5]])}, fh, ensure_ascii=False, indent=2, allow_nan=False)
    with open(pareto_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": result["experiment_id"], "config_hash": result["config_hash"],
                   "note": "driver-space pareto is reported via top_k ranking; "
                           "policy-space pareto lives in policy-search artifacts"},
                  fh, ensure_ascii=False, indent=2, allow_nan=False)
    for value in [row["lifespan"] for row in long_rows]:
        if not math.isfinite(float(value)):
            raise ValueError("non-finite aging sweep output")
    return {"long_csv": long_path, "summary_csv": summary_path, "summary_json": summary_json_path,
            "binding_drivers_json": binding_path, "reversal_efficiency_json": reversal_path,
            "top_k_json": top_k_path, "pareto_front_json": pareto_path}


def load_aging_sweep_config(path: str) -> AgingDriverSweepConfig:
    """Read a binding-driver sweep JSON file into a validated config."""
    with open(path, encoding="utf-8") as fh:
        return AgingDriverSweepConfig.from_config_dict(json.load(fh))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Stage 5C binding-driver sweep.")
    parser.add_argument("--config", required=True, help="Aging sweep config JSON")
    parser.add_argument("--out-prefix", default="", help="Output prefix (default: config output_prefix)")
    args = parser.parse_args()
    config = load_aging_sweep_config(args.config)
    out_prefix = args.out_prefix or config.output_prefix
    if not out_prefix:
        raise ValueError("no out-prefix: pass --out-prefix or set output_prefix in the config")
    result = run_aging_sweep(config)
    paths = write_aging_sweep_outputs(result, out_prefix)
    print(f"[aging sweep {config.experiment_id}] {len(result['points'])} points x {len(config.seeds)} seeds")
    for key, path in paths.items():
        print(f"[{key}] {path}")


if __name__ == "__main__":
    main()
