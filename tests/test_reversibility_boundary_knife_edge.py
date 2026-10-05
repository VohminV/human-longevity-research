"""Stage 6E: knife-edge conversion probe (ultra-low band, deterministic)."""

import math

from longevity.analysis.boundary_metrics import classify_compound_wall
from longevity.experiment.organism_boundary import (
    BoundarySweepConfig,
    load_boundary_config,
    run_boundary_sweep,
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


def test_knife_edge_single_point_finite_and_deterministic():
    from longevity.experiment.organism_runner import (
        OrganismExperimentConfig,
        run_organism_experiment,
    )

    base = _mini_base()
    base["boundary_params"] = {"conversion_scale": 0.0001, "independent_accrual_scale": 0.0}
    first = run_organism_experiment(OrganismExperimentConfig.from_config_dict(base))
    second = run_organism_experiment(OrganismExperimentConfig.from_config_dict(base))
    assert first["trajectory"] == second["trajectory"]
    final = first["metrics"]["final"]
    for key in ("lifespan", "healthspan",
                "biological_age_slope_after_adulthood"):
        value = final[key]
        assert isinstance(value, float) and math.isfinite(value)
    rev = final["reversibility"]
    assert math.isfinite(rev["worst_irreversible_slope"])
    assert math.isfinite(rev["conversion_rate"])


def test_knife_edge_sweep_mini_reports_band():
    base = _mini_base()
    config = BoundarySweepConfig(
        kind="conversion_ultra_sweep",
        experiment_id="test_ke_band",
        seeds=(42, 7),
        param_axes={"conversion_scale": [0.0, 0.0001, 1.0]},
        extra_boundary_params={"independent_accrual_scale": 0.0},
        base_organism_config=base,
        v5_criteria={},
        output_prefix="",
        notes="mini",
    )
    result = run_boundary_sweep(config)
    assert len(result["points"]) == 3
    assert result["immortality_status"] == "hypothesis_not_proven"
    for point in result["points"]:
        assert math.isfinite(point["mean_lifespan"])
        assert isinstance(point["robust_v5"], bool)


def test_knife_edge_only_narrow_band_is_not_success():
    # v5 true only at 1e-4 while false at 0.0 and >=1e-3 must classify as
    # knife-edge, never as a robust success.
    out = classify_compound_wall(
        False,
        {"conversion_zero": False, "independent_zero": False,
         "both_suppressed": False, "high_ceiling": False, "unlimited_ceiling": False},
        {1e-6: False, 1e-5: False, 0.0001: True, 0.001: False},
        irr_suppressed=True, residual_binding="biological_age_slope",
        n_residual_sources=2,
        stability={"data_complete": True, "seed_stable": True,
                   "eps_stable": True, "dt_stable": True},
        exploratory_only=False)
    assert out["wall_classification"] == "knife_edge_parametric_wall"


def test_knife_edge_configs_load():
    cfg = load_boundary_config(
        "experiments/configs/organism_reversibility_boundary_knife_edge_sweep.json")
    assert isinstance(cfg, BoundarySweepConfig)
    assert 0.0001 in cfg.param_axes["conversion_scale"]
    single = load_organism_config(
        "experiments/configs/organism_reversibility_boundary_knife_edge_conversion_1e-4.json")
    assert single.to_config_dict()["boundary_params"]["conversion_scale"] == 0.0001
