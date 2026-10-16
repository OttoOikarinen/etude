# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random

import pytest

from etude.core import KeySignature
from etude.core.scale import Mode
from etude.exercises.base import ChoiceAnswer
from etude.exercises.families.key_signatures import (
    KeySignatures,
    item_id,
    key_for,
    parse_item,
)
from etude.notation.spec import Clef, StaffSpec

EXERCISE = KeySignatures()
DEFAULTS = EXERCISE.default_settings()


@pytest.mark.parametrize('mode', list(Mode))
@pytest.mark.parametrize('fifths', range(-7, 8))
def test_item_ids_round_trip(mode: Mode, fifths: int) -> None:
    assert parse_item(item_id(mode, fifths)) == (mode, fifths)


@pytest.mark.parametrize(
    'text', ['keysig.major.8s', 'keysig.major.3x', 'notes.major.0', 'keysig', 'keysig.dorian.1s']
)
def test_bad_item_ids_are_rejected(text: str) -> None:
    with pytest.raises(ValueError, match='not a key signature item'):
        parse_item(text)


def test_teaching_order_alternates_sharps_and_flats() -> None:
    items = EXERCISE.items({**DEFAULTS, 'max-accidentals': 2})
    assert items == [
        'keysig.major.0',
        'keysig.major.1s',
        'keysig.major.1b',
        'keysig.major.2s',
        'keysig.major.2b',
    ]


def test_both_modes_cover_major_then_minor() -> None:
    items = EXERCISE.items({**DEFAULTS, 'mode': 'both', 'max-accidentals': 0})
    assert items == ['keysig.major.0', 'keysig.minor.0']


@pytest.mark.parametrize(
    ('mode', 'fifths', 'tonic'),
    [
        (Mode.MAJOR, 4, 'E'),
        (Mode.MAJOR, -3, 'Eb'),
        (Mode.MINOR, 4, 'C#'),
        (Mode.MINOR, -6, 'Eb'),
        (Mode.MAJOR, 7, 'C#'),
        (Mode.MINOR, 0, 'A'),
    ],
)
def test_keys(mode: Mode, fifths: int, tonic: str) -> None:
    key = key_for(mode, fifths)
    assert key.mode is mode
    assert key.tonic.symbol == tonic.replace('#', '♯').replace('b', '♭')


def test_design_question() -> None:
    """Design 1b: four sharps in the treble clef, options C to C♯ major."""
    settings = {**DEFAULTS, 'clefs': ('treble',), 'max-accidentals': 7}
    question = EXERCISE.generate(item_id(Mode.MAJOR, 4), settings, random.Random(1))
    assert question.prompt == 'Which major key is written here?'
    assert isinstance(question.figure, StaffSpec)
    assert question.figure.clef is Clef.TREBLE
    assert question.figure.key_signature == KeySignature(4)
    assert isinstance(question.answer, ChoiceAnswer)
    labels = [o.label for o in question.answer.options]
    assert labels == [
        'C major',
        'G major',
        'D major',
        'A major',
        'E major',
        'B major',
        'F♯ major',
        'C♯ major',
    ]
    assert [o.accel for o in question.answer.options] == [str(n) for n in range(1, 9)]
    assert question.expected == '4'


def test_flat_signatures_offer_flat_keys() -> None:
    question = EXERCISE.generate(item_id(Mode.MAJOR, -2), DEFAULTS, random.Random(0))
    assert isinstance(question.answer, ChoiceAnswer)
    assert [o.label for o in question.answer.options] == [
        'C major',
        'F major',
        'B♭ major',
        'E♭ major',
        'A♭ major',
        'D♭ major',
    ]


def test_feedback_explains_the_rule() -> None:
    question = EXERCISE.generate(item_id(Mode.MAJOR, 4), DEFAULTS, random.Random(0))
    right = EXERCISE.grade(question, '4')
    assert right.correct
    assert right.title == 'Correct — E major'
    assert 'D♯' in right.detail
    assert 'leading note' in right.detail
    wrong = EXERCISE.grade(question, '3')
    assert not wrong.correct
    assert wrong.title == 'Not quite — the answer is E major'


def test_flat_feedback_names_the_second_to_last_flat() -> None:
    question = EXERCISE.generate(item_id(Mode.MAJOR, -3), DEFAULTS, random.Random(0))
    detail = EXERCISE.grade(question, '-3').detail
    assert 'B♭ E♭ A♭' in detail
    assert 'E♭ major' in detail


def test_minor_feedback_mentions_the_relative_minor() -> None:
    question = EXERCISE.generate(item_id(Mode.MINOR, 1), DEFAULTS, random.Random(0))
    feedback = EXERCISE.grade(question, '1')
    assert feedback.title == 'Correct — E minor'
    assert 'E minor' in feedback.detail


def test_clef_varies_with_settings() -> None:
    settings = {**DEFAULTS, 'clefs': ('alto', 'tenor')}
    clefs = set()
    for seed in range(20):
        question = EXERCISE.generate(item_id(Mode.MAJOR, 2), settings, random.Random(seed))
        assert isinstance(question.figure, StaffSpec)
        clefs.add(question.figure.clef)
    assert clefs == {Clef.ALTO, Clef.TENOR}


def test_scale_playback_is_in_a_comfortable_range() -> None:
    for fifths in range(-7, 8):
        question = EXERCISE.generate(item_id(Mode.MAJOR, fifths), DEFAULTS, random.Random(0))
        assert question.playback is not None
        midis = [n.midi for n in question.playback.notes]
        assert len(midis) == 8
        assert min(midis) >= 55
        assert max(midis) <= 84


def test_describe_settings() -> None:
    text = EXERCISE.describe_settings({**DEFAULTS, 'clefs': ('treble',)})
    assert text == 'Treble clef · up to 5 accidentals'
