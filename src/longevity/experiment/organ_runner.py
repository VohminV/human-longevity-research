"""EXPERIMENT ENGINE LAYER: abstract-organ experiments (Stage 4A).

Mirrors the conventions of :mod:`longevity.experiment.tissue_runner`
(config record, JSON result with trajectory + metrics + summary, runtime
block) but drives :class:`OrganModel` instead of :class:`TissueModel`.

CLI::

    PYTHONPATH=src python -m longevity.experiment.organ_runner \\
        --config experiments/configs/organ_baseline.json \\
        --out experiments/output/organ_baseline.json
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import time

from typing import Any

from longevity.analysis.organ_metrics import compute_organ_summary
from longevity.model.organ import MODEL_SCOPE, ORGAN_MODEL_VERSION, OrganConfig, OrganModel
from longevity.version import DATA_VERSION

ORGAN_ENGINE_VERSION = "organ-engine/v0"
ORGAN_RESULT_FORMAT_VERSION = "1.0"


def load_organ_config(path: str) -> OrganConfig:
    """Read an organ experiment JSON file into a validated config."""
    with open(path, encoding="utf-8") as fh:
        return OrganConfig.from_config_dict(json.load(fh))


def run_organ_experiment(config: OrganConfig, out_path: str | None = None) -> dict[str, Any]:
    """Run an organ experiment and return (and optionally persist) a result.

    Result schema: ``organ_id`` / ``model_scope`` / ``config`` /
    ``trajectory`` (t0 first) / ``metrics`` (final summary per Stage 4A) /
    ``summary`` (headline numbers) / ``runtime`` / ``rng_summary``.
    """
    wall_start = time.perf_counter()

    organ = OrganModel(config)
    trajectory = organ.run(config.steps)
    dt = float(config.dt)
    duration_time = float(config.steps) * dt
    summary = compute_organ_summary(trajectory, dt, duration_time, dict(organ.thresholds))
    wall_seconds = round(time.perf_counter() - wall_start, 4)

    result: dict[str, Any] = {
        "organ_id": config.organ_id,
        "model_scope": MODEL_SCOPE,
        "config": config.to_config_dict(),
        "trajectory": trajectory,
        "metrics": {"format": ORGAN_RESULT_FORMAT_VERSION, "final": summary},
        "summary": {
            "final_organ_function": summary["final_organ_function"],
            "time_to_organ_viability_failure": summary["time_to_organ_viability_failure"],
            "organ_healthspan_proxy": summary["organ_healthspan_proxy"],
            "primary_organ_failure_cause": summary["primary_organ_failure_cause"],
            "bottleneck_tissue_final": summary["bottleneck_tissue_final"],
            "min_vascular_allocation_ratio": summary["min_vascular_allocation_ratio"],
            "min_immune_allocation_ratio": summary["min_immune_allocation_ratio"],
            "final_vascular_capacity": summary["capacity"]["final_vascular_capacity"],
            "final_immune_capacity": summary["capacity"]["final_immune_capacity"],
        },
        "runtime": {
            "engine": ORGAN_ENGINE_VERSION,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "wall_seconds": wall_seconds,
        },
        "rng_summary": {
            "seed": config.seed,
            "per_tissue_seeds": [config.seed + index for index in range(len(config.tissues))],
        },
    }

    if out_path is not None:
        parent = os.path.dirname(os.path.abspath(out_path))
        os.makedirs(parent, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Stage 4A abstract-organ experiment.")
    parser.add_argument("--config", required=True, help="Organ config JSON (e.g. experiments/configs/organ_baseline.json)")
    parser.add_argument(
        "--out",
        default="",
        help="Output JSON path (default: experiments/output/<organ_id>.json)",
    )
    args = parser.parse_args()

    config = load_organ_config(args.config)
    out_path = args.out or f"experiments/output/{config.organ_id}.json"
    result = run_organ_experiment(config, out_path=out_path)
    print(f"[organ {config.organ_id}] {config.steps} steps x {len(config.tissues)} tissues (seed {config.seed})")
    print(f"[organ_function] final={result['summary']['final_organ_function']:.4f} "
          f"ttf={result['summary']['time_to_organ_viability_failure']:.1f} "
          f"cause={result['summary']['primary_organ_failure_cause']} "
          f"bottleneck={result['summary']['bottleneck_tissue_final']}")
    print(f"[out] {out_path}")


if __name__ == "__main__":
    main()
