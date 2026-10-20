# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared helpers of the harmony exercises. This module defines no exercise.

* Roman numerals and figures for display: :func:`roman_label`,
  :func:`numeral_base`, :func:`figure_text`, :data:`TRIAD_FIGURES`,
  :data:`SEVENTH_FIGURES`.
* Keys and the common settings: :func:`keys_within`, :func:`modes_setting`
  (``mode``: major, minor or both), :func:`limit_setting`
  (``max-accidentals``), :func:`key_from_signature`.
* Four-part figures and sound: :func:`satb_figure`, :func:`satb_voices`,
  :func:`satb_durations`, :func:`progression_playback`,
  :func:`playback_lengths`, and :func:`chord_of` to name the chord of a
  voicing.
* A four-part voicer, :func:`voicings` and :func:`voice_progression`. It is
  to be replaced by the checker-validated voicer of :mod:`etude.checkers`
  once that lands; the rules it follows are below.

Four-part writing follows Kostka & Payne, *Tonal Harmony* (ch. 5–7), with the
voice ranges of :class:`etude.checkers.voice_leading.Ranges`:

* No voice crossing, at most an octave between soprano and alto and between
  alto and tenor.
* Doubling: the root of a root-position triad; the root or fifth of a
  first-inversion major or minor triad, the third (the bass) of a
  first-inversion diminished triad; the bass (the fifth) of a six-four chord;
  never the leading tone or a chordal seventh. Seventh chords are complete,
  or leave out the fifth and double the root in root position.
* Progressions avoid parallel (and contrary) fifths and octaves, direct
  fifths and octaves in the outer voices reached by a soprano leap, voice
  overlap and augmented melodic intervals; the leading tone in the soprano
  rises to the tonic and chordal sevenths fall by step. The search keeps the
  upper voices close to the previous chord, as a harmony student would.
"""

from __future__ import annotations

import random
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from functools import cache
from itertools import permutations

from ...audio.spec import PlaybackNote, PlaybackSpec
from ...checkers.voice_leading import Ranges
from ...core import Chord, ChordKind, ChordQuality, Duration, KeySignature, Pitch, PitchName
from ...core.roman import RomanNumeral
from ...core.scale import Key, Mode
from ...notation.spec import Barline, BarStyle, Clef, Event, Head, Ink, StaffSpec, SystemSpec
from ...notation.spec import Chord as StaffChord
from ..base import ExerciseDefinition

Voicing = tuple[Pitch, Pitch, Pitch, Pitch]
"""Soprano, alto, tenor and bass, as in :class:`~etude.exercises.base.StaffInputAnswer`."""

_RANGES = Ranges()
MAX_ACCIDENTALS = 7

# Roman numerals -------------------------------------------------------------------------

_PRETTY_FIGURES = {'': '', '6': '6', '64': '6/4', '7': '7', '65': '6/5', '43': '4/3', '42': '4/2'}
TRIAD_FIGURES = ('53', '6', '64')
"""Item segments of triad inversions (``53`` is root position)."""
SEVENTH_FIGURES = ('7', '65', '43', '42')
"""Item segments of seventh-chord inversions."""


def figure_text(figure: str) -> str:
    """A figure as written after a numeral: ``'65'`` → ``'6/5'``, ``'53'`` → ``''``."""
    return _PRETTY_FIGURES.get('' if figure == '53' else figure, figure)


def roman_label(numeral: RomanNumeral) -> str:
    """Display form with slashed figures and quality signs, as Kostka–Payne print
    them: ``'V6/5'``, ``'vii°7'``, ``'iiø4/3'``, ``'IV'``, ``'V6/5/V'``, ``'♭II6'``."""
    if numeral.secondary is not None:
        primary = RomanNumeral(numeral.degree, numeral.quality, numeral.inversion, numeral.alter)
        return f'{roman_label(primary)}/{roman_label(numeral.secondary)}'
    symbol = numeral.symbol
    figure = numeral.figure
    if numeral.cadential or not figure or numeral.quality.kind is ChordKind.AUGMENTED_SIXTH:
        return symbol
    return symbol[: len(symbol) - len(figure)] + figure_text(figure)


def numeral_base(numeral: RomanNumeral) -> str:
    """The numeral without inversion figures, but with ``7`` for seventh chords:
    ``'V7'`` for V6/5, ``'vii°'`` for vii°6."""
    root = RomanNumeral(numeral.degree, numeral.quality, 0, numeral.alter)
    return root.symbol


# Keys ------------------------------------------------------------------------------------


def keys_within(limit: int, modes: Sequence[Mode]) -> list[Key]:
    """Keys with at most ``limit`` sharps or flats, per mode, in line-of-fifths order."""
    keys = []
    for mode in modes:
        for fifths in range(-MAX_ACCIDENTALS, MAX_ACCIDENTALS + 1):
            if abs(fifths) > limit:
                continue
            signature = KeySignature(fifths)
            tonic = signature.major_tonic if mode is Mode.MAJOR else signature.minor_tonic
            keys.append(Key(tonic, mode))
    return keys


def modes_setting(settings: Mapping[str, object], default: str = 'major') -> tuple[Mode, ...]:
    """The ``mode`` choice setting: ``'major'``, ``'minor'`` or ``'both'``."""
    choice = settings.get('mode', default)
    if choice == 'minor':
        return (Mode.MINOR,)
    if choice == 'both':
        return (Mode.MAJOR, Mode.MINOR)
    return (Mode.MAJOR,)


def limit_setting(settings: Mapping[str, object], default: int = 4) -> int:
    """The ``max-accidentals`` integer setting, clamped to 0–7."""
    value = settings.get('max-accidentals', default)
    return max(0, min(MAX_ACCIDENTALS, value if isinstance(value, int) else default))


def key_from_signature(signature: KeySignature | None, mode: Mode) -> Key:
    """The major or minor key of a signature (``None`` is C major or A minor), e.g. to
    read a question's key back from its figure."""
    signature = signature or KeySignature(0)
    tonic = signature.major_tonic if mode is Mode.MAJOR else signature.minor_tonic
    return Key(tonic, mode)


# Four-part voicings ----------------------------------------------------------------------


def _in_range(name: PitchName, low: Pitch, high: Pitch) -> list[Pitch]:
    return [p for p in (name.at(o) for o in range(1, 7)) if low.midi <= p.midi <= high.midi]


def doublings(chord: Chord, key: Key) -> list[tuple[int, float]]:
    """Chord-tone indices a triad may double, with a penalty (0 = the textbook choice)."""
    if chord.quality.size != 3:
        return []
    names = chord.names()
    diminished = chord.quality is ChordQuality.DIMINISHED
    if chord.inversion == 0:
        options = [(1, 0.0), (2, 3.0)] if diminished else [(0, 0.0), (2, 3.0), (1, 6.0)]
    elif chord.inversion == 1:
        options = [(1, 0.0), (2, 1.0)] if diminished else [(0, 0.0), (2, 0.5), (1, 3.0)]
    else:
        options = [(2, 0.0), (0, 4.0), (1, 5.0)]
    allowed = [(i, p) for i, p in options if names[i] != key.leading_tone]
    least = min(p for _, p in allowed)
    return [(i, p - least) for i, p in allowed]


@cache
def _voicings(
    chord: Chord,
    key: Key,
    bass: Pitch | None,
    extra: tuple[tuple[int, float], ...],
) -> tuple[tuple[Voicing, float], ...]:
    names = chord.names()
    basses = [bass] if bass is not None else _in_range(chord.bass, *_RANGES.bass)
    others = tuple(n for i, n in enumerate(names) if i != chord.inversion)
    tone_sets: list[tuple[tuple[PitchName, ...], float]] = []
    if chord.quality.size == 4:
        tone_sets.append((others, 0.0))
        if chord.inversion == 0 and names[0] != key.leading_tone:
            # Incomplete seventh chord: no fifth, doubled root.
            tone_sets.append(((names[0], names[1], names[3]), 6.0))
    else:
        penalties = dict(doublings(chord, key))
        penalties.update(extra)
        tone_sets.extend(((*others, names[i]), p) for i, p in sorted(penalties.items()))
        if chord.inversion == 0 and chord.quality is not ChordQuality.DIMINISHED:
            # Incomplete triad: tripled root and the third, no fifth.
            tone_sets.append(((names[0], names[0], names[1]), 7.0))
    found: list[tuple[Voicing, float]] = []
    for low in basses:
        for tones, penalty in tone_sets:
            for s_name, a_name, t_name in sorted(set(permutations(tones)), key=str):
                for s in _in_range(s_name, *_RANGES.soprano):
                    for a in _in_range(a_name, *_RANGES.alto):
                        if not (a.midi < s.midi <= a.midi + 12):
                            continue
                        for t in _in_range(t_name, *_RANGES.tenor):
                            if t.midi < a.midi <= t.midi + 12 and t.midi > low.midi:
                                spread = 1.0 if t.midi - low.midi > 19 else 0.0
                                found.append(((s, a, t, low), penalty + spread))
    return tuple(found)


def voicings(
    chord: Chord,
    key: Key,
    *,
    bass: Pitch | None = None,
    extra_doublings: Mapping[int, float] | None = None,
) -> list[tuple[Voicing, float]]:
    """Every four-part voicing of ``chord`` within the voice ranges, with its doubling
    penalty. ``bass`` fixes the bass pitch; ``extra_doublings`` allows (or prefers)
    further doublings, e.g. the third of vi after V."""
    extra = tuple(sorted((extra_doublings or {}).items()))
    return list(_voicings(chord, key, bass, extra))


def best_voicing(chord: Chord, key: Key, rng: random.Random) -> Voicing:
    """A textbook voicing of one chord (preferred doubling, any register)."""
    options = voicings(chord, key)
    least = min(p for _, p in options)
    return rng.choice([v for v, p in options if p == least])


def _augmented_motion(a: Pitch, b: Pitch) -> bool:
    steps = abs(b.diatonic_index - a.diatonic_index)
    semis = abs(b.midi - a.midi)
    base = (0, 2, 4, 5, 7, 9, 11)[steps % 7] + 12 * (steps // 7)
    return semis > base


@dataclass(frozen=True, slots=True)
class _Step:
    """What the tendency-tone rules need to know about two adjacent chords."""

    leading: PitchName | None
    """The leading tone when it must resolve (dominant to a chord containing the tonic)."""
    tonic: PitchName
    seventh: PitchName | None
    """The chordal seventh of the first chord, which must fall by step."""


@cache
def _step(prev_chord: Chord, next_chord: Chord, key: Key) -> _Step:
    leading = key.leading_tone
    names = prev_chord.names()
    dominant = prev_chord.root in (key.degree(5), leading) and leading in names
    resolves = dominant and key.tonic in next_chord.names()
    seventh = names[3] if prev_chord.quality.size == 4 else None
    return _Step(leading if resolves else None, key.tonic, seventh)


def motion_cost(
    prev: Voicing, nxt: Voicing, prev_chord: Chord, next_chord: Chord, key: Key
) -> float:
    """How far ``prev`` → ``nxt`` is from good four-part voice leading (0 is ideal)."""
    return _motion(prev, nxt, _step(prev_chord, next_chord, key))


def _motion(prev: Voicing, nxt: Voicing, step: _Step) -> float:
    pm = [p.midi for p in prev]
    nm = [p.midi for p in nxt]
    cost = 0.0
    for voice in range(3):
        leap = abs(nm[voice] - pm[voice])
        cost += leap
        if leap > 12:
            cost += 1000
        elif leap > 5:
            cost += (15 if voice == 0 else 20) * (leap - 5)
        if leap and _augmented_motion(prev[voice], nxt[voice]):
            cost += 1000
        elif not leap and prev[voice] != nxt[voice]:
            cost += 300  # an enharmonic change in one voice
    bass_leap = abs(nm[3] - pm[3])
    cost += 0.5 * bass_leap
    if bass_leap > 12:
        cost += 1000
    elif bass_leap > 7:
        cost += 3 * (bass_leap - 7)
    # Parallel and contrary fifths and octaves.
    for i in range(4):
        if pm[i] == nm[i]:
            continue
        for j in range(i + 1, 4):
            if pm[j] == nm[j]:
                continue
            before = (pm[i] - pm[j]) % 12
            if before in (0, 7) and before == (nm[i] - nm[j]) % 12:
                cost += 1000
    # Direct fifths and octaves in the outer voices with a soprano leap.
    s_move = nm[0] - pm[0]
    b_move = nm[3] - pm[3]
    if s_move * b_move > 0 and abs(s_move) > 2 and (nm[0] - nm[3]) % 12 in (0, 7):
        cost += 200
    # Overlap.
    for upper in range(3):
        lower = upper + 1
        if nm[lower] > pm[upper] or nm[upper] < pm[lower]:
            cost += 100
    # Tendency tones.
    if step.leading is not None:
        for voice in range(3):
            if prev[voice].name != step.leading:
                continue
            if nxt[voice].name != step.tonic:
                cost += 500 if voice == 0 else 25
            elif nm[voice] != pm[voice] + 1:
                cost += 500
    if step.seventh is not None:
        for voice in range(4):
            if prev[voice].name != step.seventh:
                continue
            steps = prev[voice].diatonic_index - nxt[voice].diatonic_index
            if not (steps == 1 and 1 <= pm[voice] - nm[voice] <= 2):
                cost += 500
    return cost


_BEAM = 14


def voice_progression(
    chords: Sequence[Chord],
    key: Key,
    rng: random.Random,
    *,
    soprano: Mapping[int, Collection[PitchName]] | None = None,
    extra_doublings: Mapping[int, Mapping[int, float]] | None = None,
) -> list[Voicing]:
    """Four-part voicings of ``chords`` with good voice leading.

    ``soprano`` restricts the soprano of some chords (chord index → allowed
    pitch names), e.g. the tonic over the final chord of a perfect authentic
    cadence. A beam search keeps the cheapest partial progressions; random
    noise on the costs varies the result from question to question.
    """
    soprano = soprano or {}
    extra_doublings = extra_doublings or {}
    target = 62 + rng.random() * 12  # a soprano register for this progression
    beam: list[tuple[float, list[Voicing]]] = [(0.0, [])]
    for index, chord in enumerate(chords):
        options = voicings(chord, key, extra_doublings=extra_doublings.get(index))
        allowed = soprano.get(index)
        if allowed is not None:
            options = [o for o in options if o[0][0].name in allowed]
        if not options:
            raise ValueError(f'no voicing of {chord} with soprano {allowed}')
        scored: list[tuple[float, list[Voicing]]] = []
        step = _step(chords[index - 1], chord, key) if index else None
        for voicing, penalty in options:
            noise = rng.random() * 2.0
            if index == 0:
                # Start in a comfortable, varied register: soprano near the middle of its range.
                centre = abs(voicing[0].midi - target) * 0.5
                scored.append((penalty + noise + centre, [voicing]))
                continue
            assert step is not None
            best = min(
                ((cost + _motion(path[-1], voicing, step), path) for cost, path in beam),
                key=lambda x: x[0],
            )
            scored.append((best[0] + penalty + noise, [*best[1], voicing]))
        scored.sort(key=lambda x: x[0])
        beam = scored[:_BEAM]
    return beam[0][1]


def progression_cost(chords: Sequence[Chord], voices: Sequence[Voicing], key: Key) -> float:
    """Total motion cost of a voiced progression (tests check it stays small)."""
    return sum(
        motion_cost(voices[i - 1], voices[i], chords[i - 1], chords[i], key)
        for i in range(1, len(voices))
    )


# Figures and playback ------------------------------------------------------------------


def satb_figure(
    voices: Sequence[Voicing],
    signature: KeySignature | None = None,
    *,
    durations: Sequence[Duration] = (),
    labels: Sequence[str | None] = (),
    highlight: Collection[int] = (),
    final_bar: bool = False,
    description: str | None = None,
) -> SystemSpec:
    """Four voices on a grand staff: soprano and alto on the treble staff, tenor
    and bass on the bass staff.

    * ``durations`` (one per chord) draws each staff as two voices with stems up
      and down, as in a chorale; without them each staff shows one stemless
      two-note chord per slot.
    * ``labels`` (one per chord, ``None`` for none) are written under the bass
      staff: Roman numerals, or figured-bass figures with lines separated by
      ``'\\n'``.
    * Chords whose index is in ``highlight`` are drawn in the accent colour, with
      their labels (the cadence of a phrase, the chord a question asked about).

    :func:`satb_voices` reads the voicings back.
    """

    def chord(i: int, voice: int, *, labelled: bool = False) -> StaffChord:
        ink = Ink.ACCENT if i in highlight else Ink.FOREGROUND
        pitches = (voices[i][voice],) if durations else (voices[i][voice + 1], voices[i][voice])
        return StaffChord(
            tuple(Head(p, ink=ink) for p in pitches),
            durations[i] if durations else None,
            label=(labels[i] if i < len(labels) else None) if labelled else None,
            ink=ink,
        )

    count = range(len(voices))
    if durations:
        ending: tuple[Event, ...] = (Barline(BarStyle.FINAL),) if final_bar else ()
        treble = StaffSpec(
            clef=Clef.TREBLE,
            key_signature=signature,
            events=(*(chord(i, 0) for i in count), *ending),
            voices=((*(chord(i, 1) for i in count), *ending),),
        )
        low = StaffSpec(
            clef=Clef.BASS,
            key_signature=signature,
            events=(*(chord(i, 2) for i in count), *ending),
            voices=((*(chord(i, 3, labelled=True) for i in count), *ending),),
        )
    else:
        ending = (Barline(BarStyle.FINAL),) if final_bar else ()
        treble = StaffSpec(
            clef=Clef.TREBLE,
            key_signature=signature,
            events=(*(chord(i, 0) for i in count), *ending),
        )
        low = StaffSpec(
            clef=Clef.BASS,
            key_signature=signature,
            events=(*(chord(i, 2, labelled=True) for i in count), *ending),
        )
    return SystemSpec(staves=(treble, low), description=description)


def satb_durations(figure: object) -> tuple[Duration, ...]:
    """The note values of a figure made by :func:`satb_figure` (empty if stemless)."""
    if not isinstance(figure, SystemSpec) or not figure.staves:
        return ()
    events = [e for e in figure.staves[0].events if isinstance(e, StaffChord)]
    found = tuple(e.duration for e in events if e.duration is not None)
    return found if len(found) == len(events) else ()


def satb_voices(figure: object) -> list[Voicing]:
    """The voicings of a figure made by :func:`satb_figure`, soprano first; empty for
    any other figure."""
    if not isinstance(figure, SystemSpec) or len(figure.staves) != 2:
        return []
    treble, low = figure.staves

    def notes(staff: StaffSpec) -> list[list[Pitch]]:
        lines = [staff.events, *staff.voices]
        columns = [[e for e in line if isinstance(e, StaffChord)] for line in lines]
        return [
            sorted((h.pitch for chord in column for h in chord.heads), reverse=True)
            for column in zip(*columns, strict=True)
        ]

    result = []
    for top, bottom in zip(notes(treble), notes(low), strict=True):
        s, a = top
        t, b = bottom
        result.append((s, a, t, b))
    return result


def progression_playback(
    voices: Sequence[Sequence[Pitch]], lengths: Sequence[Fraction] = (), tempo: float = 76.0
) -> PlaybackSpec:
    """Block chords one after another, ``lengths`` in beats (one beat each by default).

    Works for any number of voices per chord; :func:`playback_lengths`
    turns note values into lengths.
    """
    notes: list[PlaybackNote] = []
    start = Fraction(0)
    for i, voicing in enumerate(voices):
        length = lengths[i] if i < len(lengths) else Fraction(1)
        notes.extend(PlaybackNote(p.midi, start, length) for p in voicing)
        start += length
    return PlaybackSpec(tuple(notes), tempo=tempo)


def playback_lengths(durations: Sequence[Duration]) -> list[Fraction]:
    """Note values as playback lengths in beats (quarter notes)."""
    return [d.quarter_length for d in durations]


def chord_of(pitches: Sequence[Pitch], quality: ChordQuality | None = None) -> Chord:
    """The tertian chord spelled by ``pitches`` (lowest pitch = bass).

    A chord without its fifth (an incomplete V7 or a final tonic with a tripled
    root, both in root position) is read as the complete chord on its bass.
    """
    found = [c for c in Chord.identify(pitches) if c.quality.is_tertian]
    if quality is not None:
        found = [c for c in found if c.quality is quality] or found
    if found:
        return found[0]
    names = {p.name for p in pitches}
    bass = min(pitches).name
    for candidate in ChordQuality:
        if not candidate.is_tertian or (quality is not None and candidate is not quality):
            continue
        try:
            tones = Chord(bass, candidate).names()
        except ValueError:
            continue
        if names <= set(tones) and set(tones) - names == {tones[2]}:
            return Chord(bass, candidate)
    raise ValueError(f'no tertian chord in {pitches}')


EXERCISES: tuple[ExerciseDefinition, ...] = ()
