# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Several voices on one or more staves: SATB on a grand staff, two-part counterpoint.

:func:`voices_figure` puts each voice's events on its staff (the first voice of a
staff in :attr:`StaffSpec.events` with stems up, the others in
:attr:`StaffSpec.voices` with stems down) and returns a :class:`StaffSpec` for
one staff or a braced :class:`SystemSpec`. :func:`event_index` says where an
event ended up in the staff's combined event numbering (hit regions,
``event_x``, :class:`Bracket`), which staff input needs to map clicks back to
voices and slots. :func:`rhythm_line` writes one voice in its own rhythm: a rest,
notes split into tied notes where they cross a barline (fourth-species
syncopation), and the barlines.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from functools import lru_cache

from ..core import Duration, KeySignature, Meter, NoteValue
from .spec import (
    Barline,
    BarStyle,
    Bracket,
    Chord,
    Clef,
    Event,
    Ink,
    Rest,
    StaffSpec,
    SystemSpec,
)


def staff_voices(voice_staves: Sequence[int], staff: int) -> list[int]:
    """The voices written on ``staff``, top voice first."""
    return [v for v, s in enumerate(voice_staves) if s == staff]


def event_index(
    voice_staves: Sequence[int], lengths: Sequence[int], voice: int, event: int
) -> tuple[int, int]:
    """``(staff, combined index)`` of event ``event`` of ``voice``.

    ``lengths`` is the number of events of every voice. On a staff, the
    events of its first voice come first, then those of the next voice.
    """
    staff = voice_staves[voice]
    offset = sum(lengths[v] for v in staff_voices(voice_staves, staff) if v < voice)
    return staff, offset + event


def voices_figure(
    clefs: Sequence[Clef],
    voice_staves: Sequence[int],
    voices: Sequence[Sequence[Event]],
    *,
    key_signature: KeySignature | None = None,
    meter: Meter | None = None,
    brackets: Sequence[Sequence[Bracket]] = (),
    description: str | None = None,
    labels: Sequence[str] = (),
) -> StaffSpec | SystemSpec:
    """The voices (top first) on their staves.

    ``brackets`` are per staff, in the staff's combined numbering. ``labels``
    are staff names for a system (``'S'`` …); a single staff ignores them.
    """
    staves: list[StaffSpec] = []
    for staff, clef in enumerate(clefs):
        on_staff = [tuple(voices[v]) for v in staff_voices(voice_staves, staff)]
        staves.append(
            StaffSpec(
                clef=clef,
                key_signature=key_signature,
                meter=meter,
                events=on_staff[0] if on_staff else (),
                voices=tuple(on_staff[1:]),
                brackets=tuple(brackets[staff]) if staff < len(brackets) else (),
            )
        )
    if len(staves) == 1:
        only = staves[0]
        return StaffSpec(
            clef=only.clef,
            key_signature=only.key_signature,
            meter=only.meter,
            events=only.events,
            voices=only.voices,
            brackets=only.brackets,
            description=description,
        )
    return SystemSpec(staves=tuple(staves), description=description, labels=tuple(labels))


@lru_cache(maxsize=256)
def durations_of(length: Fraction) -> tuple[Duration, ...]:
    """Note values that add up to ``length`` (whole notes), longest first: one value,
    dotted if need be, or several to be tied (``5/8`` → half, eighth)."""
    if length <= 0:
        raise ValueError(f'not a length: {length}')
    for value in NoteValue:
        for dots in (0, 1):
            if Duration(value, dots).length == length:
                return (Duration(value, dots),)
    for value in NoteValue:
        if value.value < length:
            return (Duration(value), *durations_of(length - value.value))
    raise ValueError(f'no note values add up to {length}')  # pragma: no cover


@dataclass(frozen=True, slots=True)
class Line:
    """One voice's events from :func:`rhythm_line`."""

    events: tuple[Event, ...]
    starts: tuple[int, ...]
    """Index of each note's first event."""
    owners: tuple[int | None, ...]
    """The note of every event (``None`` for rests and barlines)."""


def rhythm_line(
    chords: Sequence[Chord],
    durations: Sequence[Duration],
    *,
    rest: Duration | None = None,
    bar: Fraction | None = None,
    final_bar: bool = False,
    rest_ink: Ink = Ink.FOREGROUND,
) -> Line:
    """A voice in its own rhythm: ``chords`` (their heads, ink and label) lasting
    ``durations``, after an optional ``rest``.

    With ``bar`` (a bar's length in whole notes) barlines are drawn, and a note
    that crosses one is split into notes tied over it; only its first part has the
    label. ``final_bar`` ends the line with a final barline.
    """
    if len(chords) != len(durations):
        raise ValueError('one duration per chord')
    events: list[Event] = []
    owners: list[int | None] = []
    starts: list[int] = []
    time = Fraction(0)

    def barline() -> None:
        if bar is not None and time and time % bar == 0:
            events.append(Barline())
            owners.append(None)

    if rest is not None:
        for piece in durations_of(rest.length):
            events.append(Rest(piece, ink=rest_ink))
            owners.append(None)
            time += piece.length
    for index, (chord, duration) in enumerate(zip(chords, durations, strict=True)):
        barline()
        end = time + duration.length
        parts: list[Fraction] = []
        cursor = time
        while cursor < end:
            stop = end if bar is None else min(end, (cursor // bar + 1) * bar)
            parts.append(stop - cursor)
            cursor = stop
        pieces = [d for length in parts for d in durations_of(length)]
        starts.append(len(events))
        for number, piece in enumerate(pieces):
            if number and bar is not None and time % bar == 0:
                events.append(Barline())
                owners.append(None)
            last = number == len(pieces) - 1
            events.append(
                replace(
                    chord,
                    duration=piece,
                    tie_to_next=chord.tie_to_next if last else True,
                    label=chord.label if number == 0 else None,
                )
            )
            owners.append(index)
            time += piece.length
    if final_bar:
        events.append(Barline(BarStyle.FINAL))
        owners.append(None)
    return Line(tuple(events), tuple(starts), tuple(owners))
