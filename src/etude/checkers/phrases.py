# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Short four-part phrases of chromatic harmony: chromatic chords, modulations, sequences.

Every phrase is a plan of Roman numerals voiced by :func:`.realize.realize` and
checker-clean: :func:`.voice_leading.check` finds no error in it with
:meth:`Phrase.context`. A :class:`Phrase` keeps its analysis, so exercises that
show it, ask about it or play it (the eye exercises now, ear training later)
read the numerals, keys, pivot and phrase break from it instead of analysing
the notes::

    phrase = chromatic_phrase('Ger+6', Key.parse('c'), random.Random(seed))
    phrase.voicings      # soprano, alto, tenor, bass of each chord
    phrase.focus         # index of the Ger+6
    phrase.readings[i]   # the numeral(s) of chord i and the key each is read in

**Chromatic chords** (:data:`CHROMATIC_CHORDS`, Kostka–Payne ch. 16–17, 21–23):
secondary dominants and leading-tone chords (``V/V``, ``V7/ii``, ``viio7/V``,
``viiø7/V`` …, in any inversion), mode mixture in major (``iv``, ``iio``,
``iiø7``, ``bIII``, ``bVI``, ``bVII``, ``viio7``), the Neapolitan sixth
(``N6``) and the augmented sixths (``It+6``, ``Fr+6``, ``Ger+6``; in major the
Ger+6 before a cadential six-four is spelled with ♭3̂ or ♯2̂ at random). Each
stands in a short phrase that prepares and resolves it as the books do: a
secondary function goes to its target (the target in first inversion after a
4/2), the Neapolitan to V, to Cad6/4–V or through vii°7/V, the Ger+6 to Cad6/4
and the It+6 and Fr+6 to V or Cad6/4.

**Modulations** (:func:`modulation`, K–P ch. 18–19 and 27; Aldwell–Schachter
ch. 27–28 and 31), all starting with tonic–dominant–tonic in the home key:

* *pivot chord* to a closely related key: the pivot is a chord diatonic in both
  keys, preferably a predominant of the new key (ii, IV; iv, VI, ii°6), and is
  followed at once by a chord the old key does not have (the new V, V7, V6/5 or
  vii°), so the pivot is the last chord before the first new-key accidental, as
  K–P teach to find it;
* *direct* (phrase) modulation: a cadence in the home key, then a phrase in the
  new key starting on its tonic, with a double bar between them;
* *common tone*: from a major tonic to a major key a third away (III, ♭III, VI,
  ♭VI), the shared note held in the soprano over the phrase break;
* *enharmonic*: the home key's vii°7 respelled as the vii°7 of a minor key a minor
  third or tritone away, or the Ger+6 respelled as the V7 of ♭II.

**Sequences** (:func:`sequence`, K–P ch. 15 and 17; A–S ch. 17 and 24):
descending fifths (diatonic, and as a chain of secondary dominant sevenths), the
descending 5–6 (I–V6–vi–iii6–IV–I6: descending thirds) and the ascending 5–6
(I–vi6–ii–vii°6–iii).
"""

from __future__ import annotations

import random
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from itertools import pairwise

from ..core import Chord, Interval, Pitch, PitchName, Quality, RomanNumeral
from ..core.chord import ChordQuality
from ..core.scale import Key, Mode
from .realize import RealisationError, Voicing, realize
from .voice_leading import Context, Ranges, alteration

VARIANTS = 3
"""Phrases a generator writes for one request (chord or modulation, and key): a question
draws one with its ``rng``, and the plan and voicing of each are fixed and cached, so
generating many questions stays fast. Keys bring the variety."""

_ATTEMPTS = 12
"""Plans a generator tries (its random choices made again) before it gives up."""
_BASS_LINES = 8
"""Bass lines the voicer tries per plan: a plan that fails with these rarely succeeds."""


class ChromaticFamily(Enum):
    SECONDARY = 'secondary'
    """Secondary (applied) dominants and leading-tone chords."""
    MIXTURE = 'mixture'
    """Chords borrowed from the parallel minor in a major key."""
    NEAPOLITAN = 'neapolitan'
    AUGMENTED_SIXTH = 'augmented-sixth'


class Technique(Enum):
    PIVOT = 'pivot'
    DIRECT = 'direct'
    COMMON_TONE = 'common-tone'
    ENHARMONIC_DIMINISHED = 'enharmonic-dim7'
    """The vii°7 respelled as the vii°7 of another key."""
    ENHARMONIC_GERMAN = 'enharmonic-ger6'
    """The Ger+6 respelled as V7 of ♭II."""


class SequenceKind(Enum):
    DESCENDING_FIFTHS = 'descending-fifths'
    SECONDARY_DOMINANTS = 'secondary-dominants'
    """Descending fifths as a chain of secondary dominant sevenths."""
    DESCENDING_FIVE_SIX = 'descending-5-6'
    ASCENDING_FIVE_SIX = 'ascending-5-6'


# Phrases ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Reading:
    """A Roman numeral read in a key: one level of the analysis of a chord."""

    numeral: RomanNumeral
    key: Key

    @property
    def chord(self) -> Chord:
        return self.numeral.realize(self.key)


@dataclass(frozen=True, slots=True)
class Phrase:
    """A voiced phrase with its analysis.

    ``readings`` holds one reading per chord, or two for a pivot chord (old key
    first). The chord is spelled as its last reading: an enharmonic pivot is written
    as it resolves in the new key.
    """

    key: Key
    """The home key."""
    readings: tuple[tuple[Reading, ...], ...]
    voicings: tuple[Voicing, ...]
    new_key: Key | None = None
    """The key a modulation ends in."""
    pivot: int | None = None
    """Index of the pivot chord (pivot-chord and enharmonic modulations)."""
    focus: int | None = None
    """Index of the chord a chromatic-chord phrase is about."""
    breaks: tuple[int, ...] = field(default=())
    """Chords after which a phrase ends (the double bar of a direct modulation)."""

    @property
    def chords(self) -> tuple[Chord, ...]:
        return tuple(r[-1].chord for r in self.readings)

    @property
    def keys(self) -> tuple[Key, ...]:
        """The key each chord functions in (:attr:`.voice_leading.Context.keys`)."""
        return tuple(r[-1].numeral.tonicized_key(r[-1].key) for r in self.readings)

    def context(self, ranges: Ranges | None = None) -> Context:
        """The checker's context for these chords."""
        return Context(self.key, self.chords, ranges or Ranges(), keys=self.keys)


def _numeral(text: str) -> RomanNumeral:
    return RomanNumeral.parse(text)


@lru_cache(maxsize=4096)
def _voiced(
    plan: tuple[tuple[str, Key], ...],
    home: Key,
    variant: int,
    soprano: tuple[tuple[int, str], ...],
) -> tuple[Voicing, ...]:
    """The cached realisation of a plan of (numeral, key) pairs; ``soprano`` pins the
    top voice of some chords to a pitch (index, pitch text)."""
    rng = random.Random(variant)
    numerals = [_numeral(text) for text, _key in plan]
    keys = [key for _text, key in plan]
    tops: list[Pitch | None] = [None] * len(plan)
    for index, pitch in soprano:
        tops[index] = Pitch.parse(pitch)
    return realize(
        numerals, home, rng, keys=keys, soprano=tops if soprano else None, attempts=_BASS_LINES
    )


def bass_moves(before: Chord, after: Chord) -> bool:
    """The bass can go from one chord to the next by a chromatic step or by a leap of at
    most a sixth that is not augmented. Plans whose bass would need an augmented second
    or a seventh (C–D♯) are not voiced: the voicer would fail on them."""
    if before.bass.letter == after.bass.letter:
        return True
    low = before.bass.at(4)
    for octave in (3, 4, 5):
        other = after.bass.at(octave)
        a, b = sorted((low, other), key=lambda p: p.diatonic_index)
        if not 0 < b.diatonic_index - a.diatonic_index <= 5:
            continue
        try:
            interval = Interval.between(a, b)
        except ValueError:
            continue
        if interval.quality not in (Quality.AUGMENTED, Quality.DOUBLY_AUGMENTED):
            return True
    return False


def _moves(chords: Sequence[Chord]) -> bool:
    return all(bass_moves(a, b) for a, b in pairwise(chords))


def voiced(numerals: Sequence[str], key: Key, variant: int) -> tuple[Voicing, ...]:
    """A correct voicing of numeral texts in ``key``, one of :data:`VARIANTS` (cached).
    Raises :class:`RealisationError`."""
    return _voiced(tuple((text, key) for text in numerals), key, variant % VARIANTS, ())


def _plans_of(rng: random.Random, *request: object) -> Iterator[random.Random]:
    """Generators of the random choices of a phrase: the first is one of :data:`VARIANTS`
    drawn with ``rng``, the next ones (when a plan cannot be voiced) follow it. Each is
    seeded from ``request`` and its number, so the same request and variant always make
    the same phrase."""
    first = rng.randrange(VARIANTS)
    base = '|'.join(str(part) for part in request)
    for attempt in range(_ATTEMPTS):
        yield random.Random(f'{base}|{first + attempt}')


def _phrase(
    home: Key,
    readings: Sequence[Sequence[Reading]],
    rng: random.Random,
    *,
    soprano: tuple[tuple[int, str], ...] = (),
    new_key: Key | None = None,
    pivot: int | None = None,
    focus: int | None = None,
    breaks: tuple[int, ...] = (),
) -> Phrase:
    plan = tuple((str(r[-1].numeral), r[-1].key) for r in readings)
    voicings = _voiced(plan, home, rng.randrange(VARIANTS), soprano)
    return Phrase(home, tuple(tuple(r) for r in readings), voicings, new_key, pivot, focus, breaks)


# Chromatic chords ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChromaticChord:
    """A chromatic chord the exercises name and write, in one mode."""

    id: str
    """The numeral in root position, ASCII: ``'V7/V'``, ``'viio7/ii'``, ``'bVI'``,
    ``'N6'``, ``'Ger+6'``; with :attr:`mode` it makes an item id."""
    family: ChromaticFamily
    mode: Mode
    inversions: tuple[int, ...] = (0,)
    """Positions a phrase may use (the Neapolitan is always N6)."""

    @property
    def numeral(self) -> RomanNumeral:
        return _numeral(self.id)

    def at(self, inversion: int) -> RomanNumeral:
        """The numeral in an inversion."""
        n = self.numeral
        return RomanNumeral(n.degree, n.quality, inversion, n.alter, n.secondary)


_TRIAD = (0, 1)
_SEVENTH = (0, 1, 2, 3)
_LEADING_SEVENTH = (0, 1, 2)
"""A leading-tone seventh in 4/2 has the seventh (♭6̂ of the target) in the bass, which
must fall to 5̂ of the target, a six-four: left out."""
_S = ChromaticFamily.SECONDARY
_M = ChromaticFamily.MIXTURE
_N = ChromaticFamily.NEAPOLITAN
_A = ChromaticFamily.AUGMENTED_SIXTH
_MAJ = Mode.MAJOR
_MIN = Mode.MINOR

CHROMATIC_CHORDS = (
    # Secondary functions, the dominant's first (K–P ch. 16–17).
    ChromaticChord('V/V', _S, _MAJ, _TRIAD),
    ChromaticChord('V7/V', _S, _MAJ, _SEVENTH),
    ChromaticChord('viio7/V', _S, _MAJ, _LEADING_SEVENTH),
    ChromaticChord('viiø7/V', _S, _MAJ, _LEADING_SEVENTH),
    ChromaticChord('V/ii', _S, _MAJ, _TRIAD),
    ChromaticChord('V7/ii', _S, _MAJ, _SEVENTH),
    ChromaticChord('viio7/ii', _S, _MAJ, _LEADING_SEVENTH),
    ChromaticChord('V/vi', _S, _MAJ, _TRIAD),
    ChromaticChord('V7/vi', _S, _MAJ, _SEVENTH),
    ChromaticChord('viio7/vi', _S, _MAJ, _LEADING_SEVENTH),
    ChromaticChord('V7/IV', _S, _MAJ, _SEVENTH),
    ChromaticChord('V/V', _S, _MIN, _TRIAD),
    ChromaticChord('V7/V', _S, _MIN, _SEVENTH),
    ChromaticChord('viio7/V', _S, _MIN, _LEADING_SEVENTH),
    ChromaticChord('V/iv', _S, _MIN, _TRIAD),
    ChromaticChord('V7/iv', _S, _MIN, _SEVENTH),
    ChromaticChord('viio7/iv', _S, _MIN, _LEADING_SEVENTH),
    ChromaticChord('V7/VI', _S, _MIN, _SEVENTH),
    # Mode mixture in major (K–P ch. 21).
    ChromaticChord('iv', _M, _MAJ, _TRIAD),
    ChromaticChord('iio', _M, _MAJ, (1,)),
    ChromaticChord('iiø7', _M, _MAJ, (0, 1, 2)),
    ChromaticChord('bVI', _M, _MAJ),
    ChromaticChord('bIII', _M, _MAJ),
    ChromaticChord('bVII', _M, _MAJ),
    ChromaticChord('viio7', _M, _MAJ, _LEADING_SEVENTH),
    # The Neapolitan sixth (K–P ch. 22).
    ChromaticChord('N6', _N, _MAJ, (1,)),
    ChromaticChord('N6', _N, _MIN, (1,)),
    # Augmented sixth chords (K–P ch. 23).
    ChromaticChord('It+6', _A, _MAJ),
    ChromaticChord('Fr+6', _A, _MAJ),
    ChromaticChord('Ger+6', _A, _MAJ),
    ChromaticChord('It+6', _A, _MIN),
    ChromaticChord('Fr+6', _A, _MIN),
    ChromaticChord('Ger+6', _A, _MIN),
)
"""In teaching order: secondary dominants, mixture, the Neapolitan, augmented sixths.
V/III and V/VI in minor are left out: they are the diatonic VII and III."""


def chromatic_chord(id: str, mode: Mode) -> ChromaticChord:
    """The chord of :data:`CHROMATIC_CHORDS` with this id and mode."""
    for chord in CHROMATIC_CHORDS:
        if chord.id == id and chord.mode is mode:
            return chord
    raise ValueError(f'not a chromatic chord: {id!r} in {mode.value}')


def _tonic(mode: Mode) -> str:
    return 'I' if mode is Mode.MAJOR else 'i'


def _plans(chord: ChromaticChord, inversion: int) -> list[tuple[list[str], int]]:
    """Plans of numerals (with the chord at the returned index) that prepare and resolve
    the chord in ``inversion``."""
    tonic = _tonic(chord.mode)
    numeral = chord.at(inversion)
    text = str(numeral)
    dominant = ['V', tonic]
    if chord.family is _S:
        target = numeral.secondary
        assert target is not None
        goal = str(target) + ('6' if _resolves_to_sixth(numeral) else '')
        after = {
            'V': [tonic],
            'ii': ['V', tonic],
            'vi': ['ii6', 'V', tonic],
            'IV': ['V', tonic],
            'iv': ['V', tonic],
            'VI': ['iio6', 'V', tonic],
        }[str(target)]
        plans = [([tonic, text, goal, *after], 1)]
        if str(target) == 'V':
            plans.append(([tonic, 'IV' if chord.mode is _MAJ else 'iv', text, goal, *after], 2))
            # The six-four holds a seventh over (V7/V–Cad6/4); in major the E♭ of
            # vii°7/V would have to rise to E♮, so it goes to V directly.
            if numeral.inversion < 3 and (numeral.is_upper or chord.mode is _MIN):
                plans.append(([tonic, text, 'Cad64', 'V', tonic], 1))
        return plans
    if chord.family is _M:
        base = chord.id
        return {
            'iv': [([tonic, text, *dominant], 1), ([tonic, text, tonic], 1)],
            'iio': [([tonic, text, *dominant], 1)],
            'iiø7': [([tonic, text, *dominant], 1)],
            'bVI': [([tonic, text, *dominant], 1), ([tonic, text, 'iv', *dominant], 1)],
            'bIII': [([tonic, text, 'bVI', *dominant], 1), ([tonic, text, 'iv', *dominant], 1)],
            'bVII': [([tonic, text, 'bVI', *dominant], 1)],
            'viio7': [
                ([tonic, text, tonic + ('6' if _resolves_to_sixth(numeral) else '')], 1),
                ([tonic, 'IV', text, tonic + ('6' if _resolves_to_sixth(numeral) else '')], 2),
            ],
        }[base]
    if chord.family is _N:
        return [
            ([tonic, text, *dominant], 1),
            ([tonic, text, 'Cad64', *dominant], 1),
            ([tonic, 'iv', text, *dominant], 2),
            ([tonic, text, 'viio7/V', *dominant], 1),
        ]
    # Augmented sixths: the Ger+6 through the cadential six-four, the others either way.
    predominant = 'iv6'
    if chord.id == 'Ger+6':
        texts = [text]
        if chord.mode is _MAJ:
            texts.append(str(_numeral('Ger+6(#2)')))
        return [
            plan
            for spelled in texts
            for plan in (
                ([tonic, spelled, 'Cad64', *dominant], 1),
                ([tonic, predominant, spelled, 'Cad64', *dominant], 2),
            )
        ]
    return [
        ([tonic, text, *dominant], 1),
        ([tonic, predominant, text, *dominant], 2),
        ([tonic, text, 'Cad64', *dominant], 1),
    ]


def _resolves_to_sixth(numeral: RomanNumeral) -> bool:
    """The chord of resolution is in first inversion: after a V4/2 (the seventh falls to
    the third), and after a leading-tone seventh in 6/5 or 4/3 (K–P ch. 14: vii°6/5–I
    would give unequal fifths d5–P5 with the bass, and the bass of vii°4/3 falls to 3̂)."""
    if numeral.degree == 7:
        return numeral.inversion in (1, 2)
    return numeral.inversion == 3


def chromatic_phrase(
    chord: ChromaticChord | str, key: Key, rng: random.Random, *, inversion: int | None = None
) -> Phrase:
    """A phrase in ``key`` that prepares and resolves ``chord`` (an id is read in the
    key's mode), at :attr:`Phrase.focus`. The inversion is one of the chord's
    :attr:`~ChromaticChord.inversions`, chosen with ``rng`` unless given.

    Raises :class:`ValueError` for a chord of another mode and
    :class:`RealisationError` when no plan can be voiced (keys with many accidentals).
    """
    if isinstance(chord, str):
        chord = chromatic_chord(chord, key.mode)
    if chord.mode is not key.mode:
        raise ValueError(f'{chord.id} is a chord of {chord.mode.value} keys')
    failure: RealisationError | None = None
    for plan in _plans_of(rng, chord.id, chord.mode.value, key, inversion):
        position = plan.choice(chord.inversions) if inversion is None else inversion
        plans = [
            (texts, focus)
            for texts, focus in _plans(chord, position)
            if _moves([_numeral(t).realize(key) for t in texts])
        ] or _plans(chord, position)
        texts, focus = plan.choice(plans)
        readings = [(Reading(_numeral(t), key),) for t in texts]
        try:
            return _phrase(key, readings, plan, focus=focus)
        except RealisationError as error:
            failure = error
    assert failure is not None
    raise failure


# Keys ----------------------------------------------------------------------------------

_NUMERALS = ('I', 'II', 'III', 'IV', 'V', 'VI', 'VII')


def key_relation(home: Key, other: Key) -> str:
    """The Roman numeral of ``other``'s tonic in ``home``, as K–P name key relations: upper
    case for a major key, lower case for minor, with an accidental when the tonic is
    not in the home key's scale (``'V'``, ``'vi'``, ``'bVI'``, ``'#iv'``). ASCII; the
    exercises print ``♭`` and ``♯``."""
    degree = (other.tonic.letter - home.tonic.letter) % 7
    scale = home.degree(degree + 1)
    alter = other.tonic.alter - scale.alter
    numeral = _NUMERALS[degree]
    if other.mode is Mode.MINOR:
        numeral = numeral.lower()
    return ('#' * alter if alter > 0 else 'b' * -alter) + numeral


CLOSELY_RELATED = {
    Mode.MAJOR: ('V', 'IV', 'vi', 'ii', 'iii'),
    Mode.MINOR: ('III', 'v', 'iv', 'VI', 'VII'),
}
"""Relations of the closely related keys (one accidental apart), in teaching order."""

COMMON_TONE = ('bVI', 'VI', 'bIII', 'III')
"""Major keys a third away that a common-tone modulation from a major tonic reaches."""


def related_key(home: Key, relation: str) -> Key:
    """The key in ``relation`` to ``home``: ``related_key(C major, 'vi')`` is A minor."""
    numeral = RomanNumeral.parse(relation)
    tonic = home.degree(numeral.degree)
    tonic = PitchName(tonic.letter, tonic.alter + numeral.alter)
    return Key(tonic, Mode.MAJOR if numeral.is_upper else Mode.MINOR)


@lru_cache(maxsize=64)
def enharmonic_keys(home: Key) -> tuple[Key, ...]:
    """The three minor keys whose vii°7 sounds like the home key's: in C, a, e♭ and f♯
    (the chord B–D–F–A♭ respelled G♯–B–D–F, D–F–A♭–C♭, E♯–G♯–B–D). Each key is
    spelled with the fewest accidentals."""
    leading = home.leading_tone
    found: list[Key] = []
    for step in ('m3', 'd5', 'd7'):
        tone = leading.transpose(Interval.parse(step))
        candidates: list[tuple[int, bool, Key]] = []
        for spelled in (tone, *tone.enharmonics(max_alter=2)):
            tonic = spelled.transpose(Interval.parse('m2'))
            if abs(tonic.alter) > 1:
                continue
            key = Key(tonic, Mode.MINOR)
            if not key.is_theoretical:
                candidates.append((abs(key.signature.fifths), spelled != tone, key))
        # The fewest accidentals; on a tie the chord's own spelling (D–F–A♭–C♭: e♭).
        candidates.sort(key=lambda c: (c[0], c[1]))
        found.append(candidates[0][2])
    return tuple(found)


def neapolitan_key(home: Key) -> Key:
    """♭II major, the key whose V7 sounds like the home key's Ger+6 (D♭ in C)."""
    return related_key(home, 'bII')


@lru_cache(maxsize=64)
def _diatonic_triads(key: Key) -> dict[Chord, str]:
    """Triads of the key's own chords (in minor with V, vii° and also v and VII), with
    their numerals."""
    found: dict[Chord, str] = {}
    for degree in range(1, 8):
        chord = key.triad(degree)
        numeral = RomanNumeral.analyze(chord, key)
        if numeral is not None:
            found.setdefault(chord, str(numeral))
    if key.mode is Mode.MINOR:
        for text in ('v', 'VII'):
            found.setdefault(_numeral(text).realize(key), text)
    return found


@lru_cache(maxsize=64)
def _strict_pool(key: Key) -> frozenset[PitchName]:
    """The notes of the key: major scale, or natural minor with the leading tone."""
    pool = set(key.scale.names())
    if key.mode is Mode.MINOR:
        pool.add(key.leading_tone)
    return frozenset(pool)


def _foreign(chord: Chord, key: Key) -> bool:
    return not set(chord.names()) <= _strict_pool(key)


# Modulations ---------------------------------------------------------------------------

_PIVOT_FUNCTIONS = {
    Mode.MAJOR: (('ii', 'IV'), ('vi',), ('I',)),
    Mode.MINOR: (('iv', 'VI', 'iio6'), ('i',)),
}
"""Pivot functions in the new key, by preference: predominants, then others."""


@lru_cache(maxsize=256)
def pivots(home: Key, new: Key) -> tuple[tuple[str, str], ...]:
    """Possible pivot chords from ``home`` to ``new``: (numeral in home, numeral in new),
    the most usual first (a predominant of the new key)."""
    old_triads = _diatonic_triads(home)
    for group in _PIVOT_FUNCTIONS[new.mode]:
        found = []
        for text in group:
            chord = _numeral(text).realize(new)
            root_position = chord.with_inversion(0)
            if root_position in old_triads:
                old = _numeral(old_triads[root_position])
                old = RomanNumeral(old.degree, old.quality, chord.inversion, old.alter)
                found.append((str(old), text))
        if found:
            return tuple(found)
    return ()


def _dominants(home: Key, new: Key) -> list[str]:
    """New-key dominants the old key does not have, to follow the pivot. The relative
    major of a minor key has none (all its notes are in the minor key): its V7 and the
    cadence establish it."""
    found = [t for t in _DOMINANTS if _foreign(_numeral(t).realize(new), home)]
    return found or ['V7']


_DOMINANTS = ('V', 'V7')
"""The dominants after a pivot: root position, so that V(7)–I is the authentic cadence
that confirms the new key. (V6/5 and vii° have no note V7 lacks, so they would mark no
other pivot.)"""


def pivot_is_marked(home: Key, new: Key) -> bool:
    """The chord after the pivot has a note the home key does not (every closely related
    key but the relative major of a minor key), so the pivot can be found as the last
    chord before it."""
    return any(_foreign(_numeral(t).realize(new), home) for t in _DOMINANTS)


def _opening(home: Key, rng: random.Random, *, ends_on_tonic: bool = True) -> list[str]:
    """Tonic, dominant (and tonic): the home key established."""
    tonic = _tonic(home.mode)
    dominant = rng.choice(('V', 'V7', 'V65', 'V6'))
    return [tonic, dominant, tonic] if ends_on_tonic else [tonic, dominant]


def modulation(home: Key, technique: Technique, target: Key | str, rng: random.Random) -> Phrase:
    """A phrase from ``home`` to ``target`` (a key, or a relation such as ``'V'``).

    Pivot-chord and direct modulations go to closely related keys, common-tone
    modulations from a major key to :data:`COMMON_TONE`, enharmonic ones through the
    vii°7 to :func:`enharmonic_keys` and through the Ger+6 to :func:`neapolitan_key`.
    Raises :class:`ValueError` for a target the technique does not reach and
    :class:`RealisationError` when the phrase cannot be voiced.
    """
    new = related_key(home, target) if isinstance(target, str) else target
    builders = {
        Technique.PIVOT: _pivot_modulation,
        Technique.DIRECT: _direct_modulation,
        Technique.COMMON_TONE: _common_tone_modulation,
        Technique.ENHARMONIC_DIMINISHED: _diminished_modulation,
        Technique.ENHARMONIC_GERMAN: _german_modulation,
    }
    failure: RealisationError | None = None
    for plan in _plans_of(rng, home, technique.value, new):
        try:
            return builders[technique](home, new, plan)
        except RealisationError as error:
            failure = error
    assert failure is not None
    raise failure


def _in(key: Key, texts: Sequence[str]) -> list[tuple[Reading, ...]]:
    return [(Reading(_numeral(t), key),) for t in texts]


def _pivot_modulation(home: Key, new: Key, rng: random.Random) -> Phrase:
    if key_relation(home, new) not in CLOSELY_RELATED[home.mode]:
        raise ValueError(f'{new} is not closely related to {home}')
    choices = pivots(home, new)
    if not choices:  # pragma: no cover - every closely related key has one
        raise ValueError(f'no pivot from {home} to {new}')
    combos = [
        (old, pivot, dominant)
        for old, pivot in choices
        for dominant in _dominants(home, new)
        if bass_moves(_numeral(pivot).realize(new), _numeral(dominant).realize(new))
    ]
    old, pivot, dominant = rng.choice(combos or [(*choices[0], _dominants(home, new)[0])])
    tonic = _tonic(home.mode)
    opening = _opening(home, rng, ends_on_tonic=old != tonic)
    readings = [
        *_in(home, opening),
        (Reading(_numeral(old), home), Reading(_numeral(pivot), new)),
        *_in(new, [dominant, _tonic(new.mode)]),
    ]
    return _phrase(home, readings, rng, new_key=new, pivot=len(opening))


def _cadence(key: Key, rng: random.Random) -> list[str]:
    """Predominant, dominant and tonic."""
    tonic = _tonic(key.mode)
    if key.mode is Mode.MAJOR:
        predominant = rng.choice(('IV', 'ii6', 'ii'))
    else:
        predominant = rng.choice(('iv', 'iio6'))
    return [predominant, rng.choice(('V', 'V7')), tonic]


def _direct_modulation(home: Key, new: Key, rng: random.Random) -> Phrase:
    if key_relation(home, new) not in CLOSELY_RELATED[home.mode]:
        raise ValueError(f'{new} is not closely related to {home}')
    old = [_tonic(home.mode), *_cadence(home, rng)]
    second = [_tonic(new.mode), *_cadence(new, rng)]
    readings = [*_in(home, old), *_in(new, second)]
    return _phrase(home, readings, rng, new_key=new, breaks=(len(old) - 1,))


def _common_tone_modulation(home: Key, new: Key, rng: random.Random) -> Phrase:
    if home.mode is not Mode.MAJOR or key_relation(home, new) not in COMMON_TONE:
        raise ValueError(f'no common-tone modulation from {home} to {new}')
    old_tonic = Chord(home.tonic, ChordQuality.MAJOR)
    new_tonic = Chord(new.tonic, ChordQuality.MAJOR)
    shared = sorted(set(old_tonic.names()) & set(new_tonic.names()), key=str)
    if not shared:  # pragma: no cover - keys a third away share a note
        raise ValueError(f'{home} and {new} share no tonic note')
    tone = shared[0]
    old = [_tonic(home.mode), *_cadence(home, rng)]
    second = ['I', *_cadence(new, rng)]
    octave = 5 if tone.at(5).midi <= 76 else 4
    pitch = str(tone.at(octave))
    readings = [*_in(home, old), *_in(new, second)]
    junction = len(old) - 1
    return _phrase(
        home,
        readings,
        rng,
        soprano=((junction, pitch), (junction + 1, pitch)),
        new_key=new,
        breaks=(junction,),
    )


def _respelled(old: RomanNumeral, home: Key, chord: Chord) -> RomanNumeral:
    """``old`` in the inversion whose bass sounds like ``chord``'s bass."""
    for inversion in range(old.quality.size):
        candidate = RomanNumeral(old.degree, old.quality, inversion, old.alter, old.secondary)
        if candidate.realize(home).bass.pitch_class == chord.bass.pitch_class:
            return candidate
    raise ValueError(f'{chord} is not a respelling of {old}')  # pragma: no cover


def _diminished_modulation(home: Key, new: Key, rng: random.Random) -> Phrase:
    if new not in enharmonic_keys(home):
        raise ValueError(f'the vii°7 of {home} is not the vii°7 of {new}')
    tonic = _tonic(home.mode)
    # vi (VI) lets the bass reach a new leading tone that lies an augmented second above
    # the bass of IV and ii6 (G major to E minor: C–D♯).
    pivot = RomanNumeral.parse('viio7')
    options = ('iv', 'iio6', 'VI') if home.mode is Mode.MINOR else ('IV', 'ii6', 'vi')
    predominant = rng.choice(
        [t for t in options if bass_moves(_numeral(t).realize(home), pivot.realize(new))] or options
    )
    old = _respelled(pivot, home, pivot.realize(new))
    ending = rng.choice((['i', 'V7', 'i'], ['i', 'iv', 'V', 'i'], ['i', 'iio6', 'V', 'i']))
    readings = [
        *_in(home, [tonic, predominant]),
        (Reading(old, home), Reading(pivot, new)),
        *_in(new, ending),
    ]
    return _phrase(home, readings, rng, new_key=new, pivot=2)


def _german_modulation(home: Key, new: Key, rng: random.Random) -> Phrase:
    if new != neapolitan_key(home):
        raise ValueError(f'the Ger+6 of {home} is not the V7 of {new}')
    tonic = _tonic(home.mode)
    pivot = RomanNumeral.parse('V7')
    old = _respelled(RomanNumeral.parse('Ger+6'), home, pivot.realize(new))
    ending = ['I', rng.choice(('IV', 'ii6')), 'V7', 'I']
    readings = [
        *_in(home, [tonic, 'iv6']),
        (Reading(old, home), Reading(pivot, new)),
        *_in(new, ending),
    ]
    return _phrase(home, readings, rng, new_key=new, pivot=2)


def modulation_targets(home: Key, technique: Technique) -> tuple[str, ...]:
    """The relations (``'V'``, ``'bVI'`` …) ``technique`` reaches from ``home``, or for the
    enharmonic ones the relations of :func:`enharmonic_keys` and ``'bII'``."""
    if technique in (Technique.PIVOT, Technique.DIRECT):
        return CLOSELY_RELATED[home.mode]
    if technique is Technique.COMMON_TONE:
        return COMMON_TONE if home.mode is Mode.MAJOR else ()
    if technique is Technique.ENHARMONIC_DIMINISHED:
        return tuple(key_relation(home, k) for k in enharmonic_keys(home))
    return ('bII',)


# Sequences -----------------------------------------------------------------------------

SEQUENCES: dict[SequenceKind, dict[Mode, tuple[str, ...]]] = {
    SequenceKind.DESCENDING_FIFTHS: {
        Mode.MAJOR: ('I', 'IV', 'viio', 'iii', 'vi', 'ii', 'V', 'I'),
        Mode.MINOR: ('i', 'iv', 'VII', 'III', 'VI', 'iio', 'V', 'i'),
    },
    SequenceKind.SECONDARY_DOMINANTS: {
        Mode.MAJOR: ('I', 'V7/vi', 'V7/ii', 'V7/V', 'V7', 'I'),
    },
    SequenceKind.DESCENDING_FIVE_SIX: {
        Mode.MAJOR: ('I', 'V6', 'vi', 'iii6', 'IV', 'I6', 'V', 'I'),
        Mode.MINOR: ('i', 'v6', 'VI', 'III6', 'iv', 'i6', 'V', 'i'),
    },
    SequenceKind.ASCENDING_FIVE_SIX: {
        Mode.MAJOR: ('I', 'vi6', 'ii', 'viio6', 'iii', 'IV', 'V', 'I'),
    },
}
"""The numerals of each sequence, per mode it is written in."""


def sequence(kind: SequenceKind, key: Key, rng: random.Random) -> Phrase:
    """The sequence in ``key``. Raises :class:`ValueError` when ``kind`` has no form in
    the key's mode and :class:`RealisationError` when it cannot be voiced."""
    texts = SEQUENCES[kind].get(key.mode)
    if texts is None:
        raise ValueError(f'no {kind.value} sequence in {key.mode.value}')
    failure: RealisationError | None = None
    for plan in _plans_of(rng, kind.value, key):
        try:
            return _phrase(key, _in(key, texts), plan)
        except RealisationError as error:
            failure = error
    assert failure is not None
    raise failure


def chromatic_tones(chord: Chord, key: Key) -> tuple[PitchName, ...]:
    """The chord's notes outside ``key`` (:func:`.voice_leading.alteration`)."""
    return tuple(n for n in chord.names() if alteration(n, key) != 0)
