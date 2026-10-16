# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import timedelta

import pytest
from tests.learning.fakes import FakeAttemptLog, FakeCardStore, outcome, utc

from etude.learning.mastery import Mastery, MasteryConfig
from etude.learning.model import Card, CardState, ItemId

NOW = utc(2026, 10, 15, 9)


def setup(cards: list[Card], answers: dict[str, list[bool]]) -> Mastery:
    attempts = FakeAttemptLog()
    for item, results in answers.items():
        for n, correct in enumerate(results):
            attempts.add(outcome(item, NOW + timedelta(minutes=n), correct=correct), None)
    return Mastery(FakeCardStore(cards), attempts)


def card(item: str, stability: float | None, state: CardState = CardState.REVIEW) -> Card:
    return Card(ItemId(item), NOW, state, stability=stability)


@pytest.mark.parametrize(
    ('state', 'stability', 'answers', 'mastered'),
    [
        (CardState.REVIEW, 21.0, [True] * 10, True),
        (CardState.REVIEW, 60.0, [False] + [True] * 9, True),  # exactly 90 %
        (CardState.REVIEW, 20.9, [True] * 10, False),  # not durable yet
        (CardState.RELEARNING, 60.0, [True] * 10, False),  # just forgotten
        (CardState.LEARNING, 60.0, [True] * 10, False),
        (CardState.REVIEW, None, [True] * 10, False),
        (CardState.REVIEW, 60.0, [False, False] + [True] * 8, False),  # 80 %
        (CardState.REVIEW, 60.0, [True, True], False),  # too few answers
        # Only the last ten answers count: old mistakes were fixed.
        (CardState.REVIEW, 60.0, [False] * 5 + [True] * 10, True),
    ],
)
def test_item_mastery(
    state: CardState, stability: float | None, answers: list[bool], mastered: bool
) -> None:
    mastery = setup([card('a', stability, state)], {'a': answers})
    assert mastery.is_mastered(ItemId('a')) is mastered


def test_item_without_a_card_is_not_mastered() -> None:
    assert not setup([], {'a': [True] * 10}).is_mastered(ItemId('a'))


def test_unit_fraction_and_unlocking() -> None:
    items = [ItemId(f'i{n}') for n in range(5)]
    cards = [card(i, 30.0) for i in items]
    answers = {i: [True] * 5 for i in items[:4]} | {items[4]: [False] * 5}
    mastery = setup(cards, answers)
    assert mastery.mastered(items) == set(items[:4])
    assert mastery.fraction(items) == pytest.approx(0.8)
    assert mastery.is_unlocked_by(items)
    assert mastery.fraction([*items, ItemId('new')]) == pytest.approx(4 / 6)
    assert not mastery.is_unlocked_by([*items, ItemId('new')])
    # Duplicates count once.
    assert mastery.fraction([items[0], items[0], items[4]]) == pytest.approx(0.5)


def test_empty_unit_counts_as_mastered() -> None:
    mastery = setup([], {})
    assert mastery.fraction([]) == 1.0
    assert mastery.is_unlocked_by([])


def test_thresholds_are_configurable() -> None:
    attempts = FakeAttemptLog(
        [outcome('a', NOW + timedelta(minutes=n), correct=n > 0) for n in range(4)]
    )
    config = MasteryConfig(stability_days=7.0, item_accuracy=0.75, min_answers=4)
    mastery = Mastery(FakeCardStore([card('a', 7.0)]), attempts, config)
    assert mastery.is_mastered(ItemId('a'))
    assert Mastery(FakeCardStore([card('a', 7.0)]), attempts).is_mastered(ItemId('a')) is False
