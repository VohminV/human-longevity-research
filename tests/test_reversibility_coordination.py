"""Stage 6C: reversibility coordination."""

import pytest

from longevity.model.intervention import build_effect
from longevity.model.reversibility import (
    REVERSIBILITY_COORDINATION_MODES,
    coordinate_reversibility_effects,
    default_reversibility_state,
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


def _effect(itype="damage_prevention"):
    return build_effect(itype, 1.0, [], source="t")


def test_all_modes_deterministic_and_pure():
    rev = default_reversibility_state()
    effects = [_effect("damage_prevention"), _effect("irreversible_repair_pulse")]
    for mode in REVERSIBILITY_COORDINATION_MODES:
        first = coordinate_reversibility_effects(effects, rev, mode, None)
        second = coordinate_reversibility_effects(effects, rev, mode, None)
        assert first == second
        assert len(effects) == 2
    with pytest.raises(ValueError):
        coordinate_reversibility_effects(effects, rev, "nope", None)


def test_independent_executes_all():
    rev = default_reversibility_state()
    result = coordinate_reversibility_effects([_effect()], rev, "independent_reversibility", None)
    assert len(result["executed"]) == 1


def test_repair_ceiling_guard_blocks_over_ceiling():
    rev = default_reversibility_state()
    rev["repair_remaining"] = 0.01
    big = build_effect("irreversible_repair_pulse", 5.0, [], source="t")
    result = coordinate_reversibility_effects([big], rev, "repair_ceiling_guard", None)
    assert len(result["executed"]) == 0


def test_information_and_mutation_guards():
    rev = default_reversibility_state()
    rev["information_debt"] = 0.6
    reprog = build_effect("epigenetic_reprogramming_pulse", 1.0, [], source="t")
    result = coordinate_reversibility_effects([reprog], rev, "information_guard", None)
    assert len(result["executed"]) == 0
    rev2 = default_reversibility_state()
    rev2["mutation_fixation"] = 0.6
    result2 = coordinate_reversibility_effects([reprog], rev2, "mutation_guard", None)
    assert len(result2["executed"]) == 0


def test_preventive_priority_prefers_prevention():
    rev = default_reversibility_state()
    prev = _effect("damage_prevention")
    repair = build_effect("irreversible_repair_pulse", 1.0, [], source="t")
    result = coordinate_reversibility_effects([repair, prev], rev, "preventive_priority", None)
    assert prev in result["executed"]


def test_model_level_routing_and_stats():
    model = OrganismModel(seed=2, aging_model="mechanistic_drivers", aging_drivers={},
                          organ_backed_model="reduced_organ_proxies",
                          organ_network_model="reduced_network_feedback",
                          reversibility_model="split_reversible_irreversible",
                          coordination_mode="repair_ceiling_guard")
    model.state.reversibility["repair_remaining"] = 0.0
    big = build_effect("irreversible_repair_pulse", 5.0, [], source="t")
    executed, detail = model._coordinate_effects([big])
    assert detail["mode"] == "repair_ceiling_guard"
    assert len(executed) == 0
