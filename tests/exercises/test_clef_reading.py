# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Clef Reading: melodies rewritten in another clef at the same pitch."""

from __future__ import annotations

import random

import pytest

from etude.core import Interval, Pitch
from etude.exercises.base import StaffInputAnswer
from etude.exercises.families.clef_reading import (
    PAIRS,
    ClefReading,
    item_id,
    pair_clefs,
    pair_label,
    parse_item,
)
from etude.exercises.families.note_naming import full_name
from etude.notation.spec import Chord as StaffChord
from etude.notation.spec import Clef, StaffSpec

CLEF_READING = ClefReading()
OCTAVE = Interval.parse('P8')


def test_items_follow_the_settings() -> None:
    assert CLEF_READING.items(CLEF_READING.default_settings()) == [item_id(p) for p in PAIRS]
    assert CLEF_READING.items({'pairs': ('tenor-bass',)}) == ['clef.rewrite.tenor-bass']
    assert CLEF_READING.items({'pairs': ()}) == [item_id(p) for p in PAIRS]
    assert parse_item('clef.rewrite.alto-treble') == 'alto-treble'
    with pytest.raises(ValueError, match='not a clef reading item'):
        parse_item('clef.rewrite.treble-treble')
    assert pair_label('alto-treble') == 'Alto clef → treble clef'
    assert CLEF_READING.describe_settings({}) == 'Alto and tenor clefs · 5 notes'
    assert CLEF_READING.describe_settings({'pairs': ('tenor-bass',), 'notes': 3}) == (
        'Tenor clef → bass clef · 3 notes'
    )


def test_the_c_clefs_mark_middle_c_as_the_feedback_says() -> None:
    middle_c = Pitch.parse('C4')
    assert Clef.ALTO.staff_position(middle_c) == 4  # the middle line
    assert Clef.TENOR.staff_position(middle_c) == 6  # the fourth line
    assert Clef.TREBLE.staff_position(middle_c) == -2  # one ledger line below
    assert Clef.BASS.staff_position(middle_c) == 10  # one ledger line above


@pytest.mark.parametrize('pair', PAIRS)
def test_the_melody_fits_both_staves_and_keeps_its_pitches(pair: str) -> None:
    source, target = pair_clefs(pair)
    for seed in range(30):
        question = CLEF_READING.generate(item_id(pair), {}, random.Random(seed))
        figure = question.figure
        answer = question.answer
        assert isinstance(figure, StaffSpec)
        assert isinstance(answer, StaffInputAnswer)
        assert (figure.clef, answer.clef) == (source, target)
        assert figure.key_signature == answer.key_signature
        written = [e.heads[0].pitch for e in figure.events if isinstance(e, StaffChord)]
        assert question.expected == tuple((p,) for p in written)
        assert answer.slots == len(written) == 5
        for clef in (source, target):
            positions = [clef.staff_position(p) for p in written]
            assert min(positions) >= -4, (pair, seed)
            assert max(positions) <= 12, (pair, seed)
        assert all(abs(p.alter) <= 1 for p in written)
        assert f'the {target.value} clef' in question.prompt


def test_grading_names_octave_and_spelling_mistakes() -> None:
    question = CLEF_READING.generate('clef.rewrite.alto-treble', {}, random.Random(3))
    expected = [c[0] for c in question.expected]  # type: ignore[union-attr]
    assert CLEF_READING.grade(question, question.expected).correct
    low = [(p.transpose(OCTAVE, down=True),) if i == 1 else (p,) for i, p in enumerate(expected)]
    feedback = CLEF_READING.grade(question, tuple(low))
    assert not feedback.correct
    assert feedback.score == pytest.approx(1 - 1 / len(expected))
    assert 'Note 2: ' in feedback.detail
    assert 'is an octave too low' in feedback.detail
    assert 'In the alto clef middle C (C4) is the middle line.' in feedback.detail
    assert feedback.play_given is not None
    respelled = expected[0].transpose(Interval.parse('d2'))
    assert respelled.midi == expected[0].midi
    spelled = ((respelled,), *((p,) for p in expected[1:]))
    assert 'sounds right, but the note is spelled' in CLEF_READING.grade(question, spelled).detail
    high = ((expected[0].transpose(OCTAVE),), *((p,) for p in expected[1:]))
    assert 'is an octave too high' in CLEF_READING.grade(question, high).detail
    assert CLEF_READING.grade(question, ()).score == 0
    # Notes left out are named; two notes in one place are not read note by note.
    short = CLEF_READING.grade(question, tuple((p,) for p in expected[:3]))
    assert f'Note 4 ({full_name(expected[3])}) is missing.' in short.detail
    assert short.score == pytest.approx(3 / len(expected))
    doubled = ((expected[0], expected[1]), *((p,) for p in expected[1:]))
    assert 'Write one note in each place.' in CLEF_READING.grade(question, doubled).detail
