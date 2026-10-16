# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""FSRS scheduling on top of the ``fsrs`` library.

:class:`FsrsScheduler` converts between Etude's immutable :class:`Card` and
``fsrs.Card`` and adds the two counters FSRS itself does not keep (``reps``
and ``lapses``). Interval fuzzing is applied here with an injected
:class:`random.Random` instead of inside ``fsrs`` (which uses the global
random generator), so tests can make it deterministic or switch it off.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import fsrs
from fsrs.scheduler import DEFAULT_PARAMETERS

from .model import Card, CardState, ItemId, Rating

DEFAULT_DESIRED_RETENTION = 0.9
"""FSRS's recommended target: reviews are scheduled when recall has dropped to 90 %."""

_FUZZ_RANGES: tuple[tuple[float, float, float], ...] = (
    # (start, end, factor) in days, as in FSRS: longer intervals get more fuzz.
    (2.5, 7.0, 0.15),
    (7.0, 20.0, 0.1),
    (20.0, float('inf'), 0.05),
)


def as_utc(moment: datetime) -> datetime:
    """``moment`` in UTC; naive datetimes are rejected because their meaning is ambiguous."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f'datetime {moment!r} is not timezone-aware')
    return moment.astimezone(UTC)


class FsrsScheduler:
    """Implements :class:`etude.learning.ports.Scheduler` with FSRS-6.

    ``fuzz`` spreads out review intervals of 3 days or more by a few days so
    that items learned together do not stay due together forever. Pass
    ``fuzz=False`` (or a seeded ``rng``) for deterministic tests.
    """

    def __init__(
        self,
        *,
        desired_retention: float = DEFAULT_DESIRED_RETENTION,
        fuzz: bool = True,
        rng: random.Random | None = None,
        parameters: Sequence[float] | None = None,
        learning_steps: Sequence[timedelta] = (timedelta(minutes=1), timedelta(minutes=10)),
        relearning_steps: Sequence[timedelta] = (timedelta(minutes=10),),
        maximum_interval_days: int = 36500,
    ) -> None:
        if not 0.0 < desired_retention < 1.0:
            raise ValueError(f'desired retention {desired_retention} is outside (0, 1)')
        self._fsrs = fsrs.Scheduler(
            parameters=DEFAULT_PARAMETERS if parameters is None else parameters,
            desired_retention=desired_retention,
            learning_steps=tuple(learning_steps),
            relearning_steps=tuple(relearning_steps),
            maximum_interval=maximum_interval_days,
            enable_fuzzing=False,
        )
        self._fuzz = fuzz
        self._rng = rng if rng is not None else random.Random()

    @property
    def desired_retention(self) -> float:
        return self._fsrs.desired_retention

    def new_card(self, item_id: ItemId, now: datetime) -> Card:
        return Card(item_id=item_id, due=as_utc(now))

    def review(self, card: Card, rating: Rating, now: datetime) -> Card:
        now = as_utc(now)
        reviewed, _log = self._fsrs.review_card(
            _to_fsrs(card), fsrs.Rating(int(rating)), review_datetime=now
        )
        due = reviewed.due
        if self._fuzz and reviewed.state == fsrs.State.Review:
            due = now + self._fuzzed(due - now)
        lapsed = rating is Rating.AGAIN and card.state is CardState.REVIEW
        return replace(
            card,
            due=due,
            state=CardState(int(reviewed.state)),
            step=reviewed.step,
            stability=reviewed.stability,
            difficulty=reviewed.difficulty,
            last_review=reviewed.last_review,
            reps=card.reps + 1,
            lapses=card.lapses + int(lapsed),
        )

    def retrievability(self, card: Card, now: datetime) -> float:
        return float(self._fsrs.get_card_retrievability(_to_fsrs(card), as_utc(now)))

    def _fuzzed(self, interval: timedelta) -> timedelta:
        days = interval.days
        if days < 2.5:
            return interval
        delta = 1.0
        for start, end, factor in _FUZZ_RANGES:
            delta += factor * max(min(float(days), end) - start, 0.0)
        maximum = self._fsrs.maximum_interval
        high = min(round(days + delta), maximum)
        low = min(max(2, round(days - delta)), high)
        fuzzed = min(round(self._rng.random() * (high - low + 1) + low), maximum)
        return timedelta(days=fuzzed)


def _to_fsrs(card: Card) -> fsrs.Card:
    return fsrs.Card(
        # A fixed id: fsrs otherwise derives one from the clock and sleeps 1 ms per card.
        card_id=0,
        state=fsrs.State(int(card.state)),
        step=card.step,
        stability=card.stability,
        difficulty=card.difficulty,
        due=as_utc(card.due),
        last_review=None if card.last_review is None else as_utc(card.last_review),
    )
