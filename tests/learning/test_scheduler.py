# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random
from datetime import datetime, timedelta, timezone

import pytest
from tests.learning.fakes import utc

from etude.learning.model import CardState, ItemId, Rating
from etude.learning.scheduler import FsrsScheduler, as_utc

ITEM = ItemId('keysig.major.2s')
T0 = utc(2026, 10, 15, 9)


def graduate(scheduler: FsrsScheduler, rating: Rating = Rating.GOOD):
    """A card reviewed until it reaches the REVIEW state."""
    card = scheduler.new_card(ITEM, T0)
    now = T0
    while card.state is not CardState.REVIEW:
        card = scheduler.review(card, rating, now)
        now = card.due
    return card


def test_new_card_is_due_immediately() -> None:
    card = FsrsScheduler().new_card(ITEM, T0)
    assert card.item_id == ITEM
    assert card.due == T0
    assert card.state is CardState.LEARNING
    assert card.step == 0
    assert card.reps == 0


def test_review_advances_learning_steps() -> None:
    scheduler = FsrsScheduler(fuzz=False)
    card = scheduler.review(scheduler.new_card(ITEM, T0), Rating.GOOD, T0)
    assert card.state is CardState.LEARNING
    assert card.step == 1
    assert card.due == T0 + timedelta(minutes=10)
    assert card.last_review == T0
    assert card.reps == 1
    assert card.stability is not None
    assert card.difficulty is not None


def test_easy_graduates_at_once() -> None:
    scheduler = FsrsScheduler(fuzz=False)
    card = scheduler.review(scheduler.new_card(ITEM, T0), Rating.EASY, T0)
    assert card.state is CardState.REVIEW
    assert card.due - T0 >= timedelta(days=1)


def test_intervals_grow_with_successful_reviews() -> None:
    scheduler = FsrsScheduler(fuzz=False)
    card = graduate(scheduler)
    intervals = []
    for _ in range(5):
        now = card.due
        card = scheduler.review(card, Rating.GOOD, now)
        intervals.append(card.due - now)
    assert intervals == sorted(intervals)
    assert intervals[-1] > intervals[0] * 3


def test_lapse_counts_and_relearns() -> None:
    scheduler = FsrsScheduler(fuzz=False)
    card = graduate(scheduler)
    lapsed = scheduler.review(card, Rating.AGAIN, card.due)
    assert lapsed.state is CardState.RELEARNING
    assert lapsed.lapses == card.lapses + 1
    # Failing again while relearning is not another lapse.
    again = scheduler.review(lapsed, Rating.AGAIN, lapsed.due)
    assert again.lapses == lapsed.lapses


def test_failing_a_learning_card_is_not_a_lapse() -> None:
    scheduler = FsrsScheduler(fuzz=False)
    card = scheduler.review(scheduler.new_card(ITEM, T0), Rating.AGAIN, T0)
    assert card.lapses == 0


def test_desired_retention_changes_intervals() -> None:
    def interval(retention: float) -> timedelta:
        scheduler = FsrsScheduler(desired_retention=retention, fuzz=False)
        card = graduate(scheduler)
        return scheduler.review(card, Rating.GOOD, card.due).due - card.due

    assert interval(0.8) > interval(0.9) > interval(0.95)
    assert FsrsScheduler(desired_retention=0.8).desired_retention == 0.8


@pytest.mark.parametrize('retention', [0.0, 1.0, 1.5])
def test_desired_retention_is_validated(retention: float) -> None:
    with pytest.raises(ValueError, match='retention'):
        FsrsScheduler(desired_retention=retention)


def test_fuzz_is_deterministic_with_a_seeded_rng() -> None:
    def run(seed: int) -> list[datetime]:
        scheduler = FsrsScheduler(rng=random.Random(seed))
        card = graduate(scheduler)
        dues = []
        for _ in range(6):
            card = scheduler.review(card, Rating.GOOD, card.due)
            dues.append(card.due)
        return dues

    assert run(1) == run(1)
    assert any(run(seed) != run(1) for seed in range(2, 10))


def test_fuzz_stays_near_the_unfuzzed_interval() -> None:
    plain = FsrsScheduler(fuzz=False)
    card = graduate(plain)
    for _ in range(4):
        card = plain.review(card, Rating.GOOD, card.due)
    exact = plain.review(card, Rating.GOOD, card.due).due - card.due
    for seed in range(20):
        fuzzy = FsrsScheduler(rng=random.Random(seed))
        interval = fuzzy.review(card, Rating.GOOD, card.due).due - card.due
        assert abs(interval - exact) <= exact * 0.1 + timedelta(days=1)


def test_short_intervals_are_not_fuzzed() -> None:
    fuzzy = FsrsScheduler(rng=random.Random(3))
    for days in (1, 2):
        assert fuzzy._fuzzed(timedelta(days=days)) == timedelta(days=days)
    assert {fuzzy._fuzzed(timedelta(days=30)) for _ in range(30)} != {timedelta(days=30)}


def test_fuzz_respects_the_maximum_interval() -> None:
    scheduler = FsrsScheduler(rng=random.Random(0), maximum_interval_days=3)
    card = graduate(scheduler, Rating.EASY)
    for _ in range(5):
        now = card.due
        card = scheduler.review(card, Rating.EASY, now)
        assert card.due - now <= timedelta(days=3)


def test_retrievability() -> None:
    scheduler = FsrsScheduler(fuzz=False)
    new = scheduler.new_card(ITEM, T0)
    assert scheduler.retrievability(new, T0) == 0.0
    card = graduate(scheduler)
    assert scheduler.retrievability(card, card.last_review) == pytest.approx(1.0)
    at_due = scheduler.retrievability(card, card.due)
    assert at_due == pytest.approx(0.9, abs=0.03)
    later = scheduler.retrievability(card, card.due + timedelta(days=30))
    assert 0.0 < later < at_due


def test_non_utc_datetimes_are_converted() -> None:
    helsinki = timezone(timedelta(hours=3))
    scheduler = FsrsScheduler(fuzz=False)
    local = T0.astimezone(helsinki)
    card = scheduler.review(scheduler.new_card(ITEM, local), Rating.GOOD, local)
    assert card.due.utcoffset() == timedelta(0)
    assert card.last_review == T0


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError, match='timezone-aware'):
        as_utc(datetime(2026, 10, 15))
