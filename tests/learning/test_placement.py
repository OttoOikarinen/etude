# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random
from collections import Counter

import pytest
from hypothesis import given
from hypothesis import strategies as st

from etude.learning.model import ItemId
from etude.learning.placement import (
    PASS_FRACTION,
    PlacementWalk,
    balanced_sample,
    needed,
    passes,
)


def ids(prefix: str, count: int) -> list[ItemId]:
    return [ItemId(f'{prefix}.{n}') for n in range(count)]


# Scoring


@pytest.mark.parametrize(
    ('total', 'expected'), [(1, 1), (4, 4), (5, 4), (10, 8), (30, 24), (31, 25)]
)
def test_needed_is_eighty_percent_rounded_up(total: int, expected: int) -> None:
    assert PASS_FRACTION == 0.8
    assert needed(total) == expected


def test_passes() -> None:
    assert passes(24, 30)
    assert not passes(23, 30)
    assert passes(4, 5)
    assert not passes(0, 0), 'an exam without answers is not passed'


# Balanced samples


def test_balanced_sample_spreads_evenly_and_interleaves() -> None:
    groups = [ids('a', 20), ids('b', 20), ids('c', 20)]
    sample = balanced_sample(groups, 9, random.Random(1))
    assert Counter(i.split('.')[0] for i in sample) == {'a': 3, 'b': 3, 'c': 3}
    assert [i.split('.')[0] for i in sample[:3]] == ['a', 'b', 'c']


def test_balanced_sample_gives_unused_shares_to_other_groups() -> None:
    groups = [ids('a', 2), ids('b', 20), ids('c', 20)]
    sample = balanced_sample(groups, 12, random.Random(1))
    counts = Counter(i.split('.')[0] for i in sample)
    assert counts == {'a': 2, 'b': 5, 'c': 5}


def test_balanced_sample_is_limited_by_the_items_available() -> None:
    groups = [ids('a', 2), [], ids('b', 1)]
    assert sorted(balanced_sample(groups, 30, random.Random(1))) == ['a.0', 'a.1', 'b.0']


def test_balanced_sample_counts_shared_items_once() -> None:
    shared = ids('a', 3)
    sample = balanced_sample([shared, [*shared, *ids('b', 3)]], 6, random.Random(2))
    assert len(sample) == len(set(sample)) == 6


@given(
    st.lists(st.integers(min_value=0, max_value=15), min_size=1, max_size=8),
    st.integers(min_value=0, max_value=60),
    st.integers(min_value=0, max_value=1000),
)
def test_balanced_sample_properties(sizes: list[int], size: int, seed: int) -> None:
    groups = [ids(f'g{n}', count) for n, count in enumerate(sizes)]
    sample = balanced_sample(groups, size, random.Random(seed))
    assert len(sample) == min(size, sum(sizes))
    assert len(set(sample)) == len(sample)
    counts = Counter(i.split('.')[0] for i in sample)
    # No group falls more than one question behind another that still had items to give.
    for n, count in enumerate(sizes):
        mine = counts[f'g{n}']
        if mine < count:
            assert all(counts[f'g{m}'] <= mine + 1 for m in range(len(sizes)))


# Placement walk


def walk_of(*units: tuple[str, int]) -> PlacementWalk:
    return PlacementWalk([(unit, ids(unit, count)) for unit, count in units])


def test_walk_places_out_units_and_stops_at_the_first_failure() -> None:
    walk = walk_of(('u1', 5), ('u2', 5), ('u3', 5))
    assert len(walk.items) == 15
    for n in range(4):
        walk.record(ItemId(f'u1.{n}'), True)
    assert walk.placed == ('u1',)
    assert not walk.wants(ItemId('u1.4')), 'a decided unit needs no more questions'
    assert walk.wants(ItemId('u2.0'))
    walk.record(ItemId('u2.0'), False)
    assert not walk.finished, 'one slip is allowed'
    walk.record(ItemId('u2.1'), False)
    assert walk.failed == 'u2'
    assert walk.finished
    assert not walk.wants(ItemId('u3.0'))
    assert walk.placed == ('u1',)
    walk.record(ItemId('u3.0'), True)  # ignored after the end
    assert walk.placed == ('u1',)


def test_walk_finishes_when_every_unit_is_placed_out() -> None:
    walk = walk_of(('u1', 2), ('u2', 1))
    for item in walk.items:
        walk.record(item, True)
    assert walk.placed == ('u1', 'u2')
    assert walk.finished
    assert walk.failed is None


def test_walk_skips_units_without_items_and_ignores_unknown_items() -> None:
    walk = PlacementWalk([('empty', []), ('u1', ids('u1', 1))])
    walk.record(ItemId('other.1'), False)
    assert not walk.finished
    walk.record(ItemId('u1.0'), True)
    assert walk.placed == ('u1',)


def test_walk_rejects_items_sampled_for_two_units() -> None:
    with pytest.raises(ValueError, match='two units'):
        PlacementWalk([('u1', ids('x', 2)), ('u2', ids('x', 1))])
