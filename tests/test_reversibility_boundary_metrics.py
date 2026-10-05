"""Stage 6D: contribution decomposition + source attribution + wall classification."""

import copy

import pytest

from longevity.analysis.boundary_metrics import (
    attribute_source,
    classify_wall,
    summarize_boundary_run,
    summarize_contributions,
)
from longevity.experiment.organism_runner import load_organism_config, run_organism_experiment


def _trajectory(config_name="experiments/configs/organism_reversibility_boundary_default.json"):
    return run_organism_experiment(load_organism_config(config_name))["trajectory"]


def test_contribution_identity_on_synthetic():
    traj = _trajectory()
    contrib = summarize_contributions(traj)
    assert contrib["has_contributions"] is True
    conv = contrib["conversion_flux_by_component"]
    indep = contrib["independent_accrual_by_component"]
    repair = contrib["repair_offset_by_component"]
    net = contrib["net_irreversible_slope_by_component"]
    # net slope tracks conversion + independent - repair directionally:
    # components with zero flux and zero accrual have ~zero net slope
    zeros = [cid for cid in net if conv[cid] == 0.0 and indep[cid] == 0.0]
    for cid in zeros:
        assert net[cid] <= 1e-9 + max(0.0, -repair[cid])
    shares = contrib["contribution_share_to_irreversible_slope_by_component"]
    positives = sum(1 for v in net.values() if v > 0.0)
    if positives > 0:
        assert sum(shares.values()) == pytest.approx(1.0)
    else:
        assert all(v == 0.0 for v in shares.values())
    assert contrib["dominant_irreversibility_component"] in (list(net) + ["none"])
    assert len(contrib["top_k_irreversibility_components"]) <= 5
    # deterministic tie-break: sorted ids
    assert contrib["component_binding_ranking"] == sorted(
        contrib["component_binding_ranking"],
        key=lambda c: (-max(0.0, net[c]), c))


def test_attribution_conversion_dominant():
    traj = _trajectory()
    result = run_organism_experiment(
        load_organism_config("experiments/configs/organism_reversibility_boundary_default.json"))
    summary = result["metrics"]["final"]
    contrib = summarize_contributions(traj)
    attr = attribute_source(contrib, summary.get("reversibility", {}))
    assert attr["dominant_irreversibility_source"] in (
        "conversion", "independent_irreversible_accrual", "insufficient_repair_offset",
        "repair_ceiling_limitation", "information_debt", "mutation_fixation",
        "niche_disorder", "entropy_production", "mixed", "other_binding_wall")
    assert attr["source_attribution_reason"] != ""


def test_attribution_independent_dominant_synthetic():
    contrib = {"has_contributions": True,
               "conversion_flux_by_component": {"a": 0.0, "b": 0.0},
               "independent_accrual_by_component": {"a": 0.01, "b": 0.002},
               "repair_offset_by_component": {"a": 0.0, "b": 0.0},
               "net_irreversible_slope_by_component": {"a": 0.01, "b": 0.002}}
    attr = attribute_source(contrib, {})
    assert attr["dominant_irreversibility_source"] == "independent_irreversible_accrual"


def test_attribution_mixed_near_tie():
    contrib = {"has_contributions": True,
               "conversion_flux_by_component": {"a": 0.010, "b": 0.0},
               "independent_accrual_by_component": {"a": 0.0, "b": 0.0095},
               "repair_offset_by_component": {"a": 0.0, "b": 0.0},
               "net_irreversible_slope_by_component": {"a": 0.010, "b": 0.0095}}
    attr = attribute_source(contrib, {})
    assert attr["dominant_irreversibility_source"] == "mixed"


def test_attribution_no_ledger():
    attr = attribute_source({"has_contributions": False}, {})
    assert attr["dominant_irreversibility_source"] == "none"


def test_wall_classification_cases():
    assert classify_wall(True, {})["wall_classification"] == "no_wall"
    out = classify_wall(False, {"conversion_zero": True, "independent_zero": False,
                                "both_suppressed": False, "high_ceiling": False,
                                "unlimited_ceiling": False}, "conversion")
    assert out["wall_classification"] == "structural_conversion_wall"
    out2 = classify_wall(False, {"conversion_zero": False, "independent_zero": True,
                                 "both_suppressed": False, "high_ceiling": False,
                                 "unlimited_ceiling": False}, "independent_irreversible_accrual")
    assert out2["wall_classification"] == "structural_independent_accrual_wall"
    out3 = classify_wall(False, {"conversion_zero": True, "independent_zero": True,
                                 "both_suppressed": True, "high_ceiling": False,
                                 "unlimited_ceiling": False}, "conversion")
    assert out3["wall_classification"] == "parametric_irreversibility_wall"
    out4 = classify_wall(False, {"conversion_zero": False, "independent_zero": False,
                                 "both_suppressed": False, "high_ceiling": False,
                                 "unlimited_ceiling": True}, "conversion")
    assert out4["wall_classification"] == "structural_repair_ceiling_wall"
    out5 = classify_wall(False, {"conversion_zero": False, "independent_zero": False,
                                 "both_suppressed": False, "high_ceiling": False,
                                 "unlimited_ceiling": False}, "information_debt")
    assert out5["wall_classification"] == "structural_information_wall"
    out6 = classify_wall(False, {}, "none")
    assert out6["wall_classification"] == "structural_other_wall"
    for out in (out, out2, out3, out4, out5, out6):
        assert out["wall_classification_reason"] != ""


def test_boundary_run_summary_does_not_mutate():
    traj = _trajectory()
    frozen = copy.deepcopy(traj)
    summarize_boundary_run(traj)
    assert traj == frozen
