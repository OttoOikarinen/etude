# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Statistics for the progress page (design 1h) and the session summary (design 1i).

Days are the learner's local calendar days, so every day-based query uses
the ``tzinfo`` given to :class:`Stats`; a day may be 23 or 25 hours long
across a daylight-saving change. Stored datetimes stay UTC.
"""

from __future__ import annotations

import statistics
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta, tzinfo

from .model import Card, ItemId, Outcome, SessionMode, SessionRecord, SessionSummary
from .ports import AttemptLog, CardStore, SessionLog

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class StatsConfig:
    daily_goal: int = 30
    """Questions per day that keep the streak (GSettings ``daily-goal``)."""
    weak_min_attempts: int = 3
    """Fewer attempts than this say too little about an item to call it weak."""
    weak_window: timedelta = timedelta(days=90)
    """Only recent attempts count towards weakness: old mistakes that were fixed do not."""
    speed_samples: int = 200
    """Most recent correct, unhinted answers of an exercise used for speed percentiles."""
    speed_min_samples: int = 20
    """Below this many samples the default speed thresholds are used."""
    default_fast_ms: float = 2500.0
    default_slow_ms: float = 8000.0
    recent_answers: int = 100
    """Answers an exercise's "current" accuracy is computed over (the home page cards)."""


@dataclass(frozen=True, slots=True)
class Streak:
    current: int
    longest: int
    today_met: bool
    """Whether today already counts; the current streak survives until the day is over."""


@dataclass(frozen=True, slots=True)
class Accuracy:
    correct: int
    total: int

    @property
    def ratio(self) -> float | None:
        return self.correct / self.total if self.total else None


@dataclass(frozen=True, slots=True)
class AccuracyChange:
    current: Accuracy
    previous: Accuracy

    @property
    def change_points(self) -> float | None:
        """Change in percentage points, or ``None`` when either period has no answers."""
        now, before = self.current.ratio, self.previous.ratio
        if now is None or before is None:
            return None
        return (now - before) * 100.0


@dataclass(frozen=True, slots=True)
class ItemStats:
    item_id: ItemId
    exercise_id: str
    attempts: int
    correct: int
    lapses: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.attempts


@dataclass(frozen=True, slots=True)
class SpeedThresholds:
    fast_ms: float
    slow_ms: float
    samples: int
    """``0`` when the defaults are used."""


@dataclass(frozen=True, slots=True)
class ExerciseActivity:
    """How much and how well the learner has practised one exercise (home page cards)."""

    recent: Accuracy
    """Accuracy over the last :attr:`StatsConfig.recent_answers` answers, in any session."""
    last_answered: datetime | None
    sessions: int
    """Finished sessions of this exercise that have at least one answer."""


@dataclass(slots=True)
class _ItemTally:
    exercise_id: str
    attempts: int = 0
    correct: int = 0
    wrong: int = 0


def weakest_items(
    outcomes: Iterable[Outcome],
    *,
    limit: int,
    min_attempts: int,
    cards: Mapping[ItemId, Card] | None = None,
) -> list[ItemStats]:
    """Items with the lowest accuracy among those with at least ``min_attempts`` attempts.

    Ties are broken by lapses (more first): FSRS lapses when ``cards`` are
    given, otherwise the number of wrong answers. Items answered perfectly are
    never weak.
    """
    tallies: dict[ItemId, _ItemTally] = {}
    for outcome in outcomes:
        tally = tallies.setdefault(outcome.item_id, _ItemTally(outcome.exercise_id))
        tally.attempts += 1
        tally.correct += outcome.correct
        tally.wrong += not outcome.correct
    stats = [
        ItemStats(
            item_id=item_id,
            exercise_id=tally.exercise_id,
            attempts=tally.attempts,
            correct=tally.correct,
            lapses=(
                cards[item_id].lapses if cards is not None and item_id in cards else tally.wrong
            ),
        )
        for item_id, tally in tallies.items()
        if tally.attempts >= min_attempts and tally.correct < tally.attempts
    ]
    stats.sort(key=lambda s: (s.accuracy, -s.lapses, -s.attempts, s.item_id))
    return stats[:limit]


def longest_correct_run(outcomes: Iterable[Outcome]) -> int:
    best = run = 0
    for outcome in outcomes:
        run = run + 1 if outcome.correct else 0
        best = max(best, run)
    return best


class Stats:
    """Read-only queries over the attempt and session logs."""

    def __init__(
        self,
        attempts: AttemptLog,
        sessions: SessionLog,
        *,
        tzinfo: tzinfo = UTC,
        cards: CardStore | None = None,
        config: StatsConfig | None = None,
    ) -> None:
        self._attempts = attempts
        self._sessions = sessions
        self._tz = tzinfo
        self._cards = cards
        self.config = config if config is not None else StatsConfig()

    def set_daily_goal(self, goal: int) -> None:
        """Apply a new daily goal (the ``daily-goal`` setting) to every later query."""
        if goal < 1:
            raise ValueError(f'the daily goal must be at least 1, not {goal}')
        self.config = replace(self.config, daily_goal=goal)

    # Calendar helpers

    def local_date(self, moment: datetime) -> date:
        return moment.astimezone(self._tz).date()

    def day_start(self, day: date) -> datetime:
        """The UTC instant at which local ``day`` begins."""
        return datetime.combine(day, time(), tzinfo=self._tz).astimezone(UTC)

    def day_range(self, day: date) -> tuple[datetime, datetime]:
        return self.day_start(day), self.day_start(day + timedelta(days=1))

    def period(self, now: datetime, days: int) -> tuple[datetime, datetime]:
        """The last ``days`` local days including today, as a UTC ``[start, end)``."""
        today = self.local_date(now)
        return self.day_start(today - timedelta(days=days - 1)), self.day_range(today)[1]

    # Daily activity

    def _counts_by_day(self, outcomes: Iterable[Outcome]) -> Counter[date]:
        return Counter(self.local_date(o.answered_at) for o in outcomes)

    def answered_today(self, now: datetime) -> int:
        return len(self._attempts.between(*self.day_range(self.local_date(now))))

    def best_run_today(self, now: datetime) -> int:
        """Longest run of correct answers today (the exercise footer's "Best today")."""
        outcomes = self._attempts.between(*self.day_range(self.local_date(now)))
        return longest_correct_run(sorted(outcomes, key=lambda o: o.answered_at))

    def questions_per_day(self, now: datetime, days: int = 7) -> list[tuple[date, int]]:
        """Answers on each of the last ``days`` local days, oldest first, including today."""
        counts = self._counts_by_day(self._attempts.between(*self.period(now, days)))
        today = self.local_date(now)
        return [
            (day, counts[day]) for day in (today - timedelta(days=n) for n in reversed(range(days)))
        ]

    def streak(self, now: datetime) -> Streak:
        """Consecutive local days on which the daily goal was met.

        Today counts once its goal is met; until then the streak still runs
        from yesterday, so nobody loses a streak in the morning.
        """
        counts = self._counts_by_day(self._attempts.between(EPOCH, self.period(now, 1)[1]))
        goal = self.config.daily_goal
        met = sorted(day for day, count in counts.items() if count >= goal)
        longest = run = 0
        previous: date | None = None
        for day in met:
            run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
            longest = max(longest, run)
            previous = day
        today = self.local_date(now)
        today_met = counts[today] >= goal
        current = 0
        day = today if today_met else today - timedelta(days=1)
        met_set = set(met)
        while day in met_set:
            current += 1
            day -= timedelta(days=1)
        return Streak(current=current, longest=longest, today_met=today_met)

    # Accuracy

    def accuracy(self, start: datetime, end: datetime) -> Accuracy:
        outcomes = self._attempts.between(start, end)
        return Accuracy(correct=sum(o.correct for o in outcomes), total=len(outcomes))

    def accuracy_change(self, now: datetime, days: int = 7) -> AccuracyChange:
        """Accuracy of the last ``days`` local days against the ``days`` before them."""
        start, end = self.period(now, days)
        earlier = self.day_start(self.local_date(start) - timedelta(days=days))
        return AccuracyChange(
            current=self.accuracy(start, end), previous=self.accuracy(earlier, start)
        )

    def accuracy_by_exercise(self, start: datetime, end: datetime) -> dict[str, Accuracy]:
        correct: Counter[str] = Counter()
        total: Counter[str] = Counter()
        for outcome in self._attempts.between(start, end):
            total[outcome.exercise_id] += 1
            correct[outcome.exercise_id] += outcome.correct
        return {
            exercise: Accuracy(correct=correct[exercise], total=count)
            for exercise, count in sorted(total.items())
        }

    # Sessions

    def _finished_sessions(self, start: datetime, end: datetime) -> list[SessionRecord]:
        """Finished sessions started in ``[start, end)`` in which something was answered.

        A session closed before its first answer is not practice: it counts
        neither as a session nor towards time practised or personal bests.
        """
        return [
            s
            for s in self._sessions.between(start, end)
            if s.summary is not None and s.summary.total > 0
        ]

    def time_practised(self, start: datetime, end: datetime) -> timedelta:
        """Total duration of the finished sessions started in ``[start, end)``."""
        return timedelta(
            milliseconds=sum(
                s.summary.duration_ms
                for s in self._finished_sessions(start, end)
                if s.summary is not None
            )
        )

    def session_count(self, start: datetime, end: datetime) -> int:
        return len(self._finished_sessions(start, end))

    def exercise_activity(
        self, exercise_ids: Iterable[str], now: datetime
    ) -> dict[str, ExerciseActivity]:
        """Recent accuracy, last answer and session count of each exercise up to ``now``."""
        sessions = Counter(
            s.exercise_id for s in self._finished_sessions(EPOCH, now) if s.exercise_id is not None
        )
        result = {}
        for exercise_id in exercise_ids:
            recent = [
                o
                for o in self._attempts.recent(
                    exercise_id=exercise_id, limit=self.config.recent_answers
                )
                if o.answered_at <= now
            ]
            result[exercise_id] = ExerciseActivity(
                recent=Accuracy(correct=sum(o.correct for o in recent), total=len(recent)),
                last_answered=max((o.answered_at for o in recent), default=None),
                sessions=sessions[exercise_id],
            )
        return result

    # Items

    def weakest_items(
        self, now: datetime, *, limit: int = 15, exercise_id: str | None = None
    ) -> list[ItemStats]:
        outcomes = self._attempts.between(now - self.config.weak_window, now)
        if exercise_id is not None:
            outcomes = [o for o in outcomes if o.exercise_id == exercise_id]
        cards = (
            self._cards.get_many({o.item_id for o in outcomes}) if self._cards is not None else None
        )
        return weakest_items(
            outcomes, limit=limit, min_attempts=self.config.weak_min_attempts, cards=cards
        )

    def speed_thresholds(self, exercise_id: str) -> SpeedThresholds:
        """The learner's 25th and 75th percentile response times in an exercise.

        Correct answers faster than ``fast_ms`` are rated EASY and slower than
        ``slow_ms`` HARD (:func:`etude.learning.rating.derive_rating`). Only
        correct, unhinted answers count: they are the learner's real speed.
        """
        samples = [
            o.response_ms
            for o in self._attempts.recent(exercise_id=exercise_id, limit=self.config.speed_samples)
            if o.correct and not o.hinted
        ]
        if len(samples) < self.config.speed_min_samples:
            return SpeedThresholds(self.config.default_fast_ms, self.config.default_slow_ms, 0)
        p25, _median, p75 = statistics.quantiles(samples, n=4, method='inclusive')
        return SpeedThresholds(fast_ms=p25, slow_ms=p75, samples=len(samples))

    def session_summary(
        self,
        outcomes: Sequence[Outcome],
        *,
        mode: SessionMode,
        exercise_id: str | None,
        started_at: datetime,
        finished_at: datetime,
        paused: timedelta = timedelta(),
    ) -> SessionSummary:
        """Numbers for the session-complete dialog.

        ``paused`` is time the session spent interrupted (closed and resumed
        later from the home page's Continue banner); it does not count as
        practice. ``personal_best`` means the longest run of correct answers beats every
        earlier finished session of the same mode and exercise; a first session
        has nothing to beat and is not a personal best.
        """
        best_streak = longest_correct_run(outcomes)
        earlier = [
            s.summary.best_streak
            for s in self._finished_sessions(EPOCH, started_at)
            if s.summary is not None and s.mode is mode and s.exercise_id == exercise_id
        ]
        mistakes = tuple(dict.fromkeys(o.item_id for o in outcomes if not o.correct))
        duration = max(finished_at - started_at - paused, timedelta())
        return SessionSummary(
            total=len(outcomes),
            correct=sum(o.correct for o in outcomes),
            duration_ms=duration // timedelta(milliseconds=1),
            best_streak=best_streak,
            personal_best=bool(earlier) and best_streak > max(earlier),
            mistakes=mistakes,
        )
