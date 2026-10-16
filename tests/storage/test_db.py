# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from etude.storage.db import Database, SchemaTooNewError
from etude.storage.migrations import MIGRATIONS, SCHEMA_VERSION


@pytest.fixture
def connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(':memory:', autocommit=True)
    yield connection
    connection.close()


def tables(db: Database) -> set[str]:
    rows = db.connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {r['name'] for r in rows}


def indexes(db: Database) -> set[str]:
    rows = db.connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL"
    )
    return {r['name'] for r in rows}


def test_an_empty_database_is_migrated_to_the_latest_schema() -> None:
    db = Database.memory()
    assert db.schema_version == SCHEMA_VERSION == len(MIGRATIONS)
    assert tables(db) == {'cards', 'attempts', 'sessions'}
    assert {'cards_due', 'attempts_answered_at', 'attempts_exercise', 'attempts_item'} <= indexes(
        db
    )


def test_open_creates_the_file_and_directories_in_wal_mode(tmp_path: Path) -> None:
    path = tmp_path / 'etude' / 'etude.db'
    with Database.open(path) as db:
        assert db.connection.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        assert db.connection.execute('PRAGMA foreign_keys').fetchone()[0] == 1
    assert path.exists()


def test_reopening_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / 'etude.db'
    with Database.open(path) as db:
        db.connection.execute(
            "INSERT INTO sessions (mode, started_at) VALUES ('exercise', '2026-10-15')"
        )
    with Database.open(path) as db:
        assert db.schema_version == SCHEMA_VERSION
        db.migrate()
        assert db.connection.execute('SELECT count(*) FROM sessions').fetchone()[0] == 1


def test_migrations_apply_in_order_from_any_version(connection: sqlite3.Connection) -> None:
    steps = (
        'CREATE TABLE a (x INTEGER);',
        'ALTER TABLE a ADD COLUMN y INTEGER;',
        'CREATE TABLE b (z INTEGER);',
    )
    db = Database(connection, steps[:1])
    assert db.schema_version == 1
    db.migrate(steps)
    assert db.schema_version == 3
    columns = [r['name'] for r in connection.execute('PRAGMA table_info(a)')]
    assert columns == ['x', 'y']


def test_a_failing_migration_is_rolled_back(connection: sqlite3.Connection) -> None:
    db = Database(connection, ('CREATE TABLE a (x INTEGER);',))
    broken = ('CREATE TABLE a (x INTEGER);', 'CREATE TABLE b (x INTEGER); SELECT * FROM missing;')
    with pytest.raises(sqlite3.OperationalError):
        db.migrate(broken)
    assert db.schema_version == 1
    assert 'b' not in tables(db)
    assert not connection.in_transaction


def test_a_database_from_a_newer_version_is_refused(connection: sqlite3.Connection) -> None:
    connection.execute(f'PRAGMA user_version = {SCHEMA_VERSION + 1}')
    with pytest.raises(SchemaTooNewError):
        Database(connection)


def test_transactions_commit_and_roll_back() -> None:
    db = Database.memory()
    insert = "INSERT INTO sessions (mode, started_at) VALUES ('exercise', '2026-10-15')"
    with db.transaction() as connection:
        connection.execute(insert)
        with db.transaction():  # nested: joins the outer transaction
            connection.execute(insert)

    def fail() -> None:
        with db.transaction() as connection:
            connection.execute(insert)
            raise RuntimeError

    with pytest.raises(RuntimeError):
        fail()
    assert db.connection.execute('SELECT count(*) FROM sessions').fetchone()[0] == 2


def test_foreign_keys_are_enforced() -> None:
    db = Database.memory()
    with pytest.raises(sqlite3.IntegrityError):
        db.connection.execute(
            'INSERT INTO attempts (session_id, exercise_id, item_id, correct, response_ms, '
            "answered_at) VALUES (99, 'ex', 'i', 1, 10, '2026-10-15')"
        )
