"""Stage 6E: compound wall classifier labels on synthetic inputs."""

import pytest

from longevity.analysis.boundary_metrics import (
    COMPOUND_WALL_LABELS,
    classify_compound_wall,
)

STABLE = {"data_complete": True, "seed_stable": True, "eps_stable": True, "dt_stable": True}
FALSE_VERDICTS = {"conversion_zero": False, "independent_zero": False,
                  "both_suppressed": False, "high_ceiling": False,
                  "unlimited_ceiling": False}


def test_all_labels_reachable():
    assert classify_compound_wall(True, dict(FALSE_VERDICTS), {}, **_kw())[
        "wall_classification"] == "no_wall"
    assert classify_compound_wall(False, {**FALSE_VERDICTS, "conversion_zero": True}, {},
                                  **_kw())["wall_classification"] == "single_channel_parametric_wall"
    assert classify_compound_wall(
        False, dict(FALSE_VERDICTS), {1e-6: True, 0.0001: False, 0.001: False},
        **_kw())["wall_classification"] == "knife_edge_parametric_wall"
    assert classify_compound_wall(
        False, dict(FALSE_VERDICTS), {},
        **_kw(irr=True, binding="biological_age_slope", n=3))[
            "wall_classification"] == "compound_residual_wall"
    assert classify_compound_wall(
        False, dict(FALSE_VERDICTS), {},
        **_kw())["wall_classification"] == \
        "structural_under_current_abstraction_wall"
    assert classify_compound_wall(
        False, {**FALSE_VERDICTS, "unlimited_ceiling": True}, {},
        **_kw(exploratory_only=True))["wall_classification"] == "ceiling_mediated_wall"
    assert classify_compound_wall(
        False, dict(FALSE_VERDICTS), {}, **_kw(stable=False))[
            "wall_classification"] == "inconclusive_sensitivity_failure"


def _kw(stable=True, irr=False, binding="none", n=0, exploratory_only=False):
    stability = dict(STABLE)
    if not stable:
        stability["eps_stable"] = False
    return {"irr_suppressed": irr, "residual_binding": binding,
            "n_residual_sources": n, "stability": stability,
            "exploratory_only": exploratory_only}


def test_insufficient_data_never_guesses():
    out = classify_compound_wall(False, dict(FALSE_VERDICTS), {},
                                 irr_suppressed=False, residual_binding="none",
                                 n_residual_sources=0,
                                 stability={"data_complete": False},
                                 exploratory_only=False)
    assert out["wall_classification"] == "inconclusive_sensitivity_failure"
    assert out["confidence"] == "low"


def test_unstable_eps_forces_inconclusive():
    out = classify_compound_wall(
        False, {**FALSE_VERDICTS, "conversion_zero": True}, {0.0001: True},
        irr_suppressed=True, residual_binding="biological_age_slope",
        n_residual_sources=3,
        stability={"data_complete": True, "seed_stable": True,
                   "eps_stable": False, "dt_stable": True},
        exploratory_only=False)
    assert out["wall_classification"] == "inconclusive_sensitivity_failure"


def test_invalid_verdict_types_rejected():
    with pytest.raises(ValueError):
        classify_compound_wall(False, {"conversion_zero": "yes"}, {})


def test_labels_are_known_set():
    assert set(COMPOUND_WALL_LABELS) == {
        "no_wall", "single_channel_parametric_wall", "knife_edge_parametric_wall",
        "compound_residual_wall", "structural_under_current_abstraction_wall",
        "ceiling_mediated_wall", "inconclusive_sensitivity_failure",
    }
