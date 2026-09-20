import pytest

from longevity.biology.params import DNA_DAMAGE_KEYS, MORTALITY_KEYS, TELOMERE_KEYS, TOP_LEVEL_KEYS
from longevity.calibration.compare import ModelValue, compare_metric, compare_reference_targets, distribute
from longevity.calibration.multirun import extract_calibration_metrics, run_multiseed_calibration
from longevity.calibration.reference import (
    ALL_REFERENCE_POINTS,
    BLASTOCYST_COUNTS,
    CALIBRATION_DATASET_VERSION,
    MORULA_CELL_COUNT_APPROX,
    PARAMETER_STATUS,
    STAGE_REACH_TIMES,
    parameter_status_table,
)
from longevity.calibration.stages import DevelopmentalStage, infer_stage
from longevity.experiment.config import ExperimentConfig
from longevity.experiment.runner import run_experiment
from longevity.sim.engine import PopulationEngine
from longevity.sim.rng import Rng

SLOW = {"doubling_time_mean": 10.8, "doubling_time_sd": 1.2}
DETERMINISTIC = {"doubling_time_mean": 5.0, "doubling_time_sd": 0.0}


def make_config(**overrides) -> ExperimentConfig:
    base = {
        "experiment_id": "exp-calib-test",
        "seed": 42,
        "population": 1,
        "duration": 60.0,
        "model_version": "0.1.0",
        "data_version": "0.1.0",
        "parameters": {},
        "interventions": [],
        "metrics_config": {},
    }
    base.update(overrides)
    return ExperimentConfig(**base)


# ---------------------------------------------------------------------------
# Reference data integrity
# ---------------------------------------------------------------------------


def test_reference_points_well_formed():
    for key, point in ALL_REFERENCE_POINTS.items():
        assert point.key == key
        assert point.observed_mean >= 0
        if point.observed_sd is not None:
            assert point.observed_sd >= 0
        if point.observed_range is not None:
            lo, hi = point.observed_range
            assert lo < hi
            assert lo <= point.observed_mean <= hi
        assert point.source
        assert point.units
    assert len(ALL_REFERENCE_POINTS) == len({p.key for p in ALL_REFERENCE_POINTS.values()})


def test_stage_timing_is_monotonic():
    times = [
        ALL_REFERENCE_POINTS[key].observed_mean
        for key in ("time_to_2_cell", "time_to_4_cell", "time_to_8_cell", "time_to_morula", "time_to_blastocyst")
    ]
    assert times == sorted(times)


def test_stage_times_carry_ranges_and_counts_carry_sd():
    for point in STAGE_REACH_TIMES:
        assert point.key.startswith("time_to_")
        assert point.observed_range is not None
    for point in BLASTOCYST_COUNTS:
        assert point.key.startswith("cell_count_at_")
        assert point.observed_sd is not None and point.observed_sd > 0
        assert point.observed_range is None


def test_calibration_dataset_version():
    assert CALIBRATION_DATASET_VERSION == "preimplantation/v1"


# ---------------------------------------------------------------------------
# Parameter status registry
# ---------------------------------------------------------------------------


def test_parameter_status_covers_all_model_parameters():
    group_keys = {
        "telomere": TELOMERE_KEYS,
        "dna_damage": DNA_DAMAGE_KEYS,
        "mortality": MORTALITY_KEYS,
    }
    missing = {"doubling_time_mean", "doubling_time_sd"}
    for entry in PARAMETER_STATUS:
        parts = entry.path.split(".")
        assert parts[0] in TOP_LEVEL_KEYS
        assert len(parts) in (1, 2)
        if len(parts) == 2:
            assert parts[1] in group_keys[parts[0]]
        missing.discard(entry.path)
    assert not missing


def test_parameter_status_uses_required_taxonomy():
    statuses = {entry.status for entry in PARAMETER_STATUS}
    assert {s.value for s in statuses} >= {"inf", "assumption", "unknown"}
    growth = {e.path: e for e in PARAMETER_STATUS if e.path in ("doubling_time_mean", "doubling_time_sd")}
    assert growth["doubling_time_mean"].value == 10.8
    assert growth["doubling_time_sd"].value == 1.2
    table = parameter_status_table()
    assert len(table) == len(PARAMETER_STATUS)
    assert set(table[0]) == {"parameter", "status", "value", "rationale", "source"}


# ---------------------------------------------------------------------------
# Stage inference
# ---------------------------------------------------------------------------


def test_infer_stage_zygote():
    assert infer_stage(0.0, 1).stage == DevelopmentalStage.ZYGOTE
    # a lone cell is never promoted, even at a late time
    assert infer_stage(200.0, 1).stage == DevelopmentalStage.ZYGOTE


def test_infer_stage_cleavage_bands():
    assert infer_stage(30.0, 2).stage == DevelopmentalStage.TWO_CELL
    assert infer_stage(46.0, 3).stage == DevelopmentalStage.TWO_CELL
    assert infer_stage(40.0, 4).stage == DevelopmentalStage.FOUR_CELL
    assert infer_stage(40.0, 7).stage == DevelopmentalStage.FOUR_CELL
    assert infer_stage(40.0, 9).stage == DevelopmentalStage.EIGHT_CELL


def test_infer_stage_morula_and_blastocyst():
    morula_lo, morula_hi = MORULA_CELL_COUNT_APPROX
    assert infer_stage(80.0, morula_lo).stage == DevelopmentalStage.MORULA
    assert infer_stage(95.0, morula_hi).stage == DevelopmentalStage.MORULA
    assert infer_stage(100.0, morula_hi).stage == DevelopmentalStage.BLASTOCYST
    assert infer_stage(120.0, 40).stage == DevelopmentalStage.BLASTOCYST


def test_infer_stage_compaction_short_circuit():
    assert infer_stage(80.0, 16, compacted=True).stage == DevelopmentalStage.MORULA
    assert infer_stage(120.0, 20, compacted=True).stage == DevelopmentalStage.BLASTOCYST


def test_infer_stage_never_promotes_late_small_count():
    # a 5-cell embryo at 200 h must NOT be labelled blastocyst (the model has
    # no cavitation), no matter how late it is
    inference = infer_stage(200.0, 5)
    assert inference.stage == DevelopmentalStage.FOUR_CELL
    assert inference.rationale


def test_infer_stage_validates_inputs():
    with pytest.raises(ValueError):
        infer_stage(-1.0, 5)
    with pytest.raises(ValueError):
        infer_stage(10.0, -2)


# ---------------------------------------------------------------------------
# Milestone recording (engine + runner)
# ---------------------------------------------------------------------------


def test_milestone_recording_surfaces_events_and_is_off_by_default():
    config = make_config(duration=60.0, parameters=SLOW)
    result = run_experiment(config, record_milestones=True)
    milestones = result["metrics"]["milestones"]
    assert milestones
    times = [m["sim_time"] for m in milestones]
    assert times == sorted(times)
    assert set(milestones[0]) >= {"sim_time", "live_count", "born_count", "dead_count"}
    assert run_experiment(config)["metrics"]["milestones"] == []


def test_milestone_recording_is_deterministic():
    def run() -> PopulationEngine:
        engine = PopulationEngine(Rng(42), DETERMINISTIC, population=1, record_milestones=True)
        engine.run_until(30.0)
        return engine

    first, second = run(), run()
    assert [m["sim_time"] for m in first.milestones] == [m["sim_time"] for m in second.milestones]
    assert first.living_count() == second.living_count() == 64
    assert first.milestones[0]["sim_time"] == 5.0
    assert first.milestones[0]["live_count"] == 2


def test_cleavage_timing_derived_from_milestones():
    engine = PopulationEngine(Rng(1), DETERMINISTIC, population=1, record_milestones=True)
    engine.run_until(30.0)
    reach = {n: next(m["sim_time"] for m in engine.milestones if m["live_count"] >= n) for n in (2, 4, 8)}
    assert reach[2] == 5.0
    assert reach[4] == 10.0
    assert reach[8] == 15.0
    assert reach[2] < reach[4] < reach[8]


def test_checkpoint_restore_keeps_recording_milestones():
    original = PopulationEngine(Rng(3), DETERMINISTIC, population=1, record_milestones=True)
    original.run_until(12.0)
    snapshot = original.to_checkpoint_dict()
    original.run_until(30.0)

    restored = PopulationEngine.from_checkpoint(snapshot)
    assert restored.milestones_enabled is True
    restored.run_until(30.0)
    assert [m["sim_time"] for m in restored.milestones] == [m["sim_time"] for m in original.milestones]
    assert restored.living_count() == original.living_count()


# ---------------------------------------------------------------------------
# Comparison math
# ---------------------------------------------------------------------------


def test_compare_metric_range_verdict():
    result = compare_metric("time_to_2_cell", ModelValue(mean=30.0, n_seeds=1))
    assert result.observed_mean == 27.0
    assert result.absolute_error == pytest.approx(3.0)
    assert result.relative_error == 0.1111  # rounded to 4 dp by compare_metric
    assert result.within_observed is False
    assert compare_metric("time_to_2_cell", ModelValue(mean=27.0, n_seeds=1)).within_observed is True


def test_compare_metric_sd_verdict():
    # blastocyst counts use mean +/- sd, no range
    hit = compare_metric("cell_count_at_120h", ModelValue(mean=60.0, n_seeds=4))
    assert hit.within_observed is True
    miss = compare_metric("cell_count_at_120h", ModelValue(mean=2000.0, n_seeds=4))
    assert miss.within_observed is False


def test_distribute_statistics():
    mv = distribute((1.0, 2.0, 3.0))
    assert mv.mean == pytest.approx(2.0)
    assert mv.sd == pytest.approx((2.0 / 3.0) ** 0.5)
    assert mv.n_seeds == 3
    assert mv.values == (1.0, 2.0, 3.0)
    with pytest.raises(ValueError):
        distribute(())


def test_compare_reference_targets_order_and_subset():
    rows = compare_reference_targets({"time_to_8_cell": ModelValue(mean=34.0)})
    assert [r["key"] for r in rows] == ["time_to_8_cell"]
    assert rows[0]["within_observed"] is False


# ---------------------------------------------------------------------------
# Multi-seed calibration report
# ---------------------------------------------------------------------------


def test_extract_calibration_metrics_requires_milestones():
    result = run_experiment(make_config(duration=20.0, parameters=DETERMINISTIC), record_milestones=False)
    with pytest.raises(ValueError):
        extract_calibration_metrics(result, cell_count_times=(20,))


def test_run_multiseed_calibration_report():
    config = make_config(duration=60.0, parameters=DETERMINISTIC, metrics_config={"sample_interval": 5.0})
    report = run_multiseed_calibration(config, seeds=(1, 2, 3), cell_count_times=(20,))

    expected = {
        "experiment_id",
        "model_version",
        "data_version",
        "calibration_dataset",
        "parameters",
        "parameter_status",
        "population",
        "duration_hours",
        "sample_interval_hours",
        "seeds",
        "n_seeds",
        "per_seed_metrics",
        "modelled",
        "comparisons",
    }
    assert expected <= set(report)
    assert report["n_seeds"] == 3
    assert report["calibration_dataset"] == "preimplantation/v1"

    # deterministic params -> every seed identical
    per_seed = list(report["per_seed_metrics"].values())
    assert all(row == per_seed[0] for row in per_seed)
    assert per_seed[0]["time_to_2_cell"] == 5.0
    assert per_seed[0]["time_to_4_cell"] == 10.0
    assert per_seed[0]["time_to_8_cell"] == 15.0
    assert per_seed[0]["cell_count_at_20h"] == 16.0

    assert report["modelled"]["time_to_2_cell"]["mean"] == 5.0
    # no reference target exists for cell_count_at_20h -> excluded from comparisons
    assert [c["key"] for c in report["comparisons"]] == ["time_to_2_cell", "time_to_4_cell", "time_to_8_cell"]
    assert all(c["within_observed"] is False for c in report["comparisons"])