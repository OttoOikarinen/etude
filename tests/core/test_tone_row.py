# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest
from hypothesis import given
from hypothesis import strategies as st

from etude.core import RowForm, RowLabelling, ToneRow

# Webern, Symphony op. 21 row starts on A; Schoenberg op. 25 starts on E.
SCHOENBERG_OP25 = ToneRow.parse('4 5 7 1 6 3 8 2 11 0 9 10')
rows = st.permutations(list(range(12))).map(lambda pcs: ToneRow(tuple(pcs)))


def test_parse_and_validate() -> None:
    assert ToneRow.parse('0 E 7 8 3 1 2 T 6 5 4 9').pcs == (0, 11, 7, 8, 3, 1, 2, 10, 6, 5, 4, 9)
    assert ToneRow.parse('0E78312T6549') == ToneRow.parse('0,B,7,8,3,1,2,A,6,5,4,9')
    assert str(ToneRow.parse('0E78312T6549')) == '0 E 7 8 3 1 2 T 6 5 4 9'
    with pytest.raises(ValueError, match='exactly once'):
        ToneRow((0, 1, 2))
    with pytest.raises(ValueError, match='exactly once'):
        ToneRow((0,) * 12)
    with pytest.raises(ValueError, match='not a tone row'):
        ToneRow.parse('0 1 x')


def test_fixed_c_labels() -> None:
    row = SCHOENBERG_OP25
    assert row.p(4) == row.pcs
    assert row.p(0) == (0, 1, 3, 9, 2, 11, 4, 10, 7, 8, 5, 6)
    assert row.i(4) == (4, 3, 1, 7, 2, 5, 0, 6, 9, 8, 11, 10)
    assert row.r(4) == tuple(reversed(row.pcs))
    assert row.r(4)[-1] == 4
    assert row.ri(4) == tuple(reversed(row.i(4)))
    assert row.identify(row.pcs) == [(RowForm.P, 4)]


def test_movable_labels() -> None:
    row = SCHOENBERG_OP25
    movable = RowLabelling.MOVABLE
    assert row.p(0, labelling=movable) == row.pcs
    assert row.p(8, labelling=movable) == row.p(0)
    assert row.i(0, labelling=movable) == row.i(4)
    assert row.r(0, labelling=movable) == row.r(4)
    assert row.ri(0, labelling=movable) == row.ri(4)
    assert row.identify(row.pcs, labelling=movable) == [(RowForm.P, 0)]


def test_matrix() -> None:
    row = ToneRow.parse('0 E 7 8 3 1 2 T 6 5 4 9')
    grid = row.matrix()
    assert grid[0] == row.pcs
    assert tuple(line[0] for line in grid) == row.i(0)
    assert grid[1] == (1, 0, 8, 9, 4, 2, 3, 11, 7, 6, 5, 10)
    assert all(grid[k][k] == 0 for k in range(12))
    left, top = row.matrix_labels()
    assert left[:3] == ('P0', 'P1', 'P5')
    assert top[:3] == ('I0', 'I11', 'I7')
    left, top = SCHOENBERG_OP25.matrix_labels(labelling=RowLabelling.MOVABLE)
    assert left[0] == 'P0'
    assert top[0] == 'I0'


def test_symmetrical_row_has_several_labels() -> None:
    chromatic = ToneRow(tuple(range(12)))
    assert (RowForm.RI, 11) in chromatic.identify(range(12))
    assert (RowForm.P, 0) in chromatic.identify(range(12))


@given(rows)
def test_matrix_rows_and_columns_are_row_forms(row: ToneRow) -> None:
    grid = row.matrix()
    p_forms = {row.p(n) for n in range(12)}
    i_forms = {row.i(n) for n in range(12)}
    assert set(grid) == p_forms
    assert {tuple(line[k] for line in grid) for k in range(12)} == i_forms
    assert {tuple(reversed(line)) for line in grid} == {row.r(n) for n in range(12)}
    columns = {tuple(line[k] for line in reversed(grid)) for k in range(12)}
    assert columns == {row.ri(n) for n in range(12)}


@given(rows, st.integers(0, 11), st.sampled_from(list(RowLabelling)))
def test_forms_are_rows_and_identified(row: ToneRow, index: int, labelling: RowLabelling) -> None:
    for form in RowForm:
        sequence = row.form(form, index, labelling=labelling)
        ToneRow(sequence)
        assert (form, index) in row.identify(sequence, labelling=labelling)
    assert row.ri(index) == tuple(reversed(row.i(index)))
