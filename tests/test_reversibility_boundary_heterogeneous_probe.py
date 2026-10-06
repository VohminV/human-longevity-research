"""Stage 6F: heterogeneous residual driver probe.

Diagnostic extension over Stage 6E: targeted attenuation of top
bio-age drivers via existing aging_drivers/component_overrides layers.
No new biology; boundary_probe_model=none stays Stage 6C equivalent.
"""

import copy
import json
import math
import random

import pytest

from longevity.analysis.boundary_metrics import (
    RESIDUAL_WALL_LABELS,
    SUBSTANTIAL_BIO_SLOPE_REDUCTION,
    bio_age_source_ru,
    binding_constraint_ru,
    canonical_heterogeneous_driver,
    classify_residual_wall,
    confidence_ru,
    expand_heterogeneous_driver,
    exploratory_ru,
    hypothesis_ru,
    sensitivity_stable_ru,
    v5_operational_success_ru,
    validate_heterogeneous_driver_scale,
    wall_classification_ru,
)
from longevity.experiment.organism_boundary import (
    HeterogeneousProbeConfig,
    heterogeneous_regimes,
    load_boundary_config,
    run_heterogeneous_probe,
)

STABLE = {"data_complete": True, "seed_stable": True}


def _mini_base():
    from longevity.experiment.organism_runner import load_organism_config

    base = load_organism_config(
        "experiments/configs/organism_reversibility_combined_preventive_clearance.json"
    ).to_config_dict()
    base["duration_years"] = 25.0
    base["dt"] = 0.5
    base["boundary_probe_model"] = "irreversibility_ablation"
    base["boundary_params"] = {}
    base["component_overrides"] = []
    return base


def _mini_config(**overrides):
    payload = {
        "kind": "heterogeneous_probe",
        "experiment_id": "test_hetero_mini",
        "seeds": [42, 7],
        "drivers": [{"name": "proteostasis_metabolic", "scales": [1.0, 0.0]}],
        "combination_scales": [0.0],
        "combinations": [],
        "base_organism_config": _mini_base(),
        "v5_criteria": {},
        "output_prefix": "",
        "notes": "mini",
    }
    payload.update(overrides)
    return HeterogeneousProbeConfig.from_config_dict(payload)


@pytest.fixture(scope="module")
def mini_result():
    config = _mini_config()
    frozen_base = copy.deepcopy(config.base_organism_config)
    rng_before = random.getstate()
    result = run_heterogeneous_probe(config)
    return {"result": result, "config": config, "frozen_base": frozen_base,
            "rng_before": rng_before, "rng_after": random.getstate()}


# 1. Backward compatibility -------------------------------------------------

def test_control_matches_scale_one_trajectory(mini_result):
    entries = mini_result["result"]["entries"]
    control_traj = entries["control"]["seeds"]["42"]["summary"]
    single_traj = entries["driver:proteostasis_metabolic@1"]["seeds"]["42"]["summary"]
    assert control_traj == single_traj


def test_neutral_ablation_matches_stage6c():
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


def test_legacy_6d_6e_configs_still_load():
    from longevity.experiment.organism_boundary import (
        BoundarySweepConfig,
        ComponentAttributionConfig,
        SensitivityConfig,
    )

    compound = load_boundary_config(
        "experiments/configs/organism_reversibility_boundary_compound_attribution.json")
    assert isinstance(compound, ComponentAttributionConfig)
    knife = load_boundary_config(
        "experiments/configs/organism_reversibility_boundary_knife_edge_sweep.json")
    assert isinstance(knife, BoundarySweepConfig) and knife.kind == "conversion_ultra_sweep"
    sensitivity = load_boundary_config(
        "experiments/configs/organism_reversibility_boundary_sensitivity.json")
    assert isinstance(sensitivity, SensitivityConfig)
    probe = load_boundary_config(
        "experiments/configs/organism_reversibility_boundary_heterogeneous_probe.json")
    assert isinstance(probe, HeterogeneousProbeConfig)
    sweep = load_boundary_config(
        "experiments/configs/organism_reversibility_boundary_heterogeneous_sweep.json")
    assert isinstance(sweep, HeterogeneousProbeConfig)


# 2. Config validation -------------------------------------------------------

def test_unknown_driver_rejected():
    with pytest.raises(ValueError):
        _mini_config(drivers=[{"name": "telomere_attrition", "scales": [1.0]}])
    with pytest.raises(ValueError):
        canonical_heterogeneous_driver("not_a_driver")


def test_bad_scales_rejected():
    for bad in (-0.5, float("nan"), float("inf"), "0.5", None, True):
        with pytest.raises(ValueError):
            validate_heterogeneous_driver_scale(bad, "drivers[0].scales")
        with pytest.raises(ValueError):
            _mini_config(drivers=[{"name": "stem_exhaustion", "scales": [bad]}])


def test_duplicate_and_empty_drivers_rejected():
    with pytest.raises(ValueError):
        _mini_config(drivers=[{"name": "stem", "scales": [1.0]},
                              {"name": "stem_exhaustion", "scales": [1.0]}])
    with pytest.raises(ValueError):
        _mini_config(drivers=[])
    with pytest.raises(ValueError):
        _mini_config(drivers=[{"name": "stem_exhaustion", "scales": [0.0, 0.0]}])
    with pytest.raises(ValueError):
        _mini_config(
            drivers=[{"name": "proteostasis_metabolic", "scales": [1.0]},
                     {"name": "proteostasis_loss", "scales": [1.0]}])


def test_bad_combinations_rejected():
    with pytest.raises(ValueError):
        _mini_config(combinations=[["unknown_driver"]])
    with pytest.raises(ValueError):
        _mini_config(combinations=[[]])
    with pytest.raises(ValueError):
        _mini_config(combination_scales=[-1.0])


def test_aliases_expand_to_members():
    assert expand_heterogeneous_driver("stem") == ("stem_exhaustion",)
    assert expand_heterogeneous_driver("proteostasis_metabolic") == (
        "proteostasis_loss", "mitochondrial_dysfunction")
    assert expand_heterogeneous_driver("dna_damage") == ("dna_damage",)


def test_regime_table_deterministic():
    drivers = ({"name": "proteostasis_metabolic", "scales": [1.0, 0.0]},
               {"name": "stem_exhaustion", "scales": [0.5]})
    first = heterogeneous_regimes(drivers, (("proteostasis_metabolic",
                                             "stem_exhaustion"),), (0.0,))
    second = heterogeneous_regimes(drivers, (("proteostasis_metabolic",
                                              "stem_exhaustion"),), (0.0,))
    assert first == second
    assert [r["name"] for r in first] == [
        "control",
        "driver:proteostasis_metabolic@1",
        "driver:proteostasis_metabolic@0",
        "driver:stem_exhaustion@0.5",
        "combo:proteostasis_metabolic+stem_exhaustion@0",
    ]
    assert first[2]["driver_scales"] == {"proteostasis_loss": 0.0,
                                         "mitochondrial_dysfunction": 0.0}


# 3. Determinism --------------------------------------------------------------

def test_same_config_same_seed_identical(mini_result):
    rerun = run_heterogeneous_probe(mini_result["config"])
    assert rerun["entries"] == mini_result["result"]["entries"]


def test_global_random_untouched(mini_result):
    assert mini_result["rng_before"] == mini_result["rng_after"]


# 4. Finite outputs ------------------------------------------------------------

def test_finite_outputs_and_bool_v5(mini_result):
    for name, entry in mini_result["result"]["entries"].items():
        assert isinstance(entry["robust_v5"], bool)
        for value in (entry["mean_bio_age_slope"],
                      entry["mean_bio_attribution_total_slope"],
                      entry["mean_irreversible_slope"]):
            assert math.isfinite(value), name
        for seed, attribution in entry["bio_age_attribution"].items():
            for value in list(attribution["by_component"].values()) \
                    + list(attribution["by_source"].values()):
                assert math.isfinite(value), (name, seed)


# 5. Input state non-mutation ---------------------------------------------------

def test_probe_does_not_mutate_inputs(mini_result):
    assert mini_result["config"].base_organism_config == mini_result["frozen_base"]


def test_attribution_does_not_mutate_trajectory():
    from longevity.analysis.boundary_metrics import decompose_biological_age_slope
    from longevity.experiment.organism_runner import (
        OrganismExperimentConfig,
        run_organism_experiment,
    )

    base = _mini_base()
    trajectory = run_organism_experiment(
        OrganismExperimentConfig.from_config_dict(base))["trajectory"]
    frozen = copy.deepcopy(trajectory)
    decompose_biological_age_slope(trajectory)
    assert trajectory == frozen


# 6. Attribution behavior -------------------------------------------------------

def test_suppressed_driver_reduces_contribution(mini_result):
    entries = mini_result["result"]["entries"]
    control = entries["control"]["bio_age_attribution"]["42"]["by_source"]
    suppressed = entries["driver:proteostasis_metabolic@0"]["bio_age_attribution"]["42"]
    assert suppressed["by_source"]["proteostasis_metabolic"] < \
        control["proteostasis_metabolic"]
    assert mini_result["result"]["stage_6f"]["attribution_proxy_note"] != ""


def test_flip_fields_are_diagnostic(mini_result):
    for name, entry in mini_result["result"]["entries"].items():
        assert isinstance(entry["source_flip_vs_control"], bool)
        assert isinstance(entry["binding_changed_vs_control"], bool)
        assert isinstance(entry["diagnostic_transition_note"], str)
        if entry["source_flip_vs_control"] or entry["binding_changed_vs_control"]:
            assert "диагностический переход" in entry["diagnostic_transition_note"]


def test_substantial_threshold_documented():
    assert SUBSTANTIAL_BIO_SLOPE_REDUCTION == pytest.approx(0.20)


# 7. Classifier ------------------------------------------------------------------

def test_all_residual_labels_reachable():
    assert classify_residual_wall(n_drivers_tested=2, stability=dict(STABLE))[
        "stage_6f_residual_classification"] == "diffuse_residual_wall"
    assert classify_residual_wall(substantial_single_driver_effect=True,
                                  n_drivers_tested=2,
                                  stability=dict(STABLE))[
        "stage_6f_residual_classification"] == "localized_residual_wall"
    assert classify_residual_wall(binding_or_source_flip=True, n_drivers_tested=2,
                                  stability=dict(STABLE))[
        "stage_6f_residual_classification"] == "mixed_residual_wall"
    assert classify_residual_wall(v5_robust_non_exploratory=True, n_drivers_tested=2,
                                  stability=dict(STABLE))[
        "stage_6f_residual_classification"] == "localized_residual_wall"
    assert classify_residual_wall(v5_narrow_only=True, n_drivers_tested=2,
                                  stability=dict(STABLE))[
        "stage_6f_residual_classification"] == "inconclusive_residual_probe"
    assert set(RESIDUAL_WALL_LABELS) == {
        "diffuse_residual_wall", "localized_residual_wall",
        "mixed_residual_wall", "inconclusive_residual_probe"}


def test_insufficient_data_never_guesses():
    out = classify_residual_wall(n_drivers_tested=0, stability=dict(STABLE))
    assert out["stage_6f_residual_classification"] == "inconclusive_residual_probe"
    assert out["confidence"] == "low"
    out = classify_residual_wall(n_drivers_tested=2, stability={"data_complete": False})
    assert out["stage_6f_residual_classification"] == "inconclusive_residual_probe"


def test_instability_forces_inconclusive():
    out = classify_residual_wall(substantial_single_driver_effect=True,
                                 binding_or_source_flip=True,
                                 n_drivers_tested=2,
                                 stability={"data_complete": True,
                                            "seed_stable": False})
    assert out["stage_6f_residual_classification"] == "inconclusive_residual_probe"
    assert out["confidence"] == "low"


def test_invalid_classifier_types_rejected():
    with pytest.raises(ValueError):
        classify_residual_wall(v5_robust_non_exploratory="yes",
                               n_drivers_tested=1, stability=dict(STABLE))
    with pytest.raises(ValueError):
        classify_residual_wall(n_drivers_tested=-1, stability=dict(STABLE))


def test_exploratory_flags_present_and_consistent(mini_result):
    for name, entry in mini_result["result"]["entries"].items():
        assert isinstance(entry["exploratory"], bool), name
        assert entry["exploratory_ru"] == exploratory_ru(entry["exploratory"]), name
    # Mini base is nominal: no regime may be exploratory.
    assert not any(e["exploratory"]
                   for e in mini_result["result"]["entries"].values())


def test_shipped_configs_contain_no_new_biology():
    import json

    compound_base = json.load(
        open("experiments/configs/organism_reversibility_boundary_compound_attribution.json",
             encoding="utf-8"))["base_organism_config"]
    for path in ("experiments/configs/organism_reversibility_boundary_heterogeneous_probe.json",
                 "experiments/configs/organism_reversibility_boundary_heterogeneous_sweep.json"):
        config = json.load(open(path, encoding="utf-8"))
        base = config["base_organism_config"]
        # Same config contract as the Stage 6E base: no new sections,
        # no new models, no new policy variables.
        assert set(base) == set(compound_base)
        assert base["aging_mechanism_model"] == "mechanistic_drivers"
        assert base["reversibility_model"] == "split_reversible_irreversible"
        assert base["boundary_probe_model"] == "irreversibility_ablation"
        assert base["organ_backed_model"] == compound_base["organ_backed_model"]
        assert base["organ_network_model"] == compound_base["organ_network_model"]
        assert base["policies"] == compound_base["policies"]
        blob = json.dumps(config, ensure_ascii=False).lower()
        for marker in ("energy-coupled", "energy_coupled", "new_organ",
                       "new_cell", "telomere_attrition"):
            assert marker not in blob, (path, marker)


# 8. Human-readable statuses -------------------------------------------------------

def test_ru_statuses_correct_and_enums_stable(mini_result):
    assert wall_classification_ru("compound_residual_wall") == "составная остаточная стена"
    assert wall_classification_ru("diffuse_residual_wall") == "диффузная остаточная стена"
    assert wall_classification_ru("localized_residual_wall") == \
        "локализованная остаточная стена"
    assert wall_classification_ru("mixed_residual_wall") == "смешанная остаточная стена"
    assert wall_classification_ru("inconclusive_residual_probe") == \
        "неоднозначный зонд остаточной стены"
    assert binding_constraint_ru("biological_age_slope") == "наклон биологического возраста"
    assert binding_constraint_ru("information_debt") == "информационный долг"
    assert bio_age_source_ru("proteostasis_metabolic") == \
        "протеостаз/метаболизм (proteostasis_metabolic)"
    assert confidence_ru("medium") == "средняя"
    assert hypothesis_ru("hypothesis_not_proven") == "гипотеза не доказана"
    assert v5_operational_success_ru(False) == "операционный критерий v5 не выполнен"
    assert v5_operational_success_ru(True) == "операционный критерий v5 выполнен"
    assert exploratory_ru(True) == \
        "exploratory-режим, не калиброван как биологическая модель"
    assert sensitivity_stable_ru(True, True) == "устойчиво"
    assert sensitivity_stable_ru(False, True) == "частично"
    assert sensitivity_stable_ru(False, False) == "неустойчиво"
    with pytest.raises(ValueError):
        wall_classification_ru("not_a_wall")
    result = mini_result["result"]
    assert result["immortality_status"] == "hypothesis_not_proven"
    assert result["immortality_status_ru"] == "гипотеза не доказана"
    stage_6f = result["stage_6f"]
    assert stage_6f["stage_6f_residual_classification"] in RESIDUAL_WALL_LABELS
    assert stage_6f["stage_6f_residual_classification_ru"] == wall_classification_ru(
        stage_6f["stage_6f_residual_classification"])
    json.dumps(result["stage_6f"], ensure_ascii=False, allow_nan=False)
    for entry in result["entries"].values():
        json.dumps({"v5_ru": entry["v5_operational_success_ru"],
                    "binding_ru": entry["binding_majority_ru"]},
                   ensure_ascii=False, allow_nan=False)
