# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The staff input's state, without GTK: clicks and keys → pitches → answer value."""

from __future__ import annotations

import pytest

from etude.core import Duration, KeySignature, Letter, Meter, NoteValue, Pitch
from etude.notation.spec import Chord, Clef, Head, Ink, Rest, StaffSpec, SystemSpec
from etude.ui.widgets.staff_entry import (
    MAX_POSITION,
    MIN_POSITION,
    Accidental,
    StaffEntry,
    accidental_for,
    nearest_position,
    pitch_at,
    serialize,
    voice_label,
)

P = Pitch.parse


def heads(figure: StaffSpec) -> list[list[Head]]:
    return [list(e.heads) for e in figure.events if isinstance(e, Chord)]


@pytest.mark.parametrize(
    ('clef', 'position', 'accidental', 'signature', 'pitch'),
    [
        (Clef.TREBLE, 0, Accidental.NONE, None, 'E4'),
        (Clef.TREBLE, 1, Accidental.SHARP, None, 'F#4'),
        (Clef.TREBLE, -2, Accidental.NONE, None, 'C4'),
        (Clef.BASS, 8, Accidental.FLAT, None, 'Ab3'),
        (Clef.TREBLE, 1, Accidental.NONE, KeySignature(1), 'F#4'),
        (Clef.TREBLE, 1, Accidental.NATURAL, KeySignature(1), 'F4'),
        (Clef.ALTO, 4, Accidental.NONE, KeySignature(-2), 'C4'),
        (Clef.TREBLE, 4, Accidental.NONE, KeySignature(-2), 'Bb4'),
    ],
)
def test_pitch_at(clef, position, accidental, signature, pitch) -> None:
    written = pitch_at(clef, position, accidental, signature)
    assert written == P(pitch)
    assert pitch_at(clef, position, accidental_for(written, signature), signature) == written


def test_nearest_position_jumps_at_most_three_steps() -> None:
    # From the middle line of the treble staff (B4): C5 is up one, A4 down one, F5 up four
    # is further than F4 down three.
    assert nearest_position(Clef.TREBLE, Letter.C, 4) == 5
    assert nearest_position(Clef.TREBLE, Letter.A, 4) == 3
    assert nearest_position(Clef.TREBLE, Letter.F, 4) == 1
    assert nearest_position(Clef.TREBLE, Letter.E, 4) == 7
    assert nearest_position(Clef.TREBLE, Letter.B, 4) == 4
    for letter in Letter:
        for around in range(MIN_POSITION, MAX_POSITION + 1):
            position = nearest_position(Clef.BASS, letter, around)
            assert MIN_POSITION <= position <= MAX_POSITION
            assert Clef.BASS.pitch_at(position).letter is letter


def test_click_keys_and_value() -> None:
    entry = StaffEntry(Clef.TREBLE)
    assert entry.value() is None
    assert entry.cursor == 4
    assert entry.place(1) == P('F4')
    assert entry.value() == ((P('F4'),),)
    assert entry.move(1) == P('G4')
    assert entry.toggle_accidental(Accidental.SHARP) is Accidental.SHARP
    assert entry.value() == ((P('G#4'),),)
    assert entry.toggle_accidental(Accidental.SHARP) is Accidental.NONE
    assert entry.value() == ((P('G4'),),)
    assert entry.jump(Letter.E) == P('E4')  # nearest E to G4 is below
    assert entry.jump(Letter.F, Accidental.SHARP) == P('F#4')
    assert entry.move(7) == P('F#5')
    assert entry.clear()
    assert not entry.clear()
    assert entry.value() is None


def test_moves_stay_in_range() -> None:
    entry = StaffEntry(Clef.TREBLE)
    for _ in range(40):
        entry.move(1)
    assert entry.cursor == MAX_POSITION
    for _ in range(40):
        entry.move(-7)
    assert entry.cursor == MIN_POSITION


def test_given_notes_set_the_cursor_and_come_first() -> None:
    given = StaffSpec(events=(Chord((Head(P('G4')),)),))
    entry = StaffEntry(Clef.TREBLE, given=given)
    assert entry.cursor == Clef.TREBLE.staff_position(P('G4'))
    figure = entry.figure()
    assert heads(figure)[0] == [Head(P('G4'))]
    # The empty slot shows a dim cursor note on the given note's position.
    assert heads(figure)[1] == [Head(P('G4'), ink=Ink.DIM)]
    entry.place(Clef.TREBLE.staff_position(P('E5')))
    assert heads(entry.figure())[1] == [Head(P('E5'), ink=Ink.ACCENT, halo=True)]
    assert entry.slot_events() == [1]


def test_hover_adds_a_dim_note() -> None:
    entry = StaffEntry(Clef.BASS, key_signature=KeySignature(-1))
    entry.place(4)  # D3
    figure = entry.figure(hover=8)  # the top line: A3
    (chord,) = heads(figure)
    assert [h.pitch for h in chord] == [P('D3'), P('A3')]
    assert chord[1].ink is Ink.DIM
    assert heads(entry.figure(hover=4)) == [[Head(P('D3'), ink=Ink.ACCENT, halo=True)]]
    assert entry.place(2) == P('Bb2'), 'the key signature applies'


def test_several_slots() -> None:
    entry = StaffEntry(Clef.TREBLE, slots=3)
    entry.place(0)
    entry.select(2)
    entry.place(2)
    assert entry.value() is None
    figure = entry.figure()
    assert len(figure.events) == 3
    entry.select(1)
    entry.place(1)
    assert entry.value() == ((P('E4'),), (P('F4'),), (P('G4'),))
    assert serialize(entry.value()) == 'E4 | F4 | G4'
    entry.select(0)
    assert entry.cursor == 0


def test_reveal_marks_right_and_wrong() -> None:
    entry = StaffEntry(Clef.TREBLE)
    entry.place(2)  # G4
    figure = entry.reveal_figure([[P('F4')]], given_label='Yours', expected_label='Answer')
    wrong, right = (e for e in figure.events if isinstance(e, Chord))
    assert wrong.heads == (Head(P('G4'), ink=Ink.ERROR),)
    assert (wrong.label, wrong.ink) == ('Yours', Ink.ERROR)
    assert right.heads == (Head(P('F4'), ink=Ink.SUCCESS),)
    assert right.label == 'Answer'
    correct = entry.reveal_figure([[P('G4')]], given_label='Yours', expected_label='Answer')
    (only,) = correct.events
    assert isinstance(only, Chord)
    assert only.heads == (Head(P('G4'), ink=Ink.SUCCESS),)
    assert only.label is None


# Several voices on a grand staff (four-part writing) ----------------------------------


def satb(**kwargs) -> StaffEntry:
    bass = tuple(P(n) for n in ('C3', 'F3', 'G3', 'C3'))
    return StaffEntry(
        Clef.TREBLE,
        slots=4,
        voices=4,
        staves=(Clef.TREBLE, Clef.BASS),
        given_voices={3: bass},
        labels=('I', 'IV', 'V', 'I'),
        **kwargs,
    )


def test_voices_and_printed_voices() -> None:
    entry = satb()
    assert entry.editable_voices == [0, 1, 2]
    assert entry.voice == 0, 'the top written voice comes first'
    assert entry.voice_staves == (0, 0, 1, 1)
    assert entry.voice_clef is Clef.TREBLE
    assert not entry.set_voice(3), 'the printed bass cannot be selected'
    assert entry.set_voice(2)
    assert entry.voice_clef is Clef.BASS
    assert entry.place(Clef.BASS.staff_position(P('E3'))) == P('E3')
    assert entry.next_voice()
    assert entry.voice == 0, 'Tab wraps to the soprano'
    assert entry.next_voice(-1)
    assert entry.voice == 2
    assert not entry.next_voice(wrap=False), 'past the last voice'
    assert entry.voice == 2
    assert voice_label(4, 1) == 'Alto'
    assert voice_label(2, 1) == 'Lower voice'
    assert voice_label(3, 2) == 'Voice 3'


def test_each_voice_keeps_its_cursor_and_notes() -> None:
    entry = satb()
    soprano = entry.jump(Letter.E)  # nearest E above the soprano's default cursor
    assert soprano == P('E5')
    entry.set_voice(1)
    assert entry.notes[0] is None
    alto = entry.jump(Letter.C)
    assert alto.letter is Letter.C
    entry.set_voice(0)
    assert entry.cursor == Clef.TREBLE.staff_position(P('E5')), 'back on the soprano note'
    entry.select(1)
    entry.place(Clef.TREBLE.staff_position(P('F5')))
    assert entry.parts[0][:2] == [P('E5'), P('F5')]
    assert entry.parts[1][:2] == [alto, None]


def test_value_lists_every_voice_top_first() -> None:
    entry = satb()
    music = [('E5', 'C5', 'G4'), ('F5', 'C5', 'A4'), ('D5', 'B4', 'G4'), ('E5', 'C5', 'G4')]
    for voice in range(3):
        entry.set_voice(voice)
        clef = entry.voice_clef
        for slot, notes in enumerate(music):
            entry.select(slot)
            if slot == 3 and voice == 2:
                assert entry.value() is None
            entry.place(clef.staff_position(P(notes[voice])))
    value = entry.value()
    assert value == tuple(
        (P(s), P(a), P(t), P(b))
        for (s, a, t), b in zip(music, ('C3', 'F3', 'G3', 'C3'), strict=True)
    )
    assert serialize(value).startswith('E5 C5 G4 C3 | F5 C5 A4 F3')


def test_four_part_figure() -> None:
    entry = satb()
    entry.place(Clef.TREBLE.staff_position(P('E5')))
    figure = entry.figure()
    assert isinstance(figure, SystemSpec)
    upper, lower = figure.staves
    assert (upper.clef, lower.clef) == (Clef.TREBLE, Clef.BASS)
    soprano, alto = upper.events, upper.voices[0]
    tenor, bass = lower.events, lower.voices[0]
    assert all(len(line) == 4 for line in (soprano, alto, tenor, bass))
    first = soprano[0]
    assert isinstance(first, Chord)
    assert first.heads == (Head(P('E5'), ink=Ink.ACCENT, halo=True),)
    assert first.duration is not None, 'voices have stems'
    assert all(isinstance(e, Rest) and e.ink is Ink.DIM for e in alto), 'empty: dim rests'
    assert [e.label for e in bass] == ['I', 'IV', 'V', 'I'], 'numerals under the bass'
    assert all(h.ink is Ink.FOREGROUND for e in bass for h in e.heads), 'printed'
    # Events of the second voice of a staff are numbered after the first voice's.
    assert entry.event_of(0, 2) == (0, 2)
    assert entry.event_of(1, 2) == (0, 6)
    assert entry.event_of(3, 0) == (1, 4)
    entry.set_voice(1)
    assert entry.slot_events() == [4, 5, 6, 7]


def test_four_part_reveal_marks_wrong_notes_in_place() -> None:
    entry = satb()
    expected = [
        (P('E5'), P('C5'), P('G4'), P('C3')),
        (P('F5'), P('C5'), P('A4'), P('F3')),
        (P('D5'), P('B4'), P('G4'), P('G3')),
        (P('E5'), P('C5'), P('G4'), P('C3')),
    ]
    for voice in range(3):
        entry.set_voice(voice)
        for slot, chord in enumerate(expected):
            entry.select(slot)
            pitch = chord[voice] if (voice, slot) != (1, 2) else P('D5')
            entry.place(entry.voice_clef.staff_position(pitch))
    figure = entry.reveal_figure(expected, given_label='✗', expected_label='✓')
    assert isinstance(figure, SystemSpec)
    alto = figure.staves[0].voices[0]
    assert len(alto) == 4, 'columns stay as they are'
    wrong = alto[2]
    assert isinstance(wrong, Chord)
    assert {(h.pitch, h.ink) for h in wrong.heads} == {
        (P('D5'), Ink.ERROR),
        (P('B4'), Ink.SUCCESS),
    }
    soprano = figure.staves[0].events
    assert soprano[2].label == '✗'
    assert soprano[0].heads[0].ink is Ink.SUCCESS
    assert figure.staves[1].voices[0][0].heads[0].ink is Ink.FOREGROUND, 'printed bass'


# A rhythm template (melodic dictation) ------------------------------------------------


def test_rhythm_template() -> None:
    quarter, eighth, half = (
        Duration(v) for v in (NoteValue.QUARTER, NoteValue.EIGHTH, NoteValue.HALF)
    )
    rhythm = (quarter, eighth, eighth, half)
    entry = StaffEntry(Clef.TREBLE, slots=4, rhythm=rhythm)
    figure = entry.figure()
    assert isinstance(figure, StaffSpec)
    chords = [e for e in figure.events if isinstance(e, Chord)]
    assert [c.duration for c in chords] == list(rhythm), 'drawn in the slot durations'
    assert all(h.ink is Ink.DIM for c in chords[1:] for h in c.heads), 'empty: placeholders'
    entry.place(2)
    entry.select(1)
    entry.place(3)
    chords = [e for e in entry.figure().events if isinstance(e, Chord)]
    assert chords[0].heads == (Head(P('G4'), ink=Ink.ACCENT),)
    assert chords[0].duration == quarter
    assert entry.slot_events() == [0, 1, 2, 3]
    entry.select(2)
    entry.place(4)
    entry.select(3)
    entry.place(0)
    figure = entry.reveal_figure(
        [[P('G4')], [P('A4')], [P('C5')], [P('E4')]], given_label='✗', expected_label='✓'
    )
    chords = [e for e in figure.events if isinstance(e, Chord)]
    assert [c.duration for c in chords] == list(rhythm)
    assert {h.ink for h in chords[2].heads} == {Ink.ERROR, Ink.SUCCESS}


def test_rhythm_with_a_meter_has_barlines() -> None:
    quarter = Duration(NoteValue.QUARTER)
    given = StaffSpec(meter=Meter(2, 4))
    entry = StaffEntry(Clef.TREBLE, slots=4, given=given, rhythm=(quarter,) * 4)
    figure = entry.figure()
    assert isinstance(figure, StaffSpec)
    assert figure.meter == Meter(2, 4)
    assert [type(e).__name__ for e in figure.events] == [
        'Chord',
        'Chord',
        'Barline',
        'Chord',
        'Chord',
    ]
    assert entry.slot_events() == [0, 1, 3, 4]


def test_printed_notes_before_a_rhythm_count_towards_the_bar() -> None:
    # Melodic dictation prints the first note; the rest of the 3/4 bar follows.
    quarter = Duration(NoteValue.QUARTER)
    given = StaffSpec(meter=Meter(3, 4), events=(Chord((Head(P('G4')),), quarter),))
    rhythm = (quarter, quarter, Duration(NoteValue.HALF, dots=1))
    entry = StaffEntry(Clef.TREBLE, slots=3, given=given, rhythm=rhythm)
    figure = entry.figure()
    assert isinstance(figure, StaffSpec)
    assert [type(e).__name__ for e in figure.events] == [
        'Chord',
        'Chord',
        'Chord',
        'Barline',
        'Chord',
    ]
    assert entry.slot_events() == [1, 2, 4]
