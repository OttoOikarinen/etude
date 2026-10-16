# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the window shows, and where it comes from.

Pages render plain data classes (:class:`ExerciseCardData`,
:class:`ProgressData` …). An :class:`AppModel` produces them and starts
sessions. :class:`LiveModel` reads the learner's real progress through
:class:`~etude.services.Services`; ``etude.ui.preview.PreviewModel`` serves
the fixed numbers of the design mockups for screenshots and UI tests.
"""

from __future__ import annotations

import dataclasses
import random
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from gettext import gettext as _
from typing import Protocol

from gi.repository import Gio

from ..audio.spec import Instrument, PlaybackSpec
from ..exercises.base import ExerciseDefinition, Family, Feedback, Question
from ..exercises.runner import SessionRunner
from ..learning.model import ItemId, SessionMode, SessionRequest, SessionSummary
from ..learning.stats import EPOCH
from ..services import Services

# Page data --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExerciseCardData:
    """What the home page shows for one exercise."""

    id: str
    title: str
    description: str
    family: Family
    glyph: str
    """Short symbol drawn in the icon tile."""
    accuracy: float | None
    sessions: int
    recency: int
    """Lower = practised more recently; used by "Sort: Recent"."""


@dataclass(frozen=True, slots=True)
class ContinueData:
    exercise_id: str
    title: str
    answered: int
    total: int
    accuracy: float


@dataclass(frozen=True, slots=True)
class StreakData:
    days: int
    practised_today: bool


@dataclass(frozen=True, slots=True)
class WeakItem:
    title: str
    accuracy: float
    item_id: ItemId


@dataclass(frozen=True, slots=True)
class ProgressData:
    streak: int
    longest_streak: int
    accuracy: float
    accuracy_change: int
    """Percentage points compared with the previous period."""
    minutes: int
    sessions: int
    by_exercise: tuple[tuple[str, float], ...]
    answered: tuple[tuple[str, int], ...]
    """Questions answered per day (or week); the last entry is the current one."""
    weakest: tuple[WeakItem, ...]
    drill_count: int


# Sessions -------------------------------------------------------------------------


class ShownQuestionLike(Protocol):
    @property
    def question(self) -> Question: ...
    @property
    def exercise_title(self) -> str: ...
    @property
    def settings_text(self) -> str: ...
    @property
    def play_label(self) -> str | None: ...


class SessionSource(Protocol):
    """A running session as the exercise page's controller sees it
    (:class:`~etude.exercises.runner.SessionRunner` or the preview stub)."""

    @property
    def title(self) -> str: ...
    @property
    def current(self) -> ShownQuestionLike: ...
    @property
    def number(self) -> int: ...
    @property
    def total(self) -> int: ...
    @property
    def streak(self) -> int: ...
    @property
    def best_today(self) -> int: ...
    @property
    def accuracy(self) -> float | None: ...

    def answer(self, given: object, *, response_ms: int, hinted: bool = False) -> Feedback: ...
    def skip(self, *, response_ms: int) -> Feedback: ...
    def answer_label(self, value: object) -> str: ...
    def advance(self) -> bool: ...
    def finish(self) -> SessionSummary: ...
    def again(self) -> SessionSource: ...
    def review_mistakes(self, summary: SessionSummary) -> SessionSource: ...


class AppModel(Protocol):
    def exercise_cards(self) -> Sequence[ExerciseCardData]: ...
    def continue_data(self) -> ContinueData | None: ...
    def streak(self) -> StreakData: ...
    def progress(self, period: str) -> ProgressData: ...
    def definition(self, exercise_id: str) -> ExerciseDefinition | None: ...

    def start(
        self,
        mode: SessionMode,
        *,
        exercise_id: str | None = None,
        item_ids: tuple[ItemId, ...] = (),
    ) -> SessionSource:
        """Start a session; raises :class:`~etude.exercises.runner.EmptySessionError`
        when there is nothing to practise."""

    @property
    def audio_available(self) -> bool: ...
    def new_question(self) -> None: ...
    def play(self, spec: PlaybackSpec) -> None: ...
    def stop_audio(self) -> None: ...


# The real model -----------------------------------------------------------------------


def exercise_settings(settings: Gio.Settings | None, exercise_id: str) -> dict[str, object]:
    """The learner's saved settings of one exercise (``exercise-settings``)."""
    if settings is None:
        return {}
    stored = settings.get_value('exercise-settings').unpack()
    values = stored.get(exercise_id, {})
    return {k: tuple(v) if isinstance(v, list) else v for k, v in values.items()}


class LiveModel:
    def __init__(
        self,
        services: Services,
        settings: Gio.Settings | None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.services = services
        self.settings = settings
        self._clock = clock or (lambda: datetime.now(UTC))
        self._rng = random.Random()
        self._varied = Instrument.PIANO

    @property
    def stats(self):
        return self.services.engine.stats

    # Home

    def exercise_cards(self) -> list[ExerciseCardData]:
        now = self._clock()
        accuracy = self.stats.accuracy_by_exercise(EPOCH, now)
        records = self.services.sessions.between(EPOCH, now)
        counts = Counter(r.exercise_id for r in records if r.finished_at is not None)
        last: dict[str, datetime] = {}
        for record in records:
            if record.exercise_id is not None:
                last[record.exercise_id] = record.started_at
        order = sorted(last, key=lambda e: last[e], reverse=True)
        cards = []
        for definition in self.services.registry:
            ratio = accuracy[definition.id].ratio if definition.id in accuracy else None
            cards.append(
                ExerciseCardData(
                    id=definition.id,
                    title=definition.title,
                    description=definition.description,
                    family=definition.family,
                    glyph=definition.glyph,
                    accuracy=ratio,
                    sessions=counts[definition.id],
                    recency=order.index(definition.id) if definition.id in last else len(order),
                )
            )
        return cards

    def continue_data(self) -> ContinueData | None:
        return None

    def streak(self) -> StreakData:
        now = self._clock()
        streak = self.stats.streak(now)
        return StreakData(streak.current, self.stats.answered_today(now) > 0)

    # Progress (design 1h)

    def progress(self, period: str) -> ProgressData:
        now = self._clock()
        stats = self.stats
        days = {'week': 7, 'month': 28}.get(period)
        if days is None:
            start, end = EPOCH, now
            change = 0
        else:
            start, end = stats.period(now, days)
            points = stats.accuracy_change(now, days).change_points
            change = round(points) if points is not None else 0
        streak = stats.streak(now)
        accuracy = stats.accuracy(start, end).ratio
        registry = self.services.registry
        by_exercise = []
        for exercise_id, value in sorted(stats.accuracy_by_exercise(start, end).items()):
            ratio = value.ratio
            if ratio is None:
                continue
            try:
                title = registry.get(exercise_id).title
            except KeyError:
                continue
            by_exercise.append((title, ratio))
        weak = stats.weakest_items(now)
        weakest = []
        for item in weak:
            try:
                title = registry.get(item.exercise_id).item_label(item.item_id)
            except KeyError:
                title = item.item_id
            weakest.append(WeakItem(title, item.accuracy, item.item_id))
        return ProgressData(
            streak=streak.current,
            longest_streak=streak.longest,
            accuracy=accuracy or 0.0,
            accuracy_change=change,
            minutes=int(stats.time_practised(start, end) / timedelta(minutes=1)),
            sessions=stats.session_count(start, end),
            by_exercise=tuple(by_exercise),
            answered=self._answered(period, now),
            weakest=tuple(weakest),
            drill_count=len(weakest),
        )

    def _answered(self, period: str, now: datetime) -> tuple[tuple[str, int], ...]:
        stats = self.stats
        if period == 'week':
            per_day = stats.questions_per_day(now, 7)
            labels = [day.strftime('%a') for day, _count in per_day[:-1]] + [_('Today')]
            return tuple(zip(labels, (c for _d, c in per_day), strict=True))
        if period == 'month':
            per_day = stats.questions_per_day(now, 28)
            weeks = [sum(c for _d, c in per_day[i : i + 7]) for i in range(0, 28, 7)]
            labels = [
                # Translators: a bar of the "Questions answered" chart, e.g. "Week 2".
                _('Week {number}').format(number=n)
                for n in range(1, 4)
            ] + [_('This week')]
            return tuple(zip(labels, weeks, strict=True))
        per_day = stats.questions_per_day(now, 150)
        months: dict[tuple[int, int], int] = {}
        for day, count in per_day:
            months[(day.year, day.month)] = months.get((day.year, day.month), 0) + count
        keys = sorted(months)[-5:]
        labels = [date(y, m, 1).strftime('%b') for y, m in keys[:-1]] + [_('This month')]
        return tuple(zip(labels, (months[k] for k in keys), strict=True))

    # Exercises and sessions

    def definition(self, exercise_id: str) -> ExerciseDefinition | None:
        try:
            return self.services.registry.get(exercise_id)
        except KeyError:
            return None

    def start(
        self,
        mode: SessionMode,
        *,
        exercise_id: str | None = None,
        item_ids: tuple[ItemId, ...] = (),
    ) -> SessionRunner:
        size = self.settings.get_uint('questions-per-session') if self.settings else 20
        if item_ids:
            size = len(item_ids)
        request = SessionRequest(
            mode,
            now=self._clock(),
            size=size,
            exercise_id=exercise_id,
            settings=exercise_settings(self.settings, exercise_id) if exercise_id else {},
            item_ids=item_ids,
        )
        return SessionRunner(
            self.services.engine,
            self.services.registry,
            request,
            settings_for=lambda e: exercise_settings(self.settings, e),
            rng=self.services.rng,
            clock=self._clock,
        )

    # Audio

    @property
    def audio_available(self) -> bool:
        return self.services.audio.available

    def new_question(self) -> None:
        """Pick the timbre of the next question when the preference is "varied"."""
        self._varied = self._rng.choice(list(Instrument))

    def instrument_for(self, spec: PlaybackSpec) -> PlaybackSpec:
        """Apply the ``instrument`` preference. "Varied" uses one random timbre per
        question, so replays of a question sound the same."""
        choice = self.settings.get_string('instrument') if self.settings else 'piano'
        if choice == 'varied':
            return dataclasses.replace(spec, instrument=self._varied)
        try:
            return dataclasses.replace(spec, instrument=Instrument[choice.upper()])
        except KeyError:
            return spec

    def play(self, spec: PlaybackSpec) -> None:
        self.services.audio.play(self.instrument_for(spec))

    def stop_audio(self) -> None:
        self.services.audio.stop()
