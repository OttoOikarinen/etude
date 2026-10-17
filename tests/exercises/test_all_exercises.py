# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Checks every registered exercise must pass.

These run automatically for each module in ``etude.exercises.families``,
so a new exercise is covered as soon as it is registered. Exercise-specific
tests (musical correctness of questions and explanations) live next to this
file, one module per family.
"""

from __future__ import annotations

import random
from collections.abc import Iterator, Mapping

import pytest

from etude.core import Pitch, PitchName
from etude.exercises.base import (
    BoolSetting,
    ChipsAnswer,
    ChoiceAnswer,
    ChoiceSetting,
    ExerciseDefinition,
    IntSetting,
    Modality,
    MultiChoiceSetting,
    PianoAnswer,
    Question,
    StaffInputAnswer,
    TextAnswer,
)
from etude.exercises.registry import default_registry

EXERCISES = list(default_registry())
SEEDS = range(4)
MAX_ITEMS = 80


def _ids(definition: ExerciseDefinition) -> str:
    return definition.id


def setting_variants(definition: ExerciseDefinition) -> Iterator[dict[str, object]]:
    """The defaults, then each setting at its extremes or at each of its options."""
    defaults = definition.default_settings()
    yield defaults
    for setting in definition.settings:
        values: list[object]
        if isinstance(setting, IntSetting):
            values = [setting.minimum, setting.maximum]
        elif isinstance(setting, BoolSetting):
            values = [not setting.default]
        elif isinstance(setting, ChoiceSetting):
            values = [o.key for o in setting.options if o.key != setting.default]
        elif isinstance(setting, MultiChoiceSetting):
            values = [(o.key,) for o in setting.options]
            values.append(tuple(o.key for o in setting.options))
        for value in values:
            yield {**defaults, setting.key: value}


def sampled_items(definition: ExerciseDefinition, settings: Mapping[str, object]) -> list[str]:
    items = list(definition.items(settings))
    if len(items) <= MAX_ITEMS:
        return items
    return random.Random(0).sample(items, MAX_ITEMS)


def chip_values(answer: ChipsAnswer, value: object) -> None:
    assert isinstance(value, Mapping)
    assert set(value) == {g.key for g in answer.groups}
    for group in answer.groups:
        chosen = str(value[group.key])
        keys = {o.key for o in group.options}
        if group.accidentals:
            assert chosen.rstrip('#b') in keys
        else:
            assert chosen in keys


def check_expected(question: Question) -> None:
    answer = question.answer
    if isinstance(answer, ChoiceAnswer):
        keys = [o.key for o in answer.options]
        assert len(keys) == len(set(keys)), 'option keys must be unique'
        accels = [o.accel for o in answer.options if o.accel]
        assert len(accels) == len(set(accels)), 'accelerators must be unique'
        assert question.expected in keys
        assert set(answer.targets.values()) <= set(keys)
    elif isinstance(answer, ChipsAnswer):
        chip_values(answer, question.expected)
    elif isinstance(answer, PianoAnswer):
        if answer.octave_matters:
            assert isinstance(question.expected, Pitch)
            assert answer.low.midi <= question.expected.midi <= answer.high.midi
        else:
            assert isinstance(question.expected, PitchName)
    elif isinstance(answer, TextAnswer):
        assert isinstance(question.expected, str)
        assert question.expected.strip()
    elif isinstance(answer, StaffInputAnswer):
        expected = question.expected
        assert isinstance(expected, tuple), 'staff answers are tuples of chords'
        assert all(isinstance(c, tuple) and c for c in expected)
        assert all(isinstance(p, Pitch) for c in expected for p in c)
        if answer.slots is not None:
            assert len(expected) == answer.slots


def wrong_answers(question: Question) -> list[object]:
    answer = question.answer
    if isinstance(answer, ChoiceAnswer):
        return [o.key for o in answer.options if o.key != question.expected]
    if isinstance(answer, TextAnswer):
        return ['definitely not the answer']
    if isinstance(answer, StaffInputAnswer):
        assert isinstance(question.expected, tuple)
        first = question.expected[0][0]
        rest = question.expected[1:]
        step = Pitch.from_diatonic(first.diatonic_index + 1, first.midi + 2)
        wrong: list[object] = [((step,), *rest), (), 'not notes']
        enharmonic = [p for p in first.enharmonics(max_alter=1) if p != first]
        wrong += [((p,), *rest) for p in enharmonic]
        return wrong
    return []


@pytest.mark.parametrize('definition', EXERCISES, ids=_ids)
def test_metadata(definition: ExerciseDefinition) -> None:
    assert definition.id
    assert definition.item_prefix.endswith('.')
    assert definition.title.strip()
    assert definition.description.strip()
    assert definition.play_label.strip()
    assert 1 <= definition.level <= 4
    assert isinstance(definition.modality, Modality)
    keys = [s.key for s in definition.settings]
    assert len(keys) == len(set(keys)), 'setting keys must be unique'


@pytest.mark.parametrize('definition', EXERCISES, ids=_ids)
def test_items_belong_to_the_exercise(definition: ExerciseDefinition) -> None:
    registry = default_registry()
    for settings in setting_variants(definition):
        items = list(definition.items(settings))
        assert len(items) == len(set(items)), 'items must be unique'
        for item in items:
            assert item.startswith(definition.item_prefix)
            assert registry.exercise_for(item) == definition.id
    assert definition.items(definition.default_settings()), 'defaults must cover some items'


@pytest.mark.parametrize('definition', EXERCISES, ids=_ids)
def test_questions_are_well_formed_and_gradable(definition: ExerciseDefinition) -> None:
    for settings in setting_variants(definition):
        for item in sampled_items(definition, settings):
            for seed in SEEDS:
                question = definition.generate(item, settings, random.Random(seed))
                again = definition.generate(item, settings, random.Random(seed))
                assert question == again, 'generate() must be deterministic for a seed'
                assert question.item_id == item
                assert question.exercise_id == definition.id
                assert question.prompt.strip()
                check_expected(question)
                if question.playback_is_question:
                    assert question.playback is not None
                    assert question.written_alternative is not None

                right = definition.grade(question, question.expected)
                assert right.correct, f'{item}: the expected answer must grade as correct'
                assert right.title.strip()
                for wrong in wrong_answers(question):
                    feedback = definition.grade(question, wrong)
                    assert not feedback.correct
                    assert feedback.title.strip()
                assert definition.answer_label(question, question.expected).strip()
                assert isinstance(definition.serialize(question.expected), str)


@pytest.mark.parametrize('definition', EXERCISES, ids=_ids)
def test_describe_settings_is_text(definition: ExerciseDefinition) -> None:
    for settings in setting_variants(definition):
        assert isinstance(definition.describe_settings(settings), str)
