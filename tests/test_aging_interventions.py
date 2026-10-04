"""Stage 5C: driver-targeted interventions, diminishing returns, trade-offs."""

import copy
import math

import pytest

from longevity.experiment.organism_runner import load_organism_config, run_organism_experiment
from longevity.model.aging import AGING_DRIVERS
from longevity.model.intervention import (
    INTERVENTION_TYPES,
    LongevityPolicy,
    PolicySet,
    build_effect,
)
from longevity.model.organism import (
    OrganismModel,
    validate_organism_thresholds,
    validate_stage_bounds,
    DEFAULT_ORGANISM_THRESHOLDS,
    DEFAULT_STAGE_BOUNDS,
)

BOUNDS = validate_stage_bounds(dict(DEFAULT_STAGE_BOUNDS))
THRESHOLDS = validate_organism_thresholds(dict(DEFAULT_ORGANISM_THRESHOLDS))

MECH_TYPES = (
    "dna_repair_enhancement", "epigenetic_reprogramming_pulse", "proteostasis_enhancement",
    "mitochondrial_turnover", "telomere_maintenance", "senolytic_clearance",
    "senomorphic_modulation", "stem_niche_restoration", "anti_inflammatory_resolution",
    "fibrosis_reversal_support", "cancer_surveillance_boost", "neural_protective_maintenance",
)


def _mech_model(seed=5, years=50.0):
    model = OrganismModel(seed=seed, aging_model="mechanistic_drivers", aging_drivers={})
    model.run(years, 0.5, BOUNDS, THRESHOLDS, None)
    return model


def test_all_mechanistic_types_build():
    assert set(INTERVENTION_TYPES) >= set(MECH_TYPES)
    for name in MECH_TYPES:
        effect = build_effect(name, intensity=1.0, source="test")
        assert effect["intervention_type"] == name
        assert isinstance(effect.get("target_drivers", []), list)
    with pytest.raises(ValueError):
        build_effect("dna_repair_enhancement", intensity=float("nan"))


def test_each_driver_responds_to_its_intervention():
    cases = [
        ("dna_repair_enhancement", "dna_damage"),
        ("epigenetic_reprogramming_pulse", "epigenetic_drift"),
        ("proteostasis_enhancement", "proteostasis_loss"),
        ("mitochondrial_turnover", "mitochondrial_dysfunction"),
        ("senolytic_clearance", "cellular_senescence"),
        ("stem_niche_restoration", "stem_exhaustion"),
        ("anti_inflammatory_resolution", "chronic_inflammation"),
        ("cancer_surveillance_boost", "cancer_prone"),
    ]
    for itype, driver in cases:
        model = _mech_model()
        before = model.state.aging["drivers"][driver]["damage"]
        model.apply_effect(build_effect(itype, intensity=1.0, source="test"), "test")
        after = model.state.aging["drivers"][driver]["damage"]
        assert after <= before + 1e-12, (itype, driver, before, after)
        assert after >= 0.0
    # Unknown driver targets rejected.
    from longevity.model.intervention import validate_effect
    with pytest.raises(ValueError):
        validate_effect({"intervention_type": "dna_repair_enhancement", "target_drivers": ["brain"]})
    with pytest.raises(ValueError):
        validate_effect({"intervention_type": "dna_repair_enhancement",
                         "driver_repairs": {"brain": 0.1}})


def test_diminishing_returns_and_floor():
    model = _mech_model()
    driver = "dna_damage"
    first_drops = []
    for _ in range(6):
        before = model.state.aging["drivers"][driver]["damage"]
        model.apply_effect(build_effect("dna_repair_enhancement", intensity=1.0, source="test"), "test")
        after = model.state.aging["drivers"][driver]["damage"]
        first_drops.append(before - after)
    # Later identical hits remove less-or-equal (saturation gate).
    assert first_drops[0] >= first_drops[-1] - 1e-12
    assert model.state.aging["drivers"][driver]["damage"] >= 0.0
    # Reversal events recorded.
    assert any(e["driver"] == driver for e in model.state.aging["age_reversal_events"])


def test_tradeoffs_epigenetic_telomere_stem_mito():
    model = _mech_model()
    before = model.state.to_dict()
    model.apply_effect(build_effect("epigenetic_reprogramming_pulse", intensity=1.0, source="test"), "test")
    after = model.state.to_dict()
    assert after["cancer_burden"] >= before["cancer_burden"] - 1e-12
    model2 = _mech_model()
    before2 = model2.state.to_dict()
    model2.apply_effect(build_effect("telomere_maintenance", intensity=1.0, source="test"), "test")
    assert model2.state.cancer_burden >= before2["cancer_burden"] - 1e-12
    model3 = _mech_model()
    before3 = model3.state.systems["brain_cns"]["informational_continuity"]
    model3.apply_effect(build_effect("epigenetic_reprogramming_pulse", intensity=2.0,
                                     target_systems=["brain_cns"], source="test"), "test")
    assert model3.state.systems["brain_cns"]["informational_continuity"] <= before3 + 1e-12


def test_gated_policies_need_biomarker_and_pre_adult_guard():
    young_state = {"developmental_stage": "childhood", "senescence_burden": 0.5,
                   "cancer_burden": 0.0, "systems": {"a": {"reserve": 1.0}}}
    policy = LongevityPolicy(policy_id="g", intervention_type="senolytic_clearance",
                             trigger_type="threshold_based", interval=1.0, start_age=5.0,
                             biomarker="driver:cellular_senescence", biomarker_threshold=0.01)
    holder = PolicySet([policy.to_dict()])
    assert holder.effects_for_age(10.0, young_state) == []  # pre-adult, not allowed
    allowed = LongevityPolicy(policy_id="g2", intervention_type="senolytic_clearance",
                              trigger_type="threshold_based", interval=1.0, start_age=5.0,
                              biomarker="driver:cellular_senescence", biomarker_threshold=0.01,
                              allow_pre_adult=True)
    holder2 = PolicySet([allowed.to_dict()])
    effects = holder2.effects_for_age(10.0, dict(young_state, aging={"drivers": {"cellular_senescence": {"damage": 0.5}}}))
    assert len(effects) == 1 and effects[0]["pre_adult_firing"] is True
    with pytest.raises(ValueError):
        from longevity.model.intervention import _biomarker_value
        _biomarker_value("driver:brain", {"aging": {"drivers": {}}})


def test_interventions_never_break_state():
    model = _mech_model(years=60.0)
    for itype in MECH_TYPES:
        model.apply_effect(build_effect(itype, intensity=5.0, source="test"), "test")
        for value in (model.state.cancer_burden, model.state.inflammation, model.state.fibrosis):
            assert math.isfinite(value)
        for info in model.state.aging["drivers"].values():
            assert 0.0 <= info["damage"] <= 1.0
