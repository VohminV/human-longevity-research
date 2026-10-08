"""Stage 9: epigenetic backup -- validation, determinism, gates, checkpoint, scope."""

import copy

import pytest

from longevity.analysis.boundary_metrics import (
    information_wall_proximity as boundary_wall_proximity,
    information_wall_proximity_ru as boundary_wall_proximity_ru,
)
from longevity.analysis.epigenetic_backup_metrics import (
    robust_bounded_degradation_v6,
    summarize_backup_run,
    validate_v6_criteria,
)
from longevity.experiment.organism_runner import (
    OrganismExperimentConfig,
    load_organism_config,
    run_organism_experiment,
)
from longevity.model.epigenetic_backup import (
    apply_rollback,
    capture_reference,
    default_epigenetic_backup_state,
    entropy_bio_contribution,
    entropy_step,
    information_wall_proximity,
    information_wall_proximity_ru,
    mutation_burden,
    sanitization_factor,
    validate_epigenetic_backup_model,
    validate_epigenetic_backup_params,
    validate_epigenetic_backup_state,
)
from longevity.model.intervention import build_effect
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


def _run(seed=42, years=40.0, dt=0.5, **kwargs):
    params = {"aging_model": "mechanistic_drivers",
              "epigenetic_backup_model": "reference_restore"}
    params.update(kwargs)
    model = OrganismModel(seed=seed, aging_drivers={}, **params)
    return model.run(years, dt, _bounds(), _thresholds(), None)


def _params(**over):
    params = validate_epigenetic_backup_params(None)
    params.update(over)
    return validate_epigenetic_backup_params(params)


# -- validation --------------------------------------------------------

def test_validate_model_name():
    assert validate_epigenetic_backup_model("none") == "none"
    assert validate_epigenetic_backup_model("reference_restore") == "reference_restore"
    with pytest.raises(ValueError):
        validate_epigenetic_backup_model("hard_drive_magic")


def test_validate_params_rejects_unknown_and_bad_wall():
    with pytest.raises(ValueError):
        validate_epigenetic_backup_params({"nope": 1.0})
    with pytest.raises(ValueError):
        validate_epigenetic_backup_params({"genome_sanitized": "yes"})
    with pytest.raises(ValueError):
        validate_epigenetic_backup_params({"wall_read_threshold": 2.0, "max_entropy": 1.0})
    with pytest.raises(ValueError):
        validate_epigenetic_backup_params({"backup_restore_efficiency": 1.5})


def test_validate_state_none_passthrough_and_bool_guard():
    assert validate_epigenetic_backup_state(None) is None
    bad = default_epigenetic_backup_state()
    bad["backup_read_fidelity"] = 1.5
    with pytest.raises(ValueError):
        validate_epigenetic_backup_state(bad)


def test_backup_requires_mechanistic_drivers():
    with pytest.raises(ValueError):
        OrganismModel(seed=1, aging_model="none",
                      epigenetic_backup_model="reference_restore")
    with pytest.raises(ValueError):
        OrganismExperimentConfig(
            organism_id="x", seed=1, aging_mechanism_model="none",
            epigenetic_backup_model="reference_restore")


def test_none_mode_has_no_backup_state():
    model = OrganismModel(seed=42, aging_model="mechanistic_drivers")
    assert model.state.epigenetic_backup is None
    model2 = OrganismModel(seed=42, aging_model="mechanistic_drivers",
                           epigenetic_backup_model="none",
                           epigenetic_backup_params={"noise_generation_base": 0.5})
    assert model2.state.epigenetic_backup is None


def test_none_mode_reproduces_legacy_trajectory():
    reference = run_organism_experiment(
        load_organism_config("experiments/configs/organism_aging_combined_mechanistic.json"))
    d = load_organism_config(
        "experiments/configs/organism_aging_combined_mechanistic.json").to_config_dict()
    d["organism_id"] = "tmp_backup_none_repro"
    d["epigenetic_backup_model"] = "none"
    d["epigenetic_backup_params"] = {"noise_generation_base": 0.9}
    candidate = run_organism_experiment(OrganismExperimentConfig.from_config_dict(d))
    assert candidate["trajectory"] == reference["trajectory"]
    assert candidate["metrics"]["final"]["lifespan"] == reference["metrics"]["final"]["lifespan"]


# -- determinism + checkpoint ------------------------------------------

def test_determinism_same_seed_same_trajectory():
    assert _run() == _run()


def test_checkpoint_restore_identical_to_continuous():
    model = OrganismModel(seed=7, aging_model="mechanistic_drivers", aging_drivers={},
                          epigenetic_backup_model="reference_restore")
    bounds, thresholds = _bounds(), _thresholds()
    for _ in range(20):
        model.step(0.5, bounds, thresholds, [])
    snap = model.to_checkpoint_dict({"last_fired": {}})
    restored = OrganismModel.from_checkpoint(copy.deepcopy(snap))
    for _ in range(20):
        model.step(0.5, bounds, thresholds, [])
        restored.step(0.5, bounds, thresholds, [])
    assert restored.state.to_dict() == model.state.to_dict()


def test_checkpoint_json_roundtrip():
    import json

    model = OrganismModel(seed=7, aging_model="mechanistic_drivers", aging_drivers={},
                          epigenetic_backup_model="reference_restore")
    bounds, thresholds = _bounds(), _thresholds()
    for _ in range(10):
        model.step(0.5, bounds, thresholds, [])
    snap = json.loads(json.dumps(model.to_checkpoint_dict()))
    restored = OrganismModel.from_checkpoint(snap)
    for _ in range(10):
        model.step(0.5, bounds, thresholds, [])
        restored.step(0.5, bounds, thresholds, [])
    assert restored.state.to_dict() == model.state.to_dict()


# -- entropy dynamics --------------------------------------------------

def test_reference_captured_once_at_setpoint():
    traj = _run(years=30.0)
    backups = [row["epigenetic_backup"] for row in traj[1:]]
    assert all(b is not None for b in backups)
    assert backups[-1]["reference_captured"] is True
    assert backups[-1]["reference_age"] == pytest.approx(25.0, abs=0.6)
    assert capture_reference(backups[-1], 99.0, 0.5) is False


def test_entropy_rises_without_rollback_and_fidelity_decays():
    traj = _run(years=60.0)
    first = traj[1]["epigenetic_backup"]["epigenetic_entropy"]
    last = traj[-1]["epigenetic_backup"]["epigenetic_entropy"]
    assert last > first >= 0.0
    assert traj[-1]["epigenetic_backup"]["backup_read_fidelity"] <= 1.0


def test_entropy_step_math():
    backup = default_epigenetic_backup_state()
    params = _params()
    flux = entropy_step(backup, 1.0, 1.0, 0.5, 0.5, 0.2, params)
    expected_noise = (params["noise_generation_base"]
                      * (1.0 + params["te_coupling"] * (0.5 * 0.5 + 0.5 * 0.2)
                         + params["metabolic_coupling"] * 0.5))
    assert flux["generation"] == pytest.approx(expected_noise)
    # Empty drive: nothing to repair, entropy equals generation.
    assert backup["epigenetic_entropy"] == pytest.approx(expected_noise)
    assert flux["repair"] == 0.0
    # Second step: endogenous repair now bites into the accumulated entropy.
    flux2 = entropy_step(backup, 1.0, 1.0, 0.5, 0.5, 0.2, params)
    assert flux2["repair"] == pytest.approx(params["repair_capacity"])
    assert backup["epigenetic_entropy"] == pytest.approx(
        2 * expected_noise - params["repair_capacity"])
    assert entropy_bio_contribution(0.5, params) == pytest.approx(0.5 * params["entropy_bio_weight"])


# -- rollback gates ----------------------------------------------------

def _drivers(dna=0.1, epi=0.4, cancer=0.05, mito=0.2):
    from longevity.model.aging import DEFAULT_DRIVER_PARAMS

    drivers = {}
    for name in ("dna_damage", "epigenetic_drift", "cancer_prone", "mitochondrial_dysfunction"):
        drivers[name] = {"damage": {"dna_damage": dna, "epigenetic_drift": epi,
                                    "cancer_prone": cancer,
                                    "mitochondrial_dysfunction": mito}[name],
                         "reversal_applied_total": 0.0}
    params = {name: dict(DEFAULT_DRIVER_PARAMS[name]) for name in drivers}
    return drivers, params


def test_rollback_fires_and_restores():
    backup = default_epigenetic_backup_state()
    backup["epigenetic_entropy"] = 0.5
    backup["reference_captured"] = True
    backup["reference_entropy"] = 0.05
    drivers, params = _drivers()
    event = apply_rollback(backup, {"mutation_fixation": 0.0, "information_debt": 0.3},
                           drivers, params, 0.05, 1.0, _params())
    assert event["fired"] is True
    assert event["restored"] > 0.0
    assert backup["epigenetic_entropy"] < 0.5
    assert drivers["epigenetic_drift"]["damage"] < 0.4
    assert backup["rollback_events"] == 1


def test_rollback_blocked_by_cancer_gate():
    backup = default_epigenetic_backup_state()
    backup["epigenetic_entropy"] = 0.5
    drivers, params = _drivers(cancer=0.5)
    event = apply_rollback(backup, {"mutation_fixation": 0.0, "information_debt": 0.0},
                           drivers, params, 0.5, 1.0, _params())
    assert event["fired"] is False
    assert event["blocked_reason"] == "cancer_gate"
    assert backup["rollback_blocked"] == 1
    assert backup["epigenetic_entropy"] == 0.5


def test_apoptosis_fires_before_rollback_on_mutation_burden():
    backup = default_epigenetic_backup_state()
    backup["epigenetic_entropy"] = 0.5
    drivers, params = _drivers(dna=0.9)
    rev = {"mutation_fixation": 0.9, "information_debt": 0.2}
    assert mutation_burden(rev, {n: c["damage"] for n, c in drivers.items()}) > 0.35
    event = apply_rollback(backup, rev, drivers, params, 0.01, 1.0, _params())
    assert event["fired"] is False
    assert event["apoptosis_first"] is True
    assert backup["apoptosis_events"] == 1
    assert drivers["dna_damage"]["damage"] < 0.9
    assert rev["mutation_fixation"] < 0.9


def test_rollback_preserves_identity_no_neural_cost():
    effect = build_effect("epigenetic_rollback_pulse", 1.0)
    assert effect["delta_neural_continuity"] == 0.0
    assert effect["epi_rollback"] == 1.0
    effect2 = build_effect("synthetic_apoptosis_sweep", 1.0)
    assert effect2["epi_apoptosis"] == 1.0


def test_sanitization_drops_dna_accumulation():
    plain = _run(years=60.0)
    san = _run(years=60.0, epigenetic_backup_params={"genome_sanitized": True})
    assert sanitization_factor(_params()) == 1.0
    assert sanitization_factor(_params(genome_sanitized=True)) == pytest.approx(0.1)
    dna_plain = plain[-1]["aging"]["drivers"]["dna_damage"]["damage"]
    dna_san = san[-1]["aging"]["drivers"]["dna_damage"]["damage"]
    assert dna_san < dna_plain


# -- wall proximity + v6 -------------------------------------------------

def test_information_wall_proximity_metric():
    traj = _run(years=60.0)
    wall = boundary_wall_proximity(traj)
    assert 0.0 <= wall["proximity"] <= 1.0
    assert wall["readable"] is True
    assert boundary_wall_proximity_ru(0.9, False) == "стенка чтения достигнута"
    assert information_wall_proximity_ru(0.1, True) == "драйв читаем"
    direct = information_wall_proximity(traj[-1]["epigenetic_backup"], None)
    assert direct["proximity"] == pytest.approx(wall["proximity"])
    empty = information_wall_proximity(None, None)
    assert empty["has_backup"] is False and empty["readable"] is True
    with pytest.raises(ValueError):
        boundary_wall_proximity([])


def test_v6_false_without_backup_and_on_legacy():
    assert robust_bounded_degradation_v6(
        [{"epigenetic_backup": {"has_backup": False}}])["robust_bounded_degradation_v6"] is False
    with pytest.raises(ValueError):
        robust_bounded_degradation_v6([])
    with pytest.raises(ValueError):
        validate_v6_criteria({"nope": 1.0})


def test_runner_merges_backup_summary():
    result = run_organism_experiment(load_organism_config(
        "experiments/configs/organism_backup_rollback_baseline.json"))
    backup = result["metrics"]["final"]["epigenetic_backup"]
    assert backup["has_backup"] is True
    assert backup["reference_captured"] is True
    assert result["epigenetic_backup_model"] == "reference_restore"
    assert result["immortality_status"] == "hypothesis_not_proven"
    v6 = robust_bounded_degradation_v6([result["metrics"]["final"]])
    assert isinstance(v6["robust_bounded_degradation_v6"], bool)


def test_rollback_policy_fires_in_runner():
    d = load_organism_config(
        "experiments/configs/organism_backup_rollback_baseline.json").to_config_dict()
    d["organism_id"] = "tmp_backup_rollback_fires"
    result = run_organism_experiment(OrganismExperimentConfig.from_config_dict(d))
    backup = result["metrics"]["final"]["epigenetic_backup"]
    assert backup["rollback_events"] > 0
    assert summarize_backup_run(result["trajectory"])["epigenetic_backup"]["has_backup"] is True
