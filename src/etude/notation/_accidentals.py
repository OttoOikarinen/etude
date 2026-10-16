# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Which accidentals to show, and how to stack them in front of a chord."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..core import KeySignature
from .spec import AccidentalDisplay, Head

GLYPHS = {
    -3: 'accidentalTripleFlat',
    -2: 'accidentalDoubleFlat',
    -1: 'accidentalFlat',
    0: 'accidentalNatural',
    1: 'accidentalSharp',
    2: 'accidentalDoubleSharp',
    3: 'accidentalTripleSharp',
}
"""SMuFL glyph for each alteration."""


class AccidentalMemory:
    """The alterations in force on one staff, following common practice.

    An accidental applies to its own staff position (letter and octave)
    until the next barline; everything else follows the key signature.
    """

    def __init__(self, key: KeySignature | None) -> None:
        self._key = key
        self._bar: dict[int, int] = {}

    def reset(self) -> None:
        """Forget the accidentals of the bar (call at every barline)."""
        self._bar.clear()

    def in_force(self, head: Head) -> int:
        """Alteration a reader assumes for the head's staff position."""
        pitch = head.pitch
        default = self._key.alter_for(pitch.letter) if self._key else 0
        return self._bar.get(pitch.diatonic_index, default)

    def decide(self, heads: Sequence[Head], tied: Sequence[bool] | None = None) -> list[int | None]:
        """Return the alteration to print for each head (``None`` for none).

        ``heads`` sound together (a chord, or all voices at one onset). When
        two of them share a staff position with different alterations, both
        show their accidental. A head that continues a tie (``tied``) shows
        no automatic accidental, even across a barline, and does not change
        the memory: later notes in the new bar repeat the accidental. The
        memory is updated afterwards.
        """
        tied = tied or [False] * len(heads)
        alters_at: dict[int, set[int]] = {}
        for head in heads:
            alters_at.setdefault(head.pitch.diatonic_index, set()).add(head.pitch.alter)
        shown: list[int | None] = []
        for head, continued in zip(heads, tied, strict=True):
            alter = head.pitch.alter
            if continued and head.accidental is AccidentalDisplay.AUTO:
                shown.append(None)
                continue
            match head.accidental:
                case AccidentalDisplay.ALWAYS:
                    show = True
                case AccidentalDisplay.NEVER:
                    show = False
                case AccidentalDisplay.AUTO:
                    clash = len(alters_at[head.pitch.diatonic_index]) > 1
                    show = clash or alter != self.in_force(head)
            shown.append(alter if show else None)
        for head, printed in zip(heads, shown, strict=True):
            if printed is not None:
                self._bar[head.pitch.diatonic_index] = printed
        return shown


@dataclass(frozen=True, slots=True)
class Box:
    """The extent of one accidental glyph: height range and width."""

    top: float
    bottom: float
    width: float


VERTICAL_TOLERANCE = 0.3
"""Accidentals may overlap this much vertically and still share a column
(their cut-outs interlock), so accidentals a sixth apart align."""

HORIZONTAL_GAP = 0.12
"""Space between accidentals placed side by side."""

_EPSILON = 1e-9


def _zigzag(count: int, order: Sequence[int]) -> list[int]:
    """Top, bottom, second from top, second from bottom … (Gould's order)."""
    result: list[int] = []
    low, high = 0, count - 1
    while low <= high:
        result.append(order[low])
        if low != high:
            result.append(order[high])
        low += 1
        high -= 1
    return result


def stack(boxes: Sequence[Box]) -> list[float]:
    """Return the right edge of each accidental, relative to the chord's left edge.

    Accidentals are placed top-down in zig-zag order, each as far right as
    it can go without colliding with one already placed. The result is
    always ``<= 0``; subtract the gap between accidental and notehead.
    """
    order = sorted(range(len(boxes)), key=lambda i: (boxes[i].top, i))
    placed: list[tuple[float, float, int]] = []  # (left, right, index)
    rights = [0.0] * len(boxes)
    for index in _zigzag(len(boxes), order):
        box = boxes[index]
        right = 0.0
        moved = True
        while moved:
            moved = False
            for left_edge, right_edge, other in placed:
                overlap = min(box.bottom, boxes[other].bottom) - max(box.top, boxes[other].top)
                if overlap <= VERTICAL_TOLERANCE:
                    continue
                apart = (
                    right - box.width >= right_edge + HORIZONTAL_GAP - _EPSILON
                    or right + HORIZONTAL_GAP <= left_edge + _EPSILON
                )
                if not apart:
                    right = left_edge - HORIZONTAL_GAP
                    moved = True
        rights[index] = right
        placed.append((right - box.width, right, index))
    return rights
