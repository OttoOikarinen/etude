# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Plan which items a session asks about, and in which order.

The builder puts the principles of ``docs/PEDAGOGY.md`` into practice:

* **Spaced repetition:** due items are chosen first, the most overdue ones
  when more are due than fit in the session.
* **Desirable difficulty:** new items are introduced only while the
  learner's rolling accuracy is at or above :attr:`SessionConfig.target_accuracy`
  (85 %, Wilson et al. 2019), and never more than a daily cap.
* **Interleaving:** consecutive questions come from different exercises
  where possible, the same item never appears twice in a row, and
  confusable items are placed next to each other so the learner has to
  discriminate between them.

The chosen questions are shuffled before they are interleaved, except that
new items keep their teaching order.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, tzinfo

from .model import Card, ItemId, PlannedQuestion, SessionMode, SessionRequest
from .ports import AttemptLog, CardStore, ItemCatalog, Scheduler
from .stats import weakest_items

Confusables = Callable[[ItemId], Sequence[ItemId]]
"""Items easily mistaken for the given one, e.g. ``m6`` for ``M6``."""


@dataclass(frozen=True, slots=True)
class SessionConfig:
    target_accuracy: float = 0.85
    """New items are added only while recent accuracy is at least this (the 85 % rule)."""
    accuracy_window: int = 20
    """Number of most recent answers the rolling accuracy is computed over."""
    accuracy_min_answers: int = 5
    """With fewer recent answers than this the learner is just starting: new items are allowed."""
    daily_new_limit: int = 10
    """New items introduced per local day across all exercises, so reviews stay manageable."""
    session_new_limit: int = 5
    """New items in one session: a few at a time are easier to tell apart."""
    weak_history: int = 500
    """Recent answers searched for weak items when ``DRILL_WEAK`` gets no explicit items."""
    weak_min_attempts: int = 3
    tzinfo: tzinfo = UTC
    """The learner's time zone, for what "today" means in :attr:`daily_new_limit`."""


@dataclass(frozen=True, slots=True)
class NewItems:
    """What daily reviews may still introduce today (the Today page)."""

    available: int
    """New items the learner can still meet today across daily reviews."""
    left_today: int
    """What remains of :attr:`SessionConfig.daily_new_limit` today."""
    held_back: bool
    """Recent accuracy is below :attr:`SessionConfig.target_accuracy`, so no new items for now."""


class SessionBuilder:
    """Builds the list of questions for a :class:`SessionRequest`."""

    def __init__(
        self,
        catalog: ItemCatalog,
        cards: CardStore,
        attempts: AttemptLog,
        scheduler: Scheduler,
        rng: random.Random,
        config: SessionConfig | None = None,
        *,
        confusables: Confusables | None = None,
    ) -> None:
        self._catalog = catalog
        self._cards = cards
        self._attempts = attempts
        self._scheduler = scheduler
        self._rng = rng
        self.config = config if config is not None else SessionConfig()
        self._confusables = confusables

    def build(self, request: SessionRequest) -> list[PlannedQuestion]:
        """Questions for ``request``; at most ``request.size`` except for ``REVIEW_MISTAKES``."""
        match request.mode:
            case SessionMode.DAILY_REVIEW:
                questions = self._daily_review(request)
            case SessionMode.EXERCISE:
                questions = self._exercise(request)
            case SessionMode.DRILL_WEAK:
                questions = self._drill_weak(request)
            case SessionMode.REVIEW_MISTAKES:
                questions = self._planned(request.item_ids)
            case SessionMode.PLACEMENT | SessionMode.LEVEL_EXAM:
                # Placement tests and level exams need the curriculum (W3).
                raise NotImplementedError(f'{request.mode.value} sessions are planned for W3')
        teaching = request.mode in {SessionMode.DAILY_REVIEW, SessionMode.EXERCISE}
        introduced = [q for q in questions if q.is_new] if teaching else []
        # Shuffle for variety, but introduce new items in teaching order.
        self._rng.shuffle(questions)
        return self.arrange(_new_in_order(questions, introduced))

    # Modes

    def _daily_review(self, request: SessionRequest) -> list[PlannedQuestion]:
        questions: list[PlannedQuestion] = []
        for card in self._cards.due(request.now, limit=request.size):
            exercise = self._exercise_for(card.item_id)
            if exercise is not None:
                questions.append(PlannedQuestion(exercise, card.item_id))
        slots = request.size - len(questions)
        if slots <= 0:
            return questions
        budget = min(slots, self._new_budget(request.now, exercise_id=None))
        return questions + self._round_robin_new(self._daily_candidates(), budget)

    def _daily_candidates(self) -> list[tuple[str, list[ItemId]]]:
        """Unseen items, in teaching order, of the exercises daily reviews draw new items from.

        New items come from exercises the learner has begun; a brand-new
        learner gets items from every exercise so the first session is not empty.
        """
        unseen: dict[str, list[ItemId]] = {}
        started: list[str] = []
        for exercise in self._catalog.exercise_ids():
            items = self._catalog.items(exercise, {})
            known = self._cards.get_many(items)
            unseen[exercise] = [item for item in items if item not in known]
            if known:
                started.append(exercise)
        return [(e, unseen[e]) for e in (started or self._catalog.exercise_ids())]

    def new_items_today(self, now: datetime) -> NewItems:
        """How many new items daily reviews may still introduce today, and why not more."""
        accuracy = self.recent_accuracy(None)
        held_back = accuracy is not None and accuracy < self.config.target_accuracy
        left = max(0, self.config.daily_new_limit - self.new_today(now))
        unseen = sum(len(items) for _exercise, items in self._daily_candidates())
        return NewItems(
            available=0 if held_back else min(left, unseen), left_today=left, held_back=held_back
        )

    def _exercise(self, request: SessionRequest) -> list[PlannedQuestion]:
        exercise = _required_exercise(request)
        items = list(self._catalog.items(exercise, request.settings))
        known = self._cards.get_many(items)
        due = due_first(known, request.now)[: request.size]
        questions = [PlannedQuestion(exercise, c.item_id) for c in due]
        budget = min(
            request.size - len(questions), self._new_budget(request.now, exercise_id=exercise)
        )
        unseen = [item for item in items if item not in known]
        questions += self._round_robin_new([(exercise, unseen)], budget)
        # Nothing (more) due: practise the items most likely to be forgotten next,
        # so a learner can always practise an exercise.
        chosen = {q.item_id for q in questions}
        rest = sorted(
            (c for c in known.values() if c.item_id not in chosen),
            key=lambda c: (self._scheduler.retrievability(c, request.now), c.item_id),
        )
        questions += [PlannedQuestion(exercise, c.item_id) for c in rest]
        return _cycle(questions, request.size)

    def _drill_weak(self, request: SessionRequest) -> list[PlannedQuestion]:
        if request.item_ids:
            return self._planned(request.item_ids[: request.size])
        outcomes = self._attempts.recent(
            exercise_id=request.exercise_id, limit=self.config.weak_history
        )
        cards = self._cards.get_many({o.item_id for o in outcomes})
        weak = weakest_items(
            outcomes,
            limit=request.size,
            min_attempts=self.config.weak_min_attempts,
            cards=cards,
        )
        return self._planned(tuple(s.item_id for s in weak))

    # Helpers

    def _planned(self, item_ids: Sequence[ItemId]) -> list[PlannedQuestion]:
        known = self._cards.get_many(item_ids)
        questions = []
        for item in item_ids:
            exercise = self._exercise_for(item)
            if exercise is not None:
                questions.append(PlannedQuestion(exercise, item, is_new=item not in known))
        return questions

    def _exercise_for(self, item_id: ItemId) -> str | None:
        """The owning exercise, or ``None`` for items whose exercise no longer exists."""
        try:
            return self._catalog.exercise_for(item_id)
        except KeyError:
            return None

    def recent_accuracy(self, exercise_id: str | None) -> float | None:
        """Rolling accuracy, or ``None`` while there are too few answers to judge."""
        recent = self._attempts.recent(exercise_id=exercise_id, limit=self.config.accuracy_window)
        if len(recent) < self.config.accuracy_min_answers:
            return None
        return sum(o.correct for o in recent) / len(recent)

    def new_today(self, now: datetime) -> int:
        """Items whose first ever answer was given today (local time).

        An item is new today when all of its card's reviews happened today.
        """
        local = now.astimezone(self.config.tzinfo)
        start = datetime.combine(local.date(), time(), tzinfo=self.config.tzinfo)
        today = Counter(o.item_id for o in self._attempts.between(start, now + _EPSILON))
        cards = self._cards.get_many(today)
        return sum(
            1 for item, count in today.items() if item in cards and cards[item].reps <= count
        )

    def _new_budget(self, now: datetime, *, exercise_id: str | None) -> int:
        accuracy = self.recent_accuracy(exercise_id)
        if accuracy is not None and accuracy < self.config.target_accuracy:
            return 0
        left_today = self.config.daily_new_limit - self.new_today(now)
        return max(0, min(self.config.session_new_limit, left_today))

    @staticmethod
    def _round_robin_new(
        candidates: Iterable[tuple[str, Sequence[ItemId]]], budget: int
    ) -> list[PlannedQuestion]:
        """Take unseen items in teaching order, one exercise after another."""
        queues = [(exercise, list(items)) for exercise, items in candidates if items]
        chosen: list[PlannedQuestion] = []
        while queues and len(chosen) < budget:
            for entry in list(queues):
                if len(chosen) == budget:
                    break
                exercise, queue = entry
                chosen.append(PlannedQuestion(exercise, queue.pop(0), is_new=True))
                if not queue:
                    queues.remove(entry)
        return chosen

    def arrange(self, questions: Sequence[PlannedQuestion]) -> list[PlannedQuestion]:
        """Interleave exercises, place confusables together, and separate repeated items."""
        ordered = interleave(questions)
        if self._confusables is not None:
            ordered = place_confusables(ordered, self._confusables)
        return separate_repeats(ordered)


_EPSILON = timedelta(microseconds=1)


def _required_exercise(request: SessionRequest) -> str:
    if request.exercise_id is None:
        raise ValueError(f'{request.mode.value} sessions need an exercise_id')
    return request.exercise_id


def _new_in_order(
    questions: list[PlannedQuestion], introduced: Sequence[PlannedQuestion]
) -> list[PlannedQuestion]:
    """``questions`` with its new items put back in their original (teaching) order."""
    if not introduced:
        return questions
    order = iter(introduced)
    return [next(order) if q.is_new else q for q in questions]


def _cycle(questions: list[PlannedQuestion], size: int) -> list[PlannedQuestion]:
    """``questions`` cut or repeated to ``size``; repeats are marked as no longer new."""
    if not questions:
        return []
    result = questions[:size]
    index = 0
    while len(result) < size:
        q = questions[index % len(questions)]
        result.append(PlannedQuestion(q.exercise_id, q.item_id))
        index += 1
    return result


def interleave(questions: Sequence[PlannedQuestion]) -> list[PlannedQuestion]:
    """Greedy interleaving that keeps the relative order within each exercise.

    Each step avoids repeating the previous item (hard preference) and the
    previous exercise (soft preference), and otherwise takes from whichever
    item and exercise have the most questions left, so that no exercise is
    left to clump together at the end.
    """
    remaining = list(questions)
    result: list[PlannedQuestion] = []
    while remaining:
        exercises = Counter(q.exercise_id for q in remaining)
        items = Counter(q.item_id for q in remaining)
        last = result[-1] if result else None
        _, index = min(
            (
                (
                    last is not None and q.item_id == last.item_id,
                    last is not None and q.exercise_id == last.exercise_id,
                    -items[q.item_id],
                    -exercises[q.exercise_id],
                ),
                index,
            )
            for index, q in enumerate(remaining)
        )
        result.append(remaining.pop(index))
    return result


def place_confusables(
    questions: Sequence[PlannedQuestion], confusables: Confusables
) -> list[PlannedQuestion]:
    """Move each item's first confusable partner in the plan right next to it.

    Contrasting two similar items back to back trains discrimination
    (Carvalho & Goldstone, 2014); this takes precedence over alternating
    exercises. Each question is paired at most once.
    """
    result = list(questions)
    paired: set[int] = set()
    for i in range(len(result)):
        if i in paired:
            continue
        item = result[i].item_id
        partners = set(confusables(item)) - {item}
        if not partners:
            continue
        neighbours = [j for j in (i - 1, i + 1) if 0 <= j < len(result) and j not in paired]
        adjacent = [j for j in neighbours if result[j].item_id in partners]
        if adjacent:
            paired.update((i, adjacent[0]))
            continue
        for j in range(i + 2, len(result)):
            if result[j].item_id in partners:
                result.insert(i + 1, result.pop(j))
                # Positions between i + 1 and j shifted right by one.
                paired = {p + 1 if i + 1 <= p < j else p for p in paired}
                paired.update((i, i + 1))
                break
    return result


def separate_repeats(questions: Sequence[PlannedQuestion]) -> list[PlannedQuestion]:
    """Swap questions so that no item is asked twice in a row, where that is possible."""
    result = list(questions)

    def fits(position: int, item: ItemId, ignore: int) -> bool:
        return all(
            result[n].item_id != item
            for n in (position - 1, position + 1)
            if 0 <= n < len(result) and n != ignore
        )

    for i in range(1, len(result)):
        if result[i].item_id != result[i - 1].item_id:
            continue
        for j in [*range(i + 1, len(result)), *range(i - 2, -1, -1)]:
            if fits(i, result[j].item_id, j) and fits(j, result[i].item_id, i):
                result[i], result[j] = result[j], result[i]
                break
    return result


def due_first(cards: Mapping[ItemId, Card], now: datetime) -> list[Card]:
    """Due cards, most overdue first."""
    return sorted((c for c in cards.values() if c.due <= now), key=lambda c: (c.due, c.item_id))
