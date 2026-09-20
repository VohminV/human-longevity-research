from __future__ import annotations

from typing import Any

from longevity.biology.cell import CellStatus
from longevity.sim.engine import PopulationEngine


def population_metrics(engine: PopulationEngine) -> dict[str, Any]:
    """Point-in-time metrics of the engine population. Deterministic for a
    given engine state; safe to record at any time boundary."""
    population = engine.population
    total = len(population)
    normal = sum(1 for c in population.values() if c.status is CellStatus.NORMAL)
    senescent = sum(1 for c in population.values() if c.status is CellStatus.SENESCENT)
    depth = max((len(c.lineage) for c in population.values()), default=0)

    telomeres = [c.telomere_length for c in population.values() if c.telomere_length is not None]
    damages = [c.dna_damage for c in population.values() if c.dna_damage is not None]

    return {
        "sim_time": engine.sim_time,
        "cells_total": total,
        "cells_normal": normal,
        "cells_senescent": senescent,
        "cells_dead_cumulative": engine.counters["died"],
        "max_lineage_depth": depth,
        "total_divisions": engine.counters["divisions"],
        "total_born": engine.counters["born"],
        "telomere_mean": round(sum(telomeres) / len(telomeres), 4) if telomeres else None,
        "dna_damage_mean": round(sum(damages) / len(damages), 4) if damages else None,
    }


def experiment_summary(metrics: dict[str, Any]) -> dict[str, Any]:
    """Compact, comparable summary of a run's terminal metrics."""
    return {
        "final_population": metrics["cells_total"],
        "final_normal": metrics["cells_normal"],
        "final_senescent": metrics["cells_senescent"],
        "total_deaths": metrics["cells_dead_cumulative"],
        "total_divisions": metrics["total_divisions"],
        "max_lineage_depth": metrics["max_lineage_depth"],
        "population_senescent_fraction": (
            round(metrics["cells_senescent"] / metrics["cells_total"], 4) if metrics["cells_total"] else 1.0
        ),
    }