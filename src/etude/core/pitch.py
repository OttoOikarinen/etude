# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Spelled pitches.

Pitches are *spelled*: C♯4 and D♭4 are different pitches that happen to
share MIDI number 61. Octaves follow scientific pitch notation, so C4 is
middle C (MIDI 60) and the octave number changes between B and C: B♯3
sounds like C4 and C♭4 sounds like B3.

Two coordinates are used throughout the code base:

* ``diatonic_index`` counts letter names (``octave * 7 + letter``). It
  drives staff positions and interval numbers.
* ``line_of_fifths`` places a spelling on the chain of fifths
  (… F=-1, C=0, G=1, D=2 …). It drives key signatures and enharmonics.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import IntEnum
from functools import total_ordering
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .interval import Interval

MAX_ALTER = 3
"""Largest supported alteration (triple sharp). Double sharps and flats are
the most that appear in notation; triples can arise as intermediate values
when transposing theoretical spellings."""

_NATURAL_SEMITONES = (0, 2, 4, 5, 7, 9, 11)
_NATURAL_FIFTHS = (0, 2, 4, -1, 1, 3, 5)  # C D E F G A B on the line of fifths
_ASCII_ACCIDENTALS = {-3: 'bbb', -2: 'bb', -1: 'b', 0: '', 1: '#', 2: '##', 3: '###'}
_SYMBOL_ACCIDENTALS = {-3: '♭𝄫', -2: '𝄫', -1: '♭', 0: '', 1: '♯', 2: '𝄪', 3: '♯𝄪'}
_ALTER_TOKENS = {
    '': 0,
    '#': 1,
    '##': 2,
    '###': 3,
    'x': 2,
    '♯': 1,
    '𝄪': 2,
    '♯♯': 2,
    'b': -1,
    'bb': -2,
    'bbb': -3,
    '♭': -1,
    '𝄫': -2,
    '♭♭': -2,
    '♯𝄪': 3,
    '♭𝄫': -3,
}
_NAME_RE = re.compile(r'^([A-Ga-g])(#{1,3}|x|b{1,3}|♯𝄪|♭𝄫|♯{1,2}|♭{1,2}|𝄪|𝄫)?$')
_PITCH_RE = re.compile(r'^([A-Ga-g])(#{1,3}|x|b{1,3}|♯𝄪|♭𝄫|♯{1,2}|♭{1,2}|𝄪|𝄫)?(-?\d+)$')


class Letter(IntEnum):
    """A letter name. The value is the diatonic step above C."""

    C = 0
    D = 1
    E = 2
    F = 3
    G = 4
    A = 5
    B = 6

    @property
    def semitones(self) -> int:
        """Semitones of the natural note above C."""
        return _NATURAL_SEMITONES[self]

    @property
    def fifths(self) -> int:
        """Position of the natural note on the line of fifths (C = 0)."""
        return _NATURAL_FIFTHS[self]

    def __str__(self) -> str:
        return self.name


def _check_alter(alter: int) -> None:
    if not -MAX_ALTER <= alter <= MAX_ALTER:
        raise ValueError(f'alteration {alter} is outside ±{MAX_ALTER}')


@dataclass(frozen=True, slots=True)
class PitchName:
    """A spelled pitch class without an octave, such as F♯ or B♭."""

    letter: Letter
    alter: int = 0

    def __post_init__(self) -> None:
        _check_alter(self.alter)

    @classmethod
    def parse(cls, text: str) -> PitchName:
        """Parse ``'C'``, ``'f#'``, ``'Bb'``, ``'Ebb'``, ``'Fx'`` or ``'F♯'``."""
        match = _NAME_RE.match(text.strip())
        if not match:
            raise ValueError(f'not a pitch name: {text!r}')
        return cls(Letter[match.group(1).upper()], _ALTER_TOKENS[match.group(2) or ''])

    @classmethod
    def from_line_of_fifths(cls, position: int) -> PitchName:
        """Return the spelling at ``position`` on the line of fifths (C = 0, G = 1, F = -1)."""
        # F C G D A E B is the natural segment -1..5; each 7 steps adds a sharp.
        alter, offset = divmod(position + 1, 7)
        letter = (Letter.F, Letter.C, Letter.G, Letter.D, Letter.A, Letter.E, Letter.B)[offset]
        return cls(letter, alter)

    @property
    def line_of_fifths(self) -> int:
        return self.letter.fifths + 7 * self.alter

    @property
    def pitch_class(self) -> int:
        """Integer pitch class, 0 = C."""
        return (self.letter.semitones + self.alter) % 12

    @property
    def symbol(self) -> str:
        """Display form with Unicode accidentals, e.g. ``'F♯'``."""
        return self.letter.name + _SYMBOL_ACCIDENTALS[self.alter]

    def at(self, octave: int) -> Pitch:
        """Return this spelling in a given octave."""
        return Pitch(self.letter, self.alter, octave)

    def transpose(self, interval: Interval, *, down: bool = False) -> PitchName:
        return self.at(4).transpose(interval, down=down).name

    def is_enharmonic(self, other: PitchName) -> bool:
        return self.pitch_class == other.pitch_class

    def respell(self, letter: Letter) -> PitchName:
        """Spell the same pitch class on ``letter``: C♯ on D is D♭, B♯ on C is C.

        Raises :class:`ValueError` when the spelling would need more than a
        triple sharp or flat.
        """
        alter = (self.pitch_class - letter.semitones + 6) % 12 - 6
        return PitchName(letter, alter)

    def enharmonics(self, *, max_alter: int = 2) -> tuple[PitchName, ...]:
        """Other spellings of this pitch class with at most ``max_alter`` accidentals.

        Ordered along the line of fifths (flattest first): ``C♯`` gives
        ``(D♭, B𝄪)``. ``self`` is not included.
        """
        found: list[PitchName] = []
        for letter in Letter:
            alter = (self.pitch_class - letter.semitones + 6) % 12 - 6
            if abs(alter) <= max_alter and letter != self.letter:
                found.append(PitchName(letter, alter))
        return tuple(sorted(found, key=lambda name: name.line_of_fifths))

    def simplest(self, *, prefer_flats: bool = False) -> PitchName:
        """The spelling with the fewest accidentals: B♯ → C, E𝄫 → D, F♭ → E.

        A name that already has the fewest accidentals is kept (D♭ stays
        D♭). Otherwise a tie between a sharp and a flat spelling goes to the
        sharp unless ``prefer_flats`` is set: B𝄪 → C♯, or D♭ with
        ``prefer_flats``.
        """
        candidates = (self, *self.enharmonics(max_alter=MAX_ALTER))
        best = min(abs(name.alter) for name in candidates)
        if abs(self.alter) == best:
            return self
        sign = -1 if prefer_flats else 1
        return min(
            (name for name in candidates if abs(name.alter) == best),
            key=lambda name: name.alter * -sign,
        )

    def __str__(self) -> str:
        return self.letter.name + _ASCII_ACCIDENTALS[self.alter]


@total_ordering
@dataclass(frozen=True, slots=True, eq=True)
class Pitch:
    """A spelled pitch in scientific pitch notation (C4 = middle C).

    Equality is spelled (``C♯4 != D♭4``); use :meth:`is_enharmonic` to
    compare sounding pitch. Ordering sorts by sounding pitch first and by
    letter second, which keeps it consistent with equality.
    """

    letter: Letter
    alter: int = 0
    octave: int = 4

    def __post_init__(self) -> None:
        _check_alter(self.alter)

    @classmethod
    def parse(cls, text: str) -> Pitch:
        """Parse ``'C4'``, ``'f#5'``, ``'Bb3'``, ``'Fx4'`` or ``'C-1'``."""
        match = _PITCH_RE.match(text.strip())
        if not match:
            raise ValueError(f'not a pitch: {text!r}')
        return cls(
            Letter[match.group(1).upper()],
            _ALTER_TOKENS[match.group(2) or ''],
            int(match.group(3)),
        )

    @classmethod
    def from_diatonic(cls, diatonic_index: int, midi: int) -> Pitch:
        """Spell ``midi`` on the letter given by ``diatonic_index``."""
        octave, step = divmod(diatonic_index, 7)
        letter = Letter(step)
        natural = 12 * (octave + 1) + letter.semitones
        return cls(letter, midi - natural, octave)

    @classmethod
    def from_midi(cls, midi: int, *, prefer_flats: bool = False) -> Pitch:
        """Default spelling of a MIDI note: naturals, else sharps (or flats)."""
        octave, pc = divmod(midi, 12)
        octave -= 1
        for letter in Letter:
            if letter.semitones == pc:
                return cls(letter, 0, octave)
        if prefer_flats:
            letter = Letter(next(i for i, s in enumerate(_NATURAL_SEMITONES) if s == pc + 1))
            return cls(letter, -1, octave)
        letter = Letter(next(i for i, s in enumerate(_NATURAL_SEMITONES) if s == pc - 1))
        return cls(letter, 1, octave)

    @property
    def name(self) -> PitchName:
        return PitchName(self.letter, self.alter)

    @property
    def diatonic_index(self) -> int:
        """Number of letter steps above C0. C4 = 28, D4 = 29, C5 = 35."""
        return self.octave * 7 + self.letter

    @property
    def midi(self) -> int:
        """MIDI note number. C4 = 60. May fall outside 0–127 for extreme pitches."""
        return 12 * (self.octave + 1) + self.letter.semitones + self.alter

    @property
    def pitch_class(self) -> int:
        return self.midi % 12

    @property
    def symbol(self) -> str:
        """Display form with Unicode accidentals, e.g. ``'F♯4'``."""
        return f'{self.name.symbol}{self.octave}'

    def frequency(self, a4: float = 440.0) -> float:
        """Equal-tempered frequency in hertz."""
        return a4 * math.pow(2.0, (self.midi - 69) / 12)

    def transpose(self, interval: Interval, *, down: bool = False) -> Pitch:
        """Move by a spelled interval. ``C4 + M3 = E4``, ``C4 - M3 = A♭3``."""
        sign = -1 if down else 1
        return Pitch.from_diatonic(
            self.diatonic_index + sign * (interval.number - 1),
            self.midi + sign * interval.semitones,
        )

    def is_enharmonic(self, other: Pitch) -> bool:
        return self.midi == other.midi

    def respell(self, letter: Letter) -> Pitch:
        """Spell the same sounding pitch on ``letter``: C♯4 → D♭4, B♯3 → C4, C4 → B♯3.

        The octave follows the letter, so the MIDI number never changes.
        Raises :class:`ValueError` beyond a triple sharp or flat.
        """
        alter = (self.pitch_class - letter.semitones + 6) % 12 - 6
        natural = self.midi - alter
        return Pitch(letter, alter, (natural - letter.semitones) // 12 - 1)

    def enharmonics(self, *, max_alter: int = 2) -> tuple[Pitch, ...]:
        """Other spellings of the same sounding pitch (see :meth:`PitchName.enharmonics`)."""
        return tuple(
            self.respell(name.letter) for name in self.name.enharmonics(max_alter=max_alter)
        )

    def simplest(self, *, prefer_flats: bool = False) -> Pitch:
        """The same sounding pitch with the fewest accidentals: B♯3 → C4."""
        return self.respell(self.name.simplest(prefer_flats=prefer_flats).letter)

    def _key(self) -> tuple[int, int]:
        return (self.midi, self.diatonic_index)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Pitch):
            return NotImplemented
        return self._key() < other._key()

    def __str__(self) -> str:
        return f'{self.name}{self.octave}'
