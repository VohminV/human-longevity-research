import json

import pytest

from longevity.experiment.config import ExperimentConfig
from longevity.experiment.runner import run_experiment

SLOW = {"doubling_time_mean": 10.8, "doubling_time_sd": 1.2}


def make_config(**overrides) -> ExperimentConfig:
    base = {
        "experiment_id": "exp-test-1",
        "seed": 42,
        "population": 1,
        "duration": 20.0,
        "model_version": "0.1.0",
        "data_version": "0.0.1",
        "parameters": {},
        "interventions": [],
        "metrics_config": {},
    }
    base.update(overrides)
    return ExperimentConfig(**base)


def test_config_validation():
    with pytest.raises(ValueError):
        make_config(seed=1.5)
    with pytest.raises(ValueError):
        make_config(population=0)
    with pytest.raises(ValueError):
        make_config(duration=-1.0)
    with pytest.raises(ValueError):
        make_config(experiment_id="")
    with pytest.raises(ValueError):
        make_config(model_version="")
    with pytest.raises(ValueError):
        make_config(data_version="")
    with pytest.raises(ValueError):
        make_config(parameters={"bogus": 1})
    with pytest.raises(ValueError):
        make_config(interventions=[{"parameter": "telomere.loss_per_division"}])
    with pytest.raises(ValueError):
        make_config(metrics_config={"sample_interval": 0})


def test_config_roundtrip():
    config = make_config(notes="hello")
    assert ExperimentConfig.from_config_dict(config.to_config_dict()) == config


def test_effective_parameters_with_intervention():
    config = make_config(interventions=[{"parameter": "telomere.loss_per_division", "value": 2}])
    effective = config.effective_parameters()
    assert effective["telomere"]["loss_per_division"] == 2
    assert config.parameters == {}
    assert "telomere" not in config.parameters


def test_run_experiment_schema(tmp_path):
    config = make_config(metrics_config={"sample_interval": 5.0})
    out_path = str(tmp_path / "result.json")
    result = run_experiment(config, out_path=out_path)

    keys = {"experiment_id", "config", "metrics", "summary", "runtime", "rng_summary"}
    assert keys <= set(result)
    assert result["experiment_id"] == "exp-test-1"
    assert result["rng_summary"]["rng_seed_confirmed"] is True
    assert result["config"]["effective_parameters"]["doubling_time_mean"] == 10.8
    assert len(result["metrics"]["series"]) >= 4

    import pathlib

    written = json.loads(pathlib.Path(out_path).read_text(encoding="utf-8"))
    assert written["metrics"]["final"] == result["metrics"]["final"]
    assert written["summary"] == result["summary"]


def test_run_experiment_is_deterministic(tmp_path):
    first = run_experiment(make_config(), out_path=str(tmp_path / "a.json"))
    second = run_experiment(make_config(), out_path=str(tmp_path / "b.json"))
    assert first["metrics"] == second["metrics"]
    assert first["summary"] == second["summary"]
    assert first["rng_summary"] == second["rng_summary"]


def test_baseline_vs_intervention_telomere():
    base_params = {"doubling_time_mean": 2.0, "doubling_time_sd": 0.0}
    baseline = run_experiment(
        make_config(duration=12.0, population=1, parameters=base_params)
    )
    intervention = run_experiment(
        make_config(
            duration=12.0,
            population=1,
            parameters=base_params,
            interventions=[
                {"parameter": "telomere.length_start", "value": 4.0},
                {"parameter": "telomere.loss_per_division", "value": 1.0},
            ],
        )
    )
    assert baseline["summary"]["final_senescent"] == 0
    assert intervention["summary"]["final_senescent"] > 0
    assert intervention["summary"]["final_population"] < baseline["summary"]["final_population"]
    assert intervention["config"]["parameters"] == base_params