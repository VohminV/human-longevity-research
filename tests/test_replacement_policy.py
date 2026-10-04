"""Stage 3A: replacement planning logic and policy-vs-baseline experiments."""

import pytest

from longevity.analysis.tissue_metrics import compare_against_baseline, compute_tissue_summary
from longevity.experiment.tissue_runner import TissueExperimentConfig, run_tissue_experiment
from longevity.model.policy import ReplacementPlan, ReplacementPolicy
from longevity.model.tissue import TissueModel, TissueState
from longevity.sim.rng import Rng

BASELINE_POLICY = {
    "name": "disabled",
    "enabled": False,
    "target": "none",
    "source": "none",
    "frequency": 5,
    "max_replacement_fraction": 0.0,
    "preserve_architecture": 1.0,
    "immune_compatibility": 1.0,
    "cancer_control": 1.0,
}

MODERATE_POLICY = {
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

AGGRESSIVE_POLICY = {
    "name": "aggressive",
    "enabled": True,
    "target": "senescent",
    "source": "stem_pool",
    "frequency": 1,
    "max_replacement_fraction": 0.8,
    "preserve_architecture": 0.4,
    "immune_compatibility": 0.4,
    "cancer_control": 0.4,
}

STEPS = 200


def _metrics(policy_dict, seed: int = 42) -> dict:
    model = TissueModel(rng=Rng(seed))
    policy = ReplacementPolicy.from_dict(policy_dict)
    trajectory = model.run(STEPS, policy)
    return compute_tissue_summary(
        trajectory, model.parameters["dt"], model.replacement_events, model.total_replaced_cells
    )


def test_disabled_policy_equals_baseline():
    with_policy = _metrics(BASELINE_POLICY)
    model = TissueModel(rng=Rng(42))
    trajectory = model.run(STEPS, None)
    without_policy = compute_tissue_summary(
        trajectory, model.parameters["dt"], model.replacement_events, model.total_replaced_cells
    )
    assert with_policy == without_policy
    assert with_policy["replacement_events"] == 0
    assert with_policy["total_replaced_cells"] == 0.0


def test_senescent_replacement_reduces_senescent_burden():
    baseline = _metrics(BASELINE_POLICY)
    moderate = _metrics(MODERATE_POLICY)
    assert moderate["final_senescent_cells"] < baseline["final_senescent_cells"]
    assert moderate["area_under_senescent_curve"] < baseline["area_under_senescent_curve"]
    assert moderate["total_replaced_cells"] > 0.0
    assert moderate["replacement_events"] > 0


def test_aggressive_replacement_shows_cost():
    moderate = _metrics(MODERATE_POLICY)
    aggressive = _metrics(AGGRESSIVE_POLICY)
    baseline = _metrics(BASELINE_POLICY)
    costs = (
        aggressive["max_cancer_risk"] > moderate["max_cancer_risk"]
        or aggressive["final_fibrosis_index"] > moderate["final_fibrosis_index"]
        or aggressive["final_immune_pressure"] > moderate["final_immune_pressure"]
        or aggressive["final_ecm_quality"] < moderate["final_ecm_quality"]
    )
    assert costs, "aggressive policy must cost somewhere vs moderate"
    # Aggression still clears senescent burden relative to doing nothing.
    assert aggressive["final_senescent_cells"] < baseline["final_senescent_cells"]


def test_planning_does_not_mutate_state():
    model = TissueModel(rng=Rng(3))
    model.run(37, None)
    before = model.state.to_dict()
    policy = ReplacementPolicy.from_dict(MODERATE_POLICY)
    plan = policy.plan(model.state, model.parameters, model.step_count)
    assert isinstance(plan, ReplacementPlan)
    assert model.state.to_dict() == before
    assert model.replacement_events == 0
    assert model.total_replaced_cells == 0.0


def test_plan_respects_frequency_and_empty_pool():
    policy = ReplacementPolicy.from_dict(MODERATE_POLICY)
    model = TissueModel(rng=Rng(0))
    assert policy.is_due(5) is True
    assert policy.is_due(6) is False
    assert policy.plan(model.state, model.parameters, 6).target_count == 0.0
    model.state.senescent_cells = 0.0
    assert policy.plan(model.state, model.parameters, 5).target_count == 0.0


def test_plan_counts_match_fraction_of_target_pool():
    policy = ReplacementPolicy.from_dict(MODERATE_POLICY)
    state = TissueState(senescent_cells=1000.0, stem_cells=10_000.0)
    model = TissueModel(state=state, rng=Rng(0))
    plan = policy.plan(model.state, model.parameters, step_count=5)
    assert plan.target_count == pytest.approx(200.0)
    assert plan.source_count == pytest.approx(200.0)
    for field in (
        "expected_architecture_cost",
        "expected_immune_cost",
        "expected_cancer_risk_delta",
        "expected_fibrosis_delta",
    ):
        assert getattr(plan, field) >= 0.0


def test_enabled_policy_requires_target_and_source():
    with pytest.raises(ValueError):
        ReplacementPolicy.from_dict({**MODERATE_POLICY, "target": "none"})
    with pytest.raises(ValueError):
        ReplacementPolicy.from_dict({**MODERATE_POLICY, "source": "none"})
    with pytest.raises(ValueError):
        ReplacementPolicy.from_dict({**MODERATE_POLICY, "target": "brain"})
    with pytest.raises(ValueError):
        ReplacementPolicy.from_dict({**MODERATE_POLICY, "frequency": 0})


def test_tissue_experiment_runner_schema_and_metrics(tmp_path):
    base = {
        "experiment_id": "tissue-test",
        "seed": 42,
        "steps": 50,
        "model_version": "0.3.0",
        "data_version": "0.1.0",
        "initial_state": {},
        "tissue_parameters": {},
        "policy": MODERATE_POLICY,
    }
    config = TissueExperimentConfig(**base)
    out_path = str(tmp_path / "tissue_result.json")
    result = run_tissue_experiment(config, out_path=out_path)

    assert set(result) >= {"experiment_id", "config", "trajectory", "metrics", "summary", "runtime", "rng_summary"}
    assert len(result["trajectory"]) == 51  # t0 + 50 steps
    required = {
        "final_functional_cells",
        "final_senescent_cells",
        "final_damaged_cells",
        "final_dead_cells",
        "area_under_senescent_curve",
        "area_under_damage_curve",
        "max_cancer_risk",
        "final_fibrosis_index",
        "final_ecm_quality",
        "final_vascular_quality",
        "final_immune_pressure",
        "rejuvenation_delta",
        "replacement_events",
        "total_replaced_cells",
    }
    assert required <= set(result["metrics"]["final"])
    assert result["rng_summary"]["rng_seed_confirmed"] is True

    import json as _json
    import pathlib as _pathlib

    written = _json.loads(_pathlib.Path(out_path).read_text(encoding="utf-8"))
    assert written["metrics"] == result["metrics"]


def test_baseline_vs_intervention_comparison_helper():
    baseline = _metrics(BASELINE_POLICY)
    moderate = _metrics(MODERATE_POLICY)
    comparison = compare_against_baseline(moderate, baseline)
    assert comparison["senescent_reduction"] > 0.0
