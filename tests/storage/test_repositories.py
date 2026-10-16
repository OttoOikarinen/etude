# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract tests run against the SQLite stores and the in-memory fakes alike."""

from collections.abc import Callable
from datetime import timedelta, timezone
from typing import Any

import pytest
from tests.learning.fakes import FakeAttemptLog, FakeCardStore, FakeSessionLog, outcome, utc

from etude.learning.model import (
    Card,
    CardState,
    ItemId,
    Outcome,
    SessionMode,
    SessionSummary,
)
from etude.storage.db import Database
from etude.storage.repositories import (
    SqliteAttemptLog,
    SqliteCardStore,
    SqliteSessionLog,
    to_text,
)

T = utc(2026, 10, 15, 9)


def sqlite(kind: type) -> Callable[[], Any]:
    return lambda: kind(Database.memory())


card_stores = pytest.mark.parametrize(
    'make', [sqlite(SqliteCardStore), FakeCardStore], ids=['sqlite', 'fake']
)
attempt_logs = pytest.mark.parametrize(
    'make', [sqlite(SqliteAttemptLog), FakeAttemptLog], ids=['sqlite', 'fake']
)
session_logs = pytest.mark.parametrize(
    'make', [sqlite(SqliteSessionLog), FakeSessionLog], ids=['sqlite', 'fake']
)


# Cards


@card_stores
def test_card_round_trip(make: Callable[[], Any]) -> None:
    store = make()
    full = Card(
        item_id=ItemId('keysig.major.4s'),
        due=T + timedelta(days=3, microseconds=17),
        state=CardState.REVIEW,
        step=None,
        stability=12.345678,
        difficulty=4.5,
        last_review=T,
        reps=7,
        lapses=2,
    )
    bare = Card(ItemId('note.c4'), due=T)
    store.put(full)
    store.put(bare)
    assert store.get(full.item_id) == full
    assert store.get(bare.item_id) == bare
    assert store.get(ItemId('missing')) is None
    updated = Card(full.item_id, due=T, reps=8)
    store.put(updated)
    assert store.get(full.item_id) == updated


@card_stores
def test_due_cards_most_overdue_first(make: Callable[[], Any]) -> None:
    store = make()
    for name, hours in [('b.1', -1), ('a.1', -5), ('a_2', -3), ('A.3', -2), ('a.4', 2)]:
        store.put(Card(ItemId(name), due=T + timedelta(hours=hours)))
    store.put(Card(ItemId('a.5'), due=T))  # due exactly now
    assert [c.item_id for c in store.due(T, limit=10)] == ['a.1', 'a_2', 'A.3', 'b.1', 'a.5']
    assert [c.item_id for c in store.due(T, limit=2)] == ['a.1', 'a_2']
    # Prefixes are matched exactly: no case folding, no LIKE wildcards.
    assert [c.item_id for c in store.due(T, limit=10, prefixes=['a.'])] == ['a.1', 'a.5']
    assert [c.item_id for c in store.due(T, limit=10, prefixes=['a.', 'b.'])] == [
        'a.1',
        'b.1',
        'a.5',
    ]


@card_stores
def test_get_many(make: Callable[[], Any]) -> None:
    store = make()
    ids = [ItemId(f'item.{n}') for n in range(1200)]
    for item in ids[::2]:
        store.put(Card(item, due=T))
    found = store.get_many([*ids, ids[0]])
    assert set(found) == set(ids[::2])
    assert found[ids[0]] == Card(ids[0], due=T)
    assert store.get_many([]) == {}


def test_datetimes_are_stored_as_utc_text() -> None:
    db = Database.memory()
    store = SqliteCardStore(db)
    helsinki = timezone(timedelta(hours=3))
    store.put(Card(ItemId('x'), due=T.astimezone(helsinki)))
    row = db.connection.execute('SELECT due FROM cards').fetchone()
    assert row['due'] == '2026-10-15T09:00:00.000000+00:00'
    assert store.get(ItemId('x')).due.utcoffset() == timedelta(0)  # type: ignore[union-attr]
    assert store.all() == [Card(ItemId('x'), due=T)]


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError, match='timezone-aware'):
        to_text(T.replace(tzinfo=None))


# Attempts


@attempt_logs
def test_attempt_round_trip_and_recent(make: Callable[[], Any]) -> None:
    log = make()
    rich = Outcome(
        item_id=ItemId('dictation.1'),
        exercise_id='dictation',
        correct=True,
        response_ms=12_345,
        answered_at=T,
        hinted=True,
        score=0.85,
        given='C D E',
        expected='C D F',
    )
    log.add(rich, None)
    log.add(outcome('a', T + timedelta(seconds=2), exercise='x'), None)
    log.add(outcome('b', T + timedelta(seconds=1), exercise='y', correct=False), None)
    log.add(outcome('a', T + timedelta(seconds=2), exercise='x', correct=False), None)
    recent = log.recent()
    assert recent[0] == outcome('a', T + timedelta(seconds=2), exercise='x', correct=False)
    assert [o.item_id for o in recent] == ['a', 'a', 'b', 'dictation.1']
    assert recent[-1] == rich
    assert [o.item_id for o in log.recent(limit=2)] == ['a', 'a']
    assert [o.item_id for o in log.recent(exercise_id='y')] == ['b']
    assert [o.correct for o in log.recent(item_id=ItemId('a'))] == [False, True]
    assert log.recent(exercise_id='y', item_id=ItemId('a')) == []


@attempt_logs
def test_attempts_between_is_half_open(make: Callable[[], Any]) -> None:
    log = make()
    for minutes in (0, 10, 20, 30):
        log.add(outcome(f'i{minutes}', T + timedelta(minutes=minutes)), None)
    found = log.between(T + timedelta(minutes=10), T + timedelta(minutes=30))
    assert [o.item_id for o in found] == ['i10', 'i20']


def test_attempts_keep_their_session() -> None:
    db = Database.memory()
    sessions, attempts = SqliteSessionLog(db), SqliteAttemptLog(db)
    sid = sessions.start(SessionMode.EXERCISE, 'keys', T)
    attempts.add(outcome('a', T), sid)
    attempts.add(outcome('b', T), None)
    rows = db.connection.execute('SELECT session_id FROM attempts ORDER BY id').fetchall()
    assert [r['session_id'] for r in rows] == [sid, None]


# Sessions


@session_logs
def test_session_round_trip(make: Callable[[], Any]) -> None:
    log = make()
    first = log.start(SessionMode.EXERCISE, 'keys', T)
    second = log.start(SessionMode.DAILY_REVIEW, None, T + timedelta(hours=1))
    assert first != second
    summary = SessionSummary(
        total=20,
        correct=17,
        duration_ms=300_000,
        best_streak=9,
        personal_best=True,
        mistakes=(ItemId('a'), ItemId('b')),
    )
    log.finish(first, T + timedelta(minutes=5), summary)
    records = log.between(T, T + timedelta(days=1))
    assert [r.id for r in records] == [first, second]
    done, open_ = records
    assert (done.mode, done.exercise_id, done.started_at) == (SessionMode.EXERCISE, 'keys', T)
    assert done.finished_at == T + timedelta(minutes=5)
    assert done.summary == summary
    assert (open_.mode, open_.exercise_id, open_.finished_at, open_.summary) == (
        SessionMode.DAILY_REVIEW,
        None,
        None,
        None,
    )
    assert log.between(T + timedelta(minutes=1), T + timedelta(hours=1)) == []


def test_sqlite_session_get_and_unknown_finish() -> None:
    log = SqliteSessionLog(Database.memory())
    sid = log.start(SessionMode.DRILL_WEAK, None, T)
    record = log.get(sid)
    assert record is not None
    assert record.mode is SessionMode.DRILL_WEAK
    assert log.get(999) is None
    summary = SessionSummary(0, 0, 0, 0, False, ())
    with pytest.raises(KeyError):
        log.finish(999, T, summary)
