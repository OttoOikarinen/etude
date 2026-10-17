# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random

import pytest

from etude.core import Interval, Pitch
from etude.exercises.base import StaffInputAnswer
from etude.exercises.families.interval_construction import (
    WRITABLE,
    IntervalConstruction,
    item_id,
    parse_item,
)
from etude.notation.spec import Chord, StaffSpec

EXERCISE = IntervalConstruction()
DEFAULTS = EXERCISE.default_settings()
BOTH = {**DEFAULTS, 'direction': 'both', 'altered': True}


def given_note(q) -> Pitch:
    answer = q.answer
    assert isinstance(answer, StaffInputAnswer)
    assert isinstance(answer.given, StaffSpec)
    chord = answer.given.events[0]
    assert isinstance(chord, Chord)
    return chord.heads[0].pitch


def test_no_tritone_items_and_directions() -> None:
    assert 'TT' not in WRITABLE
    items = EXERCISE.items(BOTH)
    assert items[0] == 'interval.write.above.P5'
    assert 'interval.write.below.m3' in items
    assert 'interval.write.above.A4' in items
    assert not any(i.endswith('.TT') for i in items)
    assert parse_item(item_id('below', 'M6')) == ('below', 'M6')
    with pytest.raises(ValueError, match='not an interval-construction item'):
        parse_item('interval.write.above.TT')


@pytest.mark.parametrize('item', EXERCISE.items(BOTH))
def test_expected_note_spells_the_interval(item: str) -> None:
    direction, key = parse_item(item)
    for seed in range(12):
        q = EXERCISE.generate(item, BOTH, random.Random(seed))
        start = given_note(q)
        (answer,) = q.expected[0]
        low, high = (start, answer) if direction == 'above' else (answer, start)
        assert Interval.between(low, high) == Interval.parse(key)
        assert abs(start.alter) <= 1
        assert abs(answer.alter) <= 1


def test_prompt_articles() -> None:
    q = EXERCISE.generate('interval.write.above.M6', DEFAULTS, random.Random(0))
    assert q.prompt.startswith('Write a major sixth above ')
    q = EXERCISE.generate('interval.write.below.A4', BOTH, random.Random(0))
    assert q.prompt.startswith('Write an augmented fourth below ')


def _question_from(start: str):
    """A major sixth above ``start``, whatever the seed chose."""
    for seed in range(400):
        q = EXERCISE.generate('interval.write.above.M6', DEFAULTS, random.Random(seed))
        if given_note(q) == Pitch.parse(start):
            return q
    raise AssertionError(f'no question from {start}')


def test_enharmonic_answer_is_wrong_with_a_spelling_explanation() -> None:
    q = _question_from('G4')
    assert q.expected == ((Pitch.parse('E5'),),)
    feedback = EXERCISE.grade(q, ((Pitch.parse('Fb5'),),))
    assert not feedback.correct
    assert feedback.detail.startswith(
        'Right sound, wrong spelling: a major sixth spans six letter names'
    )
    assert 'G A B C D E' in feedback.detail
    assert EXERCISE.grade(q, q.expected).correct


@pytest.mark.parametrize(
    ('written', 'fact'),
    [
        ('Eb5', 'E♭5 makes a minor sixth: the right letter names, but eight semitones instead'),
        ('F5', 'F5 makes a minor seventh, which spans seven letter names'),
        ('E4', 'E4 is not above G4'),
    ],
)
def test_wrong_answers_are_named(written: str, fact: str) -> None:
    q = _question_from('G4')
    feedback = EXERCISE.grade(q, ((Pitch.parse(written),),))
    assert not feedback.correct
    assert fact in feedback.detail
    assert 'G4 to E5 spans six letter names and nine semitones: a major sixth.' in feedback.detail
    assert feedback.play_given is not None


def test_confusables_keep_direction() -> None:
    assert EXERCISE.confusables('interval.write.below.M6') == [
        'interval.write.below.m6',
        'interval.write.below.m7',
    ]
    assert 'interval.write.above.TT' not in EXERCISE.confusables('interval.write.above.P5')


def test_no_accidentals_setting_writes_naturals_where_possible() -> None:
    settings = {**DEFAULTS, 'accidentals': 'none'}
    for seed in range(20):
        q = EXERCISE.generate('interval.write.above.P5', settings, random.Random(seed))
        assert given_note(q).alter == 0
