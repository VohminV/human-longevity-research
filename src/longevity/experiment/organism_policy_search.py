"""EXPERIMENT ENGINE LAYER: deterministic longevity policy search (Stage 5A).

Grid, seeded-random, and hill-climbing-lite search over policy parameters
(no external ML). Fitness is multi-objective (see organism_metrics);
deterministic tie-breaking throughout; never touches global random.

CLI::

    PYTHONPATH=src python -m longevity.experiment.organism_policy_search \\
        --config experiments/configs/organism_policy_search_mini.json \\
        --out-prefix experiments/output/organism_policy_search
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

from longevity.analysis.organism_metrics import (
    aggregate_summaries,
    fitness,
    pareto_frontier,
    robust_fitness,
    validate_fitness_weights,
)
from longevity.experiment.organism_runner import OrganismExperimentConfig, run_organism_experiment
from longevity.model.organism import MODEL_SCOPE, ORGANISM_MODEL_VERSION
from longevity.sim.rng import Rng

POLICY_SEARCH_FORMAT_VERSION = "1.0"
MIN_SEARCH_SEEDS = 2
SEARCH_METHODS = ("grid", "random", "hill_climbing")


def _require_seeds(seeds: Any) -> tuple[int, ...]:
    if not isinstance(seeds, (list, tuple)) or len(seeds) == 0:
        raise ValueError("search seeds must be a non-empty list")
    cleaned = []
    for seed in seeds:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError(f"search seed must be an int, got {seed!r}")
        cleaned.append(seed)
    if len(set(cleaned)) != len(cleaned):
        raise ValueError("search seeds must be unique")
    if len(cleaned) < MIN_SEARCH_SEEDS:
        raise ValueError(f"search needs at least {MIN_SEARCH_SEEDS} seeds, got {len(cleaned)}")
    return tuple(cleaned)


def _set_nested(container: dict[str, Any], path: str, value: Any) -> None:
    """Set dotted path (``policies.0.interval``) inside a nested structure."""
    parts = path.split(".")
    node: Any = container
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    last = parts[-1]
    if isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value


def _candidate_configs(base: dict[str, Any], search_space: dict[str, list],
                       method: str, random_seed: int, n_random: int) -> list[dict[str, Any]]:
    """Expand the search space into candidate config dicts (pure)."""
    if method not in SEARCH_METHODS:
        raise ValueError(f"search method must be one of {SEARCH_METHODS}, got {method!r}")
    names = sorted(search_space)
    for name, values in search_space.items():
        if not isinstance(values, list) or not values:
            raise ValueError(f"search_space[{name!r}] must be a non-empty list")
    combos: list[dict[str, Any]] = []
    if method == "grid":
        for values in itertools.product(*[search_space[name] for name in names]):
            combos.append(dict(zip(names, values)))
    elif method == "random":
        rng = Rng(random_seed)
        for _ in range(n_random):
            combos.append({name: search_space[name][int(rng.random() * len(search_space[name]))] for name in names})
    else:  # hill_climbing: start at first grid corner, greedily step (evaluated by caller loop)
        combos.append({name: search_space[name][0] for name in names})
    configs = []
    for combo in combos:
        data = copy.deepcopy(base)
        for path, value in combo.items():
            _set_nested(data, path, value)
        configs.append((combo, data))
    return configs


def _hill_neighbors(center: dict[str, Any], search_space: dict[str, list]) -> list[dict[str, Any]]:
    """One-step neighbors of a combo along each axis (deterministic order)."""
    neighbors = []
    for name in sorted(search_space):
        values = search_space[name]
        try:
            index = next(i for i, v in enumerate(values) if v == center[name])
        except StopIteration:
            continue
        for step in (-1, 1):
            neighbor_index = index + step
            if 0 <= neighbor_index < len(values):
                neighbor = dict(center)
                neighbor[name] = values[neighbor_index]
                neighbors.append(neighbor)
    return neighbors


@dataclass(frozen=True)
class OrganismPolicySearchConfig:
    """Complete, self-describing policy-search configuration."""

    experiment_id: str
    seeds: tuple[int, ...] = ()
    method: str = "grid"
    random_seed: int = 0
    n_random: int = 8
    hill_steps: int = 4
    top_k: int = 5
    search_space: dict[str, list] = field(default_factory=dict)
    fitness_weights: dict[str, float] = field(default_factory=dict)
    base_organism_config: dict[str, Any] = field(default_factory=dict)
    output_prefix: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id must be non-empty")
        _require_seeds(list(self.seeds))
        if self.method not in SEARCH_METHODS:
            raise ValueError(f"method must be one of {SEARCH_METHODS}, got {self.method!r}")
        if not isinstance(self.search_space, dict) or not self.search_space:
            raise ValueError("search_space must be a non-empty dict")
        for name, values in self.search_space.items():
            if not isinstance(values, list) or not values:
                raise ValueError(f"search_space[{name!r}] must be a non-empty list")
        validate_fitness_weights(dict(self.fitness_weights))
        if not isinstance(self.base_organism_config, dict) or not self.base_organism_config:
            raise ValueError("base_organism_config must be a non-empty dict")
        OrganismExperimentConfig.from_config_dict(copy.deepcopy(self.base_organism_config))

    def to_config_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "seeds": list(self.seeds),
            "method": self.method,
            "random_seed": self.random_seed,
            "n_random": self.n_random,
            "hill_steps": self.hill_steps,
            "top_k": self.top_k,
            "search_space": copy.deepcopy(self.search_space),
            "fitness_weights": validate_fitness_weights(dict(self.fitness_weights)),
            "base_organism_config": copy.deepcopy(self.base_organism_config),
            "output_prefix": self.output_prefix,
            "notes": self.notes,
        }

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "OrganismPolicySearchConfig":
        return cls(
            experiment_id=data["experiment_id"],
            seeds=tuple(data.get("seeds", ())),
            method=data.get("method", "grid"),
            random_seed=int(data.get("random_seed", 0)),
            n_random=int(data.get("n_random", 8)),
            hill_steps=int(data.get("hill_steps", 4)),
            top_k=int(data.get("top_k", 5)),
            search_space=copy.deepcopy(data.get("search_space", {})),
            fitness_weights=copy.deepcopy(data.get("fitness_weights", {})),
            base_organism_config=copy.deepcopy(data.get("base_organism_config", {})),
            output_prefix=data.get("output_prefix", ""),
            notes=data.get("notes", ""),
        )


def search_config_hash(config: OrganismPolicySearchConfig) -> str:
    canonical = json.dumps(config.to_config_dict(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _evaluate_combo(combo: dict[str, Any], config: OrganismPolicySearchConfig) -> dict[str, Any]:
    seed_summaries: dict[str, Any] = {}
    for seed in config.seeds:
        data = copy.deepcopy(config.base_organism_config)
        for path, value in combo.items():
            _set_nested(data, path, value)
        data["seed"] = seed
        experiment = OrganismExperimentConfig.from_config_dict(data)
        result = run_organism_experiment(experiment, out_path=None)
        seed_summaries[str(seed)] = result["metrics"]["final"]
    aggregate = aggregate_summaries(list(seed_summaries.values()))
    weights = validate_fitness_weights(dict(config.fitness_weights))
    mean = lambda key: aggregate[key]["mean"]
    representative = {
        "lifespan": mean("lifespan"),
        "healthspan": mean("healthspan"),
        "functional_reserve_area": mean("functional_reserve_area"),
        "damage_auc": mean("damage_auc"),
        "cancer_auc": mean("cancer_auc"),
        "inflammation_auc": sum(s.get("inflammation_auc", 0.0) for s in seed_summaries.values()) / len(seed_summaries),
        "neural_identity_preservation": sum(
            s.get("neural_identity_preservation", 1.0) for s in seed_summaries.values()) / len(seed_summaries),
        "bounded_degradation_indicator": any(s["bounded_degradation_indicator"] for s in seed_summaries.values()),
    }
    robust = robust_fitness(list(seed_summaries.values()), weights)
    from longevity.analysis.aging_metrics import robust_bounded_degradation_v2  # local: analysis reuse

    v2 = robust_bounded_degradation_v2(list(seed_summaries.values()))
    w = dict(weights)
    worst_driver = max([float(s.get("drivers", {}).get("worst_driver_slope", 0.0))
                        for s in seed_summaries.values()] + [0.0])
    driver_penalty = w.get("w_driver_slope", 0.0) * worst_driver
    v2_bonus = w.get("w_bounded_v2_bonus", 0.0) * (1.0 if v2["robust_bounded_degradation_v2"] else 0.0)
    from longevity.analysis.organ_backed_metrics import (  # local: analysis reuse
        robust_bounded_degradation_v3,
    )

    v3 = robust_bounded_degradation_v3(list(seed_summaries.values()))
    worst_organ = min([float(s.get("organs", {}).get("worst_organ_function_slope", 0.0))
                       for s in seed_summaries.values()] + [0.0])
    organ_penalty = w.get("w_organ_slope", 0.0) * max(0.0, -worst_organ)
    shortfall = max([float(s.get("systemic_resources", {}).get("total_shortfall_auc", 0.0))
                     for s in seed_summaries.values()] + [0.0])
    resource_penalty = w.get("w_resource_shortfall", 0.0) * shortfall
    v3_bonus = w.get("w_bounded_v3_bonus", 0.0) * (1.0 if v3["robust_bounded_degradation_v3"] else 0.0)
    return {
        "combo": combo,
        "fitness": robust["robust_fitness"] - driver_penalty + v2_bonus
        - organ_penalty - resource_penalty + v3_bonus,
        "fitness_mean": robust["fitness_mean"],
        "fitness_std": robust["fitness_std"],
        "fitness_min": robust["fitness_min"],
        "robust_fitness": robust["robust_fitness"],
        "worst_driver_slope": worst_driver,
        "worst_organ_slope": worst_organ,
        "total_shortfall_auc": shortfall,
        "robust_v2": v2,
        "robust_v3": v3,
        "aggregate": aggregate,
        "seeds": seed_summaries,
        "representative": representative,
    }


def run_policy_search(config: OrganismPolicySearchConfig) -> dict[str, Any]:
    """Run the deterministic policy search; returns a JSON-serializable result."""
    wall_start = time.perf_counter()
    evaluated: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _evaluate(combo: dict[str, Any]) -> dict[str, Any]:
        key = json.dumps(combo, sort_keys=True)
        for existing in evaluated:
            if json.dumps(existing["combo"], sort_keys=True) == key:
                return existing
        result = _evaluate_combo(combo, config)
        evaluated.append(result)
        seen.add(key)
        return result

    if config.method == "hill_climbing":
        current = {name: config.search_space[name][0] for name in sorted(config.search_space)}
        _evaluate(current)
        for _ in range(config.hill_steps):
            neighbors = [n for n in _hill_neighbors(current, dict(config.search_space))
                         if json.dumps(n, sort_keys=True) not in seen]
            if not neighbors:
                break
            scored = [(_evaluate(n)["fitness"], n) for n in neighbors]
            best_fitness, best_combo = max(scored, key=lambda pair: (pair[0], json.dumps(pair[1], sort_keys=True)))
            current_fitness = next(e["fitness"] for e in evaluated
                                   if json.dumps(e["combo"], sort_keys=True) == json.dumps(current, sort_keys=True))
            if best_fitness <= current_fitness:
                break
            current = best_combo
    else:
        for combo, _ in _candidate_configs(config.base_organism_config, dict(config.search_space),
                                           config.method, config.random_seed, config.n_random):
            _evaluate(combo)
    ranked = sorted(evaluated, key=lambda e: (-e["fitness"], json.dumps(e["combo"], sort_keys=True)))
    pareto = pareto_frontier([
        {"combo": e["combo"], "lifespan": e["representative"]["lifespan"],
         "healthspan": e["representative"]["healthspan"], "cancer_auc": e["representative"]["cancer_auc"]}
        for e in evaluated
    ])
    wall_seconds = round(time.perf_counter() - wall_start, 4)
    return {
        "experiment_id": config.experiment_id,
        "format": POLICY_SEARCH_FORMAT_VERSION,
        "config": config.to_config_dict(),
        "config_hash": search_config_hash(config),
        "model_scope": MODEL_SCOPE,
        "immortality_status": "hypothesis_not_proven",
        "seeds": list(config.seeds),
        "n_evaluated": len(evaluated),
        "ranked": ranked,
        "top_k": ranked[:config.top_k],
        "pareto": pareto,
        "runtime": {
            "engine": "organism-policy-search/v0",
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


def write_policy_search_outputs(result: dict[str, Any], out_prefix: str) -> dict[str, str]:
    """Write long CSV, summary JSON, best JSON, pareto JSON artifacts."""
    parent = os.path.dirname(os.path.abspath(out_prefix))
    os.makedirs(parent, exist_ok=True)
    long_path = f"{out_prefix}_long.csv"
    summary_path = f"{out_prefix}_summary.json"
    best_path = f"{out_prefix}_best.json"
    pareto_path = f"{out_prefix}_pareto.json"
    with open(long_path, "w", encoding="utf-8", newline="") as fh:
        fieldnames = ["rank", "fitness", "combo", "lifespan", "healthspan", "cancer_auc", "bounded_any"]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for rank, entry in enumerate(result["ranked"]):
            writer.writerow({
                "rank": rank,
                "fitness": _round6(entry["fitness"]),
                "combo": json.dumps(entry["combo"], sort_keys=True),
                "lifespan": _round6(entry["representative"]["lifespan"]),
                "healthspan": _round6(entry["representative"]["healthspan"]),
                "cancer_auc": _round6(entry["representative"]["cancer_auc"]),
                "bounded_any": entry["representative"]["bounded_degradation_indicator"],
            })
    payload = _round6(result)
    for path, key in ((summary_path, None), (best_path, "top_k"), (pareto_path, "pareto")):
        with open(path, "w", encoding="utf-8") as fh:
            chunk = {"experiment_id": payload["experiment_id"], "config_hash": payload["config_hash"],
                     "model_scope": payload["model_scope"],
                     "immortality_status": payload["immortality_status"],
                     key: payload[key]} if key else payload
            json.dump(chunk, fh, ensure_ascii=False, indent=2, allow_nan=False)
    for value in payload["ranked"]:
        for number in (value["fitness"], value["representative"]["lifespan"]):
            if not math.isfinite(number):
                raise ValueError("non-finite search output")
    return {"long_csv": long_path, "summary_json": summary_path,
            "best_json": best_path, "pareto_json": pareto_path}


def load_policy_search_config(path: str) -> OrganismPolicySearchConfig:
    """Read a policy-search JSON file into a validated config."""
    with open(path, encoding="utf-8") as fh:
        return OrganismPolicySearchConfig.from_config_dict(json.load(fh))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Stage 5A longevity policy search.")
    parser.add_argument("--config", required=True, help="Policy search config JSON")
    parser.add_argument("--out-prefix", default="", help="Output prefix (default: config output_prefix)")
    args = parser.parse_args()
    config = load_policy_search_config(args.config)
    out_prefix = args.out_prefix or config.output_prefix
    if not out_prefix:
        raise ValueError("no out-prefix: pass --out-prefix or set output_prefix in the config")
    result = run_policy_search(config)
    paths = write_policy_search_outputs(result, out_prefix)
    print(f"[policy search {config.experiment_id}] {result['n_evaluated']} combos x {len(config.seeds)} seeds")
    if result["top_k"]:
        best = result["top_k"][0]
        print(f"[best] fitness={best['fitness']:.2f} lifespan={best['representative']['lifespan']:.1f} "
              f"healthspan={best['representative']['healthspan']:.1f}")
    for key, path in paths.items():
        print(f"[{key}] {path}")


if __name__ == "__main__":
    main()
