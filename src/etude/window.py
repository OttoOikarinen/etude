# window.py
#
# Copyright 2026 Otto Oikarinen
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The main window: sidebar navigation, section pages and pushed exercise pages."""

from dataclasses import dataclass
from gettext import gettext as _
from gettext import ngettext

from gi.repository import Adw, Gdk, Gio, GObject, Gtk

from .exercises.base import Family
from .ui import preview
from .ui.common import get_settings
from .ui.controller import PreviewExerciseController
from .ui.dialogs.session_summary import RESPONSE_BACK
from .ui.pages.exercise import ExercisePage
from .ui.pages.home import HomePage
from .ui.pages.placeholder import create_placeholder_page
from .ui.pages.progress import ProgressPage
from .ui.pages.setup import SetupPage


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    icon_name: str = ''
    glyph: str = ''
    family: Family | None = None
    heading: bool = False
    """A non-selectable group heading ("Practice")."""


def sections() -> tuple[Section, ...]:
    return (
        Section('today', _('Today'), 'x-office-calendar-symbolic'),
        Section('path', _('Path'), 'find-location-symbolic'),
        Section('practice', _('Practice'), heading=True),
        Section('all', _('All exercises'), glyph='♪'),
        Section('notation', _('Notation'), glyph='♩', family=Family.NOTATION),
        Section('ear', _('Ear training'), 'audio-headphones-symbolic', family=Family.EAR),
        Section('rhythm', _('Rhythm'), glyph='♫', family=Family.RHYTHM),
        Section('harmony', _('Harmony'), glyph='♯', family=Family.HARMONY),
        Section('vocabulary', _('Vocabulary'), 'insert-text-symbolic', family=Family.VOCABULARY),
        Section('theory', _('Theory'), 'x-office-document-symbolic'),
        Section('glossary', _('Glossary'), 'accessories-dictionary-symbolic'),
        Section('progress', _('Progress'), 'x-office-spreadsheet-symbolic'),
    )


PLACEHOLDERS = {
    'today': ('x-office-calendar-symbolic', _('Your daily review of due items arrives soon')),
    'path': ('find-location-symbolic', _('The curriculum map arrives soon')),
    'theory': ('x-office-document-symbolic', _('Theory lessons arrive soon')),
    'glossary': ('accessories-dictionary-symbolic', _('The glossary arrives soon')),
}


class SidebarRow(Gtk.ListBoxRow):
    __gtype_name__ = 'EtudeSidebarRow'

    def __init__(self, section: Section) -> None:
        super().__init__()
        self.section = section
        if section.heading:
            label = Gtk.Label(label=section.title, xalign=0)
            label.add_css_class('heading')
            label.add_css_class('sidebar-heading')
            self.set_child(label)
            self.set_selectable(False)
            self.set_activatable(False)
            self.set_focusable(False)
            return
        box = Gtk.Box(spacing=12)
        if section.icon_name:
            box.append(
                Gtk.Image(
                    icon_name=section.icon_name, accessible_role=Gtk.AccessibleRole.PRESENTATION
                )
            )
        else:
            glyph = Gtk.Label(label=section.glyph, accessible_role=Gtk.AccessibleRole.PRESENTATION)
            glyph.add_css_class('sidebar-glyph')
            box.append(glyph)
        box.append(Gtk.Label(label=section.title, xalign=0))
        self.set_child(box)


@Gtk.Template(resource_path='/fi/oikarinenotto/etude/window.ui')
class EtudeWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'EtudeWindow'

    toast_overlay: Adw.ToastOverlay = Gtk.Template.Child()
    nav_view: Adw.NavigationView = Gtk.Template.Child()
    split_view: Adw.NavigationSplitView = Gtk.Template.Child()
    sidebar_list: Gtk.ListBox = Gtk.Template.Child()
    streak_number: Gtk.Label = Gtk.Template.Child()
    streak_caption: Gtk.Label = Gtk.Template.Child()
    practised_box: Gtk.Box = Gtk.Template.Child()

    compact = GObject.Property(type=bool, default=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.settings = get_settings()
        if self.settings is not None:
            flags = Gio.SettingsBindFlags.DEFAULT
            self.settings.bind('window-width', self, 'default-width', flags)
            self.settings.bind('window-height', self, 'default-height', flags)
            self.settings.bind('window-maximized', self, 'maximized', flags)

        # Stub data for W1; W2 feeds these pages from the registry and statistics.
        self.cards = preview.exercise_cards()
        self.home_page = HomePage()
        self.home_page.set_exercises(self.cards)
        self.home_page.set_continue(preview.continue_data())
        self.home_page.connect('exercise-activated', self._on_exercise_activated)
        self.home_page.connect('resume-activated', lambda _p, ex: self.start_exercise(ex))
        self.progress_page = ProgressPage(preview.progress)
        self.progress_page.connect('drill-requested', self._on_drill_requested)
        for page in (self.home_page, self.progress_page):
            self.bind_property('compact', page, 'compact', GObject.BindingFlags.SYNC_CREATE)
        self._placeholders: dict[str, Adw.NavigationPage] = {}
        self.controller: PreviewExerciseController | None = None

        streak = preview.streak()
        self.streak_number.set_label(str(streak.days))
        self.streak_caption.set_label(ngettext('Day streak', 'Day streak', streak.days))
        self.practised_box.set_visible(streak.practised_today)

        self.rows: dict[str, SidebarRow] = {}
        for section in sections():
            row = SidebarRow(section)
            self.rows[section.id] = row
            self.sidebar_list.append(row)
        self.show_section('all')

        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self._on_key_pressed)
        self.add_controller(keys)

    # Navigation -----------------------------------------------------------------------

    def show_section(self, section_id: str) -> Adw.NavigationPage:
        section = next(s for s in sections() if s.id == section_id)
        self.sidebar_list.select_row(self.rows[section_id])
        if section_id == 'all' or section.family is not None:
            self.home_page.set_exercises(self.cards, section.family)
            page = self.home_page
        elif section_id == 'progress':
            page = self.progress_page
        else:
            if section_id not in self._placeholders:
                icon, description = PLACEHOLDERS[section_id]
                self._placeholders[section_id] = create_placeholder_page(
                    section_id, section.title, icon, description
                )
            page = self._placeholders[section_id]
        if self.split_view.get_content() is not page:
            self.split_view.set_content(page)
        self.split_view.set_show_content(True)
        return page

    def open_setup(self, exercise_id: str) -> SetupPage:
        page = SetupPage(preview.PreviewKeySignatures())
        page.connect('start', lambda _p, ex, _settings: self.start_exercise(ex, replace=True))
        self.nav_view.push(page)
        return page

    def start_exercise(self, exercise_id: str, replace: bool = False) -> ExercisePage:
        questions = preview.preview_questions()
        key = exercise_id if exercise_id in questions else 'keysig'
        item = questions[key]
        page = ExercisePage(item.exercise_title, item.modality)
        self.bind_property('compact', page, 'compact', GObject.BindingFlags.SYNC_CREATE)
        page.connect('close-requested', lambda _p: self.nav_view.pop_to_tag('main'))
        session = preview.PreviewSession([key])
        self.controller = PreviewExerciseController(page, session, self._on_session_finished)
        if replace or self.nav_view.find_page('exercise') is not None:
            self.nav_view.replace([self.nav_view.find_page('main'), page])
        else:
            self.nav_view.push(page)
        return page

    def _on_session_finished(self, response: str) -> None:
        if response == RESPONSE_BACK:
            self.nav_view.pop_to_tag('main')

    def visible_exercise_page(self) -> ExercisePage | None:
        page = self.nav_view.get_visible_page()
        return page if isinstance(page, ExercisePage) else None

    # Handlers -------------------------------------------------------------------------

    def _on_exercise_activated(self, _page: HomePage, exercise_id: str) -> None:
        if exercise_id == preview.PreviewKeySignatures.id:
            self.open_setup(exercise_id)
        else:
            self.start_exercise(exercise_id)

    def _on_drill_requested(self, _page: ProgressPage, _item_ids: tuple) -> None:
        self.start_exercise('interval-ear')

    def _on_key_pressed(
        self, _controller: Gtk.EventControllerKey, keyval: int, _code: int, state
    ) -> bool:
        page = self.visible_exercise_page()
        if page is None or self.get_visible_dialog() is not None:
            return False
        focus = self.get_focus()
        if isinstance(focus, Gtk.Text | Gtk.Editable) and keyval != Gdk.KEY_Escape:
            return False
        return page.handle_key(keyval, state)

    @Gtk.Template.Callback()
    def _on_sidebar_row_activated(self, _list: Gtk.ListBox, row: SidebarRow) -> None:
        if not row.section.heading:
            self.show_section(row.section.id)

    @Gtk.Template.Callback()
    def _on_breakpoint_apply(self, _breakpoint: Adw.Breakpoint) -> None:
        self.compact = True

    @Gtk.Template.Callback()
    def _on_breakpoint_unapply(self, _breakpoint: Adw.Breakpoint) -> None:
        self.compact = False
