# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Schema migrations, applied in order.

``MIGRATIONS[n]`` upgrades a database from ``PRAGMA user_version`` *n* to
*n + 1*. Never edit a released migration: learners' databases have
already run it. Append a new one instead.

Datetimes are ISO 8601 UTC text with microseconds
(``2026-10-15T09:30:00.000000+00:00``), so text order is time order and
range queries can use the indexes.
"""

from __future__ import annotations

from typing import Final

_V1: Final = """
CREATE TABLE cards (
    item_id     TEXT PRIMARY KEY,
    due         TEXT NOT NULL,
    state       INTEGER NOT NULL CHECK (state IN (1, 2, 3)),
    step        INTEGER,
    stability   REAL,
    difficulty  REAL,
    last_review TEXT,
    reps        INTEGER NOT NULL DEFAULT 0 CHECK (reps >= 0),
    lapses      INTEGER NOT NULL DEFAULT 0 CHECK (lapses >= 0)
) STRICT;

-- Due cards, most overdue first (CardStore.due).
CREATE INDEX cards_due ON cards (due);

CREATE TABLE sessions (
    id            INTEGER PRIMARY KEY,
    mode          TEXT NOT NULL,
    exercise_id   TEXT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    total         INTEGER,
    correct       INTEGER,
    duration_ms   INTEGER,
    best_streak   INTEGER,
    personal_best INTEGER CHECK (personal_best IN (0, 1)),
    mistakes      TEXT  -- JSON array of item ids
) STRICT;

-- Time practised and session counts per period; personal bests per exercise.
CREATE INDEX sessions_started_at ON sessions (started_at);

CREATE TABLE attempts (
    id          INTEGER PRIMARY KEY,
    session_id  INTEGER REFERENCES sessions (id) ON DELETE SET NULL,
    exercise_id TEXT NOT NULL,
    item_id     TEXT NOT NULL,
    correct     INTEGER NOT NULL CHECK (correct IN (0, 1)),
    score       REAL CHECK (score BETWEEN 0.0 AND 1.0),
    hinted      INTEGER NOT NULL DEFAULT 0 CHECK (hinted IN (0, 1)),
    response_ms INTEGER NOT NULL CHECK (response_ms >= 0),
    given       TEXT NOT NULL DEFAULT '',
    expected    TEXT NOT NULL DEFAULT '',
    answered_at TEXT NOT NULL
) STRICT;

-- Answers per period (streaks, accuracy, questions per day).
CREATE INDEX attempts_answered_at ON attempts (answered_at);
-- Rolling accuracy and speed percentiles of one exercise.
CREATE INDEX attempts_exercise ON attempts (exercise_id, answered_at);
-- Item history (mastery, weakest items).
CREATE INDEX attempts_item ON attempts (item_id, answered_at);
CREATE INDEX attempts_session ON attempts (session_id);
"""

MIGRATIONS: Final[tuple[str, ...]] = (_V1,)

SCHEMA_VERSION: Final = len(MIGRATIONS)
