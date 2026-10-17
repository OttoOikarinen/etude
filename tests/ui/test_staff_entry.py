# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The staff input's state, without GTK: clicks and keys → pitches → answer value."""

from __future__ import annotations

import pytest

from etude.core import KeySignature, Letter, Pitch
from etude.notation.spec import Chord, Clef, Head, Ink, StaffSpec
from etude.ui.widgets.staff_entry import (
    MAX_POSITION,
    MIN_POSITION,
    Accidental,
    StaffEntry,
    accidental_for,
    nearest_position,
    pitch_at,
    serialize,
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
