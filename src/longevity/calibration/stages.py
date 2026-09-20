"""Developmental stage inference (analysis-level, NOT part of the engine).

The engine itself has no notion of embryo stages: it only divides, senesces or
kills cells. This module derives a coarse stage label from the observable
state (time, cell count, compaction flag) so calibration runs can be compared
to the reference time landmarks.

Honesty notes:
- Cleavage stages (2/4/8-cell) are defined by BANDED cell counts, not exact
  ones: asynchronous cleavage means a 5-cell embryo is mid-transition and
  stays "4-cell" until 8 cells actually exist.
- Morula and blastocyst require compaction / cavitation, which this model does
  NOT simulate. `compacted` is accepted but defaults to False; when False the
  morula/blastocyst labels are a count+time heuristic only, and that is stated
  in the rationale returned with every call.
- A small count at a late time is NEVER promoted to a later stage: stage
  inference must not mask a missing biological process.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from longevity.calibration.reference import MORULA_CELL_COUNT_APPROX


class DevelopmentalStage(str, Enum):
    ZYGOTE = "zygote"
    TWO_CELL = "two_cell"
    FOUR_CELL = "four_cell"
    EIGHT_CELL = "eight_cell"
    MORULA = "morula"
    BLASTOCYST = "blastocyst"


@dataclass(frozen=True)
class StageInference:
    stage: DevelopmentalStage
    rationale: str
    compacted_assumed: bool


# Time guards (hours): compaction ~day3-4, cavitation ~day4-5 (S-7).
_MORULA_EARLIEST_H = 72.0
_BLASTOCYST_EARLIEST_H = 100.0

_MORULA_COUNT_LO, _MORULA_COUNT_HI = MORULA_CELL_COUNT_APPROX  # 16..32


def infer_stage(time_h: float, cell_count: int, compacted: bool = False) -> StageInference:
    """Infer a coarse developmental stage from (time, cell count, compaction).

    The returned :class:`StageInference` always carries a human-readable
    rationale so a staged result can never be mistaken for a biological fact.

    Precedence: blastocyst -> morula -> 8-cell -> 4-cell -> 2-cell -> zygote.
    A count outside a stage's time band falls back to the count-based cleavage
    label rather than being promoted.
    """
    if cell_count < 0:
        raise ValueError(f"cell_count must be >= 0, got {cell_count}")
    if time_h < 0.0:
        raise ValueError(f"time_h must be >= 0, got {time_h}")

    if cell_count == 0:
        return StageInference(DevelopmentalStage.ZYGOTE, "population empty; no stage yet", compacted)
    if cell_count == 1:
        return StageInference(DevelopmentalStage.ZYGOTE, "single cell before first cleavage", compacted)

    if cell_count >= 32 and time_h >= _BLASTOCYST_EARLIEST_H:
        return StageInference(
            DevelopmentalStage.BLASTOCYST,
            "cavitation assumed; blastocyst size reached (count+time heuristic, TE/ICM not modeled)",
            compacted,
        )
    if compacted and cell_count >= _MORULA_COUNT_LO and time_h >= _BLASTOCYST_EARLIEST_H:
        return StageInference(
            DevelopmentalStage.BLASTOCYST,
            "cavitation reported after compaction; blastocyst",
            compacted,
        )
    if _MORULA_COUNT_LO <= cell_count <= _MORULA_COUNT_HI and time_h >= _MORULA_EARLIEST_H:
        return StageInference(
            DevelopmentalStage.MORULA,
            "morula inferred from count band + time (compaction not modeled)",
            compacted,
        )
    if compacted and cell_count >= _MORULA_COUNT_LO:
        return StageInference(
            DevelopmentalStage.MORULA,
            "compaction reported; morula",
            compacted,
        )

    if cell_count >= 8:
        return StageInference(
            DevelopmentalStage.EIGHT_CELL,
            "8 cells or more; beyond band but not yet morula/blastocyst",
            compacted,
        )
    if cell_count >= 4:
        return StageInference(
            DevelopmentalStage.FOUR_CELL,
            "4-7 cells, asynchronous cleavage transition to 8-cell",
            compacted,
        )
    if cell_count >= 2:
        return StageInference(
            DevelopmentalStage.TWO_CELL,
            "2-3 cells, asynchronous cleavage transition to 4-cell",
            compacted,
        )
    return StageInference(DevelopmentalStage.ZYGOTE, "unexpected count; treated as zygote", compacted)