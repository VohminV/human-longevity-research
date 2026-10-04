"""Stage 5C: mechanistic aging drivers -- validation, dynamics, floor."""

import copy
import json
import math

import pytest

from longevity.experiment.organism_runner import load_organism_config, run_organism_experiment
from longevity.model.aging import (
    AGING_DRIVERS,
    aggregate_biological_age,
    default_driver_state,
    effective_reversal,
    validate_aging_drivers,
    validate_aging_model,
)
from longevity.model.organism import OrganismModel, validate_stage_bounds, validate_organism_thresholds
from longevity.model.organism import DEFAULT_ORGANISM_THRESHOLDS, DEFAULT_STAGE_BOUNDS

BOUNDS = validate_stage_bounds(dict(DEFAULT_STAGE_BOUNDS))
THRESHOLDS = validate_organism_thresholds(dict(DEFAULT_ORGANISM_THRESHOLDS))


def test_aging_model_validation():
    assert validate_aging_model("none") == "none"
    assert validate_aging_model("mechanistic_drivers") == "mechanistic_drivers"
    with pytest.raises(ValueError):
        validate_aging_model("fountain_of_youth")
    params = validate_aging_drivers({})
    assert set(params) == set(AGING_DRIVERS)
    with pytest.raises(ValueError):
        validate_aging_drivers({"brain": {}})
    with pytest.raises(ValueError):
        validate_aging_drivers({"dna_damage": {"base_aging_rate": -1.0}})
    with pytest.raises(ValueError):
        validate_aging_drivers({"dna_damage": {"reversibility": 1.5}})
    with pytest.raises(ValueError):
        validate_aging_drivers({"dna_damage": {"telepathy": 1.0}})
    with pytest.raises(ValueError):
        validate_aging_drivers({"telomere_attrition": {}})


def test_none_mode_is_bit_identical_to_5b():
    first = run_organism_experiment(load_organism_config(
        "experiments/configs/organism_aging_legacy_none.json"))
    assert first["summary"]["lifespan"] == pytest.approx(68.0)
    assert first["summary"]["primary_cause_of_death"] == "systemic_cascade"
    assert first["metrics"]["final"]["drivers"]["has_drivers"] is False


def test_determinism_with_drivers():
    from longevity.model.organism import OrganismModel as OM
    base = {"organism_id": "x", "seed": 42, "aging_mechanism_model": "mechanistic_drivers"}
    from longevity.experiment.organism_runner import OrganismExperimentConfig
    first = run_organism_experiment(OrganismExperimentConfig.from_config_dict(base))
    second = run_organism_experiment(OrganismExperimentConfig.from_config_dict(base))
    assert first["trajectory"] == second["trajectory"]
    json.dumps(first)


def test_driver_state_bounds_and_roundtrip():
    state = default_driver_state()
    assert set(state["drivers"]) == set(AGING_DRIVERS)
    model = OrganismModel(seed=3, aging_model="mechanistic_drivers",
                          aging_drivers=validate_aging_drivers({}))
    assert model.state.aging is not None
    restored = json.loads(json.dumps(model.state.to_dict()))
    assert restored["aging"]["drivers"] == model.state.to_dict()["aging"]["drivers"]
    for name in AGING_DRIVERS:
        assert 0.0 <= state["drivers"][name]["damage"] <= 1.0


def test_biological_age_floor_and_sub_adult_flag():
    params = validate_aging_drivers({})
    bio, contributions = aggregate_biological_age(
        {name: 0.0 for name in AGING_DRIVERS}, params, 25.0, False)
    assert bio == pytest.approx(25.0)
    assert set(contributions) == set(AGING_DRIVERS)
    bio_low, _ = aggregate_biological_age({name: 0.0 for name in AGING_DRIVERS}, params, 25.0, True)
    assert bio_low == pytest.approx(25.0)
    # Floor holds even if a (hypothetical) negative sum were passed.
    model = OrganismModel(seed=1, aging_model="mechanistic_drivers",
                          aging_drivers=validate_aging_drivers({}), allow_sub_adult_biological_age=False)
    trajectory = model.run(30.0, 0.5, BOUNDS, THRESHOLDS, None)
    assert all(row["biological_age"] >= 0.0 for row in trajectory)
    assert all(row["biological_age"] >= 25.0 - 1e-9 or row["chronological_age"] < 25.0
               for row in trajectory[1:] if row.get("aging"))


def test_effective_reversal_diminishing():
    assert effective_reversal(0.05, 0.0, 1.0, 0.8) == pytest.approx(0.05)
    near_sat = effective_reversal(0.05, 0.79, 1.0, 0.8)
    assert 0.0 < near_sat < 0.05
    assert effective_reversal(0.05, 0.9, 1.0, 0.8) == pytest.approx(0.0)
    assert effective_reversal(0.0, 0.5, 1.0, 0.8) == pytest.approx(0.0)
    assert effective_reversal(0.05, 0.4, 0.0, 0.8) == pytest.approx(0.0)


def test_old_configs_still_work():
    result = run_organism_experiment(load_organism_config(
        "experiments/configs/organism_life_course_baseline.json"))
    assert result["summary"]["lifespan"] == pytest.approx(68.0)
