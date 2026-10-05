"""Stage 6B: network-aware coordination."""

import copy

import pytest

from longevity.model.organ_backed import default_organ_backed_state
from longevity.model.organ_network import (
    NETWORK_COORDINATION_MODES,
    coordinate_network_effects,
    default_organ_network_state,
)
from longevity.model.organism import (
    DEFAULT_ORGANISM_THRESHOLDS,
    DEFAULT_STAGE_BOUNDS,
    OrganismModel,
    validate_organism_thresholds,
    validate_stage_bounds,
)


def _bounds():
    return validate_stage_bounds(dict(DEFAULT_STAGE_BOUNDS))


def _thresholds():
    return validate_organism_thresholds(dict(DEFAULT_ORGANISM_THRESHOLDS))


def _proxies(low_one=None):
    ob = default_organ_backed_state()
    if low_one:
        ob["proxies"][low_one]["function"] = 0.1
    return ob["proxies"]


def _alloc(level=1.0):
    return {"perfusion": level, "immune": level, "metabolic": level, "repair": level}


def _effect(pid="renal_proxy", itype="tissue_organ_maintenance"):
    from longevity.model.intervention import build_effect
    return build_effect(itype, 1.0, [], source="t", target_organs=[pid])


def test_all_modes_deterministic_and_pure():
    proxies = _proxies()
    effects = [_effect("renal_proxy"), _effect("hepatic_proxy")]
    for mode in NETWORK_COORDINATION_MODES:
        first = coordinate_network_effects(effects, proxies, _alloc(0.3), mode, None, None)
        second = coordinate_network_effects(effects, proxies, _alloc(0.3), mode, None, None)
        assert first == second
        # inputs not mutated
        assert len(effects) == 2
    # unknown mode rejected
    with pytest.raises(ValueError):
        coordinate_network_effects(effects, proxies, _alloc(), "nope", None, None)


def test_independent_network_executes_all():
    proxies = _proxies()
    effects = [_effect("renal_proxy"), _effect("hepatic_proxy")]
    result = coordinate_network_effects(effects, proxies, _alloc(0.1),
                                        "independent_network", None, None)
    assert len(result["executed"]) == 2
    assert result["queue"] == []


def test_bottleneck_priority_prefers_bottleneck():
    proxies = _proxies(low_one="renal_proxy")
    bottleneck_hit = _effect("renal_proxy")
    other = _effect("hepatic_proxy")
    result = coordinate_network_effects([other, bottleneck_hit], proxies, _alloc(0.3),
                                        "network_bottleneck_priority", None, None)
    assert bottleneck_hit in result["executed"]


def test_cascade_guard_defers_risky_when_hot():
    proxies = _proxies()
    net = default_organ_network_state()
    net["cascade_risk"] = 0.9
    risky = _effect("hepatic_proxy", "regenerative_boost")
    result = coordinate_network_effects([risky], proxies, _alloc(0.8),
                                        "cascade_guard", None, net)
    assert len(result["executed"]) == 0
    # cool network executes
    net["cascade_risk"] = 0.1
    result2 = coordinate_network_effects([risky], proxies, _alloc(0.8),
                                         "cascade_guard", None, net)
    assert len(result2["executed"]) == 1


def test_mutation_guard_limits_proliferative():
    proxies = _proxies()
    net = default_organ_network_state()
    net["mutation_load"] = 0.95
    risky = _effect("hepatic_proxy", "stem_niche_restoration")
    result = coordinate_network_effects([risky], proxies, _alloc(0.3),
                                        "mutation_load_guard", None, net)
    assert len(result["executed"]) == 0


def test_information_priority_protects_brain():
    proxies = _proxies()
    proxies["brain_cns_proxy"]["informational_continuity"] = 0.4
    from longevity.model.intervention import build_effect
    harmful = build_effect("epigenetic_reprogramming_pulse", 1.0, [], source="t",
                           target_organs=["brain_cns_proxy"])
    result = coordinate_network_effects([harmful], proxies, _alloc(),
                                        "information_preservation_priority", None, None)
    assert len(result["executed"]) == 0


def test_model_level_coordination_stats():
    model = OrganismModel(seed=2, aging_model="mechanistic_drivers", aging_drivers={},
                          organ_backed_model="reduced_organ_proxies",
                          organ_network_model="reduced_network_feedback",
                          coordination_mode="cascade_guard")
    model.state.organ_network["cascade_risk"] = 0.9
    from longevity.model.intervention import build_effect
    effects = [build_effect("regenerative_boost", 1.0, [], source="t",
                            target_organs=["hepatic_proxy"])]
    executed, detail = model._coordinate_effects(effects)
    assert detail["mode"] == "cascade_guard"
    assert len(executed) == 0
