"""ANALYSIS LAYER: tissue-experiment metrics (Stage 3A).

All metrics derive from a recorded trajectory (list of TissueState dicts,
t0 first) plus run counters. Definitions:

- ``area_under_*_curve``: rectangle-rule integral of the pool over steps
  (``sum(pool) * dt``) -- cumulative burden, not a rate.
- ``rejuvenation_delta``: ``final_functional - initial_functional`` of THIS
  run -- a LOCAL tissue-level proxy. Comparing an intervention against its
  baseline (same seed) is done with :func:`compare_against_baseline`, which
  yields ``functional_gain`` / ``senescent_reduction``. Neither equals
  organism rejuvenation (see docs/TISSUE_MODEL.md, docs/LONGEVITY.md).
"""

from __future__ import annotations

from typing import Any


def _auc(values: list[float], dt: float) -> float:
    return sum(values) * dt


def compute_tissue_summary(
    trajectory: list[dict[str, Any]],
    dt: float,
    replacement_events: int,
    total_replaced_cells: float,
) -> dict[str, Any]:
    """Terminal + cumulative metrics for one tissue run.

    Returns exactly the metric set required by Stage 3A (see
    docs/TISSUE_MODEL.md): final pools, areas under curves, peak cancer risk,
    final niche qualities, local rejuvenation delta, and replacement counters.
    """
    if not trajectory:
        raise ValueError("trajectory must be non-empty")
    initial = trajectory[0]
    final = trajectory[-1]
    senescent = [float(row["senescent_cells"]) for row in trajectory]
    damaged = [float(row["damaged_cells"]) for row in trajectory]
    cancer = [float(row["cancer_risk"]) for row in trajectory]
    return {
        "final_functional_cells": float(final["functional_cells"]),
        "final_senescent_cells": float(final["senescent_cells"]),
        "final_damaged_cells": float(final["damaged_cells"]),
        "final_dead_cells": float(final["dead_cells"]),
        "area_under_senescent_curve": _auc(senescent, dt),
        "area_under_damage_curve": _auc(damaged, dt),
        "max_cancer_risk": max(cancer),
        "final_fibrosis_index": float(final["fibrosis_index"]),
        "final_ecm_quality": float(final["ecm_quality"]),
        "final_vascular_quality": float(final["vascular_quality"]),
        "final_immune_pressure": float(final["immune_pressure"]),
        "rejuvenation_delta": float(final["functional_cells"]) - float(initial["functional_cells"]),
        "replacement_events": int(replacement_events),
        "total_replaced_cells": float(total_replaced_cells),
    }


def compare_against_baseline(
    intervention_summary: dict[str, Any],
    baseline_summary: dict[str, Any],
) -> dict[str, Any]:
    """Baseline-vs-intervention comparison at equal seed (EXPERIMENTS.md §5).

    Positive ``functional_gain`` means the intervention ends with more
    functional cells; positive ``senescent_reduction`` means fewer senescent
    cells. Both are LOCAL tissue deltas, not organism rejuvenation.
    """
    return {
        "functional_gain": (
            float(intervention_summary["final_functional_cells"])
            - float(baseline_summary["final_functional_cells"])
        ),
        "senescent_reduction": (
            float(baseline_summary["final_senescent_cells"])
            - float(intervention_summary["final_senescent_cells"])
        ),
    }
