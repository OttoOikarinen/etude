# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The application's long-lived objects, wired together once at start-up.

Progress lives in ``$XDG_DATA_HOME/etude/progress.db`` (inside the Flatpak
sandbox that is ``~/.var/app/fi.oikarinenotto.etude/data/etude/``).
``ETUDE_DATA_DIR`` overrides the directory, for tests and development.
This module has no GTK dependency.
"""

from __future__ import annotations

import logging
import os
import random
import threading
from collections.abc import Mapping
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .audio.backend import AudioBackend
from .exercises.registry import ExerciseRegistry, default_registry
from .learning.engine import LearningEngine
from .learning.stats import StatsConfig
from .storage.db import Database
from .storage.repositories import SqliteAttemptLog, SqliteCardStore, SqliteSessionLog

log = logging.getLogger(__name__)

DATA_DIR_ENV = 'ETUDE_DATA_DIR'
DATABASE_NAME = 'progress.db'


def user_data_dir(environ: Mapping[str, str] = os.environ) -> Path:
    override = environ.get(DATA_DIR_ENV)
    if override:
        return Path(override)
    base = environ.get('XDG_DATA_HOME') or str(Path.home() / '.local' / 'share')
    return Path(base) / 'etude'


def local_timezone(environ: Mapping[str, str] = os.environ) -> tzinfo:
    """The learner's time zone, with daylight-saving rules, for daily streaks.

    ``$TZ`` wins; otherwise ``/etc/localtime`` names the zone (Flatpak links it
    to the host's zone). Falls back to the current fixed UTC offset.
    """
    candidates = []
    if environ.get('TZ'):
        candidates.append(environ['TZ'].lstrip(':'))
    try:
        target = os.readlink('/etc/localtime')
    except OSError:
        target = ''
    if 'zoneinfo/' in target:
        candidates.append(target.split('zoneinfo/', 1)[1])
    for name in candidates:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            continue
    return datetime.now().astimezone().tzinfo or UTC


class Services:
    """Database, exercise registry, learning engine and (lazily) the audio backend."""

    def __init__(
        self,
        database: Database,
        *,
        registry: ExerciseRegistry | None = None,
        timezone: tzinfo | None = None,
        audio: AudioBackend | None = None,
        rng: random.Random | None = None,
        stats_config: StatsConfig | None = None,
    ) -> None:
        self.database = database
        self.registry = registry if registry is not None else default_registry()
        self.timezone = timezone if timezone is not None else local_timezone()
        self.rng = rng if rng is not None else random.Random()
        self.cards = SqliteCardStore(database)
        self.attempts = SqliteAttemptLog(database)
        self.sessions = SqliteSessionLog(database)
        self.engine = LearningEngine.create(
            self.registry,
            self.cards,
            self.attempts,
            self.sessions,
            tzinfo=self.timezone,
            rng=self.rng,
            stats_config=stats_config,
        )
        self._audio = audio
        self._audio_lock = threading.Lock()

    @classmethod
    def open(
        cls, data_dir: Path | None = None, *, stats_config: StatsConfig | None = None
    ) -> Services:
        directory = data_dir if data_dir is not None else user_data_dir()
        database = Database.open(directory / DATABASE_NAME)
        log.info('progress database: %s', directory / DATABASE_NAME)
        return cls(database, stats_config=stats_config)

    @property
    def audio(self) -> AudioBackend:
        """The audio backend, started on first use (FluidSynth or silent)."""
        with self._audio_lock:
            if self._audio is None:
                from .audio.service import create_backend

                self._audio = create_backend()
            return self._audio

    def close(self) -> None:
        with self._audio_lock:
            if self._audio is not None:
                self._audio.close()
                self._audio = None
        self.database.close()
