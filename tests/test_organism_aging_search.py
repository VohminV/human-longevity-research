"""Stage 5C: mechanistic search, binding sweep, stress, checkpoint, scope."""

import copy
import csv
import json
import math
import random

import pytest

from longevity.experiment.organism_aging import (
    load_aging_sweep_config,
    run_aging_sweep,
    write_aging_sweep_outputs,
)
from longevity.experiment.organism_runner import load_organism_config, run_organism_experiment
from longevity.model.organism import OrganismModel


def _tiny_sweep(**overrides):
    base = {
        "experiment_id": "aging-sweep-test",
        "seeds": [11, 12],
        "driver_axes": {"cellular_senescence.base_aging_rate": [0.002, 0.008],
                        "dna_damage.contribution": [10.0, 40.0]},
        "base_organism_config": {
            "organism_id": "sweep-base", "seed": 11, "duration_years": 150.0, "dt": 1.0,
            "aging_mechanism_model": "mechanistic_drivers",
            "policies": [],
        },
        "output_prefix": "",
        "notes": "",
    }
    base.update(overrides)
    from longevity.experiment.organism_aging import AgingDriverSweepConfig
    return AgingDriverSweepConfig.from_config_dict(base)


def test_binding_sweep_end_to_end_and_determinism(tmp_path):
    first = run_aging_sweep(_tiny_sweep())
    second = run_aging_sweep(_tiny_sweep())
    assert first["points"] == second["points"]
    assert first["config_hash"] == second["config_hash"]
    assert len(first["points"]) == 4  # 2 x 2 grid
    assert first["model_scope"] == "abstract_organism_life_course"
    paths = write_aging_sweep_outputs(first, str(tmp_path / "aging"))
    assert set(paths) == {"long_csv", "summary_csv", "summary_json", "binding_drivers_json",
                          "reversal_efficiency_json", "top_k_json", "pareto_front_json"}
    with open(paths["long_csv"], encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 4 * 2
    for key in ("summary_json", "binding_drivers_json", "reversal_efficiency_json",
                "top_k_json", "pareto_front_json"):
        with open(paths[key], encoding="utf-8") as fh:
            json.load(fh)
    json.dumps(first)


def test_binding_sweep_validation():
    with pytest.raises(ValueError):
        _tiny_sweep(seeds=[11])
    with pytest.raises(ValueError):
        _tiny_sweep(driver_axes={})
    with pytest.raises(ValueError):
        _tiny_sweep(driver_axes={"brain.base_aging_rate": [0.1]})
    with pytest.raises(ValueError):
        _tiny_sweep(driver_axes={"dna_damage.base_aging_rate": []})
    with pytest.raises(ValueError):
        _tiny_sweep(driver_axes={"dna_damage.telepathy": [0.1]})
    with pytest.raises(ValueError):
        _tiny_sweep(base_organism_config={})


def test_mechanistic_search_mini_and_stress(tmp_path):
    from longevity.experiment.organism_policy_search import load_policy_search_config, run_policy_search
    from longevity.experiment.organism_robust import load_robust_config, run_robust_evaluation
    search = run_policy_search(load_policy_search_config(
        "experiments/configs/organism_aging_robust_search_mini.json"))
    assert search["ranked"]
    assert all("worst_driver_slope" in entry for entry in search["ranked"])
    stress = run_robust_evaluation(load_robust_config(
        "experiments/configs/organism_aging_stress_mechanistic.json"))
    assert len(stress["cells"]) == 3 * 6
    assert stress["immortality_status"] == "hypothesis_not_proven"


def test_checkpoint_covers_drivers_cooldown_and_streams():
    holder_policies = [{
        "policy_id": "seno_t", "enabled": True, "start_age": 25.0, "stop_age": 150.0,
        "trigger_type": "threshold_based", "interval": 1.0, "intensity": 1.0,
        "intervention_type": "senolytic_clearance", "target_systems": [],
        "biomarker": "driver:cellular_senescence", "biomarker_threshold": 0.05}]
    from longevity.model.intervention import PolicySet
    from longevity.model.organism import validate_organism_thresholds, validate_stage_bounds
    from longevity.model.organism import DEFAULT_ORGANISM_THRESHOLDS, DEFAULT_STAGE_BOUNDS
    bounds = validate_stage_bounds(dict(DEFAULT_STAGE_BOUNDS))
    thresholds = validate_organism_thresholds(dict(DEFAULT_ORGANISM_THRESHOLDS))
    holder = PolicySet(holder_policies)
    model = OrganismModel(seed=42, aging_model="mechanistic_drivers", aging_drivers={})
    model.run(40.0, 0.5, bounds, thresholds, holder)
    snapshot = model.to_checkpoint_dict(holder.to_state_dict())
    assert snapshot["aging_drivers"]
    model.run(20.0, 0.5, bounds, thresholds, holder)
    revived = OrganismModel.from_checkpoint(json.loads(json.dumps(snapshot)))
    holder2 = PolicySet(holder_policies)
    holder2.load_state_dict(snapshot["policy_cooldown"])
    revived.run(20.0, 0.5, bounds, thresholds, holder2)
    assert revived.state.to_dict() == model.state.to_dict()
    assert revived.state.aging["drivers"] == model.state.aging["drivers"]


def test_global_random_untouched_by_aging_sweep():
    before = random.getstate()
    run_aging_sweep(_tiny_sweep())
    assert random.getstate() == before


def test_scope_and_no_bio_claims():
    result = run_organism_experiment(load_organism_config(
        "experiments/configs/organism_aging_combined_mechanistic.json"))
    assert result["model_scope"] == "abstract_organism_life_course"
    assert result["immortality_status"] == "hypothesis_not_proven"
    blob = json.dumps(result)
    for forbidden in ("human", "patient", "clinical"):
        assert forbidden not in blob.lower()
    assert "candidate_immortality_policy_found" not in blob  # no such claim field
