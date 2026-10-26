# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Roman numeral analysis.

Notation follows common North American usage (Kostka & Payne, *Tonal
Harmony*; Gotham et al., *Open Music Theory*):

* **Case and symbols give the quality.** Upper case is major, lower case
  minor, ``o`` (or ``°``) diminished, ``ø`` half-diminished and ``+``
  augmented. With a seventh: ``V7`` is a dominant (major-minor) seventh,
  ``IM7`` a major seventh, ``ii7`` a minor seventh, ``iiø7``
  half-diminished, ``viio7`` fully diminished, ``iM7`` minor-major,
  ``III+M7`` augmented-major and ``V+7`` augmented (dominant ♯5).
* **Figures give the inversion**, written without slashes in the output:
  ``6`` and ``64`` for triads, ``7``, ``65``, ``43`` and ``42`` for
  seventh chords. Input may use slashes (``V6/5``) and ``2`` for ``42``.
* **Roots are scale degrees of the key's own scale**: the major scale in
  major and the natural minor scale in minor, so ``III``, ``VI`` and
  ``VII`` in C minor are E♭, A♭ and B♭ without accidentals. A lower-case
  ``vii`` in minor (``viio``, ``viio7``, ``viiø7``) is built on the
  raised leading tone, as in Kostka & Payne. An accidental before the
  numeral alters the root from there: ``bVI`` in C major is A♭ (modal
  mixture) and ``bII6`` is the Neapolitan sixth in both modes (D♭–F–A♭ in
  C major and C minor). ``N6`` is accepted as input.
* **Secondary functions** are written ``V7/V``, ``viio7/ii``; the target
  numeral's case says whether the tonicized key is major or minor, and
  targets can be chained (``V/V/V``).
* **Augmented sixth chords** are ``It+6``, ``Fr+6`` and ``Ger+6`` (input
  also accepts ``It6``, ``Fr43``, ``Ger65``). They are built on the
  lowered sixth degree with the raised fourth and the tonic: A♭–C–F♯,
  A♭–C–D–F♯ and A♭–C–E♭–F♯ in C major and C minor. In major the German sixth
  may be spelled with ♯2̂ for ♭3̂ (A♭–C–D♯–F♯ in C, the doubly augmented fourth
  that rises to the third of a cadential six-four); it is still labelled
  ``Ger+6``, and its ASCII form is ``Ger+6(#2)``.
* **Cad64** is the cadential six-four: the tonic triad in second inversion,
  analysed by its dominant function. :meth:`RomanNumeral.analyze` cannot
  tell it from ``I64`` without context and returns ``I64``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .chord import Chord, ChordKind, ChordQuality
from .interval import Interval
from .pitch import PitchName
from .scale import Key, Mode

_Q = ChordQuality

# (upper case, symbol) for every quality a Roman numeral can show.
_SPELLING: dict[ChordQuality, tuple[bool, str]] = {
    _Q.MAJOR: (True, ''),
    _Q.MINOR: (False, ''),
    _Q.DIMINISHED: (False, 'o'),
    _Q.AUGMENTED: (True, '+'),
    _Q.DOMINANT_SEVENTH: (True, ''),
    _Q.MAJOR_SEVENTH: (True, 'M'),
    _Q.MINOR_SEVENTH: (False, ''),
    _Q.HALF_DIMINISHED_SEVENTH: (False, 'ø'),
    _Q.DIMINISHED_SEVENTH: (False, 'o'),
    _Q.MINOR_MAJOR_SEVENTH: (False, 'M'),
    _Q.AUGMENTED_MAJOR_SEVENTH: (True, '+M'),
    _Q.AUGMENTED_SEVENTH: (True, '+'),
}
_TRIAD_BY_SPELLING = {spelling: q for q, spelling in _SPELLING.items() if q.kind is ChordKind.TRIAD}
_SEVENTH_BY_SPELLING = {
    spelling: q for q, spelling in _SPELLING.items() if q.kind is ChordKind.SEVENTH
}
_AUGMENTED_SIXTHS = {
    _Q.ITALIAN_SIXTH: 'It',
    _Q.FRENCH_SIXTH: 'Fr',
    _Q.GERMAN_SIXTH: 'Ger',
    _Q.DOUBLY_AUGMENTED_FOURTH: 'Ger',
}
_NUMERALS = ('I', 'II', 'III', 'IV', 'V', 'VI', 'VII')
_TRIAD_FIGURES = ('', '6', '64')
_SEVENTH_FIGURES = ('7', '65', '43', '42')
_FIGURE_INPUT = {
    None: (False, 0),
    '53': (False, 0),
    '5/3': (False, 0),
    '6': (False, 1),
    '63': (False, 1),
    '6/3': (False, 1),
    '64': (False, 2),
    '6/4': (False, 2),
    '7': (True, 0),
    '65': (True, 1),
    '6/5': (True, 1),
    '43': (True, 2),
    '4/3': (True, 2),
    '42': (True, 3),
    '4/2': (True, 3),
    '2': (True, 3),
}
_ACCIDENTAL_INPUT = {None: 0, 'b': -1, '♭': -1, 'bb': -2, '♭♭': -2, '#': 1, '♯': 1, '##': 2}
_FIGURE = r'(?P<figure>6/5|6/4|6/3|5/3|4/3|4/2|65|64|63|53|43|42|7|6|2)?'
_SECONDARY = r'(?:/(?P<secondary>[^\d].*))?'
_NUMERAL_RE = re.compile(
    r'^(?P<accidental>bb|b|♭♭|♭|##|#|♯)?'
    r'(?P<numeral>VII|VI|IV|V|III|II|I|vii|vi|iv|v|iii|ii|i)'
    r'(?P<symbol>\+M|o|ø|\+|M)?' + _FIGURE + _SECONDARY + '$'
)
_NEAPOLITAN_RE = re.compile(r'^N(?P<figure>6|63|6/3|53|5/3|64|6/4)?' + _SECONDARY + '$')
_AUGMENTED_SIXTH_RE = re.compile(
    r'^(?P<kind>It|Fr|Ger)(?:\+?6|\+?43|\+?4/3|\+?65|\+?6/5|\+)?'
    r'(?P<sharp_two>\((?:#|♯)2\))?' + _SECONDARY + '$'
)
_SHARP_TWO = '(#2)'
"""ASCII mark of the German sixth spelled with ♯2̂ (the doubly augmented fourth)."""
_CADENTIAL_RE = re.compile(r'^Cad(?:64|6/4)?$')
_MINOR_SIXTH = Interval.parse('m6')


@dataclass(frozen=True, slots=True)
class RomanNumeral:
    """A chord labelled relative to a key: degree, quality, inversion and secondary target.

    ``alter`` is the chromatic alteration of the root (``-1`` for ``bVI``).
    For augmented sixth chords ``degree`` is 6 and ``alter`` -1 (the
    lowered sixth degree of the major scale, which is the natural sixth in
    minor). ``cadential`` marks ``Cad64``, whose ``quality`` is stored as
    major and realized as the key's tonic triad.
    """

    degree: int
    quality: ChordQuality
    inversion: int = 0
    alter: int = 0
    secondary: RomanNumeral | None = None
    cadential: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.degree <= 7:
            raise ValueError(f'scale degree must be 1–7, not {self.degree}')
        if self.quality in _AUGMENTED_SIXTHS:
            if (self.degree, self.alter, self.inversion) != (6, -1, 0):
                raise ValueError('augmented sixth chords stand on ♭6 with ♭6 in the bass')
        elif self.quality not in _SPELLING:
            raise ValueError(f'a Roman numeral cannot show a {self.quality.value} chord')
        if not 0 <= self.inversion < self.quality.size:
            raise ValueError(f'a {self.quality.value} chord has no inversion {self.inversion}')
        if self.cadential and (self.degree, self.quality, self.inversion, self.alter) != (
            1,
            _Q.MAJOR,
            2,
            0,
        ):
            raise ValueError('Cad64 is stored as I64')
        target = self.secondary
        if target is not None and (
            target.quality not in (_Q.MAJOR, _Q.MINOR)
            or target.inversion
            or target.cadential
            or (target.degree == 1 and target.alter == 0 and target.secondary is None)
        ):
            raise ValueError('a secondary target must be a major or minor triad other than I')

    # Parsing and formatting -------------------------------------------------

    @classmethod
    def parse(cls, text: str) -> RomanNumeral:
        """Parse a Roman numeral such as ``'ii6'``, ``'V65'``, ``'viiø43'``, ``'V7/V'``,
        ``'bII6'``, ``'N6'``, ``'It+6'``, ``'Ger65'``, ``'Cad64'`` or ``'bVI'``."""
        text = text.strip().replace('°', 'o').replace('/o', 'ø')
        if _CADENTIAL_RE.match(text):
            return cls(1, _Q.MAJOR, 2, cadential=True)
        if match := _AUGMENTED_SIXTH_RE.match(text):
            quality = next(q for q, k in _AUGMENTED_SIXTHS.items() if k == match['kind'])
            if match['sharp_two']:
                if quality is not _Q.GERMAN_SIXTH:
                    raise ValueError(f'only the German sixth is spelled with ♯2: {text!r}')
                quality = _Q.DOUBLY_AUGMENTED_FOURTH
            return cls(6, quality, 0, -1, cls._parse_secondary(match['secondary']))
        if match := _NEAPOLITAN_RE.match(text):
            _, inversion = _FIGURE_INPUT[match['figure']]
            return cls(2, _Q.MAJOR, inversion, -1, cls._parse_secondary(match['secondary']))
        match = _NUMERAL_RE.match(text)
        if not match:
            raise ValueError(f'not a Roman numeral: {text!r}')
        numeral = match['numeral']
        upper = numeral.isupper()
        symbol = match['symbol'] or ''
        seventh, inversion = _FIGURE_INPUT[match['figure']]
        if symbol == 'ø' and match['figure'] is None:
            seventh = True  # 'viiø' is read as 'viiø7'
        table = _SEVENTH_BY_SPELLING if seventh else _TRIAD_BY_SPELLING
        found = table.get((upper, symbol))
        if found is None:
            raise ValueError(f'no chord quality is written {numeral}{symbol} in {text!r}')
        return cls(
            _NUMERALS.index(numeral.upper()) + 1,
            found,
            inversion,
            _ACCIDENTAL_INPUT[match['accidental']],
            cls._parse_secondary(match['secondary']),
        )

    @classmethod
    def _parse_secondary(cls, text: str | None) -> RomanNumeral | None:
        return None if text is None else cls.parse(text)

    @property
    def figure(self) -> str:
        """Inversion figure as written after the numeral (``''``, ``'6'``, ``'65'`` …)."""
        if self.quality.kind is ChordKind.TRIAD:
            return _TRIAD_FIGURES[self.inversion]
        return _SEVENTH_FIGURES[self.inversion]

    def _format(self, *, unicode: bool) -> str:
        if self.cadential:
            text = 'Cad64'
        elif self.quality in _AUGMENTED_SIXTHS:
            text = _AUGMENTED_SIXTHS[self.quality] + '+6'
            if self.quality is _Q.DOUBLY_AUGMENTED_FOURTH and not unicode:
                text += _SHARP_TWO
        else:
            upper, symbol = _SPELLING[self.quality]
            numeral = _NUMERALS[self.degree - 1]
            sharp, flat = ('♯', '♭') if unicode else ('#', 'b')
            accidental = sharp * self.alter if self.alter > 0 else flat * -self.alter
            if unicode:
                symbol = symbol.replace('o', '°')
            text = f'{accidental}{numeral if upper else numeral.lower()}{symbol}{self.figure}'
        if self.secondary is not None:
            text += '/' + self.secondary._format(unicode=unicode)
        return text

    def __str__(self) -> str:
        """ASCII form (``'viiø43'``, ``'bII6'``, ``'V7/V'``, ``'Ger+6(#2)'``) that
        :meth:`parse` reads back."""
        return self._format(unicode=False)

    @property
    def symbol(self) -> str:
        """Display form with ``♭``, ``♯`` and ``°``: ``'vii°7'``, ``'♭II6'``; both spellings
        of the German sixth are ``'Ger+6'``, as Kostka–Payne label them."""
        return self._format(unicode=True)

    # Realization ------------------------------------------------------------

    @property
    def is_upper(self) -> bool:
        if self.quality in _AUGMENTED_SIXTHS:
            return True
        return _SPELLING[self.quality][0]

    def tonicized_key(self, key: Key) -> Key:
        """The key the primary numeral is read in: ``key`` itself, or the secondary target's."""
        if self.secondary is None:
            return key
        target = self.secondary
        root = target._root(target.tonicized_key(key))
        return Key(root, Mode.MAJOR if target.quality is _Q.MAJOR else Mode.MINOR)

    def _root(self, key: Key) -> PitchName:
        if self.quality in _AUGMENTED_SIXTHS:
            return key.tonic.transpose(_MINOR_SIXTH)
        base = key.degree(self.degree)
        if key.mode is Mode.MINOR and self.degree == 7 and not self.is_upper:
            base = key.leading_tone
        return PitchName(base.letter, base.alter + self.alter)

    def realize(self, key: Key) -> Chord:
        """The spelled chord this numeral stands for in ``key``."""
        local = self.tonicized_key(key)
        if self.cadential:
            quality = _Q.MAJOR if local.mode is Mode.MAJOR else _Q.MINOR
            return Chord(local.tonic, quality, 2)
        return Chord(self._root(local), self.quality, self.inversion)

    # Analysis ---------------------------------------------------------------

    @classmethod
    def analyze(cls, chord: Chord, key: Key) -> RomanNumeral | None:
        """Label a spelled chord in a key, or return None if no label fits.

        Preference order, as a harmony textbook would label a chord out of
        context:

        1. Diatonic chords, including modal mixture: a chord whose tones all
           belong to the major key or all to the minor key on the same tonic
           (natural minor plus raised sixth and seventh): ``ii``, ``V7``,
           ``bVI``, ``iv`` in major, ``IV`` or ``I`` in minor.
        2. Augmented sixth chords with the lowered sixth degree in the bass.
        3. Secondary dominants and leading-tone chords of the diatonic major
           and minor triads (``V7/V``, ``viio7/ii``), and secondary augmented
           sixths.
        4. Any other chord with a numeral quality is labelled by its altered
           root, e.g. ``bII`` for the Neapolitan.
        """
        if chord.quality not in _SPELLING and chord.quality not in _AUGMENTED_SIXTHS:
            return None
        if chord.quality in _AUGMENTED_SIXTHS:
            candidate: RomanNumeral | None = None
            if chord.inversion == 0:
                candidate = cls(6, chord.quality, 0, -1)
        else:
            candidate = cls._by_root(chord, key)
        if candidate is not None and candidate.realize(key) == chord:
            names = set(chord.names())
            if candidate.quality in _AUGMENTED_SIXTHS or any(names <= pool for pool in _pools(key)):
                return candidate
        secondary = cls._as_secondary(chord, key)
        if secondary is not None:
            return secondary
        if candidate is not None and candidate.realize(key) == chord:
            return candidate
        return None

    @classmethod
    def _by_root(cls, chord: Chord, key: Key) -> RomanNumeral | None:
        degree = (chord.root.letter - key.tonic.letter) % 7 + 1
        probe = cls(degree, chord.quality, chord.inversion)
        alter = chord.root.alter - probe._root(key).alter
        if abs(alter) > 1:
            return None
        return cls(degree, chord.quality, chord.inversion, alter)

    @classmethod
    def _as_secondary(cls, chord: Chord, key: Key) -> RomanNumeral | None:
        if chord.quality in (_Q.MAJOR, _Q.DOMINANT_SEVENTH):
            primary = (5, 0)
        elif chord.quality in (_Q.DIMINISHED, _Q.DIMINISHED_SEVENTH, _Q.HALF_DIMINISHED_SEVENTH):
            primary = (7, 0)
        elif chord.quality in _AUGMENTED_SIXTHS and chord.inversion == 0:
            primary = (6, -1)
        else:
            return None
        for target in _targets(key):
            candidate = cls(primary[0], chord.quality, chord.inversion, primary[1], target)
            if candidate.realize(key) == chord:
                return candidate
        return None


def _pools(key: Key) -> tuple[set[PitchName], set[PitchName]]:
    major = set(Key(key.tonic, Mode.MAJOR).scale.names())
    minor_key = Key(key.tonic, Mode.MINOR)
    minor = set(minor_key.scale.names())
    minor |= {minor_key.leading_tone, key.tonic.transpose(Interval.parse('M6'))}
    return major, minor


def _targets(key: Key) -> tuple[RomanNumeral, ...]:
    """Tonicizable diatonic triads, the dominant first."""
    if key.mode is Mode.MAJOR:
        return tuple(
            RomanNumeral(d, q)
            for d, q in ((5, _Q.MAJOR), (2, _Q.MINOR), (6, _Q.MINOR), (4, _Q.MAJOR), (3, _Q.MINOR))
        )
    return tuple(
        RomanNumeral(d, q)
        for d, q in ((5, _Q.MAJOR), (4, _Q.MINOR), (6, _Q.MAJOR), (3, _Q.MAJOR), (7, _Q.MAJOR))
    )
