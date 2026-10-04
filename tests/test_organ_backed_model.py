"""Stage 6A: organ-backed model -- compat, determinism, mapping, emergence, checkpoint."""

import copy
import json

import pytest

from longevity.experiment.organism_runner import load_organism_config, run_organism_experiment
from longevity.model.intervention import PolicySet
from longevity.model.organ_backed import (
    ORGAN_BACKED_SCOPE,
    ORGAN_PROXIES,
    default_organ_backed_state,
    scope_for_model,
    validate_coordination_mode,
    validate_emergent_weights,
    validate_organ_backed_model,
    validate_proxy_params,
    validate_resource_budgets,
)
from longevity.model.organism import (
    DEFAULT_ORGANISM_THRESHOLDS,
    DEFAULT_STAGE_BOUNDS,
    MODEL_SCOPE,
    OrganismModel,
    validate_organism_thresholds,
    validate_stage_bounds,
)


def _bounds():
    return validate_stage_bounds(dict(DEFAULT_STAGE_BOUNDS))


def _thresholds():
    return validate_organism_thresholds(dict(DEFAULT_ORGANISM_THRESHOLDS))


def _run(seed=42, years=40.0, dt=0.5, **kwargs):
    params = {"organ_backed_model": "reduced_organ_proxies"}
    params.update(kwargs)
    model = OrganismModel(seed=seed, aging_model="mechanistic_drivers",
                          aging_drivers={}, **params)
    return model.run(years, dt, _bounds(), _thresholds(), None)


def test_none_mode_reproduces_stage5c_bit_for_bit():
    reference = run_organism_experiment(
        load_organism_config("experiments/configs/organism_aging_mechanistic_baseline.json"))
    candidate = run_organism_experiment(
        load_organism_config("experiments/configs/organism_organ_backed_legacy_none.json"))
    assert candidate["model_scope"] == MODEL_SCOPE == reference["model_scope"]
    for key in ("lifespan", "healthspan", "primary_cause_of_death",
                "biological_age_slope_after_adulthood", "final_biological_age"):
        assert candidate["metrics"]["final"][key] == reference["metrics"]["final"][key]
    assert candidate["trajectory"] == reference["trajectory"]


def test_organ_backed_determinism_and_no_global_random():
    import random

    before = random.getstate()
    first = _run(seed=7)
    second = _run(seed=7)
    assert first == second
    assert random.getstate() == before


def test_validation_rejects_bad_blocks():
    with pytest.raises(ValueError):
        validate_organ_backed_model("full_cell_simulation")
    with pytest.raises(ValueError):
        validate_proxy_params({"no_such_proxy": {}})
    with pytest.raises(ValueError):
        validate_proxy_params({"brain_cns_proxy": {"failure_threshold": 0.9,
                                                   "warning_threshold": 0.4}})
    with pytest.raises(ValueError):
        validate_resource_budgets({"perfusion": -1.0})
    with pytest.raises(ValueError):
        validate_resource_budgets({"no_such_resource": 1.0})
    with pytest.raises(ValueError):
        validate_coordination_mode("central_planner")
    with pytest.raises(ValueError):
        validate_emergent_weights({"cellular_senescence": 1.5})
    with pytest.raises(ValueError):
        validate_emergent_weights({"no_such_driver": 0.5})
    assert scope_for_model("none") == MODEL_SCOPE
    assert scope_for_model("reduced_organ_proxies") == ORGAN_BACKED_SCOPE


def test_proxy_damage_maps_to_vital_systems_and_brain_continuity():
    model = OrganismModel(seed=1, aging_model="mechanistic_drivers", aging_drivers={},
                          organ_backed_model="reduced_organ_proxies")
    before_sys = copy.deepcopy(model.state.systems["hepatic"]["function"])
    hepatic = model.state.organ_backed["proxies"]["hepatic_proxy"]
    hepatic["damage"] = 1.0
    hepatic["senescence_burden"] = 0.8
    hepatic["fibrosis"] = 0.5
    hepatic["ecm_quality"] = 0.2
    model._map_proxies_to_systems()
    assert model.state.systems["hepatic"]["function"] < before_sys
    # Non-brain proxies carry no continuity slot.
    assert model.state.organ_backed["proxies"]["hepatic_proxy"]["informational_continuity"] is None
    brain_before = model.state.systems["brain_cns"]["informational_continuity"]
    model.state.organ_backed["proxies"]["brain_cns_proxy"]["informational_continuity"] = 0.1
    model._map_proxies_to_systems()
    assert model.state.systems["brain_cns"]["informational_continuity"] < brain_before


def test_emergent_blend_moves_drivers():
    plain = _run(seed=11, emergent_weights={n: 0.0 for n in (
        "dna_damage", "epigenetic_drift", "proteostasis_loss", "mitochondrial_dysfunction",
        "cellular_senescence", "stem_exhaustion", "chronic_inflammation", "cancer_prone")})
    blended = _run(seed=11)
    plain_sen = plain[-1]["aging"]["drivers"]["cellular_senescence"]["damage"]
    blended_sen = blended[-1]["aging"]["drivers"]["cellular_senescence"]["damage"]
    assert blended_sen != pytest.approx(plain_sen)
    # Bounds still hold everywhere.
    for row in blended[1:]:
        for cell in row["aging"]["drivers"].values():
            assert 0.0 <= cell["damage"] <= 1.0


def test_checkpoint_restore_identical_continuation():
    model = OrganismModel(seed=5, aging_model="mechanistic_drivers", aging_drivers={},
                          organ_backed_model="reduced_organ_proxies")
    policy = PolicySet([])
    model.run(20.0, 0.5, _bounds(), _thresholds(), policy)
    checkpoint = model.to_checkpoint_dict(policy.to_state_dict())
    roundtripped = json.loads(json.dumps(checkpoint))
    restored = OrganismModel.from_checkpoint(roundtripped)
    assert restored.state.to_dict() == model.state.to_dict()
    assert restored.organ_backed_model == "reduced_organ_proxies"
    restored.run(20.0, 0.5, _bounds(), _thresholds(), policy)
    reference = OrganismModel(seed=5, aging_model="mechanistic_drivers", aging_drivers={},
                              organ_backed_model="reduced_organ_proxies")
    reference.run(40.0, 0.5, _bounds(), _thresholds(), PolicySet([]))
    assert restored.state.to_dict() == reference.state.to_dict()


def test_legacy_checkpoint_restores_without_organ_block():
    model = OrganismModel(seed=5, aging_model="mechanistic_drivers", aging_drivers={},
                          organ_backed_model="reduced_organ_proxies")
    checkpoint = model.to_checkpoint_dict(None)
    del checkpoint["organ_backed_model"]
    del checkpoint["organ_proxies"]
    del checkpoint["systemic_resources"]
    del checkpoint["coordination_mode"]
    del checkpoint["emergent_weights"]
    checkpoint["state"]["organ_backed"] = None
    restored = OrganismModel.from_checkpoint(checkpoint)
    assert restored.organ_backed_model == "none"
    assert set(default_organ_backed_state()["proxies"]) == set(ORGAN_PROXIES)
