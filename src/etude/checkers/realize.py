# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Correct four-part realisations of a chord progression: the project's SATB voicer.

Exercises need model answers (four-part writing, figured bass), correct
passages to break on purpose (spot the error) and chords to play. Use
:func:`realize` for all of them::

    import random
    from etude.checkers.realize import RealisationError, realize
    from etude.core import Key, PitchName

    key = Key.parse('G')
    try:
        chords = realize(
            ['I', 'IV', 'V7', 'I'],  # Roman numerals, RomanNumeral or Chord objects
            key,
            random.Random(seed),  # different seeds give different correct answers
            soprano=[None, None, None, PitchName.parse('G')],  # a PAC: tonic on top
        )
    except RealisationError:
        ...  # no correct voicing (e.g. an impossible soprano)
    soprano, alto, tenor, bass = chords[0]

:func:`bass_line` picks a singable bass for the chords' bass notes when none
is given (tendency tones in the bass resolve: V4/2 falls to I6, V6 rises to
I). Every chord is a voicing of chord tones within the voices' ranges, with
good spacing and doubling; the voicings are joined by the smoothest motion
that :func:`~etude.checkers.voice_leading.check` finds no error in (a dynamic
programme over the candidate voicings of each chord, whose rules only ever
look at one chord or two neighbours). ``rng`` adds a little noise to the
costs, so different seeds give different correct answers.

Chromatic chords are voiced like the others, in the key they are read in
(:func:`function_keys`: the tonicized key of ``V7/V``, the new key after a
modulation passed in ``keys``), with the doublings of Kostka–Payne and
Aldwell–Schachter: the Neapolitan sixth doubles its bass (the third), chromatic
tones are not doubled (a lowered root of ♭VI, ♭III or ♭VII is), and augmented
sixth chords are complete (the It+6 doubles the tonic). The checker's rules for
chromatic tones (:mod:`.voice_leading`) do the rest: the voicer only keeps
voicings without errors.
"""

from __future__ import annotations

import random
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from functools import lru_cache
from itertools import product

from ..core import Pitch, PitchName, RomanNumeral
from ..core.chord import Chord, ChordKind, ChordQuality
from ..core.interval import Interval, Quality
from ..core.scale import Key
from .voice_leading import (
    ALTO,
    BASS,
    MOTION_RULES,
    SOPRANO,
    TENOR,
    Context,
    Ranges,
    Rule,
    Severity,
    alteration,
    errors,
    scan,
)
from .voice_leading import _tones as tones_of

Voicing = tuple[Pitch, Pitch, Pitch, Pitch]
"""Soprano, alto, tenor and bass."""

MAX_CANDIDATES = 48
"""Voicings kept per chord, the cheapest first."""

_PAIR_RULES = MOTION_RULES | {Rule.INCOMPLETE_CHORD, Rule.WRONG_DOUBLING}
"""Rules whose outcome for a chord can depend on the chord before it."""


DEFAULT_ATTEMPTS = 24
"""Bass lines :func:`realize` tries before it gives up, when no bass is given."""

Soprano = Pitch | PitchName | Collection[PitchName] | None
"""A soprano constraint for one chord: a pitch exactly, a pitch name in any octave, a
set of pitch names (3̂ or 5̂ over the final tonic of an imperfect cadence), or free."""

Harmony = Chord | RomanNumeral | str
"""A chord, given as a spelled chord, a Roman numeral, or a numeral's text (``'V65'``)."""


class RealisationError(ValueError):
    """No correct voicing exists for the request (an impossible exercise)."""


Keys = Sequence[Key | None]
"""A key per chord; ``None`` for the main key."""


def _reading_key(key: Key, keys: Keys | None, index: int) -> Key:
    if keys is not None and index < len(keys):
        local = keys[index]
        if local is not None:
            return local
    return key


def chords_of(harmony: Sequence[Harmony], key: Key, keys: Keys | None = None) -> tuple[Chord, ...]:
    """The spelled chords of ``harmony``: numerals are realised in ``key``, or in their
    entry of ``keys`` (the new key after a modulation)."""
    result: list[Chord] = []
    for index, item in enumerate(harmony):
        if isinstance(item, str):
            item = RomanNumeral.parse(item)
        local = _reading_key(key, keys, index)
        result.append(item.realize(local) if isinstance(item, RomanNumeral) else item)
    return tuple(result)


def function_keys(
    harmony: Sequence[Harmony], key: Key, keys: Keys | None = None
) -> tuple[Key, ...]:
    """The key each chord functions in, for :attr:`.voice_leading.Context.keys`: the
    tonicized key of a secondary numeral (G major for ``V7/V`` in C), otherwise the key
    it is read in (``key``, or its entry of ``keys``). Spelled chords are read in that
    key as they are."""
    result: list[Key] = []
    for index, item in enumerate(harmony):
        if isinstance(item, str):
            item = RomanNumeral.parse(item)
        local = _reading_key(key, keys, index)
        result.append(item.tonicized_key(local) if isinstance(item, RomanNumeral) else local)
    return tuple(result)


def bass_line(
    harmony: Sequence[Chord], rng: random.Random, ranges: Ranges | None = None
) -> tuple[Pitch, ...]:
    """A bass for the chords: their bass notes, moving by small, singable intervals.

    Starts in the middle of the range; each next note is one of the nearest
    octaves of the chord's bass (never an augmented interval or more than a
    fifth away when a smaller move exists), chosen with ``rng``.
    """
    ranges = ranges or Ranges()
    low, high = ranges.of(BASS)
    line: list[Pitch] = []
    for chord in harmony:
        options = [
            chord.bass.at(octave)
            for octave in range(low.octave - 1, high.octave + 2)
            if low.midi + 2 <= chord.bass.at(octave).midi <= high.midi - 2
        ]
        if not options:
            options = [
                chord.bass.at(o)
                for o in range(low.octave - 1, high.octave + 2)
                if low.midi <= chord.bass.at(o).midi <= high.midi
            ]
        if not line:
            middle = (low.midi + high.midi) // 2 - 2
            options.sort(key=lambda p: abs(p.midi - middle))
            line.append(options[0] if len(options) == 1 else rng.choice(options[:2]))
            continue
        previous = line[-1]
        every = [
            chord.bass.at(o)
            for o in range(low.octave - 1, high.octave + 2)
            if low.midi <= chord.bass.at(o).midi <= high.midi
        ]
        resolution = _bass_resolution(harmony[len(line) - 1], chord, previous, every)
        if resolution is not None:
            line.append(resolution)
            continue
        singable = [p for p in options if _singable(previous, p)]
        # Near the edges of the range a singable note may lie outside the comfortable
        # middle (B2–E♯2 rather than the augmented fourth B2–E♯3).
        pool = singable or [p for p in every if _singable(previous, p)] or options
        pool.sort(key=lambda p: abs(p.midi - previous.midi))
        near = [p for p in pool if abs(p.midi - previous.midi) <= 7] or pool[:1]
        line.append(rng.choice(near))
    return tuple(line)


def _bass_resolution(
    before: Chord, after: Chord, previous: Pitch, options: Sequence[Pitch]
) -> Pitch | None:
    """The note a tendency tone in the bass must move to: a chordal seventh down by step
    (V4/2–I6), the third of a dominant up by step to the root a fourth above (V6–I),
    and any half step to the next bass note (the Phrygian iv6–V) rather than a leap of
    a major seventh. These may use the whole range, down to its lowest note."""
    for option in options:
        if (
            abs(option.diatonic_index - previous.diatonic_index) == 1
            and abs(option.midi - previous.midi) == 1
        ):
            return option
    tones = tones_of(before)
    direction = 0
    if before.quality.kind is ChordKind.SEVENTH and before.inversion == 3:
        direction = -1
    elif (
        before.inversion == 1
        and before.quality in (ChordQuality.MAJOR, ChordQuality.DOMINANT_SEVENTH)
        and after.root == tones[0].transpose(Interval.parse('P4'))
    ):
        direction = 1
    if not direction:
        return None
    for option in options:
        steps = option.diatonic_index - previous.diatonic_index
        semitones = option.midi - previous.midi
        if steps == direction and 1 <= semitones * direction <= 2:
            return option
    return None


def _singable(before: Pitch, after: Pitch) -> bool:
    if before.diatonic_index == after.diatonic_index:
        return before.midi == after.midi
    low, high = sorted((before, after), key=lambda p: p.diatonic_index)
    try:
        interval = Interval.between(low, high)
    except ValueError:
        return False
    return interval.quality not in (Quality.AUGMENTED, Quality.DOUBLY_AUGMENTED) and (
        interval.number <= 8
    )


@dataclass(frozen=True, slots=True)
class _Candidate:
    voicing: Voicing
    cost: float
    midi: tuple[int, int, int, int] = (0, 0, 0, 0)
    """The voicing's MIDI numbers, for :func:`_movement`."""


def realize(
    harmony: Sequence[Harmony],
    key: Key,
    rng: random.Random | None = None,
    *,
    bass: Sequence[Pitch] | None = None,
    soprano: Sequence[Soprano] | None = None,
    ranges: Ranges | None = None,
    attempts: int = DEFAULT_ATTEMPTS,
    complete: bool = False,
    keys: Keys | None = None,
) -> tuple[Voicing, ...]:
    """A correct four-part voicing (soprano, alto, tenor, bass) of every chord.

    ``harmony`` holds chords, Roman numerals or numeral texts, read in ``key``, or per
    chord in ``keys`` (a modulating phrase: the numerals after the pivot in the new
    key); each chord is checked in its :func:`function_keys`.
    ``bass`` fixes the bass notes (they must be the chords' bass notes); without
    it :func:`bass_line` picks one, and up to ``attempts`` bass lines are tried.
    ``soprano`` constrains the top voice per chord: a :class:`Pitch` exactly, a
    :class:`PitchName` in any octave, a set of pitch names (any of them), ``None``
    freely. ``rng`` varies the answer (a fixed seed when omitted). With
    ``complete`` every chord has all its tones (root-position seventh chords
    otherwise may drop their fifth), for questions that ask what a chord is.

    Doubling follows the textbook defaults as a preference: the root of a
    root-position triad, the bass of ii°6 and vii°6, of six-four chords and of the
    Neapolitan sixth, the root or fifth before the third elsewhere, the third of vi
    (VI) after V, and no chromatic tone.

    The result has no error under :func:`check` with the chords as harmony and
    :func:`function_keys` as the keys. Raises :class:`RealisationError` when no
    correct voicing exists, and :class:`ValueError` when ``bass``, ``soprano`` or
    ``keys`` do not have one entry per chord.
    """
    chords = chords_of(harmony, key, keys)
    if not chords:
        raise ValueError('nothing to realise')
    for name, given in (('bass', bass), ('soprano', soprano), ('keys', keys)):
        if given is not None and len(given) != len(chords):
            raise ValueError(f'{name} needs one entry per chord')
    local = function_keys(harmony, key, keys)
    rng = rng or random.Random(0)
    ranges = ranges or Ranges()
    tops = tuple(soprano) if soprano is not None else (None,) * len(chords)
    if bass is not None:
        return _realize(chords, key, local, tuple(bass), tops, rng, ranges, complete)
    failure: RealisationError | None = None
    for _attempt in range(max(1, attempts)):
        try:
            line = bass_line(chords, rng, ranges)
            return _realize(chords, key, local, line, tops, rng, ranges, complete)
        except RealisationError as error:
            failure = error
    assert failure is not None
    raise failure


def _fits(pitch: Pitch, constraint: Soprano) -> bool:
    if constraint is None:
        return True
    if isinstance(constraint, Pitch):
        return pitch == constraint
    if isinstance(constraint, PitchName):
        return pitch.name == constraint
    return pitch.name in constraint


def _realize(
    harmony: tuple[Chord, ...],
    key: Key,
    keys: tuple[Key, ...],
    bass: tuple[Pitch, ...],
    soprano: tuple[Soprano, ...],
    rng: random.Random,
    ranges: Ranges,
    complete: bool = False,
) -> tuple[Voicing, ...]:
    context = Context(key, harmony, ranges, keys=keys)
    layers: list[list[_Candidate]] = []
    for index, (chord, low, top) in enumerate(zip(harmony, bass, soprano, strict=True)):
        if low.name != chord.bass:
            raise RealisationError(f'{low} is not the bass of {chord}')
        tones = len(tones_of(chord))
        deceptive = index > 0 and _is_deceptive(harmony[index - 1], chord, keys[index - 1])
        candidates = [
            _Candidate(
                v,
                cost + rng.random() * 2.5 + (_deceptive_cost(chord, v) if deceptive else 0.0),
            )
            for v, cost in _voicings(chord, low, keys[index], ranges)
            if _fits(v[SOPRANO], top) and (not complete or len({p.name for p in v}) == tones)
        ]
        candidates.sort(key=lambda c: c.cost)
        if not candidates:
            raise RealisationError(f'no voicing of {chord} over {low}')
        layers.append(
            [
                _Candidate(
                    c.voicing,
                    c.cost,
                    (c.voicing[0].midi, c.voicing[1].midi, c.voicing[2].midi, c.voicing[3].midi),
                )
                for c in candidates[:MAX_CANDIDATES]
            ]
        )

    # Dynamic programme: best[i][j] = (cost, back pointer) of candidate j of chord i.
    best: list[list[tuple[float, int]]] = [[(c.cost, -1) for c in layers[0]]]
    for index in range(1, len(layers)):
        row: list[tuple[float, int]] = []
        previous_layer = layers[index - 1]
        pair_context = Context(
            key,
            (harmony[index - 1], harmony[index]),
            ranges,
            _PAIR_RULES,
            keys=(keys[index - 1], keys[index]),
        )
        for candidate in layers[index]:
            options = sorted(
                (
                    best[index - 1][k][0] + _movement(previous.midi, candidate.midi),
                    k,
                )
                for k, previous in enumerate(previous_layer)
                if best[index - 1][k][0] < float('inf')
            )
            chosen = (float('inf'), -1)
            for cost, k in options:
                found = scan((previous_layer[k].voicing, candidate.voicing), pair_context, first=1)
                if any(v.severity is Severity.ERROR and v.slot == 1 for v in found):
                    continue
                warnings = sum(1 for v in found if v.slot == 1)
                chosen = (cost + candidate.cost + 4.0 * warnings, k)
                break
            row.append(chosen)
        best.append(row)
    end = min(range(len(best[-1])), key=lambda j: best[-1][j][0])
    if best[-1][end][0] == float('inf'):
        raise RealisationError('the chords cannot be joined without errors over this bass')
    path: list[Voicing] = []
    j = end
    for index in range(len(layers) - 1, -1, -1):
        path.append(layers[index][j].voicing)
        j = best[index][j][1]
    result = tuple(reversed(path))
    remaining = errors(scan(result, context))
    if remaining:  # pragma: no cover - the programme checks every pair
        raise RealisationError(f'{remaining[0].rule.value} in chord {remaining[0].slot + 1}')
    return result


DOUBLING_COST = 4.0
"""Cost of doubling another chord tone than the textbook one (a preference, not a rule)."""


def _preferred_doubling(chord: Chord, key: Key) -> dict[int, float]:
    """Chord tone (0 root, 1 third, 2 fifth) → cost of doubling it, after Kostka–Payne
    and Aldwell–Schachter: the root of a root-position triad; the bass of a six-four
    chord (its fifth), of a diminished triad in first inversion (its third: ii°6,
    vii°6) and of the Neapolitan sixth (its third); otherwise the root or fifth before
    the third. Where the rules call for another doubling (the third of vi after V) the
    error-free alternatives win."""
    if chord.inversion == 1 and _is_neapolitan(chord, key):
        return {1: 0.0, 0: 2 * DOUBLING_COST, 2: DOUBLING_COST}
    if chord.inversion == 2:
        return {2: 0.0, 0: DOUBLING_COST, 1: DOUBLING_COST}
    if chord.inversion == 1 and chord.quality is ChordQuality.DIMINISHED:
        return {1: 0.0, 0: 2 * DOUBLING_COST, 2: DOUBLING_COST}
    if chord.inversion == 1:
        return {0: 0.0, 2: 0.3, 1: DOUBLING_COST * 0.7}
    return {0: 0.0, 2: DOUBLING_COST * 0.7, 1: DOUBLING_COST}


def _is_neapolitan(chord: Chord, key: Key) -> bool:
    """A major triad on the lowered second degree (♭II)."""
    return (
        chord.quality is ChordQuality.MAJOR
        and chord.root.letter == key.degree(2).letter
        and alteration(chord.root, key) < 0
    )


def _is_deceptive(before: Chord, chord: Chord, key: Key) -> bool:
    """V(7)–vi (VI) with vi in root position."""
    return (
        chord.inversion == 0
        and chord.quality.kind is ChordKind.TRIAD
        and chord.root == key.degree(6)
        and before.root == key.degree(5)
    )


def _deceptive_cost(chord: Chord, voicing: Voicing) -> float:
    """After V the third of vi (VI) is doubled: undo the usual preference for the root
    (and the out-of-context warning on a doubled third of a major triad)."""
    root, third = tones_of(chord)[:2]
    names = [p.name for p in voicing]
    cost = 0.0
    if names.count(third) > 1:
        cost -= DOUBLING_COST + (3.0 if chord.quality is ChordQuality.MAJOR else 0.0)
    if names.count(root) > 1:
        cost += DOUBLING_COST
    return cost


_INCOMPLETE_SEVENTH = {
    ChordQuality.HALF_DIMINISHED_SEVENTH: 6.0,
    ChordQuality.DIMINISHED_SEVENTH: 6.0,
    ChordQuality.MINOR_SEVENTH: 3.0,
}
"""Cost of a seventh chord without its fifth: fine for V7, but without its diminished
fifth a half-diminished seventh sounds like a minor seventh."""


def _doubling_cost(chord: Chord, voicing: Voicing, key: Key) -> float:
    names = tones_of(chord)
    counts = [sum(1 for p in voicing if p.name == name) for name in names]
    chromatic = sum(
        DOUBLING_COST
        for role, (name, count) in enumerate(zip(names, counts, strict=True))
        if count > 1
        and alteration(name, key) != 0
        and not (role == 0 and chord.inversion == 0 and chord.quality.kind is ChordKind.TRIAD)
    )
    return chromatic + _usual_doubling_cost(chord, counts, key)


def _usual_doubling_cost(chord: Chord, counts: list[int], key: Key) -> float:
    if chord.quality.kind is ChordKind.SEVENTH:
        # Complete seventh chords are the norm; a root-position one may drop its fifth
        # and double the root.
        if min(counts) >= 1:
            return 0.0
        cost = _INCOMPLETE_SEVENTH.get(chord.quality, 0.5)
        return cost if counts[0] > 1 else cost + DOUBLING_COST  # double the root
    if chord.quality.kind is not ChordKind.TRIAD:
        return 0.0
    costs = _preferred_doubling(chord, key)
    return sum(costs.get(role, 0.0) for role, count in enumerate(counts) if count > 1)


def _movement(before: tuple[int, ...], after: tuple[int, ...]) -> float:
    """Total motion of the upper voices in semitones (MIDI numbers of two voicings);
    leaps in inner voices weigh more."""
    soprano = abs(after[SOPRANO] - before[SOPRANO])
    alto = abs(after[ALTO] - before[ALTO])
    tenor = abs(after[TENOR] - before[TENOR])
    return float(soprano + alto + tenor + max(0, alto - 4) + max(0, tenor - 4))


def _voicings(chord: Chord, bass: Pitch, key: Key, ranges: Ranges) -> list[tuple[Voicing, float]]:
    return list(_voicings_cached(chord, bass, key, ranges))


@lru_cache(maxsize=512)
def _voicings_cached(
    chord: Chord, bass: Pitch, key: Key, ranges: Ranges
) -> tuple[tuple[Voicing, float], ...]:
    """Every error-free voicing of ``chord`` over ``bass`` with its cost (lower is better)."""
    names = tones_of(chord)
    pools = []
    for voice in (SOPRANO, ALTO, TENOR):
        low, high = ranges.of(voice)
        pools.append(
            [
                name.at(octave)
                for name in names
                for octave in range(low.octave - 1, high.octave + 2)
                if low.midi <= name.at(octave).midi <= high.midi
            ]
        )
    context = Context(key, (chord,), ranges)
    found: list[tuple[Voicing, float]] = []
    # A missing root, third or seventh is always an error (any tone of an augmented
    # sixth chord): skip such voicings before the (slower) checker sees them.
    if chord.quality.kind is ChordKind.AUGMENTED_SIXTH:
        required = set(names)
    else:
        required = {names[0], names[1], *names[3:4]}
    for soprano, alto, tenor in product(*pools):
        if not (soprano.midi >= alto.midi >= tenor.midi >= bass.midi):
            continue
        if soprano.midi - alto.midi > 12 or alto.midi - tenor.midi > 12:
            continue
        if not required <= {soprano.name, alto.name, tenor.name, bass.name}:
            continue
        voicing: Voicing = (soprano, alto, tenor, bass)
        violations = scan((voicing,), context)
        if errors(violations):
            continue
        cost = 3.0 * len(violations)
        cost += _doubling_cost(chord, voicing, key)
        if soprano.midi == alto.midi or alto.midi == tenor.midi or tenor.midi == bass.midi:
            cost += 2.0  # unisons weaken the texture
        # Keep the soprano in its comfortable middle, around C5.
        cost += abs(soprano.midi - 72) * 0.2
        found.append((voicing, cost))
    return tuple(found)
