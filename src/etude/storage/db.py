# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The SQLite connection, its settings and schema upgrades."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from os import PathLike
from pathlib import Path
from types import TracebackType
from typing import Self

from .migrations import MIGRATIONS


class SchemaTooNewError(RuntimeError):
    """The database was written by a newer Etude; opening it could lose data."""


class Database:
    """One connection to the learning database.

    The connection runs in autocommit mode; :meth:`transaction` groups
    statements. Write-ahead logging keeps reads (the progress page) from
    blocking writes (recording an answer), and foreign keys are enforced.
    """

    def __init__(
        self, connection: sqlite3.Connection, migrations: Sequence[str] = MIGRATIONS
    ) -> None:
        self.connection = connection
        self._depth = 0
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys = ON')
        connection.execute('PRAGMA journal_mode = WAL')
        connection.execute('PRAGMA synchronous = NORMAL')
        connection.execute('PRAGMA busy_timeout = 5000')
        self.migrate(migrations)

    @classmethod
    def open(cls, path: str | PathLike[str]) -> Self:
        """Open (creating if needed) the database at ``path`` and upgrade its schema."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        return cls(sqlite3.connect(path, autocommit=True))

    @classmethod
    def memory(cls) -> Self:
        """A private in-memory database, for tests."""
        return cls(sqlite3.connect(':memory:', autocommit=True))

    @property
    def schema_version(self) -> int:
        version: int = self.connection.execute('PRAGMA user_version').fetchone()[0]
        return version

    def migrate(self, migrations: Sequence[str] = MIGRATIONS) -> None:
        """Apply the migrations the database has not run yet, each in its own transaction."""
        version = self.schema_version
        if version > len(migrations):
            raise SchemaTooNewError(
                f'database schema {version} is newer than this version of Etude '
                f'(schema {len(migrations)})'
            )
        for number, script in enumerate(migrations[version:], start=version + 1):
            try:
                self.connection.executescript(
                    f'BEGIN IMMEDIATE;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;'
                )
            except BaseException:
                if self.connection.in_transaction:
                    self.connection.execute('ROLLBACK')
                raise

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run the block atomically; nested blocks join the outer transaction."""
        if self._depth:
            self._depth += 1
            try:
                yield self.connection
            finally:
                self._depth -= 1
            return
        self.connection.execute('BEGIN IMMEDIATE')
        self._depth = 1
        try:
            yield self.connection
        except BaseException:
            self.connection.execute('ROLLBACK')
            raise
        else:
            self.connection.execute('COMMIT')
        finally:
            self._depth = 0

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
