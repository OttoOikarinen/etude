# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The audio backend interface.

The application uses one backend for its lifetime: FluidSynth when the
library and SoundFont load, otherwise :class:`~etude.audio.null.NullBackend`
(``available`` is ``False`` and the UI offers the written alternative for
ear-training tasks).

Threading: backends may invoke ``on_finished`` and ``on_beat`` from a
non-main thread. GTK code must hop to the main loop (``GLib.idle_add``)
before touching widgets.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .spec import PlaybackSpec


class PlaybackHandle(Protocol):
    def stop(self) -> None:
        """Stop this playback early; ``on_finished`` is not called."""

    @property
    def started_at(self) -> float:
        """Monotonic time (``time.monotonic()``, seconds) at which beat 0 sounds,
        compensated for output latency. Rhythm tapping compares GDK event times
        against this."""


class AudioBackend(Protocol):
    @property
    def available(self) -> bool: ...

    @property
    def output_latency_ms(self) -> float:
        """Estimated delay between scheduling and hearing a note."""

    def play(
        self,
        spec: PlaybackSpec,
        *,
        on_finished: Callable[[], None] | None = None,
        on_beat: Callable[[int], None] | None = None,
    ) -> PlaybackHandle:
        """Start a playback, stopping any playback already running.

        ``on_beat`` is called with the beat number (negative during the
        count-in) for metronome visuals.
        """

    def stop(self) -> None:
        """Silence everything."""

    def close(self) -> None:
        """Release the synthesizer and audio device."""
