# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random

import pytest

from etude.core import Key, Mode, PitchName
from etude.exercises.base import ChoiceAnswer
from etude.exercises.families.degree_ear import (
    DegreeEar,
    cadence,
    item_id,
    parse_item,
    tonic_pitch,
)
from etude.exercises.registry import default_registry
from etude.notation.spec import Chord, StaffSpec

EXERCISE = DegreeEar()
DEFAULTS = EXERCISE.default_settings()
BOTH = {**DEFAULTS, 'mode': 'both'}


def test_items_do_not_overlap_the_eye_exercise() -> None:
    registry = default_registry()
    assert registry.exercise_for('degree-ear.major.5') == 'degree-ear'
    assert registry.exercise_for('degree.major.5') == 'scale-degree'
    assert EXERCISE.items(DEFAULTS)[:3] == [
        'degree-ear.major.1',
        'degree-ear.major.5',
        'degree-ear.major.4',
    ]
    assert parse_item(item_id(Mode.MINOR, 3)) == (Mode.MINOR, 3)
    with pytest.raises(ValueError, match='not a scale-degree ear item'):
        parse_item('degree-ear.major.8')


@pytest.mark.parametrize('item', EXERCISE.items(BOTH))
def test_the_last_note_is_the_degree(item: str) -> None:
    mode, degree = parse_item(item)
    for seed in range(6):
        q = EXERCISE.generate(item, BOTH, random.Random(seed))
        figure = q.written_alternative
        assert isinstance(figure, StaffSpec)
        assert figure.key_signature is not None
        signature = figure.key_signature
        tonic = signature.major_tonic if mode is Mode.MAJOR else signature.minor_tonic
        key = Key(tonic, mode)
        chord = figure.events[0]
        assert isinstance(chord, Chord)
        note = chord.heads[0].pitch
        assert key.scale.degree_of(note.name) == degree
        assert q.playback is not None
        assert q.playback.notes[-1].midi == note.midi
        assert q.context == f'Key: {key.tonic.symbol} {mode.value}'


def test_minor_degree_names() -> None:
    q = EXERCISE.generate('degree-ear.minor.7', {**DEFAULTS, 'mode': 'minor'}, random.Random(0))
    assert isinstance(q.answer, ChoiceAnswer)
    captions = [o.description for o in q.answer.options]
    assert captions == ['Tonic', 'Supert.', 'Mediant', 'Subdom.', 'Dominant', 'Submed.', 'Subtonic']
    feedback = EXERCISE.grade(q, '3')
    assert feedback.title == 'Not quite — the answer is 7, the subtonic'
    assert 'becomes the leading tone' in feedback.detail
    assert feedback.play_given is not None


def test_minor_cadence_has_a_major_dominant() -> None:
    key = Key(PitchName.parse('A'), Mode.MINOR)
    spec = cadence(key, tonic_pitch(key))
    beats = sorted({n.start for n in spec.notes})
    assert len(beats) == 4
    dominant = {n.midi % 12 for n in spec.notes if n.start == beats[2]}
    assert dominant == {4, 8, 11}  # E G♯ B
    tonic = {n.midi % 12 for n in spec.notes if n.start == beats[0]}
    assert tonic == {9, 0, 4}  # A C E


def test_scale_context() -> None:
    q = EXERCISE.generate('degree-ear.major.3', {**DEFAULTS, 'context': 'scale'}, random.Random(0))
    assert q.playback is not None
    assert len(q.playback.notes) == 9
    feedback = EXERCISE.grade(q, '5')
    assert feedback.play_given is not None
    assert len(feedback.play_given.notes) == 9
