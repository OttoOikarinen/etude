# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Spelled intervals.

An interval has a *number* (1 = unison, 8 = octave, 10 = tenth) that
counts letter names, and a *quality* that fixes the exact size. G4–E5 is
a major sixth because it spans six letter names and nine semitones.
Intervals carry no direction; pass ``down=True`` to
:meth:`etude.core.pitch.Pitch.transpose` for descending motion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .pitch import Pitch

_SIMPLE_SEMITONES = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11}
_PERFECT_CLASS = frozenset({1, 4, 5})
_INTERVAL_RE = re.compile(r'^(dd|d|m|P|M|AA|A)(\d+)$')


class Quality(Enum):
    DOUBLY_DIMINISHED = 'dd'
    DIMINISHED = 'd'
    MINOR = 'm'
    PERFECT = 'P'
    MAJOR = 'M'
    AUGMENTED = 'A'
    DOUBLY_AUGMENTED = 'AA'


# Semitone offset from the perfect or major size of the same number.
_PERFECT_OFFSETS = {
    Quality.DOUBLY_DIMINISHED: -2,
    Quality.DIMINISHED: -1,
    Quality.PERFECT: 0,
    Quality.AUGMENTED: 1,
    Quality.DOUBLY_AUGMENTED: 2,
}
_MAJOR_OFFSETS = {
    Quality.DOUBLY_DIMINISHED: -3,
    Quality.DIMINISHED: -2,
    Quality.MINOR: -1,
    Quality.MAJOR: 0,
    Quality.AUGMENTED: 1,
    Quality.DOUBLY_AUGMENTED: 2,
}
_INVERTED_QUALITY = {
    Quality.DOUBLY_DIMINISHED: Quality.DOUBLY_AUGMENTED,
    Quality.DIMINISHED: Quality.AUGMENTED,
    Quality.MINOR: Quality.MAJOR,
    Quality.PERFECT: Quality.PERFECT,
    Quality.MAJOR: Quality.MINOR,
    Quality.AUGMENTED: Quality.DIMINISHED,
    Quality.DOUBLY_AUGMENTED: Quality.DOUBLY_DIMINISHED,
}


@dataclass(frozen=True, slots=True)
class Interval:
    quality: Quality
    number: int

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError(f'interval number must be 1 or more, not {self.number}')
        if self.quality not in self._offsets():
            raise ValueError(f'{self.quality.name.lower()} is not a quality of a {self.number}')
        if self.number == 1 and self._offsets()[self.quality] < 0:
            raise ValueError('a unison cannot be diminished')

    @classmethod
    def parse(cls, text: str) -> Interval:
        """Parse the usual abbreviations: ``'P5'``, ``'m6'``, ``'A4'``, ``'dd7'``, ``'M10'``."""
        match = _INTERVAL_RE.match(text.strip())
        if not match:
            raise ValueError(f'not an interval: {text!r}')
        return cls(Quality(match.group(1)), int(match.group(2)))

    @classmethod
    def between(cls, low: Pitch, high: Pitch) -> Interval:
        """Return the interval from ``low`` up to ``high``.

        ``high`` must not be spelled on a lower letter than ``low``. Raises
        :class:`ValueError` when the size is beyond doubly augmented or
        diminished, e.g. C♯4 to C♭4.
        """
        number = high.diatonic_index - low.diatonic_index + 1
        if number < 1:
            raise ValueError(f'{high} is spelled below {low}')
        semitones = high.midi - low.midi
        simple = (number - 1) % 7 + 1
        offset = semitones - _SIMPLE_SEMITONES[simple] - 12 * ((number - 1) // 7)
        offsets = _PERFECT_OFFSETS if simple in _PERFECT_CLASS else _MAJOR_OFFSETS
        for quality, value in offsets.items():
            if value == offset and not (number == 1 and value < 0):
                return cls(quality, number)
        raise ValueError(f'no interval quality spans {low} to {high}')

    def _offsets(self) -> dict[Quality, int]:
        return _PERFECT_OFFSETS if self.is_perfect_class else _MAJOR_OFFSETS

    @property
    def simple_number(self) -> int:
        """Number reduced to 1–7 (an octave reduces to 1)."""
        return (self.number - 1) % 7 + 1

    @property
    def octaves(self) -> int:
        """Whole octaves contained above the simple part."""
        return (self.number - 1) // 7

    @property
    def is_perfect_class(self) -> bool:
        return self.simple_number in _PERFECT_CLASS

    @property
    def is_compound(self) -> bool:
        """True for intervals wider than an octave."""
        return self.number > 8

    @property
    def semitones(self) -> int:
        return (
            _SIMPLE_SEMITONES[self.simple_number]
            + 12 * self.octaves
            + self._offsets()[self.quality]
        )

    def simple(self) -> Interval:
        """Reduce a compound interval: M10 → M3, P15 → P8. Simple intervals are returned as is."""
        if not self.is_compound:
            return self
        number = self.simple_number
        return Interval(self.quality, 8 if number == 1 else number)

    def inverted(self) -> Interval:
        """Invert within the octave: m6 → M3, A4 → d5, P8 → P1. Compound intervals reduce first."""
        simple = self.simple()
        return Interval(_INVERTED_QUALITY[simple.quality], 9 - simple.number)

    def __str__(self) -> str:
        return f'{self.quality.value}{self.number}'
