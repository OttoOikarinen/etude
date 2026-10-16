# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import json
from pathlib import Path

import pytest

from etude.notation.smufl import CODEPOINTS, FontMetrics


def test_bravura_is_cached(metrics: FontMetrics) -> None:
    assert FontMetrics.bravura() is metrics
    assert metrics.name == 'Bravura'


def test_every_codepoint_has_metrics(metrics: FontMetrics) -> None:
    for name, codepoint in CODEPOINTS.items():
        info = metrics.glyph(name)
        assert info.codepoint == codepoint
        assert len(codepoint) == 1
        assert 0xE000 <= ord(codepoint) <= 0xF8FF  # SMuFL lives in the Private Use Area
        assert info.width >= 0
        assert info.height >= 0


def test_codepoints_are_unique() -> None:
    assert len(set(CODEPOINTS.values())) == len(CODEPOINTS)


def test_glyph_metrics(metrics: FontMetrics) -> None:
    head = metrics.glyph('noteheadBlack')
    assert head.bbox_sw == (0.0, -0.5)
    assert head.bbox_ne == (1.18, 0.5)
    assert head.anchor('stemUpSE') == (1.18, 0.168)
    assert head.anchor('stemDownNW') == (0.0, -0.168)
    assert head.advance == pytest.approx(1.18)
    assert metrics.glyph('noteheadBlack') is head  # cached


def test_engraving_defaults(metrics: FontMetrics) -> None:
    assert metrics.engraving_default('staffLineThickness') == 0.13
    assert metrics.engraving_default('stemThickness') == 0.12
    assert metrics.engraving_default('legerLineExtension') == 0.4
    with pytest.raises(KeyError):
        metrics.engraving_default('textFontFamily')  # a list, not a number
    with pytest.raises(KeyError):
        metrics.engraving_default('noSuchKey')


def test_unknown_glyphs(metrics: FontMetrics, tmp_path: Path) -> None:
    with pytest.raises(KeyError, match='no code point'):
        metrics.glyph('noSuchGlyph')
    metadata = tmp_path / 'Tiny.json'
    metadata.write_text(json.dumps({'fontName': 'Tiny', 'engravingDefaults': {}}))
    tiny = FontMetrics.load(metadata)
    assert tiny.name == 'Tiny'
    with pytest.raises(KeyError, match='no metrics'):
        tiny.glyph('gClef')
