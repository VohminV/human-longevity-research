from __future__ import annotations

import json
import os
import platform
import time

from typing import Any

from longevity.analysis.metrics import experiment_summary, population_metrics
from longevity.experiment.config import ExperimentConfig
from longevity.sim.engine import PopulationEngine
from longevity.sim.rng import Rng

ENGINE_VERSION = "population-engine/v0"
RESULT_FORMAT_VERSION = "1.0"


def run_experiment(config: ExperimentConfig, out_path: str | None = None) -> dict[str, Any]:
    """Run a configured experiment and return (and optionally persist) a result
    record whose schema follows docs/EXPERIMENTS.md."""
    wall_start = time.perf_counter()

    rng = Rng(config.seed)
    engine = PopulationEngine(
        rng=rng,
        parameters=config.effective_parameters(),
        population=config.population,
        interventions=[],
        model_version=config.model_version,
        experiment_id=config.experiment_id,
    )

    series: list[dict[str, Any]] = []
    interval = config.metrics_config.get("sample_interval")
    if interval is not None:
        t = 0.0
        while t <= config.duration:
            engine.run_until(t)
            series.append(population_metrics(engine))
            t += interval

    engine.run_until(config.duration)
    engine.assert_invariants()
    final_metrics = population_metrics(engine)
    wall_seconds = round(time.perf_counter() - wall_start, 4)

    result: dict[str, Any] = {
        "experiment_id": config.experiment_id,
        "config": config.to_config_dict(),
        "metrics": {
            "format": RESULT_FORMAT_VERSION,
            "series": series,
            "final": final_metrics,
        },
        "summary": experiment_summary(final_metrics),
        "runtime": {
            "engine": ENGINE_VERSION,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "wall_seconds": wall_seconds,
        },
        "rng_summary": {"seed": config.seed, "rng_seed_confirmed": engine.rng.seed == config.seed},
    }

    if out_path is not None:
        parent = os.path.dirname(os.path.abspath(out_path))
        os.makedirs(parent, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2, default=_json_default)

    return result


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (tuple, set)):
        return list(obj)
    raise TypeError(f"not JSON serializable: {type(obj)}")