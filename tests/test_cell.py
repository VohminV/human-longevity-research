from longevity.biology.cell import (
    CellStatus,
    daughter_cells,
    from_dict,
    invariant_violation,
    root_cell,
    to_dict,
)


def test_root_cell_shape():
    cell = root_cell(7)
    assert cell.id == 7
    assert cell.parent_id is None
    assert cell.generation == 0
    assert cell.lineage == (7,)
    assert cell.born_at == 0.0
    assert cell.is_normal
    assert cell.is_living
    assert invariant_violation(cell) is None


def test_daughter_cells_invariants():
    mother = root_cell(0)
    daughter_a, daughter_b = daughter_cells(mother, 1, 2, 10.0)
    assert daughter_a.generation == 1 == daughter_b.generation
    assert daughter_a.parent_id == mother.id == daughter_b.parent_id
    assert daughter_a.lineage == (0, 1)
    assert daughter_b.lineage == (0, 2)
    assert daughter_a.born_at == daughter_b.born_at == 10.0
    for daughter in (daughter_a, daughter_b):
        assert daughter.is_normal
        assert invariant_violation(daughter) is None


def test_to_from_dict_roundtrip():
    mother = root_cell(5)
    daughter_a, _daughter_b = daughter_cells(mother, 6, 7, 12.5)
    daughter_a.telomere_length = 90.0
    daughter_a.dna_damage = 1.5
    daughter_a.division_time = 25.0
    restored = from_dict(to_dict(daughter_a))
    assert restored == daughter_a
    assert restored.lineage == daughter_a.lineage
    assert restored.telomere_length == 90.0


def test_status_transitions():
    cell = root_cell(0)
    cell.status = CellStatus.SENESCENT
    assert not cell.is_normal
    assert cell.is_living
    cell.status = CellStatus.DEAD
    assert not cell.is_living
    cell.status = CellStatus.APOPTOTIC
    assert not cell.is_living