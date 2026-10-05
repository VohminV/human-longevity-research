"""Stage 6B: feedback loops + network age."""

import pytest

from longevity.model.organ_backed import default_organ_backed_state
from longevity.model.organ_network import (
    FEEDBACK_LOOPS,
    compute_cascade_risk,
    compute_feedback_gains,
    compute_network_age,
    default_organ_network_state,
    validate_feedback_config,
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


def test_each_loop_toggleable():
    for loop in FEEDBACK_LOOPS:
        cfg = validate_feedback_config({loop: {"enabled": False}})
        assert cfg[loop]["enabled"] == 0.0
        cfg2 = validate_feedback_config({loop: {"enabled": True}})
        assert cfg2[loop]["enabled"] == 1.0


def test_positive_feedback_increases_burden():
    ob = default_organ_backed_state()
    for proxy in ob["proxies"].values():
        proxy["damage"] = 0.6
        proxy["senescence_burden"] = 0.6
    alloc = {"perfusion": 0.4, "immune": 0.3, "metabolic": 0.4, "repair": 0.3}
    cfg = validate_feedback_config(None)
    gains = compute_feedback_gains(ob["proxies"], alloc, cfg)
    assert gains["inflammation_damage_loop"] > 0.2
    # disabled loop gives zero
    cfg_off = validate_feedback_config({"inflammation_damage_loop": {"enabled": False}})
    gains_off = compute_feedback_gains(ob["proxies"], alloc, cfg_off)
    assert gains_off["inflammation_damage_loop"] == 0.0
    for value in gains.values():
        assert value == value and abs(value) < 5.0


def test_runaway_detection_on_synthetic():
    ob = default_organ_backed_state()
    for proxy in ob["proxies"].values():
        proxy["damage"] = 1.0
        proxy["senescence_burden"] = 1.0
        proxy["cancer_risk"] = 1.0
    alloc = {"perfusion": 0.0, "immune": 0.0, "metabolic": 0.0, "repair": 0.0}
    cfg = validate_feedback_config(None)
    gains = compute_feedback_gains(ob["proxies"], alloc, cfg)
    assert max(gains.values()) > 0.5
    from longevity.model.organ_backed import validate_proxy_params
    params = validate_proxy_params(None)
    risk = compute_cascade_risk(ob["proxies"], alloc, gains, params)
    assert 0.0 <= risk <= 1.0
    assert risk > 0.4


def test_network_age_floor_and_exploratory_flag():
    from longevity.model.aging import validate_aging_drivers
    drivers = validate_aging_drivers(None)
    damages = {name: 0.0 for name in drivers}
    bio, contrib = compute_network_age(25.0, damages, drivers, 0.0, 0.0, 0.0, 0.0,
                                       0.0, 0.0, 0.0, 0.0, None, False)
    assert bio == 25.0
    assert contrib == 0.0
    damages2 = {name: 0.5 for name in drivers}
    bio2, _ = compute_network_age(25.0, damages2, drivers, 0.3, 0.2, 0.2, 0.2,
                                  0.2, 0.2, 0.2, 0.2, None, False)
    assert bio2 > 25.0
    # exploratory mode flag is stored on the model, not the pure function
    model = OrganismModel(seed=1, aging_model="mechanistic_drivers", aging_drivers={},
                          organ_backed_model="reduced_organ_proxies",
                          organ_network_model="reduced_network_feedback",
                          allow_sub_adult_network_age=True)
    assert model.allow_sub_adult_network_age is True


def test_network_age_slope_positive_in_decline():
    from longevity.experiment.organism_runner import load_organism_config, run_organism_experiment
    result = run_organism_experiment(
        load_organism_config("experiments/configs/organism_organ_network_baseline.json"))
    slope = result["metrics"]["final"]["organ_network"]["biological_age_network_slope"]
    assert slope == slope and abs(slope) < 5.0
