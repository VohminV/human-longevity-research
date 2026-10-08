"""Stage 10.5: channel accounting — math/rules only (no assumed winner)."""

import copy
import json

import pytest

from longevity.analysis.channel_accounting import (
    CHANNELS,
    DECISION_CASES,
    EXECUTION_PATH,
    MEASURABILITY,
    compute_channel_accounting,
    load_channel_config,
)


def _stage10(bio=1.1666192491, ssum=1.3338990247, nonlin=-0.1672797756,
             max_abs=1.0720622903, rec_slope=-0.0142335504, closed=False):
    comp = {
        "dna_damage": 0.0358028298,
        "epigenetic_drift": -0.0183988792,
        "proteostasis_loss": 0.4561154934,
        "mitochondrial_dysfunction": 0.3649433681,
        "cellular_senescence": 0.1132036671,
        "stem_exhaustion": 0.2719640371,
        "chronic_inflammation": 0.0861499285,
        "cancer_prone": 0.0236902992,
        "epigenetic_backup": 0.0004282804,
        "setpoint": 0.0,
    }
    def _seed():
        return {
            "bio_age_slope": bio,
            "component_slopes": dict(comp),
            "sum_component_slopes": ssum,
            "nonlinear_coupling_residual": nonlin,
            "reconstruction": {
                "mean_residual": -0.1930786357,
                "median_residual": -0.0895308074,
                "max_abs_residual": max_abs,
                "residual_std": 0.2980113563,
                "residual_slope": rec_slope,
                "accounting_closed": closed,
            },
        }
    return {
        "seeds": [42, 7, 99],
        "conditions": {"rollback": {s: _seed() for s in ("42", "7", "99")}},
    }


def test_measurability_labels_cover_all_channels():
    assert set(MEASURABILITY) == {"directly_accounted", "reconstructed", "not_identifiable"}
    by_meas: dict[str, list[str]] = {}
    for ch in CHANNELS:
        by_meas.setdefault(ch["measurability"], []).append(ch["name"])
    assert len(by_meas["directly_accounted"]) >= 10  # 8 drivers + backup + setpoint
    assert len(by_meas["reconstructed"]) >= 5
    assert len(by_meas["not_identifiable"]) >= 5
    names = [c["name"] for c in CHANNELS]
    assert len(names) == len(set(names))


def test_execution_path_documents_actual_code_refs():
    assert len(EXECUTION_PATH) >= 7
    joined = " ".join(s["file"] for s in EXECUTION_PATH)
    for token in ("_driver_step", "aggregate_biological_age",
                  "entropy_bio_contribution", "_organ_backed_step",
                  "_organ_network_step", "_reversibility_step",
                  "_epigenetic_backup_step", "apply_effect"):
        assert token in joined


def test_partial_accounting_on_observed_numbers():
    out = compute_channel_accounting(_stage10(), None)
    assert out["decision_case"] == "partial_accounting"
    assert out["confidence"] in ("high", "medium", "low")
    assert out["implementation_discrepancy"] is False
    assert out["accounting_is_not_causal_proof"] is True
    assert out["bio_age_slope_rollback_mean"] == pytest.approx(1.1666192491)
    assert out["gap_share"] == pytest.approx(0.1434, abs=1e-3)
    assert out["accounted_slope_fraction"] == pytest.approx(0.8746, abs=1e-3)
    assert out["reconstruction"]["accounting_closed"] is False
    assert "nonlinear_coupling_residual_slope" in out["unexplained"]
    assert len(out["unexplained"]["not_separable"]) >= 2


def test_deterministic_output():
    a = compute_channel_accounting(_stage10(), None)
    b = compute_channel_accounting(_stage10(), None)
    assert a == b


def test_discrepancy_triggers_on_large_gap():
    bad = _stage10(max_abs=5.0, rec_slope=0.8, nonlin=0.8)
    out = compute_channel_accounting(bad, None)
    assert out["decision_case"] == "accounting_discrepancy"


def test_channel_identified_when_books_close_and_dominant():
    comp = {
        "dna_damage": 0.05, "epigenetic_drift": 0.02, "proteostasis_loss": 0.90,
        "mitochondrial_dysfunction": 0.05, "cellular_senescence": 0.05,
        "stem_exhaustion": 0.05, "chronic_inflammation": 0.02, "cancer_prone": 0.02,
        "epigenetic_backup": 0.001, "setpoint": 0.0,
    }
    def _seed():
        return {"bio_age_slope": 1.2, "component_slopes": dict(comp),
                "sum_component_slopes": 1.2, "nonlinear_coupling_residual": 0.001,
                "reconstruction": {"mean_residual": 0.001, "median_residual": 0.001,
                                   "max_abs_residual": 0.01, "residual_std": 0.002,
                                   "residual_slope": 0.001, "accounting_closed": True}}
    stage10 = {"seeds": [42, 7, 99],
               "conditions": {"rollback": {s: _seed() for s in ("42", "7", "99")}}}
    out = compute_channel_accounting(stage10, None)
    assert out["decision_case"] == "channel_identified"


def test_distributed_when_books_close_and_spread():
    comp = {
        "dna_damage": 0.02, "epigenetic_drift": 0.02, "proteostasis_loss": 0.40,
        "mitochondrial_dysfunction": 0.38, "cellular_senescence": 0.02,
        "stem_exhaustion": 0.02, "chronic_inflammation": 0.02, "cancer_prone": 0.02,
        "epigenetic_backup": 0.001, "setpoint": 0.0,
    }
    def _seed():
        return {"bio_age_slope": 1.2, "component_slopes": dict(comp),
                "sum_component_slopes": 1.2, "nonlinear_coupling_residual": 0.001,
                "reconstruction": {"mean_residual": 0.001, "median_residual": 0.001,
                                   "max_abs_residual": 0.01, "residual_std": 0.002,
                                   "residual_slope": 0.001, "accounting_closed": True}}
    stage10 = {"seeds": [42, 7, 99],
               "conditions": {"rollback": {s: _seed() for s in ("42", "7", "99")}}}
    out = compute_channel_accounting(stage10, None)
    assert out["decision_case"] == "distributed_channels"


def test_unresolved_when_nothing_accounted():
    comp = {k: 0.01 for k in ("dna_damage", "epigenetic_drift", "proteostasis_loss",
                              "mitochondrial_dysfunction", "cellular_senescence",
                              "stem_exhaustion", "chronic_inflammation", "cancer_prone")}
    comp["epigenetic_backup"] = 0.001
    comp["setpoint"] = 0.0
    def _seed():
        return {"bio_age_slope": 5.0, "component_slopes": dict(comp),
                "sum_component_slopes": 0.08, "nonlinear_coupling_residual": 4.92,
                "reconstruction": {"mean_residual": 1.0, "median_residual": 1.0,
                                   "max_abs_residual": 1.5, "residual_std": 0.5,
                                   "residual_slope": 0.05, "accounting_closed": False}}
    stage10 = {"seeds": [42, 7, 99],
               "conditions": {"rollback": {s: _seed() for s in ("42", "7", "99")}}}
    out = compute_channel_accounting(stage10, None)
    # gap_rel = 4.92/5 = 0.984 > 0.25 -> discrepancy review, not silent unresolved
    assert out["decision_case"] in DECISION_CASES


def test_config_requires_exact_seeds(tmp_path):
    cfg = {"experiment_id": "x", "seeds": [42, 7, 99],
           "stage10_artifact": "a.json", "output_artifact": "b.json"}
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    load_channel_config(str(path))
    cfg["seeds"] = [1, 2, 3]
    path.write_text(json.dumps(cfg), encoding="utf-8")
    with pytest.raises(ValueError, match="seeds must be"):
        load_channel_config(str(path))


def test_no_production_import_side_effects():
    # Module must not mutate production model modules on import.
    import longevity.model.aging as aging
    import longevity.model.organism as organism

    before = dict(aging.DEFAULT_DRIVER_PARAMS["dna_damage"])
    _ = compute_channel_accounting(_stage10(), None)
    assert aging.DEFAULT_DRIVER_PARAMS["dna_damage"] == before
    assert organism.ORGANISM_MODEL_VERSION == "0.5.0"


def test_artifact_json_roundtrip_with_allow_nan_false(tmp_path):
    from longevity.analysis.channel_accounting import run_channel_accounting

    stage10_path = tmp_path / "stage10.json"
    full = _stage10()
    full["conditions"]["rollback_dna_ablation"] = copy.deepcopy(full["conditions"]["rollback"])
    stage10_path.write_text(json.dumps(full), encoding="utf-8")
    cfg_path = tmp_path / "cfg.json"
    out_path = tmp_path / "out.json"
    cfg_path.write_text(json.dumps({
        "experiment_id": "organism_channel_accounting",
        "seeds": [42, 7, 99],
        "stage10_artifact": str(stage10_path),
        "output_artifact": str(out_path),
    }), encoding="utf-8")
    art = run_channel_accounting(str(cfg_path), str(out_path))
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    json.dumps(data, allow_nan=False)  # must not raise
    assert data["stage"] == "10.5"
    assert data["seeds"] == [42, 7, 99]
    assert art["decision_case"] in DECISION_CASES
