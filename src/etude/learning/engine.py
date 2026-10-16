# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The facade the UI uses to run sessions.

A typical session::

    plan = engine.start_session(SessionRequest(SessionMode.DAILY_REVIEW, now=now))
    for planned in plan:
        ...  # generate, show and grade a question
        engine.record(outcome)
    summary = engine.finish_session()
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, tzinfo

from .model import Card, Outcome, PlannedQuestion, SessionMode, SessionRequest, SessionSummary
from .ports import AttemptLog, CardStore, ItemCatalog, Scheduler, SessionLog
from .rating import derive_rating
from .scheduler import FsrsScheduler
from .session import Confusables, SessionBuilder, SessionConfig
from .stats import Stats, StatsConfig


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class _ActiveSession:
    id: int
    mode: SessionMode
    exercise_id: str | None
    started_at: datetime
    plan: list[PlannedQuestion]
    outcomes: list[Outcome] = field(default_factory=list)


class LearningEngine:
    def __init__(
        self,
        *,
        builder: SessionBuilder,
        cards: CardStore,
        attempts: AttemptLog,
        sessions: SessionLog,
        scheduler: Scheduler,
        stats: Stats,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._builder = builder
        self._cards = cards
        self._attempts = attempts
        self._sessions = sessions
        self._scheduler = scheduler
        self.stats = stats
        self._clock = clock
        self._active: _ActiveSession | None = None

    @classmethod
    def create(
        cls,
        catalog: ItemCatalog,
        cards: CardStore,
        attempts: AttemptLog,
        sessions: SessionLog,
        *,
        tzinfo: tzinfo = UTC,
        scheduler: Scheduler | None = None,
        rng: random.Random | None = None,
        session_config: SessionConfig | None = None,
        stats_config: StatsConfig | None = None,
        confusables: Confusables | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> LearningEngine:
        """Wire up an engine with the default FSRS scheduler and the learner's time zone."""
        rng = rng if rng is not None else random.Random()
        scheduler = scheduler if scheduler is not None else FsrsScheduler(rng=rng)
        session_config = replace(session_config or SessionConfig(), tzinfo=tzinfo)
        builder = SessionBuilder(
            catalog, cards, attempts, scheduler, rng, session_config, confusables=confusables
        )
        stats = Stats(attempts, sessions, tzinfo=tzinfo, cards=cards, config=stats_config)
        return cls(
            builder=builder,
            cards=cards,
            attempts=attempts,
            sessions=sessions,
            scheduler=scheduler,
            stats=stats,
            clock=clock,
        )

    @property
    def active_plan(self) -> list[PlannedQuestion] | None:
        return None if self._active is None else list(self._active.plan)

    def start_session(self, request: SessionRequest) -> list[PlannedQuestion]:
        """Plan a session and open it in the session log.

        An unfinished previous session is finished first, so its answers keep
        counting towards time practised.
        """
        if self._active is not None:
            self.finish_session(request.now)
        plan = self._builder.build(request)
        session_id = self._sessions.start(request.mode, request.exercise_id, request.now)
        self._active = _ActiveSession(
            session_id, request.mode, request.exercise_id, request.now, plan
        )
        return list(plan)

    def record(self, outcome: Outcome) -> Card:
        """Rate an answer, reschedule its item and store both; returns the new card.

        Answers given outside a session (for example in a lesson's check
        question) are recorded without a session id.
        """
        speed = self.stats.speed_thresholds(outcome.exercise_id)
        rating = derive_rating(outcome, fast_ms=speed.fast_ms, slow_ms=speed.slow_ms)
        card = self._cards.get(outcome.item_id) or self._scheduler.new_card(
            outcome.item_id, outcome.answered_at
        )
        card = self._scheduler.review(card, rating, outcome.answered_at)
        self._cards.put(card)
        self._attempts.add(outcome, None if self._active is None else self._active.id)
        if self._active is not None:
            self._active.outcomes.append(outcome)
        return card

    def finish_session(self, now: datetime | None = None) -> SessionSummary:
        """Close the active session and return its summary."""
        active = self._active
        if active is None:
            raise RuntimeError('no session is active')
        finished_at = self._clock() if now is None else now
        summary = self.stats.session_summary(
            active.outcomes,
            mode=active.mode,
            exercise_id=active.exercise_id,
            started_at=active.started_at,
            finished_at=finished_at,
        )
        self._sessions.finish(active.id, finished_at, summary)
        self._active = None
        return summary
