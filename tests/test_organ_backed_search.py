"""Stage 6A: organ-backed search, sweeps, stress, and scope flags."""

import json

import pytest

from longevity.analysis.organism_metrics import validate_fitness_weights
from longevity.experiment.organism_organ_backed import (
    CoordinationCompareConfig,
    ResourceSensitivityConfig,
    load_organ_backed_config,
    run_coordination_compare,
    run_resource_sensitivity,
    write_coordination_outputs,
    write_sensitivity_outputs,
)
from longevity.experiment.organism_policy_search import (
    load_policy_search_config,
    run_policy_search,
)
from longevity.experiment.organism_robust import load_robust_config, run_robust_evaluation
from longevity.model.organ_backed import ORGAN_BACKED_SCOPE


def _tiny_base(organism_id="tiny_backed", policies=None, duration=30.0, dt=0.5):
    return {"organism_id": organism_id, "model_version": "0.5.0",
            "data_version": "0.1.0", "seed": 42, "duration_years": duration,
            "dt": dt, "organism_parameters": {}, "stage_bounds": {},
            "thresholds": {}, "policies": policies or [], "bounded_epsilon": 0.01,
            "aging_mechanism_model": "mechanistic_drivers", "aging_drivers": {},
            "adult_age_setpoint": 25.0, "allow_sub_adult_biological_age": False,
            "organ_backed_model": "reduced_organ_proxies", "organ_proxies": {},
            "systemic_resources": {}, "coordination_mode": "independent_organ_policies",
            "emergent_weights": {}, "notes": "tiny 6A fixture"}


def _tiny_policy(pid="m", interval=5.0):
    return {"policy_id": pid, "enabled": True, "start_age": 25.0, "stop_age": 150.0,
            "trigger_type": "periodic", "interval": interval, "intensity": 1.0,
            "intervention_type": "tissue_organ_maintenance", "target_systems": [],
            "target_organ_ids": [], "max_cancer_allowed": 1.0, "min_reserve_required": 0.0}


def test_mini_search_end_to_end_and_deterministic():
    from longevity.experiment.organism_policy_search import OrganismPolicySearchConfig

    config = OrganismPolicySearchConfig(
        experiment_id="tiny_search", seeds=(42, 7), method="grid",
        search_space={"policies.0.interval": [5.0, 10.0]},
        fitness_weights={"w_organ_slope": 10.0, "w_bounded_v3_bonus": 5.0},
        base_organism_config=_tiny_base(policies=[_tiny_policy()]), top_k=2)
    first = run_policy_search(config)
    second = run_policy_search(config)
    assert first["n_evaluated"] == 2
    assert [e["combo"] for e in first["ranked"]] == [e["combo"] for e in second["ranked"]]
    assert len(first["top_k"]) == 2 and len(first["pareto"]) >= 1
    for entry in first["ranked"]:
        assert entry["fitness"] == entry["fitness"]  # finite, no NaN
        assert "robust_v3" in entry and "worst_organ_slope" in entry
    assert first["immortality_status"] == "hypothesis_not_proven"


def test_coordination_compare_tiny_and_artifacts(tmp_path):
    config = CoordinationCompareConfig(
        experiment_id="tiny_coord", seeds=(42, 7),
        coordination_modes=("independent_organ_policies", "global_resource_aware_scaling"),
        base_organism_config=_tiny_base(policies=[_tiny_policy()]))
    result = run_coordination_compare(config)
    assert result["model_scope"] == ORGAN_BACKED_SCOPE
    assert result["immortality_status"] == "hypothesis_not_proven"
    assert isinstance(result["candidate_robust_bounded_degradation_v3_found"], bool)
    assert result["comparison"]["independent_organ_policies"]["lifespan_gain_vs_independent"] == 0.0
    paths = write_coordination_outputs(result, str(tmp_path / "tiny_coord"))
    assert set(paths) == {"long_csv", "summary_csv", "summary_json",
                          "comparison_json", "binding_constraints_json"}
    for path in paths.values():
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert content
        if path.endswith(".json"):
            json.loads(content)


def test_resource_sensitivity_tiny_and_boundary(tmp_path):
    config = ResourceSensitivityConfig(
        experiment_id="tiny_sens", seeds=(42, 7),
        resource_axes={"repair": [4.0, 8.0]},
        base_organism_config=_tiny_base(policies=[_tiny_policy()]))
    result = run_resource_sensitivity(config)
    assert len(result["points"]) == 2
    assert set(result["boundary"]) == {"repair"}
    assert result["boundary"]["repair"]["transition_budget"] in (4.0, 8.0, None)
    paths = write_sensitivity_outputs(result, str(tmp_path / "tiny_sens"))
    assert set(paths) == {"long_csv", "summary_csv", "summary_json", "boundary_json",
                          "binding_constraints_json", "organ_failures_json"}


def test_stress_tiny_with_resource_shock():
    config = load_robust_config("experiments/configs/organism_organ_backed_stress.json")
    tiny = dict(config.to_config_dict())
    tiny["seeds"] = [42, 7]
    tiny["scenarios"] = ["nominal", "global_resource_shock"]
    tiny["runs"] = {"tiny": _tiny_base(policies=[_tiny_policy()])}
    from longevity.experiment.organism_robust import OrganismRobustConfig

    config = OrganismRobustConfig.from_config_dict(tiny)
    result = run_robust_evaluation(config)
    assert len(result["cells"]) == 2
    for cell in result["cells"]:
        assert cell["aggregate"]["lifespan"]["mean"] == cell["aggregate"]["lifespan"]["mean"]


def test_config_loaders_and_fitness_weights():
    compare = load_organ_backed_config(
        "experiments/configs/organism_organ_backed_coordination_compare.json")
    assert isinstance(compare, CoordinationCompareConfig)
    sweep = load_organ_backed_config(
        "experiments/configs/organism_organ_backed_resource_sensitivity_sweep.json")
    assert isinstance(sweep, ResourceSensitivityConfig)
    search = load_policy_search_config(
        "experiments/configs/organism_organ_backed_robust_search_mini.json")
    assert search.to_config_dict()["fitness_weights"]["w_bounded_v3_bonus"] == 30.0
    weights = validate_fitness_weights({})
    assert weights["w_organ_slope"] == 0.0 and weights["w_bounded_v3_bonus"] == 0.0
    with pytest.raises(ValueError):
        validate_fitness_weights({"no_such_weight": 1.0})
    with pytest.raises(ValueError):
        load_organ_backed_config(
            "experiments/configs/organism_aging_binding_driver_sweep.json")
