# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Runs one practice session from plan to summary.

The learning engine decides *which* items to practise; the exercise
definitions turn each item into a fresh question and grade the answer; the
runner records every answer so the scheduler and statistics see it. It has
no UI code: the exercise page's controller drives it, and tests drive it
with in-memory stores.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from gettext import gettext as _

from ..learning.engine import LearningEngine
from ..learning.model import (
    ItemId,
    Outcome,
    PlannedQuestion,
    SessionMode,
    SessionRequest,
    SessionSummary,
)
from .base import ExerciseDefinition, Feedback, Question
from .registry import ExerciseRegistry

log = logging.getLogger(__name__)

SettingsProvider = Callable[[str], Mapping[str, object]]
"""The learner's saved settings of an exercise (the setup page, design 1j)."""


class EmptySessionError(Exception):
    """Nothing to practise: no items are due and no new items may be introduced."""


@dataclass(frozen=True, slots=True)
class ShownQuestion:
    """A generated question with what the exercise page shows around it."""

    question: Question
    exercise_title: str
    settings_text: str
    """Header subtitle after the question counter, e.g. "Treble clef · up to 5 accidentals"."""
    play_label: str
    is_new: bool


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SessionRunner:
    """One session: ``current`` → ``answer``/``skip`` → ``advance`` … → ``finish``."""

    def __init__(
        self,
        engine: LearningEngine,
        registry: ExerciseRegistry,
        request: SessionRequest,
        *,
        settings_for: SettingsProvider | None = None,
        rng: random.Random | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.engine = engine
        self.registry = registry
        self.request = request
        self._settings_for = settings_for
        self._rng = rng if rng is not None else random.Random()
        self._clock = clock
        self._plan = [p for p in engine.start_session(request) if self._known(p)]
        self._session_id = engine.active_session_id
        self.index = 0
        self.answered = 0
        self.correct = 0
        self.streak = 0
        self.best_today = engine.stats.best_run_today(request.now)
        self._graded = False
        self._finished = False
        self._current = self._first_question()

    @property
    def title(self) -> str:
        """Title of the exercise page: the exercise, or the kind of mixed session."""
        if self.request.exercise_id is not None:
            return self.registry.get(self.request.exercise_id).title
        return {
            SessionMode.DAILY_REVIEW: _('Daily Review'),
            SessionMode.DRILL_WEAK: _('Weakest Items'),
            SessionMode.REVIEW_MISTAKES: _('Review Mistakes'),
            SessionMode.PLACEMENT: _('Placement Test'),
            SessionMode.LEVEL_EXAM: _('Level Exam'),
        }.get(self.request.mode, _('Practice'))

    # Progress

    @property
    def current(self) -> ShownQuestion:
        return self._current

    @property
    def number(self) -> int:
        """1-based number of the current question."""
        return self.index + 1

    @property
    def total(self) -> int:
        return len(self._plan)

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.answered if self.answered else None

    @property
    def is_answered(self) -> bool:
        """Whether the current question has been answered or skipped."""
        return self._graded

    @property
    def is_open(self) -> bool:
        """Whether this session is still the engine's open session.

        Starting another session finishes an unfinished one (see
        :meth:`LearningEngine.start_session`), which closes this runner too.
        """
        return not self._finished and self.engine.active_session_id == self._session_id

    # Interruptions (the home page's Continue banner, design 1a)

    def pause(self) -> None:
        """The learner left the exercise page; time until :meth:`resume` is not practice."""
        self._require_open()
        self.engine.pause_session(self._clock())

    def resume(self) -> None:
        self._require_open()
        self.engine.resume_session(self._clock())

    # Answering

    def answer(self, given: object, *, response_ms: int, hinted: bool = False) -> Feedback:
        """Grade ``given``, record the outcome and return the feedback to show."""
        shown = self._begin_grading()
        definition = self.registry.get(shown.question.exercise_id)
        feedback = definition.grade(shown.question, given)
        self._record(
            definition, shown.question, feedback.correct, response_ms, hinted, given, feedback.score
        )
        return feedback

    def skip(self, *, response_ms: int) -> Feedback:
        """Count the question as not known and show its answer.

        A skipped item is due again soon, like a wrong answer: the learner
        could not retrieve it, and seeing the answer right away is feedback.
        """
        shown = self._begin_grading()
        question = shown.question
        definition = self.registry.get(question.exercise_id)
        reference = definition.grade(question, question.expected)
        self._record(definition, question, False, response_ms, False, None, None)
        label = definition.answer_label(question, question.expected)
        return Feedback(
            correct=False,
            # Translators: shown after skipping a question, e.g. "Skipped — the answer is F4".
            title=_('Skipped — the answer is {answer}').format(answer=label),
            detail=reference.detail,
            expected_label=label,
            figure=reference.figure,
            play_expected=reference.play_expected,
        )

    def answer_label(self, value: object) -> str:
        question = self._current.question
        return self.registry.get(question.exercise_id).answer_label(question, value)

    def advance(self) -> bool:
        """Move to the next question; ``False`` when the session is over."""
        self.index += 1
        self._graded = False
        while self.index < len(self._plan):
            shown = self._generate(self._plan[self.index])
            if shown is not None:
                self._current = shown
                return True
            del self._plan[self.index]
        return False

    def finish(self) -> SessionSummary:
        """Close the session; the summary covers every answer, also from before a pause."""
        self._require_open()
        self._finished = True
        return self.engine.finish_session(self._clock())

    def _require_open(self) -> None:
        if self._finished:
            raise RuntimeError('the session is already finished')
        if self.engine.active_session_id != self._session_id:
            raise RuntimeError('the session was closed when another one started')

    # Follow-up sessions (design 1i)

    def again(self) -> SessionRunner:
        return self._follow_up(replace(self.request, now=self._clock()))

    def review_mistakes(self, summary: SessionSummary) -> SessionRunner:
        request = SessionRequest(
            SessionMode.REVIEW_MISTAKES,
            now=self._clock(),
            size=len(summary.mistakes),
            item_ids=summary.mistakes,
        )
        return self._follow_up(request)

    def _follow_up(self, request: SessionRequest) -> SessionRunner:
        return SessionRunner(
            self.engine,
            self.registry,
            request,
            settings_for=self._settings_for,
            rng=self._rng,
            clock=self._clock,
        )

    # Internals

    def _known(self, planned: PlannedQuestion) -> bool:
        """Drop items of exercises that no longer exist (e.g. after an update)."""
        try:
            self.registry.get(planned.exercise_id)
        except KeyError:
            log.warning('skipping %s: exercise %r is unknown', planned.item_id, planned.exercise_id)
            return False
        return True

    def _first_question(self) -> ShownQuestion:
        while self._plan:
            shown = self._generate(self._plan[0])
            if shown is not None:
                return shown
            del self._plan[0]
        raise EmptySessionError

    def settings(self, exercise_id: str) -> dict[str, object]:
        definition = self.registry.get(exercise_id)
        merged = definition.default_settings()
        if self._settings_for is not None:
            merged.update(self._settings_for(exercise_id))
        if self.request.exercise_id == exercise_id:
            merged.update(self.request.settings)
        return merged

    def _generate(self, planned: PlannedQuestion) -> ShownQuestion | None:
        definition = self.registry.get(planned.exercise_id)
        settings = self.settings(planned.exercise_id)
        try:
            question = definition.generate(planned.item_id, settings, self._rng)
        except (KeyError, ValueError):
            # An item that the current settings no longer cover, or a stale id.
            log.warning('cannot generate %s', planned.item_id, exc_info=True)
            return None
        if self.request.exercise_id is not None:
            settings_text = definition.describe_settings(settings)
        else:
            settings_text = definition.title
        return ShownQuestion(
            question=question,
            exercise_title=definition.title,
            settings_text=settings_text,
            play_label=definition.play_label,
            is_new=planned.is_new,
        )

    def _begin_grading(self) -> ShownQuestion:
        if self._graded:
            raise RuntimeError('the current question was already answered')
        self._graded = True
        return self._current

    def _record(
        self,
        definition: ExerciseDefinition,
        question: Question,
        correct: bool,
        response_ms: int,
        hinted: bool,
        given: object,
        score: float | None,
    ) -> None:
        outcome = Outcome(
            item_id=ItemId(question.item_id),
            exercise_id=question.exercise_id,
            correct=correct,
            response_ms=max(0, response_ms),
            answered_at=self._clock(),
            hinted=hinted,
            score=score,
            given='' if given is None else definition.serialize(given),
            expected=definition.serialize(question.expected),
        )
        self.engine.record(outcome)
        self.answered += 1
        if correct:
            self.correct += 1
            self.streak += 1
            self.best_today = max(self.best_today, self.streak)
        else:
            self.streak = 0
