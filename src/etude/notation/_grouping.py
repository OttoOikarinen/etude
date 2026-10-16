# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Rhythmic grouping for layout: onsets, beam groups and tuplet groups.

These functions look at one voice (a sequence of events) and know nothing
about geometry, so the rules can be tested on their own.
"""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction

from ..core import Duration, Meter, NoteValue, Tuplet
from .spec import Barline, Chord, Event, Rest

STEMLESS_LENGTH = Fraction(1, 4)
"""Time a stemless note (``duration=None``) occupies when events are aligned by onset."""

FLAG_COUNTS = {
    NoteValue.EIGHTH: 1,
    NoteValue.SIXTEENTH: 2,
    NoteValue.THIRTY_SECOND: 3,
    NoteValue.SIXTY_FOURTH: 4,
}
"""Number of flags (or beams) of each note value; longer values have none."""

DEFAULT_BEAT = Fraction(1, 4)
"""Beam grouping unit when a staff has no meter."""


def event_length(event: Event) -> Fraction:
    """Time an event occupies: barlines take none, stemless notes count as quarters."""
    if isinstance(event, Barline):
        return Fraction(0)
    if event.duration is None:
        return STEMLESS_LENGTH
    return event.duration.length


def onsets(events: Sequence[Event]) -> list[Fraction]:
    """Start time of every event, in whole notes from the beginning of the staff."""
    result: list[Fraction] = []
    time = Fraction(0)
    for event in events:
        result.append(time)
        time += event_length(event)
    return result


def flag_count(duration: Duration | None) -> int:
    if duration is None:
        return 0
    return FLAG_COUNTS.get(duration.value, 0)


def _beat_boundaries(meter: Meter | None) -> tuple[Fraction, list[Fraction]]:
    """Bar length and the start of every beat group within a bar."""
    if meter is None:
        return DEFAULT_BEAT, [Fraction(0)]
    starts = [Fraction(0)]
    for group in meter.groups[:-1]:
        starts.append(starts[-1] + Fraction(group, meter.beat_unit))
    return meter.bar_length, starts


def _group_id(time: Fraction, bar: Fraction, starts: Sequence[Fraction]) -> tuple[int, int]:
    index, within = divmod(time, bar)
    group = max(i for i, start in enumerate(starts) if start <= within)
    return int(index), group


def beam_groups(events: Sequence[Event], meter: Meter | None) -> list[list[int]]:
    """Indices of chords beamed together, following the meter's beat groups.

    Eighths and shorter are beamed within a beat group (``Meter.groups``;
    quarter-note beats without a meter). Rests, barlines and longer notes
    break beams. Groups of a single note are not returned: they get flags.
    """
    bar, starts = _beat_boundaries(meter)
    times = onsets(events)
    groups: list[list[int]] = []
    current: list[int] = []
    current_id: tuple[int, int] | None = None
    for index, event in enumerate(events):
        beamable = isinstance(event, Chord) and flag_count(event.duration) > 0
        group_id = _group_id(times[index], bar, starts) if beamable else None
        if not beamable or group_id != current_id:
            if len(current) > 1:
                groups.append(current)
            current = []
            current_id = group_id
        if beamable:
            current.append(index)
    if len(current) > 1:
        groups.append(current)
    return groups


def _tuplet_of(event: Event) -> Tuplet | None:
    if isinstance(event, Chord | Rest) and event.duration is not None:
        return event.duration.tuplet
    return None


def _written_length(event: Chord | Rest) -> Fraction:
    assert event.duration is not None
    return Duration(event.duration.value, event.duration.dots).length


def tuplet_groups(events: Sequence[Event]) -> list[tuple[Tuplet, list[int]]]:
    """Consecutive events that form one tuplet, such as three triplet eighths.

    A group closes once its written length reaches ``actual`` times its
    shortest written value (three eighths for an eighth-note triplet, or a
    quarter and an eighth), or when the ratio changes.
    """
    groups: list[tuple[Tuplet, list[int]]] = []
    current: list[int] = []
    current_tuplet: Tuplet | None = None
    written = Fraction(0)
    shortest = Fraction(0)
    for index, event in enumerate(events):
        tuplet = _tuplet_of(event)
        if tuplet != current_tuplet and current:
            # An unfinished group still gets its number.
            assert current_tuplet is not None
            groups.append((current_tuplet, current))
            current = []
        current_tuplet = tuplet
        if tuplet is None:
            continue
        assert isinstance(event, Chord | Rest)
        length = _written_length(event)
        if not current:
            written = Fraction(0)
            shortest = length
        current.append(index)
        written += length
        shortest = min(shortest, length)
        if written >= tuplet.actual * shortest:
            groups.append((tuplet, current))
            current = []
    if current:
        assert current_tuplet is not None
        groups.append((current_tuplet, current))
    return groups
