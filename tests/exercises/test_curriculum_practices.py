# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The curriculum only names exercises and settings that exist, and every
practice covers some items."""

from __future__ import annotations

import pytest

from etude.content.library import ContentLibrary, content_dir
from etude.exercises.base import ChoiceSetting, IntSetting, MultiChoiceSetting
from etude.exercises.registry import default_registry
from etude.exercises.settings import SettingError, coerce

LIBRARY = ContentLibrary.load(content_dir())
PRACTICES = [
    (unit.id, practice)
    for level in LIBRARY.curriculum.levels
    for unit in level.units
    for practice in unit.practices
]


@pytest.mark.parametrize(
    ('unit_id', 'practice'), PRACTICES, ids=[f'{u}:{p.exercise_id}' for u, p in PRACTICES]
)
def test_practices_resolve(unit_id: str, practice) -> None:
    registry = default_registry()
    definition = registry.get(practice.exercise_id)
    settings = {**definition.default_settings(), **coerce(definition, practice.settings)}
    assert definition.items(settings), f'{unit_id}: {practice.exercise_id} covers no items'


def test_coerce_types() -> None:
    definition = default_registry().get('note-naming')
    values = coerce(
        definition,
        {'clefs': 'treble alto', 'ledger-lines': '2', 'accidentals': 'true', 'octave': 'false'},
    )
    assert values == {
        'clefs': ('treble', 'alto'),
        'ledger-lines': 2,
        'accidentals': True,
        'octave': False,
    }


@pytest.mark.parametrize(
    ('raw', 'message'),
    [
        ({'colour': 'red'}, 'does not exist'),
        ({'accidentals': 'yes'}, 'true or false'),
        ({'ledger-lines': 'two'}, 'a number'),
        ({'ledger-lines': '9'}, 'must be'),
        ({'clefs': 'treble soprano'}, 'no options'),
        ({'clefs': ''}, 'at least'),
    ],
)
def test_coerce_rejects(raw: dict[str, str], message: str) -> None:
    with pytest.raises(SettingError, match=message):
        coerce(default_registry().get('note-naming'), raw)


def test_coerce_choice() -> None:
    definition = default_registry().get('keysig')
    assert any(isinstance(s, ChoiceSetting) for s in definition.settings)
    assert coerce(definition, {'mode': 'minor'}) == {'mode': 'minor'}
    with pytest.raises(SettingError):
        coerce(definition, {'mode': 'dorian'})
    assert any(isinstance(s, IntSetting | MultiChoiceSetting) for s in definition.settings)
