# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""SQLite implementations of the :mod:`etude.learning.ports` stores."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from ..learning.model import (
    Card,
    CardState,
    ItemId,
    Outcome,
    SessionMode,
    SessionRecord,
    SessionSummary,
)
from .db import Database


def to_text(moment: datetime) -> str:
    """ISO 8601 UTC with a fixed width, so that text order is time order."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f'datetime {moment!r} is not timezone-aware')
    return moment.astimezone(UTC).isoformat(timespec='microseconds')


def from_text(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


def _optional_time(text: str | None) -> datetime | None:
    return None if text is None else from_text(text)


_CARD_COLUMNS = 'item_id, due, state, step, stability, difficulty, last_review, reps, lapses'


def card_from_row(row: sqlite3.Row) -> Card:
    return Card(
        item_id=ItemId(row['item_id']),
        due=from_text(row['due']),
        state=CardState(row['state']),
        step=row['step'],
        stability=row['stability'],
        difficulty=row['difficulty'],
        last_review=_optional_time(row['last_review']),
        reps=row['reps'],
        lapses=row['lapses'],
    )


def card_to_row(card: Card) -> tuple[object, ...]:
    return (
        card.item_id,
        to_text(card.due),
        int(card.state),
        card.step,
        card.stability,
        card.difficulty,
        None if card.last_review is None else to_text(card.last_review),
        card.reps,
        card.lapses,
    )


class SqliteCardStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get(self, item_id: ItemId) -> Card | None:
        row = self._db.connection.execute(
            f'SELECT {_CARD_COLUMNS} FROM cards WHERE item_id = ?', (item_id,)
        ).fetchone()
        return None if row is None else card_from_row(row)

    def put(self, card: Card) -> None:
        self._db.connection.execute(
            f'INSERT OR REPLACE INTO cards ({_CARD_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            card_to_row(card),
        )

    def due(self, now: datetime, *, limit: int, prefixes: Sequence[str] = ()) -> list[Card]:
        sql = f'SELECT {_CARD_COLUMNS} FROM cards WHERE due <= ?'
        params: list[object] = [to_text(now)]
        if prefixes:
            # substr() instead of LIKE: LIKE ignores case and treats _ and % as wildcards.
            sql += ' AND (' + ' OR '.join('substr(item_id, 1, ?) = ?' for _ in prefixes) + ')'
            for prefix in prefixes:
                params += [len(prefix), prefix]
        sql += ' ORDER BY due, item_id LIMIT ?'
        params.append(limit)
        return [card_from_row(r) for r in self._db.connection.execute(sql, params)]

    def get_many(self, item_ids: Iterable[ItemId]) -> dict[ItemId, Card]:
        ids = list(dict.fromkeys(item_ids))
        cards: dict[ItemId, Card] = {}
        # Stay well below SQLite's limit on the number of parameters.
        for start in range(0, len(ids), 500):
            chunk = ids[start : start + 500]
            marks = ', '.join('?' * len(chunk))
            for row in self._db.connection.execute(
                f'SELECT {_CARD_COLUMNS} FROM cards WHERE item_id IN ({marks})', chunk
            ):
                card = card_from_row(row)
                cards[card.item_id] = card
        return cards

    def all(self) -> list[Card]:
        return [
            card_from_row(r)
            for r in self._db.connection.execute(
                f'SELECT {_CARD_COLUMNS} FROM cards ORDER BY item_id'
            )
        ]


_ATTEMPT_COLUMNS = (
    'exercise_id, item_id, correct, score, hinted, response_ms, given, expected, answered_at'
)


def outcome_from_row(row: sqlite3.Row) -> Outcome:
    return Outcome(
        item_id=ItemId(row['item_id']),
        exercise_id=row['exercise_id'],
        correct=bool(row['correct']),
        response_ms=row['response_ms'],
        answered_at=from_text(row['answered_at']),
        hinted=bool(row['hinted']),
        score=row['score'],
        given=row['given'],
        expected=row['expected'],
    )


class SqliteAttemptLog:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, outcome: Outcome, session_id: int | None) -> None:
        self._db.connection.execute(
            f'INSERT INTO attempts (session_id, {_ATTEMPT_COLUMNS}) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (
                session_id,
                outcome.exercise_id,
                outcome.item_id,
                int(outcome.correct),
                outcome.score,
                int(outcome.hinted),
                outcome.response_ms,
                outcome.given,
                outcome.expected,
                to_text(outcome.answered_at),
            ),
        )

    def recent(
        self,
        *,
        exercise_id: str | None = None,
        item_id: ItemId | None = None,
        limit: int = 50,
    ) -> list[Outcome]:
        conditions = []
        params: list[object] = []
        if exercise_id is not None:
            conditions.append('exercise_id = ?')
            params.append(exercise_id)
        if item_id is not None:
            conditions.append('item_id = ?')
            params.append(item_id)
        where = f'WHERE {" AND ".join(conditions)} ' if conditions else ''
        params.append(limit)
        rows = self._db.connection.execute(
            f'SELECT {_ATTEMPT_COLUMNS} FROM attempts {where}'
            'ORDER BY answered_at DESC, id DESC LIMIT ?',
            params,
        )
        return [outcome_from_row(r) for r in rows]

    def between(self, start: datetime, end: datetime) -> list[Outcome]:
        """Answers given in ``[start, end)``, oldest first."""
        rows = self._db.connection.execute(
            f'SELECT {_ATTEMPT_COLUMNS} FROM attempts '
            'WHERE answered_at >= ? AND answered_at < ? ORDER BY answered_at, id',
            (to_text(start), to_text(end)),
        )
        return [outcome_from_row(r) for r in rows]


_SESSION_COLUMNS = (
    'id, mode, exercise_id, started_at, finished_at, '
    'total, correct, duration_ms, best_streak, personal_best, mistakes'
)


def session_from_row(row: sqlite3.Row) -> SessionRecord:
    summary = None
    if row['total'] is not None:
        summary = SessionSummary(
            total=row['total'],
            correct=row['correct'],
            duration_ms=row['duration_ms'],
            best_streak=row['best_streak'],
            personal_best=bool(row['personal_best']),
            mistakes=tuple(ItemId(i) for i in json.loads(row['mistakes'])),
        )
    return SessionRecord(
        id=row['id'],
        mode=SessionMode(row['mode']),
        exercise_id=row['exercise_id'],
        started_at=from_text(row['started_at']),
        finished_at=_optional_time(row['finished_at']),
        summary=summary,
    )


class SqliteSessionLog:
    def __init__(self, db: Database) -> None:
        self._db = db

    def start(self, mode: SessionMode, exercise_id: str | None, now: datetime) -> int:
        cursor = self._db.connection.execute(
            'INSERT INTO sessions (mode, exercise_id, started_at) VALUES (?, ?, ?)',
            (mode.value, exercise_id, to_text(now)),
        )
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def finish(self, session_id: int, now: datetime, summary: SessionSummary) -> None:
        cursor = self._db.connection.execute(
            'UPDATE sessions SET finished_at = ?, total = ?, correct = ?, duration_ms = ?, '
            'best_streak = ?, personal_best = ?, mistakes = ? WHERE id = ?',
            (
                to_text(now),
                summary.total,
                summary.correct,
                summary.duration_ms,
                summary.best_streak,
                int(summary.personal_best),
                json.dumps(list(summary.mistakes)),
                session_id,
            ),
        )
        if cursor.rowcount == 0:
            raise KeyError(session_id)

    def get(self, session_id: int) -> SessionRecord | None:
        row = self._db.connection.execute(
            f'SELECT {_SESSION_COLUMNS} FROM sessions WHERE id = ?', (session_id,)
        ).fetchone()
        return None if row is None else session_from_row(row)

    def between(self, start: datetime, end: datetime) -> list[SessionRecord]:
        rows = self._db.connection.execute(
            f'SELECT {_SESSION_COLUMNS} FROM sessions '
            'WHERE started_at >= ? AND started_at < ? ORDER BY started_at, id',
            (to_text(start), to_text(end)),
        )
        return [session_from_row(r) for r in rows]
