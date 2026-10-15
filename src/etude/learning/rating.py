# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Turn an answer into an FSRS rating without asking the learner.

Speed thresholds are per exercise, because naming a note and taking a
harmonic dictation take very different amounts of time; callers pass the
learner's own percentiles (see :mod:`etude.learning.stats`).
"""

from __future__ import annotations

from .model import Outcome, Rating

PARTIAL_CREDIT_PASS = 0.8
"""Minimum ``score`` for a partially correct answer to count as recalled."""


def derive_rating(outcome: Outcome, *, fast_ms: float, slow_ms: float) -> Rating:
    """Wrong → AGAIN; hinted, slow or barely passing → HARD; fast → EASY; otherwise GOOD."""
    if outcome.score is not None:
        if outcome.score < PARTIAL_CREDIT_PASS:
            return Rating.AGAIN
        if outcome.score < 1.0:
            return Rating.HARD
    elif not outcome.correct:
        return Rating.AGAIN
    if outcome.hinted or outcome.response_ms > slow_ms:
        return Rating.HARD
    if outcome.response_ms < fast_ms:
        return Rating.EASY
    return Rating.GOOD
