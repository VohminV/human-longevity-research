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
        record_milestones: bool = False,
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
        self._record_milestones = record_milestones
        self.milestones: list[dict[str, Any]] = []
        cell_cycle = self.parameters.get("cell_cycle")
        if cell_cycle is not None and population != 1:
            raise ValueError("cell_cycle phases assume a single developing embryo; population must be 1")
        self._living = population
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

    @property
    def feature_cell_cycle_enabled(self) -> bool:
        return self.parameters.get("cell_cycle") is not None

    @property
    def milestones_enabled(self) -> bool:
        """Whether division-event milestones are being recorded.

        Milestones capture the exact sim_time of every handled division with a
        snapshot of the living count, which is what precise `time_to_N_cell`
        calibration metrics are computed from. Off by default so ordinary runs
        and checkpoints are not burdened with an event log.
        """
        return self._record_milestones

    def _allocate_id(self) -> int:
        cell_id = self.next_id
        self.next_id += 1
        return cell_id

    def _phase_for_count(self, count: int) -> dict[str, Any] | None:
        """The cell-cycle phase governing a cell that divides while `count`
        cells are living, or None for the constant-cycle (baseline) model.

        Phases are ordered by strictly increasing `threshold`; the phase whose
        threshold is the largest value <= `count` applies (the first phase,
        threshold 0, always matches). The count is the living population at the
        time the doubling time is drawn -- i.e. a developmental-state proxy
        (a model for the nucleo-cytoplasmic ratio, NOT spatial compaction).
        """
        cell_cycle = self.parameters.get("cell_cycle")
        if cell_cycle is None:
            return None
        phase = cell_cycle["phases"][0]
        for candidate in cell_cycle["phases"]:
            if candidate["threshold"] <= count:
                phase = candidate
            else:
                break
        return phase

    def _draw_doubling_time(self) -> float:
        phase = self._phase_for_count(self.living_count())
        if phase is not None:
            mean = float(phase["mean"])
            sd = float(phase.get("sd", self.parameters["doubling_time_sd"]))
            return max(0.0, self.rng.gauss(mean, sd))
        mean = self.parameters["doubling_time_mean"]
        sd = self.parameters["doubling_time_sd"]
        return max(0.0, self.rng.gauss(mean, sd))

    def _division_death_rate(self) -> float:
        """Per-division death chance for the cell about to divide.

        Combines the global `mortality.rate` with the current phase's
        `death_per_division` as independent risks. With no `cell_cycle` this
        reduces exactly to the baseline global mortality.
        """
        mortality = self.parameters.get("mortality")
        global_rate = float(mortality.get("rate", 0.0)) if mortality is not None else 0.0
        phase = self._phase_for_count(self.living_count())
        if phase is None:
            return global_rate
        phase_rate = float(phase.get("death_per_division", 0.0))
        return 1.0 - (1.0 - global_rate) * (1.0 - phase_rate)

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
        death_rate = self._division_death_rate()
        if death_rate > 0.0 and self.rng.random() < death_rate:
            del self.population[cell.id]
            self.counters["died"] += 1
            self._living -= 1
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
        self._living += 1

        for daughter in (daughter_a, daughter_b):
            if self._born_senescent(daughter):
                daughter.status = CellStatus.SENESCENT
                self.counters["senescent"] += 1
                continue
            daughter.division_time = time + self._draw_doubling_time()
            self._schedule(daughter)

        if self._record_milestones:
            self.milestones.append(
                {
                    "sim_time": time,
                    "live_count": self.living_count(),
                    "born_count": self.counters["born"],
                    "dead_count": self.counters["died"],
                }
            )

    def living_count(self) -> int:
        """Number of living (normal + senescent) cells right now (O(1))."""
        return self._living

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
            "milestones": list(self.milestones),
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
        engine._living = sum(1 for c in engine.population.values() if c.is_living)
        milestones = data.get("milestones", [])
        engine.milestones = [dict(m) for m in milestones]
        engine._record_milestones = bool(milestones)
        engine.events = []
        engine._event_seq = 0
        for cell in sorted(engine.population.values(), key=lambda c: c.id):
            engine._schedule(cell)
        return engine