from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from longevity.biology.params import apply_interventions, validate_parameters


@dataclass(frozen=True)
class ExperimentConfig:
    """Complete, self-describing experiment configuration (see docs/EXPERIMENTS.md)."""

    experiment_id: str
    seed: int
    population: int
    duration: float
    model_version: str
    data_version: str
    parameters: dict[str, Any] = field(default_factory=dict)
    interventions: list[dict[str, Any]] = field(default_factory=list)
    metrics_config: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id must be non-empty")
        if not isinstance(self.seed, int):
            raise ValueError("seed must be an int")
        if self.population < 1:
            raise ValueError("population must be >= 1")
        if self.duration < 0:
            raise ValueError("duration must be >= 0")
        if not self.model_version:
            raise ValueError("model_version must be non-empty")
        if not self.data_version:
            raise ValueError("data_version must be non-empty")
        if not isinstance(self.parameters, dict):
            raise ValueError("parameters must be a dict")
        validate_parameters(self.parameters)
        for intervention in self.interventions:
            if not isinstance(intervention, dict) or "parameter" not in intervention or "value" not in intervention:
                raise ValueError(f"intervention must be {{'parameter', 'value'}}: {intervention!r}")
        if not isinstance(self.metrics_config, dict):
            raise ValueError("metrics_config must be a dict")
        interval = self.metrics_config.get("sample_interval")
        if interval is not None and (not isinstance(interval, (int, float)) or isinstance(interval, bool) or interval <= 0):
            raise ValueError("metrics_config.sample_interval must be a positive number")

    def effective_parameters(self) -> dict[str, Any]:
        return apply_interventions(self.parameters, self.interventions)

    def to_config_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "seed": self.seed,
            "population": self.population,
            "duration": self.duration,
            "model_version": self.model_version,
            "data_version": self.data_version,
            "parameters": self.parameters,
            "effective_parameters": self.effective_parameters(),
            "interventions": self.interventions,
            "metrics_config": self.metrics_config,
            "notes": self.notes,
        }

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "ExperimentConfig":
        return cls(
            experiment_id=data["experiment_id"],
            seed=data["seed"],
            population=data["population"],
            duration=data["duration"],
            model_version=data["model_version"],
            data_version=data["data_version"],
            parameters=data.get("parameters", {}),
            interventions=data.get("interventions", []),
            metrics_config=data.get("metrics_config", {}),
            notes=data.get("notes", ""),
        )