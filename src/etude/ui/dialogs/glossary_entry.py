# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""A glossary entry in a dialog, opened from the glossary or a term in a lesson.

Links in the definition and "See also" open further entries inside the same
dialog, with a back button, so the learner never loses their place.
"""

from __future__ import annotations

from collections.abc import Callable

from gi.repository import Adw, Gtk

from ...content.model import GlossaryEntry
from ..content import PlayHandler, entry_detail

Lookup = Callable[[str], GlossaryEntry | None]


class GlossaryEntryDialog(Adw.Dialog):
    __gtype_name__ = 'EtudeGlossaryEntryDialog'

    def __init__(self, lookup: Lookup, on_play: PlayHandler, entry_id: str) -> None:
        super().__init__(content_width=520, content_height=560, follows_content_size=False)
        self._lookup = lookup
        self._on_play = on_play
        self.nav_view = Adw.NavigationView()
        self.nav_view.connect('popped', self._on_popped)
        self.set_child(self.nav_view)
        self.shown: list[str] = []
        self.show_entry(entry_id)

    def show_entry(self, entry_id: str) -> bool:
        """Open ``entry_id`` (pushed over the current entry); ``False`` if it is unknown."""
        entry = self._lookup(entry_id)
        if entry is None:
            return False
        if self.shown and self.shown[-1] == entry_id:
            return True
        see_also = [e for e in (self._lookup(i) for i in entry.see_also) if e is not None]
        detail = entry_detail(entry, self.show_entry, self._on_play, see_also)
        clamp = Adw.Clamp(maximum_size=560, child=detail)
        clamp.add_css_class('glossary-dialog-body')
        scroller = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True, child=clamp
        )
        toolbar = Adw.ToolbarView(content=scroller)
        toolbar.add_top_bar(Adw.HeaderBar(show_title=False))
        page = Adw.NavigationPage(title=entry.headword, child=toolbar)
        self.nav_view.push(page)
        self.set_title(entry.headword)
        self.shown.append(entry_id)
        return True

    def _on_popped(self, view: Adw.NavigationView, _page: Adw.NavigationPage) -> None:
        if self.shown:
            self.shown.pop()
        visible = view.get_visible_page()
        if visible is not None:
            self.set_title(visible.get_title())
