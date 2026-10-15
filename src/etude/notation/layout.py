# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Engraving: turn a :data:`~etude.notation.spec.Figure` into a display list."""

from __future__ import annotations

from .displaylist import DisplayList
from .smufl import FontMetrics
from .spec import Figure


def layout(figure: Figure, metrics: FontMetrics, *, width: float | None = None) -> DisplayList:
    """Lay out a staff or system.

    ``width`` (in staff spaces) stretches the events to fill the given
    width; when ``None`` the natural width is used. The result is
    deterministic so it can be golden-tested.
    """
    raise NotImplementedError
