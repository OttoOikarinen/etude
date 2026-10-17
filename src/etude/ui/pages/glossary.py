# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The glossary: every term of the curriculum, searchable and grouped by level.

Activating a term opens it in :class:`~etude.ui.dialogs.glossary_entry.GlossaryEntryDialog`
(the window does that). "Practise Vocabulary" appears when a vocabulary
exercise is registered.
"""

from __future__ import annotations

from gettext import gettext as _
from gettext import ngettext

from gi.repository import Adw, GObject, Gtk

from ...content.model import GlossaryEntry
from ..common import ui_resource
from ..content import language_name
from ..model import GlossaryData


def matches(entry: GlossaryEntry, query: str) -> bool:
    """Whether a search (case-insensitive) finds ``entry`` by headword, term, gloss or
    abbreviation."""
    needle = query.strip().casefold()
    if not needle:
        return True
    fields = (entry.headword, entry.term, entry.gloss, entry.abbreviation or '')
    return any(needle in text.casefold() for text in fields)


def level_heading(number: int, title: str) -> str:
    if not title:
        return _('Level {number}').format(number=number)
    # Translators: a glossary group, e.g. "Level 1 · Fundamentals".
    return _('Level {number} · {title}').format(number=number, title=title)


@Gtk.Template(resource_path=ui_resource('pages/glossary.ui'))
class GlossaryPage(Adw.NavigationPage):
    """Signals: ``entry-activated(entry_id)`` and ``practise-requested``."""

    __gtype_name__ = 'EtudeGlossaryPage'
    __gsignals__ = {  # noqa: RUF012 (GObject API)
        'entry-activated': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        'practise-requested': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    practise_button: Gtk.Button = Gtk.Template.Child()
    search_entry: Gtk.SearchEntry = Gtk.Template.Child()
    results_stack: Gtk.Stack = Gtk.Template.Child()
    groups_box: Gtk.Box = Gtk.Template.Child()

    compact = GObject.Property(type=bool, default=False)

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.data = GlossaryData(())
        self.rows: dict[str, Adw.ActionRow] = {}
        self._groups: list[tuple[Adw.PreferencesGroup, list[GlossaryEntry]]] = []
        self.search_entry.set_key_capture_widget(self)
        self.connect('notify::compact', lambda *_a: self._apply_compact())

    def _apply_compact(self) -> None:
        if self.compact:
            self.add_css_class('compact')
        else:
            self.remove_css_class('compact')

    def set_data(self, data: GlossaryData) -> None:
        self.data = data
        self.practise_button.set_visible(data.vocabulary_available)
        self._rebuild()

    @property
    def visible_entries(self) -> list[str]:
        return [entry_id for entry_id, row in self.rows.items() if row.get_visible()]

    def _rebuild(self) -> None:
        for group, _entries in self._groups:
            self.groups_box.remove(group)
        self._groups = []
        self.rows = {}
        levels: dict[int, list[GlossaryEntry]] = {}
        for entry in self.data.entries:
            levels.setdefault(entry.level, []).append(entry)
        for number in sorted(levels):
            group = Adw.PreferencesGroup(
                title=level_heading(number, self.data.level_titles.get(number, ''))
            )
            for entry in levels[number]:
                row = self._row(entry)
                self.rows[entry.id] = row
                group.add(row)
            self.groups_box.append(group)
            self._groups.append((group, levels[number]))
        self._filter()

    def _row(self, entry: GlossaryEntry) -> Adw.ActionRow:
        row = Adw.ActionRow(title=entry.headword, subtitle=entry.gloss, activatable=True)
        row.set_title_selectable(False)
        row.set_use_markup(False)
        if entry.foreign_language:
            language = Gtk.Label(label=language_name(entry.foreign_language))
            language.set_valign(Gtk.Align.CENTER)
            language.add_css_class('language-pill')
            language.add_css_class('caption')
            row.add_suffix(language)
        row.add_suffix(
            Gtk.Image(icon_name='go-next-symbolic', accessible_role=Gtk.AccessibleRole.PRESENTATION)
        )
        row.connect(
            'activated', lambda _r, entry_id=entry.id: self.emit('entry-activated', entry_id)
        )
        return row

    def _filter(self) -> None:
        query = self.search_entry.get_text()
        shown = 0
        for group, entries in self._groups:
            visible = 0
            for entry in entries:
                found = matches(entry, query)
                self.rows[entry.id].set_visible(found)
                visible += found
            group.set_visible(visible > 0)
            group.set_description(
                ngettext('{n} term', '{n} terms', visible).format(n=visible) if visible else ''
            )
            shown += visible
        self.results_stack.set_visible_child_name('list' if shown else 'empty')

    @Gtk.Template.Callback()
    def _on_search_changed(self, _entry: Gtk.SearchEntry) -> None:
        self._filter()

    @Gtk.Template.Callback()
    def _on_practise_clicked(self, _button: Gtk.Button) -> None:
        self.emit('practise-requested')
