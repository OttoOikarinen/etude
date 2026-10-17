# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""SMuFL font metadata (Bravura).

Layout needs glyph bounding boxes, anchors (stem attachment points) and
the font's engraving defaults (line thicknesses), all measured in staff
spaces. They come from ``fonts/Bravura.json``.

Glyph names map to code points through :data:`CODEPOINTS`, a table of the
glyphs Etude uses, taken from the SMuFL specification. (The specification's
``glyphnames.json`` carries no explicit licence, so it is not bundled.)

SMuFL measures y upwards from the glyph origin; :class:`GlyphInfo` keeps
that convention, exactly as the metadata file does. Layout flips the sign
when it converts to display-list coordinates, where y grows downwards.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from ..paths import data_file

CODEPOINTS: dict[str, str] = {
    # Staff brackets and dividers
    'brace': '',
    # Repeats
    'repeatDot': '',
    # Clefs
    'gClef': '',
    'gClef8vb': '',
    'cClef': '',
    'fClef': '',
    'unpitchedPercussionClef1': '',
    # Time signatures
    'timeSig0': '',
    'timeSig1': '',
    'timeSig2': '',
    'timeSig3': '',
    'timeSig4': '',
    'timeSig5': '',
    'timeSig6': '',
    'timeSig7': '',
    'timeSig8': '',
    'timeSig9': '',
    # Noteheads
    'noteheadDoubleWhole': '',
    'noteheadWhole': '',
    'noteheadHalf': '',
    'noteheadBlack': '',
    # Individual notes
    'noteQuarterUp': '\ue1d5',
    'noteQuarterDown': '\ue1d6',
    # Augmentation dot
    'augmentationDot': '',
    # Flags
    'flag8thUp': '',
    'flag8thDown': '',
    'flag16thUp': '',
    'flag16thDown': '',
    'flag32ndUp': '',
    'flag32ndDown': '',
    'flag64thUp': '',
    'flag64thDown': '',
    # Accidentals
    'accidentalFlat': '',
    'accidentalNatural': '',
    'accidentalSharp': '',
    'accidentalDoubleSharp': '',
    'accidentalDoubleFlat': '',
    'accidentalTripleSharp': '',
    'accidentalTripleFlat': '',
    # Articulation
    'articAccentAbove': '\ue4a0',
    'articAccentBelow': '\ue4a1',
    'articStaccatoAbove': '\ue4a2',
    'articStaccatoBelow': '\ue4a3',
    'articTenutoAbove': '\ue4a4',
    'articTenutoBelow': '\ue4a5',
    # Holds and pauses
    'fermataAbove': '\ue4c0',
    'fermataBelow': '\ue4c1',
    # Rests
    'restDoubleWhole': '',
    'restWhole': '',
    'restHalf': '',
    'restQuarter': '',
    'rest8th': '',
    'rest16th': '',
    'rest32nd': '',
    'rest64th': '',
    # Dynamics
    'dynamicPiano': '\ue520',
    'dynamicForte': '\ue522',
    'dynamicPP': '\ue52b',
    'dynamicMP': '\ue52c',
    'dynamicMF': '\ue52d',
    'dynamicFF': '\ue52f',
    'dynamicCrescendoHairpin': '\ue53e',
    'dynamicDiminuendoHairpin': '\ue53f',
    # Tuplets
    'tuplet0': '',
    'tuplet1': '',
    'tuplet2': '',
    'tuplet3': '',
    'tuplet4': '',
    'tuplet5': '',
    'tuplet6': '',
    'tuplet7': '',
    'tuplet8': '',
    'tuplet9': '',
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
    advance: float = 0.0
    """Advance width in staff spaces (0 when the font gives none)."""

    @property
    def width(self) -> float:
        return self.bbox_ne[0] - self.bbox_sw[0]

    @property
    def height(self) -> float:
        return self.bbox_ne[1] - self.bbox_sw[1]

    def anchor(self, name: str) -> tuple[float, float]:
        """Return an anchor such as ``'stemUpSE'``; raises :class:`KeyError` if missing."""
        return self.anchors[name]


def _pair(value: Any) -> tuple[float, float]:
    return (float(value[0]), float(value[1]))


class FontMetrics:
    """Glyph metrics and engraving defaults, in staff spaces."""

    __slots__ = ('_advances', '_anchors', '_bboxes', '_cache', '_defaults', 'name')

    def __init__(
        self,
        name: str,
        defaults: dict[str, float],
        bboxes: dict[str, tuple[tuple[float, float], tuple[float, float]]],
        anchors: dict[str, dict[str, tuple[float, float]]],
        advances: dict[str, float],
    ) -> None:
        self.name = name
        self._defaults = defaults
        self._bboxes = bboxes
        self._anchors = anchors
        self._advances = advances
        self._cache: dict[str, GlyphInfo] = {}

    @classmethod
    def load(cls, metadata: Path) -> FontMetrics:
        """Read a SMuFL font metadata file such as ``Bravura.json``."""
        data = json.loads(metadata.read_text(encoding='utf-8'))
        defaults = {
            key: float(value)
            for key, value in data.get('engravingDefaults', {}).items()
            if isinstance(value, int | float)
        }
        bboxes = {
            name: (_pair(box['bBoxSW']), _pair(box['bBoxNE']))
            for name, box in data.get('glyphBBoxes', {}).items()
        }
        anchors = {
            name: {anchor: _pair(point) for anchor, point in points.items()}
            for name, points in data.get('glyphsWithAnchors', {}).items()
        }
        advances = {
            name: float(value) for name, value in data.get('glyphAdvanceWidths', {}).items()
        }
        return cls(str(data.get('fontName', metadata.stem)), defaults, bboxes, anchors, advances)

    @classmethod
    def bravura(cls) -> FontMetrics:
        """Load the bundled Bravura metadata from the data directory (cached)."""
        return _load_cached(data_file('fonts', 'Bravura.json'))

    def glyph(self, name: str) -> GlyphInfo:
        """Metrics of a glyph listed in :data:`CODEPOINTS`.

        Raises :class:`KeyError` for glyphs without a code point or metrics.
        """
        info = self._cache.get(name)
        if info is None:
            if name not in CODEPOINTS:
                raise KeyError(f'no code point for SMuFL glyph {name!r}')
            if name not in self._bboxes:
                raise KeyError(f'{self.name} has no metrics for {name!r}')
            sw, ne = self._bboxes[name]
            info = GlyphInfo(
                name=name,
                codepoint=CODEPOINTS[name],
                bbox_sw=sw,
                bbox_ne=ne,
                anchors=dict(self._anchors.get(name, {})),
                advance=self._advances.get(name, 0.0),
            )
            self._cache[name] = info
        return info

    def engraving_default(self, key: str) -> float:
        """E.g. ``'staffLineThickness'``, ``'stemThickness'``, ``'legerLineExtension'``."""
        try:
            return self._defaults[key]
        except KeyError:
            raise KeyError(f'{self.name} has no engraving default {key!r}') from None


@cache
def _load_cached(path: Path) -> FontMetrics:
    return FontMetrics.load(path)
