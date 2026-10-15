# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Value types shared by scheduling, sessions, statistics and storage.

The unit of learning is a *knowledge item*: a hierarchical id such as
``interval.ear.melodic.asc.m6`` or ``keysig.major.6b``. Exercises turn an
item into a fresh concrete question every time (new root, register, clef,
timbre), so learners acquire the concept instead of memorising one
question. Each item has one FSRS :class:`Card`.

All datetimes are timezone-aware UTC.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from typing import NewType

ItemId = NewType('ItemId', str)


class Rating(IntEnum):
    """FSRS ratings. Derived automatically from answers; learners never rate themselves."""

    AGAIN = 1
    HARD = 2
    GOOD = 3
    EASY = 4


class CardState(IntEnum):
    LEARNING = 1
    REVIEW = 2
    RELEARNING = 3


@dataclass(frozen=True, slots=True)
class Card:
    """Scheduling state of one knowledge item (mirrors ``fsrs.Card``)."""

    item_id: ItemId
    due: datetime
    state: CardState = CardState.LEARNING
    step: int | None = 0
    stability: float | None = None
    difficulty: float | None = None
    last_review: datetime | None = None
    reps: int = 0
    lapses: int = 0


@dataclass(frozen=True, slots=True)
class Outcome:
    """One answered question."""

    item_id: ItemId
    exercise_id: str
    correct: bool
    response_ms: int
    answered_at: datetime
    hinted: bool = False
    score: float | None = None
    """Partial credit in 0–1 for multi-part answers (dictation); ``None`` = all or nothing."""
    given: str = ''
    """The learner's answer, serialised by the exercise, for "Review mistakes"."""
    expected: str = ''


class SessionMode(Enum):
    DAILY_REVIEW = 'daily_review'
    """Interleaved review of due items across all exercises, plus a few new items."""
    EXERCISE = 'exercise'
    """One exercise with the learner's settings (design 1b–1g)."""
    DRILL_WEAK = 'drill_weak'
    """The weakest items (design 1h, "Drill these 15 items")."""
    REVIEW_MISTAKES = 'review_mistakes'
    """Repeat the items missed in a just-finished session (design 1i)."""
    PLACEMENT = 'placement'
    LEVEL_EXAM = 'level_exam'


@dataclass(frozen=True, slots=True)
class SessionRequest:
    mode: SessionMode
    now: datetime
    size: int = 20
    exercise_id: str | None = None
    settings: Mapping[str, object] = field(default_factory=dict)
    item_ids: tuple[ItemId, ...] = ()
    """Explicit items for ``REVIEW_MISTAKES`` and ``DRILL_WEAK``."""


@dataclass(frozen=True, slots=True)
class PlannedQuestion:
    exercise_id: str
    item_id: ItemId
    is_new: bool = False


@dataclass(frozen=True, slots=True)
class SessionSummary:
    """Numbers shown in the session-complete dialog (design 1i)."""

    total: int
    correct: int
    duration_ms: int
    best_streak: int
    personal_best: bool
    mistakes: tuple[ItemId, ...]
