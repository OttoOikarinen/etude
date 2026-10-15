# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import UTC, datetime

import pytest

from etude.learning.model import ItemId, Outcome, Rating
from etude.learning.rating import derive_rating


def outcome(
    *, correct: bool = True, ms: int = 2000, hinted: bool = False, score: float | None = None
) -> Outcome:
    return Outcome(
        item_id=ItemId('interval.ear.melodic.asc.m6'),
        exercise_id='intervals-ear',
        correct=correct,
        response_ms=ms,
        answered_at=datetime(2026, 10, 15, tzinfo=UTC),
        hinted=hinted,
        score=score,
    )


@pytest.mark.parametrize(
    ('answer', 'rating'),
    [
        (outcome(correct=False), Rating.AGAIN),
        (outcome(correct=False, ms=100), Rating.AGAIN),
        (outcome(hinted=True), Rating.HARD),
        (outcome(ms=9000), Rating.HARD),
        (outcome(ms=500), Rating.EASY),
        (outcome(ms=500, hinted=True), Rating.HARD),
        (outcome(), Rating.GOOD),
        (outcome(score=0.5), Rating.AGAIN),
        (outcome(score=0.9), Rating.HARD),
        (outcome(score=1.0, ms=500), Rating.EASY),
    ],
)
def test_derive_rating(answer: Outcome, rating: Rating) -> None:
    assert derive_rating(answer, fast_ms=1000, slow_ms=5000) is rating
