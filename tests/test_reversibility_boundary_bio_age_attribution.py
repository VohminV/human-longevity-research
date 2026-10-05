"""Stage 6E: biological_age_slope diagnostic attribution."""

import copy

import pytest

from longevity.analysis.boundary_metrics import decompose_biological_age_slope
from longevity.experiment.organism_runner import load_organism_config, run_organism_experiment


def _mini_trajectory():
    from longevity.experiment.organism_runner import OrganismExperimentConfig

    base = load_organism_config(
        "experiments/configs/organism_reversibility_combined_preventive_clearance.json").to_config_dict()
    base["duration_years"] = 30.0
    base["dt"] = 0.5
    base["seed"] = 42
    return run_organism_experiment(OrganismExperimentConfig.from_config_dict(base))["trajectory"]


def test_attribution_present_in_new_modes():
    attribution = decompose_biological_age_slope(_mini_trajectory())
    assert attribution["has_bio_age_attribution"] is True
    assert attribution["deterministic"] is True
    assert attribution["dominant_component"] != ""
    assert attribution["dominant_source"] != ""
    assert len(attribution["top_components"]) == 3
    assert len(attribution["top_sources"]) == 3
    assert attribution["share_sum"] == pytest.approx(1.0)


def test_attribution_does_not_break_legacy_outputs():
    # Pure function over trajectories; boundary=none trajectories carry no
    # reversibility ledger but still carry the mechanistic driver ledger.
    result = run_organism_experiment(
        load_organism_config("experiments/configs/organism_reversibility_legacy_none.json"))
    attribution = decompose_biological_age_slope(result["trajectory"])
    assert attribution["has_bio_age_attribution"] is True
    assert attribution["notes"] != ""


def test_shares_consistent_within_clamping():
    attribution = decompose_biological_age_slope(_mini_trajectory())
    by_component = attribution["by_component"]
    by_source = attribution["by_source"]
    assert abs(sum(by_component.values()) + attribution["residual"]
               - attribution["total_slope"]) < 1e-9
    assert attribution["share_sum"] == pytest.approx(1.0)
    assert sum(attribution["by_source"].values()) == pytest.approx(
        sum(by_component.values()))


def test_dominant_deterministic_and_ties_stable():
    first = decompose_biological_age_slope(_mini_trajectory())
    second = decompose_biological_age_slope(_mini_trajectory())
    assert first == second
    # Tie-break is sorted-name order: construct equal positive slopes.
    assert first["top_components"] == sorted(
        first["top_components"],
        key=lambda k: (-max(0.0, first["by_component"][k]), k))


def test_no_mutation_and_no_nan_inf():
    import math

    traj = _mini_trajectory()
    frozen = copy.deepcopy(traj)
    attribution = decompose_biological_age_slope(traj)
    assert traj == frozen
    for value in list(attribution["by_component"].values()) \
            + list(attribution["by_source"].values()) \
            + [attribution["total_slope"], attribution["residual"], attribution["share_sum"]]:
        assert math.isfinite(value)


def test_empty_trajectory_rejected():
    with pytest.raises(ValueError):
        decompose_biological_age_slope([])


def test_n_significant_sources_present():
    attribution = decompose_biological_age_slope(_mini_trajectory())
    assert isinstance(attribution["n_significant_sources"], int)
    assert attribution["n_significant_sources"] >= 1
