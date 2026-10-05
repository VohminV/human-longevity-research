"""Stage 6C: reversible / irreversible dynamics, conversion, ceiling, floor."""

import pytest

from longevity.model.organism import (
    DEFAULT_ORGANISM_THRESHOLDS,
    DEFAULT_STAGE_BOUNDS,
    OrganismModel,
    validate_organism_thresholds,
    validate_stage_bounds,
)
from longevity.model.reversibility import (
    compute_reversibility_age,
    conversion_modifiers,
    validate_reversibility_params,
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
    return OrganismModel(seed=11, aging_model="mechanistic_drivers",
                         aging_drivers={}, **params)


def test_clearance_reduces_reversible_not_below_zero():
    from longevity.model.intervention import build_effect
    model = _model()
    model.run(25.0, 0.5, _bounds(), _thresholds(), None)
    before = dict(model.state.reversibility["drivers"]["cellular_senescence"])
    effect = build_effect("reversible_clearance", 1.0, [], source="t")
    model.apply_effect(dict(effect), "t")
    after = model.state.reversibility["drivers"]["cellular_senescence"]
    assert after["reversible"] <= before["reversible"] + 1e-12
    assert after["reversible"] >= 0.0
    assert after["irreversible"] >= 0.0


def test_conversion_moves_mass_rev_to_irr():
    model = _model()
    model.run(30.0, 0.5, _bounds(), _thresholds(), None)
    rev = model.state.reversibility
    total_irr_before = sum(c["irreversible"] for c in rev["drivers"].values())
    model._reversibility_step(0.5, "late_aging")
    total_irr_after = sum(c["irreversible"] for c in model.state.reversibility["drivers"].values())
    assert total_irr_after >= total_irr_before - 1e-12
    for comp in list(model.state.reversibility["drivers"].values()) \
            + list(model.state.reversibility["organs"].values()):
        assert comp["reversible"] >= 0.0 and comp["irreversible"] >= 0.0
        assert comp["reversible"] <= 1.0 and comp["irreversible"] <= 1.0


def test_irreversible_repair_bounded_by_ceiling_and_floor():
    from longevity.model.intervention import build_effect
    model = _model(reversibility_params={"repair_ceiling": 0.05})
    model.run(30.0, 0.5, _bounds(), _thresholds(), None)
    rev = model.state.reversibility
    assert rev["repair_remaining"] <= 0.05 + 1e-12
    effect = build_effect("irreversible_repair_pulse", 5.0, [], source="t")
    used_before = rev["repair_used_global"]
    model.apply_effect(dict(effect), "t")
    used_after = model.state.reversibility["repair_used_global"]
    assert used_after - used_before <= 0.05 + 1e-9
    assert model.state.reversibility["repair_remaining"] >= 0.0
    # ceiling=0 forbids repair
    model0 = _model(reversibility_params={"repair_ceiling": 0.0})
    model0.run(30.0, 0.5, _bounds(), _thresholds(), None)
    r0 = model0.state.reversibility["repair_remaining"]
    model0.apply_effect(dict(build_effect("irreversible_repair_pulse", 1.0, [], source="t")), "t")
    assert model0.state.reversibility["repair_used_global"] == pytest.approx(0.0)


def test_conversion_modifiers_monotone():
    params = validate_reversibility_params(None)
    calm = conversion_modifiers(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, params)
    hot = conversion_modifiers(0.8, 0.8, 0.8, 0.8, 0.8, 0.8, params)
    assert hot > calm >= 1.0


def test_biological_age_floor_holds():
    params = validate_reversibility_params(None)
    total, floor, rev_c, irr_c = compute_reversibility_age(25.0, 0.0, 0.3, 0.1, 0.1, 0.1,
                                                           params, False)
    assert total >= floor >= 25.0
    assert irr_c > 0.0
    total2, floor2, _, _ = compute_reversibility_age(25.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                                                    params, False)
    assert total2 == pytest.approx(25.0)
    assert floor2 == pytest.approx(25.0)


def test_no_nan_inf_in_step():
    import math
    model = _model()
    model.run(40.0, 0.5, _bounds(), _thresholds(), None)
    blob = json_dumps(model.state.reversibility)
    assert blob is not None
    for comp in list(model.state.reversibility["drivers"].values()):
        for key in ("reversible", "irreversible", "conversion_rate"):
            assert math.isfinite(comp[key])


def json_dumps(state):
    import json
    return json.loads(json.dumps(state))
