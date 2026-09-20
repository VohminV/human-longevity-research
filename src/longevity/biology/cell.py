from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Optional


class CellStatus(enum.Enum):
    """Life status of a cell. Transitions are enforced by the engine.

    A cell that leaves NORMAL stops dividing. SENESCENT cells remain
    registered in the population but never divide again.
    """

    NORMAL = "normal"
    SENESCENT = "senescent"
    APOPTOTIC = "apoptotic"
    DEAD = "dead"


class CellCycleState(enum.Enum):
    G0 = "G0"
    G1 = "G1"
    S = "S"
    G2 = "G2"
    M = "M"


@dataclass
class Cell:
    """A node in the lineage tree.

    Invariants enforced by code/constructors and asserted by tests:
      - `id` is globally unique within a run;
      - `generation == len(lineage) - 1`;
      - `lineage[-1] == id`;
      - for `generation > 0`: `parent_id == lineage[-2]`.
    """

    id: int
    parent_id: Optional[int]
    generation: int
    lineage: tuple[int, ...]
    born_at: float
    status: CellStatus = CellStatus.NORMAL
    cell_cycle_state: CellCycleState = CellCycleState.G1
    telomere_length: Optional[float] = None
    dna_damage: Optional[float] = None
    division_time: Optional[float] = None

    @property
    def is_living(self) -> bool:
        return self.status in (CellStatus.NORMAL, CellStatus.SENESCENT)

    @property
    def is_normal(self) -> bool:
        return self.status is CellStatus.NORMAL

    @property
    def lineage_depth(self) -> int:
        return len(self.lineage)


def root_cell(cell_id: int) -> Cell:
    """A founding cell with empty ancestry: generation 0 lineage (id,)."""
    return Cell(
        id=cell_id,
        parent_id=None,
        generation=0,
        lineage=(cell_id,),
        born_at=0.0,
    )


def daughter_cells(mother: Cell, id_a: int, id_b: int, time: float) -> tuple[Cell, Cell]:
    """Two daughters of `mother`, born at `time`; parent-child and lineage set."""
    generation = mother.generation + 1
    a = Cell(
        id=id_a,
        parent_id=mother.id,
        generation=generation,
        lineage=mother.lineage + (id_a,),
        born_at=time,
    )
    b = Cell(
        id=id_b,
        parent_id=mother.id,
        generation=generation,
        lineage=mother.lineage + (id_b,),
        born_at=time,
    )
    return a, b


def to_dict(cell: Cell) -> dict[str, Any]:
    return {
        "id": cell.id,
        "parent_id": cell.parent_id,
        "generation": cell.generation,
        "lineage": list(cell.lineage),
        "born_at": cell.born_at,
        "status": cell.status.value,
        "cell_cycle_state": cell.cell_cycle_state.value,
        "telomere_length": cell.telomere_length,
        "dna_damage": cell.dna_damage,
        "division_time": cell.division_time,
    }


def from_dict(data: dict[str, Any]) -> Cell:
    return Cell(
        id=data["id"],
        parent_id=data.get("parent_id"),
        generation=data["generation"],
        lineage=tuple(data["lineage"]),
        born_at=data["born_at"],
        status=CellStatus(data.get("status", CellStatus.NORMAL.value)),
        cell_cycle_state=CellCycleState(data.get("cell_cycle_state", CellCycleState.G1.value)),
        telomere_length=data.get("telomere_length"),
        dna_damage=data.get("dna_damage"),
        division_time=data.get("division_time"),
    )


def invariant_violation(cell: Cell) -> Optional[str]:
    """First violated cell invariant, or None when the cell is consistent."""
    if cell.generation != len(cell.lineage) - 1:
        return f"cell {cell.id}: generation {cell.generation} != len(lineage)-1"
    if cell.lineage[-1] != cell.id:
        return f"cell {cell.id}: lineage tail {cell.lineage[-1]} != id"
    if cell.generation > 0 and cell.parent_id != cell.lineage[-2]:
        return f"cell {cell.id}: parent_id {cell.parent_id} != lineage[-2]"
    if cell.generation == 0 and cell.parent_id is not None:
        return f"cell {cell.id}: root has parent_id {cell.parent_id}"
    return None