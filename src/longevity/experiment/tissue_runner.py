"""EXPERIMENT ENGINE LAYER: tissue-replacement experiments (Stage 3A).

Mirrors the conventions of :mod:`longevity.experiment.runner` (config record,
JSON result with trajectory + metrics + summary, runtime block) but drives
:class:`TissueModel` instead of :class:`PopulationEngine`.
"""

from __future__ import annotations

import json
import os
import platform
import time

from dataclasses import dataclass, field
from typing import Any

from longevity.analysis.tissue_metrics import compute_tissue_summary
from longevity.model.policy import ReplacementPolicy
from longevity.model.tissue import (
    TISSUE_MODEL_VERSION,
    TissueModel,
    TissueState,
    assert_tissue_invariants,
    validate_tissue_parameters,
)
from longevity.sim.rng import Rng
from longevity.version import DATA_VERSION

TISSUE_ENGINE_VERSION = "tissue-engine/v0"
TISSUE_RESULT_FORMAT_VERSION = "1.0"


@dataclass(frozen=True)
class TissueExperimentConfig:
    """Complete, self-describing tissue-experiment configuration."""

    experiment_id: str
    seed: int
    steps: int
    model_version: str = TISSUE_MODEL_VERSION
    data_version: str = DATA_VERSION
    initial_state: dict[str, Any] = field(default_factory=dict)
    tissue_parameters: dict[str, Any] = field(default_factory=dict)
    policy: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id must be non-empty")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise ValueError("seed must be an int")
        if not isinstance(self.steps, int) or isinstance(self.steps, bool) or self.steps < 0:
            raise ValueError("steps must be a non-negative int")
        if not self.model_version:
            raise ValueError("model_version must be non-empty")
        if not self.data_version:
            raise ValueError("data_version must be non-empty")
        if not isinstance(self.initial_state, dict):
            raise ValueError("initial_state must be a dict")
        if not isinstance(self.tissue_parameters, dict):
            raise ValueError("tissue_parameters must be a dict")
        if not isinstance(self.policy, dict):
            raise ValueError("policy must be a dict")
        validate_tissue_parameters(self.tissue_parameters)
        assert_tissue_invariants(TissueState.from_dict(self.initial_state))
        ReplacementPolicy.from_dict(self.policy)

    def to_config_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "seed": self.seed,
            "steps": self.steps,
            "model_version": self.model_version,
            "data_version": self.data_version,
            "initial_state": TissueState.from_dict(self.initial_state).to_dict(),
            "tissue_parameters": validate_tissue_parameters(dict(self.tissue_parameters)),
            "policy": ReplacementPolicy.from_dict(self.policy).to_dict(),
            "notes": self.notes,
        }

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "TissueExperimentConfig":
        return cls(
            experiment_id=data["experiment_id"],
            seed=data["seed"],
            steps=data["steps"],
            model_version=data.get("model_version", TISSUE_MODEL_VERSION),
            data_version=data.get("data_version", DATA_VERSION),
            initial_state=data.get("initial_state", {}),
            tissue_parameters=data.get("tissue_parameters", {}),
            policy=data.get("policy", {}),
            notes=data.get("notes", ""),
        )


def run_tissue_experiment(
    config: TissueExperimentConfig, out_path: str | None = None
) -> dict[str, Any]:
    """Run a tissue experiment and return (and optionally persist) a result.

    Result schema: ``experiment_id`` / ``config`` / ``trajectory`` (t0 first) /
    ``metrics`` (final summary per Stage 3A) / ``runtime`` / ``rng_summary``.
    """
    wall_start = time.perf_counter()

    rng = Rng(config.seed)
    model = TissueModel(
        state=TissueState.from_dict(config.initial_state),
        parameters=validate_tissue_parameters(dict(config.tissue_parameters)),
        rng=rng,
    )
    policy = ReplacementPolicy.from_dict(config.policy)

    trajectory = model.run(config.steps, policy)
    dt = float(model.parameters["dt"])
    metrics = compute_tissue_summary(
        trajectory,
        dt,
        model.replacement_events,
        model.total_replaced_cells,
    )
    wall_seconds = round(time.perf_counter() - wall_start, 4)

    result: dict[str, Any] = {
        "experiment_id": config.experiment_id,
        "config": config.to_config_dict(),
        "trajectory": trajectory,
        "metrics": {"format": TISSUE_RESULT_FORMAT_VERSION, "final": metrics},
        "summary": {
            "final_functional_cells": metrics["final_functional_cells"],
            "final_senescent_cells": metrics["final_senescent_cells"],
            "total_replaced_cells": metrics["total_replaced_cells"],
            "max_cancer_risk": metrics["max_cancer_risk"],
        },
        "runtime": {
            "engine": TISSUE_ENGINE_VERSION,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "wall_seconds": wall_seconds,
        },
        "rng_summary": {"seed": config.seed, "rng_seed_confirmed": model.rng.seed == config.seed},
    }

    if out_path is not None:
        parent = os.path.dirname(os.path.abspath(out_path))
        os.makedirs(parent, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)

    return result


def load_tissue_config(path: str) -> TissueExperimentConfig:
    """Read a tissue experiment JSON file into a validated config."""
    with open(path, encoding="utf-8") as fh:
        return TissueExperimentConfig.from_config_dict(json.load(fh))
