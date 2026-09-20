"""Tests for Stage 4: developmental (count-based) cell-cycle dynamics.

Covers the `cell_cycle` parameter group end to end -- validation, the
phase-aware doubling-time draw, per-phase death, the population=1 guard for a
single-embryo model, backward compatibility with the constant-cycle baseline,
and checkpoint/restore of phase-carrying engines.
"""

import pytest

from longevity.biology.params import apply_interventions
from longevity.experiment.config import ExperimentConfig
from longevity.sim.engine import PopulationEngine
from longevity.sim.rng import Rng

DETERMINISTIC_PHASES = {
    "phases": [
        {"threshold": 0, "mean": 26.0, "sd": 0.0},
        {"threshold": 2, "mean": 17.0, "sd": 0.0},
        {"threshold": 8, "mean": 24.0, "sd": 0.0},
    ]
}

STOCHASTIC_PHASES = {
    "phases": [
        {"threshold": 0, "mean": 26.0, "sd": 3.0},
        {"threshold": 2, "mean": 17.0, "sd": 2.0},
        {"threshold": 8, "mean": 24.0, "sd": 4.0},
    ]
}


def _milestone_reach(engine: PopulationEngine, target: int) -> float:
    return next(m["sim_time"] for m in engine.milestones if m["live_count"] >= target)


def _engine(parameters, seed=1, population=1, record_milestones=True):
    return PopulationEngine(
        rng=Rng(seed),
        parameters=parameters,
        population=population,
        model_version="test",
        experiment_id="test",
        record_milestones=record_milestones,
    )


# ---------------------------------------------------------------------------
# Phase-aware doubling time
# ---------------------------------------------------------------------------


def test_deterministic_phase_schedule():
    engine = _engine({"doubling_time_sd": 0.0, "cell_cycle": DETERMINISTIC_PHASES})
    engine.run_until(100.0)
    # root draws phase 0 (26h): 2-cell at 26; the 2-cell daughters draw phase 1
    # (17h) at count 2: 4-cell at 43; the 4-cell daughters draw phase 1 at
    # count 4: 8-cell at 60. Phase 2 only governs daughters born at count >= 8.
    assert _milestone_reach(engine, 2) == 26.0
    assert _milestone_reach(engine, 4) == 43.0
    assert _milestone_reach(engine, 8) == 60.0
    engine.assert_invariants()


def test_same_seed_is_deterministic_with_cell_cycle():
    params = {"doubling_time_sd": 0.0, "cell_cycle": STOCHASTIC_PHASES}
    engine_a = _engine(params, seed=7)
    engine_b = _engine(params, seed=7)
    engine_a.run_until(120.0)
    engine_b.run_until(120.0)
    a_series = "|".join(f"{m['sim_time']}:{m['live_count']}" for m in engine_a.milestones)
    b_series = "|".join(f"{m['sim_time']}:{m['live_count']}" for m in engine_b.milestones)
    assert a_series == b_series

    engine_c = _engine(params, seed=8)
    engine_c.run_until(120.0)
    c_series = "|".join(f"{m['sim_time']}:{m['live_count']}" for m in engine_c.milestones)
    assert c_series != a_series


def test_cell_cycle_feature_is_opt_in():
    assert not _engine({"doubling_time_mean": 10.8}).feature_cell_cycle_enabled
    assert _engine({"doubling_time_sd": 0.0, "cell_cycle": DETERMINISTIC_PHASES}).feature_cell_cycle_enabled


def test_single_phase_equals_baseline():
    """One phase spanning every count with the baseline mean/sd must reproduce
    the constant-cycle model exactly (backward-compatibility equivalence)."""
    base_params = {"doubling_time_mean": 10.8, "doubling_time_sd": 1.2}
    phase_params = {
        "doubling_time_mean": 10.8,
        "doubling_time_sd": 1.2,
        "cell_cycle": {"phases": [{"threshold": 0, "mean": 10.8, "sd": 1.2}]},
    }
    for seed in (1, 2, 3):
        base = _engine(base_params, seed=seed)
        phased = _engine(phase_params, seed=seed)
        base.run_until(168.0)
        phased.run_until(168.0)
        a = [(m["sim_time"], m["live_count"]) for m in base.milestones]
        b = [(m["sim_time"], m["live_count"]) for m in phased.milestones]
        assert a == b
        assert base.counters == phased.counters


# ---------------------------------------------------------------------------
# Per-phase death
# ---------------------------------------------------------------------------


def test_phase_death_bounds_count():
    """With phase 2 (count >= 8) set to certain death per division, the
    population can never exceed 8: each attempt at count 8 kills the divider,
    dropping the count before the next division attempt occurs."""
    params = {
        "doubling_time_sd": 0.0,
        "cell_cycle": {
            "phases": [
                {"threshold": 0, "mean": 17.0, "sd": 0.0},
                {"threshold": 2, "mean": 17.0, "sd": 0.0},
                {"threshold": 8, "mean": 17.0, "sd": 0.0, "death_per_division": 1.0},
            ]
        },
    }
    engine = _engine(params, seed=5)
    engine.run_until(400.0)
    assert all(m["live_count"] <= 8 for m in engine.milestones)
    assert engine.living_count() <= 8
    assert engine.counters["died"] > 0
    engine.assert_invariants()


def test_death_combines_with_global_mortality():
    """Phase death and global mortality.rate combine as independent risks."""
    params = {
        "doubling_time_sd": 0.0,
        "mortality": {"rate": 0.5},
        "cell_cycle": {
            "phases": [
                {"threshold": 0, "mean": 17.0, "sd": 0.0},
                {"threshold": 2, "mean": 17.0, "sd": 0.0},
                {"threshold": 8, "mean": 17.0, "sd": 0.0, "death_per_division": 0.5},
            ]
        },
    }
    engine = _engine(params, seed=5)
    engine.run_until(50.0)
    engine.assert_invariants()


# ---------------------------------------------------------------------------
# population=1 guard
# ---------------------------------------------------------------------------


def test_cell_cycle_requires_population_one():
    with pytest.raises(ValueError, match="population must be 1"):
        PopulationEngine(
            rng=Rng(1),
            parameters={"doubling_time_sd": 0.0, "cell_cycle": DETERMINISTIC_PHASES},
            population=2,
        )


def test_config_guard_rejects_population_two_with_cell_cycle():
    with pytest.raises(ValueError, match="population must be 1"):
        ExperimentConfig(
            experiment_id="guard-test",
            seed=1,
            population=2,
            duration=168.0,
            model_version="0.2.0",
            data_version="0.1.0",
            parameters={"doubling_time_sd": 0.0, "cell_cycle": DETERMINISTIC_PHASES},
        )


# ---------------------------------------------------------------------------
# Checkpoint / restore
# ---------------------------------------------------------------------------


def test_checkpoint_restore_preserves_cell_cycle():
    params = {"doubling_time_sd": 0.0, "cell_cycle": STOCHASTIC_PHASES}
    engine = _engine(params, seed=3)
    engine.run_until(50.0)
    snapshot = engine.to_checkpoint_dict()
    restored = PopulationEngine.from_checkpoint(snapshot)
    assert restored.feature_cell_cycle_enabled
    engine.run_until(100.0)
    restored.run_until(100.0)
    a = [(m["sim_time"], m["live_count"]) for m in engine.milestones]
    b = [(m["sim_time"], m["live_count"]) for m in restored.milestones]
    assert a == b
    assert engine.counters == restored.counters


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_phases",
    [
        [],
        "not-a-list",
        [{"mean": 20.0}],  # threshold missing
        [{"threshold": 1, "mean": 20.0}],  # phase 0 threshold must be 0
        [
            {"threshold": 0, "mean": 26.0},
            {"threshold": 0, "mean": 17.0},  # not strictly increasing
        ],
        [{"threshold": True, "mean": 20.0}],  # bool is not a number
        [{"threshold": 0}],  # mean missing
        [{"threshold": 0, "mean": True}],  # bool mean
        [{"threshold": 0, "mean": 26.0, "sd": -1.0}],
        [{"threshold": 0, "mean": 26.0, "death_per_division": 1.5}],
        [{"threshold": 0, "mean": 26.0, "death_per_division": -0.1}],
        [{"threshold": 0, "mean": 26.0, "unknown_key": 1}],
    ],
)
def test_cell_cycle_validation_rejects_bad_phases(bad_phases):
    with pytest.raises(ValueError):
        _engine({"doubling_time_sd": 0.0, "cell_cycle": {"phases": bad_phases}})


def test_cell_cycle_validation_rejects_bad_top_level():
    with pytest.raises(ValueError, match="non-empty list"):
        _engine({"doubling_time_sd": 0.0, "cell_cycle": {}})
    with pytest.raises(ValueError, match="unknown cell_cycle"):
        _engine({"doubling_time_sd": 0.0, "cell_cycle": {"phases": DETERMINISTIC_PHASES["phases"], "bogus": 1}})


def test_phase_sd_defaults_to_doubling_time_sd():
    engine = _engine({"doubling_time_sd": 2.5, "cell_cycle": {"phases": [{"threshold": 0, "mean": 20.0}]}})
    assert engine.parameters["cell_cycle"]["phases"][0]["sd"] == 2.5
    assert engine.parameters["cell_cycle"]["phases"][0]["death_per_division"] == 0.0


# ---------------------------------------------------------------------------
# apply_interventions over list-indexed phase paths
# ---------------------------------------------------------------------------


def test_apply_interventions_indexes_into_phases():
    base = {"doubling_time_sd": 0.0, "cell_cycle": DETERMINISTIC_PHASES}
    original = base["cell_cycle"]["phases"][2]["mean"]
    result = apply_interventions(base, [{"parameter": "cell_cycle.phases.2.mean", "value": 30.0}])
    assert result["cell_cycle"]["phases"][2]["mean"] == 30.0
    assert result["cell_cycle"]["phases"][0]["mean"] == 26.0
    assert result["cell_cycle"]["phases"][1]["mean"] == 17.0
    # the input must not be mutated by the deep-copy fix
    assert base["cell_cycle"]["phases"][2]["mean"] == original == 24.0


def test_apply_interventions_death_path():
    result = apply_interventions(
        {"doubling_time_sd": 0.0, "cell_cycle": DETERMINISTIC_PHASES},
        [{"parameter": "cell_cycle.phases.2.death_per_division", "value": 0.05}],
    )
    assert result["cell_cycle"]["phases"][2]["death_per_division"] == 0.05
    assert result["cell_cycle"]["phases"][0]["death_per_division"] == 0.0