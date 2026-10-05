"""Stage 6E: eps/dt/seed sensitivity of the wall verdict."""

import math

from longevity.analysis.boundary_metrics import compute_eps_sensitivity
from longevity.experiment.organism_boundary import (
    SensitivityConfig,
    load_boundary_config,
    run_sensitivity,
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


def test_eps_sensitivity_mini_reuses_trajectories():
    from longevity.experiment.organism_runner import (
        OrganismExperimentConfig,
        run_organism_experiment,
    )

    base = _mini_base()
    summaries = [run_organism_experiment(
        OrganismExperimentConfig.from_config_dict({**base, "seed": seed})
    )["metrics"]["final"] for seed in (42, 7)]
    out = compute_eps_sensitivity(summaries, [0.002, 0.004, 0.008])
    assert out["eps_values"] == [0.002, 0.004, 0.008]
    assert set(out["verdict_by_eps"]) == {"0.002", "0.004", "0.008"}
    assert isinstance(out["eps_stable"], bool)
    assert out["reason"] != ""


def test_eps_sensitivity_rejects_bad_inputs():
    import pytest

    with pytest.raises(ValueError):
        compute_eps_sensitivity([], [0.004])
    with pytest.raises(ValueError):
        compute_eps_sensitivity([{"lifespan": 1.0}], [])


def test_sensitivity_runner_mini_end_to_end(tmp_path):
    base = _mini_base()
    config = SensitivityConfig(
        experiment_id="test_6e_sens",
        seeds=(42, 7),
        eps_values=(0.002, 0.008),
        dts=(0.5, 0.25),
        ablations={"default": {}, "conversion_zero": {"conversion_scale": 0.0}},
        base_organism_config=base,
        v5_criteria={},
        output_prefix=str(tmp_path / "sens"),
        notes="mini",
    )
    result = run_sensitivity(config)
    assert len(result["cells"]) == 2 * 2 * 2
    assert result["immortality_status"] == "hypothesis_not_proven"
    assert isinstance(result["eps_stable"], bool)
    assert isinstance(result["dt_stable"], bool)
    assert isinstance(result["seed_stable"], bool)
    assert result["compound_wall"]["wall_classification"] != ""
    for cell in result["cells"].values():
        assert math.isfinite(cell["success_rate_v5"])


def test_sensitivity_config_loads():
    cfg = load_boundary_config(
        "experiments/configs/organism_reversibility_boundary_sensitivity.json")
    assert isinstance(cfg, SensitivityConfig)
    assert cfg.eps_values == (0.002, 0.004, 0.008)
