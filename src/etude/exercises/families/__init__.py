# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Exercise families.

Each module defines one or more exercises and exposes them as
``EXERCISES: tuple[ExerciseDefinition, ...]``. Modules are discovered by
:func:`etude.exercises.registry.default_registry`; see docs/ADDING_EXERCISES.md.
"""
