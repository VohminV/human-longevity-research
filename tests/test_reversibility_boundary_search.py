"""Stage 6D: boundary sweeps + search + stress end-to-end (small, fast)."""

from longevity.experiment.organism_boundary import (
    BoundarySweepConfig,
    ComponentAttributionConfig,
    load_boundary_config,
    run_boundary_sweep,
    run_component_attribution,
)
from longevity.experiment.organism_runner import load_organism_config


def _mini_base():
    base = load_organism_config(
        "experiments/configs/organism_reversibility_combined_preventive_clearance.json").to_config_dict()
    base["duration_years"] = 30.0
    base["dt"] = 0.5
    base["seed"] = 42
    base["boundary_probe_model"] = "irreversibility_ablation"
    base["boundary_params"] = {}
    return base


def test_conversion_ultra_sweep_mini(tmp_path):
    base = _mini_base()
    config = BoundarySweepConfig(
        kind="conversion_ultra_sweep",
        experiment_id="test_b_conv",
        seeds=(42, 7),
        param_axes={"conversion_scale": [0.0, 1.0]},
        extra_boundary_params={},
        base_organism_config=base,
        v5_criteria={},
        output_prefix=str(tmp_path / "conv"),
        notes="mini",
    )
    result = run_boundary_sweep(config)
    assert len(result["points"]) == 2
    assert result["immortality_status"] == "hypothesis_not_proven"
    assert "v5_threshold" in result


def test_independent_ultra_sweep_mini(tmp_path):
    base = _mini_base()
    config = BoundarySweepConfig(
        kind="independent_ultra_sweep",
        experiment_id="test_b_ind",
        seeds=(42, 7),
        param_axes={"independent_accrual_scale": [0.0, 1.0]},
        extra_boundary_params={},
        base_organism_config=base,
        v5_criteria={},
        output_prefix=str(tmp_path / "ind"),
        notes="mini",
    )
    result = run_boundary_sweep(config)
    assert len(result["points"]) == 2


def test_ceiling_ultra_sweep_mini(tmp_path):
    base = _mini_base()
    config = BoundarySweepConfig(
        kind="ceiling_ultra_sweep",
        experiment_id="test_b_ceil",
        seeds=(42, 7),
        param_axes={"repair_ceiling_scale": [0.0, 1.0]},
        extra_boundary_params={},
        base_organism_config=base,
        v5_criteria={},
        output_prefix=str(tmp_path / "ceil"),
        notes="mini",
    )
    result = run_boundary_sweep(config)
    assert len(result["points"]) == 2


def test_component_attribution_mini(tmp_path):
    base = _mini_base()
    config = ComponentAttributionConfig(
        experiment_id="test_b_attr",
        seeds=(42, 7),
        ablations={"default": {}, "conversion_zero": {"conversion_scale": 0.0}},
        base_organism_config=base,
        v5_criteria={},
        output_prefix=str(tmp_path / "attr"),
        notes="mini",
    )
    result = run_component_attribution(config)
    assert set(result["entries"]) == {"default", "conversion_zero"}
    assert "wall_classification" in result
    assert result["wall_classification"]["wall_classification"] != ""


def test_boundary_search_mini():
    from longevity.experiment.organism_policy_search import (
        OrganismPolicySearchConfig,
        run_policy_search,
    )
    base = _mini_base()
    config = OrganismPolicySearchConfig(
        experiment_id="test_b_search",
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


def test_boundary_stress_mini():
    from longevity.experiment.organism_robust import OrganismRobustConfig, run_robust_evaluation
    base = _mini_base()
    config = OrganismRobustConfig(
        experiment_id="test_b_stress",
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
    for name in ("organism_reversibility_boundary_conversion_ultra_sweep.json",
                 "organism_reversibility_boundary_independent_ultra_sweep.json",
                 "organism_reversibility_boundary_ceiling_ultra_sweep.json"):
        cfg = load_boundary_config(f"experiments/configs/{name}")
        assert isinstance(cfg, BoundarySweepConfig)
    cfg = load_boundary_config("experiments/configs/organism_reversibility_boundary_component_attribution.json")
    assert isinstance(cfg, ComponentAttributionConfig)
    from longevity.experiment.organism_policy_search import load_policy_search_config
    from longevity.experiment.organism_robust import load_robust_config
    load_policy_search_config("experiments/configs/organism_reversibility_boundary_robust_search.json")
    load_robust_config("experiments/configs/organism_reversibility_boundary_stress.json")
