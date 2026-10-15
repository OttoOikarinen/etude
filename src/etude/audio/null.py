# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""A silent backend used in tests and when no synthesizer is available."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from .spec import PlaybackSpec


@dataclass
class NullHandle:
    spec: PlaybackSpec
    on_finished: Callable[[], None] | None = None
    on_beat: Callable[[int], None] | None = None
    started_at: float = field(default_factory=time.monotonic)
    stopped: bool = False
    finished: bool = False

    def stop(self) -> None:
        self.stopped = True


class NullBackend:
    """Records what would have been played.

    Like a real backend, playback finishes asynchronously: nothing is
    called back until a test calls :meth:`complete`, which delivers the
    beats and the finish notification of the current playback.
    """

    def __init__(self, *, available: bool = False) -> None:
        self._available = available
        self.played: list[PlaybackSpec] = []
        self.current: NullHandle | None = None

    @property
    def available(self) -> bool:
        return self._available

    @property
    def output_latency_ms(self) -> float:
        return 0.0

    def play(
        self,
        spec: PlaybackSpec,
        *,
        on_finished: Callable[[], None] | None = None,
        on_beat: Callable[[int], None] | None = None,
    ) -> NullHandle:
        self.stop()
        self.played.append(spec)
        self.current = NullHandle(spec, on_finished, on_beat)
        return self.current

    def complete(self) -> None:
        """Deliver every beat (count-in beats are negative) and finish the playback."""
        handle = self.current
        if handle is None or handle.stopped:
            return
        if handle.on_beat is not None:
            for beat in range(-handle.spec.count_in, math.ceil(handle.spec.length)):
                handle.on_beat(beat)
        handle.finished = True
        self.current = None
        if handle.on_finished is not None:
            handle.on_finished()

    def stop(self) -> None:
        if self.current is not None:
            self.current.stop()
            self.current = None

    def close(self) -> None:
        self.stop()
