# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The interface every answer widget implements.

An answer widget renders one :data:`~etude.exercises.base.AnswerSpec` and
emits ``answered`` with the answer value, typed as documented on that spec
(an option key, a :class:`~etude.core.PitchName`, a mapping of chip groups…).
The exercise page forwards key presses to :meth:`AnswerWidget.handle_key` so
that accelerators work wherever the focus is, and calls
:meth:`AnswerWidget.reveal` once the answer has been graded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gi.repository import Gdk, GObject, Gtk

if TYPE_CHECKING:
    from ..timing import Player


class AnswerWidget(Gtk.Box):
    __gtype_name__ = 'EtudeAnswerWidget'
    __gsignals__ = {  # noqa: RUF012 (GObject API)
        'answered': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        # Asks the page to open its bottom sheet with get_sheet() (design 3b).
        'sheet-requested': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }
    captures_space = False
    """Space belongs to this widget (tapping a rhythm), not to the page's Skip."""

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault('orientation', Gtk.Orientation.VERTICAL)
        kwargs.setdefault('spacing', 12)
        super().__init__(**kwargs)
        self.add_css_class('answer-area')
        self.locked = False
        """True once answered: further input is ignored until the next question."""
        self.compact = False
        self.player: Player | None = None
        """Plays with beat callbacks (set by the page; rhythm tapping needs it)."""

    def submit(self, value: object) -> None:
        if self.locked:
            return
        self.locked = True
        self.emit('answered', value)

    def handle_key(self, keyval: int, state: Gdk.ModifierType) -> bool:
        """Handle an accelerator; return True when the key was used."""
        return False

    def activate_default(self) -> bool:
        """Enter was pressed: confirm the answer if the widget has a Check step."""
        return False

    def reveal(self, expected: object, given: object, correct: bool) -> None:
        """Show which answer was right (success) and which was wrong (error)."""
        self.locked = True

    def set_compact(self, compact: bool) -> None:
        """Switch to the narrow layout (design 3b)."""
        self.compact = compact

    def get_sheet(self) -> Gtk.Widget | None:
        """Content for the page's bottom sheet in the narrow layout, if any."""
        return None
