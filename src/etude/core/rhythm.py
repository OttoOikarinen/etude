# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Durations and meters.

Lengths are exact :class:`fractions.Fraction` values measured in whole
notes, so a dotted quarter is ``3/8`` and an eighth-note triplet is
``1/12``. Use :attr:`Duration.quarter_length` when talking to the audio
layer, which counts beats in quarter notes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

_METER_RE = re.compile(r'^(\d+)/(\d+)$')


class NoteValue(Enum):
    """Undotted note value; the value is the length in whole notes."""

    BREVE = Fraction(2)
    WHOLE = Fraction(1)
    HALF = Fraction(1, 2)
    QUARTER = Fraction(1, 4)
    EIGHTH = Fraction(1, 8)
    SIXTEENTH = Fraction(1, 16)
    THIRTY_SECOND = Fraction(1, 32)
    SIXTY_FOURTH = Fraction(1, 64)


@dataclass(frozen=True, slots=True)
class Tuplet:
    """``actual`` notes in the time of ``normal``: a triplet is ``Tuplet(3, 2)``."""

    actual: int
    normal: int

    def __post_init__(self) -> None:
        if self.actual < 1 or self.normal < 1:
            raise ValueError('tuplet ratio must be positive')

    @property
    def ratio(self) -> Fraction:
        return Fraction(self.normal, self.actual)


@dataclass(frozen=True, slots=True)
class Duration:
    value: NoteValue
    dots: int = 0
    tuplet: Tuplet | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.dots <= 3:
            raise ValueError(f'unsupported number of dots: {self.dots}')

    @property
    def length(self) -> Fraction:
        """Length in whole notes."""
        base = self.value.value * (2 - Fraction(1, 2**self.dots))
        return base * self.tuplet.ratio if self.tuplet else base

    @property
    def quarter_length(self) -> Fraction:
        """Length in quarter notes (beats for the audio layer)."""
        return self.length * 4


@dataclass(frozen=True, slots=True)
class Meter:
    """A time signature such as 3/4 or 6/8.

    ``grouping`` gives the beat groups of an irregular meter in units of
    ``beat_unit`` (7/8 as ``(2, 2, 3)``). When it is omitted, simple and
    compound meters group regularly and other meters (5/8, 7/8) are
    (odd counts of eighths or shorter) are grouped in twos with one three at
    the end.
    """

    beats: int
    beat_unit: int
    grouping: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if self.beats < 1:
            raise ValueError('a meter needs at least one beat')
        if self.beat_unit not in (1, 2, 4, 8, 16, 32):
            raise ValueError(f'unsupported beat unit: {self.beat_unit}')
        if self.grouping is not None and sum(self.grouping) != self.beats:
            raise ValueError('grouping must add up to the number of beats')

    @classmethod
    def parse(cls, text: str) -> Meter:
        match = _METER_RE.match(text.strip())
        if not match:
            raise ValueError(f'not a meter: {text!r}')
        return cls(int(match.group(1)), int(match.group(2)))

    @property
    def bar_length(self) -> Fraction:
        """Length of one bar in whole notes."""
        return Fraction(self.beats, self.beat_unit)

    @property
    def is_compound(self) -> bool:
        """6/8, 9/8, 12/8 and the like: the pulse is a dotted note."""
        if self.grouping is not None:
            return len(self.grouping) > 1 and all(group == 3 for group in self.grouping)
        return self.beats % 3 == 0 and self.beats > 3

    @property
    def groups(self) -> tuple[int, ...]:
        """Beat groups in units of ``beat_unit``.

        4/4 → (1, 1, 1, 1), 6/8 → (3, 3), 7/8 → (2, 2, 3).
        """
        if self.grouping is not None:
            return self.grouping
        if self.is_compound:
            return (3,) * (self.beats // 3)
        if self.beat_unit >= 8 and self.beats > 3 and self.beats % 2:
            threes = 1
            twos = (self.beats - 3 * threes) // 2
            return (2,) * twos + (3,) * threes
        return (1,) * self.beats

    @property
    def pulse(self) -> Fraction:
        """Length of the felt beat in whole notes (a dotted quarter in 6/8)."""
        if self.is_compound:
            return Fraction(3, self.beat_unit)
        return Fraction(1, self.beat_unit)

    def __str__(self) -> str:
        return f'{self.beats}/{self.beat_unit}'
