# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The learning path: curriculum units as knowledge items, unlocking, level
exams and the placement test.

* A unit's **items** are the union over its practices of the items its
  exercise covers with the practice's settings (on top of the exercise's
  defaults), plus the vocabulary exercise's items for the unit's glossary
  entries when that exercise is registered.
* A unit is **complete** when :attr:`MasteryConfig.unlock_fraction` (80 %) of
  its items are mastered (``etude.learning.mastery``), when the placement test
  placed the learner out of it, or when its level exam was passed. A unit
  without items (a lesson-only unit) is complete as soon as it is unlocked,
  so it neither blocks the path nor opens the way past the units before it.
* A unit is **unlocked** when every unit it requires is complete. The first
  unit of the curriculum is always unlocked; the first unit of a later level
  unlocks when the previous level is passed or all its units are complete.
  Placed-out units and units of a passed level are unlocked too. Locked
  units can still be read and, after a confirmation, practised: the lock is
  advice, not a wall (learner autonomy, docs/PEDAGOGY.md).
* The **level exam** samples the level's items evenly per unit; passing it
  (:data:`~etude.learning.placement.PASS_FRACTION`, 80 %) marks the level as
  passed. See ``etude.learning.placement`` for the reasoning.
* The **placement test** walks the units in curriculum order, asking about
  what each unit adds to the units before it, and places the learner out of
  units until the first one they do not know.

What is persisted (passed levels and placed-out units) is a
:class:`PathRecord`; the UI keeps it in GSettings.
"""

from __future__ import annotations

import itertools
import logging
import random
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from gettext import gettext as _
from typing import Any

from ..content.library import ContentLibrary
from ..content.model import Level, Practice, Unit
from ..learning.engine import LearningEngine
from ..learning.mastery import Mastery
from ..learning.model import ItemId, SessionRequest, SessionSummary
from ..learning.placement import PLACEMENT_SAMPLE, PlacementWalk, balanced_sample, needed, passes
from .base import Feedback
from .registry import ExerciseRegistry
from .runner import SessionRunner
from .settings import SettingError, coerce

log = logging.getLogger(__name__)

VOCABULARY_EXERCISE = 'vocabulary'
"""The vocabulary flashcards; its items are ``vocab.<glossary entry id>.<direction>``."""


@dataclass(frozen=True, slots=True)
class PathRecord:
    """What the learner achieved outside of mastery: passed exams and placement."""

    passed_levels: frozenset[str] = frozenset()
    placed_units: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class UnitStatus:
    unit: Unit
    items: tuple[ItemId, ...]
    mastered: int
    """Items of the unit that are mastered."""
    placed: bool
    complete: bool
    unlocked: bool
    missing: tuple[Unit, ...] = ()
    """Units that must be completed before this one unlocks (empty when unlocked)."""

    @property
    def fraction(self) -> float | None:
        """Share of mastered items; ``None`` for a unit without items."""
        return self.mastered / len(self.items) if self.items else None


@dataclass(frozen=True, slots=True)
class LevelStatus:
    level: Level
    units: tuple[UnitStatus, ...]
    passed: bool

    @property
    def items(self) -> tuple[ItemId, ...]:
        return tuple(dict.fromkeys(i for u in self.units for i in u.items))

    @property
    def completed(self) -> int:
        return sum(u.complete for u in self.units)

    @property
    def exam_ready(self) -> bool:
        """The learner reached the end of the level: every unit is unlocked."""
        return all(u.unlocked for u in self.units)


@dataclass(frozen=True, slots=True)
class PlacementPlan:
    samples: tuple[tuple[str, tuple[ItemId, ...]], ...]
    """Units in curriculum order with the items asked about each."""
    followers: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    """Units placed out together with a sampled unit: everything they practise
    was already sampled for the units before them."""

    @property
    def items(self) -> tuple[ItemId, ...]:
        return tuple(i for _unit, items in self.samples for i in items)


class LearningPath:
    """The curriculum of a :class:`ContentLibrary` against the exercises and the
    learner's mastery."""

    def __init__(
        self, library: ContentLibrary, registry: ExerciseRegistry, mastery: Mastery
    ) -> None:
        self.library = library
        self.curriculum = library.curriculum
        self.registry = registry
        self.mastery = mastery
        self._items: dict[str, tuple[ItemId, ...]] = {}

    # Items

    def practice_settings(self, practice: Practice) -> dict[str, object] | None:
        """The practice's settings as values; ``None`` when its exercise is unknown."""
        try:
            definition = self.registry.get(practice.exercise_id)
        except KeyError:
            log.warning('the curriculum names an unknown exercise %r', practice.exercise_id)
            return None
        try:
            return coerce(definition, practice.settings)
        except SettingError:
            log.warning('bad curriculum settings for %r', practice.exercise_id, exc_info=True)
            return None

    def unit_items(self, unit: Unit) -> tuple[ItemId, ...]:
        """The knowledge items a unit practises, in teaching order (cached)."""
        cached = self._items.get(unit.id)
        if cached is not None:
            return cached
        items: list[ItemId] = []
        for practice in unit.practices:
            settings = self.practice_settings(practice)
            if settings is not None:
                items.extend(self.registry.items(practice.exercise_id, settings))
        items.extend(self._vocabulary_items(unit))
        result = tuple(dict.fromkeys(items))
        self._items[unit.id] = result
        return result

    def _vocabulary_items(self, unit: Unit) -> list[ItemId]:
        if VOCABULARY_EXERCISE not in self.registry.exercise_ids() or not unit.vocabulary_tags:
            return []
        entries = {e.id for e in self.library.vocabulary(unit)}
        if not entries:
            return []
        pool = self.registry.items(VOCABULARY_EXERCISE, {})
        return [i for i in pool if len(parts := i.split('.')) == 3 and parts[1] in entries]

    def settings_for(self, units: Iterable[Unit]) -> dict[str, dict[str, object]]:
        """Exercise settings for a session over ``units``: each exercise with the
        settings of the last of the units that practises it."""
        overlay: dict[str, dict[str, object]] = {}
        for unit in units:
            for practice in unit.practices:
                settings = self.practice_settings(practice)
                if settings is not None:
                    overlay[practice.exercise_id] = settings
        return overlay

    # Progress

    def status(self, record: PathRecord) -> tuple[LevelStatus, ...]:
        unlock = self.mastery.config.unlock_fraction
        units = {u.id: u for level in self.curriculum.levels for u in level.units}
        level_of = {u.id: level for level in self.curriculum.levels for u in level.units}
        previous_level = {
            later.id: earlier for earlier, later in itertools.pairwise(self.curriculum.levels)
        }
        details: dict[str, tuple[tuple[ItemId, ...], int]] = {}
        for unit_id, unit in units.items():
            items = self.unit_items(unit)
            details[unit_id] = (items, len(self.mastery.mastered(items)) if items else 0)

        def required(unit: Unit) -> list[Unit]:
            if unit.requires:
                return [units[r] for r in unit.requires]
            earlier = previous_level.get(level_of[unit.id].id)
            if earlier is not None and earlier.id not in record.passed_levels:
                return list(earlier.units)
            return []

        complete: dict[str, bool] = {}
        unlocked: dict[str, bool] = {}
        visiting: set[str] = set()

        def resolve(unit_id: str) -> None:
            if unit_id in complete:
                return
            if unit_id in visiting:  # a cycle in the curriculum: do not lock it forever
                complete[unit_id] = unlocked[unit_id] = True
                return
            visiting.add(unit_id)
            unit = units[unit_id]
            done = level_of[unit_id].id in record.passed_levels or unit_id in record.placed_units
            for other in required(unit):
                resolve(other.id)
            is_unlocked = done or all(complete[u.id] for u in required(unit))
            items, mastered = details[unit_id]
            # A unit without items has nothing to master: it is complete as soon as
            # it is open, so it neither blocks the path nor lets learners skip the
            # units before it.
            enough = mastered / len(items) >= unlock if items else is_unlocked
            complete[unit_id] = done or enough
            unlocked[unit_id] = is_unlocked
            visiting.discard(unit_id)

        def blockers(unit: Unit) -> list[Unit]:
            """Incomplete prerequisites, looking through units without items."""
            found: list[Unit] = []
            for other in required(unit):
                if complete[other.id]:
                    continue
                if details[other.id][0] or other.id in record.placed_units:
                    found.append(other)
                else:
                    found.extend(blockers(other))
            return list(dict.fromkeys(found))

        levels: list[LevelStatus] = []
        for level in self.curriculum.levels:
            statuses = []
            for unit in level.units:
                resolve(unit.id)
                items, mastered = details[unit.id]
                statuses.append(
                    UnitStatus(
                        unit,
                        items,
                        mastered,
                        unit.id in record.placed_units,
                        complete[unit.id],
                        unlocked[unit.id],
                        () if unlocked[unit.id] else tuple(blockers(unit)),
                    )
                )
            levels.append(LevelStatus(level, tuple(statuses), level.id in record.passed_levels))
        return tuple(levels)

    # Level exams and placement

    def exam_items(self, level: Level, rng: random.Random) -> tuple[ItemId, ...]:
        """``exam_size`` items spread evenly over the level's units, interleaved."""
        groups = [self.unit_items(u) for u in level.units]
        return tuple(balanced_sample(groups, level.exam_size, rng))

    def placement_plan(
        self, record: PathRecord, rng: random.Random, per_unit: int = PLACEMENT_SAMPLE
    ) -> PlacementPlan:
        """Samples for the placement walk over the units the learner has not
        completed through placement or an exam, in curriculum order.

        Each unit is asked about what it adds to the units before it (for
        example the altered notes of a unit that adds accidentals), so that
        the walk tests every unit on its own content.
        """
        seen: set[ItemId] = set()
        samples: list[tuple[str, tuple[ItemId, ...]]] = []
        followers: dict[str, list[str]] = {}
        for level in self.curriculum.levels:
            for unit in level.units:
                items = self.unit_items(unit)
                fresh = [i for i in items if i not in seen]
                seen.update(items)
                done = level.id in record.passed_levels or unit.id in record.placed_units
                if done or not items:
                    continue
                if not fresh:
                    if samples:
                        followers.setdefault(samples[-1][0], []).append(unit.id)
                    continue
                rng.shuffle(fresh)
                samples.append((unit.id, tuple(fresh[:per_unit])))
        return PlacementPlan(tuple(samples), {k: tuple(v) for k, v in followers.items()})


# Sessions --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExamResult:
    correct: int
    total: int
    passed: bool
    complete: bool
    """Every question was answered; an exam left early is never passed."""

    @property
    def needed(self) -> int:
        return needed(self.total)


class ExamRunner(SessionRunner):
    """A level exam: passed with 80 % of all its questions answered correctly."""

    def __init__(
        self,
        engine: LearningEngine,
        registry: ExerciseRegistry,
        request: SessionRequest,
        *,
        level: Level,
        on_passed: Callable[[str], None],
        **kwargs: Any,
    ) -> None:
        self.level = level
        self._on_passed = on_passed
        self.result: ExamResult | None = None
        # Translators: title of a level exam session, e.g. "Level 1 Exam".
        kwargs.setdefault('title', _('Level {number} Exam').format(number=level.number))
        self._kwargs = kwargs
        super().__init__(engine, registry, request, **kwargs)

    def finish(self) -> SessionSummary:
        summary = super().finish()
        complete = self.answered >= self.total
        passed = complete and passes(self.correct, self.total)
        self.result = ExamResult(self.correct, self.total, passed, complete)
        if passed:
            self._on_passed(self.level.id)
        return summary

    def again(self) -> ExamRunner:
        return ExamRunner(
            self.engine,
            self.registry,
            replace(self.request, now=self._clock()),
            level=self.level,
            on_passed=self._on_passed,
            **self._kwargs,
        )


@dataclass(frozen=True, slots=True)
class PlacementResult:
    placed: tuple[str, ...]
    """Units placed out, including followers."""
    failed: str | None
    """The unit where the walk stopped, if it stopped before the end."""


class PlacementRunner(SessionRunner):
    """The adaptive placement test: questions of decided units are skipped and
    the session ends at the first unit the learner does not know.

    ``on_placed(unit_id)`` is called as soon as a unit is placed out, so an
    interrupted test keeps what it found.
    """

    def __init__(
        self,
        engine: LearningEngine,
        registry: ExerciseRegistry,
        request: SessionRequest,
        *,
        plan: PlacementPlan,
        on_placed: Callable[[str], None],
        **kwargs: Any,
    ) -> None:
        self.plan = plan
        self.walk = PlacementWalk(plan.samples)
        self._on_placed = on_placed
        self._placed: list[str] = []
        self._kwargs = kwargs
        super().__init__(engine, registry, request, **kwargs)

    @property
    def result(self) -> PlacementResult:
        return PlacementResult(tuple(self._placed), self.walk.failed)

    def answer(self, given: object, *, response_ms: int, hinted: bool = False) -> Feedback:
        feedback = super().answer(given, response_ms=response_ms, hinted=hinted)
        self._judge(feedback.correct)
        return feedback

    def skip(self, *, response_ms: int) -> Feedback:
        feedback = super().skip(response_ms=response_ms)
        self._judge(False)
        return feedback

    def _judge(self, correct: bool) -> None:
        before = set(self.walk.placed)
        self.walk.record(ItemId(self.current.question.item_id), correct)
        for unit_id in self.walk.placed:
            if unit_id not in before:
                for placed in (unit_id, *self.plan.followers.get(unit_id, ())):
                    self._placed.append(placed)
                    self._on_placed(placed)
        self.drop_upcoming(lambda planned: not self.walk.wants(planned.item_id))

    def again(self) -> PlacementRunner:
        return PlacementRunner(
            self.engine,
            self.registry,
            replace(self.request, now=self._clock()),
            plan=self.plan,
            on_placed=self._on_placed,
            **self._kwargs,
        )


def merged_settings(
    learner: Callable[[str], Mapping[str, object]], overlay: Mapping[str, Mapping[str, object]]
) -> Callable[[str], dict[str, object]]:
    """A runner settings provider: the learner's settings with the unit's on top."""

    def settings_for(exercise_id: str) -> dict[str, object]:
        return {**learner(exercise_id), **overlay.get(exercise_id, {})}

    return settings_for
