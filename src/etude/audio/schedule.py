# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Turn a :class:`~etude.audio.spec.PlaybackSpec` into timed synthesizer events.

Pure and backend-free, so the timing maths is tested without a synthesizer.
Times are milliseconds relative to beat 0; count-in events have negative
times.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from . import metronome
from .spec import PlaybackNote, PlaybackSpec

MELODIC_CHANNEL = 0
PERCUSSION_CHANNEL = 9
"""General MIDI channel 10."""
CLICK_MS = 80.0
"""How long a metronome click is held."""
RELEASE_MS = 300.0
"""Time allowed after the last note-off for release tails before ``on_finished``."""


class EventKind(IntEnum):
    """Event types, in the order they are processed when they share a time."""

    NOTE_OFF = 0
    BEAT = 1
    NOTE_ON = 2
    FINISHED = 3


@dataclass(frozen=True, slots=True, order=True)
class ScheduledEvent:
    time_ms: float
    kind: EventKind
    channel: int = MELODIC_CHANNEL
    key: int = 0
    velocity: int = 0
    beat: int = 0


@dataclass(frozen=True, slots=True)
class Schedule:
    events: tuple[ScheduledEvent, ...]
    """Sorted by time; note-offs come before note-ons at the same time."""

    @property
    def start_ms(self) -> float:
        """Time of the earliest event or of beat 0, whichever is earlier."""
        return min([0.0, *(e.time_ms for e in self.events)])

    @property
    def end_ms(self) -> float:
        """Time of the ``FINISHED`` event."""
        return max((e.time_ms for e in self.events), default=0.0)


def _note_events(spec: PlaybackSpec, note: PlaybackNote) -> tuple[ScheduledEvent, ScheduledEvent]:
    channel = PERCUSSION_CHANNEL if note.percussion else MELODIC_CHANNEL
    on = spec.beats_to_ms(note.start)
    off = spec.beats_to_ms(note.start + note.length)
    return (
        ScheduledEvent(on, EventKind.NOTE_ON, channel, note.midi, note.velocity),
        ScheduledEvent(off, EventKind.NOTE_OFF, channel, note.midi),
    )


def build_schedule(
    spec: PlaybackSpec, *, click_ms: float = CLICK_MS, release_ms: float = RELEASE_MS
) -> Schedule:
    """Every note, metronome click, beat callback and the finish marker of ``spec``.

    Count-in beats always click; beats from 0 on click only when
    ``spec.click`` is set. Every beat gets a ``BEAT`` event for ``on_beat``.
    """
    events: list[ScheduledEvent] = []
    for note in spec.notes:
        events.extend(_note_events(spec, note))
    for beat in metronome.beats(spec.meter, spec.count_in, spec.length):
        time = spec.beats_to_ms(beat.start)
        events.append(ScheduledEvent(time, EventKind.BEAT, beat=beat.number))
        if beat.number < 0 or spec.click:
            key = metronome.ACCENT_KEY if beat.accent else metronome.CLICK_KEY
            velocity = metronome.ACCENT_VELOCITY if beat.accent else metronome.CLICK_VELOCITY
            events.append(
                ScheduledEvent(time, EventKind.NOTE_ON, PERCUSSION_CHANNEL, key, velocity)
            )
            events.append(
                ScheduledEvent(time + click_ms, EventKind.NOTE_OFF, PERCUSSION_CHANNEL, key)
            )
    last_off = max(
        (e.time_ms for e in events if e.kind is EventKind.NOTE_OFF),
        default=0.0,
    )
    events.append(ScheduledEvent(max(last_off, 0.0) + release_ms, EventKind.FINISHED))
    events.sort()
    return Schedule(tuple(events))


def to_ticks(time_ms: float, origin_tick: int, ticks_per_second: float = 1000.0) -> int:
    """Absolute sequencer tick of ``time_ms`` when beat 0 is at ``origin_tick``.

    Each event is rounded on its own, so rounding errors never accumulate.
    """
    return origin_tick + round(time_ms * ticks_per_second / 1000.0)
