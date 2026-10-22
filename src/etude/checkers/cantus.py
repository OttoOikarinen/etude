# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Cantus firmi: Fux's own, one per mode, and new ones generated in any mode.

:data:`FUX` holds the cantus firmus Fux sets in each of his six modes in
*Gradus ad Parnassum* (1725; Mann's translation, *The Study of
Counterpoint*), the melodies of his two-voice figures 5–88. They are in the
public domain. :func:`generate` writes a new cantus firmus: 8–14 notes,
mostly stepwise with a few leaps that turn back, a single climax, beginning
on the final and ending 2̂–1̂, accepted only when
:func:`~etude.checkers.counterpoint.check_cantus` finds nothing wrong with
it. :func:`modal_keys` lists the transpositions of a mode within a number of
sharps or flats, and :func:`transpose` moves a cantus firmus to another final.
"""

from __future__ import annotations

import itertools
import random
from collections.abc import Sequence

from ..core import Interval, KeySignature, Pitch, PitchName, Scale, ScaleType
from .counterpoint import MODES, check_cantus

FUX: dict[ScaleType, tuple[Pitch, ...]] = {
    mode: tuple(Pitch.parse(n) for n in notes.split())
    for mode, notes in (
        (ScaleType.DORIAN, 'D4 F4 E4 D4 G4 F4 A4 G4 F4 E4 D4'),
        (ScaleType.PHRYGIAN, 'E4 C4 D4 C4 A3 A4 G4 E4 F4 E4'),
        (ScaleType.LYDIAN, 'F3 G3 A3 F3 D3 E3 F3 C4 A3 F3 G3 F3'),
        (ScaleType.MIXOLYDIAN, 'G3 C4 B3 G3 C4 E4 D4 G4 E4 C4 D4 B3 A3 G3'),
        (ScaleType.AEOLIAN, 'A3 C4 B3 D4 C4 E4 F4 E4 D4 C4 B3 A3'),
        (ScaleType.IONIAN, 'C4 E4 F4 G4 E4 A4 G4 E4 F4 E4 D4 C4'),
    )
}
"""Fux's cantus firmus of each mode, at his pitch (figures 5, 11, 13, 15, 22 and 44)."""

MIN_LENGTH = 8
MAX_LENGTH = 14

_FIFTHS = {
    ScaleType.LYDIAN: -1,
    ScaleType.IONIAN: 0,
    ScaleType.MIXOLYDIAN: 1,
    ScaleType.DORIAN: 2,
    ScaleType.AEOLIAN: 3,
    ScaleType.PHRYGIAN: 4,
}
"""Line-of-fifths position of each mode's final with no sharps or flats (F Lydian …)."""


def fux_mode(mode_type: ScaleType) -> Scale:
    """The mode on Fux's final (D Dorian, E Phrygian …)."""
    return Scale(PitchName.from_line_of_fifths(_FIFTHS[mode_type]), mode_type)


def signature(mode: Scale) -> KeySignature:
    """The key signature of a transposed mode: none for D Dorian, one flat for G Dorian."""
    return KeySignature(mode.tonic.line_of_fifths - _FIFTHS[mode.type])


def modal_keys(mode_type: ScaleType, max_accidentals: int) -> list[Scale]:
    """The mode on every final whose signature has at most ``max_accidentals`` sharps or
    flats, flats first."""
    if mode_type not in _FIFTHS:
        raise ValueError(f'not one of the six modes: {mode_type.value}')
    limit = max(0, min(7, max_accidentals))
    return [
        Scale(PitchName.from_line_of_fifths(_FIFTHS[mode_type] + fifths), mode_type)
        for fifths in range(-limit, limit + 1)
    ]


def transpose(
    cantus: Sequence[Pitch], interval: Interval, *, down: bool = False
) -> tuple[Pitch, ...]:
    return tuple(p.transpose(interval, down=down) for p in cantus)


def fux_cantus(mode: Scale, final: Pitch | None = None) -> tuple[Pitch, ...]:
    """Fux's cantus firmus of ``mode``'s type, moved to ``mode``'s final (to ``final``
    with its octave when given, otherwise to the nearest octave of Fux's pitch)."""
    original = FUX[mode.type]
    start = original[0]
    if final is None:
        candidates = [mode.tonic.at(octave) for octave in range(start.octave - 1, start.octave + 2)]
        final = min(candidates, key=lambda p: abs(p.midi - start.midi))
    if final.name != mode.tonic:
        raise ValueError(f'{final} is not the final of {mode}')
    up = start.diatonic_index <= final.diatonic_index
    low, high = (start, final) if up else (final, start)
    return transpose(original, Interval.between(low, high), down=not up)


def generate(
    mode: Scale,
    final: Pitch,
    rng: random.Random,
    *,
    length: int | None = None,
    attempts: int = 200,
) -> tuple[Pitch, ...]:
    """A new cantus firmus in ``mode`` beginning on ``final``.

    It has ``length`` notes (8–14, chosen with ``rng`` when omitted), stays
    within an octave, mostly moves by step with two to four leaps, reaches
    its single climax once in its middle part, ends 2̂–1̂, and passes
    :func:`~etude.checkers.counterpoint.check_cantus` without a warning.
    Raises :class:`ValueError` when ``final`` is not the mode's final.
    """
    if final.name != mode.tonic:
        raise ValueError(f'{final} is not the final of {mode}')
    if mode.type not in MODES:
        raise ValueError(f'not one of the six modes: {mode.type.value}')
    for _attempt in range(attempts):
        size = length if length is not None else rng.randint(MIN_LENGTH, MAX_LENGTH - 2)
        size = max(MIN_LENGTH, min(MAX_LENGTH, size))
        found = _attempt_line(mode, final, size, rng)
        if found is not None and not check_cantus(found, mode):
            return found
    return fux_cantus(mode, final)  # pragma: no cover - the search practically never fails


def _scale_pitches(mode: Scale, low: Pitch, high: Pitch) -> list[Pitch]:
    names = mode.names()
    return sorted(
        (
            name.at(octave)
            for name in names
            for octave in range(low.octave - 1, high.octave + 2)
            if low.midi <= name.at(octave).midi <= high.midi
        ),
        key=lambda p: p.midi,
    )


def _attempt_line(
    mode: Scale, final: Pitch, size: int, rng: random.Random
) -> tuple[Pitch, ...] | None:
    """One randomised depth-first search for a line with a given climax."""
    octave = Interval.parse('P8')
    fourth = Interval.parse('P4')
    lowest = final.transpose(fourth, down=True) if rng.random() < 0.3 else final
    pitches = _scale_pitches(mode, lowest, lowest.transpose(octave))  # within an octave
    above = [p for p in pitches if p.midi > final.midi + 2]
    climax = rng.choice(above[: max(1, len(above) - 1)] if len(above) > 2 else above)
    peak = rng.randint(max(2, size // 3), max(2, (size * 2) // 3))
    second = mode.degree(2)
    penultimate = next(p for p in pitches if p.name == second and p.midi > final.midi)
    line: list[Pitch] = [final]
    budget = [400]

    def allowed(previous: Pitch, pitch: Pitch, index: int) -> bool:
        steps = pitch.diatonic_index - previous.diatonic_index
        semitones = pitch.midi - previous.midi
        if steps == 0:
            return False
        size_ = abs(steps)
        if size_ in (5, 6) or (size_ > 4 and not (size_ == 7 and abs(semitones) == 12)):
            return False  # sixths and sevenths; fifths and octaves only when perfect
        if size_ == 4 and abs(semitones) != 7:
            return False
        if size_ == 3 and abs(semitones) != 5:
            return False  # the tritone
        if len(line) >= 2:
            before = previous.diatonic_index - line[-2].diatonic_index
            if abs(before) > 1 and (abs(steps) > 1 and (before > 0) == (steps > 0)):
                return False  # two leaps in one direction
            if abs(before) >= 3 and (before > 0) == (steps > 0):
                return False  # turn after a leap of a fourth or more
            if abs(before) > 1 and abs(steps) > 1:
                return False  # a leap is followed by a step
        if len(line) >= 3 and pitch == line[-2] and previous == line[-3]:
            return False  # a b a b
        if sum(1 for p in line if p == pitch) >= 3:
            return False
        if index == peak:
            return pitch == climax
        return pitch.midi < climax.midi

    def search(index: int) -> bool:
        budget[0] -= 1
        if budget[0] < 0:
            return False
        if index == size - 1:
            return allowed(line[-1], final, index) and _leaps_ok([*line, final])
        if index == size - 2:
            options = [penultimate]
        else:
            options = [p for p in pitches if allowed(line[-1], p, index)]
            rng.shuffle(options)
            options.sort(
                key=lambda p: (
                    abs(p.diatonic_index - line[-1].diatonic_index) > 1 and rng.random() < 0.75
                )
            )
        for pitch in options:
            if not allowed(line[-1], pitch, index):
                continue
            line.append(pitch)
            if search(index + 1):
                return True
            line.pop()
        return False

    if search(1):
        line.append(final)
        return tuple(line)
    return None


def _leaps_ok(line: Sequence[Pitch]) -> bool:
    leaps = sum(
        1 for a, b in itertools.pairwise(line) if abs(b.diatonic_index - a.diatonic_index) > 1
    )
    return 2 <= leaps <= 4
