# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random

import pytest
from hypothesis import given
from hypothesis import strategies as st

from etude.audio.latency import (
    LatencyEstimate,
    NotEnoughTapsError,
    TapGrade,
    TapMatch,
    estimate_offset,
    grade_taps,
    tolerance_windows,
)

CLICKS = [i * 500.0 for i in range(16)]


def test_constant_offset() -> None:
    taps = [c + 42 for c in CLICKS]
    estimate = estimate_offset(CLICKS, taps)
    assert estimate == LatencyEstimate(42.0, 0.0, 16, 0)
    assert estimate.is_reliable()


def test_offset_larger_than_half_the_interval_is_still_matched() -> None:
    clicks = [i * 400.0 for i in range(12)]
    taps = [c + 230 for c in clicks]
    assert estimate_offset(clicks, taps).offset_ms == 230


def test_outliers_and_missed_clicks_are_rejected() -> None:
    rng = random.Random(1)
    taps = [c + 80 + rng.uniform(-10, 10) for c in CLICKS]
    del taps[3]  # a missed click
    taps[7] += 150  # a stumble
    taps.append(taps[10] + 2)  # a double tap
    estimate = estimate_offset(CLICKS, taps)
    assert abs(estimate.offset_ms - 80) < 6
    assert estimate.rejected == 2
    assert estimate.used == 14
    assert 0 < estimate.spread_ms < 15


def test_early_taps_give_negative_offset() -> None:
    assert estimate_offset(CLICKS, [c - 25 for c in CLICKS]).offset_ms == -25


def test_spread_reports_inconsistent_tapping() -> None:
    rng = random.Random(7)
    taps = [c + 60 + rng.gauss(0, 40) for c in CLICKS]
    estimate = estimate_offset(CLICKS, taps)
    assert not estimate.is_reliable()


def test_too_few_taps() -> None:
    with pytest.raises(NotEnoughTapsError, match='at least 8'):
        estimate_offset(CLICKS, CLICKS[:5])
    with pytest.raises(NotEnoughTapsError):
        estimate_offset([], CLICKS)
    with pytest.raises(NotEnoughTapsError, match='near a click'):
        estimate_offset([0.0], [c + 10_000 for c in CLICKS])
    # Many taps, but they pile up on a few clicks.
    with pytest.raises(NotEnoughTapsError, match='matched'):
        estimate_offset(CLICKS[:3], [c + 10 for c in CLICKS[:3]] * 4)


def test_scattered_taps_are_not_enough() -> None:
    taps = [c + 30 for c in CLICKS[:8]] + [c + 250 for c in CLICKS[8:]]
    with pytest.raises(NotEnoughTapsError, match='matched'):
        estimate_offset(CLICKS, taps, min_taps=9)


@given(
    st.floats(min_value=-150, max_value=250),
    st.lists(st.floats(min_value=-8, max_value=8), min_size=16, max_size=16),
    st.floats(min_value=400, max_value=1000),
)
def test_offset_recovered_from_jittery_taps(
    offset: float, jitter: list[float], interval: float
) -> None:
    clicks = [i * interval for i in range(16)]
    taps = [c + offset + j for c, j in zip(clicks, jitter, strict=True)]
    estimate = estimate_offset(clicks, taps)
    assert abs(estimate.offset_ms - offset) <= 8
    assert estimate.used >= 14


def test_tolerance_windows_scale_with_tempo() -> None:
    assert tolerance_windows(60) == (50, 100)
    assert tolerance_windows(120) == (50, 100)
    assert tolerance_windows(240) == (25, 50)
    good, ok = tolerance_windows(80, min_interval_ms=125)
    assert ok == pytest.approx(56.25)
    assert good == pytest.approx(28.125)
    assert tolerance_windows(80, min_interval_ms=1000) == (50, 100)
    with pytest.raises(ValueError, match='tempo'):
        tolerance_windows(0)


def test_grade_perfect_and_sloppy_taps() -> None:
    onsets = [0.0, 500.0, 1000.0, 1500.0]
    result = grade_taps(onsets, [5, 490, 1070, 1600, 1800], tempo=120)
    assert [m.grade for m in result.matches] == [
        TapGrade.GOOD,
        TapGrade.GOOD,
        TapGrade.OK,
        TapGrade.OK,
    ]
    assert (result.good, result.ok, result.missed, result.extra) == (2, 2, 0, 1)
    assert result.extra_taps == (1800,)
    assert result.score == pytest.approx(3 / 5)
    assert result.mean_error_ms == pytest.approx((5 - 10 + 70 + 100) / 4)
    assert not result.perfect


def test_grade_missing_taps_and_offset() -> None:
    onsets = [0.0, 500.0, 1000.0]
    result = grade_taps(onsets, [60, 1065], tempo=120, offset_ms=60)
    assert result.matches[1] == TapMatch(500.0, None, TapGrade.MISSED)
    assert result.matches[1].error_ms is None
    assert result.matches[0].error_ms == 0
    assert result.missed == 1
    assert result.score == pytest.approx(2 / 3)


def test_each_tap_matches_one_onset() -> None:
    # Two taps near one onset: the closer one counts, the other is extra.
    result = grade_taps([0.0, 1000.0], [-30, 10], tempo=60)
    assert result.matches[0].tap_ms == 10
    assert result.extra_taps == (-30,)
    assert result.missed == 1


def test_fast_rhythm_windows_shrink() -> None:
    onsets = [i * 125.0 for i in range(8)]  # sixteenths at 120
    result = grade_taps(onsets, [o + 40 for o in onsets], tempo=120)
    assert result.ok_ms == pytest.approx(56.25)
    assert result.good == 0
    assert result.ok == 8


def test_empty_grading() -> None:
    assert grade_taps([], [], tempo=100).score == 1.0
    assert grade_taps([], [1.0], tempo=100).score == 0.0
    assert grade_taps([], [], tempo=100).mean_error_ms is None
    assert grade_taps([0.0], [0.0], tempo=100).perfect


@given(
    st.lists(st.floats(min_value=0, max_value=10_000), max_size=10, unique=True),
    st.lists(st.floats(min_value=-200, max_value=10_200), max_size=12),
    st.floats(min_value=40, max_value=240),
)
def test_grading_accounts_for_every_tap_and_onset(
    onsets: list[float], taps: list[float], tempo: float
) -> None:
    result = grade_taps(onsets, taps, tempo=tempo)
    matched = [m.tap_ms for m in result.matches if m.tap_ms is not None]
    assert len(result.matches) == len(onsets)
    assert len(matched) + result.extra == len(taps)
    assert 0.0 <= result.score <= 1.0
    for m in result.matches:
        if m.error_ms is not None:
            assert abs(m.error_ms) <= result.ok_ms
            assert (m.grade is TapGrade.GOOD) == (abs(m.error_ms) <= result.good_ms)


def test_inconsistent_taps_are_rejected_as_outliers() -> None:
    taps = [c + 50 for c in CLICKS[:8]] + [c + 140 for c in CLICKS[8:10]]
    assert estimate_offset(CLICKS, taps).rejected == 2
    with pytest.raises(NotEnoughTapsError, match='consistent'):
        estimate_offset(CLICKS, taps, min_taps=9)


def test_single_tap_when_allowed() -> None:
    assert estimate_offset(CLICKS, [512.0], min_taps=1) == LatencyEstimate(12.0, 0.0, 1, 0)
