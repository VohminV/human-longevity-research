"""Stage 5A: organism metrics -- summaries, slopes, bounded degradation, fitness."""

import copy
import math

import pytest

from longevity.analysis.organism_metrics import (
    aggregate_summaries,
    compare_against_baseline,
    compute_organism_summary,
    fitness,
    pareto_frontier,
    validate_fitness_weights,
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


def _run(seed=42, years=150.0, dt=0.5, policies=None):
    from longevity.model.intervention import PolicySet
    model = OrganismModel(seed=seed)
    return model.run(years, dt, BOUNDS, THRESHOLDS, PolicySet(policies) if policies else None)


def test_summary_schema_and_healthspan_le_lifespan():
    trajectory = _run()
    summary = compute_organism_summary(trajectory, 0.5, THRESHOLDS)
    assert summary["healthspan"] <= summary["lifespan"] + 1e-9
    assert summary["lifespan"] > 20.0  # reaches adulthood and beyond
    assert summary["primary_cause_of_death"] != "none"
    assert set(summary) >= {"lifespan", "healthspan", "damage_slope_after_adulthood",
                            "biological_age_slope_after_adulthood", "bounded_degradation_indicator",
                            "neural_identity_preservation", "rejuvenation_events",
                            "final_function_by_system", "time_to_system_failure_by_system"}
    with pytest.raises(ValueError):
        compute_organism_summary([], 0.5, THRESHOLDS)


def test_slopes_and_bounded_on_synthetic():
    healthy = {"function": 0.9, "damage": 0.05, "failure_threshold": 0.25, "critical": True,
               "reserve": 1.0, "ecm_quality": 1.0, "reserve_cap": 1.0, "vascular_quality": 1.0,
               "immune_pressure": 0.1, "cancer_risk": 0.0, "fibrosis_index": 0.0,
               "brain_cns": 0.0, "aging_rate": 0.01, "repair_capacity": 0.01,
               "warning_threshold": 0.4, "inflammation_sensitivity": 0.5, "cancer_sensitivity": 0.5,
               "neural_identity_relevance": 0.0, "vitality_weight": 1.0, "growth_rate": 0.4,
               "informational_continuity": 1.0}

    def _row(age, bio, damage, alive=True, cause="none"):
        systems = {name: dict(healthy, function=0.9) for name in
                   ("brain_cns", "cardiovascular", "respiratory", "hepatic",
                    "renal", "immune", "metabolic", "musculoskeletal")}
        return {"chronological_age": age, "biological_age": bio, "global_damage": damage,
                "developmental_stage": "adult_homeostasis", "alive": alive,
                "functional_reserve": 0.9, "vitality_index": 0.9,
                "senescence_burden": 0.05, "inflammation": 0.05, "fibrosis": 0.05,
                "cancer_burden": 0.05, "epigenetic_drift": 0.05, "systems": systems,
                "intervention_history": [], "rejuvenation_events": 0,
                "failure_cause": cause, "death_time": None if alive else age}

    flat = [_row(30.0 + i, 30.0 + 0.001 * i, 0.05) for i in range(5)]
    summary = compute_organism_summary(flat, 1.0, THRESHOLDS, epsilon=0.01)
    assert summary["biological_age_slope_after_adulthood"] == pytest.approx(0.001, abs=1e-9)
    assert summary["bounded_degradation_indicator"] is True
    rising = [_row(30.0 + i, 30.0 + 1.0 * i, 0.05 + 0.05 * i) for i in range(5)]
    summary2 = compute_organism_summary(rising, 1.0, THRESHOLDS, epsilon=0.01)
    assert summary2["bounded_degradation_indicator"] is False
    dead = dict(flat[-1], alive=False, failure_cause="brain_failure", death_time=34.0)
    summary3 = compute_organism_summary(flat + [dead], 1.0, THRESHOLDS)
    assert summary3["lifespan"] == pytest.approx(34.0)
    assert summary3["primary_cause_of_death"] == "brain_failure"


def test_biological_age_can_drop_below_chronological():
    from longevity.model.intervention import PolicySet, build_effect
    model = OrganismModel(seed=42)
    model.run(60.0, 0.5, BOUNDS, THRESHOLDS, None)
    bio_before, chrono = model.state.biological_age, model.state.chronological_age
    model.apply_effect(build_effect("molecular_repair", intensity=2.0, source="test"), "test")
    assert model.state.biological_age < bio_before
    assert model.state.biological_age < chrono  # rejuvenated below chronological


def test_compare_and_fitness_and_pareto():
    base = {"lifespan": 68.0, "healthspan": 61.0, "functional_reserve_area": 50.0,
            "damage_auc": 10.0, "cancer_auc": 2.0, "inflammation_auc": 3.0,
            "neural_identity_preservation": 0.9, "bounded_degradation_indicator": False}
    better = dict(base, lifespan=80.0, healthspan=73.0)
    comparison = compare_against_baseline(better, base)
    assert comparison["lifespan_gain"] == pytest.approx(12.0)
    weights = validate_fitness_weights({})
    assert fitness(better, weights) > fitness(base, weights)
    with pytest.raises(ValueError):
        validate_fitness_weights({"w_lifespan": -1.0})
    with pytest.raises(ValueError):
        validate_fitness_weights({"telepathy": 1.0})
    candidates = [
        {"combo": "a", "lifespan": 80.0, "healthspan": 70.0, "cancer_auc": 2.0},
        {"combo": "b", "lifespan": 70.0, "healthspan": 60.0, "cancer_auc": 3.0},
        {"combo": "c", "lifespan": 80.0, "healthspan": 70.0, "cancer_auc": 1.0},
    ]
    frontier = pareto_frontier(candidates)
    assert {c["combo"] for c in frontier} == {"c"}
    with pytest.raises(ValueError):
        from longevity.analysis.organism_metrics import aggregate_summaries as agg
        agg([])


def test_aggregate_counts_causes_and_bounded():
    summaries = [
        {"lifespan": 70.0, "healthspan": 60.0, "damage_auc": 9.0, "cancer_auc": 2.0,
         "functional_reserve_area": 45.0, "biological_age_slope_after_adulthood": 0.9,
         "primary_cause_of_death": "brain_failure", "bounded_degradation_indicator": False},
        {"lifespan": 80.0, "healthspan": 70.0, "damage_auc": 8.0, "cancer_auc": 1.0,
         "functional_reserve_area": 55.0, "biological_age_slope_after_adulthood": 0.8,
         "primary_cause_of_death": "none", "bounded_degradation_indicator": True},
    ]
    aggregate = aggregate_summaries(summaries)
    assert aggregate["lifespan"]["mean"] == pytest.approx(75.0)
    assert aggregate["primary_cause_counts"] == {"brain_failure": 1, "none": 1}
    assert aggregate["bounded_count"] == 1
    assert aggregate["n_runs"] == 2
