"""Stage 3 calibration driver.

Runs the preimplantation calibration experiments over a set of seeds and writes:
- raw per-seed results under `experiments/output/calibration/<tag>/` (gitignored)
- committed summary + sensitivity reports under `experiments/reports/<tag>/`

Usage:
    python experiments/run_calibration.py [--seeds 20] [--tag v1]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))

from longevity.calibration.multirun import run_multiseed_calibration  # noqa: E402
from longevity.calibration.sensitivity import run_sensitivity  # noqa: E402

CONFIG_DIR = os.path.join(_REPO_ROOT, "experiments", "configs")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Stage 3 preimplantation calibration.")
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--sensitivity-seeds", type=int, default=4)
    parser.add_argument("--tag", default="v1")
    parser.add_argument("--configs", nargs="*", default=["early_development_baseline", "blastocyst_calibration"])
    args = parser.parse_args()

    seeds = tuple(range(1, args.seeds + 1))
    sens_seeds = tuple(range(1, args.sensitivity_seeds + 1))

    out_base = os.path.join(_REPO_ROOT, "experiments", "output", "calibration", args.tag)
    report_dir = os.path.join(_REPO_ROOT, "experiments", "reports", args.tag)
    os.makedirs(out_base, exist_ok=True)
    os.makedirs(report_dir, exist_ok=True)

    for name in args.configs:
        with open(os.path.join(CONFIG_DIR, f"{name}.json"), encoding="utf-8") as fh:
            raw = json.load(fh)
        raw["seed"] = seeds[0]
        config = _make_config(raw)

        report = run_multiseed_calibration(config, seeds=seeds)
        _write_json(os.path.join(report_dir, f"{name}_summary_{args.tag}.json"), report)

        for seed in seeds:
            from dataclasses import replace

            from longevity.calibration.multirun import run_seed_calibration

            seed_result = run_seed_calibration(config, seed)
            _write_json(os.path.join(out_base, name, f"seed_{seed:02d}.json"), seed_result)

        print(f"[{name}] wrote summary for {len(seeds)} seeds -> {report['comparisons']}")

    sensitivity = run_sensitivity(_make_config_from_file("early_development_baseline"), seeds=sens_seeds)
    sensitivity_report = {"tag": args.tag, "seeds": list(sens_seeds), "rows": sensitivity}
    _write_json(os.path.join(report_dir, f"sensitivity_{args.tag}.json"), sensitivity_report)
    print(f"[sensitivity] {len(sensitivity)} rows -> {os.path.join(report_dir, f'sensitivity_{args.tag}.json')}")


def _make_config_from_file(name: str) -> Any:
    with open(os.path.join(CONFIG_DIR, f"{name}.json"), encoding="utf-8") as fh:
        return _make_config(json.load(fh))


def _make_config(raw: dict[str, Any]) -> Any:
    from longevity.biology.params import validate_parameters
    from longevity.experiment.config import ExperimentConfig
    from longevity.version import DATA_VERSION, MODEL_VERSION

    parameters = validate_parameters(raw.get("parameters", {}))
    return ExperimentConfig(
        experiment_id=raw["experiment_id"],
        seed=int(raw["seed"]),
        population=raw.get("population", 1),
        duration=float(raw["duration"]),
        model_version=MODEL_VERSION,
        data_version=DATA_VERSION,
        parameters=parameters,
        interventions=raw.get("interventions", []),
        metrics_config=raw.get("metrics_config", {}),
        notes=raw.get("notes", ""),
    )


def _write_json(path: str, payload: dict[str, Any]) -> None:
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()