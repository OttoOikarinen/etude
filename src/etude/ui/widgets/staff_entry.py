# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the learner has written on a staff-input answer, without any GTK.

:class:`StaffEntry` is the state behind the staff input widget
(:mod:`etude.ui.widgets.staff_input`): one note per *slot*, a cursor (the
staff position that the arrow keys move and the letter keys jump from), the
accidental chosen with the ♯ ♮ ♭ toggles, and the figure that shows all of
it. Keeping it free of GObject lets tests check the mapping from clicks and
keys to pitches without a display.

Slots hold chords (``tuple[Pitch, ...]``), as the answer value does; the
level-1 exercises enter one note per slot. Several voices (SATB) will add a
voice index to the cursor.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

from ...core import KeySignature, Pitch
from ...core.pitch import Letter
from ...notation.spec import Chord, Clef, Event, Head, Ink, StaffSpec

MIN_POSITION = -7
"""Lowest staff position that can be entered: below the third ledger line."""
MAX_POSITION = 15
"""Highest staff position that can be entered: above the third ledger line."""
MIDDLE_LINE = 4


class Accidental(Enum):
    """The accidental toggles. ``NONE`` follows the key signature."""

    NONE = 'none'
    SHARP = 'sharp'
    NATURAL = 'natural'
    FLAT = 'flat'


Value = tuple[tuple[Pitch, ...], ...]
"""The answer value of :class:`~etude.exercises.base.StaffInputAnswer`."""


def clamp(position: int) -> int:
    return max(MIN_POSITION, min(MAX_POSITION, position))


def pitch_at(
    clef: Clef,
    position: int,
    accidental: Accidental = Accidental.NONE,
    key_signature: KeySignature | None = None,
) -> Pitch:
    """The pitch written at ``position`` with ``accidental`` under ``key_signature``."""
    natural = clef.pitch_at(position)
    match accidental:
        case Accidental.SHARP:
            alter = 1
        case Accidental.FLAT:
            alter = -1
        case Accidental.NATURAL:
            alter = 0
        case Accidental.NONE:
            alter = key_signature.alter_for(natural.letter) if key_signature else 0
    return Pitch(natural.letter, alter, natural.octave)


def accidental_for(pitch: Pitch, key_signature: KeySignature | None = None) -> Accidental:
    """The toggle that writes ``pitch``: ``NONE`` when the key signature already does."""
    implied = key_signature.alter_for(pitch.letter) if key_signature else 0
    if pitch.alter == implied:
        return Accidental.NONE
    return {1: Accidental.SHARP, -1: Accidental.FLAT, 0: Accidental.NATURAL}.get(
        pitch.alter, Accidental.NONE
    )


def nearest_position(clef: Clef, letter: Letter, around: int) -> int:
    """The staff position with ``letter`` closest to ``around`` (at most three steps away),
    kept within the positions that can be entered."""
    step = (letter - clef.pitch_at(around).letter) % 7
    position = around + step if step <= 3 else around + step - 7
    if position > MAX_POSITION:
        position -= 7
    if position < MIN_POSITION:
        position += 7
    return position


def serialize(value: Value) -> str:
    """``'E5'``, or ``'C4 E4 | G4'`` for several slots and chords (attempt log)."""
    return ' | '.join(' '.join(str(p) for p in chord) for chord in value)


@dataclass(frozen=True, slots=True)
class SlotMark:
    """How a slot looks after answering: the learner's note and, if wrong, the right one."""

    given: tuple[Pitch, ...]
    expected: tuple[Pitch, ...]

    @property
    def correct(self) -> bool:
        return self.given == self.expected


@dataclass
class StaffEntry:
    """Notes entered on one staff, slot by slot."""

    clef: Clef
    key_signature: KeySignature | None = None
    slots: int = 1
    given: StaffSpec | None = None
    """Printed notes the entered ones follow (the lower note of an interval)."""
    notes: list[Pitch | None] = field(default_factory=list)
    current: int = 0
    cursor: int = MIDDLE_LINE
    accidental: Accidental = Accidental.NONE

    def __post_init__(self) -> None:
        self.slots = max(1, self.slots)
        if not self.notes:
            self.notes = [None] * self.slots
        given = self.given_pitches()
        if given:
            self.cursor = clamp(self.clef.staff_position(given[-1]))

    # Reading

    def given_pitches(self) -> list[Pitch]:
        if self.given is None:
            return []
        return [h.pitch for e in self.given.events if isinstance(e, Chord) for h in e.heads]

    @property
    def cursor_pitch(self) -> Pitch:
        """The note at the cursor with the chosen accidental: what a click or Enter writes."""
        return pitch_at(self.clef, self.cursor, self.accidental, self.key_signature)

    @property
    def complete(self) -> bool:
        return all(note is not None for note in self.notes)

    def value(self) -> Value | None:
        """The answer value, or ``None`` while a slot is empty."""
        if not self.complete:
            return None
        return tuple((note,) for note in self.notes if note is not None)

    # Editing

    def place(self, position: int) -> Pitch:
        """Write a note at ``position`` in the current slot, with the chosen accidental."""
        self.cursor = clamp(position)
        pitch = self.cursor_pitch
        self.notes[self.current] = pitch
        return pitch

    def move(self, steps: int) -> Pitch:
        """Move the current note (or the cursor of an empty slot) by staff steps."""
        return self.place(self.cursor + steps)

    def jump(self, letter: Letter, accidental: Accidental | None = None) -> Pitch:
        """Write ``letter`` at its position nearest the cursor (the letter keys)."""
        if accidental is not None:
            self.accidental = accidental
        return self.place(nearest_position(self.clef, letter, self.cursor))

    def toggle_accidental(self, accidental: Accidental) -> Accidental:
        """Turn a toggle on, or off if it was on; a written note in the current slot follows."""
        self.accidental = Accidental.NONE if self.accidental is accidental else accidental
        if self.notes[self.current] is not None:
            self.place(self.cursor)
        return self.accidental

    def clear(self) -> bool:
        """Remove the note of the current slot; ``False`` if it was empty."""
        if self.notes[self.current] is None:
            return False
        self.notes[self.current] = None
        return True

    def select(self, slot: int) -> None:
        """Make ``slot`` current; the cursor moves to its note if it has one."""
        self.current = max(0, min(self.slots - 1, slot))
        note = self.notes[self.current]
        if note is not None:
            self.cursor = clamp(self.clef.staff_position(note))
            self.accidental = accidental_for(note, self.key_signature)

    # Figures

    def _given_events(self) -> tuple[Event, ...]:
        return self.given.events if self.given is not None else ()

    def figure(self, hover: int | None = None, *, description: str | None = None) -> StaffSpec:
        """The staff as the learner edits it.

        The current slot's note is accent-coloured with a halo; an empty current
        slot shows the cursor as a dim note. ``hover`` adds a dim note where the
        pointer would write one. Empty slots after the current one are not drawn.
        """
        events: list[Event] = list(self._given_events())
        last = max(
            [self.current, *(i for i, note in enumerate(self.notes) if note is not None)],
        )
        for slot in range(last + 1):
            note = self.notes[slot]
            heads: list[Head] = []
            current = slot == self.current
            if note is not None:
                if current:
                    heads.append(Head(note, ink=Ink.ACCENT, halo=True))
                else:
                    heads.append(Head(note))
            if current:
                ghost = self.cursor if note is None and hover is None else hover
                if ghost is not None:
                    pitch = pitch_at(self.clef, clamp(ghost), self.accidental, self.key_signature)
                    if note is None or self.clef.staff_position(note) != clamp(ghost):
                        heads.append(Head(pitch, ink=Ink.DIM))
            if heads:
                heads.sort(key=lambda h: h.pitch.diatonic_index)
                events.append(Chord(tuple(heads)))
            else:
                # An empty slot before the current one keeps its column with a dim cursor.
                events.append(Chord((Head(self.clef.pitch_at(MIDDLE_LINE), ink=Ink.DIM),)))
        return StaffSpec(
            clef=self.clef,
            key_signature=self.key_signature,
            events=tuple(events),
            description=description,
        )

    def slot_events(self) -> list[int]:
        """Figure event index of every drawn slot, as :meth:`figure` lays them out."""
        start = len(self._given_events())
        last = max([self.current, *(i for i, note in enumerate(self.notes) if note is not None)])
        return [start + slot for slot in range(last + 1)]

    def marks(self, expected: Sequence[Sequence[Pitch]]) -> list[SlotMark]:
        given = self.value() or tuple(() if n is None else (n,) for n in self.notes)
        return [
            SlotMark(tuple(g), tuple(e))
            for g, e in zip(given, expected, strict=False)  # a short answer leaves slots unmarked
        ]

    def reveal_figure(
        self,
        expected: Sequence[Sequence[Pitch]],
        *,
        given_label: str,
        expected_label: str,
        description: str | None = None,
    ) -> StaffSpec:
        """The answer checked: right notes in success ink; a wrong note in error ink,
        followed by the right one in success ink, each labelled underneath."""
        events: list[Event] = list(self._given_events())
        for mark in self.marks(expected):
            if mark.correct:
                heads = tuple(Head(p, ink=Ink.SUCCESS) for p in mark.given)
                events.append(Chord(heads, ink=Ink.SUCCESS))
                continue
            if mark.given:
                heads = tuple(Head(p, ink=Ink.ERROR) for p in mark.given)
                events.append(Chord(heads, label=given_label, ink=Ink.ERROR))
            heads = tuple(Head(p, ink=Ink.SUCCESS) for p in mark.expected)
            events.append(Chord(heads, label=expected_label, ink=Ink.SUCCESS))
        return StaffSpec(
            clef=self.clef,
            key_signature=self.key_signature,
            events=tuple(events),
            description=description,
        )
