# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mastery of items and of units (mastery learning, Bloom 1984).

An item is mastered when memory of it is *durable* and *accurate*:

* its FSRS card is in the REVIEW state with a stability of at least
  :attr:`MasteryConfig.stability_days`, i.e. the learner is predicted to
  still recall it with 90 % probability three weeks after the last review;
* and its recent answers are at least :attr:`MasteryConfig.item_accuracy`
  correct, so lucky guesses on multiple choice do not count.

A unit (or any collection of items) is mastered, and unlocks what builds
on it, when :attr:`MasteryConfig.unlock_fraction` of its items are
mastered: requiring every single item would hold learners back on one
stubborn item, which remains in their reviews anyway.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .model import Card, CardState, ItemId
from .ports import AttemptLog, CardStore


@dataclass(frozen=True, slots=True)
class MasteryConfig:
    stability_days: float = 21.0
    """Three weeks: well past the first few expanding intervals, which consolidate an item."""
    item_accuracy: float = 0.9
    """Above the 85 % training target, so mastery means more than "being trained"."""
    accuracy_window: int = 10
    """Most recent answers an item's accuracy is computed over."""
    min_answers: int = 3
    """Fewer answers than this are not evidence of mastery."""
    unlock_fraction: float = 0.8
    """Share of a unit's items that must be mastered before the next unit unlocks."""


class Mastery:
    def __init__(
        self, cards: CardStore, attempts: AttemptLog, config: MasteryConfig | None = None
    ) -> None:
        self._cards = cards
        self._attempts = attempts
        self.config = config if config is not None else MasteryConfig()

    def is_durable(self, card: Card | None) -> bool:
        return (
            card is not None
            and card.state is CardState.REVIEW
            and card.stability is not None
            and card.stability >= self.config.stability_days
        )

    def is_accurate(self, item_id: ItemId) -> bool:
        recent = self._attempts.recent(item_id=item_id, limit=self.config.accuracy_window)
        if len(recent) < self.config.min_answers:
            return False
        return sum(o.correct for o in recent) / len(recent) >= self.config.item_accuracy

    def is_mastered(self, item_id: ItemId) -> bool:
        return self.is_durable(self._cards.get(item_id)) and self.is_accurate(item_id)

    def mastered(self, item_ids: Iterable[ItemId]) -> set[ItemId]:
        items = list(dict.fromkeys(item_ids))
        cards = self._cards.get_many(items)
        return {i for i in items if self.is_durable(cards.get(i)) and self.is_accurate(i)}

    def fraction(self, item_ids: Iterable[ItemId]) -> float:
        """Share of mastered items; an empty collection counts as fully mastered.

        Treating an empty unit as mastered keeps a unit without items (for
        example a lesson-only unit) from blocking everything after it.
        """
        items = list(dict.fromkeys(item_ids))
        if not items:
            return 1.0
        return len(self.mastered(items)) / len(items)

    def is_unlocked_by(self, prerequisite_items: Iterable[ItemId]) -> bool:
        """Whether a unit whose prerequisites are ``prerequisite_items`` is open."""
        return self.fraction(prerequisite_items) >= self.config.unlock_fraction
