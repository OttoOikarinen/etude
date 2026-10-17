# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Layout and description of :class:`GlyphFigure` (symbols on their own)."""

from __future__ import annotations

import itertools

from hypothesis import given
from hypothesis import strategies as st

from etude.notation.a11y import describe
from etude.notation.displaylist import GlyphItem, LineItem
from etude.notation.layout import MARGIN, item_bounds, layout
from etude.notation.smufl import FontMetrics
from etude.notation.spec import GlyphFigure, Ink

METRICS = FontMetrics.bravura()
STANDALONE = (
    'dynamicPP',
    'dynamicPiano',
    'dynamicMP',
    'dynamicMF',
    'dynamicForte',
    'dynamicFF',
    'dynamicCrescendoHairpin',
    'dynamicDiminuendoHairpin',
    'noteQuarterUp',
    'noteQuarterDown',
)


def _inside(display, item) -> bool:
    x0, y0, x1, _y1 = item_bounds(item, METRICS)
    eps = 1e-6
    return x0 >= MARGIN - eps and y0 >= MARGIN - eps and x1 <= display.width - MARGIN + eps


@given(st.lists(st.sampled_from(STANDALONE), min_size=1, max_size=6), st.booleans())
def test_glyphs_side_by_side_in_order_inside_the_margins(glyphs: list[str], staff: bool) -> None:
    figure = GlyphFigure(tuple(glyphs), 'Symbols.', staff=staff)
    display = layout(figure, METRICS)
    items = [i for i in display.items if isinstance(i, GlyphItem)]
    assert [i.glyph for i in items] == glyphs
    assert len({i.y for i in items}) == 1, 'one baseline'
    for left, right in itertools.pairwise(items):
        assert item_bounds(left, METRICS)[2] < item_bounds(right, METRICS)[0]
    assert all(_inside(display, i) for i in display.items)
    assert display.height >= max(item_bounds(i, METRICS)[3] for i in display.items) + MARGIN - 1e-6
    lines = [i for i in display.items if isinstance(i, LineItem)]
    if staff:
        assert len(lines) == 5
        (geometry,) = display.staves
        assert items[0].y == geometry.y_of(4), 'symbols stand on the middle line'
    else:
        assert not lines
        assert display.staves == ()


def test_articulations_attach_above_and_below() -> None:
    figure = GlyphFigure(
        ('noteQuarterDown', 'articAccentAbove', 'noteQuarterUp', 'articStaccatoBelow'), 'Notes.'
    )
    display = layout(figure, METRICS)
    down, accent, up, staccato = (i for i in display.items if isinstance(i, GlyphItem))
    nx0, ny0, nx1, _ny1 = item_bounds(down, METRICS)
    ax0, _ay0, ax1, ay1 = item_bounds(accent, METRICS)
    assert ay1 < ny0, 'above the notehead'
    assert abs((ax0 + ax1) / 2 - (nx0 + nx1) / 2) < 1e-6, 'centred on it'
    _ux0, _uy0, _ux1, uy1 = item_bounds(up, METRICS)
    _sx0, sy0, _sx1, _sy1 = item_bounds(staccato, METRICS)
    assert sy0 > uy1, 'below the notehead'
    assert ax1 < item_bounds(up, METRICS)[0], 'the next note comes after the accent'


def test_a_fermata_clears_the_staff() -> None:
    figure = GlyphFigure(('noteQuarterDown', 'fermataAbove'), 'A held note.', staff=True)
    display = layout(figure, METRICS)
    fermata = next(
        i for i in display.items if isinstance(i, GlyphItem) and i.glyph == 'fermataAbove'
    )
    (geometry,) = display.staves
    assert item_bounds(fermata, METRICS)[3] < geometry.top


def test_ink_and_description() -> None:
    figure = GlyphFigure(('dynamicFF',), 'A dynamic marking.', ink=Ink.ACCENT)
    display = layout(figure, METRICS)
    assert all(i.ink is Ink.ACCENT for i in display.items)
    assert describe(figure) == 'A dynamic marking.'
    assert layout(GlyphFigure((), ''), METRICS).items == ()
