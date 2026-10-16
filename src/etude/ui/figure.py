# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The figure area of the exercise page.

Pages never construct notation widgets themselves: they call
:func:`create_figure_widget`. In W1 it returns a neutral placeholder that
shows the figure's text description over five faint staff lines; W2 swaps in
``etude.notation.widget.StaffView`` here, in one place.
"""

from __future__ import annotations

from gettext import gettext as _

from gi.repository import Graphene, Gtk

from ..notation.spec import Clef, Figure, StaffSpec, SystemSpec


def describe_figure(figure: Figure) -> str:
    """Accessible description of ``figure``.

    Uses :func:`etude.notation.a11y.describe` once the notation engine implements
    it, and a short generic description until then.
    """
    from ..notation import a11y

    try:
        return a11y.describe(figure)
    except NotImplementedError:
        pass
    if figure.description:
        return figure.description
    staves = figure.staves if isinstance(figure, SystemSpec) else (figure,)
    names = {
        Clef.TREBLE: _('Treble staff'),
        Clef.BASS: _('Bass staff'),
        Clef.ALTO: _('Alto staff'),
        Clef.TENOR: _('Tenor staff'),
        Clef.TREBLE_8VB: _('Treble staff, an octave lower'),
        Clef.PERCUSSION: _('Rhythm staff'),
    }
    return ', '.join(names[s.clef] for s in staves)


class _StaffLines(Gtk.Widget):
    """Five faint horizontal lines that hint at a staff."""

    __gtype_name__ = 'EtudeStaffLines'

    def __init__(self, lines: int = 5) -> None:
        super().__init__(hexpand=True, accessible_role=Gtk.AccessibleRole.PRESENTATION)
        self._lines = lines

    def do_measure(self, orientation: Gtk.Orientation, for_size: int) -> tuple[int, int, int, int]:
        if orientation == Gtk.Orientation.HORIZONTAL:
            return 120, 480, -1, -1
        return 64, 72, -1, -1

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        width, height = self.get_width(), self.get_height()
        color = self.get_color()
        color.alpha *= 0.35
        gap = 12
        top = (height - gap * (self._lines - 1)) / 2
        for i in range(self._lines):
            rect = Graphene.Rect().init(0, top + i * gap, width, 1)
            snapshot.append_color(color, rect)


def create_figure_widget(figure: Figure | None) -> Gtk.Widget:
    """A widget that shows ``figure``. W1: a placeholder; W2: ``StaffView``."""
    box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=12, accessible_role=Gtk.AccessibleRole.IMG
    )
    box.add_css_class('figure-placeholder')
    if figure is None:
        box.set_visible(False)
        return box
    lines = figure.lines if isinstance(figure, StaffSpec) else 5
    box.append(_StaffLines(lines))
    description = describe_figure(figure)
    label = Gtk.Label(label=description, wrap=True, justify=Gtk.Justification.CENTER)
    label.add_css_class('dim-label')
    box.append(label)
    box.update_property([Gtk.AccessibleProperty.LABEL], [description])
    return box
