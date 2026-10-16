# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""In-memory implementations of the :mod:`etude.learning.ports` protocols.

They behave like the SQLite stores (``tests/storage/test_repositories.py``
runs the same contract tests against both), so any test can use them::

    from tests.learning.fakes import FakeAttemptLog, FakeCardStore, FakeCatalog
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

from etude.learning.model import (
    Card,
    ItemId,
    Outcome,
    SessionMode,
    SessionRecord,
    SessionSummary,
)


def utc(*args: int) -> datetime:
    """``utc(2026, 10, 15, 9)`` is a timezone-aware UTC datetime."""
    return datetime(*args, tzinfo=UTC)  # type: ignore[misc]


@dataclass
class FakeClock:
    """A clock that only moves when told to."""

    now: datetime = field(default_factory=lambda: utc(2026, 10, 15, 9))

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta = timedelta(seconds=5)) -> datetime:
        self.now += delta
        return self.now


class FakeCatalog:
    """Exercises with fixed item lists, in teaching order.

    ``settings`` may contain ``'only'``, a collection of items to restrict
    the pool to, standing in for real exercise settings.
    """

    def __init__(self, exercises: Mapping[str, Sequence[str]]) -> None:
        self._exercises = {e: [ItemId(i) for i in items] for e, items in exercises.items()}
        self._owner = {i: e for e, items in self._exercises.items() for i in items}

    def exercise_ids(self) -> Sequence[str]:
        return list(self._exercises)

    def items(self, exercise_id: str, settings: Mapping[str, object]) -> Sequence[ItemId]:
        items = self._exercises[exercise_id]
        only = settings.get('only')
        if isinstance(only, Iterable):
            allowed = set(only)
            items = [i for i in items if i in allowed]
        return list(items)

    def exercise_for(self, item_id: ItemId) -> str:
        return self._owner[item_id]


class FakeCardStore:
    def __init__(self, cards: Iterable[Card] = ()) -> None:
        self.cards: dict[ItemId, Card] = {c.item_id: c for c in cards}

    def get(self, item_id: ItemId) -> Card | None:
        return self.cards.get(item_id)

    def put(self, card: Card) -> None:
        self.cards[card.item_id] = card

    def due(self, now: datetime, *, limit: int, prefixes: Sequence[str] = ()) -> list[Card]:
        due = [
            c
            for c in self.cards.values()
            if c.due <= now and (not prefixes or any(c.item_id.startswith(p) for p in prefixes))
        ]
        return sorted(due, key=lambda c: (c.due, c.item_id))[:limit]

    def get_many(self, item_ids: Iterable[ItemId]) -> dict[ItemId, Card]:
        return {i: self.cards[i] for i in item_ids if i in self.cards}


class FakeAttemptLog:
    def __init__(self, outcomes: Iterable[Outcome] = ()) -> None:
        self.entries: list[tuple[Outcome, int | None]] = [(o, None) for o in outcomes]

    def add(self, outcome: Outcome, session_id: int | None) -> None:
        self.entries.append((outcome, session_id))

    def _ordered(self) -> list[Outcome]:
        # Stable sort: equal times keep insertion order, like ORDER BY answered_at, id.
        return sorted((o for o, _ in self.entries), key=lambda o: o.answered_at)

    def recent(
        self,
        *,
        exercise_id: str | None = None,
        item_id: ItemId | None = None,
        limit: int = 50,
    ) -> list[Outcome]:
        matching = [
            o
            for o in self._ordered()
            if (exercise_id is None or o.exercise_id == exercise_id)
            and (item_id is None or o.item_id == item_id)
        ]
        return list(reversed(matching))[:limit]

    def between(self, start: datetime, end: datetime) -> list[Outcome]:
        return [o for o in self._ordered() if start <= o.answered_at < end]


class FakeSessionLog:
    def __init__(self) -> None:
        self.records: dict[int, SessionRecord] = {}

    def start(self, mode: SessionMode, exercise_id: str | None, now: datetime) -> int:
        session_id = len(self.records) + 1
        self.records[session_id] = SessionRecord(session_id, mode, exercise_id, now)
        return session_id

    def finish(self, session_id: int, now: datetime, summary: SessionSummary) -> None:
        self.records[session_id] = replace(
            self.records[session_id], finished_at=now, summary=summary
        )

    def between(self, start: datetime, end: datetime) -> list[SessionRecord]:
        return sorted(
            (r for r in self.records.values() if start <= r.started_at < end),
            key=lambda r: (r.started_at, r.id),
        )


def outcome(
    item: str,
    at: datetime,
    *,
    correct: bool = True,
    exercise: str = 'ex',
    ms: int = 3000,
    hinted: bool = False,
) -> Outcome:
    return Outcome(
        item_id=ItemId(item),
        exercise_id=exercise,
        correct=correct,
        response_ms=ms,
        answered_at=at,
        hinted=hinted,
    )
