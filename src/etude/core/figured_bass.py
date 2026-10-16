# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Figured bass.

A figure is a stack of numbers, each optionally with an accidental, that
names the intervals above the bass. Notes take the key signature unless
an accidental says otherwise. Conventions (Kostka & Payne, *Tonal
Harmony*, ch. 4; Open Music Theory, "Figured bass"):

* An accidental next to a number (before or after it: ``#6``, ``6#``,
  ``b7``) raises or lowers that note by a semitone *from the key
  signature*; ``♮`` (or ``n``) cancels the signature. So ``#3`` over G in
  F major (B♭ in the signature) gives B♮.
* An accidental standing alone applies to the third above the bass:
  ``#`` is ``5 #3``, ``6 #`` is ``6 #3``.
* A slashed number (``6\\``, ``6+`` or ``6`` with a combining stroke,
  ``6̸``) raises that note by a semitone, like ``#6``.
* Abbreviations expand as usual: nothing or ``5`` → 5/3, ``6`` → 6/3,
  ``7`` → 7/5/3, ``6/5`` → 6/5/3, ``4/3`` → 6/4/3, ``4/2`` and ``2`` →
  6/4/2, ``9`` → 9/5/3, ``4`` → 5/4. Other stacks are taken literally.

Figures are separated by ``/``, spaces or commas; adjacent digits are
separate figures (``65`` is 6 over 5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .key import KeySignature
from .pitch import Letter, PitchName
from .scale import Key


class FigureAccidental(Enum):
    SHARP = '#'
    FLAT = 'b'
    NATURAL = '♮'
    RAISED = '+'
    """A slashed figure: raise by a semitone."""

    @property
    def symbol(self) -> str:
        return {'#': '♯', 'b': '♭', '♮': '♮', '+': '+'}[self.value]


_ACCIDENTALS = {
    '#': FigureAccidental.SHARP,
    '♯': FigureAccidental.SHARP,
    'b': FigureAccidental.FLAT,
    '♭': FigureAccidental.FLAT,
    'n': FigureAccidental.NATURAL,
    '♮': FigureAccidental.NATURAL,
}
_TOKEN_RE = re.compile(r'([#♯b♭n♮]?)(\d)([#♯b♭n♮]?)([\\+̸⃥]?)|([#♯b♭n♮])')
_EXPANSIONS: dict[frozenset[int], tuple[int, ...]] = {
    frozenset(): (5, 3),
    frozenset({3}): (5, 3),
    frozenset({5}): (5, 3),
    frozenset({6}): (6, 3),
    frozenset({7}): (7, 5, 3),
    frozenset({7, 3}): (7, 5, 3),
    frozenset({7, 5}): (7, 5, 3),
    frozenset({6, 5}): (6, 5, 3),
    frozenset({4, 3}): (6, 4, 3),
    frozenset({2}): (6, 4, 2),
    frozenset({4, 2}): (6, 4, 2),
    frozenset({9}): (9, 5, 3),
    frozenset({4}): (5, 4),
}


@dataclass(frozen=True, slots=True)
class Figure:
    """One number of a figured-bass stack, e.g. ``#6``."""

    number: int
    accidental: FigureAccidental | None = None

    def __post_init__(self) -> None:
        if self.number < 2:
            raise ValueError(f'figures start at 2, not {self.number}')

    def __str__(self) -> str:
        if self.accidental is FigureAccidental.RAISED:
            return f'{self.number}+'
        prefix = self.accidental.value if self.accidental else ''
        return f'{prefix}{self.number}'


@dataclass(frozen=True, slots=True)
class FiguredBass:
    """The figures written under one bass note, as given (not expanded).

    ``FiguredBass.parse('6/5')`` has the figures 6 and 5; :meth:`expanded`
    adds the implied 3.
    """

    figures: tuple[Figure, ...]

    @classmethod
    def parse(cls, text: str) -> FiguredBass:
        """Parse ``''``, ``'6'``, ``'6/4'``, ``'7'``, ``'65'``, ``'4/3'``, ``'#'``, ``'b6'``,
        ``'♮'``, ``'6\\'`` or ``'7 #'``. A lone accidental belongs to the third."""
        compact = re.sub(r'[\s,/]+', ' ', text.strip())
        figures: list[Figure] = []
        position = 0
        for match in _TOKEN_RE.finditer(compact):
            if compact[position : match.start()].strip():
                raise ValueError(f'not a figured bass: {text!r}')
            position = match.end()
            before, digit, after, slash, alone = match.groups()
            if alone:
                figures.append(Figure(3, _ACCIDENTALS[alone]))
                continue
            if before and after:
                raise ValueError(f'two accidentals on one figure in {text!r}')
            accidental = _ACCIDENTALS[before or after] if before or after else None
            if slash:
                if accidental is not None:
                    raise ValueError(f'a slashed figure cannot have an accidental: {text!r}')
                accidental = FigureAccidental.RAISED
            figures.append(Figure(int(digit), accidental))
        if compact[position:].strip():
            raise ValueError(f'not a figured bass: {text!r}')
        numbers = [f.number for f in figures]
        if len(numbers) != len(set(numbers)):
            raise ValueError(f'a figure is repeated in {text!r}')
        return cls(tuple(figures))

    def expanded(self) -> tuple[Figure, ...]:
        """The full stack, highest number first, with implied figures added: 6/5 → 6 5 3."""
        given = {f.number: f for f in self.figures}
        numbers = _EXPANSIONS.get(frozenset(given), tuple(sorted(given, reverse=True)))
        return tuple(given.get(n, Figure(n)) for n in sorted(numbers, reverse=True))

    def realize(self, bass: PitchName, key: Key | KeySignature) -> tuple[PitchName, ...]:
        """Pitch names above the bass, lowest interval first.

        ``FiguredBass.parse('6/5').realize(B, C major)`` gives D F G.
        """
        signature = key.signature if isinstance(key, Key) else key
        result: list[PitchName] = []
        for figure in reversed(self.expanded()):
            letter = Letter((bass.letter + figure.number - 1) % 7)
            alter = signature.alter_for(letter)
            match figure.accidental:
                case FigureAccidental.SHARP | FigureAccidental.RAISED:
                    alter += 1
                case FigureAccidental.FLAT:
                    alter -= 1
                case FigureAccidental.NATURAL:
                    alter = 0
                case None:
                    pass
            result.append(PitchName(letter, alter))
        return tuple(result)

    def __str__(self) -> str:
        return '/'.join(str(f) for f in sorted(self.figures, key=lambda f: -f.number))


def figures_for_inversion(size: int, inversion: int) -> FiguredBass:
    """Abbreviated figures for a triad (``size=3``) or seventh chord (``size=4``) inversion."""
    table = {3: ('', '6', '6/4'), 4: ('7', '6/5', '4/3', '4/2')}
    if size not in table or not 0 <= inversion < size:
        raise ValueError(f'no inversion figure for inversion {inversion} of a {size}-note chord')
    return FiguredBass.parse(table[size][inversion])
