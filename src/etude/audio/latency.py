# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Latency calibration and tap grading.

Both work on plain millisecond timestamps on one clock: click and note
onsets computed from ``PlaybackHandle.started_at`` and the spec, and the
learner's taps (key or pointer events).

*Calibration* plays a steady click and asks the learner to tap along. The
taps lag the scheduled clicks by a roughly constant amount: audio output
latency the backend did not know about, input latency, and the learner's
habit of tapping early or late. :func:`estimate_offset` measures it so
that later taps can be compensated with ``offset_ms``.

*Grading* matches a learner's taps to the expected onsets of a rhythm.

:class:`EventClock` puts input events on that clock: windowing systems
stamp events in milliseconds on a clock of their own, which is more exact
than the time the event reaches the application's main loop.
"""

from __future__ import annotations

import bisect
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from itertools import pairwise

MIN_TAPS = 8
"""Matched taps needed for a calibration result."""
MAX_OFFSET_MS = 300.0
"""Largest plausible offset between a click and its tap."""
VOTE_WINDOW_MS = 40.0
"""A tap supports an offset hypothesis when it is this close to it."""
MATCH_WINDOW_MS = 100.0
"""Taps further than this from the rough offset are not paired with a click."""
MAD_SCALE = 1.4826
"""Turns a median absolute deviation into a standard-deviation estimate."""
OUTLIER_SIGMAS = 3.0
MIN_OUTLIER_MS = 20.0
"""Never reject taps closer than this to the median."""

RESYNC_MS = 1000.0
"""An event clock that seems to have jumped by more than this is synchronised anew."""

GOOD_MS = 50.0
OK_MS = 100.0
REFERENCE_TEMPO = 120.0
"""Tolerance windows are the nominal ones at or below this tempo."""


class NotEnoughTapsError(ValueError):
    """Too few taps matched a click to estimate the latency."""


@dataclass(frozen=True, slots=True)
class LatencyEstimate:
    offset_ms: float
    """Median of tap minus click; positive when taps come late."""
    spread_ms: float
    """Robust standard deviation of the kept differences (consistency of the taps)."""
    used: int
    """Taps that went into the estimate."""
    rejected: int
    """Taps that matched no click or were outliers."""

    def is_reliable(self, max_spread_ms: float = 30.0) -> bool:
        return self.spread_ms <= max_spread_ms


def _robust_sigma(values: Sequence[float], centre: float) -> float:
    if len(values) < 2:
        return 0.0
    return MAD_SCALE * statistics.median(abs(v - centre) for v in values)


def estimate_offset(
    clicks_ms: Sequence[float],
    taps_ms: Sequence[float],
    *,
    min_taps: int = MIN_TAPS,
    max_offset_ms: float = MAX_OFFSET_MS,
    match_window_ms: float = MATCH_WINDOW_MS,
) -> LatencyEstimate:
    """Estimate the constant delay between scheduled ``clicks_ms`` and ``taps_ms``.

    Clicks are periodic, so an offset is only known up to the click interval.
    Every tap–click difference within ``max_offset_ms`` is a candidate; the
    one that lines up the most taps with clicks (the smallest, on a tie) is
    the rough offset. Each tap is then paired, each click at most once, with
    the click nearest to ``tap - rough offset`` if it is within
    ``match_window_ms``. Differences further than three robust standard
    deviations (and at least :data:`MIN_OUTLIER_MS`) from their median are
    rejected, and the median of the rest is the estimate.

    Raises :class:`NotEnoughTapsError` when fewer than ``min_taps`` survive.
    """
    clicks = sorted(clicks_ms)
    taps = sorted(taps_ms)
    if not clicks or len(taps) < min_taps:
        raise NotEnoughTapsError(f'need at least {min_taps} taps, got {len(taps)}')

    def nearest(t: float) -> int:
        """Index of the click nearest to ``t``."""
        i = bisect.bisect_left(clicks, t)
        if i == len(clicks) or (i > 0 and t - clicks[i - 1] <= clicks[i] - t):
            return i - 1
        return i

    candidates = {t - c for t in taps for c in clicks if abs(t - c) <= max_offset_ms}
    if not candidates:
        raise NotEnoughTapsError('no tap was near a click')

    def support(offset: float) -> tuple[int, float]:
        lined_up = sum(
            1 for t in taps if abs(t - offset - clicks[nearest(t - offset)]) <= VOTE_WINDOW_MS
        )
        return lined_up, -abs(offset)

    rough = max(sorted(candidates), key=support)

    used_clicks: set[int] = set()
    diffs: list[float] = []
    for t in taps:
        index = nearest(t - rough)
        diff = t - clicks[index]
        if index in used_clicks or abs(diff - rough) > match_window_ms:
            continue
        used_clicks.add(index)
        diffs.append(diff)

    if len(diffs) < min_taps:
        raise NotEnoughTapsError(f'only {len(diffs)} taps matched a click; need {min_taps}')
    centre = statistics.median(diffs)
    limit = max(OUTLIER_SIGMAS * _robust_sigma(diffs, centre), MIN_OUTLIER_MS)
    kept = [d for d in diffs if abs(d - centre) <= limit]
    if len(kept) < min_taps:
        raise NotEnoughTapsError(f'only {len(kept)} consistent taps; need {min_taps}')
    offset = statistics.median(kept)
    return LatencyEstimate(
        offset_ms=offset,
        spread_ms=_robust_sigma(kept, offset),
        used=len(kept),
        rejected=len(taps) - len(kept),
    )


class TapGrade(Enum):
    GOOD = 'good'
    OK = 'ok'
    MISSED = 'missed'


@dataclass(frozen=True, slots=True)
class TapMatch:
    onset_ms: float
    tap_ms: float | None
    """The (offset-compensated) tap matched to this onset, if any."""
    grade: TapGrade

    @property
    def error_ms(self) -> float | None:
        """Tap minus onset: positive when late."""
        return None if self.tap_ms is None else self.tap_ms - self.onset_ms


@dataclass(frozen=True, slots=True)
class TapResult:
    matches: tuple[TapMatch, ...]
    """One per expected onset, in time order."""
    extra_taps: tuple[float, ...]
    """Taps that matched no onset."""
    good_ms: float
    ok_ms: float
    """The tolerance windows used."""

    def count(self, grade: TapGrade) -> int:
        return sum(1 for m in self.matches if m.grade is grade)

    @property
    def good(self) -> int:
        return self.count(TapGrade.GOOD)

    @property
    def ok(self) -> int:
        return self.count(TapGrade.OK)

    @property
    def missed(self) -> int:
        return self.count(TapGrade.MISSED)

    @property
    def extra(self) -> int:
        return len(self.extra_taps)

    @property
    def score(self) -> float:
        """Between 0 and 1: a good tap counts 1, an ok tap ½, and every missed
        onset and extra tap adds to the total that is divided by."""
        total = len(self.matches) + self.extra
        if total == 0:
            return 1.0
        return (self.good + 0.5 * self.ok) / total

    @property
    def mean_error_ms(self) -> float | None:
        """Mean signed error of the matched taps: a tendency to rush (<0) or drag (>0)."""
        errors = [m.error_ms for m in self.matches if m.error_ms is not None]
        return statistics.fmean(errors) if errors else None

    @property
    def perfect(self) -> bool:
        return self.missed == 0 and self.extra == 0 and self.ok == 0


def tolerance_windows(
    tempo: float,
    *,
    good_ms: float = GOOD_MS,
    ok_ms: float = OK_MS,
    min_interval_ms: float | None = None,
) -> tuple[float, float]:
    """The good and ok windows (± ms) at ``tempo`` quarter notes per minute.

    Above :data:`REFERENCE_TEMPO` the windows shrink in proportion to the
    beat. When ``min_interval_ms`` (the shortest gap between onsets) is
    given, the ok window is also kept below half of it so that a tap can
    never be in reach of two onsets.
    """
    if tempo <= 0:
        raise ValueError(f'tempo must be positive, not {tempo}')
    scale = min(1.0, REFERENCE_TEMPO / tempo)
    good, ok = good_ms * scale, ok_ms * scale
    if min_interval_ms is not None and min_interval_ms > 0:
        ceiling = 0.45 * min_interval_ms
        if ok > ceiling:
            good, ok = good * ceiling / ok, ceiling
    return good, ok


def grade_taps(
    onsets_ms: Sequence[float],
    taps_ms: Sequence[float],
    *,
    tempo: float,
    offset_ms: float = 0.0,
    good_ms: float = GOOD_MS,
    ok_ms: float = OK_MS,
) -> TapResult:
    """Match taps to expected onsets and grade each onset.

    ``offset_ms`` (from :func:`estimate_offset`) is subtracted from every
    tap first. Tap–onset pairs inside the ok window are matched closest
    first, each onset and each tap at most once.
    """
    onsets = sorted(onsets_ms)
    taps = sorted(t - offset_ms for t in taps_ms)
    gaps = [b - a for a, b in pairwise(onsets) if b > a]
    good, ok = tolerance_windows(
        tempo, good_ms=good_ms, ok_ms=ok_ms, min_interval_ms=min(gaps, default=None)
    )

    pairs = sorted(
        (abs(tap - onset), i, j)
        for i, onset in enumerate(onsets)
        for j, tap in enumerate(taps)
        if abs(tap - onset) <= ok
    )
    onset_tap: dict[int, int] = {}
    used_taps: set[int] = set()
    for _, i, j in pairs:
        if i not in onset_tap and j not in used_taps:
            onset_tap[i] = j
            used_taps.add(j)

    matches = []
    for i, onset in enumerate(onsets):
        if i in onset_tap:
            tap = taps[onset_tap[i]]
            grade = TapGrade.GOOD if abs(tap - onset) <= good else TapGrade.OK
            matches.append(TapMatch(onset, tap, grade))
        else:
            matches.append(TapMatch(onset, None, TapGrade.MISSED))
    extra = tuple(t for j, t in enumerate(taps) if j not in used_taps)
    return TapResult(tuple(matches), extra, good, ok)


class EventClock:
    """Maps input event timestamps to the monotonic clock of ``started_at``.

    GDK stamps every input event with the time the windowing system saw it
    (``Gdk.Event.get_time()``: milliseconds on an unspecified clock, which
    wraps around after 49 days). Under Wayland this is usually the kernel's
    input timestamp, so it does not include the time the event waited for
    the application's main loop, for example while a frame was drawn. Its
    epoch is unknown, though.

    Every event is also seen *arriving* on the monotonic clock. Arrival
    minus stamp is the clock difference plus a delivery delay that is never
    negative, so the smallest difference seen estimates the clock difference
    (plus the shortest delivery delay, a constant that latency calibration
    absorbs). Mapping a stamp with it removes the main loop's jitter from
    the tap time. When a stamp is missing (0, as in synthesized events) or
    the clocks seem to have jumped by more than :data:`RESYNC_MS`, the
    arrival time is used and the estimate starts over.
    """

    def __init__(self) -> None:
        self._offset_ms: float | None = None

    def reset(self) -> None:
        self._offset_ms = None

    def to_monotonic(self, event_ms: int, arrival: float) -> float:
        """The monotonic time (seconds) of an event stamped ``event_ms`` that
        arrived at ``arrival`` (seconds, e.g. ``time.monotonic()``)."""
        if event_ms <= 0:
            return arrival
        sample = arrival * 1000.0 - event_ms
        offset = self._offset_ms
        if offset is None or sample < offset or sample - offset > RESYNC_MS:
            self._offset_ms = offset = sample
        return (event_ms + offset) / 1000.0
