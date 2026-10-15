# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""A silent backend used in tests and when no synthesizer is available."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from .spec import PlaybackSpec


@dataclass
class NullHandle:
    started_at: float = field(default_factory=time.monotonic)
    stopped: bool = False

    def stop(self) -> None:
        self.stopped = True


class NullBackend:
    """Records what would have been played and finishes immediately."""

    def __init__(self, *, available: bool = False) -> None:
        self._available = available
        self.played: list[PlaybackSpec] = []

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
        self.played.append(spec)
        if on_finished is not None:
            on_finished()
        return NullHandle()

    def stop(self) -> None:
        pass

    def close(self) -> None:
        pass
