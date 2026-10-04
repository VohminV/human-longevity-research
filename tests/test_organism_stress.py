"""Stage 5B: rolling windows, robust indicator, binding constraints, stress."""

import copy
import math

import pytest

from longevity.analysis.organism_metrics import (
    binding_constraints,
    robust_aggregate,
    robust_bounded_degradation,
    rolling_slopes,
    validate_robust_criteria,
)
from longevity.experiment.organism_robust import (
    OrganismRobustConfig,
    load_robust_config,
    run_robust_evaluation,
    write_robust_outputs,
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


def _healthy_trajectory(n=12, bio_slope=0.001):
    rows = []
    for i in range(n):
        age = 30.0 + i
        systems = {name: {"function": 0.9, "damage": 0.05, "failure_threshold": 0.25,
                          "warning_threshold": 0.4, "critical": True, "reserve": 1.0,
                          "reserve_cap": 1.0, "aging_rate": 0.01, "repair_capacity": 0.01,
                          "vascular_quality": 0.9, "ecm_quality": 0.9, "immune_pressure": 0.1,
                          "cancer_risk": 0.0, "fibrosis_index": 0.0,
                          "inflammation_sensitivity": 0.5, "cancer_sensitivity": 0.5,
                          "neural_identity_relevance": 0.0, "vitality_weight": 1.0,
                          "growth_rate": 0.4, "informational_continuity": 0.95}
                    for name in ("brain_cns", "cardiovascular", "respiratory", "hepatic",
                                 "renal", "immune", "metabolic", "musculoskeletal")}
        rows.append({"chronological_age": age, "biological_age": 30.0 + bio_slope * i,
                     "global_damage": 0.05, "developmental_stage": "adult_homeostasis",
                     "senescence_burden": 0.05, "inflammation": 0.05, "fibrosis": 0.05,
                     "cancer_burden": 0.05, "epigenetic_drift": 0.05, "systems": systems})
    return rows


def test_rolling_slopes_and_windows():
    rows = rolling_slopes(_healthy_trajectory(), 25.0)
    assert rows
    assert rows[0]["biological_age_slope"] == pytest.approx(0.001, abs=1e-9)
    assert all(r["min_critical_function"] == pytest.approx(0.9) for r in rows)
    with pytest.raises(ValueError):
        rolling_slopes([], 10.0)


def test_robust_indicator_healthy_vs_declining():
    healthy = [{"bounded_degradation_indicator": True, "biological_age_slope_after_adulthood": 0.01,
                "damage_slope_after_adulthood": 0.001, "cancer_auc": 1.0, "lifespan": 150.0} for _ in range(3)]
    result = robust_bounded_degradation(healthy)
    assert result["robust_bounded_degradation_indicator"] is True
    assert result["success_rate_bounded"] == pytest.approx(1.0)
    mixed = healthy[:2] + [{"bounded_degradation_indicator": False, "biological_age_slope_after_adulthood": 2.0,
                            "damage_slope_after_adulthood": 0.5, "cancer_auc": 9.0, "lifespan": 60.0}]
    result2 = robust_bounded_degradation(mixed)
    assert result2["robust_bounded_degradation_indicator"] is False
    assert result2["worst_case_biological_age_slope"] == pytest.approx(2.0)
    with pytest.raises(ValueError):
        robust_bounded_degradation([])
    with pytest.raises(ValueError):
        validate_robust_criteria({"min_success_rate": 2.0})


def test_binding_first_and_sequence_and_purity():
    rows = _healthy_trajectory()
    before = copy.deepcopy(rows)
    binding = binding_constraints(rows)
    assert binding["first_constraint_violated"] == "none"
    assert binding["binding_constraint_sequence"] == []
    assert rows == before
    assert binding["n_windows_evaluated"] > 0
    bad = _healthy_trajectory()
    for row in bad[6:]:
        row["cancer_burden"] = 0.9
    binding2 = binding_constraints(bad)
    assert binding2["first_constraint_violated"] == "cancer_burden"
    assert binding2["time_to_first_constraint_violation"] is not None


def test_robust_aggregate_and_distributions():
    from longevity.analysis.organism_metrics import compute_organism_summary
    model = OrganismModel(seed=42)
    trajectory = model.run(150.0, 0.5, BOUNDS, THRESHOLDS, None)
    summary = compute_organism_summary(trajectory, 0.5, THRESHOLDS)
    aggregate = robust_aggregate([summary, summary], [trajectory, trajectory])
    assert aggregate["n_runs"] == 2
    assert aggregate["robust"]["success_rate_bounded"] in (0.0, 1.0)
    assert aggregate["median_lifespan"] == pytest.approx(summary["lifespan"])
    assert aggregate["binding_constraint_distribution"]
    assert aggregate["min_informational_continuity"] <= 1.0


def _tiny_robust(**overrides):
    base = {
        "experiment_id": "robust-test",
        "seeds": [11, 12, 13],
        "scenarios": ["nominal", "shocks_only"],
        "runs": {"baseline": {
            "organism_id": "base", "seed": 11, "duration_years": 150.0, "dt": 1.0,
            "organism_parameters": {}, "stage_bounds": {}, "thresholds": {},
            "policies": [], "bounded_epsilon": 0.01}},
        "robust_criteria": {},
        "output_prefix": "",
        "notes": "",
    }
    base.update(overrides)
    return OrganismRobustConfig.from_config_dict(base)


def test_stress_suite_end_to_end(tmp_path):
    result = run_robust_evaluation(_tiny_robust())
    assert len(result["cells"]) == 2  # 1 run x 2 scenarios
    assert result["model_scope"] == "abstract_organism_life_course"
    assert result["immortality_status"] == "hypothesis_not_proven"
    paths = write_robust_outputs(result, str(tmp_path / "robust"))
    assert set(paths) == {"long_csv", "summary_csv", "summary_json",
                          "robust_comparison_json", "binding_constraints_json", "stress_suite_json"}
    import csv as _csv
    import json as _json
    with open(paths["long_csv"], encoding="utf-8", newline="") as fh:
        rows = list(_csv.DictReader(fh))
    assert len(rows) == 2 * 3
    for key in ("summary_json", "robust_comparison_json", "binding_constraints_json", "stress_suite_json"):
        with open(paths[key], encoding="utf-8") as fh:
            _json.load(fh)

    def _walk(node, path="$"):
        if isinstance(node, float):
            assert math.isfinite(node), f"non-finite at {path}"
        elif isinstance(node, dict):
            for key, value in node.items():
                _walk(value, f"{path}[{key}]")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                _walk(value, f"{path}[{index}]")

    _walk(result)


def test_stress_determinism_and_validation():
    first = run_robust_evaluation(_tiny_robust())
    second = run_robust_evaluation(_tiny_robust())
    assert first["cells"] == second["cells"]
    assert first["config_hash"] == second["config_hash"]
    with pytest.raises(ValueError):
        _tiny_robust(seeds=[11])
    with pytest.raises(ValueError):
        _tiny_robust(scenarios=[])
    with pytest.raises(ValueError):
        _tiny_robust(scenarios=["meteor_strike"])
    with pytest.raises(ValueError):
        _tiny_robust(runs={})


def test_real_stress_config_loads():
    config = load_robust_config("experiments/configs/organism_stress_suite.json")
    assert len(config.seeds) >= 2 and len(config.scenarios) >= 2
