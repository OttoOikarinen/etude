# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Metronome beats, count-ins and click tracks.

A *beat* here is the felt pulse of a meter: every quarter in 4/4, every
dotted quarter in 6/8, and the 2+2+3 eighth-note groups of 7/8. Positions
are in quarter-note beats like everything else in :mod:`etude.audio.spec`.
Beat 0 is the first beat of the playback; count-in beats are negative.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from fractions import Fraction

from ..core import Meter
from .spec import PlaybackNote, PlaybackSpec

ACCENT_KEY = 76
"""GM percussion key for the first beat of a bar (high wood block)."""
CLICK_KEY = 77
"""GM percussion key for the other beats (low wood block)."""
ACCENT_VELOCITY = 115
CLICK_VELOCITY = 85
CLICK_LENGTH = Fraction(1, 4)
"""Written length of a click in beats; wood blocks ring out by themselves."""


@dataclass(frozen=True, slots=True)
class Beat:
    number: int
    """Beat number: negative during the count-in, 0 for the first beat of the playback."""
    start: Fraction
    """Position in quarter-note beats relative to beat 0."""
    accent: bool
    """The first beat of a bar."""


def bar_length(meter: Meter) -> Fraction:
    """Length of one bar in quarter-note beats."""
    return meter.bar_length * 4


def pulse_offsets(meter: Meter) -> tuple[Fraction, ...]:
    """Where the beats of one bar fall, in quarter-note beats from the barline.

    4/4 → (0, 1, 2, 3); 6/8 → (0, 3/2); 7/8 → (0, 1, 2).
    """
    unit = Fraction(4, meter.beat_unit)
    offsets: list[Fraction] = []
    position = Fraction(0)
    for group in meter.groups:
        offsets.append(position)
        position += group * unit
    return tuple(offsets)


def beats(meter: Meter | None, count_in: int, length: Fraction) -> tuple[Beat, ...]:
    """The beats of a playback: ``count_in`` beats before beat 0, then every beat
    that starts before ``length``.

    The playback is assumed to start on a downbeat; the count-in fills the
    preceding bars from their end, so a count-in shorter than a bar starts
    mid-bar like an upbeat. Without a meter every quarter is a beat and only
    the first count-in beat and beat 0 are accented.
    """
    if count_in < 0:
        raise ValueError('count-in cannot be negative')
    if meter is None:
        result = [Beat(n, Fraction(n), n in (-count_in, 0)) for n in range(-count_in, 0)]
        result.extend(Beat(n, Fraction(n), n == 0) for n in range(math.ceil(length)))
        return tuple(result)

    offsets = pulse_offsets(meter)
    bar = bar_length(meter)
    per_bar = len(offsets)

    def beat(number: int) -> Beat:
        bar_index, index = divmod(number, per_bar)
        return Beat(number, bar_index * bar + offsets[index], index == 0)

    result = [beat(n) for n in range(-count_in, 0)]
    number = 0
    while (b := beat(number)).start < length:
        result.append(b)
        number += 1
    return tuple(result)


def pulses_per_bar(meter: Meter) -> int:
    return len(meter.groups)


def click_note(beat: Beat, start: Fraction | None = None) -> PlaybackNote:
    """A wood-block click for ``beat`` (at ``start`` if given, else at the beat)."""
    return PlaybackNote(
        ACCENT_KEY if beat.accent else CLICK_KEY,
        beat.start if start is None else start,
        CLICK_LENGTH,
        ACCENT_VELOCITY if beat.accent else CLICK_VELOCITY,
        percussion=True,
    )


def count_in(meter: Meter, tempo: float, *, bars: int = 1) -> PlaybackSpec:
    """A playback that is only a count-in: ``bars`` bars of clicks before beat 0.

    Nothing sounds at beat 0 itself, so ``PlaybackHandle.started_at`` is the
    moment the learner should come in (start tapping or singing).
    """
    if bars < 1:
        raise ValueError('a count-in needs at least one bar')
    return PlaybackSpec((), tempo, count_in=bars * pulses_per_bar(meter), meter=meter)


def click_track(meter: Meter, tempo: float, *, bars: int) -> PlaybackSpec:
    """``bars`` bars of clicks written out as percussion notes from beat 0.

    Use it for metronome practice and latency calibration: the onset of
    every click is ``spec.beats_to_ms(note.start)`` after ``started_at``.
    """
    if bars < 1:
        raise ValueError('a click track needs at least one bar')
    notes = tuple(click_note(b) for b in beats(meter, 0, bars * bar_length(meter)))
    return PlaybackSpec(notes, tempo, meter=meter)


def with_metronome(
    spec: PlaybackSpec, meter: Meter, *, count_in_bars: int = 1, click: bool = False
) -> PlaybackSpec:
    """``spec`` with a count-in of ``count_in_bars`` bars of ``meter`` and, if
    ``click`` is set, the metronome running through it."""
    if count_in_bars < 0:
        raise ValueError('count-in cannot be negative')
    return replace(spec, meter=meter, count_in=count_in_bars * pulses_per_bar(meter), click=click)
