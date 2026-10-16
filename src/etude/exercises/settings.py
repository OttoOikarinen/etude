# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Turn the text settings of curriculum units into an exercise's setting values."""

from __future__ import annotations

from collections.abc import Mapping

from .base import (
    BoolSetting,
    ChoiceSetting,
    ExerciseDefinition,
    IntSetting,
    MultiChoiceSetting,
)


class SettingError(ValueError):
    """A curriculum names a setting the exercise does not have, or a bad value."""


def coerce(definition: ExerciseDefinition, raw: Mapping[str, str]) -> dict[str, object]:
    """``{'clefs': 'treble bass', 'ledger-lines': '1'}`` → ``{'clefs': ('treble', 'bass'),
    'ledger-lines': 1}``, checked against the exercise's settings."""
    settings = {s.key: s for s in definition.settings}
    values: dict[str, object] = {}
    for key, text in raw.items():
        setting = settings.get(key)
        where = f'{definition.id}: setting {key!r}'
        if setting is None:
            raise SettingError(f'{where} does not exist')
        if isinstance(setting, BoolSetting):
            if text not in ('true', 'false'):
                raise SettingError(f'{where} must be true or false, not {text!r}')
            values[key] = text == 'true'
        elif isinstance(setting, IntSetting):
            try:
                number = int(text)
            except ValueError:
                raise SettingError(f'{where} must be a number, not {text!r}') from None
            if not setting.minimum <= number <= setting.maximum:
                raise SettingError(
                    f'{where} must be {setting.minimum}–{setting.maximum}, not {number}'
                )
            values[key] = number
        elif isinstance(setting, ChoiceSetting):
            if text not in {o.key for o in setting.options}:
                raise SettingError(f'{where} has no option {text!r}')
            values[key] = text
        elif isinstance(setting, MultiChoiceSetting):
            chosen = tuple(text.split())
            unknown = set(chosen) - {o.key for o in setting.options}
            if unknown:
                raise SettingError(f'{where} has no options {sorted(unknown)}')
            if len(chosen) < setting.minimum:
                raise SettingError(f'{where} needs at least {setting.minimum} options')
            values[key] = chosen
    return values
