# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Registry of exercise definitions; implements the learning engine's
:class:`~etude.learning.ports.ItemCatalog`."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterator, Mapping, Sequence
from functools import cache

from ..learning.model import ItemId
from . import families
from .base import ExerciseDefinition, Family


class ExerciseRegistry:
    def __init__(self, definitions: Sequence[ExerciseDefinition] = ()) -> None:
        self._definitions: dict[str, ExerciseDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: ExerciseDefinition) -> None:
        if definition.id in self._definitions:
            raise ValueError(f'exercise {definition.id!r} is already registered')
        for other in self._definitions.values():
            if definition.item_prefix.startswith(other.item_prefix) or other.item_prefix.startswith(
                definition.item_prefix
            ):
                raise ValueError(
                    f'item prefix {definition.item_prefix!r} of {definition.id!r} overlaps '
                    f'{other.item_prefix!r} of {other.id!r}'
                )
        self._definitions[definition.id] = definition

    def get(self, exercise_id: str) -> ExerciseDefinition:
        return self._definitions[exercise_id]

    def __iter__(self) -> Iterator[ExerciseDefinition]:
        return iter(self._definitions.values())

    def __len__(self) -> int:
        return len(self._definitions)

    def by_family(self, family: Family) -> list[ExerciseDefinition]:
        return [d for d in self if d.family is family]

    # ItemCatalog

    def exercise_ids(self) -> Sequence[str]:
        return list(self._definitions)

    def items(self, exercise_id: str, settings: Mapping[str, object]) -> Sequence[ItemId]:
        definition = self.get(exercise_id)
        merged = {**definition.default_settings(), **settings}
        return definition.items(merged)

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        """The owning exercise's confusable items (the session builder's hook)."""
        try:
            return self.get(self.exercise_for(item_id)).confusables(item_id)
        except KeyError:
            return ()

    def exercise_for(self, item_id: ItemId) -> str:
        for definition in self:
            if item_id.startswith(definition.item_prefix):
                return definition.id
        raise KeyError(item_id)


@cache
def default_registry() -> ExerciseRegistry:
    """All exercises of the application.

    Every module in :mod:`etude.exercises.families` exposes
    ``EXERCISES: tuple[ExerciseDefinition, ...]``; modules are discovered
    automatically, so adding an exercise never touches a shared list.
    """
    registry = ExerciseRegistry()
    for module_info in sorted(pkgutil.iter_modules(families.__path__), key=lambda m: m.name):
        module = importlib.import_module(f'{families.__name__}.{module_info.name}')
        for definition in getattr(module, 'EXERCISES', ()):
            registry.register(definition)
    return registry
