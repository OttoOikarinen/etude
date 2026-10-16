# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Any

import pytest

from etude.core import Duration, KeySignature, Meter, NoteValue, Pitch, Tuplet
from etude.notation.a11y import describe
from etude.notation.spec import (
    Barline,
    BarStyle,
    Bracket,
    Chord,
    Clef,
    Head,
    Ink,
    Rest,
    StaffSpec,
    SystemSpec,
)

Q = Duration(NoteValue.QUARTER)


def note(*pitches: str, d: Duration | None = None, **kwargs: Any) -> Chord:
    return Chord(tuple(Head(Pitch.parse(p)) for p in pitches), d, **kwargs)


def test_design_example() -> None:
    spec = StaffSpec.notes('G4', 'E5', key_signature=KeySignature(4))
    assert describe(spec) == 'Treble staff, four sharps. Two notes: G4, E5.'


def test_explicit_description_wins() -> None:
    spec = StaffSpec.notes('G4', description='An interval to name.')
    assert describe(spec) == 'An interval to name.'
    system = SystemSpec((spec,), description='Hidden.')
    assert describe(system) == 'Hidden.'


def test_pitch_naming_is_pluggable() -> None:
    spec = StaffSpec.notes('B4', 'Bb4')
    names = {'B4': 'H4', 'Bb4': 'B4'}
    assert describe(spec, lambda p: names[str(p)]) == 'Treble staff. Two notes: H4, B4.'


@pytest.mark.parametrize(
    ('spec', 'expected'),
    [
        (StaffSpec(clef=Clef.BASS), 'Bass staff.'),
        (StaffSpec(clef=Clef.ALTO, key_signature=KeySignature(-1)), 'Alto staff, one flat.'),
        (StaffSpec(clef=Clef.TENOR, meter=Meter(6, 8)), 'Tenor staff, 6/8 time.'),
        (
            StaffSpec(clef=Clef.TREBLE_8VB, key_signature=KeySignature(0), meter=Meter(3, 4)),
            'Treble staff an octave lower, no sharps or flats, 3/4 time.',
        ),
        (StaffSpec(clef=Clef.PERCUSSION), 'Percussion staff.'),
        (StaffSpec(lines=1), 'Single-line staff.'),
        (StaffSpec(key_signature=KeySignature(-7)), 'Treble staff, seven flats.'),
    ],
)
def test_headings(spec: StaffSpec, expected: str) -> None:
    assert describe(spec) == expected


def test_chords() -> None:
    spec = StaffSpec(events=(note('E4', 'G4', 'B4'),))
    assert describe(spec) == 'Treble staff. One chord: E4, G4, B4.'


def test_rhythm_and_events() -> None:
    triplet = Duration(NoteValue.EIGHTH, tuplet=Tuplet(3, 2))
    quintuplet = Duration(NoteValue.SIXTEENTH, tuplet=Tuplet(5, 4))
    spec = StaffSpec(
        meter=Meter(4, 4),
        events=(
            note('C4', d=Duration(NoteValue.QUARTER, 1)),
            note('D4', 'F4', d=Duration(NoteValue.HALF, 2), tie_to_next=True),
            Rest(Duration(NoteValue.EIGHTH)),
            note('E4', d=triplet),
            note('E4', d=quintuplet),
            Barline(),
            Barline(BarStyle.DOUBLE),
            Barline(BarStyle.FINAL),
            Barline(BarStyle.REPEAT_START),
            Barline(BarStyle.REPEAT_END),
        ),
    )
    assert describe(spec) == (
        'Treble staff, 4/4 time. Ten events: C4 dotted quarter, '
        'chord D4 F4 double-dotted half, tied, eighth rest, E4 eighth triplet, '
        'E4 16th in a 5:4 tuplet, bar line, double bar line, final bar line, '
        'start repeat, end repeat.'
    )


@pytest.mark.parametrize(
    ('value', 'name'),
    [
        (NoteValue.BREVE, 'breve'),
        (NoteValue.WHOLE, 'whole'),
        (NoteValue.THIRTY_SECOND, '32nd'),
        (NoteValue.SIXTY_FOURTH, '64th'),
    ],
)
def test_value_names(value: NoteValue, name: str) -> None:
    spec = StaffSpec(events=(Rest(Duration(value)),))
    assert describe(spec) == f'Treble staff. One event: {name} rest.'


def test_many_notes_use_digits() -> None:
    spec = StaffSpec.notes(*(['C4'] * 13))
    assert describe(spec).startswith('Treble staff. 13 notes: C4, C4')


def test_labels_marks_and_brackets() -> None:
    spec = StaffSpec(
        events=(
            Chord((Head(Pitch.parse('D4')),), label='1'),
            Chord((Head(Pitch.parse('G4'), halo=True),), label='4'),
            Chord((Head(Pitch.parse('A4'), ink=Ink.SUCCESS),)),
            Chord((Head(Pitch.parse('B4'), ink=Ink.ERROR),)),
        ),
        brackets=(Bracket(0, 1, '?'), Bracket(3, 3, '!')),
    )
    assert describe(spec) == (
        'Treble staff. Four notes: D4, G4, A4, B4. Labels: 1, 4. Highlighted: G4. '
        'Marked correct: A4. Marked wrong: B4. '
        'Bracket labelled “?” over events 1 to 2. Bracket labelled “!” at event 4.'
    )


def test_grand_staff_and_voices() -> None:
    upper = StaffSpec(events=(note('B4', d=Q),), voices=((note('G4', d=Q),),))
    lower = StaffSpec(clef=Clef.BASS, events=(note('D3', d=Q),), description='Bass part.')
    system = SystemSpec((upper, lower), labels=('S A', ''))
    assert describe(system) == (
        'Grand staff. S A: Treble staff. One event: B4 quarter. '
        'Lower voice: One event: G4 quarter. Bass part.'
    )


def test_other_systems() -> None:
    system = SystemSpec((StaffSpec(), StaffSpec(clef=Clef.ALTO), StaffSpec(clef=Clef.BASS)))
    assert describe(system) == 'System of 3 staves. Treble staff. Alto staff. Bass staff.'
