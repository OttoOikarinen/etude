# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""SMuFL font metadata (Bravura).

Layout needs glyph bounding boxes, anchors (stem attachment points) and
the font's engraving defaults (line thicknesses), all measured in staff
spaces. They come from ``fonts/Bravura.json``.

Glyph names map to code points through :data:`CODEPOINTS`, a table of the
glyphs Etude uses, taken from the SMuFL specification. (The specification's
``glyphnames.json`` carries no explicit licence, so it is not bundled.)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CODEPOINTS: dict[str, str] = {
    'gClef': '\uE050',
    'fClef': '\uE062',
    'cClef': '\uE05C',
    'noteheadBlack': '\uE0A4',
}
"""SMuFL glyph name → code point. Extend as layout needs more glyphs."""


@dataclass(frozen=True, slots=True)
class GlyphInfo:
    name: str
    codepoint: str
    """The glyph as a one-character string."""
    bbox_sw: tuple[float, float]
    bbox_ne: tuple[float, float]
    anchors: dict[str, tuple[float, float]]


class FontMetrics:
    """Glyph metrics and engraving defaults, in staff spaces."""

    @classmethod
    def load(cls, metadata: Path) -> FontMetrics:
        raise NotImplementedError

    @classmethod
    def bravura(cls) -> FontMetrics:
        """Load the bundled Bravura metadata from the data directory (cached)."""
        raise NotImplementedError

    def glyph(self, name: str) -> GlyphInfo:
        raise NotImplementedError

    def engraving_default(self, key: str) -> float:
        """E.g. ``'staffLineThickness'``, ``'stemThickness'``, ``'legerLineExtension'``."""
        raise NotImplementedError
