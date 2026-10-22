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
level-1 exercises enter one note per slot.

With several ``voices`` (four-part writing) every voice has its own notes and
its own cursor, and :attr:`StaffEntry.voice` says which one the keys and
clicks write; :attr:`StaffEntry.notes` and :attr:`StaffEntry.cursor` are
always the current voice's. Voices in ``given_voices`` are printed and cannot
be selected. The voices stand on the staves of ``staves`` (a grand staff),
stems up for the upper voice of a staff and down for the lower one, and the
value lists one pitch per voice in every slot, top voice first.

With a ``rhythm`` (dictation) the single voice is drawn in those durations;
empty slots show a dim placeholder note on the middle line, so the learner
sees the rhythm they write pitches into.

With ``voice_rhythms`` (species counterpoint) every voice has its own rhythm
and number of notes: a rest before the first note, notes tied over the barlines
of ``meter`` where they cross them (written once), and the value lists each
voice's notes. :attr:`StaffEntry.slots` and :attr:`StaffEntry.current` are then
the current voice's.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from fractions import Fraction
from gettext import gettext as _
from gettext import pgettext

from ...core import Duration, KeySignature, Meter, NoteValue, Pitch
from ...core.pitch import Letter
from ...notation.parts import Line, event_index, rhythm_line, voices_figure
from ...notation.spec import Barline, Chord, Clef, Event, Head, Ink, Rest, StaffSpec, SystemSpec

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


QUARTER = Duration(NoteValue.QUARTER)
"""Several voices are drawn as quarter notes, so each voice shows its stems."""


def _length(event: Event) -> Fraction:
    """Time an event takes (stemless notes count as quarters, as layout aligns them)."""
    if isinstance(event, Barline):
        return Fraction(0)
    return event.duration.length if event.duration is not None else Fraction(1, 4)


def voice_label(voices: int, voice: int) -> str:
    """The name of a voice: "Soprano" … "Bass" in four parts, "Upper voice" and
    "Lower voice" in two, "Voice 3" otherwise."""
    if voices == 4:
        return (
            pgettext('voice', 'Soprano'),
            pgettext('voice', 'Alto'),
            pgettext('voice', 'Tenor'),
            pgettext('voice', 'Bass'),
        )[voice]
    if voices == 2:
        return (_('Upper voice'), _('Lower voice'))[voice]
    # Translators: a voice of a multi-voice staff answer, e.g. "Voice 3".
    return _('Voice {number}').format(number=voice + 1)


def voice_letter(voices: int, voice: int) -> str:
    """A one-letter mark of a voice ("S", "A", "T", "B" in four parts, else its number)."""
    if voices == 4:
        # Translators: one-letter abbreviations of soprano, alto, tenor and bass.
        return (
            pgettext('voice letter', 'S'),
            pgettext('voice letter', 'A'),
            pgettext('voice letter', 'T'),
            pgettext('voice letter', 'B'),
        )[voice]
    return str(voice + 1)


@dataclass
class StaffEntry:
    """Notes entered on one staff (or a grand staff), slot by slot and voice by voice."""

    clef: Clef
    key_signature: KeySignature | None = None
    slots: int = 1
    given: StaffSpec | None = None
    """Printed notes the entered ones follow (the lower note of an interval)."""
    notes: list[Pitch | None] = field(default_factory=list)
    """The current voice's notes, one per slot (``None`` while empty)."""
    current: int = 0
    cursor: int = MIDDLE_LINE
    """The current voice's cursor: a staff position on its staff."""
    accidental: Accidental = Accidental.NONE
    voices: int = 1
    staves: tuple[Clef, ...] = ()
    """Clefs of a system; empty means one staff in ``clef``."""
    voice_staves: tuple[int, ...] = ()
    """Staff of each voice (default as :meth:`StaffInputAnswer.staff_of_voice`)."""
    given_voices: Mapping[int, tuple[Pitch, ...]] = field(default_factory=dict)
    rhythm: tuple[Duration, ...] = ()
    labels: tuple[str, ...] = ()
    """Text under each slot (Roman numerals), drawn under the lowest voice."""
    voice: int = 0
    """The voice that keys and clicks write."""
    parts: list[list[Pitch | None]] = field(default_factory=list)
    """Every voice's notes, top voice first; ``notes`` is ``parts[voice]``."""
    cursors: list[int] = field(default_factory=list)
    voice_rhythms: Mapping[int, tuple[Duration, ...]] = field(default_factory=dict)
    """Each voice's own note durations (species counterpoint); see the module notes."""
    voice_rests: Mapping[int, Duration] = field(default_factory=dict)
    meter: Meter | None = None
    """Barlines of ``voice_rhythms``."""
    voice_names: tuple[str, ...] = ()
    lines: list[Line] = field(default_factory=list, init=False)
    """Where each voice's notes fall among its events (``voice_rhythms``)."""

    def __post_init__(self) -> None:
        if self.rhythm:
            self.slots = len(self.rhythm)
        self.slots = max(1, self.slots)
        self.voices = max(1, self.voices)
        if not self.voice_staves:
            self.voice_staves = tuple(self._default_staff(v) for v in range(self.voices))
        if not self.parts:
            self.parts = []
            for v in range(self.voices):
                count = self.count(v)
                fixed = self.given_voices.get(v)
                if fixed is not None:
                    self.parts.append([*fixed[:count], *[None] * (count - len(fixed))])
                elif v == 0 and self.notes:
                    self.parts.append(self.notes)
                else:
                    self.parts.append([None] * count)
        editable = self.editable_voices
        if self.voice not in editable and editable:
            self.voice = editable[0]
        if self.voice_rhythms:
            self.slots = self.count(self.voice)
            self.lines = [
                self._line(v, [Chord(()) for _ in range(self.count(v))]) for v in range(self.voices)
            ]
        if not self.cursors:
            self.cursors = [self._default_cursor(v) for v in range(self.voices)]
        self.notes = self.parts[self.voice]
        given = self.given_pitches()
        if given and self.voices == 1:
            self.cursors[0] = clamp(self.clef.staff_position(given[-1]))
        self.cursor = self.cursors[self.voice]

    def count(self, voice: int) -> int:
        """The number of notes ``voice`` has."""
        if self.voice_rhythms:
            return len(self.voice_rhythms.get(voice, ()))
        return self.slots

    def onset(self, voice: int, slot: int) -> Fraction:
        """When note ``slot`` of ``voice`` starts (``voice_rhythms``), in whole notes."""
        rest = self.voice_rests.get(voice)
        time = rest.length if rest is not None else Fraction(0)
        return time + sum((d.length for d in self.voice_rhythms[voice][:slot]), Fraction(0))

    def voice_name(self, voice: int) -> str:
        """The name of a voice: from ``voice_names``, else as :func:`voice_label`."""
        if voice < len(self.voice_names):
            return self.voice_names[voice]
        return voice_label(self.voices, voice)

    def _line(self, voice: int, chords: Sequence[Chord]) -> Line:
        bar = self.meter.bar_length if self.meter is not None else None
        return rhythm_line(
            chords,
            self.voice_rhythms[voice],
            rest=self.voice_rests.get(voice),
            bar=bar,
            final_bar=True,
            rest_ink=Ink.DIM if voice in self.editable_voices else Ink.FOREGROUND,
        )

    def _default_staff(self, voice: int) -> int:
        if len(self.staves) < 2:
            return 0
        return 0 if voice < (self.voices + 1) // 2 else len(self.staves) - 1

    def _default_cursor(self, voice: int) -> int:
        """Upper voice of a shared staff a third above the middle line, lower a third below."""
        on_staff = self.staff_voices(self.voice_staves[voice])
        if len(on_staff) < 2:
            return MIDDLE_LINE
        return MIDDLE_LINE + 2 if on_staff.index(voice) == 0 else MIDDLE_LINE - 2

    # Reading

    @property
    def multipart(self) -> bool:
        """Drawn with voices, staves or a rhythm, not as level-1 stemless notes."""
        return self.voices > 1 or len(self.staves) > 1 or bool(self.rhythm)

    @property
    def editable_voices(self) -> list[int]:
        return [v for v in range(self.voices) if v not in self.given_voices]

    def staff_voices(self, staff: int) -> list[int]:
        return [v for v, s in enumerate(self.voice_staves) if s == staff]

    def clef_of(self, voice: int) -> Clef:
        if not self.staves:
            return self.clef
        return self.staves[self.voice_staves[voice]]

    @property
    def voice_clef(self) -> Clef:
        """The clef of the current voice's staff."""
        return self.clef_of(self.voice)

    def given_pitches(self) -> list[Pitch]:
        if self.given is None:
            return []
        return [h.pitch for e in self.given.events if isinstance(e, Chord) for h in e.heads]

    @property
    def cursor_pitch(self) -> Pitch:
        """The note at the cursor with the chosen accidental: what a click or Enter writes."""
        return pitch_at(self.voice_clef, self.cursor, self.accidental, self.key_signature)

    @property
    def complete(self) -> bool:
        return all(note is not None for part in self.parts for note in part)

    def value(self) -> Value | None:
        """The answer value, or ``None`` while a slot is empty."""
        if not self.complete:
            return None
        if self.voice_rhythms:
            return tuple(tuple(n for n in part if n is not None) for part in self.parts)
        return tuple(
            tuple(note for part in self.parts if (note := part[slot]) is not None)
            for slot in range(self.slots)
        )

    def note(self, voice: int, slot: int) -> Pitch | None:
        return self.parts[voice][slot]

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
        return self.place(nearest_position(self.voice_clef, letter, self.cursor))

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
        self._follow_note()

    def set_voice(self, voice: int) -> bool:
        """Make ``voice`` current; ``False`` for a given (printed) voice or no such voice."""
        if voice not in self.editable_voices:
            return False
        self.cursors[self.voice] = self.cursor
        if self.voice_rhythms and voice != self.voice:
            # Keep the place in time: the note of the new voice sounding then.
            time = self.onset(self.voice, self.current)
            self.slots = self.count(voice)
            self.current = max(
                (k for k in range(self.slots) if self.onset(voice, k) <= time), default=0
            )
        self.voice = voice
        self.notes = self.parts[voice]
        self.cursor = self.cursors[voice]
        self.accidental = Accidental.NONE
        self._follow_note()
        return True

    def next_voice(self, step: int = 1, *, wrap: bool = True) -> bool:
        """Select the next editable voice down (``step`` -1: up). Without ``wrap``,
        ``False`` at the last (first) voice, which then stays selected."""
        editable = self.editable_voices
        index = editable.index(self.voice) + step
        if not 0 <= index < len(editable):
            if not wrap:
                return False
            index %= len(editable)
        return self.set_voice(editable[index])

    def _follow_note(self) -> None:
        note = self.notes[self.current]
        if note is not None:
            self.cursor = clamp(self.voice_clef.staff_position(note))
            self.accidental = accidental_for(note, self.key_signature)

    # Figures

    def _given_events(self) -> tuple[Event, ...]:
        return self.given.events if self.given is not None else ()

    def figure(
        self, hover: int | None = None, *, description: str | None = None
    ) -> StaffSpec | SystemSpec:
        """The staff as the learner edits it.

        The current slot's note is accent-coloured with a halo; an empty current
        slot shows the cursor as a dim note. ``hover`` adds a dim note where the
        pointer would write one. Empty slots after the current one are not drawn
        (on one staff without rhythm); with voices or a rhythm every slot is
        drawn, empty ones as dim rests (voices) or dim placeholder notes (rhythm),
        and the current voice is accent-coloured.
        """
        if self.voice_rhythms:
            return self._lines_figure(hover, description)
        if self.multipart:
            return self._part_figure(hover, description)
        events: list[Event] = list(self._given_events())
        last = max(
            [self.current, *(i for i, note in enumerate(self.notes) if note is not None)],
        )
        for slot in range(last + 1):
            note = self.notes[slot]
            heads = self._heads(slot, note, hover, current_voice=True)
            if heads:
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

    def _heads(
        self, slot: int, note: Pitch | None, hover: int | None, *, current_voice: bool
    ) -> list[Head]:
        """The heads of the current voice in ``slot``: its note and the dim cursor."""
        heads: list[Head] = []
        current = current_voice and slot == self.current
        if note is not None:
            if current:
                heads.append(Head(note, ink=Ink.ACCENT, halo=True))
            elif current_voice and self.multipart:
                heads.append(Head(note, ink=Ink.ACCENT))
            else:
                heads.append(Head(note))
        if current:
            clef = self.voice_clef
            ghost = self.cursor if note is None and hover is None else hover
            if ghost is not None:
                pitch = pitch_at(clef, clamp(ghost), self.accidental, self.key_signature)
                if note is None or clef.staff_position(note) != clamp(ghost):
                    heads.append(Head(pitch, ink=Ink.DIM))
        heads.sort(key=lambda h: h.pitch.diatonic_index)
        return heads

    def _duration(self, slot: int) -> Duration | None:
        if self.rhythm:
            return self.rhythm[slot]
        return QUARTER if self.voices > 1 else None

    def _meter(self) -> Meter | None:
        """The given staff's meter, used for barlines when there is a rhythm."""
        return self.given.meter if self.given is not None and self.rhythm else None

    def _meter_bar(self) -> Fraction | None:
        meter = self._meter()
        return meter.bar_length if meter is not None else None

    def _barlines_before(self) -> list[bool]:
        """Whether a barline stands before each slot (a rhythm with the given staff's meter)."""
        bar = self._meter_bar()
        result = [False] * self.slots
        if bar is None:
            return result
        given = self._given_events() if self.voices == 1 else ()
        # Printed notes before the slots (the first note of a dictation) take time too.
        time = sum((_length(e) for e in given), Fraction(0))
        ends_with_bar = bool(given) and isinstance(given[-1], Barline)
        for slot in range(self.slots):
            if time and time % bar == 0 and not (slot == 0 and ends_with_bar):
                result[slot] = True
            time += self.rhythm[slot].length
        return result

    def _voice_events(self, voice: int, hover: int | None, label_voice: int) -> list[Event]:
        events: list[Event] = list(self._given_events()) if self.voices == 1 else []
        bars = self._barlines_before()
        clef = self.clef_of(voice)
        current_voice = voice == self.voice and voice in self.editable_voices
        for slot in range(self.slots):
            if bars[slot]:
                events.append(Barline())
            duration = self._duration(slot)
            note = self.parts[voice][slot]
            heads = self._heads(slot, note, hover, current_voice=current_voice)
            label = self.labels[slot] if voice == label_voice and slot < len(self.labels) else None
            if heads:
                ink = Ink.ACCENT if current_voice and label is None else Ink.FOREGROUND
                events.append(Chord(tuple(heads), duration, label, ink))
            elif self.voices == 1 or duration is None:
                placeholder = Head(clef.pitch_at(MIDDLE_LINE), ink=Ink.DIM)
                events.append(Chord((placeholder,), duration, label, Ink.DIM))
            elif label is not None:
                # A labelled slot needs a chord to carry its label: a dim placeholder.
                placeholder = Head(clef.pitch_at(self._default_cursor(voice)), ink=Ink.DIM)
                events.append(Chord((placeholder,), duration, label, Ink.DIM))
            else:
                events.append(Rest(duration, ink=Ink.DIM))
        return events

    def _part_figure(self, hover: int | None, description: str | None) -> StaffSpec | SystemSpec:
        clefs = self.staves or (self.clef,)
        events = [self._voice_events(v, hover, self.voices - 1) for v in range(self.voices)]
        return voices_figure(
            clefs,
            self.voice_staves,
            events,
            key_signature=self.key_signature,
            meter=self._meter(),
            description=description,
        )

    def _lines_figure(
        self, hover: int | None, description: str | None, chords: list[list[Chord]] | None = None
    ) -> StaffSpec | SystemSpec:
        """Every voice in its own rhythm; ``chords`` replaces the notes (the reveal)."""
        events: list[tuple[Event, ...]] = []
        for voice in range(self.voices):
            if chords is not None:
                line = chords[voice]
            else:
                current_voice = voice == self.voice and voice in self.editable_voices
                line = []
                for slot in range(self.count(voice)):
                    note = self.parts[voice][slot]
                    heads = self._heads(slot, note, hover, current_voice=current_voice)
                    if current_voice and slot == self.current and note is None:
                        # Whole and half notes have no stem to colour: a halo shows
                        # which empty note the keys write.
                        heads = [replace(h, halo=True) for h in heads]
                    if heads:
                        ink = Ink.ACCENT if current_voice else Ink.FOREGROUND
                        line.append(Chord(tuple(heads), ink=ink))
                    else:
                        # On the middle line as the key signature has it (no natural).
                        clef = self.clef_of(voice)
                        position = self._default_cursor(voice)
                        pitch = pitch_at(clef, position, Accidental.NONE, self.key_signature)
                        line.append(Chord((Head(pitch, ink=Ink.DIM),), ink=Ink.DIM))
            events.append(self._line(voice, line).events)
        return voices_figure(
            self.staves or (self.clef,),
            self.voice_staves,
            events,
            key_signature=self.key_signature,
            meter=self.meter,
            description=description,
        )

    def _slot_offsets(self) -> list[int]:
        """Index of each slot's event within its voice (after given notes and barlines)."""
        start = len(self._given_events()) if self.voices == 1 else 0
        bars = self._barlines_before()
        offsets = []
        for slot in range(self.slots):
            start += bars[slot]
            offsets.append(start + slot)
        return offsets

    def event_of(self, voice: int, slot: int) -> tuple[int, int]:
        """``(staff, combined event index)`` of ``voice``'s event in ``slot``, as
        :meth:`figure` lays them out with voices or a rhythm (with ``voice_rhythms``
        the first of a tied note's events)."""
        if self.voice_rhythms:
            lengths = [len(line.events) for line in self.lines]
            return event_index(self.voice_staves, lengths, voice, self.lines[voice].starts[slot])
        offsets = self._slot_offsets()
        length = offsets[-1] + 1  # every voice has the same events
        return event_index(self.voice_staves, [length] * self.voices, voice, offsets[slot])

    def slot_events(self) -> list[int]:
        """Figure event index of every drawn slot of the current voice, as :meth:`figure`
        lays them out (on the current voice's staff)."""
        if self.multipart:
            return [self.event_of(self.voice, slot)[1] for slot in range(self.slots)]
        start = len(self._given_events())
        last = max([self.current, *(i for i, note in enumerate(self.notes) if note is not None)])
        return [start + slot for slot in range(last + 1)]

    def slot_columns(self) -> list[tuple[int, int]]:
        """``(figure event index, slot)`` of every drawn event of the current voice's notes,
        both parts of a tied note included (what a click near them selects)."""
        if not self.voice_rhythms:
            return [(event, slot) for slot, event in enumerate(self.slot_events())]
        lengths = [len(line.events) for line in self.lines]
        line = self.lines[self.voice]
        return [
            (event_index(self.voice_staves, lengths, self.voice, index)[1], owner)
            for index, owner in enumerate(line.owners)
            if owner is not None
        ]

    def marks(self, expected: Sequence[Sequence[Pitch]]) -> list[SlotMark]:
        if self.multipart:
            given = [
                tuple(note for part in self.parts if (note := part[slot]) is not None)
                for slot in range(self.slots)
            ]
        else:
            given = list(self.value() or tuple(() if n is None else (n,) for n in self.notes))
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
    ) -> StaffSpec | SystemSpec:
        """The answer checked: right notes in success ink; a wrong note in error ink,
        followed by the right one in success ink, each labelled underneath.

        With voices or a rhythm the columns stay as they are: a wrong note is drawn
        in error ink with the right one beside it on the same stem in success ink,
        and the slot's top voice is labelled ``given_label``.
        """
        if self.voice_rhythms:
            return self._reveal_lines(expected, description)
        if self.multipart:
            return self._reveal_parts(expected, given_label, description)
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

    def _reveal_lines(
        self, expected: Sequence[Sequence[Pitch]], description: str | None
    ) -> StaffSpec | SystemSpec:
        """Each voice as written: a note that matches the expected line in success ink;
        another in error ink with the expected one beside it in success ink."""
        chords: list[list[Chord]] = []
        for voice in range(self.voices):
            line: list[Chord] = []
            right_line = expected[voice] if voice < len(expected) else ()
            for slot, note in enumerate(self.parts[voice]):
                right = right_line[slot] if slot < len(right_line) else None
                if voice in self.given_voices and note is not None:
                    line.append(Chord((Head(note),)))
                elif note is not None and (right is None or note == right):
                    line.append(Chord((Head(note, ink=Ink.SUCCESS),), ink=Ink.SUCCESS))
                else:
                    heads = [Head(note, ink=Ink.ERROR)] if note is not None else []
                    if right is not None and (
                        note is None or note.diatonic_index != right.diatonic_index
                    ):
                        heads.append(Head(right, ink=Ink.SUCCESS))
                    heads.sort(key=lambda h: h.pitch.diatonic_index)
                    line.append(Chord(tuple(heads), ink=Ink.ERROR))
            chords.append(line)
        return self._lines_figure(None, description, chords)

    def _reveal_parts(
        self, expected: Sequence[Sequence[Pitch]], wrong_label: str, description: str | None
    ) -> StaffSpec | SystemSpec:
        bars = self._barlines_before()
        voices: list[list[Event]] = []
        for voice in range(self.voices):
            events: list[Event] = list(self._given_events()) if self.voices == 1 else []
            given_voice = voice in self.given_voices
            for slot in range(self.slots):
                if bars[slot]:
                    events.append(Barline())
                duration = self._duration(slot)
                note = self.parts[voice][slot]
                right = (
                    expected[slot][voice]
                    if slot < len(expected) and voice < len(expected[slot])
                    else None
                )
                wrong_slot = slot < len(expected) and tuple(
                    n for part in self.parts if (n := part[slot]) is not None
                ) != tuple(expected[slot])
                label = None
                if voice == self.voices - 1 and slot < len(self.labels):
                    label = self.labels[slot]
                if voice == 0 and wrong_slot and label is None:
                    label = wrong_label
                heads: list[Head] = []
                ink = Ink.FOREGROUND
                if given_voice and note is not None:
                    heads.append(Head(note))
                elif note is not None and (right is None or note == right):
                    heads.append(Head(note, ink=Ink.SUCCESS))
                    ink = Ink.SUCCESS
                else:
                    ink = Ink.ERROR
                    if note is not None:
                        heads.append(Head(note, ink=Ink.ERROR))
                    if right is not None and (
                        note is None or note.diatonic_index != right.diatonic_index
                    ):
                        heads.append(Head(right, ink=Ink.SUCCESS))
                if voice == 0 and wrong_slot:
                    ink = Ink.ERROR
                heads.sort(key=lambda h: h.pitch.diatonic_index)
                if heads:
                    events.append(Chord(tuple(heads), duration, label, ink))
                elif duration is not None:
                    events.append(Rest(duration, ink=Ink.DIM))
            voices.append(events)
        return voices_figure(
            self.staves or (self.clef,),
            self.voice_staves,
            voices,
            key_signature=self.key_signature,
            meter=self._meter(),
            description=description,
        )
