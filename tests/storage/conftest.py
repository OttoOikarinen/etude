# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

from collections.abc import Iterator

import pytest

from etude.storage.db import Database


@pytest.fixture(autouse=True)
def close_memory_databases(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Close every ``Database.memory()`` a test opens, so connections do not leak."""
    opened: list[Database] = []
    original = Database.memory.__func__  # type: ignore[attr-defined]

    def memory(cls: type[Database]) -> Database:
        db: Database = original(cls)
        opened.append(db)
        return db

    monkeypatch.setattr(Database, 'memory', classmethod(memory))
    yield
    for db in opened:
        db.close()
