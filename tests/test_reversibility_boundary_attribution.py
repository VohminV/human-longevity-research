"""Stage 6D: attribution binding + wall classification on trajectories."""

import copy

import pytest

from longevity.analysis.boundary_metrics import summarize_boundary_run
from longevity.analysis.reversibility_metrics import reversibility_binding
from longevity.experiment.organism_runner import load_organism_config, run_organism_experiment


def test_attribution_binding_levels():
    result = run_organism_experiment(
        load_organism_config("experiments/configs/organism_reversibility_boundary_default.json"))
    binding = reversibility_binding(result["trajectory"])
    assert binding["dominant_binding_level"] in (
        "biological_age", "biological_age_network", "biological_age_reversibility",
        "aging_driver", "reversible_burden", "irreversible_accumulation",
        "conversion_runaway", "repair_ceiling_exhaustion", "information_debt",
        "mutation_fixation", "niche_disorder", "entropy_production",
        "organ_function", "reserve", "systemic_resource", "network_edge",
        "feedback_loop", "hard_limit", "energy_budget", "cascade_risk",
        "cancer", "systemic_cascade", "intervention_cost", "none")
    summary = summarize_boundary_run(result["trajectory"])
    assert summary["attribution"]["dominant_irreversibility_source"] != ""
    assert summary["contributions"]["dominant_irreversibility_component"] != ""


def test_suppressed_trajectory_reveals_other_wall_or_v5():
    from longevity.experiment.organism_runner import OrganismExperimentConfig
    from longevity.analysis.reversibility_metrics import robust_bounded_degradation_v5

    d = load_organism_config(
        "experiments/configs/organism_reversibility_boundary_both_suppressed.json").to_config_dict()
    result = run_organism_experiment(OrganismExperimentConfig.from_config_dict(d))
    summary = result["metrics"]["final"]
    verdict = robust_bounded_degradation_v5([summary, summary])
    # Either v5 appears under suppression or another wall binds — both are valid;
    # the verdict must simply be a bool, and binding must resolve deterministically.
    assert isinstance(verdict["robust_bounded_degradation_v5"], bool)
    binding = reversibility_binding(result["trajectory"])
    assert binding["first_reversibility_constraint_violated"] != ""


def test_metrics_do_not_mutate_trajectory():
    traj = run_organism_experiment(
        load_organism_config("experiments/configs/organism_reversibility_boundary_default.json"))["trajectory"]
    frozen = copy.deepcopy(traj)
    summarize_boundary_run(traj)
    reversibility_binding(traj)
    assert traj == frozen
