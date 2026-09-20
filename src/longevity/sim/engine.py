from __future__ import annotations

import heapq

from typing import Any

from longevity.biology.cell import Cell, CellStatus, daughter_cells, from_dict, invariant_violation, root_cell, to_dict
from longevity.biology.params import apply_interventions
from longevity.sim.rng import Rng, state_from_json, state_to_json


class PopulationEngine:
    """Discrete-event engine over a population of Cells.

    State owned here: `sim_time`, `next_id` (id allocator), `population`
    (id -> Cell for living cells), `counters`, and a min-heap of division
    events ordered by (time, cell_id, seq) so tie-broken processing is fully
    deterministic for a given RNG path.
    """

    def __init__(
        self,
        rng: Rng,
        parameters: dict[str, Any],
        population: int = 1,
        interventions: list[dict[str, Any]] | None = None,
        model_version: str = "",
        experiment_id: str = "",
    ):
        self.experiment_id = experiment_id
        self.model_version = model_version
        self.parameters = apply_interventions(parameters, interventions or [])
        self.rng = rng
        self.sim_time = 0.0
        self.next_id = 0
        self.population: dict[int, Cell] = {}
        self.counters = {
            "born": 0,
            "died": 0,
            "divisions": 0,
            "senescent": 0,
        }
        self.events: list[tuple[float, int, int]] = []
        self._event_seq = 0
        self._seed_population(population)

    @property
    def feature_telomere_enabled(self) -> bool:
        return self.parameters.get("telomere") is not None

    @property
    def feature_dna_damage_enabled(self) -> bool:
        return self.parameters.get("dna_damage") is not None

    @property
    def feature_mortality_enabled(self) -> bool:
        return self.parameters.get("mortality") is not None

    def _allocate_id(self) -> int:
        cell_id = self.next_id
        self.next_id += 1
        return cell_id

    def _draw_doubling_time(self) -> float:
        mean = self.parameters["doubling_time_mean"]
        sd = self.parameters["doubling_time_sd"]
        return max(0.0, self.rng.gauss(mean, sd))

    def _schedule(self, cell: Cell) -> None:
        if cell.is_normal and cell.division_time is not None:
            heapq.heappush(self.events, (cell.division_time, cell.id, self._event_seq))
            self._event_seq += 1

    def _seed_population(self, population: int) -> None:
        telomere_start = None
        if self.feature_telomere_enabled:
            telomere_start = float(self.parameters["telomere"].get("length_start", 100.0))
        for _ in range(population):
            cell = root_cell(self._allocate_id())
            if telomere_start is not None:
                cell.telomere_length = telomere_start
            if self.feature_dna_damage_enabled:
                cell.dna_damage = 0.0
            cell.division_time = self._draw_doubling_time()
            self.population[cell.id] = cell
            self._schedule(cell)
        self.counters["born"] += population

    def _next_telomere(self, cell: Cell, loss: float) -> float:
        base = cell.telomere_length if cell.telomere_length is not None else 0.0
        return base - loss

    def _next_damage(self, cell: Cell, accrual: float, repair: float) -> float:
        base = cell.dna_damage if cell.dna_damage is not None else 0.0
        return max(0.0, base + accrual - repair)

    def _handle_division(self, cell: Cell, time: float) -> None:
        self.sim_time = time
        mortality = self.parameters.get("mortality")
        if mortality is not None:
            rate = float(mortality.get("rate", 0.0))
            if rate > 0.0 and self.rng.random() < rate:
                del self.population[cell.id]
                self.counters["died"] += 1
                return

        id_a = self._allocate_id()
        id_b = self._allocate_id()
        daughter_a, daughter_b = daughter_cells(cell, id_a, id_b, time)

        if self.feature_telomere_enabled:
            loss = float(self.parameters["telomere"].get("loss_per_division", 5.0))
            daughter_a.telomere_length = self._next_telomere(cell, loss)
            daughter_b.telomere_length = self._next_telomere(cell, loss)

        damage_config = self.parameters.get("dna_damage")
        if damage_config is not None:
            accrual = float(damage_config.get("accrual_per_division", 0.2))
            repair = float(damage_config.get("repair_per_division", 0.0))
            daughter_a.dna_damage = self._next_damage(cell, accrual, repair)
            daughter_b.dna_damage = self._next_damage(cell, accrual, repair)

        del self.population[cell.id]
        self.population[id_a] = daughter_a
        self.population[id_b] = daughter_b
        self.counters["divisions"] += 1
        self.counters["born"] += 2

        for daughter in (daughter_a, daughter_b):
            if self._born_senescent(daughter):
                daughter.status = CellStatus.SENESCENT
                self.counters["senescent"] += 1
                continue
            daughter.division_time = time + self._draw_doubling_time()
            self._schedule(daughter)

    def _born_senescent(self, cell: Cell) -> bool:
        if self.feature_telomere_enabled and cell.telomere_length <= 0.0:
            return True
        if self.feature_dna_damage_enabled:
            threshold = float(self.parameters["dna_damage"].get("threshold", 5.0))
            if cell.dna_damage >= threshold:
                return True
        return False

    def step(self) -> bool:
        """Process the single next division event. Returns False when empty."""
        event = self._peek_ready()
        if event is None:
            return False
        time, cell_id, _seq = event
        heapq.heappop(self.events)
        cell = self.population[cell_id]
        self._handle_division(cell, time)
        return True

    def run_until(self, end_time: float) -> None:
        """Process all division events with time <= end_time, in event order."""
        if end_time < self.sim_time:
            raise ValueError(f"end_time {end_time} < current sim_time {self.sim_time}")
        while self.events:
            time, cell_id, seq = self.events[0]
            if time > end_time:
                break
            heapq.heappop(self.events)
            cell = self.population.get(cell_id)
            if cell is None or not cell.is_normal or cell.division_time != time:
                continue
            self._handle_division(cell, time)

    def _peek_ready(self) -> tuple[float, int, int] | None:
        while self.events:
            time, cell_id, seq = self.events[0]
            cell = self.population.get(cell_id)
            if cell is None or not cell.is_normal or cell.division_time != time:
                heapq.heappop(self.events)
                continue
            return (time, cell_id, seq)
        return None

    def assert_invariants(self) -> None:
        """Raise AssertionError when a run-level invariant is violated."""
        seen: set[int] = set()
        for cell in self.population.values():
            if cell.id in seen:
                raise AssertionError(f"duplicate cell id {cell.id}")
            seen.add(cell.id)
            violation = invariant_violation(cell)
            if violation is not None:
                raise AssertionError(violation)

    def to_checkpoint_dict(self) -> dict[str, Any]:
        _, generator_state = self.rng.getstate()
        return {
            "model_version": self.model_version,
            "experiment_id": self.experiment_id,
            "seed": self.rng.seed,
            "sim_time": self.sim_time,
            "next_id": self.next_id,
            "rng": {"seed": self.rng.seed, "generator_state": state_to_json(generator_state)},
            "parameters": self.parameters,
            "counters": dict(self.counters),
            "population": [to_dict(c) for c in self.population.values()],
        }

    @classmethod
    def from_checkpoint(cls, data: dict[str, Any], rng: Rng | None = None) -> "PopulationEngine":
        engine = cls.__new__(cls)
        engine.experiment_id = data["experiment_id"]
        engine.model_version = data["model_version"]
        engine.parameters = data["parameters"]
        engine.rng = rng or Rng(data["rng"]["seed"])
        engine.rng.setstate((data["rng"]["seed"], state_from_json(data["rng"]["generator_state"])))
        engine.sim_time = data["sim_time"]
        engine.next_id = data["next_id"]
        engine.population = {c.id: c for c in (from_dict(d) for d in data["population"])}
        engine.counters = dict(data["counters"])
        engine.events = []
        engine._event_seq = 0
        for cell in sorted(engine.population.values(), key=lambda c: c.id):
            engine._schedule(cell)
        return engine