# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Smoke tests for ``StaffView``; they need PyGObject, GTK 4, libadwaita and a display."""

from __future__ import annotations

from typing import Any

import pytest

gi = pytest.importorskip('gi')

pytestmark = pytest.mark.gtk

from etude.core import Duration, KeySignature, NoteValue, Pitch  # noqa: E402
from etude.notation.spec import Bracket, Chord, Head, Ink, StaffSpec, SystemSpec  # noqa: E402

Q = Duration(NoteValue.QUARTER)


def _gtk() -> tuple[Any, Any, Any]:
    gi.require_version('Gtk', '4.0')
    gi.require_version('Gdk', '4.0')
    gi.require_version('Adw', '1')
    from gi.repository import Adw, Gdk, Gtk

    # GTK 4 can initialise without a display, so check for one explicitly.
    if not Gtk.init_check() or Gdk.Display.get_default() is None:
        pytest.skip('no display')
    Adw.init()
    return Adw, Gdk, Gtk


def _figure() -> StaffSpec:
    return StaffSpec(
        key_signature=KeySignature(2),
        events=(
            Chord((Head(Pitch.parse('C4')), Head(Pitch.parse('E4'))), Q),
            Chord((Head(Pitch.parse('G4'), halo=True),), Q, label='5', ink=Ink.ACCENT),
        ),
        brackets=(Bracket(0, 1, '?'),),
    )


def test_measure_scale_and_description() -> None:
    _adw, _gdk, gtk = _gtk()
    from etude.notation.widget import StaffView

    view = StaffView(_figure())
    natural = view.measure(gtk.Orientation.HORIZONTAL, -1)[1]
    assert natural > 0
    view.props.scale = 2.0
    assert view.measure(gtk.Orientation.HORIZONTAL, -1)[1] >= 2 * natural - 2
    view.props.staff_space = 6.0
    assert view.measure(gtk.Orientation.VERTICAL, -1)[1] > 0
    view.props.fill_width = True
    view.figure = None
    assert view.measure(gtk.Orientation.HORIZONTAL, -1)[1] == 0
    assert view.get_accessible_role() == gtk.AccessibleRole.IMG


def test_keyboard_and_click_activate_heads() -> None:
    _adw, gdk, _gtk_module = _gtk()
    from etude.notation.widget import StaffView

    view = StaffView(_figure())
    activated: list[tuple[int, int, int]] = []
    view.connect('head-activated', lambda _v, s, e, h: activated.append((s, e, h)))
    assert view._on_key(None, gdk.KEY_Return, 0, 0)
    assert activated[-1] == (0, 0, 0)  # leftmost event, lowest head first
    assert view._on_key(None, gdk.KEY_Up, 0, 0)
    assert view._on_key(None, gdk.KEY_space, 0, 0)
    assert activated[-1] == (0, 0, 1)
    assert view._on_key(None, gdk.KEY_Right, 0, 0)
    assert view._on_key(None, gdk.KEY_Return, 0, 0)
    assert activated[-1] == (0, 1, 0)
    assert view._on_key(None, gdk.KEY_Home, 0, 0)
    assert not view._on_key(None, gdk.KEY_a, 0, 0)

    display = view.display_list
    assert display is not None
    region = next(r for r in display.hit_regions if r.event == 1 and r.head == 0)
    px = view.pixels_per_space
    centre = (region.x + region.width / 2) * px, (region.y + region.height / 2) * px
    view._on_click(None, 1, *centre)
    assert activated[-1] == (0, 1, 0)


def test_renderer_draws_every_item_kind() -> None:
    _adw, _gdk, gtk = _gtk()
    gi.require_version('PangoCairo', '1.0')
    from gi.repository import PangoCairo

    from etude.notation.layout import layout
    from etude.notation.smufl import FontMetrics
    from etude.notation.widget import Palette, Renderer

    figure = SystemSpec((_figure(), StaffSpec(events=(Chord((Head(Pitch.parse('C5')),), Q),))))
    display = layout(figure, FontMetrics.bravura())
    renderer = Renderer(PangoCairo.FontMap.get_default().create_context())
    for palette in (Palette.light(), Palette.dark()):
        snapshot = gtk.Snapshot()
        renderer.draw(snapshot, display, 12.0, palette, focus=display.hit_regions[0])
        assert snapshot.to_node() is not None
