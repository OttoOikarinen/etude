# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random

import pytest

from etude.core import Chord
from etude.exercises.base import ChoiceAnswer
from etude.exercises.families.inversion_ear import (
    QUALITIES,
    InversionEar,
    parse_item,
    pitches_of,
)
from etude.notation.spec import StaffSpec, SystemSpec

EXERCISE = InversionEar()
ALL = {'qualities': ('major', 'minor', 'dim'), 'sevenths': 'all'}


def test_items_cover_quality_times_inversion() -> None:
    items = EXERCISE.items(EXERCISE.default_settings())
    assert items[:3] == [
        'inversion.ear.major.root',
        'inversion.ear.minor.root',
        'inversion.ear.major.first',
    ]
    assert len(items) == 6
    everything = EXERCISE.items({**EXERCISE.default_settings(), **ALL})
    assert len(everything) == 3 * 3 + 4 * 4
    assert not any('.aug.' in i or '.dim7.' in i for i in everything), 'symmetric chords'
    dominant = EXERCISE.items({**EXERCISE.default_settings(), 'sevenths': 'dominant'})
    assert 'inversion.ear.dom7.third' in dominant
    with pytest.raises(ValueError, match='not an inversion item'):
        parse_item('inversion.ear.major.third')


def test_confusables_stay_within_the_chord() -> None:
    assert EXERCISE.confusables('inversion.ear.major.first') == [
        'inversion.ear.major.second',
        'inversion.ear.major.root',
    ]
    assert 'inversion.ear.dom7.second' in EXERCISE.confusables('inversion.ear.dom7.third')


@pytest.mark.parametrize('voicing', ['close', 'keyboard'])
def test_the_bass_is_the_tone_of_the_inversion(voicing: str) -> None:
    settings = {**EXERCISE.default_settings(), **ALL, 'voicing': voicing}
    for item in EXERCISE.items(settings):
        quality_key, inversion = parse_item(item)
        for seed in range(4):
            question = EXERCISE.generate(item, settings, random.Random(seed))
            figure = question.written_alternative
            if voicing == 'keyboard':
                assert isinstance(figure, SystemSpec)
            else:
                assert isinstance(figure, StaffSpec)
            pitches = pitches_of(figure)
            chord = next(c for c in Chord.identify(pitches) if c.quality is QUALITIES[quality_key])
            assert chord.inversion == inversion
            assert pitches[0].name == chord.bass
            assert {p.name for p in pitches} == set(chord.names()), 'complete chord'
            assert question.playback is not None
            assert min(n.midi for n in question.playback.notes) == pitches[0].midi
            assert question.context.lower() in (
                'major triad',
                'minor triad',
                'diminished triad',
                'dominant seventh',
                'major seventh',
                'minor seventh',
                'half-diminished seventh',
            )


def test_feedback_compares_bass_notes() -> None:
    settings = {**EXERCISE.default_settings(), **ALL, 'voicing': 'keyboard'}
    question = EXERCISE.generate('inversion.ear.dom7.second', settings, random.Random(3))
    assert isinstance(question.answer, ChoiceAnswer)
    assert [o.description for o in question.answer.options] == ['7', '6/5', '4/3', '4/2']
    right = EXERCISE.grade(question, 'second')
    assert right.correct
    assert 'The fifth' in right.detail
    assert '(4/3)' in right.detail
    wrong = EXERCISE.grade(question, 'root')
    assert not wrong.correct
    assert wrong.play_given is not None
    assert question.playback is not None
    expected_bass = min(n.midi for n in question.playback.notes)
    given_bass = min(n.midi for n in wrong.play_given.notes)
    assert expected_bass != given_bass
    assert abs(expected_bass - given_bass) <= 6
