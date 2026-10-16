# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Lead-sheet chord symbols.

:meth:`ChordSymbol.parse` accepts the common spellings found in fake
books and jazz texts and normalises them:

* major seventh: ``Cmaj7``, ``CM7``, ``CΔ7``, ``CΔ``, ``C^7``, ``Cma7``
* minor: ``Cm``, ``Cmin``, ``Cmi``, ``C-``
* half-diminished: ``Cm7b5``, ``Cø``, ``Cø7``, ``C-7b5``, ``Cmi7(♭5)``
* diminished: ``Cdim``, ``Co``, ``C°``; ``Cdim7``, ``Co7``, ``C°7``
* augmented: ``Caug``, ``C+``; ``C7#5``, ``C+7``, ``Caug7``, ``C7+5``
* altered tones with ``b``/``#``/``♭``/``♯`` or ``-``/``+`` after a
  number: ``C7b9``, ``C7(#9)``, ``C7-9``; parentheses and commas are
  ignored
* ``Csus`` is ``Csus4``, ``C6/9`` is ``C69``, ``Cadd2`` is ``Cadd9``
* a slash names the bass: ``C/E``, ``Am7/G``, ``C/D``

Symbols are written back in one canonical form (``str()`` in ASCII,
:attr:`ChordSymbol.symbol` with ``♭ ♯ ° ø``): ``Cmaj7``, ``Cm7``,
``Cm7b5``/``Cø7``, ``Cdim7``/``C°7``, ``Caug``/``C+``, ``C69``, ``C7#9``.
The extended chords are spelled as described in :mod:`etude.core.chord`
(``C13`` omits the eleventh).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .chord import Chord, ChordQuality
from .pitch import PitchName

_Q = ChordQuality

# quality: (ASCII form, Unicode form, accepted normalised spellings)
_SYMBOLS: dict[ChordQuality, tuple[str, str, tuple[str, ...]]] = {
    _Q.MAJOR: ('', '', ('maj',)),
    _Q.MINOR: ('m', 'm', ()),
    _Q.DIMINISHED: ('dim', '°', ()),
    _Q.AUGMENTED: ('aug', '+', ('#5',)),
    _Q.SUS2: ('sus2', 'sus2', ()),
    _Q.SUS4: ('sus4', 'sus4', ('sus',)),
    _Q.DOMINANT_SEVENTH: ('7', '7', ()),
    _Q.MAJOR_SEVENTH: ('maj7', 'maj7', ()),
    _Q.MINOR_SEVENTH: ('m7', 'm7', ()),
    _Q.HALF_DIMINISHED_SEVENTH: ('m7b5', 'ø7', ('ø', 'ø7')),
    _Q.DIMINISHED_SEVENTH: ('dim7', '°7', ()),
    _Q.MINOR_MAJOR_SEVENTH: ('m(maj7)', 'm(maj7)', ('mmaj7',)),
    _Q.AUGMENTED_MAJOR_SEVENTH: ('maj7#5', 'maj7♯5', ('augmaj7', 'maj7aug', '#5maj7')),
    _Q.AUGMENTED_SEVENTH: ('7#5', '7♯5', ('aug7', '7aug')),
    _Q.MAJOR_SIXTH: ('6', '6', ('maj6',)),
    _Q.MINOR_SIXTH: ('m6', 'm6', ()),
    _Q.SIX_NINE: ('69', '6/9', ('maj69',)),
    _Q.MINOR_SIX_NINE: ('m69', 'm6/9', ()),
    _Q.ADD_NINE: ('add9', 'add9', ('add2',)),
    _Q.MINOR_ADD_NINE: ('m(add9)', 'm(add9)', ('madd9', 'madd2')),
    _Q.DOMINANT_SEVENTH_FLAT_FIVE: ('7b5', '7♭5', ()),
    _Q.DOMINANT_SEVENTH_SUS4: ('7sus4', '7sus4', ('7sus', 'sus7', 'sus47')),
    _Q.DOMINANT_NINTH: ('9', '9', ()),
    _Q.MAJOR_NINTH: ('maj9', 'maj9', ()),
    _Q.MINOR_NINTH: ('m9', 'm9', ()),
    _Q.MINOR_MAJOR_NINTH: ('m(maj9)', 'm(maj9)', ('mmaj9',)),
    _Q.DOMINANT_NINTH_SUS4: ('9sus4', '9sus4', ('9sus',)),
    _Q.DOMINANT_FLAT_NINTH: ('7b9', '7♭9', ()),
    _Q.DOMINANT_SHARP_NINTH: ('7#9', '7♯9', ()),
    _Q.DOMINANT_FLAT_FIVE_FLAT_NINTH: ('7b5b9', '7♭5♭9', ('7b9b5',)),
    _Q.DOMINANT_FLAT_FIVE_SHARP_NINTH: ('7b5#9', '7♭5♯9', ('7#9b5',)),
    _Q.DOMINANT_SHARP_FIVE_FLAT_NINTH: ('7#5b9', '7♯5♭9', ('7b9#5', 'aug7b9')),
    _Q.DOMINANT_SHARP_FIVE_SHARP_NINTH: ('7#5#9', '7♯5♯9', ('7#9#5', 'aug7#9')),
    _Q.DOMINANT_ELEVENTH: ('11', '11', ()),
    _Q.MINOR_ELEVENTH: ('m11', 'm11', ()),
    _Q.DOMINANT_SHARP_ELEVENTH: ('7#11', '7♯11', ()),
    _Q.DOMINANT_NINTH_SHARP_ELEVENTH: ('9#11', '9♯11', ()),
    _Q.MAJOR_SEVENTH_SHARP_ELEVENTH: ('maj7#11', 'maj7♯11', ()),
    _Q.MAJOR_NINTH_SHARP_ELEVENTH: ('maj9#11', 'maj9♯11', ()),
    _Q.DOMINANT_THIRTEENTH: ('13', '13', ()),
    _Q.MAJOR_THIRTEENTH: ('maj13', 'maj13', ()),
    _Q.MINOR_THIRTEENTH: ('m13', 'm13', ()),
    _Q.DOMINANT_THIRTEENTH_FLAT_NINTH: ('13b9', '13♭9', ()),
    _Q.DOMINANT_THIRTEENTH_SHARP_ELEVENTH: ('13#11', '13♯11', ()),
    _Q.DOMINANT_FLAT_THIRTEENTH: ('7b13', '7♭13', ()),
    _Q.ALTERED: ('7alt', '7alt', ('alt',)),
}

_TOKEN_RE = re.compile(
    r'(?P<half>halfdim|ø|Ø)'
    r'|(?P<maj>maj|Maj|MAJ|ma(?!dd)|Ma|MA|M|Δ|\^)'
    r'|(?P<min>min|mi|m)'
    r'|(?P<dim>dim|o|°)'
    r'|(?P<word>aug|sus|add|alt)'
    r'|(?P<acc>[#♯b♭+-])'
    r'|(?P<num>\d+)'
)
_ROOT_RE = re.compile(r'^([A-G](?:##|bb|#|b|x|♯|♭|𝄪|𝄫)?)(.*)$')
_BASS_RE = re.compile(r'^[A-G](?:##|bb|#|b|x|♯|♭|𝄪|𝄫)?$')


def _normalise(suffix: str) -> str:
    text = re.sub(r'[\s(),]', '', suffix)
    text = text.replace('6/9', '69')
    text = re.sub(r'Δ(?!\d)', 'Δ7', text)
    out: list[str] = []
    position = 0
    while position < len(text):
        match = _TOKEN_RE.match(text, position)
        if not match:
            raise ValueError(f'not a chord symbol suffix: {suffix!r}')
        position = match.end()
        kind = match.lastgroup
        token = match.group()
        if kind == 'acc':
            follows_number = bool(out) and out[-1][-1].isdigit()
            before_number = position < len(text) and text[position].isdigit()
            if token in '#♯' or (token == '+' and before_number and (follows_number or out)):
                out.append('#')
            elif token in 'b♭' or (token == '-' and before_number and follows_number):
                out.append('b')
            elif token == '+':
                out.append('aug')
            else:  # a leading '-' means minor
                out.append('m')
        elif kind == 'half':
            out.append('ø')
        elif kind == 'maj':
            out.append('maj')
        elif kind == 'min':
            out.append('m')
        elif kind == 'dim':
            out.append('dim')
        else:
            out.append(token)
    normalised = ''.join(out)
    return {'m7b5': 'ø7', 'mb5': 'dim', 'augmaj7': 'maj7#5'}.get(normalised, normalised)


_LOOKUP: dict[str, ChordQuality] = {}
for _quality, (_ascii, _unicode, _aliases) in _SYMBOLS.items():
    for _spelling in (_ascii, *_aliases):
        _LOOKUP[_normalise(_spelling)] = _quality


@dataclass(frozen=True, slots=True)
class ChordSymbol:
    """A lead-sheet symbol: root, quality and an optional bass note (``C/E``)."""

    root: PitchName
    quality: ChordQuality
    bass: PitchName | None = None

    def __post_init__(self) -> None:
        if self.quality not in _SYMBOLS:
            raise ValueError(f'no chord symbol for a {self.quality.value} chord')

    @classmethod
    def parse(cls, text: str) -> ChordSymbol:
        """Parse a chord symbol such as ``'Cm7'``, ``'F#ø7'``, ``'Bb13'`` or ``'C/E'``."""
        text = text.strip()
        bass: PitchName | None = None
        head, slash, tail = text.rpartition('/')
        if slash and _BASS_RE.match(tail.strip()):
            text, bass = head, PitchName.parse(tail.strip())
        match = _ROOT_RE.match(text)
        if not match:
            raise ValueError(f'not a chord symbol: {text!r}')
        root = PitchName.parse(match.group(1))
        quality = _LOOKUP.get(_normalise(match.group(2)))
        if quality is None:
            raise ValueError(f'unknown chord symbol: {text!r}')
        if bass == root:
            bass = None
        return cls(root, quality, bass)

    @classmethod
    def from_chord(cls, chord: Chord) -> ChordSymbol:
        """Symbol for a chord; inversions become slash chords (C major/E → ``C/E``)."""
        return cls(chord.root, chord.quality, chord.bass if chord.inversion else None)

    def to_chord(self) -> Chord:
        """The chord the symbol names, inverted when the bass is a chord tone.

        Raises :class:`ValueError` when the bass is not a chord tone
        (``C/D``); use :attr:`chord_without_bass` and :attr:`bass` then.
        """
        chord = self.chord_without_bass
        if self.bass is None:
            return chord
        names = chord.names()
        if self.bass not in names:
            raise ValueError(f'{self.bass} is not a chord tone of {self}')
        return chord.with_inversion(names.index(self.bass))

    @property
    def chord_without_bass(self) -> Chord:
        return Chord(self.root, self.quality)

    def __str__(self) -> str:
        text = f'{self.root}{_SYMBOLS[self.quality][0]}'
        return f'{text}/{self.bass}' if self.bass else text

    @property
    def symbol(self) -> str:
        """Display form with Unicode accidentals and ``° ø +``: ``'F♯ø7'``, ``'B♭7♯9'``."""
        text = f'{self.root.symbol}{_SYMBOLS[self.quality][1]}'
        return f'{text}/{self.bass.symbol}' if self.bass else text
