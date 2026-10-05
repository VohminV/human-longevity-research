"""EXPERIMENT ENGINE LAYER: organism life-course experiments (Stage 5A).

Mirrors tissue/organ runner conventions (config record, JSON result with
trajectory + metrics + summary, runtime block) but drives
:class:`OrganismModel` with a :class:`PolicySet`.

CLI::

    PYTHONPATH=src python -m longevity.experiment.organism_runner \\
        --config experiments/configs/organism_life_course_baseline.json \\
        --out experiments/output/organism_baseline.json
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import time

from dataclasses import dataclass, field
from typing import Any

from longevity.analysis.organism_metrics import compute_organism_summary
from longevity.model.intervention import PolicySet
from longevity.model.organism import (
    MODEL_SCOPE,
    ORGANISM_MODEL_VERSION,
    OrganismModel,
    OrganismState,
    assert_organism_invariants,
    validate_organism_parameters,
    validate_organism_thresholds,
    validate_perturbation,
    validate_stage_bounds,
)
from longevity.sim.rng import Rng
from longevity.version import DATA_VERSION

ORGANISM_ENGINE_VERSION = "organism-engine/v0"
ORGANISM_RESULT_FORMAT_VERSION = "1.0"


@dataclass(frozen=True)
class OrganismExperimentConfig:
    """Complete, self-describing organism life-course configuration."""

    organism_id: str
    seed: int
    duration_years: float = 150.0
    dt: float = 0.25
    model_version: str = ORGANISM_MODEL_VERSION
    data_version: str = DATA_VERSION
    initial_state: dict[str, Any] = field(default_factory=dict)
    organism_parameters: dict[str, Any] = field(default_factory=dict)
    stage_bounds: dict[str, Any] = field(default_factory=dict)
    thresholds: dict[str, Any] = field(default_factory=dict)
    policies: list = field(default_factory=list)
    bounded_epsilon: float = 0.01
    perturbation: dict[str, Any] = field(default_factory=dict)
    aging_mechanism_model: str = "none"
    aging_drivers: dict[str, Any] = field(default_factory=dict)
    adult_age_setpoint: float = 25.0
    allow_sub_adult_biological_age: bool = False
    organ_backed_model: str = "none"
    organ_proxies: dict[str, Any] = field(default_factory=dict)
    systemic_resources: dict[str, Any] = field(default_factory=dict)
    coordination_mode: str = "independent_organ_policies"
    emergent_weights: dict[str, Any] = field(default_factory=dict)
    organ_network_model: str = "none"
    organ_network_edges: list = field(default_factory=list)
    organ_network_feedback: dict[str, Any] = field(default_factory=dict)
    organ_network_hard_limits: dict[str, Any] = field(default_factory=dict)
    irreversible_thresholds: dict[str, Any] = field(default_factory=dict)
    allow_sub_adult_network_age: bool = False
    reversibility_model: str = "none"
    reversibility_params: dict[str, Any] = field(default_factory=dict)
    allow_sub_adult_reversibility_age: bool = False
    boundary_probe_model: str = "none"
    boundary_params: dict[str, Any] = field(default_factory=dict)
    component_overrides: list = field(default_factory=list)
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.organism_id:
            raise ValueError("organism_id must be non-empty")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("seed must be an int")
        if not isinstance(self.duration_years, (int, float)) or self.duration_years < 0:
            raise ValueError("duration_years must be >= 0")
        if not isinstance(self.dt, (int, float)) or self.dt <= 0:
            raise ValueError("dt must be > 0")
        if not self.model_version:
            raise ValueError("model_version must be non-empty")
        validate_organism_parameters(dict(self.organism_parameters))
        validate_stage_bounds(dict(self.stage_bounds) or default_stage_bounds())
        validate_organism_thresholds(dict(self.thresholds) or default_thresholds())
        PolicySet(list(self.policies or []))
        if not isinstance(self.bounded_epsilon, (int, float)) or float(self.bounded_epsilon) < 0:
            raise ValueError("bounded_epsilon must be >= 0")
        validate_perturbation(dict(self.perturbation or {}))
        from longevity.model.aging import validate_aging_drivers, validate_aging_model
        validate_aging_model(self.aging_mechanism_model)
        validate_aging_drivers(dict(self.aging_drivers or {}))
        from longevity.model.organ_backed import (
            validate_coordination_mode,
            validate_emergent_weights,
            validate_organ_backed_model,
            validate_proxy_params,
            validate_resource_budgets,
        )
        validate_organ_backed_model(self.organ_backed_model)
        validate_proxy_params(dict(self.organ_proxies or {}))
        validate_resource_budgets(dict(self.systemic_resources or {}))
        validate_coordination_mode(self.coordination_mode)
        validate_emergent_weights(dict(self.emergent_weights or {}))
        from longevity.model.organ_network import (
            validate_feedback_config,
            validate_hard_limits,
            validate_irreversible_thresholds,
            validate_network_edges,
            validate_organ_network_model,
        )
        validate_organ_network_model(self.organ_network_model)
        validate_network_edges(list(self.organ_network_edges or []) or None
                               if self.organ_network_edges else None)
        validate_feedback_config(dict(self.organ_network_feedback or {}))
        validate_hard_limits(dict(self.organ_network_hard_limits or {}))
        validate_irreversible_thresholds(dict(self.irreversible_thresholds or {}))
        if not isinstance(self.allow_sub_adult_network_age, bool):
            raise ValueError("allow_sub_adult_network_age must be a bool")
        from longevity.model.reversibility import (
            validate_reversibility_model,
            validate_reversibility_params,
        )
        validate_reversibility_model(self.reversibility_model)
        validate_reversibility_params(dict(self.reversibility_params or {}))
        if not isinstance(self.allow_sub_adult_reversibility_age, bool):
            raise ValueError("allow_sub_adult_reversibility_age must be a bool")
        from longevity.model.boundary import (
            validate_boundary_params,
            validate_boundary_probe_model,
            validate_component_overrides,
        )
        validate_boundary_probe_model(self.boundary_probe_model)
        validate_boundary_params(dict(self.boundary_params or {}))
        validate_component_overrides(list(self.component_overrides or []))
        if not isinstance(self.adult_age_setpoint, (int, float)) or float(self.adult_age_setpoint) < 0:
            raise ValueError("adult_age_setpoint must be >= 0")
        if not isinstance(self.allow_sub_adult_biological_age, bool):
            raise ValueError("allow_sub_adult_biological_age must be a bool")
        if self.initial_state:
            assert_organism_invariants(OrganismState.from_dict(dict(self.initial_state)))

    def effective_bounds(self) -> dict[str, float]:
        return validate_stage_bounds(dict(self.stage_bounds) or default_stage_bounds())

    def effective_thresholds(self) -> dict[str, Any]:
        return validate_organism_thresholds(dict(self.thresholds) or default_thresholds())

    def effective_parameters(self) -> dict[str, float]:
        return validate_organism_parameters(dict(self.organism_parameters))

    def effective_perturbation(self) -> dict[str, Any]:
        return validate_perturbation(dict(self.perturbation or {}))

    def effective_aging(self) -> dict[str, Any]:
        from longevity.model.aging import validate_aging_drivers, validate_aging_model
        return {
            "aging_mechanism_model": validate_aging_model(self.aging_mechanism_model),
            "aging_drivers": validate_aging_drivers(dict(self.aging_drivers or {})),
            "adult_age_setpoint": float(self.adult_age_setpoint),
            "allow_sub_adult_biological_age": bool(self.allow_sub_adult_biological_age),
        }

    def effective_organ_backed(self) -> dict[str, Any]:
        from longevity.model.organ_backed import (
            scope_for_model,
            validate_coordination_mode,
            validate_emergent_weights,
            validate_organ_backed_model,
            validate_proxy_params,
            validate_resource_budgets,
        )
        mode = validate_organ_backed_model(self.organ_backed_model)
        return {
            "organ_backed_model": mode,
            "organ_proxies": validate_proxy_params(dict(self.organ_proxies or {})),
            "systemic_resources": validate_resource_budgets(dict(self.systemic_resources or {})),
            "coordination_mode": validate_coordination_mode(self.coordination_mode),
            "emergent_weights": validate_emergent_weights(dict(self.emergent_weights or {})),
            "model_scope": scope_for_model(mode),
        }

    def effective_organ_network(self) -> dict[str, Any]:
        from longevity.model.organ_network import (
            scope_for_network_model,
            validate_feedback_config,
            validate_hard_limits,
            validate_irreversible_thresholds,
            validate_network_edges,
            validate_organ_network_model,
        )
        mode = validate_organ_network_model(self.organ_network_model)
        edges = validate_network_edges(list(self.organ_network_edges or []) or None
                                       if self.organ_network_edges else None)
        scope = scope_for_network_model(mode)
        if mode == "none":
            from longevity.model.organ_backed import scope_for_model

            scope = self.effective_organ_backed()["model_scope"]
        return {
            "organ_network_model": mode,
            "organ_network_edges": edges,
            "organ_network_feedback": validate_feedback_config(
                dict(self.organ_network_feedback or {})),
            "organ_network_hard_limits": validate_hard_limits(
                dict(self.organ_network_hard_limits or {})),
            "irreversible_thresholds": validate_irreversible_thresholds(
                dict(self.irreversible_thresholds or {})),
            "allow_sub_adult_network_age": bool(self.allow_sub_adult_network_age),
            "model_scope": scope,
        }

    def effective_reversibility(self) -> dict[str, Any]:
        from longevity.model.reversibility import (
            scope_for_reversibility_model,
            validate_reversibility_model,
            validate_reversibility_params,
        )
        mode = validate_reversibility_model(self.reversibility_model)
        scope = scope_for_reversibility_model(mode)
        if mode == "none":
            scope = self.effective_organ_network()["model_scope"]
        return {
            "reversibility_model": mode,
            "reversibility_params": validate_reversibility_params(
                dict(self.reversibility_params or {})),
            "allow_sub_adult_reversibility_age": bool(self.allow_sub_adult_reversibility_age),
            "model_scope": scope,
        }

    def effective_boundary(self) -> dict[str, Any]:
        from longevity.model.boundary import (
            is_neutral_boundary,
            scope_for_boundary_model,
            validate_boundary_params,
            validate_boundary_probe_model,
            validate_component_overrides,
        )
        mode = validate_boundary_probe_model(self.boundary_probe_model)
        params = validate_boundary_params(dict(self.boundary_params or {}))
        overrides = validate_component_overrides(list(self.component_overrides or []))
        scope = scope_for_boundary_model(mode)
        if mode == "none":
            scope = self.effective_reversibility()["model_scope"]
        return {
            "boundary_probe_model": mode,
            "boundary_params": params,
            "component_overrides": overrides,
            "neutral": is_neutral_boundary(params, overrides) if mode != "none" else True,
            "model_scope": scope,
        }

    def to_config_dict(self) -> dict[str, Any]:
        network = self.effective_organ_network()
        reversibility = self.effective_reversibility()
        boundary = self.effective_boundary()
        scope = boundary["model_scope"]
        return {
            "organism_id": self.organism_id,
            "model_scope": scope,
            "model_version": self.model_version,
            "data_version": self.data_version,
            "seed": self.seed,
            "duration_years": float(self.duration_years),
            "dt": float(self.dt),
            "initial_state": OrganismState.from_dict(dict(self.initial_state)).to_dict() if self.initial_state else {},
            "organism_parameters": self.effective_parameters(),
            "stage_bounds": self.effective_bounds(),
            "thresholds": self.effective_thresholds(),
            "policies": [p.to_dict() for p in PolicySet(list(self.policies or [])).policies],
            "bounded_epsilon": float(self.bounded_epsilon),
            "perturbation": validate_perturbation(dict(self.perturbation or {})),
            "aging_mechanism_model": self.effective_aging()["aging_mechanism_model"],
            "aging_drivers": self.effective_aging()["aging_drivers"],
            "adult_age_setpoint": float(self.adult_age_setpoint),
            "allow_sub_adult_biological_age": bool(self.allow_sub_adult_biological_age),
            "organ_backed_model": self.effective_organ_backed()["organ_backed_model"],
            "organ_proxies": self.effective_organ_backed()["organ_proxies"],
            "systemic_resources": self.effective_organ_backed()["systemic_resources"],
            "coordination_mode": self.effective_organ_backed()["coordination_mode"],
            "emergent_weights": self.effective_organ_backed()["emergent_weights"],
            "organ_network_model": network["organ_network_model"],
            "organ_network_edges": network["organ_network_edges"],
            "organ_network_feedback": network["organ_network_feedback"],
            "organ_network_hard_limits": network["organ_network_hard_limits"],
            "irreversible_thresholds": network["irreversible_thresholds"],
            "allow_sub_adult_network_age": network["allow_sub_adult_network_age"],
            "reversibility_model": reversibility["reversibility_model"],
            "reversibility_params": reversibility["reversibility_params"],
            "allow_sub_adult_reversibility_age": reversibility["allow_sub_adult_reversibility_age"],
            "boundary_probe_model": boundary["boundary_probe_model"],
            "boundary_params": boundary["boundary_params"],
            "component_overrides": boundary["component_overrides"],
            "notes": self.notes,
        }

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "OrganismExperimentConfig":
        return cls(
            organism_id=data["organism_id"],
            seed=data["seed"],
            duration_years=float(data.get("duration_years", 150.0)),
            dt=float(data.get("dt", 0.25)),
            model_version=data.get("model_version", ORGANISM_MODEL_VERSION),
            data_version=data.get("data_version", DATA_VERSION),
            initial_state=data.get("initial_state", {}),
            organism_parameters=data.get("organism_parameters", {}),
            stage_bounds=data.get("stage_bounds", {}),
            thresholds=data.get("thresholds", {}),
            policies=data.get("policies", []),
            bounded_epsilon=float(data.get("bounded_epsilon", 0.01)),
            perturbation=data.get("perturbation", {}),
            aging_mechanism_model=data.get("aging_mechanism_model", "none"),
            aging_drivers=data.get("aging_drivers", {}),
            adult_age_setpoint=float(data.get("adult_age_setpoint", 25.0)),
            allow_sub_adult_biological_age=bool(data.get("allow_sub_adult_biological_age", False)),
            organ_backed_model=data.get("organ_backed_model", "none"),
            organ_proxies=data.get("organ_proxies", {}),
            systemic_resources=data.get("systemic_resources", {}),
            coordination_mode=data.get("coordination_mode", "independent_organ_policies"),
            emergent_weights=data.get("emergent_weights", {}),
            organ_network_model=data.get("organ_network_model", "none"),
            organ_network_edges=data.get("organ_network_edges", []),
            organ_network_feedback=data.get("organ_network_feedback", {}),
            organ_network_hard_limits=data.get("organ_network_hard_limits", {}),
            irreversible_thresholds=data.get("irreversible_thresholds", {}),
            allow_sub_adult_network_age=bool(data.get("allow_sub_adult_network_age", False)),
            reversibility_model=data.get("reversibility_model", "none"),
            reversibility_params=data.get("reversibility_params", {}),
            allow_sub_adult_reversibility_age=bool(data.get("allow_sub_adult_reversibility_age", False)),
            boundary_probe_model=data.get("boundary_probe_model", "none"),
            boundary_params=data.get("boundary_params", {}),
            component_overrides=data.get("component_overrides", []),
            notes=data.get("notes", ""),
        )


def default_stage_bounds() -> dict[str, float]:
    from longevity.model.organism import DEFAULT_STAGE_BOUNDS
    return dict(DEFAULT_STAGE_BOUNDS)


def default_thresholds() -> dict[str, Any]:
    from longevity.model.organism import DEFAULT_ORGANISM_THRESHOLDS
    return dict(DEFAULT_ORGANISM_THRESHOLDS)


def load_organism_config(path: str) -> OrganismExperimentConfig:
    """Read an organism experiment JSON file into a validated config."""
    with open(path, encoding="utf-8") as fh:
        return OrganismExperimentConfig.from_config_dict(json.load(fh))


def run_organism_experiment(config: OrganismExperimentConfig, out_path: str | None = None) -> dict[str, Any]:
    """Run an organism life-course and return (and optionally persist) a result."""
    wall_start = time.perf_counter()
    bounds = config.effective_bounds()
    thresholds = config.effective_thresholds()
    model = OrganismModel(
        state=OrganismState.from_dict(dict(config.initial_state)) if config.initial_state else None,
        parameters=config.effective_parameters(),
        rng=Rng(config.seed),
        seed=config.seed,
        perturbation=config.effective_perturbation(),
        aging_model=config.effective_aging()["aging_mechanism_model"],
        aging_drivers=config.effective_aging()["aging_drivers"],
        adult_age_setpoint=config.effective_aging()["adult_age_setpoint"],
        allow_sub_adult_biological_age=config.effective_aging()["allow_sub_adult_biological_age"],
        organ_backed_model=config.effective_organ_backed()["organ_backed_model"],
        organ_proxies=config.effective_organ_backed()["organ_proxies"],
        systemic_resources=config.effective_organ_backed()["systemic_resources"],
        coordination_mode=config.effective_organ_backed()["coordination_mode"],
        emergent_weights=config.effective_organ_backed()["emergent_weights"],
        organ_network_model=config.effective_organ_network()["organ_network_model"],
        organ_network_edges=config.effective_organ_network()["organ_network_edges"],
        organ_network_feedback=config.effective_organ_network()["organ_network_feedback"],
        organ_network_hard_limits=config.effective_organ_network()["organ_network_hard_limits"],
        irreversible_thresholds=config.effective_organ_network()["irreversible_thresholds"],
        allow_sub_adult_network_age=config.effective_organ_network()["allow_sub_adult_network_age"],
        reversibility_model=config.effective_reversibility()["reversibility_model"],
        reversibility_params=config.effective_reversibility()["reversibility_params"],
        allow_sub_adult_reversibility_age=config.effective_reversibility()[
            "allow_sub_adult_reversibility_age"],
        boundary_probe_model=config.effective_boundary()["boundary_probe_model"],
        boundary_params=config.effective_boundary()["boundary_params"],
        component_overrides=config.effective_boundary()["component_overrides"],
    )
    policies = PolicySet(list(config.policies or []))
    trajectory = model.run(config.duration_years, config.dt, bounds, thresholds, policies)
    summary = compute_organism_summary(trajectory, config.dt, thresholds, config.bounded_epsilon)
    organ_backed_summary: dict[str, Any] = {}
    if config.effective_organ_backed()["organ_backed_model"] != "none":
        from longevity.analysis.organ_backed_metrics import summarize_organ_backed_run

        organ_backed_summary = summarize_organ_backed_run(trajectory)
        summary["organs"] = organ_backed_summary["organs"]
        summary["systemic_resources"] = organ_backed_summary["systemic_resources"]
        summary["cross_scale"] = organ_backed_summary["cross_scale"]
    if config.effective_organ_network()["organ_network_model"] != "none":
        from longevity.analysis.organ_network_metrics import summarize_organ_network_run

        network_summary = summarize_organ_network_run(trajectory, config.dt)
        summary["organ_network"] = network_summary["organ_network"]
        summary["network_binding"] = network_summary["network_binding"]
        summary["hard_limits"] = network_summary["hard_limits"]
    if config.effective_reversibility()["reversibility_model"] != "none":
        from longevity.analysis.reversibility_metrics import summarize_reversibility_run

        rev_summary = summarize_reversibility_run(trajectory, config.dt)
        summary["reversibility"] = rev_summary["reversibility"]
        summary["reversibility_binding"] = rev_summary["reversibility_binding"]
    if config.effective_boundary()["boundary_probe_model"] != "none":
        from longevity.analysis.boundary_metrics import summarize_boundary_run

        boundary_summary = summarize_boundary_run(trajectory, config.dt)
        summary["boundary"] = boundary_summary["boundary"]
        summary["contributions"] = boundary_summary["contributions"]
        summary["attribution"] = boundary_summary["attribution"]
    wall_seconds = round(time.perf_counter() - wall_start, 4)
    result: dict[str, Any] = {
        "organism_id": config.organism_id,
        "model_scope": config.effective_boundary()["model_scope"],
        "immortality_status": "hypothesis_not_proven",
        "organ_backed_model": config.effective_organ_backed()["organ_backed_model"],
        "organ_network_model": config.effective_organ_network()["organ_network_model"],
        "reversibility_model": config.effective_reversibility()["reversibility_model"],
        "boundary_probe_model": config.effective_boundary()["boundary_probe_model"],
        "boundary_exploratory": bool((trajectory[-1].get("boundary") or {}).get("exploratory", False)),
        "coordination_mode": config.effective_organ_backed()["coordination_mode"],
        "config": config.to_config_dict(),
        "trajectory": trajectory,
        "metrics": {"format": ORGANISM_RESULT_FORMAT_VERSION, "final": summary},
        "summary": {
            "lifespan": summary["lifespan"],
            "healthspan": summary["healthspan"],
            "primary_cause_of_death": summary["primary_cause_of_death"],
            "bounded_degradation_indicator": summary["bounded_degradation_indicator"],
            "final_biological_age": summary["final_biological_age"],
        },
        "runtime": {
            "engine": ORGANISM_ENGINE_VERSION,
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Stage 5A organism life-course experiment.")
    parser.add_argument("--config", required=True, help="Organism config JSON")
    parser.add_argument("--out", default="", help="Output JSON path (default: experiments/output/<organism_id>.json)")
    args = parser.parse_args()
    config = load_organism_config(args.config)
    out_path = args.out or f"experiments/output/{config.organism_id}.json"
    result = run_organism_experiment(config, out_path=out_path)
    summary = result["summary"]
    print(f"[organism {config.organism_id}] lifespan={summary['lifespan']:.1f} "
          f"healthspan={summary['healthspan']:.1f} cause={summary['primary_cause_of_death']} "
          f"bounded={summary['bounded_degradation_indicator']}")
    print(f"[out] {out_path}")


if __name__ == "__main__":
    main()
