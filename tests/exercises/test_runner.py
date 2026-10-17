# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import random
from datetime import timedelta

import pytest
from tests.learning.fakes import FakeAttemptLog, FakeCardStore, FakeClock, FakeSessionLog

from etude.exercises.families.key_signatures import KeySignatures
from etude.exercises.registry import ExerciseRegistry
from etude.exercises.runner import EmptySessionError, SessionRunner
from etude.learning.engine import LearningEngine
from etude.learning.model import ItemId, SessionMode, SessionRequest
from etude.learning.scheduler import FsrsScheduler


class World:
    def __init__(self) -> None:
        self.clock = FakeClock()
        self.registry = ExerciseRegistry([KeySignatures()])
        self.cards = FakeCardStore()
        self.attempts = FakeAttemptLog()
        self.sessions = FakeSessionLog()
        rng = random.Random(7)
        self.engine = LearningEngine.create(
            self.registry,
            self.cards,
            self.attempts,
            self.sessions,
            scheduler=FsrsScheduler(rng=rng, fuzz=False),
            rng=rng,
            clock=self.clock,
        )

    def runner(self, mode: SessionMode = SessionMode.EXERCISE, **kwargs: object) -> SessionRunner:
        request = SessionRequest(
            mode,
            now=self.clock(),
            size=kwargs.pop('size', 5),  # type: ignore[arg-type]
            exercise_id='keysig' if mode is SessionMode.EXERCISE else None,
            **kwargs,  # type: ignore[arg-type]
        )
        return SessionRunner(
            self.engine, self.registry, request, rng=random.Random(3), clock=self.clock
        )


@pytest.fixture
def world() -> World:
    return World()


def play_through(runner: SessionRunner, clock: FakeClock, *, wrong_every: int = 0) -> None:
    while True:
        clock.advance(timedelta(seconds=3))
        question = runner.current.question
        if wrong_every and runner.number % wrong_every == 0:
            given: object = next(
                o.key
                for o in question.answer.options  # type: ignore[union-attr]
                if o.key != question.expected
            )
        else:
            given = question.expected
        runner.answer(given, response_ms=2500)
        if not runner.advance():
            break


def test_a_session_records_every_answer(world: World) -> None:
    runner = world.runner(size=5)
    assert runner.title == 'Key Signatures'
    assert runner.total == 5
    assert runner.current.exercise_title == 'Key Signatures'
    assert runner.current.play_label == 'Play scale'
    assert runner.current.settings_text == 'Mixed clefs · up to 5 accidentals'
    play_through(runner, world.clock, wrong_every=2)
    summary = runner.finish()
    assert summary.total == 5
    assert summary.correct == 3
    assert len(world.attempts.entries) == 5
    assert all(o.exercise_id == 'keysig' for o, _ in world.attempts.entries)
    assert len(summary.mistakes) == 2
    assert world.cards.cards, 'answers reschedule cards'


def test_streak_and_accuracy(world: World) -> None:
    runner = world.runner(size=4)
    assert runner.accuracy is None
    question = runner.current.question
    runner.answer(question.expected, response_ms=1000)
    assert (runner.streak, runner.best_today, runner.accuracy) == (1, 1, 1.0)
    runner.advance()
    runner.skip(response_ms=1000)
    assert (runner.streak, runner.best_today, runner.accuracy) == (0, 1, 0.5)


def test_skip_reveals_the_answer_and_counts_as_not_known(world: World) -> None:
    runner = world.runner(size=2)
    feedback = runner.skip(response_ms=4000)
    assert not feedback.correct
    assert feedback.title.startswith('Skipped — the answer is ')
    assert feedback.detail
    outcome = world.attempts.entries[-1][0]
    assert not outcome.correct
    assert outcome.given == ''


def test_a_question_is_graded_once(world: World) -> None:
    runner = world.runner(size=2)
    runner.answer(runner.current.question.expected, response_ms=1000)
    with pytest.raises(RuntimeError):
        runner.answer(runner.current.question.expected, response_ms=1000)


def test_review_mistakes_repeats_exactly_the_missed_items(world: World) -> None:
    runner = world.runner(size=4)
    play_through(runner, world.clock, wrong_every=2)
    summary = runner.finish()
    review = runner.review_mistakes(summary)
    assert review.request.mode is SessionMode.REVIEW_MISTAKES
    assert review.title == 'Review Mistakes'
    assert review.total == len(summary.mistakes)
    seen = []
    while True:
        seen.append(review.current.question.item_id)
        review.answer(review.current.question.expected, response_ms=1000)
        if not review.advance():
            break
    assert sorted(seen) == sorted(summary.mistakes)
    # Mixed sessions show the exercise as the header subtitle.
    assert review.current.settings_text == 'Key Signatures'


def test_again_starts_a_fresh_session(world: World) -> None:
    runner = world.runner(size=3)
    play_through(runner, world.clock)
    runner.finish()
    again = runner.again()
    assert again.total == 3
    assert again.number == 1
    assert len(world.sessions.records) == 2


def test_daily_review_for_a_new_learner_introduces_items(world: World) -> None:
    runner = world.runner(SessionMode.DAILY_REVIEW, size=10)
    assert runner.title == 'Daily Review'
    assert runner.total > 0
    assert runner.current.is_new


def test_nothing_to_practise_raises(world: World) -> None:
    with pytest.raises(EmptySessionError):
        world.runner(SessionMode.REVIEW_MISTAKES, item_ids=())
    assert world.sessions.records == {}


def test_stale_items_are_skipped(world: World) -> None:
    runner = world.runner(
        SessionMode.REVIEW_MISTAKES,
        size=2,
        item_ids=(ItemId('keysig.major.99s'), ItemId('keysig.major.1s')),
    )
    assert runner.total == 1
    assert runner.current.question.item_id == 'keysig.major.1s'


def test_saved_settings_apply(world: World) -> None:
    request = SessionRequest(SessionMode.EXERCISE, now=world.clock(), size=3, exercise_id='keysig')
    runner = SessionRunner(
        world.engine,
        world.registry,
        request,
        settings_for=lambda _id: {'clefs': ('bass',), 'max-accidentals': 1},
        rng=random.Random(0),
        clock=world.clock,
    )
    assert runner.current.settings_text == 'Bass clef · up to 1 accidental'
    assert runner.settings('keysig')['clefs'] == ('bass',)


def test_finishing_twice_is_an_error(world: World) -> None:
    runner = world.runner(size=1)
    runner.answer(runner.current.question.expected, response_ms=1000)
    runner.finish()
    with pytest.raises(RuntimeError):
        runner.finish()


def test_pause_and_resume_keep_one_session(world: World) -> None:
    runner = world.runner(size=4)
    for _ in range(2):
        world.clock.advance(timedelta(seconds=3))
        runner.answer(runner.current.question.expected, response_ms=2000)
        assert runner.is_answered
        runner.advance()
        assert not runner.is_answered
    runner.pause()
    world.clock.advance(timedelta(hours=1))
    assert runner.is_open
    runner.resume()
    play_through(runner, world.clock)
    summary = runner.finish()
    assert summary.total == 4
    assert summary.correct == 4
    assert summary.duration_ms == 12_000, 'the hour away is not practice'
    assert not runner.is_open
    assert len(world.sessions.records) == 1


def test_a_session_closes_when_another_one_starts(world: World) -> None:
    first = world.runner(size=3)
    first.answer(first.current.question.expected, response_ms=2000)
    first.advance()
    first.pause()
    second = world.runner(size=3)
    assert not first.is_open
    assert second.is_open
    with pytest.raises(RuntimeError, match='another one started'):
        first.finish()
    with pytest.raises(RuntimeError):
        first.resume()
    assert world.sessions.records[1].summary is not None
    assert world.sessions.records[1].summary.total == 1


def test_a_title_names_the_session_and_its_repeats(world: World) -> None:
    request = SessionRequest(SessionMode.DAILY_REVIEW, now=world.clock(), size=3)
    runner = SessionRunner(
        world.engine, world.registry, request, clock=world.clock, title='Major Keys'
    )
    assert runner.title == 'Major Keys'
    play_through(runner, world.clock, wrong_every=2)
    summary = runner.finish()
    assert summary.mistakes
    assert runner.again().title == 'Major Keys'
    assert runner.review_mistakes(summary).title == 'Review Mistakes'


def test_drop_upcoming_removes_later_questions_only(world: World) -> None:
    runner = world.runner(size=5)
    first = runner.current.question.item_id
    runner.drop_upcoming(lambda planned: True)
    assert runner.total == 1
    assert runner.current.question.item_id == first
    runner.answer(runner.current.question.expected, response_ms=1000)
    assert not runner.advance()
