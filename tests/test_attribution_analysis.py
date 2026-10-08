"""Stage 9b: constraint attribution -- correctness of math and rules (no assumed winner)."""

import copy
import json

import pytest

from longevity.analysis.attribution_analysis import (
    adult_rows,
    analyze_constraint_migration,
    analyze_interaction,
    least_squares_slope,
    load_attribution_config,
    per_seed_attribution,
)


def _per_seed(bio=1.0, h_epi=0.001, life=68.0, health=60.0, slopes=None, failure="none"):
    drivers = ("dna_damage", "epigenetic_drift", "proteostasis_loss",
               "mitochondrial_dysfunction", "cellular_senescence",
               "stem_exhaustion", "chronic_inflammation", "cancer_prone")
    base = {d: 0.01 for d in drivers}
    if slopes:
        base.update(slopes)
    return {"bio_slope": bio, "h_epi_slope": h_epi, "lifespan": life,
            "healthspan": health, "driver_slopes": dict(base),
            "driver_finals": dict(base),
            "contributions": {d: 1.0 for d in drivers},
            "epigenetic_entropy_final": 0.05, "rollback_events": 5,
            "apoptosis_events": 1, "failure": failure, "resources": {}}


def _results(top_effects):
    baseline = {s: _per_seed(bio=1.0) for s in ("42", "7", "99")}
    ablations = {}
    drivers = ("dna_damage", "epigenetic_drift", "proteostasis_loss",
               "mitochondrial_dysfunction", "cellular_senescence",
               "stem_exhaustion", "chronic_inflammation", "cancer_prone")
    for d in drivers:
        delta = top_effects.get(d, 0.02)
        ablations[d] = {s: _per_seed(bio=1.0 - delta) for s in ("42", "7", "99")}
    return {"baseline": baseline, "ablations": ablations}


def test_least_squares_slope_math():
    assert least_squares_slope([0.0, 1.0, 2.0], [1.0, 3.0, 5.0]) == pytest.approx(2.0)
    assert least_squares_slope([5.0], [1.0]) == 0.0
    assert least_squares_slope([], []) == 0.0
    assert least_squares_slope([1.0, 1.0], [2.0, 3.0]) == 0.0


def test_adult_rows_setpoint():
    traj = [{"chronological_age": 10.0}, {"chronological_age": 25.0},
            {"chronological_age": 30.0, "epigenetic_backup": {"reference_age": 27.0}},
            {"chronological_age": 40.0}]
    rows = adult_rows(traj)
    assert [r["chronological_age"] for r in rows] == [30.0, 40.0]
    assert adult_rows([]) == []


def test_per_seed_attribution_rejects_empty():
    with pytest.raises(ValueError):
        per_seed_attribution([], {})


def test_single_driver_classification():
    verdict = analyze_constraint_migration(_results({"proteostasis_loss": 0.40}))
    assert verdict["classification"] == "single_driver_migration"
    assert verdict["candidate_binding_driver"] == "proteostasis_loss"
    assert verdict["confidence"] == "high"
    assert verdict["ranking"][0] == "proteostasis_loss"
    assert verdict["deterministic"] is True


def test_single_driver_close_margin_low_confidence():
    verdict = analyze_constraint_migration(
        _results({"proteostasis_loss": 0.35, "stem_exhaustion": 0.25}))
    assert verdict["classification"] == "single_driver_migration"
    assert verdict["confidence"] == "low"


def test_distributed_classification():
    verdict = analyze_constraint_migration(
        _results({"proteostasis_loss": 0.35, "stem_exhaustion": 0.33}))
    assert verdict["classification"] == "distributed_residual"
    assert verdict["candidate_binding_driver"] is None
    assert verdict["confidence"] == "medium"


def test_unresolved_classification():
    verdict = analyze_constraint_migration(_results({}))
    assert verdict["classification"] == "aggregation_or_unresolved_residual"
    assert verdict["candidate_binding_driver"] is None
    assert verdict["confidence"] == "low"
    assert verdict["diagnostic_decomposition"]["aggregation_formula_unchanged"] is True


def test_confounded_driver_excluded():
    results = _results({"proteostasis_loss": 0.40})
    for seed in results["ablations"]["proteostasis_loss"]:
        results["ablations"]["proteostasis_loss"][seed]["lifespan"] = 50.0
        results["ablations"]["proteostasis_loss"][seed]["failure"] = "other_failure"
    verdict = analyze_constraint_migration(results)
    assert verdict["ablation_results"]["proteostasis_loss"]["confounded"] is True
    assert verdict["classification"] == "aggregation_or_unresolved_residual"


def test_seed_mismatch_rejected():
    results = _results({})
    results["ablations"]["dna_damage"] = {"42": _per_seed(bio=0.9)}
    with pytest.raises(ValueError):
        analyze_constraint_migration(results)


def test_unknown_driver_and_empty_rejected():
    with pytest.raises(ValueError):
        analyze_constraint_migration({"baseline": {}, "ablations": {}})
    results = _results({})
    results["ablations"]["mystery"] = {s: _per_seed() for s in ("42", "7", "99")}
    with pytest.raises(ValueError):
        analyze_constraint_migration(results)
    with pytest.raises(ValueError):
        analyze_constraint_migration({"baseline": _results({})["baseline"],
                                      "ablations": _results({})["ablations"],
                                      "thresholds": {"relative": 5.0}})


def test_deterministic_analysis():
    first = analyze_constraint_migration(_results({"dna_damage": 0.05}))
    second = analyze_constraint_migration(_results({"dna_damage": 0.05}))
    assert first == second


def test_interaction_labels():
    base = 1.0
    mk = lambda bio: {s: _per_seed(bio=bio) for s in ("42", "7", "99")}
    add = analyze_interaction({"A": "x", "B": "y",
                               "conditions": {"A": mk(0.9), "B": mk(0.9), "AB": mk(0.8)}}, base)
    assert add["label"] == "approximately_additive"
    sup = analyze_interaction({"A": "x", "B": "y",
                               "conditions": {"A": mk(0.9), "B": mk(0.9), "AB": mk(0.5)}}, base)
    assert sup["label"] == "superadditive_model_interaction"
    sub = analyze_interaction({"A": "x", "B": "y",
                               "conditions": {"A": mk(0.9), "B": mk(0.9), "AB": mk(0.95)}}, base)
    assert sub["label"] == "subadditive_model_interaction"
    with pytest.raises(ValueError):
        analyze_interaction({"A": "x"}, base)


def test_load_config_validation(tmp_path):
    good = {"experiment_id": "x", "seeds": [42],
            "base_organism_config": "c.json", "drivers": [
                "dna_damage", "epigenetic_drift", "proteostasis_loss",
                "mitochondrial_dysfunction", "cellular_senescence",
                "stem_exhaustion", "chronic_inflammation", "cancer_prone"],
            "ablation_driver_scale": 0.1, "output_artifact": "o.json"}
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(good), encoding="utf-8")
    assert load_attribution_config(str(path))["experiment_id"] == "x"
    bad = dict(good, ablation_driver_scale=1.5)
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError):
        load_attribution_config(str(path))
    bad2 = dict(good, drivers=["dna_damage"])
    path.write_text(json.dumps(bad2), encoding="utf-8")
    with pytest.raises(ValueError):
        load_attribution_config(str(path))
    bad3 = dict(good)
    del bad3["seeds"]
    path.write_text(json.dumps(bad3), encoding="utf-8")
    with pytest.raises(ValueError):
        load_attribution_config(str(path))


def test_mini_study_schema_and_determinism(tmp_path):
    from longevity.analysis.attribution_analysis import run_attribution_study

    cfg = {"experiment_id": "tmp_9b_mini", "stage": "9b", "seeds": [42],
           "base_organism_config": "experiments/configs/organism_backup_rollback_baseline.json",
           "rollback_policy_overrides": {"policy_index": 6, "biomarker_threshold": 0.05,
                                         "intensity": 1.0, "interval": 5.0},
           "apoptosis_policy_overrides": {"policy_index": 7, "interval": 10.0},
           "ablation_driver_scale": 0.1,
           "drivers": ["dna_damage", "epigenetic_drift", "proteostasis_loss",
                       "mitochondrial_dysfunction", "cellular_senescence",
                       "stem_exhaustion", "chronic_inflammation", "cancer_prone"],
           "single_driver_relative_threshold": 0.3, "single_driver_margin": 2.0,
           "output_artifact": str(tmp_path / "mini.json")}
    cfg_path = tmp_path / "mini_cfg.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    first = run_attribution_study(str(cfg_path))
    second = run_attribution_study(str(cfg_path))
    assert first["classification"] in ("single_driver_migration", "distributed_residual",
                                       "aggregation_or_unresolved_residual")
    for run in (first, second):
        run.pop("runtime", None)
        run.pop("artifact_path", None)
    assert first == second
    for key in ("experiment_id", "seeds", "baseline", "ablations", "ranking",
                "classification", "candidate_binding_driver", "confidence",
                "notes", "hypothesis_status", "deterministic"):
        assert key in first
    assert first["hypothesis_status"] == "hypothesis_not_proven"
    assert len(first["ranking"]) == 8
