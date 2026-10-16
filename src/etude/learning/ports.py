# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Interfaces the learning engine depends on.

``etude.storage`` implements the stores with SQLite and
``etude.exercises.registry`` implements :class:`ItemCatalog`, so the
learning engine depends on neither and is tested with in-memory fakes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Protocol

from .model import (
    Card,
    ItemId,
    Outcome,
    Rating,
    SessionMode,
    SessionRecord,
    SessionSummary,
)


class Scheduler(Protocol):
    def new_card(self, item_id: ItemId, now: datetime) -> Card: ...

    def review(self, card: Card, rating: Rating, now: datetime) -> Card: ...

    def retrievability(self, card: Card, now: datetime) -> float:
        """Probability in 0–1 that the learner recalls the item now."""


class CardStore(Protocol):
    def get(self, item_id: ItemId) -> Card | None: ...

    def put(self, card: Card) -> None: ...

    def due(self, now: datetime, *, limit: int, prefixes: Sequence[str] = ()) -> list[Card]:
        """Cards due at ``now``, most overdue first, optionally limited to item-id prefixes."""

    def get_many(self, item_ids: Iterable[ItemId]) -> dict[ItemId, Card]: ...


class AttemptLog(Protocol):
    def add(self, outcome: Outcome, session_id: int | None) -> None: ...

    def recent(
        self,
        *,
        exercise_id: str | None = None,
        item_id: ItemId | None = None,
        limit: int = 50,
    ) -> list[Outcome]:
        """Most recent outcomes first."""

    def between(self, start: datetime, end: datetime) -> list[Outcome]: ...


class SessionLog(Protocol):
    def start(self, mode: SessionMode, exercise_id: str | None, now: datetime) -> int: ...

    def finish(self, session_id: int, now: datetime, summary: SessionSummary) -> None: ...

    def between(self, start: datetime, end: datetime) -> list[SessionRecord]:
        """Sessions started in ``[start, end)``, oldest first."""


class ItemCatalog(Protocol):
    def exercise_ids(self) -> Sequence[str]: ...

    def items(self, exercise_id: str, settings: Mapping[str, object]) -> Sequence[ItemId]:
        """Items an exercise covers under ``settings``, in teaching order:
        earlier items are introduced first."""

    def exercise_for(self, item_id: ItemId) -> str:
        """The exercise that owns an item (items are never shared)."""
