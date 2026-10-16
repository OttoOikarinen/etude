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
