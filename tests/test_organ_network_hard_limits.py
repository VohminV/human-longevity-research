"""Stage 6B: hard physical/informational limits."""

import copy

import pytest

from longevity.model.intervention import PolicySet, build_effect
from longevity.model.organ_network import validate_hard_limits
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
              "organ_network_model": "reduced_network_feedback"}
    params.update(kwargs)
    return OrganismModel(seed=11, aging_model="mechanistic_drivers",
                         aging_drivers={}, **params)


def test_energy_exhaustion_throttles_repair():
    model = _model()
    net = model.state.organ_network
    net["energy_budget"] = 0.05
    before = copy.deepcopy(model.state.organ_backed["proxies"]["hepatic_proxy"]["repair_capacity"])
    model._organ_network_step(0.5, "adult_homeostasis")
    after = model.state.organ_backed["proxies"]["hepatic_proxy"]["repair_capacity"]
    assert after <= before
    assert model.state.organ_network["energy_budget"] >= 0.0


def test_mutation_ceiling_records_violation():
    model = _model(organ_network_hard_limits={"max_mutation_load": 0.01})
    effect = build_effect("telomere_maintenance", 1.0, [], source="t")
    for _ in range(5):
        model.apply_effect(dict(effect), "t")
    assert model.state.organ_network["mutation_load"] > 0.01
    model._organ_network_step(0.25, "adult_homeostasis")
    assert "mutation_load_ceiling" in model.state.organ_network["failed_hard_limit_ids"]


def test_information_preservation_not_free():
    model = _model()
    brain = model.state.organ_backed["proxies"]["brain_cns_proxy"]
    brain["informational_continuity"] = 0.4
    before = brain["informational_continuity"]
    effect = build_effect("neural_protective_maintenance", 1.0, [], source="t")
    model.apply_effect(dict(effect), "t")
    after = model.state.organ_backed["proxies"]["brain_cns_proxy"]["informational_continuity"]
    # continuity improves at most by the capped effect, never jumps to 1.0
    assert after <= before + 0.02 + 1e-9
    # aggressive reprogramming harms continuity
    reprog = build_effect("epigenetic_reprogramming_pulse", 1.0, [], source="t")
    c0 = model.state.organ_backed["proxies"]["brain_cns_proxy"]["informational_continuity"]
    model.apply_effect(dict(reprog), "t")
    assert model.state.organ_backed["proxies"]["brain_cns_proxy"]["informational_continuity"] <= c0


def test_irreversible_threshold_holds_floor():
    model = _model()
    proxy = model.state.organ_backed["proxies"]["renal_proxy"]
    proxy["function"] = 0.05
    proxy["damage"] = 0.8
    model._organ_network_step(0.5, "late_aging")
    floor = model.state.organ_network["nodes"]["renal_proxy"]["irreversible_damage"]
    assert floor > 0.0
    proxy["damage"] = 0.0
    model._organ_network_step(0.25, "late_aging")
    assert proxy["damage"] >= floor - 1e-9


def test_toxicity_budget_accumulates():
    model = _model()
    effect = build_effect("regenerative_boost", 2.0, [], source="t")
    model.apply_effect(dict(effect), "t")
    assert model.state.organ_network["intervention_toxicity"] > 0.0
    assert model.state.organ_network["intervention_toxicity"] == \
        pytest.approx(0.05 * 2.0 * 2.0)  # proliferative x2


def test_hard_limit_validation():
    with pytest.raises(ValueError):
        validate_hard_limits({"max_mutation_load": -1.0})
    limits = validate_hard_limits(None)
    assert limits["energy_budget_initial"] > 0
