# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""How to draw it: the output of layout, in staff-space units.

Coordinates are measured in *staff spaces* (the distance between two
staff lines), with x growing to the right and y growing downwards. The
widget multiplies by its staff-space size in pixels, so "Large notation"
is a single scale factor. Glyphs are named with SMuFL names
(``'gClef'``, ``'noteheadBlack'``, ``'accidentalSharp'`` …) and drawn
with the Bravura font.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .spec import Clef, Ink


class Align(Enum):
    START = 'start'
    CENTER = 'center'
    END = 'end'


@dataclass(frozen=True, slots=True)
class GlyphItem:
    """A SMuFL glyph whose origin (baseline-left in SMuFL terms) sits at (x, y)."""

    glyph: str
    x: float
    y: float
    ink: Ink = Ink.FOREGROUND
    scale: float = 1.0
    """Size relative to the normal glyph size (one em = four staff spaces); braces
    that span several staves are drawn larger."""


@dataclass(frozen=True, slots=True)
class LineItem:
    """A straight line with butt caps; used for staff lines, ledger lines, stems,
    barlines and brackets. ``thickness`` is centred on the line."""

    x1: float
    y1: float
    x2: float
    y2: float
    thickness: float
    ink: Ink = Ink.FOREGROUND


@dataclass(frozen=True, slots=True)
class BeamItem:
    """A filled parallelogram between two stem ends; ``thickness`` is vertical.

    The parallelogram is centred on the line from (x1, y1) to (x2, y2).
    """

    x1: float
    y1: float
    x2: float
    y2: float
    thickness: float
    ink: Ink = Ink.FOREGROUND


@dataclass(frozen=True, slots=True)
class CircleItem:
    """A filled translucent circle, used for highlight halos."""

    cx: float
    cy: float
    radius: float
    ink: Ink = Ink.ACCENT
    alpha: float = 0.16


@dataclass(frozen=True, slots=True)
class CurveItem:
    """A tie: a filled crescent from (x1, y1) to (x2, y2).

    ``bulge`` is the vertical offset of the curve's middle from the chord
    between the end points (negative arches upwards). ``thickness`` is the
    width at the middle; the ends taper to ``end_thickness``.
    """

    x1: float
    y1: float
    x2: float
    y2: float
    bulge: float
    thickness: float
    end_thickness: float = 0.1
    ink: Ink = Ink.FOREGROUND


@dataclass(frozen=True, slots=True)
class TextItem:
    """UI text (labels under notes, bracket labels); drawn with the UI font.

    ``y`` is the text baseline; ``align`` says which edge (or the centre) sits at ``x``.
    """

    text: str
    x: float
    y: float
    size: float = 1.0
    """Font size in staff spaces."""
    align: Align = Align.CENTER
    bold: bool = False
    ink: Ink = Ink.DIM


Item = GlyphItem | LineItem | BeamItem | CircleItem | CurveItem | TextItem


@dataclass(frozen=True, slots=True)
class HitRegion:
    """A clickable rectangle for one notehead (``head`` set) or a whole event."""

    staff: int
    event: int
    head: int | None
    x: float
    y: float
    width: float
    height: float

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x <= self.x + self.width and self.y <= y <= self.y + self.height


@dataclass(frozen=True, slots=True)
class StaffGeometry:
    """Where a staff ended up, so input widgets can map y back to a pitch."""

    clef: Clef
    top: float
    """y of the top staff line."""
    lines: int = 5

    def position_at(self, y: float) -> int:
        """Nearest staff position (0 = bottom line) for a y coordinate."""
        bottom = self.top + (self.lines - 1)
        return round((bottom - y) * 2)

    def y_of(self, position: int) -> float:
        return self.top + (self.lines - 1) - position / 2


@dataclass(frozen=True, slots=True)
class DisplayList:
    items: tuple[Item, ...]
    width: float
    height: float
    staves: tuple[StaffGeometry, ...]
    hit_regions: tuple[HitRegion, ...] = ()
    event_x: tuple[tuple[float, ...], ...] = ()
    """Centre x of every event, per staff; used for playback cursors and staff input."""

    def hit_test(self, x: float, y: float) -> HitRegion | None:
        """Return the topmost region at (x, y); heads win over whole events."""
        best: HitRegion | None = None
        for region in self.hit_regions:
            if region.contains(x, y) and (best is None or region.head is not None):
                best = region
        return best
