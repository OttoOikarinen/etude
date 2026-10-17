# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random

import pytest

from etude.core import Pitch
from etude.exercises.base import StaffInputAnswer
from etude.exercises.families.note_placement import (
    NotePlacement,
    compare_written,
    item_id,
    parse_item,
    staff_value_text,
    written_note,
)
from etude.notation.spec import Clef

EXERCISE = NotePlacement()
DEFAULTS = EXERCISE.default_settings()


def question(item: str, seed: int = 0):
    return EXERCISE.generate(item, DEFAULTS, random.Random(seed))


def test_items_follow_note_naming_order() -> None:
    items = EXERCISE.items(DEFAULTS)
    assert items[:2] == ['place.treble.G4', 'place.bass.F3']
    assert all(i.startswith('place.') for i in items)
    accidentals = EXERCISE.items({**DEFAULTS, 'accidentals': True})
    assert 'place.treble.F#4' in accidentals
    assert 'place.treble.E#4' not in accidentals  # a white key


@pytest.mark.parametrize('text', ['place.treble.E#4', 'place.treble.C2', 'note.treble.C4'])
def test_bad_items(text: str) -> None:
    with pytest.raises(ValueError, match='not a note-placement item'):
        parse_item(text)


def test_round_trip() -> None:
    assert parse_item(item_id(Clef.BASS, Pitch.parse('Bb2'))) == (Clef.BASS, Pitch.parse('Bb2'))


def test_question_asks_for_the_note_on_an_empty_staff() -> None:
    q = question('place.treble.F#4')
    assert q.prompt == 'Write F♯4 on the staff'
    assert q.answer == StaffInputAnswer(clef=Clef.TREBLE, slots=1)
    assert q.expected == ((Pitch.parse('F#4'),),)
    assert q.figure is None


def test_exact_spelling_and_octave() -> None:
    q = question('place.treble.F#4')
    assert EXERCISE.grade(q, ((Pitch.parse('F#4'),),)).correct
    for wrong in ('Gb4', 'F4', 'F#5'):
        assert not EXERCISE.grade(q, ((Pitch.parse(wrong),),)).correct


@pytest.mark.parametrize(
    ('expected', 'written', 'fact'),
    [
        ('F#4', 'F4', 'right line or space, but F♯4 needs a sharp'),
        ('Bb3', 'B3', 'needs a flat'),
        ('F4', 'F#4', 'has no sharp or flat'),
        ('F#4', 'Gb4', 'same key on the piano'),
        ('G4', 'G5', 'right letter in the wrong octave'),
        ('F4', 'G4', 'G4, one step too high'),
        ('F4', 'C4', 'C4, three steps too low'),
    ],
)
def test_comparisons(expected: str, written: str, fact: str) -> None:
    assert fact in compare_written(Pitch.parse(expected), Pitch.parse(written))


def test_feedback_explains_the_position() -> None:
    q = question('place.treble.F4')
    feedback = EXERCISE.grade(q, ((Pitch.parse('G4'),),))
    assert feedback.title == 'Not quite — the answer is F4'
    assert 'F4 is in the first space of the treble staff.' in feedback.detail
    assert feedback.play_given is not None
    ledger = question('place.treble.C4')
    assert 'first ledger line below' in EXERCISE.grade(ledger, ledger.expected).detail


def test_value_helpers() -> None:
    value = ((Pitch.parse('C4'), Pitch.parse('E4')), (Pitch.parse('G4'),))
    assert staff_value_text(value) == 'C4 E4 | G4'
    assert written_note(value) is None
    assert written_note(((Pitch.parse('C4'),),)) == Pitch.parse('C4')
    assert written_note('C4') is None
