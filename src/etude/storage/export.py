# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Export and import of all learning progress as JSON-compatible data.

The format is independent of the SQLite schema and has its own version,
so that a database migration does not change what an exported file means.
Importing replaces all existing progress.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any, Final

from .db import Database

FORMAT: Final = 'etude-progress'
FORMAT_VERSION: Final = 1

_TABLES: Final = {
    'cards': (
        'item_id',
        'due',
        'state',
        'step',
        'stability',
        'difficulty',
        'last_review',
        'reps',
        'lapses',
    ),
    'sessions': (
        'id',
        'mode',
        'exercise_id',
        'started_at',
        'finished_at',
        'total',
        'correct',
        'duration_ms',
        'best_streak',
        'personal_best',
        'mistakes',
    ),
    'attempts': (
        'id',
        'session_id',
        'exercise_id',
        'item_id',
        'correct',
        'score',
        'hinted',
        'response_ms',
        'given',
        'expected',
        'answered_at',
    ),
}
_BOOLEANS: Final = frozenset({'correct', 'hinted', 'personal_best'})


class ImportFormatError(ValueError):
    """The data is not an Etude progress export this version understands."""


def export_json(db: Database) -> dict[str, Any]:
    """All cards, sessions and attempts, ready for :func:`json.dump`.

    Datetimes stay ISO 8601 UTC text; flags become JSON booleans.
    """
    data: dict[str, Any] = {'format': FORMAT, 'version': FORMAT_VERSION}
    for table, columns in _TABLES.items():
        order = 'item_id' if table == 'cards' else 'id'
        rows = db.connection.execute(f'SELECT {", ".join(columns)} FROM {table} ORDER BY {order}')
        data[table] = [
            {
                c: (bool(row[c]) if c in _BOOLEANS and row[c] is not None else row[c])
                for c in columns
            }
            for row in rows
        ]
    return data


def import_json(db: Database, data: Mapping[str, Any]) -> None:
    """Replace all progress in ``db`` with an export made by :func:`export_json`.

    The import is atomic: on any error the database is left unchanged.
    """
    if data.get('format') != FORMAT:
        raise ImportFormatError('not an Etude progress export')
    version = data.get('version')
    if not isinstance(version, int) or not 1 <= version <= FORMAT_VERSION:
        raise ImportFormatError(f'unsupported progress export version {version!r}')
    with db.transaction() as connection:
        # Children first, for the foreign key from attempts to sessions.
        for table in ('attempts', 'sessions', 'cards'):
            connection.execute(f'DELETE FROM {table}')
        for table in ('cards', 'sessions', 'attempts'):
            columns = _TABLES[table]
            rows = data.get(table, [])
            if not isinstance(rows, list):
                raise ImportFormatError(f'{table!r} must be a list')
            try:
                connection.executemany(
                    f'INSERT INTO {table} ({", ".join(columns)}) '
                    f'VALUES ({", ".join("?" * len(columns))})',
                    [tuple(_column(row, c) for c in columns) for row in rows],
                )
            except (KeyError, TypeError, sqlite3.IntegrityError) as error:
                raise ImportFormatError(f'malformed {table!r} entry: {error}') from error


def _column(row: Mapping[str, Any], column: str) -> object:
    value = row[column]
    if column in _BOOLEANS and isinstance(value, bool):
        return int(value)
    return value
