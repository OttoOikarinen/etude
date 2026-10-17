# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Playback with beat callbacks for rhythm tapping, with or without sound.

Tapping needs to know when beat 0 sounds (``PlaybackHandle.started_at``)
and wants every beat for the visual metronome. With sound the model's
audio backend provides both. Without sound (no synthesizer, or the null
backend) :class:`TimerPlayback` counts the same beats on the GLib main
loop, so the visual metronome alone paces the learner.

Clocks: ``started_at`` and tap times are ``time.monotonic()`` seconds,
which is ``CLOCK_MONOTONIC`` on Linux, the clock ``GLib.get_monotonic_time()``
reads too. Tap events are put on that clock by
:class:`~etude.audio.latency.EventClock` (see :data:`TAP_CLOCK`).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from gi.repository import GLib

from ..audio.backend import PlaybackHandle
from ..audio.latency import EventClock
from ..audio.metronome import beats
from ..audio.spec import PlaybackSpec
from .common import get_settings

if TYPE_CHECKING:
    from .model import AppModel

BeatCallback = Callable[[int], None]
FinishedCallback = Callable[[], None]

LEAD_MS = 150.0
"""How far ahead a silent playback starts, so its first beat is not late."""
RELEASE_MS = 300.0
"""Matches :data:`etude.audio.schedule.RELEASE_MS`: the take ends this long after the bars."""

TAP_CLOCK = EventClock()
"""One event clock for the whole application: the longer it watches events,
the better it knows the shortest delivery delay."""


class Player(Protocol):
    """Starts a playback and reports its beats; returns the running playback."""

    def __call__(
        self,
        spec: PlaybackSpec,
        *,
        on_beat: BeatCallback | None = None,
        on_finished: FinishedCallback | None = None,
    ) -> PlaybackHandle: ...


class TimerPlayback:
    """A silent :class:`~etude.audio.backend.PlaybackHandle` driven by GLib timeouts.

    Callbacks run on the main loop. Each beat is scheduled from the start
    time, so timer delays never add up.
    """

    def __init__(
        self,
        spec: PlaybackSpec,
        on_beat: BeatCallback | None = None,
        on_finished: FinishedCallback | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.spec = spec
        self._clock = clock
        now = clock()
        count_in = beats(spec.meter, spec.count_in, spec.length)
        first = count_in[0].start if count_in else 0
        self._started_at = now + (LEAD_MS - spec.beats_to_ms(min(first, 0))) / 1000.0
        self._sources: list[int] = []
        self.stopped = False
        for beat in count_in:
            if on_beat is not None:
                self._at(spec.beats_to_ms(beat.start), on_beat, beat.number)
        if on_finished is not None:
            self._at(spec.beats_to_ms(spec.length) + RELEASE_MS, on_finished)

    @property
    def started_at(self) -> float:
        return self._started_at

    def _at(self, ms: float, callback: Callable[..., None], *args: object) -> None:
        def fire() -> bool:
            if not self.stopped:
                callback(*args)
            return GLib.SOURCE_REMOVE

        delay = max(0.0, (self._started_at - self._clock()) * 1000.0 + ms)
        self._sources.append(GLib.timeout_add(round(delay), fire))

    def stop(self) -> None:
        self.stopped = True
        context = GLib.MainContext.default()
        for source in self._sources:
            if context.find_source_by_id(source) is not None:
                GLib.source_remove(source)
        self._sources.clear()


def silent_player(
    spec: PlaybackSpec,
    *,
    on_beat: BeatCallback | None = None,
    on_finished: FinishedCallback | None = None,
) -> TimerPlayback:
    return TimerPlayback(spec, on_beat, on_finished)


def latency_ms() -> float:
    """The calibrated tap correction (``audio-latency-ms``): taps lag by this much."""
    settings = get_settings()
    return float(settings.get_int('audio-latency-ms')) if settings is not None else 0.0


def model_player(model: AppModel) -> Player:
    """A :class:`Player` that plays through the model's audio, or silently (with the
    same beats) when there is no sound."""

    def play(
        spec: PlaybackSpec,
        *,
        on_beat: BeatCallback | None = None,
        on_finished: FinishedCallback | None = None,
    ) -> PlaybackHandle:
        handle = None
        if model.audio_available:
            handle = model.play(spec, on_beat=on_beat, on_finished=on_finished)
        if handle is None:
            handle = silent_player(spec, on_beat=on_beat, on_finished=on_finished)
        return handle

    return play
