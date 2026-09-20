import json

from longevity.sim.engine import PopulationEngine
from longevity.sim.rng import Rng

FEATURED = {
    "doubling_time_mean": 2.0,
    "doubling_time_sd": 0.3,
    "telomere": {"length_start": 8.0, "loss_per_division": 1.0},
}


def _state(engine: PopulationEngine) -> tuple:
    cells = tuple(
        sorted(
            (c.id, (c.generation, c.status.value, c.lineage, c.division_time))
            for c in engine.population.values()
        )
    )
    return (engine.sim_time, engine.next_id, cells, tuple(sorted(engine.counters.items())), engine.rng.getstate())


def _restore_roundtrip(snapshot: dict) -> PopulationEngine:
    return PopulationEngine.from_checkpoint(json.loads(json.dumps(snapshot)))


def test_restore_continues_identically():
    original = PopulationEngine(Rng(42), FEATURED, population=2)
    original.run_until(10.0)
    snapshot = original.to_checkpoint_dict()
    original.run_until(25.0)

    restored = PopulationEngine.from_checkpoint(snapshot)
    restored.run_until(25.0)
    assert _state(original) == _state(restored)


def test_restore_after_json_roundtrip():
    original = PopulationEngine(Rng(42), FEATURED, population=2)
    original.run_until(10.0)
    snapshot = original.to_checkpoint_dict()
    original.run_until(25.0)

    restored = _restore_roundtrip(snapshot)
    restored.run_until(25.0)
    assert _state(original) == _state(restored)


def test_restore_midway_then_split():
    base = PopulationEngine(Rng(3), FEATURED, population=1)
    base.run_until(12.0)
    snapshot = base.to_checkpoint_dict()

    branch_a = PopulationEngine.from_checkpoint(snapshot)
    branch_a.run_until(20.0)
    branch_b = PopulationEngine.from_checkpoint(snapshot)
    branch_b.run_until(20.0)
    assert _state(branch_a) == _state(branch_b)


def test_checkpoint_is_json_serializable():
    engine = PopulationEngine(Rng(9), FEATURED, population=3)
    engine.run_until(8.0)
    json.dumps(engine.to_checkpoint_dict())