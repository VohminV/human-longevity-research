"""Stage 7: criterion and parameter robustness audit.

Audit layer over Stage 6F: parameter perturbations around baseline plus
pre-declared criterion variants (horizon/threshold/aggregation/
estimator) and channel identifiability flags. A v5=true inside the
audit is sensitivity evidence, never success. No new biology.
"""

import copy
import json
import math
import random

import pytest

from longevity.analysis.boundary_metrics import (
    STAGE7_AUDIT_LABELS,
    assess_identifiability,
    criterion_variant_ru,
    estimate_bio_slope,
    identifiability_ru,
    is_nominal_audit_multiplier,
    relativize_slope_criteria,
    truncate_trajectory,
    validate_audit_multiplier,
    wall_classification_ru,
    classify_stage7_audit,
)
from longevity.experiment.organism_boundary import (
    HeterogeneousProbeConfig,
    RobustnessAuditConfig,
    audit_parameter_regimes,
    load_boundary_config,
    run_robustness_audit,
)


def _mini_base(duration_years=40.0):
    from longevity.experiment.organism_runner import load_organism_config

    base = load_organism_config(
        "experiments/configs/organism_reversibility_combined_preventive_clearance.json"
    ).to_config_dict()
    base["duration_years"] = duration_years
    base["dt"] = 0.5
    base["boundary_probe_model"] = "irreversibility_ablation"
    base["boundary_params"] = {}
    base["component_overrides"] = []
    return base


def _mini_config(**overrides):
    payload = {
        "kind": "robustness_audit",
        "experiment_id": "test_audit_mini",
        "seeds": [42, 7],
        "driver_weights": [{"name": "stem_exhaustion", "mults": [1.0, 2.0]}],
        "ledger_scales": [{"param": "conversion_scale", "values": [1.0, 1.25]}],
        "combinations": [{"name": "mini_combo",
                          "driver_weights": {"stem_exhaustion": 2.0},
                          "ledger_scales": {"conversion_scale": 1.25}}],
        "criterion_horizons": [30.0, 40.0],
        "criterion_threshold_relativities": [-0.1, 0.0, 0.1],
        "criterion_aggregations": ["global", "network"],
        "criterion_estimators": ["least_squares", "endpoint"],
        "identifiability_min_change": 0.05,
        "base_organism_config": _mini_base(),
        "v5_criteria": {},
        "output_prefix": "",
        "notes": "mini",
    }
    payload.update(overrides)
    return RobustnessAuditConfig.from_config_dict(payload)


@pytest.fixture(scope="module")
def mini_result():
    config = _mini_config()
    frozen_base = copy.deepcopy(config.base_organism_config)
    rng_before = random.getstate()
    result = run_robustness_audit(config)
    return {"result": result, "config": config, "frozen_base": frozen_base,
            "rng_before": rng_before, "rng_after": random.getstate()}


# 1. Backward compatibility ---------------------------------------------------

def test_control_matches_mult_one_trajectories(mini_result):
    entries = mini_result["result"]["entries"]
    control = entries["control"]["seeds"]["42"]["summary"]
    assert entries["driver_w:stem_exhaustion@1"]["seeds"]["42"]["summary"] == control
    assert entries["ledger:conversion_scale@1"]["seeds"]["42"]["summary"] == control


def test_neutral_audit_matches_stage6c():
    from longevity.experiment.organism_runner import (
        OrganismExperimentConfig,
        run_organism_experiment,
    )

    base = _mini_base()
    ref_data = copy.deepcopy(base)
    ref_data["boundary_probe_model"] = "none"
    ref = run_organism_experiment(OrganismExperimentConfig.from_config_dict(ref_data))
    same_data = copy.deepcopy(base)
    same_data["boundary_probe_model"] = "irreversibility_ablation"
    same = run_organism_experiment(OrganismExperimentConfig.from_config_dict(same_data))
    strip = lambda traj: [{k: v for k, v in row.items() if k != "boundary"} for row in traj]
    assert strip(same["trajectory"]) == strip(ref["trajectory"])


def test_legacy_configs_still_load():
    from longevity.experiment.organism_boundary import (
        BoundarySweepConfig,
        ComponentAttributionConfig,
        HeterogeneousProbeConfig,
        SensitivityConfig,
    )

    assert isinstance(load_boundary_config(
        "experiments/configs/organism_reversibility_boundary_compound_attribution.json"),
        ComponentAttributionConfig)
    assert isinstance(load_boundary_config(
        "experiments/configs/organism_reversibility_boundary_sensitivity.json"),
        SensitivityConfig)
    assert isinstance(load_boundary_config(
        "experiments/configs/organism_reversibility_boundary_heterogeneous_probe.json"),
        HeterogeneousProbeConfig)
    assert isinstance(load_boundary_config(
        "experiments/configs/organism_reversibility_boundary_heterogeneous_sweep.json"),
        HeterogeneousProbeConfig)
    probe = load_boundary_config(
        "experiments/configs/organism_reversibility_boundary_stage7_audit.json")
    assert isinstance(probe, RobustnessAuditConfig)
    assert isinstance(load_boundary_config(
        "experiments/configs/organism_reversibility_boundary_knife_edge_sweep.json"),
        BoundarySweepConfig)


def test_shipped_audit_has_no_new_biology():
    compound_base = json.load(
        open("experiments/configs/organism_reversibility_boundary_compound_attribution.json",
             encoding="utf-8"))["base_organism_config"]
    config = json.load(
        open("experiments/configs/organism_reversibility_boundary_stage7_audit.json",
             encoding="utf-8"))
    base = config["base_organism_config"]
    assert set(base) == set(compound_base)
    assert base["aging_mechanism_model"] == "mechanistic_drivers"
    assert base["reversibility_model"] == "split_reversible_irreversible"
    assert base["policies"] == compound_base["policies"]
    blob = json.dumps(config, ensure_ascii=False).lower()
    for marker in ("energy-coupled", "energy_coupled", "new_organ",
                   "new_cell", "telomere_attrition"):
        assert marker not in blob, marker


# 2. Config validation ----------------------------------------------------------

def test_unknown_driver_and_param_rejected():
    with pytest.raises(ValueError):
        _mini_config(driver_weights=[{"name": "telomere_attrition", "mults": [1.0]}])
    with pytest.raises(ValueError):
        _mini_config(ledger_scales=[{"param": "unknown_scale", "values": [1.0]}])
    with pytest.raises(ValueError):
        _mini_config(combinations=[{"name": "bad", "driver_weights": {},
                                    "ledger_scales": {"unknown_scale": 1.0}}])
    with pytest.raises(ValueError):
        _mini_config(combinations=[{"name": "empty", "driver_weights": {},
                                    "ledger_scales": {}}])


def test_unknown_criterion_variant_rejected():
    with pytest.raises(ValueError):
        _mini_config(criterion_aggregations=["unknown_channel"])
    with pytest.raises(ValueError):
        _mini_config(criterion_estimators=["unknown_estimator"])
    with pytest.raises(ValueError):
        estimate_bio_slope([{"a": 1}], "unknown_estimator")
    with pytest.raises(ValueError):
        criterion_variant_ru("unknown_kind", 1.0)


def test_bad_multipliers_rejected():
    for bad in (-0.5, float("nan"), float("inf"), "2.0", None, True):
        with pytest.raises(ValueError):
            validate_audit_multiplier(bad, "driver_weights[0].mults")
        with pytest.raises(ValueError):
            _mini_config(driver_weights=[{"name": "stem_exhaustion",
                                          "mults": [bad]}])
    with pytest.raises(ValueError):
        _mini_config(driver_weights=[])
    with pytest.raises(ValueError):
        _mini_config(driver_weights=[{"name": "stem", "mults": [1.0]},
                                     {"name": "stem_exhaustion", "mults": [1.0]}])
    with pytest.raises(ValueError):
        _mini_config(criterion_horizons=[])
    with pytest.raises(ValueError):
        _mini_config(criterion_threshold_relativities=[-1.5])
    with pytest.raises(ValueError):
        truncate_trajectory([{"chronological_age": 0.0}], -5.0)


def test_duplicate_regimes_rejected():
    with pytest.raises(ValueError):
        _mini_config(driver_weights=[{"name": "stem_exhaustion", "mults": [2.0, 2.0]}])
    with pytest.raises(ValueError):
        audit_parameter_regimes(
            ({"name": "stem_exhaustion", "mults": [1.0]},
             {"name": "stem_exhaustion", "mults": [1.0]}), (), ())


def test_wide_range_auto_marked_exploratory():
    regimes = audit_parameter_regimes(
        ({"name": "stem_exhaustion", "mults": [1.0, 4.0]},),
        ({"param": "conversion_scale", "values": [0.5]},), ())
    by_name = {r["name"]: r for r in regimes}
    assert by_name["control"]["exploratory_wide_range"] is False
    assert by_name["driver_w:stem_exhaustion@1"]["exploratory_wide_range"] is False
    assert by_name["driver_w:stem_exhaustion@4"]["exploratory_wide_range"] is True
    assert by_name["ledger:conversion_scale@0.5"]["exploratory_wide_range"] is True
    assert is_nominal_audit_multiplier(2.0, "driver") is True
    assert is_nominal_audit_multiplier(0.5, "ledger") is False


# 3. Determinism -----------------------------------------------------------------

def test_same_config_same_seed_identical(mini_result):
    rerun = run_robustness_audit(mini_result["config"])
    assert rerun["entries"] == mini_result["result"]["entries"]
    assert rerun["criterion_probe"] == mini_result["result"]["criterion_probe"]
    assert rerun["stage_7"] == mini_result["result"]["stage_7"]


def test_global_random_untouched(mini_result):
    assert mini_result["rng_before"] == mini_result["rng_after"]


def test_regime_order_deterministic():
    first = audit_parameter_regimes(
        ({"name": "stem_exhaustion", "mults": [2.0, 0.5]},),
        ({"param": "conversion_scale", "values": [1.25]},),
        ({"name": "c", "driver_weights": {}, "ledger_scales": {"conversion_scale": 0.75}},))
    second = audit_parameter_regimes(
        ({"name": "stem_exhaustion", "mults": [2.0, 0.5]},),
        ({"param": "conversion_scale", "values": [1.25]},),
        ({"name": "c", "driver_weights": {}, "ledger_scales": {"conversion_scale": 0.75}},))
    assert first == second
    assert [r["name"] for r in first] == [
        "control", "driver_w:stem_exhaustion@2", "driver_w:stem_exhaustion@0.5",
        "ledger:conversion_scale@1.25", "combo:c"]


# 4. Finite outputs ---------------------------------------------------------------

def test_finite_outputs_and_bool_v5(mini_result):
    for name, entry in mini_result["result"]["entries"].items():
        assert isinstance(entry["robust_v5"], bool)
        for value in (entry["mean_bio_age_slope"],
                      entry["mean_bio_attribution_total_slope"],
                      entry["mean_irreversible_slope"]):
            assert math.isfinite(value), name
        for seed, slopes in entry["estimator_slopes"].items():
            for value in slopes.values():
                assert math.isfinite(value), (name, seed)


# 5. Input state non-mutation ------------------------------------------------------

def test_audit_does_not_mutate_inputs(mini_result):
    assert mini_result["config"].base_organism_config == mini_result["frozen_base"]


def test_pure_helpers_do_not_mutate_trajectory():
    from longevity.experiment.organism_runner import (
        OrganismExperimentConfig,
        run_organism_experiment,
    )

    trajectory = run_organism_experiment(
        OrganismExperimentConfig.from_config_dict(_mini_base()))["trajectory"]
    frozen = copy.deepcopy(trajectory)
    estimate_bio_slope(trajectory, "endpoint")
    estimate_bio_slope(trajectory, "trailing_window")
    truncate_trajectory(trajectory, 30.0)
    assert trajectory == frozen


# 6. Criterion sensitivity ------------------------------------------------------------

def test_baseline_estimator_and_zero_relativity_reproduce_baseline(mini_result):
    entries = mini_result["result"]["entries"]
    control = entries["control"]
    summary_slope = control["seeds"]["42"]["summary"][
        "biological_age_slope_after_adulthood"]
    assert control["estimator_slopes"]["42"]["least_squares"] == \
        pytest.approx(summary_slope)
    criterion = mini_result["result"]["criterion_probe"]
    assert criterion["threshold_variants"]["threshold_0.0"]["verdict_by_regime"] == \
        {n: e["robust_v5"] for n, e in entries.items()}


def test_full_horizon_reproduces_control_verdict(mini_result):
    criterion = mini_result["result"]["criterion_probe"]
    full = criterion["horizon_variants"]["horizon_40"]
    assert full["degenerate"] is False
    assert full["robust_v5"] == mini_result["result"]["entries"]["control"]["robust_v5"]
    assert full["binding_majority"] == \
        mini_result["result"]["entries"]["control"]["binding_majority"]


def test_estimators_and_truncation_rejected_on_bad_input():
    with pytest.raises(ValueError):
        estimate_bio_slope([], "least_squares")
    with pytest.raises(ValueError):
        truncate_trajectory([], 10.0)
    with pytest.raises(ValueError):
        relativize_slope_criteria({"eps_bio": 0.05}, float("nan"))


# 7. Identifiability --------------------------------------------------------------------

def test_identifiability_flags_reachable():
    stable = {"data_complete": True, "seed_stable": True}
    assert assess_identifiability(
        control_observable=1.0,
        driver_responses={"a": {"relative_observable_change": 0.5,
                                "binding_changed": False, "source_changed": False}},
        **stable)["identifiability"] == "identifiable"
    assert assess_identifiability(
        control_observable=1.0,
        driver_responses={"a": {"relative_observable_change": 0.01,
                                "binding_changed": False, "source_changed": False}},
        **stable)["identifiability"] == "non_identifiable"
    out = assess_identifiability(
        control_observable=1.0,
        driver_responses={"a": {"relative_observable_change": 0.5,
                                "binding_changed": False, "source_changed": False},
                          "b": {"relative_observable_change": 0.01,
                                "binding_changed": False, "source_changed": False}},
        **stable)
    assert out["identifiability"] == "weakly_identifiable"
    assert out["per_driver"]["b"]["channel"] == "weakly_identifiable"
    assert assess_identifiability(control_observable=1.0)["identifiability"] == \
        "insufficient_data"
    with pytest.raises(ValueError):
        assess_identifiability(control_observable=1.0, driver_responses={
            "a": {"relative_observable_change": float("nan"),
                  "binding_changed": False, "source_changed": False}})
    assert identifiability_ru("weakly_identifiable") == "слабо идентифицируем"
    with pytest.raises(ValueError):
        identifiability_ru("unknown_flag")


def test_audit_identifiability_present(mini_result):
    stage_7 = mini_result["result"]["stage_7"]
    flag = stage_7["identifiability"]["identifiability"]
    assert flag in ("identifiable", "weakly_identifiable",
                    "non_identifiable", "insufficient_data")
    assert stage_7["identifiability_ru"] == identifiability_ru(flag)


# 8. Classifier ----------------------------------------------------------------------------

def test_all_stage7_labels_reachable():
    stable = {"data_complete": True, "seed_stable": True}
    assert classify_stage7_audit(n_regimes_tested=2, stability=dict(stable),
                                 identifiability="identifiable")[
        "stage_7_audit_classification"] == "robust_diffuse_wall"
    assert classify_stage7_audit(criterion_flip=True, n_regimes_tested=2,
                                 stability=dict(stable),
                                 identifiability="identifiable")[
        "stage_7_audit_classification"] == "criterion_sensitive_wall"
    assert classify_stage7_audit(parameter_v5_flip=True, n_regimes_tested=2,
                                 stability=dict(stable),
                                 identifiability="identifiable")[
        "stage_7_audit_classification"] == "parameter_sensitive_wall"
    assert classify_stage7_audit(parameter_attribution_flip=True, n_regimes_tested=2,
                                 stability=dict(stable),
                                 identifiability="identifiable")[
        "stage_7_audit_classification"] == "parameter_sensitive_wall"
    assert classify_stage7_audit(n_regimes_tested=2, stability=dict(stable),
                                 identifiability="non_identifiable")[
        "stage_7_audit_classification"] == "non_identifiable_abstraction"
    assert classify_stage7_audit(n_regimes_tested=0, stability=dict(stable))[
        "stage_7_audit_classification"] == "inconclusive_insufficient_calibration"
    assert set(STAGE7_AUDIT_LABELS) == {
        "robust_diffuse_wall", "criterion_sensitive_wall",
        "parameter_sensitive_wall", "non_identifiable_abstraction",
        "inconclusive_insufficient_calibration"}


def test_audit_v5_true_is_never_success():
    stable = {"data_complete": True, "seed_stable": True}
    out = classify_stage7_audit(v5_any_non_exploratory=True,
                                parameter_v5_flip=True, n_regimes_tested=2,
                                stability=dict(stable),
                                identifiability="identifiable")
    assert out["stage_7_audit_classification"] == "parameter_sensitive_wall"
    assert "hypothesis_not_proven" in out["stage_7_audit_classification_reason"]


def test_insufficient_and_unstable_never_guess():
    out = classify_stage7_audit(n_regimes_tested=2,
                                stability={"data_complete": False})
    assert out["stage_7_audit_classification"] == "inconclusive_insufficient_calibration"
    assert out["confidence"] == "low"
    out = classify_stage7_audit(criterion_flip=True, parameter_v5_flip=True,
                                n_regimes_tested=2,
                                stability={"data_complete": True,
                                           "seed_stable": False},
                                identifiability="identifiable")
    assert out["stage_7_audit_classification"] == "inconclusive_insufficient_calibration"
    with pytest.raises(ValueError):
        classify_stage7_audit(criterion_flip="yes", n_regimes_tested=1,
                              stability={"data_complete": True, "seed_stable": True})
    with pytest.raises(ValueError):
        classify_stage7_audit(n_regimes_tested=1, stability={"data_complete": True},
                              identifiability="unknown")


# 9. Human-readable statuses ---------------------------------------------------------------------

def test_ru_statuses_correct_and_enums_stable(mini_result):
    assert wall_classification_ru("robust_diffuse_wall") == "устойчивая диффузная стена"
    assert wall_classification_ru("criterion_sensitive_wall") == \
        "стена, чувствительная к критерию"
    assert wall_classification_ru("parameter_sensitive_wall") == \
        "стена, чувствительная к параметрам"
    assert wall_classification_ru("non_identifiable_abstraction") == \
        "неидентифицируемая абстракция"
    assert wall_classification_ru("inconclusive_insufficient_calibration") == \
        "неоднозначно: недостаточно калибровки"
    assert "порог" in criterion_variant_ru("threshold", -0.2)
    assert "горизонт" in criterion_variant_ru("horizon", 100.0)
    result = mini_result["result"]
    assert result["immortality_status"] == "hypothesis_not_proven"
    assert result["immortality_status_ru"] == "гипотеза не доказана"
    assert result["candidate_robust_bounded_degradation_v5_found"] is False
    stage_7 = result["stage_7"]
    assert stage_7["stage_7_audit_classification"] in STAGE7_AUDIT_LABELS
    assert stage_7["stage_7_audit_classification_ru"] == wall_classification_ru(
        stage_7["stage_7_audit_classification"])
    json.dumps({"stage_7": stage_7, "criterion": result["criterion_probe"]},
               ensure_ascii=False, allow_nan=False)
    for entry in result["entries"].values():
        assert isinstance(entry["exploratory"], bool)
        json.dumps({"v5_ru": entry["v5_operational_success_ru"],
                    "exploratory_ru": entry["exploratory_ru"]},
                   ensure_ascii=False, allow_nan=False)
