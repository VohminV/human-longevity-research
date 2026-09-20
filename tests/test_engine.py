from typing import Any

from longevity.sim.engine import PopulationEngine
from longevity.sim.rng import Rng

FAST = {"doubling_time_mean": 1.0, "doubling_time_sd": 0.0}


def _state(engine: PopulationEngine) -> tuple:
    cells = tuple(
        sorted(
            (c.id, (c.generation, c.status.value, c.parent_id, c.division_time, c.lineage))
            for c in engine.population.values()
        )
    )
    return (engine.sim_time, engine.next_id, cells, tuple(sorted(engine.counters.items())))


def _run(seed: int, duration: float, parameters: dict[str, Any] | None = None, population: int = 1) -> tuple:
    engine = PopulationEngine(Rng(seed), parameters or {}, population=population)
    engine.run_until(duration)
    engine.assert_invariants()
    return _state(engine)


def test_same_seed_is_deterministic():
    assert _run(42, 30.0) == _run(42, 30.0)
    assert _run(7, 30.0) == _run(7, 30.0)


def test_determinism_with_features():
    params = {
        "doubling_time_mean": 2.0,
        "doubling_time_sd": 0.4,
        "telomere": {"length_start": 8.0, "loss_per_division": 1.0},
        "dna_damage": {"accrual_per_division": 0.8, "threshold": 3.0, "repair_per_division": 0.1},
    }
    assert _run(11, 40.0, params, population=2) == _run(11, 40.0, params, population=2)


def test_invariants_hold_for_many_seeds():
    for seed in (1, 7, 42, 99):
        engine = PopulationEngine(Rng(seed), FAST, population=3)
        engine.run_until(15.0)
        engine.assert_invariants()
        assert engine.next_id == max(engine.population) + 1


def test_clean_exponential_growth():
    engine = PopulationEngine(Rng(0), FAST, population=1)
    engine.run_until(10.0)
    assert engine.counters["senescent"] == 0
    assert engine.counters["died"] == 0
    assert len(engine.population) == 2**10
    assert engine.counters["divisions"] == 2**10 - 1
    assert engine.counters["born"] == 1 + 2 * (2**10 - 1)
    assert engine.sim_time == 10.0


def test_telomere_senescence_limits_growth():
    params = {"doubling_time_mean": 1.0, "doubling_time_sd": 0.0, "telomere": {"length_start": 3.0, "loss_per_division": 1.0}}
    engine = PopulationEngine(Rng(0), params, population=1)
    engine.run_until(1e3)
    assert engine.counters["senescent"] > 0
    max_depth = max(len(c.lineage) for c in engine.population.values())
    assert max_depth <= 4
    assert len(engine.population) <= 2**3


def test_dna_damage_senescence():
    params = {
        "doubling_time_mean": 1.0,
        "doubling_time_sd": 0.0,
        "dna_damage": {"accrual_per_division": 2.0, "threshold": 5.0},
    }
    engine = PopulationEngine(Rng(0), params, population=1)
    engine.run_until(1e3)
    assert engine.counters["senescent"] > 0


def test_mortality_clears_population():
    params = {"doubling_time_mean": 1.0, "doubling_time_sd": 0.0, "mortality": {"rate": 1.0}}
    engine = PopulationEngine(Rng(0), params, population=1)
    engine.run_until(5.0)
    engine.assert_invariants()
    assert engine.population == {}
    assert engine.counters["died"] == 1
    assert engine.counters["divisions"] == 0


def test_run_until_rejects_backwards_time():
    engine = PopulationEngine(Rng(1), FAST, population=1)
    engine.run_until(5.0)
    try:
        engine.run_until(4.0)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass