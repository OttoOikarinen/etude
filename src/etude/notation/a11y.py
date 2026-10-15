# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Text descriptions of notation for screen readers."""

from __future__ import annotations

from collections.abc import Callable

from ..core import Pitch
from .spec import Figure


def describe(figure: Figure, name_pitch: Callable[[Pitch], str] = str) -> str:
    """Describe a figure in words, e.g. "Treble staff, four sharps. Two notes: G4, E5."

    Uses ``figure.description`` when it is set. ``name_pitch`` lets the UI
    apply the user's note naming convention. Must never reveal the answer
    of a question that asks for exactly that information: exercises set
    ``description`` explicitly in such cases.
    """
    raise NotImplementedError
