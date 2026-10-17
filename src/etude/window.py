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

from collections.abc import Callable
from dataclasses import dataclass
from gettext import gettext as _
from gettext import ngettext

from gi.repository import Adw, Gdk, Gio, GObject, Gtk

from .exercises.base import Family
from .exercises.runner import EmptySessionError
from .learning.model import ItemId, SessionMode
from .ui.common import get_settings
from .ui.controller import ExerciseController, empty_session_message
from .ui.dialogs.glossary_entry import GlossaryEntryDialog
from .ui.dialogs.session_summary import RESPONSE_BACK
from .ui.model import AppModel, SessionSource
from .ui.pages.exercise import ExercisePage
from .ui.pages.glossary import GlossaryPage
from .ui.pages.home import HomePage
from .ui.pages.lesson import LessonPage
from .ui.pages.lessons import LessonsPage
from .ui.pages.path import PathPage
from .ui.pages.progress import ProgressPage
from .ui.pages.setup import SetupPage
from .ui.pages.today import TodayPage

RESPONSE_PRACTISE = 'practise'


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


def quoted_units(titles: tuple[str, ...]) -> str:
    """“Staff, Clefs and Note Names”, or “Intervals” and 2 more units."""
    if not titles:
        return ''
    # Translators: a unit title in quotes.
    first = _('“{unit}”').format(unit=titles[0])
    if len(titles) == 1:
        return first
    others = len(titles) - 1
    return ngettext('{unit} and {n} more unit', '{unit} and {n} more units', others).format(
        unit=first, n=others
    )


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
        box.append(Gtk.Label(label=section.title, xalign=0, hexpand=True))
        self.count_label = Gtk.Label(visible=False, valign=Gtk.Align.CENTER)
        self.count_label.add_css_class('sidebar-count')
        self.count_label.add_css_class('numeric')
        box.append(self.count_label)
        self.set_child(box)

    def set_count(self, count: int, description: str = '') -> None:
        """Show a small count after the title (due items next to "Today")."""
        self.count_label.set_label(str(count))
        self.count_label.set_visible(count > 0)
        self.update_property([Gtk.AccessibleProperty.DESCRIPTION], [description if count else ''])


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

    def __init__(self, model: AppModel, **kwargs):
        super().__init__(**kwargs)
        self.model = model
        self.settings = get_settings()
        if self.settings is not None:
            flags = Gio.SettingsBindFlags.DEFAULT
            self.settings.bind('window-width', self, 'default-width', flags)
            self.settings.bind('window-height', self, 'default-height', flags)
            self.settings.bind('window-maximized', self, 'maximized', flags)

        self.cards = list(model.exercise_cards())
        self.home_page = HomePage()
        self.home_page.connect('exercise-activated', self._on_exercise_activated)
        self.home_page.connect('resume-activated', lambda _p: self.resume_session())
        self.home_page.connect('continue-dismissed', lambda _p: self._on_continue_dismissed())
        self.today_page = TodayPage()
        self.today_page.connect(
            'start-review', lambda _p: self.start_session(SessionMode.DAILY_REVIEW)
        )
        self.today_page.connect('exercise-activated', lambda _p, ex: self.start_exercise(ex))
        self.today_page.connect('browse-requested', lambda _p: self.show_section('all'))
        self.progress_page = ProgressPage(model.progress)
        self.progress_page.connect('drill-requested', self._on_drill_requested)
        self.path_page = PathPage()
        self.path_page.connect('lesson-requested', lambda _p, unit: self.open_lesson(unit))
        self.path_page.connect('practise-requested', lambda _p, unit: self.practise_unit(unit))
        self.path_page.connect('exam-requested', lambda _p, level: self.take_exam(level))
        self.path_page.connect('placement-requested', lambda _p: self.take_placement())
        self.lessons_page = LessonsPage()
        self.lessons_page.connect('lesson-requested', lambda _p, unit: self.open_lesson(unit))
        self.glossary_page = GlossaryPage()
        self.glossary_page.connect('entry-activated', lambda _p, e: self.show_glossary_entry(e))
        self.glossary_page.connect('practise-requested', lambda _p: self.practise_vocabulary())
        for page in (
            self.home_page,
            self.today_page,
            self.progress_page,
            self.path_page,
            self.lessons_page,
            self.glossary_page,
        ):
            self.bind_property('compact', page, 'compact', GObject.BindingFlags.SYNC_CREATE)
        self.confirm_dialog: Adw.AlertDialog | None = None
        self.glossary_dialog: GlossaryEntryDialog | None = None
        self._glossary_loaded = False
        self.controller: ExerciseController | None = None
        self._paused_elapsed = 0
        """Seconds on the clock of the interrupted session, restored on resume."""
        self._page_serial = 0
        self._section = 'all'

        self.rows: dict[str, SidebarRow] = {}
        for section in sections():
            row = SidebarRow(section)
            self.rows[section.id] = row
            self.sidebar_list.append(row)
        self.refresh()
        self.show_section('all')
        self.nav_view.connect('popped', self._on_page_popped)
        self._goal_handler = 0
        self.connect('realize', lambda _w: self._watch_daily_goal(True))
        self.connect('unrealize', lambda _w: self._watch_daily_goal(False))

        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self._on_key_pressed)
        self.add_controller(keys)

    # Navigation -----------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload the numbers shown on every section page and the sidebar."""
        self.cards = list(self.model.exercise_cards())
        section = next(s for s in sections() if s.id == self._section)
        self.home_page.set_exercises(self.cards, section.family)
        self.home_page.set_continue(self.model.continue_data())
        streak = self.model.streak()
        self.streak_number.set_label(str(streak.days))
        self.streak_caption.set_label(ngettext('Day streak', 'Day streak', streak.days))
        self.practised_box.set_visible(streak.practised_today)
        self.progress_page.set_data(self.model.progress(self.progress_page.period))
        self._refresh_today()
        if self._section in ('path', 'theory'):
            self._refresh_path()

    def _refresh_path(self) -> None:
        """Mastery and unlocking change with every answer: reload the curriculum map."""
        data = self.model.path()
        self.path_page.set_data(data)
        self.lessons_page.set_data(data)

    def _watch_daily_goal(self, watch: bool) -> None:
        """Show a changed ``daily-goal`` at once (the model applies it first: it
        connected earlier). Only while the window is realized: a closed window's
        model may be gone."""
        if self.settings is None:
            return
        if watch and not self._goal_handler:
            self._goal_handler = self.settings.connect(
                'changed::daily-goal', lambda *_a: self.refresh()
            )
        elif not watch and self._goal_handler:
            self.settings.disconnect(self._goal_handler)
            self._goal_handler = 0

    def _refresh_today(self) -> None:
        today = self.model.today()
        self.today_page.set_data(today)
        self.rows['today'].set_count(
            today.due,
            # Translators: read by screen readers after "Today" in the sidebar.
            ngettext('{n} item due', '{n} items due', today.due).format(n=today.due),
        )

    def show_section(self, section_id: str) -> Adw.NavigationPage:
        section = next(s for s in sections() if s.id == section_id)
        self._section = section_id
        self.sidebar_list.select_row(self.rows[section_id])
        if section_id == 'all' or section.family is not None:
            self.home_page.set_exercises(self.cards, section.family)
            page = self.home_page
        elif section_id == 'today':
            # Items fall due as time passes: always show the current numbers.
            self._refresh_today()
            page = self.today_page
        elif section_id == 'progress':
            page = self.progress_page
        elif section_id in ('path', 'theory'):
            self._refresh_path()
            page = self.path_page if section_id == 'path' else self.lessons_page
        elif section_id == 'glossary':
            if not self._glossary_loaded:
                self.glossary_page.set_data(self.model.glossary())
                self._glossary_loaded = True
            page = self.glossary_page
        else:
            raise KeyError(section_id)
        if self.split_view.get_content() is not page:
            self.split_view.set_content(page)
        self.split_view.set_show_content(True)
        return page

    def open_setup(self, exercise_id: str) -> SetupPage:
        definition = self.model.definition(exercise_id)
        assert definition is not None
        page = SetupPage(definition)
        page.connect('start', lambda _p, ex, _settings: self.start_exercise(ex, replace=True))
        self.nav_view.push(page)
        return page

    def start_exercise(self, exercise_id: str, replace: bool = False) -> ExercisePage | None:
        return self.start_session(SessionMode.EXERCISE, exercise_id=exercise_id, replace=replace)

    def start_session(
        self,
        mode: SessionMode,
        *,
        exercise_id: str | None = None,
        item_ids: tuple[ItemId, ...] = (),
        replace: bool = False,
    ) -> ExercisePage | None:
        """Open the exercise page with a new session; ``None`` if there is nothing to do."""
        return self._start(
            lambda: self.model.start(mode, exercise_id=exercise_id, item_ids=item_ids),
            replace=replace,
        )

    def _start(
        self, factory: Callable[[], SessionSource], *, replace: bool = False
    ) -> ExercisePage | None:
        try:
            session = factory()
        except EmptySessionError:
            self.toast_overlay.add_toast(Adw.Toast(title=empty_session_message()))
            self.refresh()  # starting finished an interrupted session
            return None
        return self._open_session(session, replace=replace)

    # The learning path --------------------------------------------------------------

    def open_lesson(self, unit_id: str) -> LessonPage | None:
        """Push the lesson of a unit; reading is never locked."""
        unit = self.model.path().unit(unit_id)
        lesson = self.model.lesson(unit.lesson_id) if unit.lesson_id else None
        if lesson is None:
            return None
        page = LessonPage(lesson, unit, done=unit.lesson_done)
        self.bind_property('compact', page, 'compact', GObject.BindingFlags.SYNC_CREATE)
        page.connect('term-activated', lambda _p, entry: self.show_glossary_entry(entry))
        page.connect('play-requested', lambda _p, spec: self.model.play(spec))
        page.connect('practise-requested', lambda _p, u: self.practise_unit(u))
        page.connect('completed', self._on_lesson_completed)
        page.connect('hidden', lambda _p: self.model.stop_audio())
        self.nav_view.push(page)
        if not lesson.checks and not unit.lesson_done:
            self._on_lesson_completed(page, lesson.id)  # nothing to answer: reading completes it
        return page

    def _on_lesson_completed(self, _page: LessonPage, lesson_id: str) -> None:
        self.model.complete_lesson(lesson_id)
        self._refresh_path()

    def visible_lesson_page(self) -> LessonPage | None:
        page = self.nav_view.get_visible_page()
        return page if isinstance(page, LessonPage) else None

    def practise_unit(self, unit_id: str) -> ExercisePage | None:
        """Practise a unit's items; a locked unit asks first (the lock is advice)."""
        unit = self.model.path().unit(unit_id)

        def start() -> ExercisePage | None:
            return self._start(lambda: self.model.start_unit(unit_id))

        if unit.unlocked:
            return start()
        # Translators: confirmation before practising a locked unit; {units} are
        # unit titles in quotes, e.g. “Staff, Clefs and Note Names”.
        body = _('You haven’t mastered {units} yet. Practise anyway?').format(
            units=quoted_units(unit.missing)
        )
        self._confirm(_('Unit Not Unlocked Yet'), body, _('_Practise Anyway'), start)
        return None

    def take_exam(self, level_id: str) -> ExercisePage | None:
        level = self.model.path().level(level_id)

        def start() -> ExercisePage | None:
            return self._start(lambda: self.model.start_exam(level_id))

        if level.exam_ready or level.passed:
            return start()
        self._confirm(
            _('Take the Exam Early?'),
            _('Some units of this level are not unlocked yet. Take the exam anyway?'),
            _('_Take Exam'),
            start,
        )
        return None

    def take_placement(self) -> ExercisePage | None:
        return self._start(self.model.start_placement)

    def practise_vocabulary(self) -> ExercisePage | None:
        return self.start_session(SessionMode.EXERCISE, exercise_id='vocabulary')

    def _confirm(self, heading: str, body: str, accept: str, action: Callable[[], object]) -> None:
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response('cancel', _('_Cancel'))
        dialog.add_response(RESPONSE_PRACTISE, accept)
        dialog.set_response_appearance(RESPONSE_PRACTISE, Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response(RESPONSE_PRACTISE)
        dialog.set_close_response('cancel')

        def on_response(_dialog: Adw.AlertDialog, response: str) -> None:
            self.confirm_dialog = None
            if response == RESPONSE_PRACTISE:
                action()

        dialog.connect('response', on_response)
        self.confirm_dialog = dialog
        dialog.present(self)

    def show_glossary_entry(self, entry_id: str) -> GlossaryEntryDialog | None:
        if self.model.glossary_entry(entry_id) is None:
            return None
        if self.glossary_dialog is not None:
            self.glossary_dialog.show_entry(entry_id)
            return self.glossary_dialog
        dialog = GlossaryEntryDialog(self.model.glossary_entry, self.model.play, entry_id)
        dialog.connect('closed', self._on_glossary_closed)
        self.glossary_dialog = dialog
        dialog.present(self)
        return dialog

    def _on_glossary_closed(self, _dialog: GlossaryEntryDialog) -> None:
        self.glossary_dialog = None

    def resume_session(self) -> ExercisePage | None:
        """Go on with the interrupted session of the Continue banner."""
        session = self.model.resume()
        if session is None:
            self.refresh()
            return None
        page = self._open_session(session)
        page.set_elapsed(self._paused_elapsed)
        return page

    def _open_session(self, session: SessionSource, *, replace: bool = False) -> ExercisePage:
        page = ExercisePage(session.title)
        self.bind_property('compact', page, 'compact', GObject.BindingFlags.SYNC_CREATE)
        page.connect('close-requested', lambda _p: self._close_session())
        self.controller = ExerciseController(page, session, self.model, self._on_session_finished)
        # A page that was just closed stays in the view until its pop animation
        # ends, so every exercise page gets its own tag.
        self._page_serial += 1
        page.set_tag(f'exercise-{self._page_serial}')
        stack = self.nav_view.get_navigation_stack()
        pages = [stack.get_item(i) for i in range(stack.get_n_items())]
        if replace or any(isinstance(p, ExercisePage) for p in pages):
            self.nav_view.replace([self.nav_view.find_page('main'), page])
        else:
            self.nav_view.push(page)
        # Starting or resuming a session ends the Continue banner's session.
        self.home_page.set_continue(self.model.continue_data())
        return page

    def _close_session(self) -> None:
        self.nav_view.pop_to_tag('main')

    def _on_page_popped(self, _view: Adw.NavigationView, page: Adw.NavigationPage) -> None:
        """Leaving the exercise page in any way keeps its session for the Continue banner."""
        controller = self.controller
        if controller is None or page is not controller.page:
            return
        self.controller = None
        if controller.summary is None:
            self._paused_elapsed = controller.page.elapsed
            self.model.close_session(controller.session)
        self.refresh()

    def _on_continue_dismissed(self) -> None:
        self.model.dismiss_continue()
        self.refresh()

    def _on_session_finished(self, response: str) -> None:
        if response == RESPONSE_BACK:
            self.nav_view.pop_to_tag('main')  # refreshes through _on_page_popped
        else:
            self.refresh()

    def visible_exercise_page(self) -> ExercisePage | None:
        page = self.nav_view.get_visible_page()
        return page if isinstance(page, ExercisePage) else None

    # Handlers -------------------------------------------------------------------------

    def _on_exercise_activated(self, _page: HomePage, exercise_id: str) -> None:
        definition = self.model.definition(exercise_id)
        if definition is not None and definition.settings:
            self.open_setup(exercise_id)
        else:
            self.start_exercise(exercise_id)

    def _on_drill_requested(self, _page: ProgressPage, item_ids: tuple) -> None:
        self.start_session(SessionMode.DRILL_WEAK, item_ids=tuple(item_ids))

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
