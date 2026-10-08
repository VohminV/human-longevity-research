"""Stage 10: biological-age decomposition — math/rules only (no assumed winner)."""

import copy

import pytest

from longevity.analysis.biological_age_decomposition import (
    adult_rows,
    analyze_biological_age_decomposition,
    decompose_condition,
    detect_nonlinear_coupling,
    least_squares_slope,
    reconstruct_series,
)


def _traj(n=10, drift=0.01, entropy=0.001, setpoint=25.0):
    traj = []
    for i in range(n):
        age = setpoint + i * 1.0
        dmg = {name: 0.05 + i * drift for name in (
            "dna_damage", "epigenetic_drift", "proteostasis_loss",
            "mitochondrial_dysfunction", "cellular_senescence",
            "stem_exhaustion", "chronic_inflammation", "cancer_prone")}
        # Build bio exactly from the production formula so reconstruction closes.
        from longevity.model.aging import DEFAULT_DRIVER_PARAMS
        total = setpoint + sum(
            DEFAULT_DRIVER_PARAMS[k]["contribution"] * dmg[k] for k in dmg)
        bio = total + 8.0 * (entropy * i)
        traj.append({
            "chronological_age": age,
            "biological_age": bio,
            "aging": {"drivers": {k: {"damage": v} for k, v in dmg.items()}},
            "epigenetic_backup": {"epigenetic_entropy": entropy * i,
                                  "reference_age": setpoint},
        })
    return traj


def test_least_squares_slope_math():
    assert least_squares_slope([0.0, 1.0, 2.0], [1.0, 3.0, 5.0]) == pytest.approx(2.0)
    assert least_squares_slope([5.0], [1.0]) == 0.0
    assert least_squares_slope([], []) == 0.0
    assert least_squares_slope([1.0, 1.0], [2.0, 3.0]) == 0.0


def test_adult_rows_reference_age():
    traj = [{"chronological_age": 10.0}, {"chronological_age": 25.0},
            {"chronological_age": 30.0, "epigenetic_backup": {"reference_age": 27.0}},
            {"chronological_age": 40.0}]
    rows = adult_rows(traj)
    assert [r["chronological_age"] for r in rows] == [30.0, 40.0]
    assert adult_rows([]) == []


def test_reconstruction_closes_on_exact_formula():
    traj = _traj()
    adult = adult_rows(traj)
    out = reconstruct_series(adult)
    assert out["reconstruction"]["accounting_closed"] is True
    assert out["reconstruction"]["max_abs_residual"] == pytest.approx(0.0, abs=1e-9)


def test_slope_decomposition_sums():
    traj = _traj()
    dec = decompose_condition(traj, {})
    total = dec["sum_component_slopes"]
    assert total == pytest.approx(dec["bio_age_slope"], rel=1e-6)
    assert dec["setpoint_slope"] == 0.0
    assert dec["deterministic"] is True


def test_residual_calculation_sign():
    traj = _traj()
    # Push bio up by a constant: residual mean +1, slope unchanged.
    for row in traj:
        row["biological_age"] += 1.0
    adult = adult_rows(traj)
    out = reconstruct_series(adult)
    assert out["reconstruction"]["mean_residual"] == pytest.approx(1.0)
    assert abs(out["reconstruction"]["residual_slope"]) < 1e-9


def _per_seed(bio=1.2, top="proteostasis_loss", top_slope=0.6):
    drivers = ("dna_damage", "epigenetic_drift", "proteostasis_loss",
               "mitochondrial_dysfunction", "cellular_senescence",
               "stem_exhaustion", "chronic_inflammation", "cancer_prone")
    comp = {d: 0.05 for d in drivers}
    comp[top] = top_slope
    comp["epigenetic_backup"] = 0.001
    comp["setpoint"] = 25.0
    return {"bio_age_slope": bio, "component_slopes": comp,
            "reconstruction": {"mean_residual": 0.01, "median_residual": 0.01,
                               "max_abs_residual": 0.02, "residual_std": 0.005,
                               "residual_slope": 0.001, "accounting_closed": True},
            "nonlinear_coupling_residual": 0.001}


def _results(top="proteostasis_loss", top_slope=0.9, bio=1.2):
    base = {s: _per_seed(bio=bio, top=top, top_slope=top_slope) for s in ("42", "7", "99")}
    roll = {s: _per_seed(bio=bio, top=top, top_slope=top_slope) for s in ("42", "7", "99")}
    dna = {s: _per_seed(bio=bio, top=top, top_slope=top_slope) for s in ("42", "7", "99")}
    return {"baseline": base, "rollback": roll, "rollback_dna_ablation": dna}


def test_multi_condition_comparison_schema():
    verdict = analyze_biological_age_decomposition(_results())
    assert set(verdict["conditions"]) >= {"baseline", "rollback", "rollback_dna_ablation"}
    assert verdict["classification"] in (
        "driver_contribution", "distributed_contribution", "setpoint_dynamics",
        "aggregation_or_coupling", "accounting_discrepancy", "unresolved")


def test_deterministic_output():
    a = analyze_biological_age_decomposition(_results())
    b = analyze_biological_age_decomposition(_results())
    assert a == b


def test_classification_driver_dominant():
    verdict = analyze_biological_age_decomposition(_results(top_slope=0.9, bio=1.2))
    # 0.9 of ~1.25 positive sum = 72% share, margin holds → single driver.
    assert verdict["classification"] == "driver_contribution"
    assert verdict["confidence"] in ("high", "medium", "low")


def test_classification_distributed():
    # Two substantial, none >=50%: proteostasis 0.3 + mito-like via second call.
    drivers = ("dna_damage", "epigenetic_drift", "proteostasis_loss",
               "mitochondrial_dysfunction", "cellular_senescence",
               "stem_exhaustion", "chronic_inflammation", "cancer_prone")
    def _mix():
        comp = {d: 0.02 for d in drivers}
        comp["proteostasis_loss"] = 0.40
        comp["mitochondrial_dysfunction"] = 0.38
        comp["epigenetic_backup"] = 0.001
        comp["setpoint"] = 25.0
        return {"bio_age_slope": 1.2, "component_slopes": comp,
                "reconstruction": {"mean_residual": 0.01, "median_residual": 0.01,
                                   "max_abs_residual": 0.02, "residual_std": 0.005,
                                   "residual_slope": 0.001, "accounting_closed": True},
                "nonlinear_coupling_residual": 0.001}
    res = {"baseline": {s: _mix() for s in ("42", "7", "99")},
           "rollback": {s: _mix() for s in ("42", "7", "99")}}
    verdict = analyze_biological_age_decomposition(res)
    assert verdict["classification"] == "distributed_contribution"


def test_classification_accounting_discrepancy():
    bad = _per_seed()
    bad["reconstruction"] = {"mean_residual": 5.0, "median_residual": 5.0,
                             "max_abs_residual": 5.0, "residual_std": 1.0,
                             "residual_slope": 0.8, "accounting_closed": False}
    bad["nonlinear_coupling_residual"] = 0.8
    res = {"baseline": {"42": copy.deepcopy(bad)},
           "rollback": {"42": copy.deepcopy(bad)}}
    verdict = analyze_biological_age_decomposition(res)
    assert verdict["classification"] == "accounting_discrepancy"


def test_nonlinear_terms_documented():
    info = detect_nonlinear_coupling()
    assert info["detected"] is True
    assert len(info["terms"]) >= 5


def test_schema_keys():
    verdict = analyze_biological_age_decomposition(_results())
    for key in ("bio_age_slope", "conditions", "component_slopes", "setpoint",
                "reconstruction", "nonlinear_coupling", "classification", "confidence"):
        assert key in verdict
