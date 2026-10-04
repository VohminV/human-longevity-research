"""Stage 5A: organism life-course model -- stages, vitals, death by failure."""

import copy
import json
import math
import random

import pytest

from longevity.model.organism import (
    DEFAULT_ORGANISM_THRESHOLDS,
    DEFAULT_STAGE_BOUNDS,
    MODEL_SCOPE,
    ORGANISM_MODEL_VERSION,
    STAGES,
    VITAL_SYSTEMS,
    OrganismModel,
    OrganismState,
    VitalSystemState,
    assert_organism_invariants,
    organism_invariant_violation,
    stage_for_age,
    validate_organism_parameters,
    validate_organism_thresholds,
    validate_stage_bounds,
)
from longevity.sim.rng import Rng

BOUNDS = validate_stage_bounds(dict(DEFAULT_STAGE_BOUNDS))
THRESHOLDS = validate_organism_thresholds(dict(DEFAULT_ORGANISM_THRESHOLDS))


def test_stages_monotone_and_named():
    assert STAGES.index("embryo") < STAGES.index("adult_homeostasis") < STAGES.index("late_aging")
    assert stage_for_age(0.1, BOUNDS) == "embryo"
    assert stage_for_age(30.0, BOUNDS) == "adult_homeostasis"
    assert stage_for_age(60.0, BOUNDS) == "early_aging"
    assert stage_for_age(100.0, BOUNDS) == "late_aging"
    with pytest.raises(ValueError):
        validate_stage_bounds({**DEFAULT_STAGE_BOUNDS, "age_fetal_end": 0.1})
    with pytest.raises(ValueError):
        validate_stage_bounds({"age_embryo_end": 1.0})


def test_thresholds_validation():
    assert validate_organism_thresholds(dict(DEFAULT_ORGANISM_THRESHOLDS)) == dict(DEFAULT_ORGANISM_THRESHOLDS)
    with pytest.raises(ValueError):
        validate_organism_thresholds({"min_vitality": 0.3})
    with pytest.raises(ValueError):
        validate_organism_thresholds({**DEFAULT_ORGANISM_THRESHOLDS, "min_vitality": 2.0})
    with pytest.raises(ValueError):
        validate_organism_thresholds({**DEFAULT_ORGANISM_THRESHOLDS, "bogus": 1.0})


def test_state_invariants_and_roundtrip():
    state = OrganismModel.default_state()
    assert organism_invariant_violation(state) is None
    assert set(state.systems) == set(VITAL_SYSTEMS)
    restored = OrganismState.from_dict(json.loads(json.dumps(state.to_dict())))
    assert restored.to_dict() == state.to_dict()
    bad = OrganismState.from_dict(state.to_dict())
    bad.systems["hepatic"]["function"] = -1.0
    assert organism_invariant_violation(bad) is not None
    with pytest.raises(ValueError):
        VitalSystemState(name="brain_cns", failure_threshold=0.9, warning_threshold=0.4)


def test_determinism_same_seed_and_checkpoint():
    first = OrganismModel(seed=42)
    first.run(30.0, 0.5, BOUNDS, THRESHOLDS, None)
    second = OrganismModel(seed=42)
    second.run(30.0, 0.5, BOUNDS, THRESHOLDS, None)
    assert first.state.to_dict() == second.state.to_dict()
    assert first.step_count == second.step_count
    snapshot = first.to_checkpoint_dict()
    first.run(20.0, 0.5, BOUNDS, THRESHOLDS, None)
    revived = OrganismModel.from_checkpoint(json.loads(json.dumps(snapshot)))
    revived.run(20.0, 0.5, BOUNDS, THRESHOLDS, None)
    assert revived.state.to_dict() == first.state.to_dict()
    json.dumps(snapshot)


def test_global_random_untouched():
    before = random.getstate()
    OrganismModel(seed=3).run(10.0, 0.5, BOUNDS, THRESHOLDS, None)
    assert random.getstate() == before


def test_life_course_reaches_adult_then_aging_and_dies_by_vitals():
    model = OrganismModel(seed=42)
    trajectory = model.run(150.0, 0.25, BOUNDS, THRESHOLDS, None)
    stages = [row["developmental_stage"] for row in trajectory]
    assert "adult_homeostasis" in stages
    assert stages.index("adult_homeostasis") < len(stages) - 1
    assert model.state.alive is False
    assert model.state.failure_cause != "none"
    assert model.state.death_time is not None and model.state.death_time > 20.0
    assert model.state.death_time <= 150.0


def test_parameters_validation():
    assert validate_organism_parameters({})["damage_rate"] >= 0.0
    with pytest.raises(ValueError):
        validate_organism_parameters({"damage_rate": -1.0})
    with pytest.raises(ValueError):
        validate_organism_parameters({"telepathy": 1.0})
    with pytest.raises(ValueError):
        validate_organism_parameters({"damage_rate": float("nan")})


def test_no_nan_or_inf_on_long_run():
    model = OrganismModel(seed=11)
    trajectory = model.run(150.0, 0.25, BOUNDS, THRESHOLDS, None)

    def _walk(node, path="$"):
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            assert math.isfinite(float(node)), f"non-finite at {path}"
        elif isinstance(node, dict):
            for key, value in node.items():
                _walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                _walk(value, f"{path}[{index}]")

    _walk(trajectory[-1])
    assert model.state.to_dict()["systems"]["brain_cns"]["informational_continuity"] <= 1.0
