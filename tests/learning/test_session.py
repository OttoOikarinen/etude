# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import itertools
import random
from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st
from tests.learning.fakes import FakeAttemptLog, FakeCardStore, FakeCatalog, outcome, utc

from etude.learning.model import (
    Card,
    CardState,
    ItemId,
    PlannedQuestion,
    SessionMode,
    SessionRequest,
)
from etude.learning.scheduler import FsrsScheduler
from etude.learning.session import (
    NewItems,
    SessionBuilder,
    SessionConfig,
    interleave,
    place_confusables,
    separate_repeats,
)

NOW = utc(2026, 10, 15, 9)

CATALOG = {
    'keys': [f'keys.{n}' for n in range(10)],
    'notes': [f'notes.{n}' for n in range(10)],
    'ivl': [f'ivl.{n}' for n in range(10)],
}


def review_card(
    item: str,
    *,
    due: datetime,
    stability: float = 10.0,
    lapses: int = 0,
    last_review: datetime | None = None,
) -> Card:
    return Card(
        item_id=ItemId(item),
        due=due,
        state=CardState.REVIEW,
        step=None,
        stability=stability,
        difficulty=5.0,
        last_review=last_review or due - timedelta(days=stability),
        reps=3,
        lapses=lapses,
    )


class World:
    def __init__(
        self,
        catalog: dict[str, list[str]] | None = None,
        config: SessionConfig | None = None,
        confusables=None,
    ) -> None:
        self.catalog = FakeCatalog(catalog or CATALOG)
        self.cards = FakeCardStore()
        self.attempts = FakeAttemptLog()
        self.builder = SessionBuilder(
            self.catalog,
            self.cards,
            self.attempts,
            FsrsScheduler(fuzz=False),
            random.Random(7),
            config,
            confusables=confusables,
        )

    def due(self, item: str, days_overdue: float = 1.0, **kwargs: object) -> None:
        self.cards.put(review_card(item, due=NOW - timedelta(days=days_overdue), **kwargs))  # type: ignore[arg-type]

    def later(self, item: str, days: float = 5.0, **kwargs: object) -> None:
        self.cards.put(review_card(item, due=NOW + timedelta(days=days), **kwargs))  # type: ignore[arg-type]

    def answers(self, correct: int, wrong: int, *, exercise: str = 'keys', at=None) -> None:
        at = at or NOW - timedelta(hours=1)
        item = CATALOG.get(exercise, ['x'])[0]
        for n in range(correct + wrong):
            self.attempts.add(
                outcome(item, at + timedelta(seconds=n), correct=n < correct, exercise=exercise),
                None,
            )

    def build(self, mode: SessionMode = SessionMode.DAILY_REVIEW, **kwargs: object):
        return self.builder.build(SessionRequest(mode, now=NOW, **kwargs))  # type: ignore[arg-type]


def no_item_twice_in_a_row(plan: Sequence[PlannedQuestion]) -> bool:
    return all(a.item_id != b.item_id for a, b in itertools.pairwise(plan))


def exercise_switches(plan: Sequence[PlannedQuestion]) -> int:
    return sum(a.exercise_id != b.exercise_id for a, b in itertools.pairwise(plan))


# DAILY_REVIEW


def test_daily_review_takes_the_most_overdue_cards() -> None:
    world = World()
    for n in range(10):
        world.due(f'keys.{n}', days_overdue=n + 1)
        world.due(f'notes.{n}', days_overdue=n + 1.5)
    world.answers(20, 0)
    plan = world.build(size=6)
    assert {q.item_id for q in plan} == {
        'notes.9',
        'keys.9',
        'notes.8',
        'keys.8',
        'notes.7',
        'keys.7',
    }
    assert not any(q.is_new for q in plan)


def test_daily_review_interleaves_exercises() -> None:
    world = World()
    for n in range(4):
        world.due(f'keys.{n}', days_overdue=10 + n)  # keys are all more overdue
        world.due(f'notes.{n}', days_overdue=1 + n)
        world.due(f'ivl.{n}', days_overdue=1 + n)
    world.answers(0, 20)  # no new items
    plan = world.build(size=12)
    assert len(plan) == 12
    assert exercise_switches(plan) == 11


def test_daily_review_adds_new_items_in_teaching_order_when_accuracy_is_high() -> None:
    world = World()
    world.due('keys.5')
    world.due('notes.0')
    world.answers(18, 2)  # 90 %
    plan = world.build(size=10)
    new = [q.item_id for q in plan if q.is_new]
    # Only exercises the learner has started; ivl has no cards yet.
    assert sorted(new) == ['keys.0', 'keys.1', 'keys.2', 'notes.1', 'notes.2']
    assert [i for i in new if i.startswith('keys')] == ['keys.0', 'keys.1', 'keys.2']
    assert len(plan) == 7, 'session cap of 5 new items'


def test_new_items_need_accuracy_at_the_target() -> None:
    world = World()
    world.due('keys.5')
    world.answers(17, 3)  # exactly 85 %
    assert any(q.is_new for q in world.build(size=10))
    world.answers(0, 1, at=NOW - timedelta(minutes=1))  # 16 of the last 20: 80 %
    assert not any(q.is_new for q in world.build(size=10))


def test_beginners_get_new_items_from_every_exercise() -> None:
    world = World()
    plan = world.build(size=20)
    assert {q.item_id for q in plan} == {
        'keys.0',
        'notes.0',
        'ivl.0',
        'keys.1',
        'notes.1',
    }
    assert all(q.is_new for q in plan)


def test_daily_cap_on_new_items() -> None:
    world = World(config=SessionConfig(daily_new_limit=7, session_new_limit=5))
    world.due('keys.9')
    world.answers(20, 0, at=NOW - timedelta(days=2))
    # Four items were introduced earlier today: one answer each, one review each.
    for n in range(4):
        item = f'notes.{n}'
        world.cards.put(
            Card(ItemId(item), NOW + timedelta(minutes=10), reps=1, last_review=NOW, stability=1)
        )
        world.attempts.add(outcome(item, NOW - timedelta(hours=2), exercise='notes'), None)
    # One older item reviewed today does not count as new.
    world.cards.put(review_card('keys.8', due=NOW + timedelta(days=3)))
    world.attempts.add(outcome('keys.8', NOW - timedelta(hours=1)), None)
    assert world.builder.new_today(NOW) == 4
    assert sum(q.is_new for q in world.build(size=20)) == 3


def test_new_items_today_for_a_beginner() -> None:
    world = World(config=SessionConfig(daily_new_limit=10))
    expected = NewItems(available=10, left_today=10, held_back=False)
    assert world.builder.new_items_today(NOW) == expected


def test_new_items_today_counts_only_unseen_items_of_started_exercises() -> None:
    world = World(catalog={'keys': ['keys.0', 'keys.1', 'keys.2'], 'notes': ['notes.0']})
    world.later('keys.0')
    world.answers(20, 0, at=NOW - timedelta(days=2))
    assert world.builder.new_items_today(NOW).available == 2


def test_new_items_today_held_back_by_low_accuracy() -> None:
    world = World()
    world.later('keys.0')
    world.answers(10, 10)
    outlook = world.builder.new_items_today(NOW)
    assert outlook.held_back
    assert outlook.available == 0
    assert outlook.left_today > 0


def test_new_items_today_after_the_daily_limit() -> None:
    world = World(config=SessionConfig(daily_new_limit=2))
    for n in range(2):
        item = f'notes.{n}'
        world.cards.put(Card(ItemId(item), NOW + timedelta(minutes=10), reps=1, last_review=NOW))
        world.attempts.add(outcome(item, NOW - timedelta(hours=2), exercise='notes'), None)
    expected = NewItems(available=0, left_today=0, held_back=False)
    assert world.builder.new_items_today(NOW) == expected


def test_daily_review_does_not_pad_with_items_not_due() -> None:
    world = World()
    world.answers(0, 20)
    world.due('keys.0')
    world.later('keys.1')
    assert [q.item_id for q in world.build(size=20)] == ['keys.0']


def test_daily_review_skips_items_of_removed_exercises() -> None:
    world = World()
    world.answers(0, 20)
    world.due('gone.1', days_overdue=5)
    world.due('keys.0')
    assert [q.item_id for q in world.build(size=20)] == ['keys.0']


def test_full_session_of_due_items_has_no_new_items() -> None:
    world = World()
    world.answers(20, 0)
    for n in range(5):
        world.due(f'keys.{n}')
    assert not any(q.is_new for q in world.build(size=5))


# EXERCISE


def test_exercise_mode_uses_one_exercise_and_its_settings() -> None:
    world = World()
    world.answers(20, 0, exercise='keys')
    world.due('keys.3')
    world.due('keys.4')
    world.due('notes.0')
    allowed = ['keys.3', 'keys.5', 'keys.6', 'keys.7', 'keys.8']
    plan = world.build(SessionMode.EXERCISE, exercise_id='keys', settings={'only': allowed}, size=4)
    assert [q.item_id for q in plan].count('keys.3') == 1
    assert {q.exercise_id for q in plan} == {'keys'}
    assert {q.item_id for q in plan} <= set(allowed)
    assert {q.item_id for q in plan if q.is_new} == {'keys.5', 'keys.6', 'keys.7'}


def test_exercise_mode_gates_new_items_on_that_exercise_only() -> None:
    world = World()
    world.answers(20, 0, exercise='notes')
    world.answers(10, 10, exercise='keys')
    world.later('keys.0')
    plan = world.build(SessionMode.EXERCISE, exercise_id='keys', size=3)
    assert not any(q.is_new for q in plan)
    plan = world.build(SessionMode.EXERCISE, exercise_id='notes', size=3)
    assert all(q.is_new for q in plan)


def test_exercise_mode_fills_with_the_least_retrievable_items() -> None:
    world = World()
    world.answers(0, 20, exercise='keys')  # no new items
    reviewed = NOW - timedelta(days=1)
    world.later('keys.0', days=1, stability=30, last_review=reviewed)  # well remembered
    world.later('keys.1', days=1, stability=2, last_review=reviewed)  # fading
    world.later('keys.2', days=1, stability=5, last_review=reviewed)
    plan = world.build(SessionMode.EXERCISE, exercise_id='keys', size=2)
    assert {q.item_id for q in plan} == {'keys.1', 'keys.2'}


def test_exercise_mode_repeats_a_small_pool_to_fill_the_session() -> None:
    world = World({'keys': ['k.0', 'k.1', 'k.2']})
    plan = world.build(SessionMode.EXERCISE, exercise_id='keys', size=10)
    assert len(plan) == 10
    assert Counter(q.item_id for q in plan) == {'k.0': 4, 'k.1': 3, 'k.2': 3}
    assert sum(q.is_new for q in plan) == 3
    assert no_item_twice_in_a_row(plan)


def test_exercise_mode_requires_an_exercise() -> None:
    with pytest.raises(ValueError, match='exercise_id'):
        World().build(SessionMode.EXERCISE)


def test_exercise_mode_with_an_empty_pool() -> None:
    world = World({'keys': []})
    assert world.build(SessionMode.EXERCISE, exercise_id='keys') == []


# DRILL_WEAK and REVIEW_MISTAKES


def test_drill_weak_with_explicit_items() -> None:
    world = World()
    world.later('keys.1')
    items = tuple(ItemId(i) for i in ('keys.1', 'notes.2', 'ivl.3', 'keys.4'))
    plan = world.build(SessionMode.DRILL_WEAK, item_ids=items, size=3)
    assert len(plan) == 3
    assert {q.item_id for q in plan} == set(items[:3])
    assert {q.item_id for q in plan if q.is_new} == {'notes.2', 'ivl.3'}


def test_drill_weak_computes_the_weakest_items() -> None:
    world = World()
    t = NOW - timedelta(days=1)
    results = {
        'keys.0': [True] * 5,
        'keys.1': [False, False, True],
        'notes.1': [True, False, True, True],
        'ivl.1': [False, True, False, False],
    }
    for item, answers in results.items():
        for n, correct in enumerate(answers):
            exercise = world.catalog.exercise_for(ItemId(item))
            world.attempts.add(
                outcome(item, t + timedelta(minutes=n), correct=correct, exercise=exercise), None
            )
    plan = world.build(SessionMode.DRILL_WEAK, size=2)
    assert {q.item_id for q in plan} == {'ivl.1', 'keys.1'}
    plan = world.build(SessionMode.DRILL_WEAK, size=10, exercise_id='notes')
    assert [q.item_id for q in plan] == ['notes.1']


def test_review_mistakes_uses_exactly_the_given_items() -> None:
    world = World()
    items = tuple(ItemId(i) for i in ('keys.1', 'keys.1', 'keys.2', 'notes.1', 'keys.1'))
    plan = world.build(SessionMode.REVIEW_MISTAKES, item_ids=items, size=2)
    assert Counter(q.item_id for q in plan) == Counter(items)
    assert no_item_twice_in_a_row(plan)


def test_review_mistakes_is_shuffled() -> None:
    items = tuple(ItemId(f'keys.{n}') for n in range(10))
    orders = set()
    for seed in range(5):
        world = World()
        world.builder._rng = random.Random(seed)
        plan = world.build(SessionMode.REVIEW_MISTAKES, item_ids=items)
        orders.add(tuple(q.item_id for q in plan))
    assert len(orders) > 1


@pytest.mark.parametrize('mode', [SessionMode.PLACEMENT, SessionMode.LEVEL_EXAM])
def test_placement_and_exams_are_not_implemented_yet(mode: SessionMode) -> None:
    with pytest.raises(NotImplementedError, match='W3'):
        World().build(mode)


# Confusables


def pairs(item: ItemId) -> Sequence[ItemId]:
    partner = {'ivl.m6': 'ivl.M6', 'ivl.M6': 'ivl.m6', 'ivl.TT': 'ivl.P5', 'ivl.P5': 'ivl.TT'}
    return [ItemId(partner[item])] if item in partner else []


def test_confusable_items_are_placed_next_to_each_other() -> None:
    catalog = {
        'ivl': ['ivl.m6', 'ivl.M6', 'ivl.TT', 'ivl.P5', 'ivl.m3'],
        'keys': [f'keys.{n}' for n in range(6)],
    }
    world = World(catalog, confusables=pairs)
    world.answers(0, 20)
    for item in [*catalog['ivl'], *catalog['keys']]:
        world.due(item)
    for seed in range(10):
        world.builder._rng = random.Random(seed)
        plan = [q.item_id for q in world.build(size=11)]
        assert abs(plan.index('ivl.m6') - plan.index('ivl.M6')) == 1
        assert abs(plan.index('ivl.TT') - plan.index('ivl.P5')) == 1


def test_place_confusables_keeps_existing_neighbours() -> None:
    plan = [PlannedQuestion('ivl', ItemId(i)) for i in ('ivl.m6', 'ivl.M6', 'x', 'ivl.P5', 'y')]
    result = [q.item_id for q in place_confusables(plan, pairs)]
    assert result == ['ivl.m6', 'ivl.M6', 'x', 'ivl.P5', 'y']


def test_place_confusables_pulls_a_later_partner_forward() -> None:
    names = ('ivl.TT', 'a', 'b', 'ivl.m6', 'c', 'ivl.P5', 'd', 'ivl.M6')
    plan = [PlannedQuestion('ivl', ItemId(i)) for i in names]
    result = [q.item_id for q in place_confusables(plan, pairs)]
    assert result == ['ivl.TT', 'ivl.P5', 'a', 'b', 'ivl.m6', 'ivl.M6', 'c', 'd']


# Arrangement helpers


def q(exercise: str, item: str) -> PlannedQuestion:
    return PlannedQuestion(exercise, ItemId(item))


def test_interleave_keeps_order_within_an_exercise() -> None:
    plan = [q('a', 'a1'), q('a', 'a2'), q('a', 'a3'), q('b', 'b1'), q('b', 'b2'), q('c', 'c1')]
    result = interleave(plan)
    assert [x.item_id for x in result if x.exercise_id == 'a'] == ['a1', 'a2', 'a3']
    assert exercise_switches(result) == 5


def test_separate_repeats_when_one_exercise_has_duplicates() -> None:
    plan = [q('a', 'x'), q('a', 'x'), q('a', 'y'), q('a', 'z')]
    result = separate_repeats(plan)
    assert no_item_twice_in_a_row(result)
    assert Counter(result) == Counter(plan)


def test_separate_repeats_gives_up_when_impossible() -> None:
    plan = [q('a', 'x'), q('a', 'x'), q('a', 'x')]
    assert separate_repeats(plan) == plan


@given(
    st.lists(
        st.tuples(st.sampled_from('abc'), st.integers(min_value=0, max_value=5)),
        max_size=30,
    )
)
def test_arrangement_never_repeats_an_item_when_avoidable(entries: list[tuple[str, int]]) -> None:
    plan = [q(e, f'{e}{n}') for e, n in entries]
    result = separate_repeats(interleave(plan))
    assert Counter(result) == Counter(plan)
    counts = Counter(x.item_id for x in plan)
    if not counts or max(counts.values()) <= (len(plan) + 1) // 2:
        assert no_item_twice_in_a_row(result)
