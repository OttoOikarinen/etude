# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The FluidSynth backend.

Every note, metronome click and callback of a playback is scheduled up
front on a FluidSynth sequencer that runs on the synthesizer's sample
clock, so timing is exact to one 64-sample block (1.3 ms at 48 kHz)
however busy the Python side is.

``on_beat`` and ``on_finished`` run on the audio thread, inside the
sequencer. Keep them short (GTK code should only ``GLib.idle_add``); they
may call :meth:`FluidSynthBackend.play` or :meth:`~FluidSynthBackend.stop`.

Without an audio driver (``audio_driver=None``) nothing reaches the sound
server and the caller pulls audio with :meth:`FluidSynthBackend.render`;
the tests use this to check levels and timing offline.
"""

from __future__ import annotations

import itertools
import logging
import os
import threading
import time
from array import array
from collections.abc import Callable
from dataclasses import dataclass, field

from . import fluidsynth as fs
from .schedule import (
    MELODIC_CHANNEL,
    PERCUSSION_CHANNEL,
    EventKind,
    build_schedule,
    to_ticks,
)
from .spec import PlaybackSpec

log = logging.getLogger(__name__)

SAMPLE_RATE = 48_000
PERIOD_SIZE = 256
PERIODS = 3
GAIN = 0.8
"""Measured offline with GeneralUser GS at 48 kHz: one note at velocity 90
peaks at 0.10–0.15, a four-note chord at velocity 90 at 0.25–0.36 (organ and
flute loudest), and even seven notes at velocity 127 stay below 0.95."""
LEAD_MS = 40
"""How far ahead of the sequencer's clock the first event is scheduled, so
that a playback's events are all queued before the first one is due."""
PERCUSSION_BANK = 128


@dataclass(eq=False)
class FluidPlayback:
    """A :class:`~etude.audio.backend.PlaybackHandle` for one FluidSynth playback."""

    _backend: FluidSynthBackend
    tag: int
    """Sequencer source id of this playback's events."""
    spec: PlaybackSpec
    on_finished: Callable[[], None] | None
    on_beat: Callable[[int], None] | None
    _started_at: float = 0.0
    origin_tick: int = 0
    """Sequencer tick of beat 0."""
    stopped: bool = False
    finished: bool = False
    timers: set[int] = field(default_factory=set)

    @property
    def started_at(self) -> float:
        return self._started_at

    def stop(self) -> None:
        self._backend._cancel(self)


class FluidSynthBackend:
    """Plays :class:`PlaybackSpec` objects with FluidSynth and a General MIDI SoundFont."""

    def __init__(
        self,
        soundfont: str | os.PathLike[str],
        *,
        library: str | os.PathLike[str] | None = None,
        audio_driver: str | None = 'pulseaudio',
        sample_rate: int = SAMPLE_RATE,
        period_size: int = PERIOD_SIZE,
        periods: int = PERIODS,
        gain: float = GAIN,
    ) -> None:
        self._lib = fs.Library(library)
        self._lib.route_logging()
        self._lock = threading.Lock()
        self._current: FluidPlayback | None = None
        self._timers: dict[int, tuple[FluidPlayback, EventKind, int]] = {}
        self._timer_keys = itertools.count(1)
        self._tags = itertools.cycle(range(1000, 30000))
        self._driver: fs.AudioDriver | None = None
        self._settings = fs.Settings(self._lib)
        self._synth: fs.Synth | None = None
        self._sequencer: fs.Sequencer | None = None
        try:
            self._configure(audio_driver, sample_rate, period_size, periods, gain)
            self._synth = synth = fs.Synth(self._lib, self._settings)
            self._sfont_id = synth.sfload(soundfont)
            synth.program_select(PERCUSSION_CHANNEL, self._sfont_id, PERCUSSION_BANK, 0)
            self._sequencer = seq = fs.Sequencer(self._lib)
            self._synth_client = seq.register_fluidsynth(synth)
            self._client = seq.register_client('etude', self._on_event)
            if audio_driver is not None:
                self._driver = fs.AudioDriver(self._lib, self._settings, synth)
        except BaseException:
            self.close()
            raise
        self.sample_rate = self._settings.get_num('synth.sample-rate')
        if audio_driver is None:
            self._latency_ms = 0.0
        else:
            frames = self._settings.get_int('audio.period-size')
            count = self._settings.get_int('audio.periods')
            self._latency_ms = frames * count / self.sample_rate * 1000.0
        log.info(
            'FluidSynth %s ready (%s, %.0f Hz, latency ≈ %.1f ms)',
            self._lib.version,
            audio_driver or 'offline',
            self.sample_rate,
            self._latency_ms,
        )

    def _configure(
        self,
        audio_driver: str | None,
        sample_rate: int,
        period_size: int,
        periods: int,
        gain: float,
    ) -> None:
        settings = self._settings
        settings.set_num('synth.sample-rate', float(sample_rate))
        settings.set_num('synth.gain', gain)
        if audio_driver is not None:
            settings.set_str('audio.driver', audio_driver)
            settings.set_int('audio.period-size', period_size)
            settings.set_int('audio.periods', periods)
            if audio_driver == 'pulseaudio':
                settings.set_str('audio.pulseaudio.media-role', 'music')

    # AudioBackend

    @property
    def available(self) -> bool:
        return self._synth is not None

    @property
    def output_latency_ms(self) -> float:
        return self._latency_ms

    def play(
        self,
        spec: PlaybackSpec,
        *,
        on_finished: Callable[[], None] | None = None,
        on_beat: Callable[[int], None] | None = None,
    ) -> FluidPlayback:
        synth, seq = self._require()
        self.stop()
        schedule = build_schedule(spec)
        handle = FluidPlayback(self, next(self._tags), spec, on_finished, on_beat)
        if any(not note.percussion for note in spec.notes):
            synth.program_select(MELODIC_CHANNEL, self._sfont_id, 0, spec.instrument.value)

        # Register the callbacks before anything is queued: the first may fire at once.
        timer_keys: list[int] = []
        with self._lock:
            for event in schedule.events:
                if event.kind in (EventKind.BEAT, EventKind.FINISHED):
                    key = next(self._timer_keys)
                    self._timers[key] = (handle, event.kind, event.beat)
                    handle.timers.add(key)
                    timer_keys.append(key)
            self._current = handle

        now_tick = seq.tick
        now = time.monotonic()
        handle.origin_tick = origin = now_tick + LEAD_MS - round(schedule.start_ms)
        handle._started_at = now + (origin - now_tick + self._latency_ms) / 1000.0

        keys = iter(timer_keys)
        message = fs.Event(self._lib)
        try:
            for event in schedule.events:
                if event.kind is EventKind.NOTE_ON:
                    message.route(handle.tag, self._synth_client)
                    message.noteon(event.channel, event.key, event.velocity)
                elif event.kind is EventKind.NOTE_OFF:
                    message.route(handle.tag, self._synth_client)
                    message.noteoff(event.channel, event.key)
                else:
                    message.route(handle.tag, self._client).timer(next(keys))
                seq.send_at(message, to_ticks(event.time_ms, origin))
        finally:
            message.delete()
        if handle.stopped:
            # Stopped from another thread while its events were being queued.
            seq.remove_events(source=handle.tag)
        return handle

    def stop(self) -> None:
        with self._lock:
            current = self._current
        if current is not None:
            self._cancel(current)

    def close(self) -> None:
        if self._synth is not None and self._sequencer is not None:
            self.stop()
        # The driver goes first so that nothing renders while the rest is torn down.
        if self._driver is not None:
            self._driver.delete()
            self._driver = None
        if self._sequencer is not None:
            self._sequencer.delete()
            self._sequencer = None
        if self._synth is not None:
            self._synth.delete()
            self._synth = None
        self._settings.delete()

    # Offline rendering

    def render(self, frames: int) -> tuple[array[float], array[float]]:
        """Render ``frames`` stereo frames; only valid without an audio driver.

        Rendering advances the sequencer, so scheduled notes and callbacks
        happen here, on the calling thread.
        """
        if self._driver is not None:
            raise RuntimeError('render() is only available without an audio driver')
        synth, _ = self._require()
        return synth.write_float(frames)

    @property
    def tick(self) -> int:
        """The sequencer clock: milliseconds of audio rendered so far."""
        return self._require()[1].tick

    def tick_to_frame(self, tick: int) -> int:
        """The sample frame (since the synthesizer started) of a sequencer tick."""
        return round(tick * self.sample_rate / 1000.0)

    # Internals

    def _require(self) -> tuple[fs.Synth, fs.Sequencer]:
        if self._synth is None or self._sequencer is None:
            raise RuntimeError('the FluidSynth backend is closed')
        return self._synth, self._sequencer

    def _cancel(self, handle: FluidPlayback) -> None:
        with self._lock:
            if handle.stopped or handle.finished:
                return
            handle.stopped = True
            self._forget(handle)
        if self._synth is None or self._sequencer is None:
            return
        self._sequencer.remove_events(source=handle.tag)
        self._synth.all_notes_off(MELODIC_CHANNEL)
        self._synth.all_notes_off(PERCUSSION_CHANNEL)

    def _forget(self, handle: FluidPlayback) -> None:
        """Drop the bookkeeping of ``handle``; call with the lock held."""
        for key in handle.timers:
            self._timers.pop(key, None)
        handle.timers.clear()
        if self._current is handle:
            self._current = None

    def _on_event(self, _time: int, event: int) -> None:
        if fs.event_type(self._lib, event) != fs.FLUID_SEQ_TIMER:
            return
        key = fs.event_data(self._lib, event)
        with self._lock:
            entry = self._timers.pop(key, None)
            if entry is None:
                return
            handle, kind, beat = entry
            if handle.stopped:
                return
            handle.timers.discard(key)
            if kind is EventKind.FINISHED:
                handle.finished = True
                self._forget(handle)
        if kind is EventKind.BEAT:
            if handle.on_beat is not None:
                handle.on_beat(beat)
        elif handle.on_finished is not None:
            handle.on_finished()
