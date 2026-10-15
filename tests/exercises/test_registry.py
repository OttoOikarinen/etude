# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random
from collections.abc import Mapping, Sequence

import pytest

from etude.exercises.base import (
    ChoiceAnswer,
    ExerciseDefinition,
    Family,
    Feedback,
    IntSetting,
    Modality,
    Option,
    Question,
)
from etude.exercises.registry import ExerciseRegistry, default_registry
from etude.learning.model import ItemId


class Counting(ExerciseDefinition):
    """A minimal exercise: how many items are there?"""

    id = 'counting'
    item_prefix = 'count.'
    family = Family.NOTATION
    modality = Modality.EYE
    level = 1
    icon_name = 'view-grid-symbolic'
    settings = (IntSetting('highest', 'Highest number', default=3, minimum=1, maximum=9),)

    @property
    def title(self) -> str:
        return 'Counting'

    @property
    def description(self) -> str:
        return 'Count things.'

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        highest = settings['highest']
        assert isinstance(highest, int)
        return [ItemId(f'count.{n}') for n in range(1, highest + 1)]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        n = item_id.removeprefix('count.')
        options = tuple(Option(str(i), str(i), accel=str(i)) for i in range(1, 4))
        return Question(self.id, item_id, f'How many? {"●" * int(n)}', ChoiceAnswer(options), n)

    def grade(self, question: Question, given: object) -> Feedback:
        correct = given == question.expected
        return Feedback(correct, 'Correct' if correct else 'Not quite')


class Overlapping(Counting):
    id = 'overlapping'
    item_prefix = 'count.big.'


def test_registry_lookup_and_catalog() -> None:
    registry = ExerciseRegistry([Counting()])
    assert len(registry) == 1
    assert registry.get('counting').title == 'Counting'
    assert registry.by_family(Family.NOTATION)[0].id == 'counting'
    assert registry.by_family(Family.EAR) == []
    assert registry.exercise_ids() == ['counting']
    assert registry.items('counting', {}) == ['count.1', 'count.2', 'count.3']
    assert registry.items('counting', {'highest': 2}) == ['count.1', 'count.2']
    assert registry.exercise_for(ItemId('count.2')) == 'counting'
    with pytest.raises(KeyError):
        registry.exercise_for(ItemId('keysig.major.2s'))


def test_duplicate_ids_and_overlapping_prefixes_are_rejected() -> None:
    registry = ExerciseRegistry([Counting()])
    with pytest.raises(ValueError, match='already registered'):
        registry.register(Counting())
    with pytest.raises(ValueError, match='overlaps'):
        registry.register(Overlapping())


def test_round_trip_through_definition() -> None:
    exercise = Counting()
    question = exercise.generate(ItemId('count.2'), exercise.default_settings(), random.Random(1))
    assert exercise.grade(question, '2').correct
    assert not exercise.grade(question, '3').correct
    assert exercise.serialize('2') == '2'


def test_default_registry_loads_every_family_module() -> None:
    registry = default_registry()
    assert registry is default_registry()
    for definition in registry:
        assert definition.items(definition.default_settings()), definition.id
