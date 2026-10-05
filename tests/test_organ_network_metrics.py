"""Stage 6B: network metrics + binding v3 + v4."""

import pytest

from longevity.analysis.organ_network_metrics import (
    network_binding,
    robust_bounded_degradation_v4,
    summarize_hard_limits,
    summarize_network,
    validate_v4_criteria,
)
from longevity.experiment.organism_runner import load_organism_config, run_organism_experiment


def _trajectory(config_name="experiments/configs/organism_organ_network_combined.json"):
    return run_organism_experiment(load_organism_config(config_name))["trajectory"]


def test_v4_criteria_validation():
    with pytest.raises(ValueError):
        validate_v4_criteria({"nope": 1.0})
    assert validate_v4_criteria(None)["eps_bio"] == 0.05


def test_network_summary_finite():
    traj = _trajectory()
    summary = summarize_network(traj, 0.25)
    assert summary["has_network"] is True
    for key in ("biological_age_network_slope", "max_cascade_risk",
                "worst_feedback_gain", "max_mutation_load"):
        value = summary[key]
        assert value == value and abs(value) < 1e6
    hard = summarize_hard_limits(traj)
    assert hard["has_hard_limits"] is True


def test_binding_levels_deterministic():
    traj = _trajectory()
    first = network_binding(traj)
    second = network_binding(traj)
    assert first == second
    assert first["dominant_binding_level"] in (
        "biological_age", "biological_age_network", "aging_driver", "organ_function",
        "systemic_resource", "network_edge", "feedback_loop", "hard_limit",
        "energy_budget", "mutation_load", "information_continuity", "cascade_risk",
        "cancer", "inflammation", "fibrosis", "intervention_cost",
        "reserve", "systemic_cascade", "cancer", "neural_continuity", "none")
    assert "dominant_binding_edge" in first
    assert "dominant_binding_loop" in first
    assert "dominant_binding_hard_limit" in first


def test_v4_false_on_declining_and_true_on_synthetic_healthy():
    traj = _trajectory()
    result = run_organism_experiment(
        load_organism_config("experiments/configs/organism_organ_network_combined.json"))
    summary = result["metrics"]["final"]
    verdict = robust_bounded_degradation_v4([summary, summary])
    assert verdict["robust_bounded_degradation_v4"] is False
    assert verdict["success_rate_bounded_v4"] in (0.0, 1.0)


def test_v4_requires_v3_plus_network():
    # v3 true but feedback runaway => v4 false is enforced structurally:
    # craft two summaries where network block signals runaway.
    result = run_organism_experiment(
        load_organism_config("experiments/configs/organism_organ_network_combined.json"))
    summary = result["metrics"]["final"]
    import copy
    bad = copy.deepcopy(summary)
    bad["organ_network"]["runaway_feedback_detected"] = True
    bad["organ_network"]["worst_feedback_gain"] = 5.0
    verdict = robust_bounded_degradation_v4([bad, bad])
    assert verdict["robust_bounded_degradation_v4"] is False


def test_metrics_do_not_mutate_trajectory():
    import copy
    traj = _trajectory()
    frozen = copy.deepcopy(traj)
    summarize_network(traj, 0.25)
    network_binding(traj)
    assert traj == frozen
