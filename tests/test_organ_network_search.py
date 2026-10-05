"""Stage 6B: sweeps + mini search + stress end-to-end (small, fast)."""

import json

from longevity.experiment.organism_organ_network import (
    HardLimitSensitivityConfig,
    NetworkCoordinationCompareConfig,
    NetworkResourceSensitivityConfig,
    load_organ_network_config,
    run_coordination_compare,
    run_hard_limit_sensitivity,
    run_resource_sensitivity,
)
from longevity.experiment.organism_runner import load_organism_config


def _mini_base():
    base = load_organism_config(
        "experiments/configs/organism_organ_network_combined.json").to_config_dict()
    base["duration_years"] = 30.0
    base["dt"] = 0.5
    base["seed"] = 42
    return base


def test_coordination_compare_mini_end_to_end(tmp_path):
    base = _mini_base()
    config = NetworkCoordinationCompareConfig(
        experiment_id="test_net_coord",
        seeds=(42, 7),
        coordination_modes=("independent_network", "cascade_guard"),
        base_organism_config=base,
        v4_criteria={},
        output_prefix=str(tmp_path / "coord"),
        notes="mini",
    )
    result = run_coordination_compare(config)
    assert result["immortality_status"] == "hypothesis_not_proven"
    assert set(result["modes"]) == {"cascade_guard", "independent_network"}
    for block in result["modes"].values():
        assert block["robust_v4"]["n_runs"] == 2
    # full config file loads
    loaded = load_organ_network_config(
        "experiments/configs/organism_organ_network_coordination_compare.json")
    assert isinstance(loaded, NetworkCoordinationCompareConfig)


def test_resource_sensitivity_mini_end_to_end(tmp_path):
    base = _mini_base()
    config = NetworkResourceSensitivityConfig(
        experiment_id="test_net_res",
        seeds=(42, 7),
        resource_axes={"repair": [4.0, 8.0]},
        base_organism_config=base,
        v4_criteria={},
        output_prefix=str(tmp_path / "res"),
        notes="mini",
    )
    result = run_resource_sensitivity(config)
    assert len(result["points"]) == 2
    assert "repair" in result["boundary"]
    for point in result["points"]:
        assert point["mean_lifespan"] == point["mean_lifespan"]


def test_hard_limit_sensitivity_mini_end_to_end(tmp_path):
    base = _mini_base()
    config = HardLimitSensitivityConfig(
        experiment_id="test_net_hl",
        seeds=(42, 7),
        hard_limit_axes={"max_mutation_load": [0.5, 2.0]},
        base_organism_config=base,
        v4_criteria={},
        output_prefix=str(tmp_path / "hl"),
        notes="mini",
    )
    result = run_hard_limit_sensitivity(config)
    assert len(result["points"]) == 2
    assert all("robust_v4" in p for p in result["points"])
    loaded = load_organ_network_config(
        "experiments/configs/organism_organ_network_hard_limit_sensitivity.json")
    assert isinstance(loaded, HardLimitSensitivityConfig)


def test_policy_search_mini_end_to_end():
    from longevity.experiment.organism_policy_search import (
        OrganismPolicySearchConfig,
        run_policy_search,
    )
    base = _mini_base()
    config = OrganismPolicySearchConfig(
        experiment_id="test_net_search",
        seeds=(42, 7),
        method="grid",
        random_seed=0,
        n_random=2,
        hill_steps=1,
        top_k=2,
        search_space={"policies.0.intensity": [0.5, 1.0]},
        fitness_weights={},
        base_organism_config=base,
        output_prefix="",
        notes="mini",
    )
    result = run_policy_search(config)
    assert result["n_evaluated"] == 2
    assert "robust_v4" in result["ranked"][0]
    assert result["immortality_status"] == "hypothesis_not_proven"


def test_stress_mini_end_to_end():
    from longevity.experiment.organism_robust import OrganismRobustConfig, run_robust_evaluation
    base = _mini_base()
    config = OrganismRobustConfig(
        experiment_id="test_net_stress",
        seeds=(42, 7),
        scenarios=("nominal", "noise_and_shocks"),
        runs={"combined": base},
        scenario_overrides={},
        robust_criteria={},
        output_prefix="",
        notes="mini",
    )
    result = run_robust_evaluation(config)
    assert len(result["cells"]) == 2
    assert result["immortality_status"] == "hypothesis_not_proven"


def test_config_files_load():
    for name, kind in (
        ("organism_organ_network_coordination_compare.json", "coordination_compare"),
        ("organism_organ_network_resource_sensitivity_sweep.json", "resource_sensitivity"),
        ("organism_organ_network_hard_limit_sensitivity.json", "hard_limit_sensitivity"),
    ):
        cfg = load_organ_network_config(f"experiments/configs/{name}")
        assert cfg.to_config_dict()["kind"] == kind
    # runner-level configs load
    for name in ("organism_organ_network_baseline.json", "organism_organ_network_combined.json",
                 "organism_organ_network_robust_search_mini.json", "organism_organ_network_stress.json"):
        load_organism_config(f"experiments/configs/{name}") if "stress" not in name and "search" not in name \
            else None
    from longevity.experiment.organism_policy_search import load_policy_search_config
    from longevity.experiment.organism_robust import load_robust_config
    load_policy_search_config("experiments/configs/organism_organ_network_robust_search_mini.json")
    load_robust_config("experiments/configs/organism_organ_network_stress.json")
