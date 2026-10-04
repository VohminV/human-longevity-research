"""Stage 6A: organism-level coordination modes."""

import copy

import pytest

from longevity.model.intervention import LongevityPolicy, PolicySet, build_effect
from longevity.model.organ_backed import (
    ORGAN_PROXIES,
    coordinate_organ_effects,
    default_organ_backed_state,
    validate_coordination_mode,
)


def _effect(pid="seno", organs=None, senescence=-0.02, cost=0.02):
    effect = build_effect("senolytic_clearance", 1.0, [], source=pid)
    effect = dict(effect, target_organ_ids=list(organs or ORGAN_PROXIES))
    return effect


def _proxies():
    return default_organ_backed_state()["proxies"]


def _allocation(value=1.0):
    return {"perfusion": value, "immune": value, "metabolic": value, "repair": value}


def test_independent_passes_through_untouched():
    effects = [_effect("a"), _effect("b")]
    before = copy.deepcopy((effects, _proxies()))
    result = coordinate_organ_effects(effects, _proxies(), _allocation(0.2),
                                      "independent_organ_policies")
    assert result["executed"] == effects
    assert result["deferred"] == [] and result["rejected"] == []
    assert result["queue"] == []
    assert (effects, _proxies()) == before  # inputs never mutated


def test_global_scaling_proportional_to_allocation():
    result = coordinate_organ_effects([_effect()], _proxies(), _allocation(0.5),
                                      "global_resource_aware_scaling")
    assert len(result["executed"]) == 1
    assert result["executed"][0]["organ_delta_senescence"] == pytest.approx(-0.01)
    assert result["executed"][0]["_coord_scale"] == pytest.approx(0.5)
    full = coordinate_organ_effects([_effect()], _proxies(), _allocation(1.0),
                                    "global_resource_aware_scaling")
    assert full["executed"][0]["organ_delta_senescence"] == pytest.approx(-0.02)


def test_priority_protects_critical_organs():
    proxies = _proxies()
    critical = _effect("crit", organs=["brain_cns_proxy"])
    peripheral = _effect("periph", organs=["musculoskeletal_proxy"])
    result = coordinate_organ_effects([critical, peripheral], proxies, _allocation(0.3),
                                      "vital_organ_priority")
    # Critical plan executes at full strength; non-critical defers under contention.
    assert [e["source"] for e in result["executed"]] == ["crit"]
    assert result["executed"][0]["organ_delta_senescence"] == pytest.approx(-0.02)
    assert len(result["queue"]) == 1
    headroom = coordinate_organ_effects([], proxies, _allocation(0.9),
                                        "vital_organ_priority", result["queue"])
    assert [e["source"] for e in headroom["executed"]] == ["periph"]
    assert headroom["queue"] == []


def test_deferral_queues_then_rejects_after_retries():
    effects = [_effect()]
    result = coordinate_organ_effects(effects, _proxies(), _allocation(0.3),
                                      "deferral_organ_resource")
    assert result["executed"] == [] and result["rejected"] == []
    assert len(result["queue"]) == 1
    queue = result["queue"]
    for _ in range(3):
        result = coordinate_organ_effects([], _proxies(), _allocation(0.3),
                                          "deferral_organ_resource", queue)
        queue = result["queue"]
    assert len(queue) == 1  # retries 1..3 still queued
    result = coordinate_organ_effects([], _proxies(), _allocation(0.3),
                                      "deferral_organ_resource", queue)
    assert result["queue"] == [] and len(result["rejected"]) == 1
    # Headroom recovers queued plans.
    queued = coordinate_organ_effects(effects, _proxies(), _allocation(0.3),
                                      "deferral_organ_resource")["queue"]
    recovered = coordinate_organ_effects([], _proxies(), _allocation(0.9),
                                         "deferral_organ_resource", queued)
    assert len(recovered["executed"]) == 1 and recovered["queue"] == []


def test_lookahead_ranks_relief_over_cost():
    proxies = _proxies()
    weak = _effect("weak")
    weak["organ_delta_senescence"] = -0.001
    weak["organ_resource_cost"] = {"repair": 1.0}
    strong = _effect("strong")
    result = coordinate_organ_effects([weak, strong], proxies, _allocation(0.3),
                                      "lookahead_organ_resource")
    executed = {e["source"] for e in result["executed"]}
    assert "strong" in executed and "weak" not in executed
    assert len(result["queue"]) == 1


def test_unknown_mode_rejected_and_policies_untouched():
    with pytest.raises(ValueError):
        validate_coordination_mode("central_planner")
    with pytest.raises(ValueError):
        coordinate_organ_effects([], _proxies(), _allocation(), "central_planner")
    policies = PolicySet([{"policy_id": "p", "intervention_type": "senolytic_clearance",
                           "target_organ_ids": ["hepatic_proxy"]}])
    before = copy.deepcopy(policies.policies[0].to_dict())
    assert policies.policies[0].build_effect()["target_organ_ids"] == ["hepatic_proxy"]
    assert policies.policies[0].to_dict() == before  # planning never mutates policies
    with pytest.raises(ValueError):
        LongevityPolicy(policy_id="bad", intervention_type="senolytic_clearance",
                        target_organs=["no_such_proxy"])
