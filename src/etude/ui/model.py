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
from typing import ClassVar, Protocol

from gi.repository import Gio

from ..audio.spec import Instrument, PlaybackSpec
from ..exercises.base import ExerciseDefinition, Family, Feedback, Question
from ..exercises.runner import SessionRunner
from ..learning.model import ItemId, SessionMode, SessionRequest, SessionSummary
from ..learning.stats import EPOCH, Stats
from ..services import Services


def weekday_label(day: date) -> str:
    """Short weekday in the UI language (not the system's date locale)."""
    names = (
        # Translators: short weekday names under the "Questions answered" chart.
        _('Mon'),
        _('Tue'),
        _('Wed'),
        _('Thu'),
        _('Fri'),
        _('Sat'),
        _('Sun'),
    )
    return names[day.weekday()]


def month_label(month: int) -> str:
    """Short month name in the UI language."""
    names = (
        # Translators: short month names under the "Questions answered" chart.
        _('Jan'),
        _('Feb'),
        _('Mar'),
        _('Apr'),
        _('May'),
        _('Jun'),
        _('Jul'),
        _('Aug'),
        _('Sep'),
        _('Oct'),
        _('Nov'),
        _('Dec'),
    )
    return names[month - 1]


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
    """Accuracy over the learner's most recent answers; ``None`` before the first one."""
    sessions: int
    recency: int
    """Lower = practised more recently; used by "Sort: Recent"."""


@dataclass(frozen=True, slots=True)
class ContinueData:
    """An interrupted session the learner can resume (design 1a's Continue banner)."""

    exercise_id: str | None
    """``None`` for mixed sessions such as the daily review."""
    title: str
    answered: int
    total: int
    accuracy: float
    """Accuracy of this session so far."""
    glyph: str = '♪'


@dataclass(frozen=True, slots=True)
class StreakData:
    days: int
    practised_today: bool


@dataclass(frozen=True, slots=True)
class DueExercise:
    exercise_id: str
    title: str
    glyph: str
    due: int


@dataclass(frozen=True, slots=True)
class TodayData:
    """The Today page: what the daily review holds, and the daily goal."""

    due: int
    """Items due for review now, across all exercises."""
    new: int
    """New items daily reviews may still introduce today."""
    by_exercise: tuple[DueExercise, ...]
    """Due items per exercise, most first."""
    answered_today: int
    daily_goal: int
    streak: int
    goal_met: bool
    session_size: int = 20
    """Questions in one daily review (``questions-per-session``)."""
    new_held_back: bool = False
    """No new items for now: recent accuracy is below the 85 % target."""

    @property
    def caught_up(self) -> bool:
        """Nothing is due and nothing new is waiting: the daily review is empty."""
        return self.due == 0 and self.new == 0


@dataclass(frozen=True, slots=True)
class WeakItem:
    title: str
    accuracy: float
    item_id: ItemId


@dataclass(frozen=True, slots=True)
class ProgressData:
    streak: int
    longest_streak: int
    accuracy: float | None
    """``None`` when nothing was answered in the period."""
    accuracy_change: int | None
    """Percentage points compared with the previous period; ``None`` without a comparison."""
    minutes: int
    sessions: int
    by_exercise: tuple[tuple[str, float], ...]
    answered: tuple[tuple[str, int], ...]
    """Questions answered per day (or week); the last entry is the current one."""
    weakest: tuple[WeakItem, ...]
    """The weakest items listed on the page (the first few of :attr:`drill_items`)."""
    drill_count: int
    drill_items: tuple[ItemId, ...] = ()
    """What "Drill these N items" practises; the listed items when empty."""


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
    def today(self) -> TodayData: ...
    def progress(self, period: str) -> ProgressData:
        """``period`` is ``'week'`` (7 days), ``'month'`` (30 days) or ``'all'``."""

    def definition(self, exercise_id: str) -> ExerciseDefinition | None: ...

    def start(
        self,
        mode: SessionMode,
        *,
        exercise_id: str | None = None,
        item_ids: tuple[ItemId, ...] = (),
    ) -> SessionSource:
        """Start a session; raises :class:`~etude.exercises.runner.EmptySessionError`
        when there is nothing to practise. An interrupted session is finished first."""

    def close_session(self, session: SessionSource) -> None:
        """The learner left the exercise page: keep an unfinished session for
        :meth:`resume` (the Continue banner)."""

    def resume(self) -> SessionSource | None:
        """The interrupted session, ready to go on; ``None`` when there is none."""

    def dismiss_continue(self) -> None:
        """Finish the interrupted session without resuming it; its answers count."""

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
    """Page data from the learner's real progress, and real sessions.

    An exercise page closed before the end of its session leaves the session
    *interrupted*: the runner is kept in memory, paused, and offered on the
    home page's Continue banner until it is resumed, dismissed, or another
    session starts (which finishes it, so its answers and time count). It is
    not kept across restarts: :meth:`shutdown` finishes it.
    """

    WEAK_ROWS = 5
    """Weakest items listed on the progress page; the drill takes all of them."""
    DUE_LIMIT = 100_000
    """Upper bound when counting due cards."""

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
        self._paused: SessionRunner | None = None
        self._goal_handler = 0
        if settings is not None:
            self._apply_daily_goal(settings)
            self._goal_handler = settings.connect('changed::daily-goal', self._on_goal_changed)

    @property
    def stats(self) -> Stats:
        return self.services.engine.stats

    def _apply_daily_goal(self, settings: Gio.Settings) -> None:
        self.stats.set_daily_goal(max(1, settings.get_uint('daily-goal')))

    def _on_goal_changed(self, settings: Gio.Settings, _key: str) -> None:
        self._apply_daily_goal(settings)

    def _session_size(self) -> int:
        return self.settings.get_uint('questions-per-session') if self.settings else 20

    def shutdown(self) -> None:
        """Finish an interrupted session so that it counts; call before closing services."""
        self._finish_paused()
        if self.settings is not None and self._goal_handler:
            self.settings.disconnect(self._goal_handler)
            self._goal_handler = 0

    # Home (design 1a)

    def exercise_cards(self) -> list[ExerciseCardData]:
        now = self._clock()
        registry = self.services.registry
        activity = self.stats.exercise_activity(registry.exercise_ids(), now)
        practised = sorted(
            (a.last_answered, e) for e, a in activity.items() if a.last_answered is not None
        )
        order = [e for _last, e in reversed(practised)]
        cards = []
        for definition in registry:
            info = activity[definition.id]
            cards.append(
                ExerciseCardData(
                    id=definition.id,
                    title=definition.title,
                    description=definition.description,
                    family=definition.family,
                    glyph=definition.glyph,
                    accuracy=info.recent.ratio,
                    sessions=info.sessions,
                    recency=order.index(definition.id) if definition.id in order else len(order),
                )
            )
        return cards

    def continue_data(self) -> ContinueData | None:
        runner = self._paused
        if runner is None:
            return None
        if not runner.is_open:
            self._paused = None
            return None
        exercise_id = runner.request.exercise_id
        definition = self.definition(exercise_id) if exercise_id else None
        return ContinueData(
            exercise_id=exercise_id,
            title=runner.title,
            answered=runner.answered,
            total=runner.total,
            accuracy=runner.accuracy or 0.0,
            glyph=definition.glyph if definition is not None else '♪',
        )

    def streak(self) -> StreakData:
        now = self._clock()
        streak = self.stats.streak(now)
        return StreakData(streak.current, self.stats.answered_today(now) > 0)

    # Today

    def today(self) -> TodayData:
        now = self._clock()
        registry = self.services.registry
        counts: Counter[str] = Counter()
        for card in self.services.cards.due(now, limit=self.DUE_LIMIT):
            try:
                counts[registry.exercise_for(card.item_id)] += 1
            except KeyError:
                continue  # an item of an exercise that no longer exists
        by_exercise = []
        for exercise_id, due in counts.items():
            definition = registry.get(exercise_id)
            by_exercise.append(DueExercise(exercise_id, definition.title, definition.glyph, due))
        by_exercise.sort(key=lambda d: (-d.due, d.title.casefold()))
        new = self.services.engine.new_items(now)
        streak = self.stats.streak(now)
        return TodayData(
            due=sum(counts.values()),
            new=new.available,
            by_exercise=tuple(by_exercise),
            answered_today=self.stats.answered_today(now),
            daily_goal=self.stats.config.daily_goal,
            streak=streak.current,
            goal_met=streak.today_met,
            session_size=self._session_size(),
            new_held_back=new.held_back,
        )

    # Progress (design 1h)

    PERIOD_DAYS: ClassVar[dict[str, int]] = {'week': 7, 'month': 30}

    def progress(self, period: str) -> ProgressData:
        now = self._clock()
        stats = self.stats
        days = self.PERIOD_DAYS.get(period)
        if days is None:
            start, end = EPOCH, now
            change: int | None = None
        else:
            start, end = stats.period(now, days)
            points = stats.accuracy_change(now, days).change_points
            change = round(points) if points is not None else None
        streak = stats.streak(now)
        registry = self.services.registry
        by_exercise = []
        for exercise_id, value in stats.accuracy_by_exercise(start, end).items():
            ratio = value.ratio
            if ratio is None:
                continue
            try:
                title = registry.get(exercise_id).title
            except KeyError:
                continue
            by_exercise.append((title, ratio))
        by_exercise.sort(key=lambda entry: entry[0].casefold())
        weakest = []
        for item in stats.weakest_items(now):
            try:
                title = registry.get(item.exercise_id).item_label(item.item_id)
            except KeyError:
                continue  # the exercise no longer exists, so it cannot be drilled
            weakest.append(WeakItem(title, item.accuracy, item.item_id))
        return ProgressData(
            streak=streak.current,
            longest_streak=streak.longest,
            accuracy=stats.accuracy(start, end).ratio,
            accuracy_change=change,
            minutes=int(stats.time_practised(start, end) / timedelta(minutes=1)),
            sessions=stats.session_count(start, end),
            by_exercise=tuple(by_exercise),
            answered=self._answered(period, now),
            weakest=tuple(weakest[: self.WEAK_ROWS]),
            drill_count=len(weakest),
            drill_items=tuple(w.item_id for w in weakest),
        )

    def _answered(self, period: str, now: datetime) -> tuple[tuple[str, int], ...]:
        stats = self.stats
        if period == 'week':
            per_day = stats.questions_per_day(now, 7)
            labels = [weekday_label(day) for day, _count in per_day[:-1]] + [_('Today')]
            return tuple(zip(labels, (c for _d, c in per_day), strict=True))
        if period == 'month':
            # Four bars that add up to the 30 days of the other numbers: the
            # current week, the two before it, and the nine days before those.
            counts = [c for _d, c in stats.questions_per_day(now, 30)]
            bars = [sum(counts[:9]), sum(counts[9:16]), sum(counts[16:23]), sum(counts[23:])]
            labels = [
                # Translators: a bar of the "Questions answered" chart, e.g. "Week 2".
                _('Week {number}').format(number=n)
                for n in range(1, 4)
            ] + [_('This week')]
            return tuple(zip(labels, bars, strict=True))
        per_day = stats.questions_per_day(now, 150)
        months: dict[tuple[int, int], int] = {}
        for day, count in per_day:
            months[(day.year, day.month)] = months.get((day.year, day.month), 0) + count
        keys = sorted(months)[-5:]
        labels = [month_label(m) for _y, m in keys[:-1]] + [_('This month')]
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
        # Finish an interrupted session first, through its runner, so the
        # runner knows it is closed (the engine would finish it anyway).
        self._finish_paused()
        size = len(item_ids) if item_ids else self._session_size()
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

    def close_session(self, session: SessionSource) -> None:
        if not isinstance(session, SessionRunner) or not session.is_open:
            return
        if session.is_answered and not session.advance():
            session.finish()  # the last question was answered: the session is complete
            return
        if session.answered == 0:
            session.finish()  # nothing to come back to; empty sessions do not count
            return
        session.pause()
        self._paused = session

    def resume(self) -> SessionRunner | None:
        runner, self._paused = self._paused, None
        if runner is None or not runner.is_open:
            return None
        runner.resume()
        return runner

    def dismiss_continue(self) -> None:
        self._finish_paused()

    def _finish_paused(self) -> None:
        runner, self._paused = self._paused, None
        if runner is not None and runner.is_open:
            runner.finish()

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
