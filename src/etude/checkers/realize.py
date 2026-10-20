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
"""

from __future__ import annotations

import random
from collections.abc import Sequence
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
    errors,
    scan,
)

Voicing = tuple[Pitch, Pitch, Pitch, Pitch]
"""Soprano, alto, tenor and bass."""

MAX_CANDIDATES = 48
"""Voicings kept per chord, the cheapest first."""

_PAIR_RULES = MOTION_RULES | {Rule.INCOMPLETE_CHORD, Rule.WRONG_DOUBLING}
"""Rules whose outcome for a chord can depend on the chord before it."""


DEFAULT_ATTEMPTS = 24
"""Bass lines :func:`realize` tries before it gives up, when no bass is given."""

Harmony = Chord | RomanNumeral | str
"""A chord, given as a spelled chord, a Roman numeral, or a numeral's text (``'V65'``)."""


class RealisationError(ValueError):
    """No correct voicing exists for the request (an impossible exercise)."""


def chords_of(harmony: Sequence[Harmony], key: Key) -> tuple[Chord, ...]:
    """The spelled chords of ``harmony`` in ``key`` (numerals are realised in it)."""
    result: list[Chord] = []
    for item in harmony:
        if isinstance(item, str):
            item = RomanNumeral.parse(item)
        result.append(item.realize(key) if isinstance(item, RomanNumeral) else item)
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
        pool = singable or options
        pool.sort(key=lambda p: abs(p.midi - previous.midi))
        near = [p for p in pool if abs(p.midi - previous.midi) <= 7] or pool[:1]
        line.append(rng.choice(near))
    return tuple(line)


def _bass_resolution(
    before: Chord, after: Chord, previous: Pitch, options: Sequence[Pitch]
) -> Pitch | None:
    """The note a tendency tone in the bass must move to: a chordal seventh down by step
    (V4/2–I6), the third of a dominant up by step to the root a fourth above (V6–I)."""
    tones = before.names()
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


def realize(
    harmony: Sequence[Harmony],
    key: Key,
    rng: random.Random | None = None,
    *,
    bass: Sequence[Pitch] | None = None,
    soprano: Sequence[Pitch | PitchName | None] | None = None,
    ranges: Ranges | None = None,
    attempts: int = DEFAULT_ATTEMPTS,
) -> tuple[Voicing, ...]:
    """A correct four-part voicing (soprano, alto, tenor, bass) of every chord.

    ``harmony`` holds chords, Roman numerals or numeral texts, read in ``key``.
    ``bass`` fixes the bass notes (they must be the chords' bass notes); without
    it :func:`bass_line` picks one, and up to ``attempts`` bass lines are tried.
    ``soprano`` constrains the top voice per chord: a :class:`Pitch` exactly, a
    :class:`PitchName` in any octave, ``None`` freely. ``rng`` varies the answer
    (a fixed seed when omitted).

    The result has no error under :func:`check` with the chords as harmony.
    Raises :class:`RealisationError` when no correct voicing exists, and
    :class:`ValueError` when ``bass`` or ``soprano`` do not have one entry per
    chord.
    """
    chords = chords_of(harmony, key)
    if not chords:
        raise ValueError('nothing to realise')
    for name, given in (('bass', bass), ('soprano', soprano)):
        if given is not None and len(given) != len(chords):
            raise ValueError(f'{name} needs one entry per chord')
    rng = rng or random.Random(0)
    ranges = ranges or Ranges()
    tops = tuple(soprano) if soprano is not None else (None,) * len(chords)
    if bass is not None:
        return _realize(chords, key, tuple(bass), tops, rng, ranges)
    failure: RealisationError | None = None
    for _attempt in range(max(1, attempts)):
        try:
            return _realize(chords, key, bass_line(chords, rng, ranges), tops, rng, ranges)
        except RealisationError as error:
            failure = error
    assert failure is not None
    raise failure


def _realize(
    harmony: tuple[Chord, ...],
    key: Key,
    bass: tuple[Pitch, ...],
    soprano: tuple[Pitch | PitchName | None, ...],
    rng: random.Random,
    ranges: Ranges,
) -> tuple[Voicing, ...]:
    context = Context(key, harmony, ranges)
    layers: list[list[_Candidate]] = []
    for chord, low, top in zip(harmony, bass, soprano, strict=True):
        if low.name != chord.bass:
            raise RealisationError(f'{low} is not the bass of {chord}')
        candidates = [
            _Candidate(v, cost + rng.random() * 2.5)
            for v, cost in _voicings(chord, low, key, ranges)
            if top is None
            or (v[SOPRANO] == top if isinstance(top, Pitch) else v[SOPRANO].name == top)
        ]
        candidates.sort(key=lambda c: c.cost)
        if not candidates:
            raise RealisationError(f'no voicing of {chord} over {low}')
        layers.append(candidates[:MAX_CANDIDATES])

    # Dynamic programme: best[i][j] = (cost, back pointer) of candidate j of chord i.
    best: list[list[tuple[float, int]]] = [[(c.cost, -1) for c in layers[0]]]
    for index in range(1, len(layers)):
        row: list[tuple[float, int]] = []
        previous_layer = layers[index - 1]
        pair_context = Context(key, (harmony[index - 1], harmony[index]), ranges, _PAIR_RULES)
        for candidate in layers[index]:
            options = sorted(
                (
                    best[index - 1][k][0] + _movement(previous.voicing, candidate.voicing),
                    k,
                )
                for k, previous in enumerate(previous_layer)
                if best[index - 1][k][0] < float('inf')
            )
            chosen = (float('inf'), -1)
            for cost, k in options:
                found = scan((previous_layer[k].voicing, candidate.voicing), pair_context)
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


def _movement(before: Voicing, after: Voicing) -> float:
    """Total motion of the upper voices in semitones; leaps in inner voices weigh more."""
    total = 0.0
    for voice in (SOPRANO, ALTO, TENOR):
        distance = abs(after[voice].midi - before[voice].midi)
        total += distance
        if voice != SOPRANO and distance > 4:
            total += distance - 4
    return total


def _voicings(chord: Chord, bass: Pitch, key: Key, ranges: Ranges) -> list[tuple[Voicing, float]]:
    return list(_voicings_cached(chord, bass, key, ranges))


@lru_cache(maxsize=512)
def _voicings_cached(
    chord: Chord, bass: Pitch, key: Key, ranges: Ranges
) -> tuple[tuple[Voicing, float], ...]:
    """Every error-free voicing of ``chord`` over ``bass`` with its cost (lower is better)."""
    names = chord.names()
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
    for soprano, alto, tenor in product(*pools):
        if not (soprano.midi >= alto.midi >= tenor.midi >= bass.midi):
            continue
        if soprano.midi - alto.midi > 12 or alto.midi - tenor.midi > 12:
            continue
        voicing: Voicing = (soprano, alto, tenor, bass)
        violations = scan((voicing,), context)
        if errors(violations):
            continue
        cost = 3.0 * len(violations)
        present = [p.name for p in voicing]
        if chord.inversion == 0 and present.count(chord.root) < 2:
            cost += 1.0  # root-position chords prefer a doubled root
        if soprano.midi == alto.midi or alto.midi == tenor.midi or tenor.midi == bass.midi:
            cost += 2.0  # unisons weaken the texture
        # Keep the soprano in its comfortable middle, around C5.
        cost += abs(soprano.midi - 72) * 0.2
        found.append((voicing, cost))
    return tuple(found)
