# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random
from datetime import timedelta

import pytest
from tests.learning.fakes import (
    FakeAttemptLog,
    FakeCardStore,
    FakeCatalog,
    FakeClock,
    FakeSessionLog,
    outcome,
)

from etude.learning.engine import LearningEngine
from etude.learning.model import ItemId, Rating, SessionMode, SessionRequest
from etude.learning.scheduler import FsrsScheduler
from etude.learning.stats import StatsConfig


class Recorder(FsrsScheduler):
    def __init__(self) -> None:
        super().__init__(fuzz=False)
        self.ratings: list[Rating] = []

    def review(self, card, rating, now):  # type: ignore[no-untyped-def]
        self.ratings.append(rating)
        return super().review(card, rating, now)


def make_engine(**kwargs: object):
    catalog = FakeCatalog({'keys': ['k.0', 'k.1', 'k.2'], 'notes': ['n.0', 'n.1']})
    cards, attempts, sessions = FakeCardStore(), FakeAttemptLog(), FakeSessionLog()
    clock = FakeClock()
    scheduler = Recorder()
    engine = LearningEngine.create(
        catalog,
        cards,
        attempts,
        sessions,
        scheduler=scheduler,
        rng=random.Random(1),
        clock=clock,
        **kwargs,  # type: ignore[arg-type]
    )
    return engine, cards, attempts, sessions, clock, scheduler


def test_a_whole_session() -> None:
    engine, cards, attempts, sessions, clock, _ = make_engine()
    started = clock.now
    plan = engine.start_session(
        SessionRequest(SessionMode.EXERCISE, now=started, exercise_id='keys', size=3)
    )
    assert engine.active_plan == plan
    assert {q.item_id for q in plan} == {'k.0', 'k.1', 'k.2'}
    results = {'k.0': True, 'k.1': False, 'k.2': True}
    for planned in plan:
        card = engine.record(
            outcome(
                planned.item_id, clock.advance(), correct=results[planned.item_id], exercise='keys'
            )
        )
        assert cards.get(planned.item_id) == card
        assert card.reps == 1
    assert [sid for _, sid in attempts.entries] == [1, 1, 1]
    clock.advance(timedelta(seconds=10))
    summary = engine.finish_session()
    assert (summary.total, summary.correct) == (3, 2)
    assert summary.mistakes == (ItemId('k.1'),)
    assert summary.duration_ms == 25_000
    assert sessions.records[1].summary == summary
    assert sessions.records[1].finished_at == clock.now
    assert engine.active_plan is None


def test_rating_uses_the_learners_speed() -> None:
    engine, _, attempts, _, clock, scheduler = make_engine(
        stats_config=StatsConfig(speed_min_samples=4)
    )
    for n, ms in enumerate([1000, 2000, 3000, 4000]):
        attempts.add(outcome(f'k.{n % 3}', clock.advance(), ms=ms, exercise='keys'), None)
    # p25 = 1750 ms, p75 = 3250 ms
    engine.record(outcome('k.0', clock.advance(), ms=1500, exercise='keys'))
    engine.record(outcome('k.1', clock.advance(), ms=2500, exercise='keys'))
    engine.record(outcome('k.2', clock.advance(), ms=6000, exercise='keys'))
    engine.record(outcome('n.0', clock.advance(), ms=1500, exercise='notes'))  # defaults
    engine.record(outcome('n.1', clock.advance(), correct=False, exercise='notes'))
    assert scheduler.ratings == [Rating.EASY, Rating.GOOD, Rating.HARD, Rating.EASY, Rating.AGAIN]


def test_recording_reviews_existing_cards() -> None:
    engine, cards, _, _, clock, _ = make_engine()
    first = engine.record(outcome('k.0', clock.now, exercise='keys'))
    second = engine.record(outcome('k.0', first.due, exercise='keys'))
    assert second.reps == 2
    assert cards.get(ItemId('k.0')) == second
    assert second.last_review == first.due


def test_answers_outside_a_session_have_no_session_id() -> None:
    engine, _, attempts, _, clock, _ = make_engine()
    engine.record(outcome('k.0', clock.now, exercise='keys'))
    assert attempts.entries[0][1] is None


def test_starting_a_session_finishes_the_previous_one() -> None:
    engine, _, _, sessions, clock, _ = make_engine()
    engine.start_session(SessionRequest(SessionMode.DAILY_REVIEW, now=clock.now))
    engine.record(outcome('k.0', clock.advance(), exercise='keys'))
    later = clock.advance(timedelta(minutes=1))
    engine.start_session(SessionRequest(SessionMode.DAILY_REVIEW, now=later))
    assert sessions.records[1].finished_at == later
    assert sessions.records[1].summary is not None
    assert sessions.records[1].summary.total == 1
    assert sessions.records[2].summary is None


def test_finishing_without_a_session_is_an_error() -> None:
    engine, *_ = make_engine()
    with pytest.raises(RuntimeError, match='no session'):
        engine.finish_session()


def test_finish_session_with_an_explicit_time() -> None:
    engine, _, _, _, clock, _ = make_engine()
    engine.start_session(SessionRequest(SessionMode.DAILY_REVIEW, now=clock.now))
    summary = engine.finish_session(clock.now + timedelta(seconds=3))
    assert summary.duration_ms == 3000


def test_create_defaults() -> None:
    catalog = FakeCatalog({'keys': ['k.0']})
    engine = LearningEngine.create(catalog, FakeCardStore(), FakeAttemptLog(), FakeSessionLog())
    plan = engine.start_session(SessionRequest(SessionMode.DAILY_REVIEW, now=FakeClock().now))
    assert [q.item_id for q in plan] == ['k.0']
    assert engine.finish_session().total == 0


def test_an_empty_plan_opens_no_session() -> None:
    sessions = FakeSessionLog()
    engine = LearningEngine.create(FakeCatalog({}), FakeCardStore(), FakeAttemptLog(), sessions)
    assert engine.start_session(SessionRequest(SessionMode.DAILY_REVIEW, now=FakeClock().now)) == []
    assert sessions.records == {}
    assert engine.active_plan is None


def test_pause_and_resume_do_not_count_as_practice() -> None:
    engine, _, _, sessions, clock, _ = make_engine()
    engine.start_session(SessionRequest(SessionMode.EXERCISE, now=clock.now, exercise_id='keys'))
    assert engine.active_session_id == 1
    engine.record(outcome('k.0', clock.advance(timedelta(seconds=10)), exercise='keys'))
    engine.pause_session(clock.now)
    engine.pause_session(clock.advance(timedelta(minutes=1)))  # pausing twice changes nothing
    assert engine.is_paused
    engine.resume_session(clock.advance(timedelta(hours=2)))
    assert not engine.is_paused
    engine.record(outcome('k.1', clock.advance(timedelta(seconds=20)), exercise='keys'))
    summary = engine.finish_session(clock.now)
    assert summary.total == 2
    assert summary.duration_ms == 30_000
    assert sessions.records[1].summary == summary


def test_a_session_finished_while_paused_ends_when_it_was_paused() -> None:
    engine, _, _, sessions, clock, _ = make_engine()
    engine.start_session(SessionRequest(SessionMode.EXERCISE, now=clock.now, exercise_id='keys'))
    engine.record(outcome('k.0', clock.advance(timedelta(seconds=10)), exercise='keys'))
    paused = clock.now
    engine.pause_session(paused)
    later = clock.advance(timedelta(hours=3))
    engine.start_session(SessionRequest(SessionMode.DAILY_REVIEW, now=later))
    assert sessions.records[1].finished_at == paused
    assert sessions.records[1].summary is not None
    assert sessions.records[1].summary.duration_ms == 10_000
    assert engine.active_session_id == 2


def test_answering_resumes_a_paused_session() -> None:
    engine, _, _, _, clock, _ = make_engine()
    engine.start_session(SessionRequest(SessionMode.EXERCISE, now=clock.now, exercise_id='keys'))
    engine.pause_session(clock.advance(timedelta(seconds=10)))
    engine.record(outcome('k.0', clock.advance(timedelta(minutes=5)), exercise='keys'))
    assert not engine.is_paused
    assert engine.finish_session(clock.now).duration_ms == 10_000


def test_pausing_without_a_session_is_an_error() -> None:
    engine, _, _, _, clock, _ = make_engine()
    assert engine.active_session_id is None
    with pytest.raises(RuntimeError, match='no session'):
        engine.pause_session(clock.now)
    with pytest.raises(RuntimeError, match='no session'):
        engine.resume_session(clock.now)


def test_new_items_outlook() -> None:
    engine, _, _, _, clock, _ = make_engine()
    outlook = engine.new_items(clock.now)
    assert outlook.available == 5
    assert not outlook.held_back
