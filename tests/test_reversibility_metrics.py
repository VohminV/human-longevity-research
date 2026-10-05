"""Stage 6C: reversibility metrics + binding v4 + v5."""

import copy

import pytest

from longevity.analysis.reversibility_metrics import (
    reversibility_binding,
    robust_bounded_degradation_v5,
    summarize_reversibility,
    validate_v5_criteria,
)
from longevity.experiment.organism_runner import load_organism_config, run_organism_experiment


def _trajectory(config_name="experiments/configs/organism_reversibility_combined_preventive_clearance.json"):
    return run_organism_experiment(load_organism_config(config_name))["trajectory"]


def test_v5_criteria_validation():
    with pytest.raises(ValueError):
        validate_v5_criteria({"nope": 1.0})
    assert validate_v5_criteria(None)["eps_bio"] == pytest.approx(0.05)


def test_reversibility_summary_finite():
    traj = _trajectory()
    summary = summarize_reversibility(traj, 0.25)
    assert summary["has_reversibility"] is True
    for key in ("worst_reversible_slope", "worst_irreversible_slope",
                "conversion_rate", "biological_age_reversibility_slope"):
        value = summary[key]
        assert value == value and abs(value) < 1e6
    assert summary["repair_remaining_min"] >= 0.0
    assert 0.0 <= summary["information_debt_final"] <= 1.0


def test_binding_deterministic_and_levels():
    traj = _trajectory()
    first = reversibility_binding(traj)
    second = reversibility_binding(traj)
    assert first == second
    assert first["dominant_binding_level"] in (
        "biological_age", "biological_age_network", "biological_age_reversibility",
        "aging_driver", "reversible_burden", "irreversible_accumulation",
        "conversion_runaway", "repair_ceiling_exhaustion", "information_debt",
        "mutation_fixation", "niche_disorder", "entropy_production",
        "organ_function", "reserve", "systemic_resource", "network_edge",
        "feedback_loop", "hard_limit", "energy_budget", "cascade_risk",
        "cancer", "systemic_cascade", "organ_function", "intervention_cost", "none")
    assert "dominant_reversibility_wall" in first


def test_v5_false_on_current_policies():
    result = run_organism_experiment(
        load_organism_config("experiments/configs/organism_reversibility_combined_preventive_clearance.json"))
    summary = result["metrics"]["final"]
    verdict = robust_bounded_degradation_v5([summary, summary])
    assert verdict["robust_bounded_degradation_v5"] is False


def test_v5_requires_v4_plus_reversibility():
    result = run_organism_experiment(
        load_organism_config("experiments/configs/organism_reversibility_combined_preventive_clearance.json"))
    summary = result["metrics"]["final"]
    bad = copy.deepcopy(summary)
    bad["reversibility"]["conversion_runaway_flag"] = True
    bad["reversibility"]["conversion_rate"] = 5.0
    assert robust_bounded_degradation_v5([bad, bad])["robust_bounded_degradation_v5"] is False
    bad2 = copy.deepcopy(summary)
    bad2["reversibility"]["repair_remaining_min"] = 0.0
    assert robust_bounded_degradation_v5([bad2, bad2])["robust_bounded_degradation_v5"] is False


def test_metrics_do_not_mutate_trajectory():
    traj = _trajectory()
    frozen = copy.deepcopy(traj)
    summarize_reversibility(traj, 0.25)
    reversibility_binding(traj)
    assert traj == frozen
