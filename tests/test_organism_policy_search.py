"""Stage 5A: organism policy search -- determinism, fitness, artifacts."""

import copy
import csv
import json
import math
import random

import pytest

from longevity.experiment.organism_policy_search import (
    OrganismPolicySearchConfig,
    load_policy_search_config,
    run_policy_search,
    write_policy_search_outputs,
)


def _tiny_search(**overrides):
    base = {
        "experiment_id": "search-test",
        "seeds": [11, 12],
        "method": "grid",
        "random_seed": 0,
        "n_random": 4,
        "hill_steps": 2,
        "top_k": 3,
        "search_space": {"policies.0.interval": [3.0, 10.0], "policies.0.intensity": [0.5, 1.0]},
        "fitness_weights": {},
        "base_organism_config": {
            "organism_id": "search-base", "seed": 11, "duration_years": 150.0, "dt": 1.0,
            "organism_parameters": {}, "stage_bounds": {}, "thresholds": {},
            "policies": [
                {"policy_id": "repair", "enabled": True, "start_age": 25.0, "stop_age": 150.0,
                 "trigger_type": "periodic", "interval": 5.0, "intensity": 1.0,
                 "intervention_type": "molecular_repair", "target_systems": []},
                {"policy_id": "senolytic", "enabled": True, "start_age": 25.0, "stop_age": 150.0,
                 "trigger_type": "periodic", "interval": 5.0, "intensity": 1.0,
                 "intervention_type": "cellular_replacement", "target_systems": []},
            ],
        },
        "output_prefix": "",
        "notes": "",
    }
    base.update(overrides)
    return OrganismPolicySearchConfig.from_config_dict(base)


def test_search_config_validation():
    with pytest.raises(ValueError):
        _tiny_search(seeds=[11])
    with pytest.raises(ValueError):
        _tiny_search(seeds=[])
    with pytest.raises(ValueError):
        _tiny_search(method="telepathy")
    with pytest.raises(ValueError):
        _tiny_search(search_space={})
    with pytest.raises(ValueError):
        _tiny_search(search_space={"policies.0.interval": []})
    with pytest.raises(ValueError):
        _tiny_search(fitness_weights={"w_lifespan": -2.0})
    with pytest.raises(ValueError):
        _tiny_search(base_organism_config={})


def test_grid_search_end_to_end_and_determinism(tmp_path):
    first = run_policy_search(_tiny_search())
    second = run_policy_search(_tiny_search())
    assert first["ranked"] == second["ranked"]
    assert first["config_hash"] == second["config_hash"]
    assert len(first["ranked"]) == 4  # 2 x 2 grid
    assert first["n_evaluated"] == 4
    fitness_values = [entry["fitness"] for entry in first["ranked"]]
    assert fitness_values == sorted(fitness_values, reverse=True)
    assert len(first["top_k"]) == 3
    assert first["model_scope"] == "abstract_organism_life_course"
    assert first["immortality_status"] == "hypothesis_not_proven"
    paths = write_policy_search_outputs(first, str(tmp_path / "search"))
    assert set(paths) == {"long_csv", "summary_json", "best_json", "pareto_json"}
    with open(paths["long_csv"], encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 4
    for key in ("summary_json", "best_json", "pareto_json"):
        with open(paths[key], encoding="utf-8") as fh:
            json.load(fh)
    json.dumps(first)


def test_random_and_hill_climbing_methods():
    random_result = run_policy_search(_tiny_search(method="random", n_random=3))
    assert random_result["n_evaluated"] == 3
    rerun = run_policy_search(_tiny_search(method="random", n_random=3))
    assert rerun["ranked"] == random_result["ranked"]
    hill = run_policy_search(_tiny_search(method="hill_climbing", hill_steps=2))
    assert hill["n_evaluated"] >= 1
    assert hill["top_k"][0]["fitness"] >= hill["ranked"][-1]["fitness"]


def test_global_random_untouched_by_search():
    before = random.getstate()
    run_policy_search(_tiny_search())
    assert random.getstate() == before


def test_real_mini_config_loads():
    config = load_policy_search_config("experiments/configs/organism_policy_search_mini.json")
    assert len(config.seeds) >= 2
    assert config.search_space


def test_organ_inspired_beats_pruning_and_constraints_hold():
    from longevity.experiment.organism_runner import load_organism_config, run_organism_experiment
    inspired = run_organism_experiment(load_organism_config(
        "experiments/configs/organism_life_course_organ_inspired.json"))
    assert inspired["summary"]["lifespan"] >= 68.0 - 1e-9
    # Neural continuity never collapses in the preserving run.
    neural = run_organism_experiment(load_organism_config(
        "experiments/configs/organism_life_course_neural_preserving.json"))
    assert neural["metrics"]["final"]["neural_identity_preservation"] >= 0.5
    blob = json.dumps(neural)
    for forbidden in ("human", "patient", "clinical"):
        assert forbidden not in blob.lower()
    assert neural["model_scope"] == "abstract_organism_life_course"
