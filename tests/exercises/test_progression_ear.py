# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random

import pytest

from etude.core.scale import Mode
from etude.exercises.base import ChoiceAnswer
from etude.exercises.families.four_part import key_of, parse_numerals, voicings_of
from etude.exercises.families.progression_ear import (
    MAJOR,
    MINOR,
    PROGRESSIONS,
    ProgressionEar,
    changes,
    label,
    mode_of,
)

EXERCISE = ProgressionEar()


def test_labels_use_proper_symbols() -> None:
    assert label('i-iio6-V-i') == 'i–ii°⁶–V–i'
    assert label('I-vi-IV-V') == 'I–vi–IV–V'
    assert all(label(p) for p in PROGRESSIONS)


def test_progression_modes_match_their_numerals() -> None:
    for progression in MAJOR:
        assert mode_of(progression) is Mode.MAJOR
        assert progression.split('-')[-1] in ('I', 'V', 'IV')
    for progression in MINOR:
        assert mode_of(progression) is Mode.MINOR
        assert progression.startswith('i-')


def test_items_follow_mode_and_selection() -> None:
    defaults = EXERCISE.default_settings()
    assert [i.removeprefix('progression.ear.') for i in EXERCISE.items(defaults)] == list(MAJOR)
    minor = EXERCISE.items({**defaults, 'mode': 'minor'})
    assert [i.removeprefix('progression.ear.') for i in minor] == list(MINOR)
    chosen = EXERCISE.items({**defaults, 'mode': 'both', 'progressions': ('ii-V-I', 'i-VII-VI-V')})
    assert chosen == ['progression.ear.ii-V-I', 'progression.ear.i-VII-VI-V']
    # A selection with nothing in the chosen keys falls back to all of them.
    fallback = EXERCISE.items({**defaults, 'progressions': ('i-VII-VI-V',)})
    assert len(fallback) == len(MAJOR)


@pytest.mark.parametrize('progression', PROGRESSIONS)
def test_naming_questions_offer_same_mode_progressions(progression: str) -> None:
    settings = {**EXERCISE.default_settings(), 'mode': 'both'}
    question = EXERCISE.generate(f'progression.ear.{progression}', settings, random.Random(1))
    assert isinstance(question.answer, ChoiceAnswer)
    keys = [o.key for o in question.answer.options]
    assert progression in keys
    assert all(mode_of(k) is mode_of(progression) for k in keys)
    assert len(keys) >= 3
    key = key_of(question.written_alternative)
    assert key is not None
    assert key.mode is mode_of(progression)
    assert len(voicings_of(question.written_alternative)) == len(progression.split('-'))
    for other in keys:
        feedback = EXERCISE.grade(question, other)
        assert feedback.correct is (other == progression)
        if other != progression:
            assert feedback.play_given is not None
            assert (
                'Compared with your answer' in feedback.detail
                or 'Count the chords' in feedback.detail
            )


@pytest.mark.parametrize('progression', PROGRESSIONS)
def test_spot_the_change_changes_exactly_one_chord(progression: str) -> None:
    settings = {**EXERCISE.default_settings(), 'mode': 'both', 'task': 'change'}
    assert changes(progression)
    for seed in range(5):
        question = EXERCISE.generate(
            f'progression.ear.{progression}', settings, random.Random(seed)
        )
        assert isinstance(question.answer, ChoiceAnswer)
        assert [o.key for o in question.answer.options] == [
            str(i + 1) for i in range(len(progression.split('-')))
        ]
        heard = EXERCISE._heard(
            progression,
            key_of(question.written_alternative),
            voicings_of(question.written_alternative),
        )
        written, played = parse_numerals(progression), parse_numerals(heard)
        differing = [i for i, (a, b) in enumerate(zip(written, played, strict=True)) if a != b]
        assert differing == [int(str(question.expected)) - 1]
        assert differing[0] != 0, 'the first chord sets the key and never changes'
        right = EXERCISE.grade(question, question.expected)
        assert right.correct
        assert 'instead of the written' in right.detail
        wrong = EXERCISE.grade(question, '1')
        assert not wrong.correct
        assert wrong.play_given is not None


def test_changes_differ_from_their_neighbours() -> None:
    for progression in PROGRESSIONS:
        chords = progression.split('-')
        for index, substitute in changes(progression):
            assert substitute != chords[index]
            assert substitute != chords[index - 1]
            if index + 1 < len(chords):
                assert substitute != chords[index + 1]
