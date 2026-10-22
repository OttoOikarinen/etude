# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The figure area of the exercise page.

Pages never construct notation widgets themselves: they call
:func:`create_figure_widget`, which returns a
:class:`~etude.notation.widget.StaffView` set up with the learner's note
names and the "Large notation" setting.
"""

from __future__ import annotations

from gi.repository import Gtk

from ..core import Pitch
from ..notation import a11y
from ..notation.spec import Figure
from ..notation.widget import StaffView
from .common import note_label, setting_bool

STAFF_SPACE = 16.0
LARGE_SCALE = 1.5


def pitch_label(pitch: Pitch) -> str:
    """A pitch in the learner's naming convention with its octave, e.g. "F♯4"."""
    return f'{note_label(pitch.name)}{pitch.octave}'


def describe_figure(figure: Figure) -> str:
    """Accessible description of ``figure`` in the learner's note names."""
    return a11y.describe(figure, pitch_label)


def create_figure_widget(figure: Figure | None) -> Gtk.Widget:
    """A widget that shows ``figure``; hidden when there is none."""
    view = StaffView(
        figure=figure,
        staff_space=STAFF_SPACE,
        scale=LARGE_SCALE if setting_bool('large-notation') else 1.0,
        halign=Gtk.Align.CENTER,
    )
    view.add_css_class('staff-view')
    view.set_pitch_namer(pitch_label)
    view.set_visible(figure is not None)
    return view


class WideFigure(Gtk.Widget):
    """A figure in a sideways scroller, for figures too long to fit even at their
    smallest scale: the figure then scrolls inside its card instead of widening
    the page.

    A plain :class:`Gtk.ScrolledWindow` measures its child's height without a
    width, which gives a staff its smallest-scale height and clips it; this
    asks the staff for its height at the width it will get.
    """

    __gtype_name__ = 'EtudeWideFigure'

    def __init__(self, view: Gtk.Widget) -> None:
        super().__init__()
        self.view = view
        self._scroller = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vscrollbar_policy=Gtk.PolicyType.NEVER,
            propagate_natural_width=True,
        )
        self._scroller.set_child(view)
        self._scroller.set_parent(self)

    def do_dispose(self) -> None:
        self._scroller.unparent()

    def do_get_request_mode(self) -> Gtk.SizeRequestMode:
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self, orientation: Gtk.Orientation, for_size: int) -> tuple[int, int, int, int]:
        if orientation == Gtk.Orientation.HORIZONTAL:
            minimum, natural = self._scroller.measure(orientation, -1)[:2]
            return minimum, natural, -1, -1
        smallest, widest = self.view.measure(Gtk.Orientation.HORIZONTAL, -1)[:2]
        # The view is never narrower than its minimum: below that it scrolls.
        width = widest if for_size < 0 else max(for_size, smallest)
        minimum, natural = self.view.measure(orientation, width)[:2]
        return minimum, natural, -1, -1

    def do_size_allocate(self, width: int, height: int, baseline: int) -> None:
        self._scroller.allocate(width, height, baseline, None)

    def scroll_to(self, x: float, margin: float = 48.0) -> None:
        """Scroll as little as needed to show ``x`` (view pixels) with ``margin`` around
        it: the note a keyboard user is writing stays in sight."""
        adjustment = self._scroller.get_hadjustment()
        start = adjustment.get_value()
        page = adjustment.get_page_size()
        if page <= 0:
            return
        if x - margin < start:
            adjustment.set_value(max(adjustment.get_lower(), x - margin))
        elif x + margin > start + page:
            adjustment.set_value(min(adjustment.get_upper() - page, x + margin - page))
