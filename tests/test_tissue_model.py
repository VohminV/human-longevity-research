"""Stage 3A: tissue compartment dynamics, determinism, validation, checkpoint."""

import json
import math

import pytest

from longevity.model.policy import ReplacementPolicy
from longevity.model.tissue import (
    TissueModel,
    TissueState,
    assert_tissue_invariants,
    tissue_invariant_violation,
    validate_tissue_parameters,
)
from longevity.sim.rng import Rng

MODERATE = {
    "name": "moderate",
    "enabled": True,
    "target": "senescent",
    "source": "stem_pool",
    "frequency": 5,
    "max_replacement_fraction": 0.2,
    "preserve_architecture": 0.9,
    "immune_compatibility": 0.9,
    "cancer_control": 0.9,
}


def _run(seed: int, steps: int, policy_dict=None, params=None) -> TissueModel:
    policy = ReplacementPolicy.from_dict(policy_dict) if policy_dict else None
    model = TissueModel(parameters=params, rng=Rng(seed))
    model.run(steps, policy)
    return model


def _snapshot(model: TissueModel) -> tuple:
    return (
        model.state.to_dict(),
        model.step_count,
        model.replacement_events,
        model.total_replaced_cells,
        model.rng.getstate(),
    )


def test_pools_non_negative_after_many_steps():
    for seed in (1, 7, 42, 99):
        model = _run(seed, 500, MODERATE)
        assert_tissue_invariants(model.state)
        for pool in ("stem_cells", "functional_cells", "damaged_cells", "senescent_cells", "dead_cells"):
            assert getattr(model.state, pool) >= 0.0


def test_no_nan_or_inf_after_many_steps():
    model = _run(42, 500, MODERATE)
    for name, value in model.state.to_dict().items():
        assert math.isfinite(value), f"{name} is not finite: {value!r}"


def test_same_seed_is_deterministic():
    assert _snapshot(_run(42, 200, MODERATE)) == _snapshot(_run(42, 200, MODERATE))


def test_state_serialization_roundtrip():
    model = _run(42, 100, MODERATE)
    restored = TissueState.from_dict(json.loads(json.dumps(model.state.to_dict())))
    assert restored.to_dict() == model.state.to_dict()
    assert tissue_invariant_violation(restored) is None


def test_checkpoint_restore_equivalence():
    original = TissueModel(rng=Rng(42))
    policy = ReplacementPolicy.from_dict(MODERATE)
    original.run(60, policy)
    snapshot = original.to_checkpoint_dict()
    original.run(140, policy)

    restored = TissueModel.from_checkpoint(json.loads(json.dumps(snapshot)))
    restored.run(140, policy)
    assert _snapshot(original) == _snapshot(restored)


def test_checkpoint_is_json_serializable():
    model = _run(9, 50, MODERATE)
    json.dumps(model.to_checkpoint_dict())


def test_replacement_cannot_exceed_available_cells():
    model = TissueModel(rng=Rng(0))
    model.state.senescent_cells = 10.0
    model.state.stem_cells = 1000.0
    policy = ReplacementPolicy.from_dict({**MODERATE, "max_replacement_fraction": 0.8})
    plan = policy.plan(model.state, model.parameters, step_count=5)
    assert plan.target_count == pytest.approx(8.0)
    # Oversized plan (e.g. forged or stale) is still capped at execution.
    plan.target_count = 10_000.0
    plan.source_count = 10_000.0
    replaced = model.apply_replacement_plan(plan)
    assert replaced == pytest.approx(10.0)
    assert model.state.senescent_cells == pytest.approx(0.0)
    assert_tissue_invariants(model.state)


def test_stem_pool_source_capped_by_stem_available():
    model = TissueModel(rng=Rng(0))
    model.state.senescent_cells = 1000.0
    model.state.stem_cells = 5.0
    policy = ReplacementPolicy.from_dict(MODERATE)
    plan = policy.plan(model.state, model.parameters, step_count=5)
    replaced = model.apply_replacement_plan(plan)
    assert replaced == pytest.approx(5.0)
    assert model.state.stem_cells == pytest.approx(0.0)


def test_negative_replacement_fraction_rejected():
    with pytest.raises(ValueError):
        ReplacementPolicy.from_dict({**MODERATE, "max_replacement_fraction": -0.1})


def test_invalid_tissue_parameters_rejected():
    with pytest.raises(ValueError):
        validate_tissue_parameters({"damage_rate": -0.1})
    with pytest.raises(ValueError):
        validate_tissue_parameters({"clearance_rate": 1.5})
    with pytest.raises(ValueError):
        validate_tissue_parameters({"bogus_param": 1.0})
    with pytest.raises(ValueError):
        validate_tissue_parameters({"damage_rate": float("nan")})


def test_invalid_initial_state_rejected():
    bad = TissueState(senescent_cells=-1.0)
    assert tissue_invariant_violation(bad) is not None
    with pytest.raises(AssertionError):
        TissueModel(state=bad)
    bad_quality = TissueState(ecm_quality=1.5)
    assert tissue_invariant_violation(bad_quality) is not None
