"""Stage 6C: reversibility interventions, trade-offs, guards."""

import pytest

from longevity.model.intervention import build_effect, validate_effect
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


def _model(**kwargs):
    params = {"organ_backed_model": "reduced_organ_proxies",
              "organ_network_model": "reduced_network_feedback",
              "reversibility_model": "split_reversible_irreversible"}
    params.update(kwargs)
    return OrganismModel(seed=21, aging_model="mechanistic_drivers",
                         aging_drivers={}, **params)


def test_new_intervention_types_validate():
    for itype in ("reversible_clearance", "conversion_suppression", "damage_prevention",
                  "irreversible_repair_pulse", "information_preservation",
                  "mutation_fixation_control", "niche_integrity_support",
                  "entropy_management", "combined_reversibility_maintenance"):
        effect = build_effect(itype, 1.0, [], source="t")
        assert validate_effect(dict(effect))["intervention_type"] == itype


def test_clearance_suppression_prevention_effects():
    model = _model()
    model.run(25.0, 0.5, _bounds(), _thresholds(), None)
    rev_before = model.state.reversibility["reversible_burden"]
    model.apply_effect(dict(build_effect("reversible_clearance", 1.0, [], source="t")), "t")
    assert model.state.reversibility["reversible_burden"] <= rev_before + 1e-12
    prev_before = model.state.reversibility["prevention_pending"]
    model.apply_effect(dict(build_effect("damage_prevention", 1.0, [], source="t")), "t")
    assert model.state.reversibility["prevention_pending"] >= prev_before
    conv_before = model.state.reversibility["prevention_pending"]
    model.apply_effect(dict(build_effect("conversion_suppression", 1.0, [], source="t")), "t")
    assert model.state.reversibility["prevention_pending"] >= conv_before


def test_irreversible_repair_costs_and_debts():
    model = _model()
    model.run(30.0, 0.5, _bounds(), _thresholds(), None)
    info_before = model.state.reversibility["information_debt"]
    mut_before = model.state.reversibility["mutation_fixation"]
    cost_before = model.state.reversibility["repair_cost_auc"]
    model.apply_effect(dict(build_effect("irreversible_repair_pulse", 1.0, [], source="t")), "t")
    assert model.state.reversibility["repair_cost_auc"] >= cost_before
    assert model.state.reversibility["information_debt"] >= info_before - 1e-12
    assert model.state.reversibility["mutation_fixation"] >= mut_before - 1e-12


def test_information_mutation_niche_repairs_capped():
    model = _model()
    model.state.reversibility["information_debt"] = 0.5
    model.state.reversibility["mutation_fixation"] = 0.5
    model.state.reversibility["niche_disorder"] = 0.5
    model.apply_effect(dict(build_effect("information_preservation", 1.0, [], source="t")), "t")
    model.apply_effect(dict(build_effect("mutation_fixation_control", 1.0, [], source="t")), "t")
    model.apply_effect(dict(build_effect("niche_integrity_support", 1.0, [], source="t")), "t")
    assert 0.0 <= model.state.reversibility["information_debt"] <= 0.5
    assert 0.0 <= model.state.reversibility["mutation_fixation"] <= 0.5
    assert 0.0 <= model.state.reversibility["niche_disorder"] <= 0.5


def test_aggressive_repair_not_free():
    model = _model()
    model.run(30.0, 0.5, _bounds(), _thresholds(), None)
    tox_before = model.state.organ_network["intervention_toxicity"] \
        if model.state.organ_network else 0.0
    model.apply_effect(dict(build_effect("irreversible_repair_pulse", 2.0, [], source="t")), "t")
    tox_after = model.state.organ_network["intervention_toxicity"] \
        if model.state.organ_network else 0.0
    assert tox_after >= tox_before - 1e-12
    assert model.state.reversibility["repair_cost_auc"] > 0.0


def test_legacy_effects_unchanged_without_reversibility():
    model = OrganismModel(seed=21, aging_model="mechanistic_drivers", aging_drivers={},
                          organ_backed_model="reduced_organ_proxies",
                          organ_network_model="reduced_network_feedback",
                          reversibility_model="none")
    effect = build_effect("reversible_clearance", 1.0, [], source="t")
    # rev keys validate but are inert when the ledger is absent
    model.apply_effect(dict(effect), "t")
    assert model.state.reversibility is None
