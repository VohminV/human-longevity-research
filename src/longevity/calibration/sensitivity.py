"""One-factor-at-a-time sensitivity of population growth to existing parameters.

Scope rule (Stage 3): only parameters that already exist in the model are
swept -- doubling_time_mean, doubling_time_sd, mortality.rate. No new
parameters are introduced to chase a calibration target. The outcome is a
directional statement (which knob dominates growth) feeding the MODEL MISMATCH
discussion, not a fit.

Performance note: unlike the full calibration runs, these runs do NOT build an
hourly series (prohibitively expensive when doubling_time_mean=8h pushes the
population past ~2M cells). Counts at the sampled times are read from the
engine's O(1) living count right after ``run_until``; cleavage timing comes
from the milestone log.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from longevity.biology.params import apply_interventions
from longevity.experiment.config import ExperimentConfig
from longevity.sim.engine import PopulationEngine
from longevity.sim.rng import Rng

RESPONSE_METRICS = ("time_to_8_cell", "cell_count_at_116h", "cell_count_at_168h")

SWEEP_PLAN: dict[str, tuple[float, ...]] = {
    "doubling_time_mean": (8.0, 10.8, 13.0, 16.0, 20.0),
    "doubling_time_sd": (0.0, 1.2, 2.5, 5.0),
    "mortality.rate": (0.0, 0.01, 0.05, 0.10),
}


def _run_seed_responses(
    config: ExperimentConfig,
    seed: int,
    count_times: tuple[int, ...],
) -> dict[str, float | None]:
    engine = PopulationEngine(
        rng=Rng(seed),
        parameters=config.effective_parameters(),
        population=config.population,
        model_version=config.model_version,
        experiment_id=config.experiment_id,
        record_milestones=True,
    )

    counts: dict[str, float] = {}
    for t in sorted(count_times):
        engine.run_until(t)
        counts[f"cell_count_at_{t}h"] = engine.living_count()

    time_to_8 = next((m["sim_time"] for m in engine.milestones if m["live_count"] >= 8), None)
    time_to_4 = next((m["sim_time"] for m in engine.milestones if m["live_count"] >= 4), None)
    time_to_2 = next((m["sim_time"] for m in engine.milestones if m["live_count"] >= 2), None)
    return {**counts, "time_to_2_cell": time_to_2, "time_to_4_cell": time_to_4, "time_to_8_cell": time_to_8}


def run_sensitivity(
    config: ExperimentConfig,
    seeds: tuple[int, ...] = (1, 2, 3),
    sweep_plan: dict[str, tuple[float, ...]] | None = None,
    count_times: tuple[int, ...] = (116, 168),
    response_metrics: tuple[str, ...] = RESPONSE_METRICS,
) -> list[dict[str, Any]]:
    """Sweep each parameter one factor at a time and aggregate the response
    metrics (mean/SD over `seeds`) per combination.

    `response_metrics` selects which extracted responses to aggregate; a metric
    absent from a per-seed result (e.g. a stage never reached) is skipped.
    The default keeps the Stage 3 behaviour; Stage 4 passes the full
    time_to_2/4/8 + 120/144/168h set alongside cell_cycle-phase sweeps.
    """
    plan = sweep_plan if sweep_plan is not None else SWEEP_PLAN
    base_parameters = config.effective_parameters()
    rows: list[dict[str, Any]] = []

    for path, values in plan.items():
        for value in values:
            parameters = apply_interventions(base_parameters, [{"parameter": path, "value": value}])
            per_seed: dict[str, dict[str, float | None]] = {}
            for seed in seeds:
                cfg = replace(config, seed=seed, parameters=parameters)
                per_seed[str(seed)] = _run_seed_responses(cfg, seed, count_times)

            for metric in response_metrics:
                values_by_seed = [row[metric] for row in per_seed.values() if row.get(metric) is not None]
                if not values_by_seed:
                    continue
                mean = sum(values_by_seed) / len(values_by_seed)
                sd = (sum((v - mean) ** 2 for v in values_by_seed) / len(values_by_seed)) ** 0.5
                rows.append(
                    {
                        "parameter": path,
                        "value": value,
                        "metric": metric,
                        "mean": round(mean, 4),
                        "sd": round(sd, 4),
                        "n_seeds": len(values_by_seed),
                    }
                )

    return rows