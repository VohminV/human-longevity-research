"""Stage 5B: robust search, adaptive constraints, hybrid, neural-extended."""

import copy
import json
import math

import pytest

from longevity.experiment.organism_policy_search import (
    load_policy_search_config,
    run_policy_search,
)


def _tiny_search(**overrides):
    base = {
        "experiment_id": "robust-search-test",
        "seeds": [11, 12, 13],
        "method": "grid",
        "random_seed": 0,
        "n_random": 4,
        "hill_steps": 2,
        "top_k": 3,
        "search_space": {"policies.0.interval": [5.0, 10.0], "policies.0.intensity": [0.5, 1.0]},
        "fitness_weights": {"w_std_penalty": 2.0, "w_worst_penalty": 1.0},
        "base_organism_config": {
            "organism_id": "search-base", "seed": 11, "duration_years": 150.0, "dt": 1.0,
            "organism_parameters": {}, "stage_bounds": {}, "thresholds": {},
            "policies": [
                {"policy_id": "repair", "enabled": True, "start_age": 25.0, "stop_age": 150.0,
                 "trigger_type": "periodic", "interval": 5.0, "intensity": 1.0,
                 "intervention_type": "molecular_repair", "target_systems": []},
            ],
        },
        "output_prefix": "",
        "notes": "",
    }
    base.update(overrides)
    from longevity.experiment.organism_policy_search import OrganismPolicySearchConfig
    return OrganismPolicySearchConfig.from_config_dict(base)


def test_robust_search_end_to_end_and_determinism(tmp_path):
    from longevity.experiment.organism_policy_search import write_policy_search_outputs
    first = run_policy_search(_tiny_search())
    second = run_policy_search(_tiny_search())
    assert first["ranked"] == second["ranked"]
    assert len(first["ranked"]) == 4
    assert first["ranked"][0]["fitness"] >= first["ranked"][-1]["fitness"]
    assert "robust_fitness" in first["ranked"][0]
    assert first["ranked"][0]["fitness"] == first["ranked"][0]["robust_fitness"]
    paths = write_policy_search_outputs(first, str(tmp_path / "search"))
    assert set(paths) == {"long_csv", "summary_json", "best_json", "pareto_json"}
    with open(paths["best_json"], encoding="utf-8") as fh:
        best = json.load(fh)
    assert best["top_k"]
    json.dumps(first)


def test_robust_penalties_bite_on_variance():
    from longevity.analysis.organism_metrics import robust_fitness
    weights = {"w_std_penalty": 5.0, "w_worst_penalty": 5.0}
    flat = [{"lifespan": 80.0, "healthspan": 70.0, "functional_reserve_area": 50.0,
             "damage_auc": 8.0, "cancer_auc": 1.0, "inflammation_auc": 2.0,
             "neural_identity_preservation": 1.0, "bounded_degradation_indicator": False} for _ in range(3)]
    spread = [dict(flat[0], lifespan=100.0), dict(flat[0], lifespan=80.0), dict(flat[0], lifespan=40.0)]
    assert robust_fitness(spread, weights)["robust_fitness"] < robust_fitness(flat, weights)["robust_fitness"]
    assert robust_fitness(flat, {})["robust_fitness"] == robust_fitness(flat, {})["fitness_mean"]


def test_adaptive_constrained_caps_cancer():
    from longevity.experiment.organism_robust import load_robust_config
    from longevity.experiment.organism_runner import OrganismExperimentConfig, run_organism_experiment
    robust = load_robust_config("experiments/configs/organism_robust_adaptive_constrained.json")
    base = robust.runs["adaptive_constrained"]
    guards = [p for p in base["policies"] if p["policy_id"] == "surveillance_guard"]
    assert guards and guards[0]["max_cancer_allowed"] == pytest.approx(0.5)
    result = run_organism_experiment(OrganismExperimentConfig.from_config_dict({**base, "seed": 42}))
    assert result["summary"]["lifespan"] >= 68.0 - 1e-9
    assert result["metrics"]["final"]["rejuvenation_events"] >= 0
    # Cooldown respected: threshold firings are spaced by interval.
    firings = [h["age"] for h in result["trajectory"][-1]["intervention_history"]
               if h["effect"] == "cellular_replacement"]
    gaps = [b - a for a, b in zip(firings, firings[1:])]
    assert all(gap >= 1.0 - 1e-9 for gap in gaps)


def test_repair_plus_senolytic_moves_biomarkers():
    from longevity.experiment.organism_runner import load_organism_config, run_organism_experiment
    result = run_organism_experiment(load_organism_config(
        "experiments/configs/organism_life_course_combined_maintenance.json"))
    assert result["summary"]["lifespan"] > 68.0
    assert result["summary"]["healthspan"] <= result["summary"]["lifespan"] + 1e-9


def test_neural_extended_preserves_continuity():
    from longevity.experiment.organism_runner import load_organism_config, run_organism_experiment
    neural = run_organism_experiment(load_organism_config(
        "experiments/configs/organism_life_course_neural_preserving.json"))
    unrestricted = run_organism_experiment(load_organism_config(
        "experiments/configs/organism_life_course_senolytic.json"))
    assert neural["metrics"]["final"]["neural_identity_preservation"] >= \
        unrestricted["metrics"]["final"]["neural_identity_preservation"] - 1e-9
    blob = json.dumps(neural)
    assert neural["model_scope"] == "abstract_organism_life_course"
    assert neural["immortality_status"] == "hypothesis_not_proven"


def test_real_robust_configs_load():
    assert load_policy_search_config("experiments/configs/organism_robust_policy_search_mini.json").seeds
    assert load_policy_search_config("experiments/configs/organism_long_horizon_search.json").seeds
