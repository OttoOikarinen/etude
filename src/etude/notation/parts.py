# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Several voices on one or more staves: SATB on a grand staff, two-part counterpoint.

:func:`voices_figure` puts each voice's events on its staff (the first voice of a
staff in :attr:`StaffSpec.events` with stems up, the others in
:attr:`StaffSpec.voices` with stems down) and returns a :class:`StaffSpec` for
one staff or a braced :class:`SystemSpec`. :func:`event_index` says where an
event ended up in the staff's combined event numbering (hit regions,
``event_x``, :class:`Bracket`), which staff input needs to map clicks back to
voices and slots.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..core import KeySignature, Meter
from .spec import Bracket, Clef, Event, StaffSpec, SystemSpec


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
