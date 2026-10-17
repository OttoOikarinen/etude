# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Level exams and the placement test, independent of the curriculum.

Both follow mastery learning (Bloom, 1984, docs/PEDAGOGY.md): a learner
moves on once they show mastery, which here means answering at least
:data:`PASS_FRACTION` (80 %) of the questions correctly. Mastery-learning
programmes commonly set the criterion at 80–90 %; 80 % matches the share of
a unit's items that must be mastered before the next unit unlocks
(:attr:`etude.learning.mastery.MasteryConfig.unlock_fraction`).

* A **level exam** samples questions evenly from the units of a level
  (:func:`balanced_sample`); the level is passed with :func:`passes`.
* The **placement test** walks the units in curriculum order
  (:class:`PlacementWalk`): each unit has a short sample; a unit whose sample
  is answered well enough is *placed out* and the walk continues with the
  next unit, and the walk stops at the first unit that is not. Answers are
  recorded like any other, so the scheduler starts placed-out items with the
  stability that correct answers give them (pretesting, Richland et al. 2009).
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, field

from .model import ItemId

PASS_FRACTION = 0.8
"""Share of correct answers that passes a level exam or places out of a unit."""

PLACEMENT_SAMPLE = 5
"""Questions per unit in the placement test: four of five pass, so one slip is allowed."""


def needed(total: int, fraction: float = PASS_FRACTION) -> int:
    """Correct answers needed out of ``total`` to reach ``fraction``."""
    # The epsilon keeps 0.8 × 5 = 4.000000000000001 from asking for five.
    return math.ceil(fraction * total - 1e-9)


def passes(correct: int, total: int, fraction: float = PASS_FRACTION) -> bool:
    """Whether ``correct`` answers out of ``total`` pass; nothing answered never passes."""
    return total > 0 and correct >= needed(total, fraction)


def balanced_sample(
    groups: Sequence[Sequence[ItemId]], size: int, rng: random.Random
) -> list[ItemId]:
    """Up to ``size`` distinct items spread as evenly as possible over ``groups``.

    Every group gets an equal share (the first groups one more when ``size``
    does not divide evenly); a group with too few items gives its unused
    share to the others. An item that appears in several groups counts for
    the first group that is given it. The result alternates between groups
    (unit 1, unit 2, … unit 1, …) so that a session built from it is
    interleaved from the start.
    """
    pools = []
    seen: set[ItemId] = set()
    for group in groups:
        pool = [i for i in dict.fromkeys(group) if i not in seen]
        rng.shuffle(pool)
        seen.update(pool)
        pools.append(pool)
    quotas = [0] * len(pools)
    left = min(size, sum(len(p) for p in pools))
    while left > 0:
        open_groups = [n for n, pool in enumerate(pools) if quotas[n] < len(pool)]
        share = max(1, left // len(open_groups))
        for n in open_groups:
            if left == 0:
                break
            extra = min(share, len(pools[n]) - quotas[n], left)
            quotas[n] += extra
            left -= extra
    chosen = [pool[:quota] for pool, quota in zip(pools, quotas, strict=True)]
    result: list[ItemId] = []
    for rank in range(max(quotas, default=0)):
        result.extend(items[rank] for items in chosen if rank < len(items))
    return result


@dataclass(slots=True)
class _UnitSample:
    unit_id: str
    items: tuple[ItemId, ...]
    correct: int = 0
    wrong: int = 0

    @property
    def needed(self) -> int:
        return needed(len(self.items))

    @property
    def passed(self) -> bool:
        return self.correct >= self.needed

    @property
    def failed(self) -> bool:
        return self.wrong > len(self.items) - self.needed


@dataclass(slots=True)
class PlacementWalk:
    """The adaptive placement test over units in curriculum order.

    ``samples`` pairs each unit with the items asked about it, in the order
    they are asked; items must not repeat across units. A unit is decided as
    soon as its outcome is certain: placed out once enough answers are
    correct (its remaining items are not asked), failed once too many are
    wrong, which ends the walk.
    """

    samples: Sequence[tuple[str, Sequence[ItemId]]]
    _units: list[_UnitSample] = field(init=False)
    _owner: dict[ItemId, _UnitSample] = field(init=False)

    def __post_init__(self) -> None:
        self._units = [_UnitSample(u, tuple(items)) for u, items in self.samples if items]
        self._owner = {}
        for unit in self._units:
            for item in unit.items:
                if item in self._owner:
                    raise ValueError(f'{item} is sampled for two units')
                self._owner[item] = unit

    @property
    def items(self) -> tuple[ItemId, ...]:
        """Every item that may be asked, in order."""
        return tuple(i for unit in self._units for i in unit.items)

    def record(self, item_id: ItemId, correct: bool) -> None:
        """An answer to ``item_id``; answers to decided units or after the end are ignored."""
        unit = self._owner.get(item_id)
        if unit is None or self.finished or unit.passed or unit.failed:
            return
        if correct:
            unit.correct += 1
        else:
            unit.wrong += 1

    @property
    def placed(self) -> tuple[str, ...]:
        """Units placed out so far, in order."""
        return tuple(u.unit_id for u in self._units if u.passed)

    @property
    def failed(self) -> str | None:
        """The unit that ended the walk, if any."""
        return next((u.unit_id for u in self._units if u.failed), None)

    @property
    def finished(self) -> bool:
        """A unit was failed, or every unit is decided."""
        return self.failed is not None or all(u.passed for u in self._units)

    def wants(self, item_id: ItemId) -> bool:
        """Whether a question about ``item_id`` still helps decide the walk."""
        unit = self._owner.get(item_id)
        return unit is not None and not self.finished and not unit.passed
