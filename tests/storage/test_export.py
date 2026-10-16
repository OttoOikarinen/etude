# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import json
from datetime import timedelta
from typing import Any

import pytest
from tests.learning.fakes import outcome, utc

from etude.learning.model import Card, CardState, ItemId, Outcome, SessionMode, SessionSummary
from etude.storage.db import Database
from etude.storage.export import FORMAT, FORMAT_VERSION, ImportFormatError, export_json, import_json
from etude.storage.repositories import SqliteAttemptLog, SqliteCardStore, SqliteSessionLog

T = utc(2026, 10, 15, 9)


def filled() -> Database:
    db = Database.memory()
    cards, attempts, sessions = SqliteCardStore(db), SqliteAttemptLog(db), SqliteSessionLog(db)
    cards.put(Card(ItemId('a'), T, CardState.REVIEW, None, 3.5, 6.1, T - timedelta(days=3), 4, 1))
    cards.put(Card(ItemId('b'), T))
    sid = sessions.start(SessionMode.EXERCISE, 'keys', T)
    attempts.add(
        Outcome(
            ItemId('a'), 'keys', True, 1500, T, hinted=True, score=0.9, given='x', expected='y'
        ),
        sid,
    )
    attempts.add(outcome('b', T + timedelta(seconds=5), correct=False), sid)
    sessions.finish(sid, T + timedelta(minutes=1), SessionSummary(2, 1, 60_000, 1, False, ('b',)))  # type: ignore[arg-type]
    sessions.start(SessionMode.DAILY_REVIEW, None, T + timedelta(hours=1))
    attempts.add(outcome('a', T + timedelta(hours=2)), None)
    return db


def test_export_format() -> None:
    data = export_json(filled())
    assert data['format'] == FORMAT
    assert data['version'] == FORMAT_VERSION
    assert [c['item_id'] for c in data['cards']] == ['a', 'b']
    assert data['attempts'][0]['hinted'] is True
    assert data['attempts'][1]['correct'] is False
    assert data['sessions'][0]['personal_best'] is False
    assert data['sessions'][1]['personal_best'] is None
    assert data['attempts'][0]['answered_at'] == '2026-10-15T09:00:00.000000+00:00'
    json.dumps(data)  # serialisable as is


def test_export_import_round_trip() -> None:
    source = filled()
    data = json.loads(json.dumps(export_json(source)))
    target = Database.memory()
    SqliteCardStore(target).put(Card(ItemId('stale'), T))
    import_json(target, data)
    assert export_json(target) == export_json(source)
    assert SqliteCardStore(target).get(ItemId('stale')) is None
    assert SqliteCardStore(target).get(ItemId('a')) == SqliteCardStore(source).get(ItemId('a'))
    assert SqliteAttemptLog(target).recent() == SqliteAttemptLog(source).recent()
    # New sessions continue after the imported ids.
    assert SqliteSessionLog(target).start(SessionMode.EXERCISE, None, T) == 3


def test_empty_round_trip() -> None:
    target = filled()
    import_json(target, export_json(Database.memory()))
    assert export_json(target)['cards'] == []


@pytest.mark.parametrize(
    'data',
    [
        {},
        {'format': 'something-else', 'version': 1},
        {'format': FORMAT, 'version': FORMAT_VERSION + 1},
        {'format': FORMAT, 'version': '1'},
        {'format': FORMAT, 'version': 1, 'cards': 'nope'},
        {'format': FORMAT, 'version': 1, 'cards': [{'item_id': 'x'}]},
        {'format': FORMAT, 'version': 1, 'cards': ['x']},
        {
            'format': FORMAT,
            'version': 1,
            'cards': [
                {
                    'item_id': 'x',
                    'due': '2026-10-15T09:00:00.000000+00:00',
                    'state': 9,
                    'step': 0,
                    'stability': None,
                    'difficulty': None,
                    'last_review': None,
                    'reps': 0,
                    'lapses': 0,
                }
            ],
        },
    ],
    ids=[
        'empty',
        'wrong-format',
        'too-new',
        'bad-version',
        'not-a-list',
        'missing-column',
        'not-an-object',
        'check-violation',
    ],
)
def test_invalid_imports_change_nothing(data: dict[str, Any]) -> None:
    db = filled()
    before = export_json(db)
    with pytest.raises(ImportFormatError):
        import_json(db, data)
    assert export_json(db) == before
