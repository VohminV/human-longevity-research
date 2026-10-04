"""Stage 5C: driver metrics, binding analysis, robust v2, reversal efficiency."""

import copy
import math

import pytest

from longevity.analysis.aging_metrics import (
    reversal_efficiency,
    robust_bounded_degradation_v2,
    summarize_drivers,
    validate_v2_criteria,
)
from longevity.experiment.organism_runner import load_organism_config, run_organism_experiment
from longevity.model.aging import AGING_DRIVERS


def _mech_trajectory(seed=42, years=150.0, policies=None):
    from longevity.model.intervention import PolicySet
    from longevity.model.organism import OrganismModel, validate_organism_thresholds, validate_stage_bounds
    from longevity.model.organism import DEFAULT_ORGANISM_THRESHOLDS, DEFAULT_STAGE_BOUNDS
    model = OrganismModel(seed=seed, aging_model="mechanistic_drivers", aging_drivers={})
    return model.run(years, 0.25, validate_stage_bounds(dict(DEFAULT_STAGE_BOUNDS)),
                     validate_organism_thresholds(dict(DEFAULT_ORGANISM_THRESHOLDS)),
                     PolicySet(policies) if policies else None)


def _healthy_drivers(n=8, slope=0.001):
    rows = []
    for i in range(n):
        drivers = {name: {"damage": 0.05 + slope * i} for name in AGING_DRIVERS}
        rows.append({"chronological_age": 30.0 + i, "developmental_stage": "adult_homeostasis",
                     "aging": {"drivers": drivers, "age_reversal_events": []}})
    return rows


def test_dominant_binding_driver_and_ties():
    trajectory = _healthy_drivers()
    summary = summarize_drivers(trajectory)
    assert summary["has_drivers"] is True
    assert summary["dominant_binding_driver"] in AGING_DRIVERS
    assert summary["binding_driver_sequence"][0] == summary["dominant_binding_driver"]
    before = copy.deepcopy(trajectory)
    summarize_drivers(before)
    assert before == trajectory  # never mutates inputs
    with pytest.raises(ValueError):
        summarize_drivers([])
    # No drivers present: neutral block.
    assert summarize_drivers([{"developmental_stage": "adult_homeostasis",
                               "chronological_age": 30.0}])["has_drivers"] is False


def test_v2_healthy_vs_declining_and_aggregate_slope():
    healthy = [{"bounded_degradation_indicator": True, "biological_age_slope_after_adulthood": 0.01,
                "final_function_by_system": {n: 0.9 for n in ("a", "b")}, "cancer_auc": 10.0,
                "inflammation_auc": 5.0, "fibrosis_auc": 2.0, "neural_identity_preservation": 0.95,
                "lifespan": 150.0, "terminal_decline_reached": False,
                "drivers": {"has_drivers": True, "worst_driver_slope": 0.001}} for _ in range(3)]
    result = robust_bounded_degradation_v2(healthy)
    assert result["robust_bounded_degradation_v2"] is True
    assert result["success_rate_bounded_v2"] == pytest.approx(1.0)
    declining = [dict(healthy[0], drivers={"has_drivers": True, "worst_driver_slope": 0.5})]
    result2 = robust_bounded_degradation_v2(declining)
    assert result2["robust_bounded_degradation_v2"] is False
    assert result2["worst_case_driver_slope"] == pytest.approx(0.5)
    nodrivers = [dict(healthy[0], drivers={"has_drivers": False})]
    assert robust_bounded_degradation_v2(nodrivers)["robust_bounded_degradation_v2"] is False
    with pytest.raises(ValueError):
        robust_bounded_degradation_v2([])
    with pytest.raises(ValueError):
        validate_v2_criteria({"eps_bio": -1.0})


def test_reversal_efficiency_counts():
    trajectory = _mech_trajectory()
    efficiency = reversal_efficiency(trajectory)
    assert set(efficiency) == {"reversal_applied_by_driver", "firings_by_driver",
                               "reversal_efficiency_by_driver"}
    with pytest.raises(ValueError):
        reversal_efficiency([])


def test_real_run_driver_block_and_v2():
    result = run_organism_experiment(load_organism_config(
        "experiments/configs/organism_aging_combined_mechanistic.json"))
    drivers = result["metrics"]["final"]["drivers"]
    assert drivers["has_drivers"] is True
    assert drivers["dominant_binding_driver"] in AGING_DRIVERS
    assert math.isfinite(drivers["worst_driver_slope"])
    assert result["summary"]["lifespan"] <= result["config"]["duration_years"] + 1e-9
