# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""A simulated learner practising every evening for 60 days.

The learner recalls an item with a probability that follows the
scheduler's own retrievability (with a guessing floor and occasional
slips), and gets a brand-new item right 60 % of the time. Run this file
with ``-s`` to print the numbers.
"""

from __future__ import annotations

import itertools
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from functools import cache
from zoneinfo import ZoneInfo

import pytest
from tests.learning.fakes import (
    FakeAttemptLog,
    FakeCardStore,
    FakeCatalog,
    FakeClock,
    FakeSessionLog,
)

from etude.learning.engine import LearningEngine
from etude.learning.model import CardState, ItemId, Outcome, SessionMode, SessionRequest
from etude.learning.scheduler import FsrsScheduler
from etude.learning.session import SessionConfig

TZ = ZoneInfo('Europe/Helsinki')
DAYS = 60
EXERCISES = {name: [f'{name}.{n:02}' for n in range(40)] for name in ('keys', 'notes', 'ivl')}
CONFIG = SessionConfig(tzinfo=TZ)


@dataclass
class Simulation:
    reviews: dict[ItemId, list[datetime]] = field(default_factory=lambda: defaultdict(list))
    new_by_day: dict[date, int] = field(default_factory=lambda: defaultdict(int))
    answers_by_day: dict[date, list[bool]] = field(default_factory=lambda: defaultdict(list))
    gated: list[tuple[float | None, int]] = field(default_factory=list)
    """(rolling accuracy before a session, new items it planned) for every session."""
    cards: FakeCardStore = field(default_factory=FakeCardStore)

    @property
    def accuracy(self) -> float:
        answers = [a for day in self.answers_by_day.values() for a in day]
        return sum(answers) / len(answers)

    def gaps(self, item: ItemId) -> list[float]:
        """Days between successive reviews on different days."""
        days = sorted({t.astimezone(TZ).date() for t in self.reviews[item]})
        return [float((b - a).days) for a, b in itertools.pairwise(days)]


@cache
def simulate(skill: float, seed: int = 2026) -> Simulation:
    """``skill`` scales recall: 1.0 follows the model, lower forgets more."""
    rng = random.Random(seed)
    sim = Simulation()
    attempts, sessions = FakeAttemptLog(), FakeSessionLog()
    clock = FakeClock()
    scheduler = FsrsScheduler(rng=random.Random(seed))
    engine = LearningEngine.create(
        FakeCatalog(EXERCISES),
        sim.cards,
        attempts,
        sessions,
        tzinfo=TZ,
        scheduler=scheduler,
        rng=random.Random(seed),
        session_config=CONFIG,
        clock=clock,
    )
    start = date(2026, 9, 1)
    for offset in range(DAYS):
        day = start + timedelta(days=offset)
        clock.now = datetime.combine(day, time(18), tzinfo=TZ).astimezone(clock.now.tzinfo)
        # Up to three sessions an evening, as long as something is due.
        for _ in range(3):
            accuracy = engine._builder.recent_accuracy(None)
            plan = engine.start_session(
                SessionRequest(SessionMode.DAILY_REVIEW, now=clock.now, size=20)
            )
            sim.gated.append((accuracy, sum(q.is_new for q in plan)))
            for planned in plan:
                card = sim.cards.get(planned.item_id)
                if card is None:
                    p = 0.6
                else:
                    recall = scheduler.retrievability(card, clock.now)
                    if card.state is not CardState.REVIEW:
                        recall = max(recall, 0.8)  # seen minutes ago
                    p = 0.25 + 0.72 * recall * skill
                correct = rng.random() < p
                now = clock.advance(timedelta(seconds=rng.randint(3, 9)))
                engine.record(
                    Outcome(
                        item_id=planned.item_id,
                        exercise_id=planned.exercise_id,
                        correct=correct,
                        response_ms=rng.randint(1500, 7000),
                        answered_at=now,
                    )
                )
                sim.reviews[planned.item_id].append(now)
                sim.answers_by_day[day].append(correct)
                sim.new_by_day[day] += planned.is_new
            engine.finish_session()
            clock.advance(timedelta(minutes=30))
            if not plan:
                break
    return sim


def describe(sim: Simulation) -> str:
    introduced = sum(sim.new_by_day.values())
    early = [i for i in sim.reviews if len(sim.gaps(i)) >= 4]
    first = statistics.median(sim.gaps(i)[0] for i in early)
    fourth = statistics.median(sim.gaps(i)[3] for i in early)
    per_day = [len(a) for a in sim.answers_by_day.values()]
    return (
        f'accuracy {sim.accuracy:.1%}, items introduced {introduced}, '
        f'answers/day median {statistics.median(per_day)} max {max(per_day)}, '
        f'median gap 1st {first} d → 4th {fourth} d, '
        f'longest gap {max(max(sim.gaps(i), default=0) for i in sim.reviews)} d'
    )


def test_scheduler_spaces_reviews_out() -> None:
    sim = simulate(1.0)
    print('\nlearner:', describe(sim))
    never_lapsed = [
        i for i in sim.reviews if len(sim.gaps(i)) >= 2 and sim.cards.cards[i].lapses == 0
    ]
    assert len(never_lapsed) >= 30
    growing = [i for i in never_lapsed if sim.gaps(i)[-1] > sim.gaps(i)[0]]
    assert len(growing) / len(never_lapsed) >= 0.9
    assert statistics.median(sim.gaps(i)[-1] for i in never_lapsed) >= 10
    assert max(max(sim.gaps(i)) for i in sim.reviews) >= 21


def test_new_items_only_while_accuracy_is_at_the_target() -> None:
    sim = simulate(1.0)
    for accuracy, new in sim.gated:
        if new:
            assert accuracy is None or accuracy >= CONFIG.target_accuracy
    assert all(count <= CONFIG.daily_new_limit for count in sim.new_by_day.values())
    # Accuracy stays near the 85 % target instead of drifting far either way.
    assert 0.8 <= sim.accuracy <= 0.95


def introduced_by(sim: Simulation, days: int) -> int:
    return sum(n for day, n in sim.new_by_day.items() if (day - date(2026, 9, 1)).days < days)


def test_a_struggling_learner_gets_new_items_more_slowly() -> None:
    strong, weak = simulate(1.0), simulate(0.85)
    print('\nstruggling learner:', describe(weak))
    print(f'introduced in 20 days: {introduced_by(strong, 20)} vs {introduced_by(weak, 20)}')
    assert weak.accuracy < strong.accuracy
    assert introduced_by(weak, 20) < 0.75 * introduced_by(strong, 20)


def test_workload_stays_bounded() -> None:
    sim = simulate(1.0)
    assert max(len(a) for a in sim.answers_by_day.values()) <= 60
    reviewed = [c for c in sim.cards.cards.values() if c.state is CardState.REVIEW]
    assert len(reviewed) >= 0.8 * len(sim.cards.cards)


@pytest.mark.parametrize('seed', [1, 2, 3])
def test_simulation_is_deterministic(seed: int) -> None:
    simulate.cache_clear()
    a = describe(simulate(1.0, seed))
    simulate.cache_clear()
    assert describe(simulate(1.0, seed)) == a
