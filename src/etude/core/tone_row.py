# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Twelve-tone rows.

A row is an ordering of the twelve pitch classes (C = 0). Its 48 forms
are the prime forms P, inversions I, retrogrades R and retrograde
inversions RI, each at twelve transposition levels.

Labelling conventions differ between textbooks:

* :attr:`RowLabelling.FIXED_C` (the default) is the *integer* convention
  of Straus, *Introduction to Post-Tonal Theory*: the index is a pitch
  class. ``P<n>`` and ``I<n>`` begin on pitch class ``n``; ``R<n>`` is
  the retrograde of ``P<n>`` (so it *ends* on ``n``) and ``RI<n>`` the
  retrograde of ``I<n>``.
* :attr:`RowLabelling.MOVABLE` names the row as given ``P0`` whatever its
  first pitch class, and counts indices in semitones from there, as in
  the traditional twelve-tone matrix. ``P<n>`` begins ``n`` semitones
  above the row's first note; ``I<n>`` is the inversion beginning there;
  ``R<n>`` and ``RI<n>`` are again the retrogrades of ``P<n>`` and ``I<n>``.

The :meth:`ToneRow.matrix` has the row as given in its top row and its
inversion down the left column: rows read left to right are P forms (R
forms right to left) and columns read top to bottom are I forms (RI
bottom to top).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

_DIGITS = '0123456789TE'


class RowForm(Enum):
    P = 'P'
    I = 'I'  # noqa: E741 - the standard name of the form
    R = 'R'
    RI = 'RI'


class RowLabelling(Enum):
    FIXED_C = 'fixed-c'
    MOVABLE = 'movable'


@dataclass(frozen=True, slots=True)
class ToneRow:
    """A twelve-tone row: ``ToneRow((0, 11, 7, 8, 3, 1, 2, 10, 6, 5, 4, 9))``."""

    pcs: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.pcs) != 12 or sorted(self.pcs) != list(range(12)):
            raise ValueError(f'a tone row uses each pitch class 0–11 exactly once: {self.pcs}')

    @classmethod
    def parse(cls, text: str) -> ToneRow:
        """Parse ``'0 E 7 8 3 1 2 T 6 5 4 9'`` or ``'0,11,7,…'`` (T/A = 10, E/B = 11)."""
        tokens = text.replace(',', ' ').split()
        if len(tokens) == 1:
            tokens = list(tokens[0])
        aliases = {'T': 10, 'A': 10, 'E': 11, 'B': 11}
        try:
            pcs = tuple(aliases.get(t.upper()) or int(t) for t in tokens)
        except ValueError:
            raise ValueError(f'not a tone row: {text!r}') from None
        return cls(pcs)

    def _p0(self, labelling: RowLabelling) -> int:
        """Transposition of the row as given, in the labelling's terms."""
        return self.pcs[0] if labelling is RowLabelling.FIXED_C else 0

    def form(
        self, form: RowForm, index: int, *, labelling: RowLabelling = RowLabelling.FIXED_C
    ) -> tuple[int, ...]:
        """One of the 48 row forms, e.g. ``form(RowForm.RI, 3)``."""
        first = self.pcs[0]
        start = (index if labelling is RowLabelling.FIXED_C else first + index) % 12
        if form in (RowForm.P, RowForm.R):
            row = tuple((pc - first + start) % 12 for pc in self.pcs)
        else:
            row = tuple((first - pc + start) % 12 for pc in self.pcs)
        return row if form in (RowForm.P, RowForm.I) else tuple(reversed(row))

    def p(self, index: int, *, labelling: RowLabelling = RowLabelling.FIXED_C) -> tuple[int, ...]:
        return self.form(RowForm.P, index, labelling=labelling)

    def i(self, index: int, *, labelling: RowLabelling = RowLabelling.FIXED_C) -> tuple[int, ...]:
        return self.form(RowForm.I, index, labelling=labelling)

    def r(self, index: int, *, labelling: RowLabelling = RowLabelling.FIXED_C) -> tuple[int, ...]:
        return self.form(RowForm.R, index, labelling=labelling)

    def ri(self, index: int, *, labelling: RowLabelling = RowLabelling.FIXED_C) -> tuple[int, ...]:
        return self.form(RowForm.RI, index, labelling=labelling)

    def identify(
        self, pcs: Sequence[int], *, labelling: RowLabelling = RowLabelling.FIXED_C
    ) -> list[tuple[RowForm, int]]:
        """Every (form, index) label of a sequence; more than one for symmetrical rows."""
        wanted = tuple(pc % 12 for pc in pcs)
        return [
            (form, index)
            for form in RowForm
            for index in range(12)
            if self.form(form, index, labelling=labelling) == wanted
        ]

    def matrix(self) -> tuple[tuple[int, ...], ...]:
        """The 12×12 matrix: row ``k`` is the P form starting on the ``k``-th note of I."""
        inversion = self.form(RowForm.I, self.pcs[0])
        return tuple(self.form(RowForm.P, start) for start in inversion)

    def matrix_labels(
        self, *, labelling: RowLabelling = RowLabelling.FIXED_C
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Labels of the matrix rows (``P…``, left side) and columns (``I…``, top)."""
        offset = 0 if labelling is RowLabelling.FIXED_C else self.pcs[0]
        grid = self.matrix()
        rows = tuple(f'P{(line[0] - offset) % 12}' for line in grid)
        columns = tuple(f'I{(pc - offset) % 12}' for pc in grid[0])
        return rows, columns

    def __str__(self) -> str:
        return ' '.join(_DIGITS[pc] for pc in self.pcs)
