"""Stage 6A: organ summaries, resource summaries, cross-scale binding, v3."""

import copy

import pytest

from longevity.analysis.organ_backed_metrics import (
    cross_scale_binding,
    robust_bounded_degradation_v3,
    summarize_organ_backed_run,
    summarize_organs,
    summarize_resources,
    validate_v3_criteria,
)
from longevity.model.aging import AGING_DRIVERS
from longevity.model.organ_backed import ORGAN_PROXIES, SYSTEMIC_RESOURCES


def _proxy(pid, function=0.9):
    return {"organ_id": pid, "mapped_vital_systems": [], "function": function,
            "reserve": 0.5, "damage": 0.1, "senescence_burden": 0.05,
            "fibrosis": 0.05, "cancer_risk": 0.05, "ecm_quality": 0.9,
            "vascular_quality": 0.9, "immune_pressure": 0.05,
            "vascular_capacity": 1.0, "immune_capacity": 1.0,
            "repair_capacity": 0.005, "recovery_pending": 0.0,
            "recent_activity": 0.0, "recovery_efficiency": 0.5,
            "turnover_rate": 0.003, "replacement_tolerance": 0.6,
            "informational_continuity": 1.0 if pid == "brain_cns_proxy" else None}


def _row(age, bio=30.0, function=0.9, allocation=1.0, driver_damage=0.1,
         burden=0.1, continuity=0.9, n_interventions=0):
    if isinstance(function, dict):
        proxies = {pid: _proxy(pid, function.get(pid, 0.9)) for pid in ORGAN_PROXIES}
    else:
        proxies = {pid: _proxy(pid, function) for pid in ORGAN_PROXIES}
    return {
        "chronological_age": age, "developmental_stage": "adult_homeostasis",
        "biological_age": bio, "global_damage": 0.1,
        "cancer_burden": burden, "inflammation": burden, "fibrosis": burden,
        "systems": {"brain_cns": {"function": 0.9, "informational_continuity": continuity,
                                  "failure_threshold": 0.25, "critical": True}},
        "intervention_history": [{}] * n_interventions,
        "aging": {"drivers": {name: {"damage": driver_damage} for name in AGING_DRIVERS},
                  "age_reversal_events": []},
        "organ_backed": {
            "proxies": proxies,
            "resources": {
                "budgets": {r: 8.0 for r in SYSTEMIC_RESOURCES},
                "allocation": {r: allocation for r in SYSTEMIC_RESOURCES},
                "demand": {r: 4.0 for r in SYSTEMIC_RESOURCES},
                "shortfall": {r: 0.0 for r in SYSTEMIC_RESOURCES}},
            "coordination_queue": [],
            "coordination_stats": {"executed": 0, "scaled": 0, "deferred": 0,
                                  "rejected": 0, "recovered_from_queue": 0}},
    }


def _trajectory(n=8, **kwargs):
    rows = [_row(20.0)]
    for i in range(n):
        rows.append(_row(30.0 + i, **kwargs))
    return rows


def test_neutral_blocks_without_organ_backed():
    rows = [{"chronological_age": 30.0 + i, "developmental_stage": "adult_homeostasis"}
            for i in range(4)]
    assert summarize_organs(rows)["has_organs"] is False
    assert summarize_resources(rows, 0.25)["has_resources"] is False
    with pytest.raises(ValueError):
        summarize_organs([])
    with pytest.raises(ValueError):
        summarize_resources([], 0.25)


def test_healthy_trajectory_has_no_binding_constraint():
    trajectory = _trajectory()
    binding = cross_scale_binding(trajectory)
    assert binding["first_cross_scale_constraint_violated"] == "none"
    assert binding["cross_scale_binding_constraint_sequence"] == []
    assert binding["dominant_binding_level"] == "none"
    assert binding["time_to_first_cross_scale_constraint_violation"] is None
    before = copy.deepcopy(trajectory)
    cross_scale_binding(before)
    assert before == trajectory  # never mutates inputs
    with pytest.raises(ValueError):
        cross_scale_binding([])


def test_declining_organ_binds_before_resources():
    trajectory = _trajectory()
    for i, row in enumerate(trajectory[1:], start=1):
        row["organ_backed"]["proxies"]["hepatic_proxy"]["function"] = 0.9 - 0.1 * i
    binding = cross_scale_binding(trajectory)
    assert binding["first_cross_scale_constraint_violated"] == "organ_function_margin"
    assert binding["dominant_binding_level"] == "organ_function"
    assert binding["dominant_binding_organ"] == "hepatic_proxy"
    assert binding["time_to_first_cross_scale_constraint_violation"] is not None


def test_resource_shortage_level_and_ties():
    trajectory = _trajectory(allocation=0.3)
    binding = cross_scale_binding(trajectory)
    assert binding["first_cross_scale_constraint_violated"] == "global_resource_shortage"
    assert binding["dominant_binding_level"] == "systemic_resource"
    # All resources tie at 0.3: deterministic alphabetical pick.
    assert binding["dominant_binding_resource"] == "immune"
    organs = summarize_organs(trajectory)
    assert organs["dominant_binding_organ"] in ORGAN_PROXIES


def test_bio_slope_still_first_in_canonical_order():
    rows = _trajectory()
    for i, row in enumerate(rows[1:]):
        row["biological_age"] = 30.0 + 2.0 * i  # steep bio climb
        row["organ_backed"]["proxies"]["hepatic_proxy"]["function"] = 0.1  # also failing
    binding = cross_scale_binding(rows)
    assert binding["first_cross_scale_constraint_violated"] == "biological_age_slope"
    assert "organ_function_margin" in binding["cross_scale_binding_constraint_sequence"]


def _v3_summary(**overrides):
    summary = {
        "biological_age_slope_after_adulthood": 0.01,
        "drivers": {"has_drivers": True, "worst_driver_slope": 0.001},
        "organs": {"has_organs": True, "worst_organ_function_slope": -0.001,
                   "min_function_by_organ": {pid: 0.8 for pid in ORGAN_PROXIES},
                   "organ_reserve_final_by_organ": {pid: 0.4 for pid in ORGAN_PROXIES},
                   "informational_continuity_min": 0.9, "failed_organ_ids": []},
        "systemic_resources": {"has_resources": True, "worst_resource_slope": -0.001,
                               "min_allocation_by_resource": {r: 0.9 for r in SYSTEMIC_RESOURCES},
                               "total_shortfall_auc": 1.0},
        "lifespan": 120.0, "cancer_auc": 10.0, "inflammation_auc": 5.0,
        "fibrosis_auc": 2.0, "informational_continuity_min": 0.9,
        "n_interventions": 40, "terminal_decline_reached": False,
    }
    summary.update(overrides)
    return summary


def test_v3_healthy_passes_and_failures_fail():
    assert robust_bounded_degradation_v3([_v3_summary() for _ in range(3)])[
        "robust_bounded_degradation_v3"] is True
    declining_organ = _v3_summary(organs=dict(
        _v3_summary()["organs"], worst_organ_function_slope=-0.5))
    assert robust_bounded_degradation_v3([declining_organ])[
        "robust_bounded_degradation_v3"] is False
    runaway_resource = _v3_summary(systemic_resources=dict(
        _v3_summary()["systemic_resources"], worst_resource_slope=-0.5))
    assert robust_bounded_degradation_v3([runaway_resource])[
        "robust_bounded_degradation_v3"] is False
    # v2-true but organ-failing input must fail v3.
    assert robust_bounded_degradation_v3([_v3_summary(
        organs=dict(_v3_summary()["organs"],
                    min_function_by_organ={pid: 0.1 for pid in ORGAN_PROXIES}))])[
        "robust_bounded_degradation_v3"] is False
    missing = _v3_summary(organs={"has_organs": False})
    assert robust_bounded_degradation_v3([missing])[
        "robust_bounded_degradation_v3"] is False
    declined = _v3_summary(terminal_decline_reached=True)
    assert robust_bounded_degradation_v3([declined])[
        "robust_bounded_degradation_v3"] is False
    with pytest.raises(ValueError):
        robust_bounded_degradation_v3([])


def test_v3_criteria_validation():
    assert validate_v3_criteria({})["min_success_rate"] == pytest.approx(0.8)
    with pytest.raises(ValueError):
        validate_v3_criteria({"no_such_key": 1.0})
    with pytest.raises(ValueError):
        validate_v3_criteria({"eps_bio": -1.0})


def test_run_summary_shape():
    summary = summarize_organ_backed_run(_trajectory())
    assert summary["organs"]["has_organs"] is True
    assert summary["systemic_resources"]["has_resources"] is True
    assert summary["cross_scale"]["first_cross_scale_constraint_violated"] == "none"
    assert set(summary["organs"]["final_function_by_organ"]) == set(ORGAN_PROXIES)
