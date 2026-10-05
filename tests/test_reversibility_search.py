"""Stage 6C: sweeps + mini search + stress end-to-end (small, fast)."""

from longevity.experiment.organism_reversibility import (
    ReversibilityCoordinationCompareConfig,
    ReversibilitySensitivityConfig,
    load_reversibility_config,
    run_coordination_compare,
    run_sensitivity,
)
from longevity.experiment.organism_runner import load_organism_config


def _mini_base():
    base = load_organism_config(
        "experiments/configs/organism_reversibility_combined_preventive_clearance.json").to_config_dict()
    base["duration_years"] = 30.0
    base["dt"] = 0.5
    base["seed"] = 42
    return base


def test_coordination_compare_mini_end_to_end(tmp_path):
    base = _mini_base()
    config = ReversibilityCoordinationCompareConfig(
        experiment_id="test_rev_coord",
        seeds=(42, 7),
        coordination_modes=("independent_reversibility", "repair_ceiling_guard"),
        base_organism_config=base,
        v5_criteria={},
        output_prefix=str(tmp_path / "coord"),
        notes="mini",
    )
    result = run_coordination_compare(config)
    assert result["immortality_status"] == "hypothesis_not_proven"
    assert set(result["modes"]) == {"independent_reversibility", "repair_ceiling_guard"}
    for block in result["modes"].values():
        assert block["robust_v5"]["n_runs"] == 2
    loaded = load_reversibility_config(
        "experiments/configs/organism_reversibility_coordination_compare.json")
    assert isinstance(loaded, ReversibilityCoordinationCompareConfig)


def test_repair_ceiling_sensitivity_mini(tmp_path):
    base = _mini_base()
    config = ReversibilitySensitivityConfig(
        kind="repair_ceiling_sensitivity",
        experiment_id="test_rev_ceiling",
        seeds=(42, 7),
        param_axes={"repair_ceiling": [0.1, 0.3]},
        base_organism_config=base,
        v5_criteria={},
        output_prefix=str(tmp_path / "ceil"),
        notes="mini",
    )
    result = run_sensitivity(config)
    assert len(result["points"]) == 2
    assert result["immortality_status"] == "hypothesis_not_proven"


def test_conversion_sensitivity_mini(tmp_path):
    base = _mini_base()
    config = ReversibilitySensitivityConfig(
        kind="conversion_sensitivity",
        experiment_id="test_rev_conv",
        seeds=(42, 7),
        param_axes={"base_conversion_rate": [0.005, 0.05]},
        base_organism_config=base,
        v5_criteria={},
        output_prefix=str(tmp_path / "conv"),
        notes="mini",
    )
    result = run_sensitivity(config)
    assert len(result["points"]) == 2


def test_info_mutation_sensitivity_mini(tmp_path):
    base = _mini_base()
    config = ReversibilitySensitivityConfig(
        kind="information_mutation_sensitivity",
        experiment_id="test_rev_im",
        seeds=(42, 7),
        param_axes={"max_information_debt": [0.3, 0.9]},
        base_organism_config=base,
        v5_criteria={},
        output_prefix=str(tmp_path / "im"),
        notes="mini",
    )
    result = run_sensitivity(config)
    assert len(result["points"]) == 2


def test_policy_search_mini_end_to_end():
    from longevity.experiment.organism_policy_search import (
        OrganismPolicySearchConfig,
        run_policy_search,
    )
    base = _mini_base()
    config = OrganismPolicySearchConfig(
        experiment_id="test_rev_search",
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
    assert "robust_v5" in result["ranked"][0]
    assert result["immortality_status"] == "hypothesis_not_proven"


def test_stress_mini_end_to_end():
    from longevity.experiment.organism_robust import OrganismRobustConfig, run_robust_evaluation
    base = _mini_base()
    config = OrganismRobustConfig(
        experiment_id="test_rev_stress",
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


def test_config_files_load():
    for name, kind in (
        ("organism_reversibility_coordination_compare.json", "coordination_compare"),
        ("organism_reversibility_repair_ceiling_sweep.json", "repair_ceiling_sensitivity"),
        ("organism_reversibility_conversion_sensitivity_sweep.json", "conversion_sensitivity"),
        ("organism_reversibility_information_mutation_sweep.json", "information_mutation_sensitivity"),
    ):
        cfg = load_reversibility_config(f"experiments/configs/{name}")
        assert cfg.to_config_dict()["kind"] == kind
    from longevity.experiment.organism_policy_search import load_policy_search_config
    from longevity.experiment.organism_robust import load_robust_config
    load_policy_search_config("experiments/configs/organism_reversibility_robust_search_mini.json")
    load_robust_config("experiments/configs/organism_reversibility_stress.json")
