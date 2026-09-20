"""Stage 4 calibration driver: developmental cell-cycle dynamics (A/B/C).

Compares three model variants plus a lengthening control against the
preimplantation reference targets (Istanbul timing S-7, Hardy counts S-6):

- Model A: Stage 3 minimal baseline, unchanged (control arm).
- Model B: count-based cell-cycle phases (zygotic / cleavage / post-EGA).
- Model B_fast: Model B without post-EGA lengthening (isolates the lengthening
  factor).
- Model C: Model B plus per-division death at the post-8-cell phase.

Every model runs the same number of seeds; predictions are EXPECTED, never
tuned to the reference targets. A one-factor-at-a-time sweep over the
cell_cycle phase parameters (built on Model B) reports which knobs move the
responses, mirroring the Stage 3 sensitivity requirement.

Outputs:
- raw per-seed results    -> experiments/output/calibration/<tag>/  (gitignored)
- committed summary+sweep -> experiments/reports/<tag>/

Usage:
    python experiments/run_stage4.py [--seeds 20] [--tag v2]
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

# Responses swept in Stage 4: timing of all three cleavage stages plus the
# Hardy blastocyst counts.
STAGE4_RESPONSE_METRICS = (
    "time_to_2_cell",
    "time_to_4_cell",
    "time_to_8_cell",
    "cell_count_at_120h",
    "cell_count_at_144h",
    "cell_count_at_168h",
)

# One-factor-at-a-time plan over the cell_cycle phase parameters. Swept on top
# of Model B (the phases list must already exist: apply_interventions can index
# into a list but not synthesize one).
STAGE4_SWEEP_PLAN: dict[str, tuple[float, ...]] = {
    "cell_cycle.phases.1.mean": (14.0, 17.0, 20.0, 24.0),
    "cell_cycle.phases.2.mean": (17.0, 24.0, 32.0, 40.0),
    "cell_cycle.phases.2.threshold": (8.0, 16.0, 32.0),
    "cell_cycle.phases.2.sd": (0.0, 3.0, 6.0, 12.0),
    "cell_cycle.phases.2.death_per_division": (0.0, 0.05, 0.10, 0.20),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Stage 4 developmental cell-cycle calibration.")
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--sensitivity-seeds", type=int, default=4)
    parser.add_argument("--tag", default="v2")
    parser.add_argument(
        "--configs",
        nargs="*",
        default=["stage4_model_a", "stage4_model_b", "stage4_model_b_fast", "stage4_model_c"],
    )
    args = parser.parse_args()

    seeds = tuple(range(1, args.seeds + 1))
    sens_seeds = tuple(range(1, args.sensitivity_seeds + 1))

    out_base = os.path.join(_REPO_ROOT, "experiments", "output", "calibration", args.tag)
    report_dir = os.path.join(_REPO_ROOT, "experiments", "reports", args.tag)
    os.makedirs(out_base, exist_ok=True)
    os.makedirs(report_dir, exist_ok=True)

    for name in args.configs:
        raw = _read_config(name)
        raw["seed"] = seeds[0]
        config = _make_config(raw)

        report = run_multiseed_calibration(config, seeds=seeds, cell_count_times=(120, 144, 168))
        _write_json(os.path.join(report_dir, f"{name}_summary_{args.tag}.json"), report)
        for seed in seeds:
            from longevity.calibration.multirun import run_seed_calibration

            seed_result = run_seed_calibration(config, seed)
            _write_json(os.path.join(out_base, name, f"seed_{seed:02d}.json"), seed_result)

        print(f"[{name}] wrote summary for {len(seeds)} seeds -> {report['comparisons']}")

    sweep_base = _make_config(_read_config("stage4_model_b"))
    sweep = run_sensitivity(
        sweep_base,
        seeds=sens_seeds,
        sweep_plan=STAGE4_SWEEP_PLAN,
        count_times=(120, 144, 168),
        response_metrics=STAGE4_RESPONSE_METRICS,
    )
    sweep_report = {"tag": args.tag, "base_model": "stage4_model_b", "seeds": list(sens_seeds), "rows": sweep}
    _write_json(os.path.join(report_dir, f"stage4_sweep_{args.tag}.json"), sweep_report)
    print(f"[sweep] {len(sweep)} rows -> {os.path.join(report_dir, f'stage4_sweep_{args.tag}.json')}")


def _read_config(name: str) -> dict[str, Any]:
    with open(os.path.join(CONFIG_DIR, f"{name}.json"), encoding="utf-8") as fh:
        return json.load(fh)


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