#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""UI smoke test that runs without pytest (``meson test``) and backs tests/ui/test_smoke.py.

It compiles the GResource bundle and the GSettings schema into a temporary
directory, instantiates the window, every page, dialog and answer widget with
the W1 stub data, answers questions through the keyboard accelerators and
checks the feedback states.

Exit status: 0 on success, 1 on failure, 77 (skipped) when GTK 4, libadwaita
1.10 or a display is not available.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from collections.abc import Callable
from pathlib import Path

SKIP = 77
ROOT = Path(__file__).resolve().parents[2]


def prepare(source_root: Path, workdir: Path) -> None:
    """Compile resources and schema, point GLib at them and make ``etude`` importable."""
    schema_dir = workdir / 'schemas'
    schema_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(source_root / 'data' / 'fi.oikarinenotto.etude.gschema.xml', schema_dir)
    subprocess.run(['glib-compile-schemas', str(schema_dir)], check=True)
    os.environ['GSETTINGS_SCHEMA_DIR'] = str(schema_dir)
    os.environ['GSETTINGS_BACKEND'] = 'memory'
    package = source_root / 'src' / 'etude'
    bundle = workdir / 'etude.gresource'
    subprocess.run(
        [
            'glib-compile-resources',
            f'--sourcedir={package}',
            f'--target={bundle}',
            str(package / 'etude.gresource.xml'),
        ],
        check=True,
    )
    sys.path.insert(0, str(source_root / 'src'))
    from gi.repository import Gio

    Gio.Resource.load(str(bundle))._register()


def unavailable_reason() -> str | None:
    """Why the GTK tests cannot run here, or ``None`` when they can."""
    for tool in ('glib-compile-resources', 'glib-compile-schemas'):
        if shutil.which(tool) is None:
            return f'{tool} not found'
    try:
        import gi

        gi.require_version('Gtk', '4.0')
        gi.require_version('Gdk', '4.0')
        gi.require_version('Adw', '1')
        from gi.repository import Adw, Gdk, Gtk
    except (ImportError, ValueError) as error:
        return f'GTK 4 and libadwaita are not available: {error}'
    if (Adw.get_major_version(), Adw.get_minor_version()) < (1, 10):
        return 'libadwaita 1.10 is required'
    # GTK 4 can initialise without a display, so check for one explicitly.
    if not Gtk.init_check() or Gdk.Display.get_default() is None:
        return 'no display'
    Adw.init()  # registers the Adw types used by templates (Adw.Application does this)
    return None


def pump() -> None:
    from gi.repository import GLib

    context = GLib.MainContext.default()
    for _ in range(200):
        if not context.iteration(False):
            break


def load_css() -> None:
    """Apply style.css as the application would (screenshots need it)."""
    from gi.repository import Gdk, Gtk

    provider = Gtk.CssProvider()
    provider.load_from_resource('/fi/oikarinenotto/etude/style.css')
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


# Checks ------------------------------------------------------------------------


def new_window(model=None):
    from etude.ui.preview import PreviewModel
    from etude.window import EtudeWindow

    window = EtudeWindow(model if model is not None else PreviewModel())
    window.present()
    pump()
    return window


def press(page, key: str, shift: bool = False) -> bool:
    from gi.repository import Gdk

    keyval = Gdk.keyval_from_name(key)
    state = Gdk.ModifierType.SHIFT_MASK if shift else Gdk.ModifierType(0)
    if shift:
        keyval = Gdk.keyval_to_upper(keyval)
    return page.handle_key(keyval, state)


def check_window_and_sections() -> None:
    from etude.ui.pages.home import ExerciseCard
    from etude.window import sections

    window = new_window()
    try:
        assert window.home_page.layout_stack.get_visible_child_name() == 'grid'
        cards = [c.get_child() for c in _children(window.home_page.card_grid)]
        assert len(cards) == 6
        assert all(isinstance(c, ExerciseCard) for c in cards)
        assert window.home_page.sort_button.get_label() == 'Sort: Recent'
        window.home_page.activate_action('home.sort', _variant('name'))
        first = _children(window.home_page.card_grid)[0].get_child()
        assert first.card.title == 'Chords — Staff', first.card.title
        for section in sections():
            if not section.heading:
                page = window.show_section(section.id)
                assert window.split_view.get_content() is page
        window.show_section('ear')
        assert len(window.home_page.visible_cards()) == 1
        window.show_section('rhythm')
        assert window.home_page.layout_stack.get_visible_child_name() == 'empty'
        window.show_section('all')
        window.compact = True
        assert window.home_page.layout_stack.get_visible_child_name() == 'list'
        window.compact = False
    finally:
        window.destroy()


def check_keysig_correct_then_next() -> None:
    window = new_window()
    try:
        page = window.start_exercise('keysig')
        pump()
        assert window.visible_exercise_page() is page
        assert page.window_title.get_subtitle().startswith('Question 7 of 20 · Treble clef')
        assert press(page, '5')  # E major
        assert page.feedback is not None
        assert page.feedback.correct
        assert page.feedback_banner.has_css_class('feedback-success')
        assert page.feedback_banner.title.get_label() == 'Correct — E major'
        assert page.answer_widget.buttons['E'].has_css_class('success')
        assert 'Answered in' in page.feedback_banner.detail.get_label()
        assert press(page, 'Return')
        assert page.feedback is None
        assert page.window_title.get_subtitle().startswith('Question 8 of 20')
        assert press(page, 'question')  # hint
        assert page.hint_revealer.get_reveal_child()
        assert press(page, 'space')  # skip: shows the answer
        assert page.feedback is not None
        assert not page.feedback.correct
        assert page.feedback_banner.title.get_label().startswith('Skipped — the answer is')
        assert press(page, 'Return')
        assert page.window_title.get_subtitle().startswith('Question 9 of 20')
        page.pause_button.set_active(True)
        assert page.state_stack.get_visible_child_name() == 'paused'
        assert not press(page, '5')
        page.pause_button.set_active(False)
        page.compact = True
        assert page.window_title.get_subtitle() == '9 / 20'
        page.compact = False
    finally:
        window.destroy()


def check_interval_wrong() -> None:
    window = new_window()
    try:
        page = window.start_exercise('interval-staff')
        assert page.play_button.get_visible()
        assert page.play_content.get_label() == 'Play interval'
        assert press(page, '6')  # minor sixth: wrong
        grid = page.answer_widget
        assert grid.buttons['m6'].has_css_class('error')
        assert grid.buttons['M6'].has_css_class('success')
        assert page.feedback_banner.has_css_class('feedback-error')
        assert page.feedback_banner.title.get_label() == 'Not quite — the answer is a major sixth'
        assert page.feedback_banner.play_button.get_visible()
        assert page.streak_label.get_label() == 'Streak reset'
        assert not press(page, '7'), 'answers are locked after answering'
        page.feedback_banner.play_button.emit('clicked')
        assert window.model.played, 'play-requested was not emitted'
    finally:
        window.destroy()


def check_note_naming_piano() -> None:
    from etude.core import PitchName
    from etude.core.pitch import Letter

    window = new_window()
    try:
        page = window.start_exercise('note-naming')
        piano = page.answer_widget
        values = []
        piano.connect('answered', lambda _w, v: values.append(v))
        assert press(page, 'f')
        assert values == [PitchName(Letter.F)]
        assert page.feedback.correct
        assert page.feedback_banner.title.get_label() == 'Correct — F4'
        assert piano.keyboard.find(PitchName(Letter.F)).has_css_class('success')
        press(page, 'Return')
        piano = page.answer_widget
        piano.connect('answered', lambda _w, v: values.append(v))
        assert press(page, 'a', shift=True)
        assert values[-1] == PitchName(Letter.A, 1)
        assert piano.keyboard.find(PitchName(Letter.A, 1)).has_css_class('error')
        # Narrow layout: letter buttons and the keyboard in a bottom sheet.
        press(page, 'Return')
        page.compact = True
        piano = page.answer_widget
        assert piano._stack.get_visible_child_name() == 'compact'
        piano.emit('sheet-requested')
        assert page.bottom_sheet.get_open()
        page.compact = False
    finally:
        window.destroy()


def check_chips() -> None:
    window = new_window()
    try:
        page = window.start_exercise('chord-staff')
        chips = page.answer_widget
        assert not chips.check_button.get_sensitive()
        assert press(page, 'e')
        assert press(page, '2')
        assert press(page, '6')
        assert chips.summary.get_label() == 'Your answer so far: E, Minor, Root position'
        assert chips.check_button.get_sensitive()
        assert press(page, 'Return')
        assert page.feedback.correct
        assert chips.chips['quality']['minor'].has_css_class('success')
    finally:
        window.destroy()


def check_scale_degree_and_ear() -> None:
    window = new_window()
    try:
        page = window.start_exercise('scale-degree')
        assert page.answer_widget.buttons['5'].option.description == 'Dominant'
        assert press(page, '5')
        assert page.feedback.correct

        page = window.start_exercise('interval-ear')
        pump()
        assert page.show_staff_button.get_visible()
        assert not page.pause_button.get_visible()
        panel = page.ear_panel
        assert panel is not None
        before = panel.play_count
        assert press(page, 'r')
        assert panel.play_count == before + 1
        assert panel.context_label.get_label() == 'Root: C4'
        panel.mode_group.set_active_name('harmonic')
        panel.play()
        spec = window.model.played[-1]
        assert all(n.start == 0 for n in spec.notes), 'harmonic playback starts together'
        assert not page._figure_holder.get_visible()
        page.show_staff_button.set_active(True)
        assert page._figure_holder.get_visible()
        assert press(page, '3')  # minor third: wrong
        assert page.feedback_banner.has_css_class('feedback-error')
    finally:
        window.destroy()


def check_text_and_placeholders() -> None:
    from etude.ui import preview
    from etude.ui.pages.exercise import ExercisePage

    questions = preview.preview_questions()
    page = ExercisePage('Vocabulary')
    page.show_question(questions['vocabulary'].question, number=1, total=5)
    text = page.answer_widget
    given = []
    text.connect('answered', lambda _w, v: given.append(v))
    text.entry.set_text('crescendo')
    text.entry.emit('activate')
    assert given == ['crescendo']
    page.show_question(questions['construction'].question, number=1, total=5)
    assert type(page.answer_widget).__name__ == 'StaffInputView'
    page.show_question(questions['rhythm-dictation'].question, number=1, total=5)
    assert type(page.answer_widget).__name__ == 'RhythmInputView'
    page.show_question(questions['rhythm-tap'].question, number=1, total=5)
    assert type(page.answer_widget).__name__ == 'TapPadView'


def check_progress() -> None:
    from etude.ui import preview
    from etude.ui.pages.progress import ProgressPage

    page = ProgressPage(preview.progress)
    assert len(_children(page.stat_cards)) == 3
    assert page.drill_button.get_label() == 'Drill these 15 items'
    page.period_group.set_active_name('month')
    assert page.data.answered[-1][0] == 'This week'
    drilled = []
    page.connect('drill-requested', lambda _p, items: drilled.append(items))
    page.drill_button.emit('clicked')
    assert len(drilled[0]) == 4


def check_setup() -> None:
    from gi.repository import Adw

    from etude.ui import preview
    from etude.ui.common import get_settings
    from etude.ui.pages.setup import SetupPage

    page = SetupPage(preview.PreviewKeySignatures())
    assert page.get_title() == 'Key Signatures — Setup'
    assert isinstance(page.rows['clefs'], Adw.ExpanderRow)
    assert isinstance(page.rows['max-accidentals'], Adw.SpinRow)
    assert isinstance(page.rows['mode'], Adw.ComboRow)
    assert isinstance(page.rows['ask-relative'], Adw.SwitchRow)
    page.rows['max-accidentals'].set_value(3)
    page.rows['mode'].set_selected(2)
    stored = get_settings().get_value('exercise-settings').unpack()
    assert stored['keysig']['max-accidentals'] == 3
    assert stored['keysig']['mode'] == 'both'
    assert stored['keysig']['clefs'] == ['treble', 'bass']
    page.timed_row.set_active(True)
    assert get_settings().get_boolean('timed-mode')
    page.questions_row.set_value(30)
    assert get_settings().get_uint('questions-per-session') == 30
    started = []
    page.connect('start', lambda _p, ex, values: started.append((ex, values)))
    page.start_button.emit('clicked')
    assert started[0][0] == 'keysig'
    # Values are restored from GSettings.
    again = SetupPage(preview.PreviewKeySignatures())
    assert again.rows['max-accidentals'].get_value() == 3
    get_settings().reset('exercise-settings')
    get_settings().reset('timed-mode')
    get_settings().reset('questions-per-session')


def check_dialogs() -> None:
    from gi.repository import Gtk

    from etude.ui import preview
    from etude.ui.common import get_settings
    from etude.ui.dialogs.preferences import PreferencesDialog
    from etude.ui.dialogs.session_summary import create_session_summary_dialog

    dialog = create_session_summary_dialog(
        preview.sample_summary(), 'Key Signatures · 20 questions · treble clef'
    )
    assert dialog.has_response('again')
    assert dialog.has_response('review')
    assert dialog.get_response_label('review') == '_Review 2 Mistakes'
    prefs = PreferencesDialog()
    prefs.instrument_row.set_selected(2)
    assert get_settings().get_string('instrument') == 'guitar'
    get_settings().set_string('note-naming', 'fixed-do')
    assert prefs.note_naming_row.get_selected() == 3
    prefs.large_notation_row.set_active(True)
    assert get_settings().get_boolean('large-notation')
    for key in ('instrument', 'note-naming', 'large-notation'):
        get_settings().reset(key)
    builder = Gtk.Builder.new_from_resource('/fi/oikarinenotto/etude/shortcuts-dialog.ui')
    assert builder.get_object('shortcuts_dialog') is not None


def check_session_summary_flow() -> None:
    window = new_window()
    try:
        window.start_exercise('keysig')
        controller = window.controller
        controller.session.index = controller.session.total  # jump to the end
        dialog = controller.finish()
        pump()
        assert window.get_visible_dialog() is dialog
        dialog.close()
    finally:
        window.destroy()


def check_live_session() -> None:
    """A real key-signature session against a fresh database, end to end."""
    import tempfile

    from etude.audio.null import NullBackend
    from etude.services import Services
    from etude.ui.common import get_settings
    from etude.ui.model import LiveModel

    with tempfile.TemporaryDirectory() as data_dir:
        services = Services.open(Path(data_dir))
        services._audio = NullBackend()
        model = LiveModel(services, get_settings())
        get_settings().set_uint('questions-per-session', 5)
        window = new_window(model)
        try:
            ids = [c.id for c in window.cards]
            assert 'keysig' in ids, ids
            page = window.start_exercise('keysig')
            assert page is not None
            assert page.get_title() == 'Key Signatures'
            controller = window.controller
            for number in range(1, 6):
                assert page.window_title.get_subtitle().startswith(f'Question {number} of 5')
                assert page._figure_holder.get_visible(), 'the staff is shown'
                expected = page.question.expected
                page.answer_widget.submit(expected)
                assert page.feedback.correct, page.feedback.title
                if number < 5:
                    assert press(page, 'Return')
            assert press(page, 'Return')
            pump()
            assert controller.summary is not None
            assert controller.summary.correct == 5
            dialog = window.get_visible_dialog()
            assert dialog is not None
            dialog.close()
            window.refresh()
            card = next(c for c in window.cards if c.id == 'keysig')
            assert card.accuracy == 1.0
            assert window.model.streak().practised_today
            progress = window.model.progress('week')
            assert progress.by_exercise == (('Key Signatures', 1.0),)
        finally:
            get_settings().reset('questions-per-session')
            window.destroy()
            services.close()


def check_today_preview() -> None:
    from gi.repository import Gtk

    from etude.learning.model import SessionMode
    from etude.ui.preview import PreviewModel

    window = new_window()
    try:
        assert window.rows['today'].count_label.get_visible()
        assert window.rows['today'].count_label.get_label() == '24'
        page = window.show_section('today')
        assert page is window.today_page
        assert page.hero_stack.get_visible_child_name() == 'review'
        assert page.due_label.get_label() == '24 items due'
        assert page.review_detail.get_label() == '5 new items to learn · 20 questions per session'
        assert page.start_button.get_label() == '_Start Review'
        assert page.goal_number.get_label() == '18 of 30'
        assert page.goal_bar.get_value() == 18
        assert not page.goal_icon.get_visible()
        assert page.goal_detail.get_label() == '12 more questions to reach today’s goal'
        assert page.streak_detail.get_label() == 'Meet today’s goal to make it 13 days'
        assert len(page._due_rows) == 4
        assert page.due_group.get_visible()
        window.compact = True
        assert page.review_box.get_orientation() == Gtk.Orientation.VERTICAL
        assert page.start_button.get_halign() == Gtk.Align.FILL
        window.compact = False
        assert page.review_box.get_orientation() == Gtk.Orientation.HORIZONTAL
        page._due_rows[1].emit('activated')
        assert window.model.started[-1][:2] == (SessionMode.EXERCISE, 'keysig')
        window.nav_view.pop_to_tag('main')
        page.start_button.emit('clicked')
        pump()
        assert window.model.started[-1][0] is SessionMode.DAILY_REVIEW
        assert window.visible_exercise_page() is not None
    finally:
        window.destroy()

    window = new_window(PreviewModel(caught_up=True))
    try:
        assert not window.rows['today'].count_label.get_visible()
        page = window.show_section('today')
        assert page.hero_stack.get_visible_child_name() == 'caught-up'
        assert page.caught_up_detail.get_label().startswith('Nothing is due for review.')
        assert not page.due_group.get_visible()
        assert page.goal_icon.get_visible()
        assert page.goal_bar.has_css_class('goal-met')
        assert page.goal_detail.get_label() == 'Today’s goal is met'
        page.browse_button.emit('clicked')
        assert window.split_view.get_content() is window.home_page
    finally:
        window.destroy()


def check_continue_banner_preview() -> None:
    window = new_window()
    try:
        home = window.home_page
        assert home.continue_revealer.get_reveal_child()
        assert home.continue_title.get_label() == 'Intervals — by ear'
        assert home.continue_detail.get_label() == '7 of 20 answered · 64% accuracy'
        home.resume_button.emit('clicked')
        pump()
        page = window.visible_exercise_page()
        assert page is not None
        assert not home.continue_revealer.get_reveal_child()
        assert press(page, 'Escape')
        pump()
        assert window.visible_exercise_page() is None
        assert home.continue_revealer.get_reveal_child(), 'closing keeps the session'
        home.dismiss_button.emit('clicked')
        assert not home.continue_revealer.get_reveal_child()
        assert window.model.continue_data() is None
    finally:
        window.destroy()


def check_progress_empty() -> None:
    from etude.ui import preview
    from etude.ui.pages.progress import ProgressPage

    page = ProgressPage(preview.empty_progress)
    assert not page.drill_button.get_visible()
    assert page.accuracy_empty.get_visible()
    assert page.weakest_group.get_description().startswith('No weak items yet.')
    accuracy_card = _children(page.stat_cards)[1].get_child()
    labels = [w.get_label() for w in _children(accuracy_card)]
    assert labels[1] == '—', labels
    assert labels[2] == 'No answers yet', labels
    page.period_group.set_active_name('all')
    assert not page.drill_button.get_visible()
    # With data, the empty notes go away again.
    page.set_data(preview.progress('week'))
    assert page.drill_button.get_visible()
    assert not page.accuracy_empty.get_visible()
    assert not page.weakest_group.get_description()


class _Clock:
    """A clock for LiveModel that the test moves forward."""

    def __init__(self) -> None:
        from datetime import UTC, datetime

        self.now = datetime.now(UTC)

    def __call__(self):
        return self.now

    def advance(self, **kwargs) -> None:
        from datetime import timedelta

        self.now += timedelta(**kwargs)


def _live_window(data_dir: str, clock=None):
    from etude.audio.null import NullBackend
    from etude.services import Services
    from etude.ui.common import get_settings
    from etude.ui.model import LiveModel

    services = Services.open(Path(data_dir))
    services._audio = NullBackend()
    model = LiveModel(services, get_settings(), clock=clock)
    get_settings().set_uint('questions-per-session', 5)
    return new_window(model), services


def _close_live(window, services) -> None:
    from etude.ui.common import get_settings

    for key in ('questions-per-session', 'daily-goal'):
        get_settings().reset(key)
    window.model.shutdown()
    window.destroy()
    services.close()


def _answer(page, count: int, *, last: bool = False) -> None:
    """Answer ``count`` questions correctly; move on after each one unless ``last``."""
    for n in range(count):
        page.answer_widget.submit(page.question.expected)
        assert page.feedback is not None
        assert page.feedback.correct, page.feedback.title
        if n < count - 1 or not last:
            assert press(page, 'Return')
    pump()


def check_live_new_learner() -> None:
    """Empty states with real data: home cards, Today and progress for a brand-new learner."""
    import tempfile

    from etude.ui.pages.home import ExerciseCard

    with tempfile.TemporaryDirectory() as data_dir:
        window, services = _live_window(data_dir)
        try:
            assert all(c.accuracy is None and c.sessions == 0 for c in window.cards)
            card = next(
                c.get_child()
                for c in _children(window.home_page.card_grid)
                if isinstance(c.get_child(), ExerciseCard)
            )
            texts = [w.get_label() for w in _children(_children(card.get_child())[-1])]
            assert texts == ['Not started'], texts
            assert not window.home_page.continue_revealer.get_reveal_child()
            today = window.model.today()
            assert today.due == 0
            assert today.new > 0
            page = window.show_section('today')
            assert page.hero_stack.get_visible_child_name() == 'review'
            assert page.start_button.get_label() == '_Learn New Items'
            assert not page.due_group.get_visible()
            assert page.goal_number.get_label() == '0 of 30'
            assert not window.rows['today'].count_label.get_visible()
            progress = window.model.progress('week')
            assert progress.accuracy is None
            assert progress.accuracy_change is None
            assert progress.weakest == ()
            assert progress.drill_count == 0
            window.show_section('progress')
            assert not window.progress_page.drill_button.get_visible()
            for period in ('month', 'all'):
                window.progress_page.period_group.set_active_name(period)
                assert window.progress_page.data.sessions == 0
            window.progress_page.period_group.set_active_name('week')
        finally:
            _close_live(window, services)


def check_live_resume_session() -> None:
    """Close a real session after two answers, resume it from the banner and finish it."""
    import tempfile

    with tempfile.TemporaryDirectory() as data_dir:
        clock = _Clock()
        window, services = _live_window(data_dir, clock)
        model = window.model
        home = window.home_page
        try:
            page = window.start_exercise('keysig')
            _answer(page, 2)
            assert page.window_title.get_subtitle().startswith('Question 3 of 5')
            clock.advance(minutes=1)
            assert press(page, 'Escape')
            pump()
            assert window.visible_exercise_page() is None
            data = model.continue_data()
            assert data is not None
            assert (data.exercise_id, data.answered, data.total) == ('keysig', 2, 5)
            assert home.continue_revealer.get_reveal_child()
            assert home.continue_title.get_label() == 'Key Signatures'
            assert home.continue_detail.get_label() == '2 of 5 answered · 100% accuracy'
            assert model.progress('week').sessions == 0, 'not finished yet'
            clock.advance(hours=2)  # away: not practice
            home.resume_button.emit('clicked')
            pump()
            page = window.visible_exercise_page()
            assert page is not None
            assert page.window_title.get_subtitle().startswith('Question 3 of 5')
            assert not home.continue_revealer.get_reveal_child()
            _answer(page, 3, last=True)
            assert press(page, 'Return')
            pump()
            summary = window.controller.summary
            assert summary is not None
            assert (summary.total, summary.correct) == (5, 5), summary
            assert summary.duration_ms < 60 * 60 * 1000, 'the two hours away do not count'
            dialog = window.get_visible_dialog()
            assert dialog.get_body().startswith('Key Signatures · 5 questions · '), (
                dialog.get_body()
            )
            assert not dialog.has_response('review'), 'no mistakes, nothing to review'
            dialog.close()
            pump()
            assert window.visible_exercise_page() is None
            assert model.continue_data() is None
            assert model.progress('week').sessions == 1
            card = next(c for c in window.cards if c.id == 'keysig')
            assert (card.accuracy, card.sessions) == (1.0, 1)

            # Close after one answer, then dismiss: the session is finished and counts.
            page = window.start_exercise('keysig')
            _answer(page, 1)
            window.nav_view.pop_to_tag('main')  # any way of leaving keeps the session
            pump()
            assert home.continue_revealer.get_reveal_child()
            home.dismiss_button.emit('clicked')
            assert model.continue_data() is None
            assert model.progress('week').sessions == 2

            # Close before answering: nothing to resume, no session counted.
            page = window.start_exercise('keysig')
            assert press(page, 'Escape')
            pump()
            assert model.continue_data() is None
            assert model.progress('week').sessions == 2

            # Starting another session finishes an interrupted one.
            page = window.start_exercise('keysig')
            _answer(page, 1)
            assert press(page, 'Escape')
            pump()
            assert model.continue_data() is not None
            window.start_exercise('keysig')
            assert model.continue_data() is None
            assert model.progress('week').sessions == 3
        finally:
            _close_live(window, services)


def check_live_today_review() -> None:
    """Due items on the Today page, the daily review, and the daily-goal setting."""
    import tempfile

    from etude.ui.common import get_settings

    with tempfile.TemporaryDirectory() as data_dir:
        clock = _Clock()
        window, services = _live_window(data_dir, clock)
        model = window.model
        try:
            page = window.start_exercise('keysig')
            _answer(page, 5, last=True)
            assert press(page, 'Return')
            pump()
            window.get_visible_dialog().close()
            pump()
            clock.advance(days=60)  # fast correct answers are scheduled far ahead
            window.refresh()
            today = model.today()
            assert today.due > 0
            assert today.by_exercise[0].exercise_id == 'keysig'
            assert window.rows['today'].count_label.get_label() == str(today.due)
            assert today.answered_today == 0, 'a new day'
            page = window.show_section('today')
            assert page.due_label.get_label().endswith('due')
            assert page.start_button.get_label() == '_Start Review'
            page.start_button.emit('clicked')
            pump()
            exercise = window.visible_exercise_page()
            assert exercise is not None
            assert exercise.get_title() == 'Daily Review'
            total = window.controller.session.total
            _answer(exercise, total, last=True)
            assert press(exercise, 'Return')
            pump()
            dialog = window.get_visible_dialog()
            assert dialog.get_body() == f'Daily Review · {total} questions', dialog.get_body()
            dialog.close()
            pump()
            assert model.today().answered_today == total
            # The daily goal applies without a restart.
            get_settings().set_uint('daily-goal', 5)
            assert model.stats.config.daily_goal == 5
            assert window.today_page.data.daily_goal == 5
            assert window.today_page.data.goal_met == (total >= 5)
        finally:
            _close_live(window, services)


def check_live_exercises_fit_and_compare() -> None:
    """Every real exercise fits the 400 px layout before and after answering, ear
    questions offer the learner's own answer for comparison, and chord questions
    hide the interval-only Melodic/Harmonic toggle."""
    import tempfile

    from gi.repository import Gtk

    from etude.audio.null import NullBackend
    from etude.exercises.base import ChoiceAnswer
    from etude.services import Services
    from etude.ui.common import get_settings
    from etude.ui.model import LiveModel

    def min_width(page) -> int:
        return page.measure(Gtk.Orientation.HORIZONTAL, -1)[0]

    with tempfile.TemporaryDirectory() as data_dir:
        services = Services.open(Path(data_dir))
        services._audio = NullBackend()
        window = new_window(LiveModel(services, get_settings()))
        try:
            window.compact = True
            for exercise_id in services.registry.exercise_ids():
                page = window.start_exercise(exercise_id, replace=True)
                assert page is not None, exercise_id
                pump()
                assert min_width(page) <= 400, (exercise_id, min_width(page))
                question = page.question
                if exercise_id == 'chord-ear':
                    assert not page.ear_panel.mode_box.get_visible()
                if exercise_id == 'interval-ear':
                    assert page.ear_panel.mode_box.get_visible()
                if isinstance(question.answer, ChoiceAnswer):
                    wrong = next(
                        o.key for o in question.answer.options if o.key != question.expected
                    )
                    page.answer_widget.submit(wrong)
                else:
                    page.answer_widget.submit(question.expected)
                pump()
                assert min_width(page) <= 400, (exercise_id, 'answered', min_width(page))
                if question.playback_is_question and isinstance(question.answer, ChoiceAnswer):
                    banner = page.feedback_banner
                    assert banner.play_given_button.get_visible(), exercise_id
                    banner.play_given_button.emit('clicked')
        finally:
            window.destroy()
            services.close()


def check_reveal_details() -> None:
    """Chips mark roots chosen with ♯/♭; a right letter in the wrong octave is not
    also marked wrong."""
    from etude.core import Pitch
    from etude.exercises.base import ChipGroup, ChipsAnswer, Option, PianoAnswer
    from etude.ui.widgets.chips import ChipGroups
    from etude.ui.widgets.piano import PianoAnswerView

    letters = tuple(Option(letter, letter, accel=letter.lower()) for letter in 'CDEFGAB')
    spec = ChipsAnswer((ChipGroup('root', 'Root', letters, accidentals=True),))
    chips = ChipGroups(spec)
    from gi.repository import Gdk

    assert chips.handle_key(Gdk.KEY_F, Gdk.ModifierType.SHIFT_MASK)
    assert chips.value() == {'root': 'F#'}
    chips.reveal({'root': 'F#'}, {'root': 'F#'}, True)
    assert chips.chips['root']['F'].has_css_class('success')
    chips = ChipGroups(spec)
    chips.reveal({'root': 'Eb'}, {'root': 'E'}, False)
    assert chips.chips['root']['E'].has_css_class('success')
    assert chips._accidental_chips['root'].has_css_class('error')

    piano = PianoAnswerView(PianoAnswer(Pitch.parse('C3'), Pitch.parse('C5'), octave_matters=True))
    piano.reveal(Pitch.parse('G4'), Pitch.parse('G3'), False)
    button = piano.letter_buttons[Pitch.parse('G4').letter]
    assert button.has_css_class('success')
    assert not button.has_css_class('error')


# The learning path -------------------------------------------------------------


def _finish_session(window, page) -> None:
    """Answer every remaining question correctly until the summary dialog shows."""
    for _ in range(200):
        page.answer_widget.submit(page.question.expected)
        assert page.feedback is not None
        assert press(page, 'Return')
        pump()
        if window.controller.summary is not None:
            return
    raise AssertionError('the session did not end')


def _reset_path_settings() -> None:
    from etude.ui.common import get_settings

    for key in ('passed-levels', 'placed-units', 'completed-lessons'):
        get_settings().reset(key)


def check_lesson_preview() -> None:
    """Every kind of lesson block, glossary links, fading worked steps and checks."""
    from etude.ui.content import CheckView, WorkedExampleView
    from etude.ui.preview import PreviewModel

    window = new_window(PreviewModel(caught_up=True))  # the lesson is not completed yet
    try:
        page = window.open_lesson('l1.staff')
        pump()
        assert window.visible_lesson_page() is page
        assert page.title_label.get_label() == 'Staff, Clefs and Note Names'
        sections = _children(page.sections_box)
        assert len(sections) == 2
        css = {
            name
            for section in sections
            for child in _children(section)
            for name in child.get_css_classes()
        }
        assert {'callout-tip', 'callout-remember', 'callout-warning', 'lesson-figure'} <= css
        assert {'lesson-list', 'worked-example', 'check-card'} <= css
        text = _children(sections[0])[1].get_label()
        assert '<a href="term:staff">staff</a>' in text, text
        assert '<i>on</i>' in text

        worked = page.worked[0]
        assert isinstance(worked, WorkedExampleView)
        assert worked.shown == 1
        assert worked.next_button.get_label() == '_Next Step (2 of 3)'
        worked.next_button.emit('clicked')
        worked.next_button.emit('clicked')
        assert worked.shown == 3
        assert not worked.next_button.get_visible()

        check = page.checks[0]
        assert isinstance(check, CheckView)
        completed = []
        page.connect('completed', lambda _p, lesson_id: completed.append(lesson_id))
        check.buttons['a'].emit('clicked')  # wrong
        assert check.buttons['a'].has_css_class('error')
        assert check.buttons['b'].has_css_class('success')
        assert check.feedback.has_css_class('feedback-error')
        assert check.feedback_title.get_label() == 'Not quite — the answer is B4'
        assert check.retry_button.get_visible()
        assert completed == ['l1.staff'], 'answering every check completes the lesson'
        assert window.model.completed_lessons == {'l1.staff'}
        check.retry_button.emit('clicked')
        assert check.chosen is None
        check.buttons['b'].emit('clicked')
        assert check.feedback.has_css_class('feedback-success')
        assert not check.retry_button.get_visible()
        assert page.end_icon.has_css_class('success')

        # Playing an example goes through the model.
        figure = next(
            child for child in _children(sections[0]) if child.has_css_class('lesson-figure')
        )
        _children(figure)[-1].emit('clicked')
        assert window.model.played, 'the example was not played'

        # A term opens the glossary dialog; links inside it open further entries.
        page.emit('term-activated', 'clef')
        pump()
        dialog = window.glossary_dialog
        assert dialog is not None
        assert window.get_visible_dialog() is dialog
        assert dialog.shown == ['clef']
        assert dialog.show_entry('treble-clef')
        assert dialog.shown == ['clef', 'treble-clef']
        dialog.nav_view.pop()
        pump()
        assert dialog.shown == ['clef']
        dialog.force_close()
        pump()
        assert window.glossary_dialog is None

        page.compact = True
        assert page.practise_button.get_halign().value_nick == 'fill'
        page.practise_button.emit('clicked')
        pump()
        assert window.model.path_started[-1] == ('unit', 'l1.staff')
        assert window.visible_exercise_page() is not None
    finally:
        window.destroy()


def check_glossary_search() -> None:
    from etude.learning.model import SessionMode

    window = new_window()
    try:
        page = window.show_section('glossary')
        assert page is window.glossary_page
        assert page.practise_button.get_visible()
        assert len(page.visible_entries) == 9
        assert page.results_stack.get_visible_child_name() == 'list'
        page.search_entry.set_text('louder')
        page._filter()
        assert page.visible_entries == ['crescendo']
        page.search_entry.set_text('CRESC.')
        page._filter()
        assert page.visible_entries == ['crescendo'], 'abbreviations are found too'
        page.search_entry.set_text('lied')
        page._filter()
        assert page.visible_entries == ['lied']
        group = page._groups[1][0]
        assert group.get_title() == 'Level 2 · Diatonic Harmony'
        assert not page._groups[0][0].get_visible(), 'a group without matches hides'
        page.search_entry.set_text('zzz')
        page._filter()
        assert page.results_stack.get_visible_child_name() == 'empty'
        page.search_entry.set_text('')
        page._filter()
        page.rows['crescendo'].emit('activated')
        pump()
        dialog = window.glossary_dialog
        assert dialog is not None
        assert dialog.get_title() == 'crescendo'
        dialog.force_close()
        page.practise_button.emit('clicked')
        pump()
        assert window.model.started[-1][:2] == (SessionMode.EXERCISE, 'vocabulary')
    finally:
        window.destroy()


def check_path_preview() -> None:
    from etude.ui.preview import PreviewModel

    window = new_window()
    try:
        page = window.show_section('path')
        assert page is window.path_page
        assert not page.placement_box.get_visible()
        assert len(page.unit_cards) == 8
        current = page.unit_cards['l1.accidentals']
        assert current.has_css_class('current-unit')
        assert current.practise_button.has_css_class('suggested-action')
        assert current.status_label.get_label() == '61% mastered · 22 of 36 items'
        staff = page.unit_cards['l1.staff']
        assert staff.status_label.get_label() == 'Mastered'
        assert staff.lesson_button is not None
        rhythm = page.unit_cards['l1.rhythm']
        assert rhythm.practise_button is None, 'a lesson-only unit has nothing to practise'
        locked = page.unit_cards['l1.major']
        assert locked.has_css_class('locked')
        assert locked.status_label.get_label().startswith('Master “Accidentals')
        exam = page.exam_cards['level1']
        assert exam.button.get_label() == 'Take Exam'
        # Theory lists the units with lessons.
        theory = window.show_section('theory')
        assert list(theory.rows) == ['l1.staff']
        assert theory.coming_label.get_visible()
        theory.rows['l1.staff'].emit('activated')
        pump()
        assert window.visible_lesson_page() is not None
        window.nav_view.pop_to_tag('main')
        pump()
        window.show_section('path')
        # Practising a locked unit asks first; cancelling does nothing.
        locked.practise_button.emit('clicked')
        pump()
        dialog = window.confirm_dialog
        assert dialog is not None
        assert dialog.get_body().startswith('You haven’t mastered “Accidentals')
        dialog.emit('response', 'cancel')
        assert window.model.path_started == []
        page.unit_cards['l1.major'].practise_button.emit('clicked')
        window.confirm_dialog.emit('response', 'practise')
        pump()
        assert window.model.path_started[-1] == ('unit', 'l1.major')
        exercise = window.visible_exercise_page()
        assert exercise.get_title() == 'Major Scales and Keys'
        window.nav_view.pop_to_tag('main')
        pump()
        # The exam before every unit is unlocked also asks, then shows its outcome.
        page.exam_cards['level1'].button.emit('clicked')
        window.confirm_dialog.emit('response', 'practise')
        pump()
        assert window.model.path_started[-1] == ('exam', 'level1')
        controller = window.controller
        controller.session.index = controller.session.total
        summary = controller.finish()
        pump()
        labels = _all_labels(summary.get_extra_child())
        assert 'Level 1 Passed' in labels, labels
        summary.force_close()
        window.nav_view.pop_to_tag('main')
        pump()
        window.compact = True  # cards were rebuilt when the sessions ended
        card = page.unit_cards['l1.accidentals']
        assert card is not current
        assert card.main.get_orientation().value_nick == 'vertical'
        assert card.actions.get_homogeneous()
        window.compact = False
    finally:
        window.destroy()

    window = new_window(PreviewModel(caught_up=True))
    try:
        page = window.show_section('path')
        assert page.placement_box.get_visible()
        assert page.unit_cards['l1.staff'].practise_button.has_css_class('suggested-action')
        page.placement_button.emit('clicked')
        pump()
        assert window.model.path_started[-1] == ('placement', '')
        controller = window.controller
        assert controller.session.title == 'Placement Test'
        controller.session.index = controller.session.total
        summary = controller.finish()
        pump()
        assert 'You Placed Out of 3 Units' in _all_labels(summary.get_extra_child())
        summary.force_close()
    finally:
        window.destroy()


def _all_labels(widget) -> list[str]:
    from gi.repository import Gtk

    found = []
    if isinstance(widget, Gtk.Label):
        found.append(widget.get_label())
    for child in _children(widget):
        found.extend(_all_labels(child))
    return found


def check_live_lesson_and_glossary() -> None:
    """The real reference lesson and glossary against a fresh database."""
    import tempfile

    from etude.ui.common import get_settings

    with tempfile.TemporaryDirectory() as data_dir:
        window, services = _live_window(data_dir)
        try:
            data = window.model.path()
            staff = data.unit('l1.staff')
            assert staff.lesson_id == 'l1.staff'
            assert staff.unlocked
            assert not staff.lesson_done
            page = window.open_lesson('l1.staff')
            pump()
            assert page.title_label.get_label() == 'Staff, Clefs and Note Names'
            assert len(page.checks) == 3
            assert len(page.worked) == 1
            assert page.practise_button.get_visible()
            for check in page.checks:
                check.buttons[check.check.answer].emit('clicked')
                assert check.answered_correctly
            assert 'l1.staff' in get_settings().get_strv('completed-lessons')
            assert window.model.path().unit('l1.staff').lesson_done
            page.emit('term-activated', 'middle-c')
            pump()
            assert window.glossary_dialog is not None
            window.glossary_dialog.force_close()
            glossary = window.show_section('glossary')
            assert len(glossary.visible_entries) == len(window.model.glossary().entries)
            assert glossary.practise_button.get_visible() == (
                'vocabulary' in services.registry.exercise_ids()
            )
            glossary.search_entry.set_text('ledger')
            glossary._filter()
            assert 'ledger-line' in glossary.visible_entries
        finally:
            _reset_path_settings()
            _close_live(window, services)


def check_live_path_unit_practice() -> None:
    """A unit session asks only the unit's items; locked units are locked."""
    import tempfile

    with tempfile.TemporaryDirectory() as data_dir:
        window, services = _live_window(data_dir)
        try:
            page = window.show_section('path')
            data = window.model.path()
            assert data.placement_available
            assert data.current_unit == 'l1.staff'
            assert not data.unit('l1.accidentals').unlocked
            assert data.unit('l1.rhythm').missing == ('Staff, Clefs and Note Names',)
            assert page.placement_box.get_visible()
            page.unit_cards['l1.staff'].practise_button.emit('clicked')
            pump()
            exercise = window.visible_exercise_page()
            assert exercise is not None
            assert exercise.get_title() == 'Staff, Clefs and Note Names'
            session = window.controller.session
            assert 0 < session.total <= 5
            items = set(
                window.model.learning_path.unit_items(
                    window.model.library.curriculum.unit('l1.staff')
                )
            )
            assert all(q.item_id in items for q in session._plan)
            _finish_session(window, exercise)
            window.get_visible_dialog().close()
            pump()
            assert window.split_view.get_content() is window.path_page
            # Accidentals is locked: practising asks first.
            page.unit_cards['l1.accidentals'].practise_button.emit('clicked')
            assert window.confirm_dialog is not None
            window.confirm_dialog.emit('response', 'cancel')
        finally:
            _close_live(window, services)


def check_live_placement_and_exam() -> None:
    """Placement places out of every unit answered well; the level exam passes the level."""
    import tempfile

    from etude.ui.common import get_settings

    with tempfile.TemporaryDirectory() as data_dir:
        window, services = _live_window(data_dir)
        try:
            page = window.show_section('path')
            page.placement_button.emit('clicked')
            pump()
            exercise = window.visible_exercise_page()
            assert exercise.get_title() == 'Placement Test'
            _finish_session(window, exercise)
            dialog = window.get_visible_dialog()
            labels = _all_labels(dialog.get_extra_child())
            placed = get_settings().get_strv('placed-units')
            assert 'l1.staff' in placed
            assert 'l1.triads' in placed
            assert f'You Placed Out of {len(placed)} Units' in labels, labels
            dialog.close()
            pump()
            data = window.model.path()
            assert not data.placement_available
            assert all(u.unlocked for u in data.levels[0].units)
            assert data.levels[0].exam_ready
            assert window.path_page.exam_cards['level1'].button.has_css_class('suggested-action')
            window.path_page.exam_cards['level1'].button.emit('clicked')
            pump()
            exercise = window.visible_exercise_page()
            assert exercise.get_title() == 'Level 1 Exam'
            assert window.controller.session.total == 30
            _finish_session(window, exercise)
            dialog = window.get_visible_dialog()
            assert 'Level 1 Passed' in _all_labels(dialog.get_extra_child())
            assert get_settings().get_strv('passed-levels') == ['level1']
            dialog.close()
            pump()
            assert window.model.path().levels[0].passed
        finally:
            _reset_path_settings()
            _close_live(window, services)


def check_path_pages_fit_narrow() -> None:
    """Path, Theory, Glossary and a lesson fit the 400 px layout."""
    import tempfile

    from gi.repository import Gtk

    from etude.ui.preview import PreviewModel

    def min_width(widget) -> int:
        return widget.measure(Gtk.Orientation.HORIZONTAL, -1)[0]

    def check(window) -> None:
        window.compact = True
        for section in ('path', 'theory', 'glossary'):
            page = window.show_section(section)
            pump()
            assert min_width(page) <= 400, (section, min_width(page))
        page = window.open_lesson('l1.staff')
        pump()
        for check_view in page.checks:
            check_view.choose(next(o.key for o in check_view.check.options if not o.correct))
        for worked in page.worked:
            worked.reveal_next()
            worked.reveal_next()
        pump()
        assert min_width(page) <= 400, ('lesson', min_width(page))
        window.nav_view.pop_to_tag('main')

    for model in (PreviewModel(), PreviewModel(caught_up=True)):
        window = new_window(model)
        try:
            check(window)
        finally:
            window.destroy()
    with tempfile.TemporaryDirectory() as data_dir:
        window, services = _live_window(data_dir)
        try:
            check(window)
        finally:
            _reset_path_settings()
            _close_live(window, services)


def _gvariant(value):
    from gi.repository import GLib

    if isinstance(value, tuple):
        return GLib.Variant('as', list(value))
    if isinstance(value, bool):
        return GLib.Variant('b', value)
    if isinstance(value, int):
        return GLib.Variant('i', value)
    return GLib.Variant('s', str(value))


def _live_rhythm_window(data_dir: str, exercise_id: str, settings: dict):
    """A live window whose audio is a NullBackend that claims to be available, so the
    test drives beats and the end of playbacks with ``complete()``."""
    from gi.repository import GLib

    from etude.audio.null import NullBackend
    from etude.services import Services
    from etude.ui.common import get_settings
    from etude.ui.model import LiveModel

    services = Services.open(Path(data_dir))
    backend = NullBackend(available=True)
    services._audio = backend
    stored = {key: _gvariant(value) for key, value in settings.items()}
    get_settings().set_value('exercise-settings', GLib.Variant('a{sa{sv}}', {exercise_id: stored}))
    window = new_window(LiveModel(services, get_settings()))
    return window, services, backend


def check_tap_pad_flow() -> None:
    """Start with Enter, count in, tap on Space and the pad, see the graded timeline."""
    import tempfile

    from etude.ui.common import get_settings
    from etude.ui.widgets.tap_pad import TapPadView

    with tempfile.TemporaryDirectory() as data_dir:
        window, services, backend = _live_rhythm_window(
            data_dir, 'rhythm-tap', {'meters': ('4/4',), 'bars': 1, 'click': True}
        )
        get_settings().set_int('audio-latency-ms', 30)
        try:
            page = window.start_exercise('rhythm-tap')
            assert page is not None
            pad = page.answer_widget
            assert isinstance(pad, TapPadView)
            # Space does not skip a tap question: it is left to the tap pad.
            assert not press(page, 'space')
            assert page.feedback is None
            assert press(page, 'Return')  # Start
            assert pad.state == 'count-in'
            handle = backend.current
            assert handle is not None
            spec = handle.spec
            assert spec.count_in == 4
            assert spec.click
            assert spec.length == 4
            assert not spec.notes
            # Beat 0 sounds at t = 100 s; taps arrive 30 ms late (the calibrated delay).
            handle.started_at = 100.0
            expected = page.question.expected
            pad.tap(100.0 - 2.0)  # along with the count-in: ignored
            for index, onset in enumerate(expected):
                at = 100.0 + (onset + 30) / 1000
                if index == 0:
                    pad.keys.press(at)
                else:
                    pad.tap(at)
            assert len(pad.taps) == len(expected)
            assert all(abs(t - o) < 1e-6 for t, o in zip(pad.taps, expected, strict=True))
            # R must not replay the example during a take.
            assert press(page, 'r')
            backend.complete()  # beats, then the end of the take
            pump()
            assert page.feedback is not None
            assert page.feedback.correct, page.feedback.title
            assert page.feedback.title == 'Correct — every note on time'
            view = pad.result_view
            assert view is not None
            count = len(expected)
            assert view.summary.get_label().startswith(f'{count} of {count} on time')
            assert not pad.pad.get_visible()
            # Next question: a sloppy take, with the first note missed.
            assert press(page, 'Return')
            pad = page.answer_widget
            pad.start()
            backend.current.started_at = 50.0
            onsets = list(page.question.expected)
            for onset in onsets[1:]:
                pad.tap(50.0 + (onset + 30 + 70) / 1000)
            backend.complete()
            pump()
            feedback = page.feedback
            assert feedback is not None
            assert not feedback.correct
            assert 'No tap near note 1' in feedback.detail
            chips = [c.get_child() for c in _children(pad.result_view.chips)]
            assert any(c.has_css_class('error') for c in chips)
            assert any(c.has_css_class('warning') for c in chips)
            # A take without taps is not submitted.
            assert press(page, 'Return')
            pad = page.answer_widget
            pad.start()
            backend.complete()
            pump()
            assert page.feedback is None
            assert 'No taps' in pad.status.get_label()
            # Without sound the visual metronome counts by itself.
            pad.player = None
            pad.start()
            assert type(pad.handle).__name__ == 'TimerPlayback'
            pad.cancel()
            assert pad.state == 'idle'
        finally:
            get_settings().reset('audio-latency-ms')
            get_settings().reset('exercise-settings')
            _close_live(window, services)


def check_rhythm_input_keyboard() -> None:
    """Enter a dictated rhythm with digits, 0 for rests, Backspace and Enter."""
    import tempfile

    from etude.core import Duration, NoteValue
    from etude.ui.common import get_settings
    from etude.ui.widgets.rhythm_input import RhythmInputView

    with tempfile.TemporaryDirectory() as data_dir:
        window, services, backend = _live_rhythm_window(
            data_dir, 'rhythm-dictation', {'meters': ('2/4',), 'bars': 1}
        )
        try:
            page = window.start_exercise('rhythm-dictation')
            assert page is not None
            pump()
            assert backend.played, 'the question plays by itself'
            view = page.answer_widget
            assert isinstance(view, RhythmInputView)
            accel = {d: str(i + 1) for i, d in enumerate(view.spec.palette)}
            half = Duration(NoteValue.HALF)
            quarter = Duration(NoteValue.QUARTER)
            assert not view.check_button.get_sensitive()
            assert not press(page, 'Return')  # nothing to check yet
            assert press(page, accel[quarter])
            assert view.rhythm == ((quarter, False),)
            assert view.status.get_label() == 'Bar 1 of 1 · 1 beat left'
            # The bar-fill guard: a half note no longer fits.
            button = next(b for b in view.buttons if b.duration == half)
            assert not button.get_sensitive()
            assert press(page, accel[half])
            assert view.rhythm == ((quarter, False),)
            assert press(page, '0')  # rests
            assert view.rest_mode
            assert press(page, accel[quarter])
            assert view.rhythm == ((quarter, False), (quarter, True))
            assert view.full
            assert view.check_button.get_sensitive()
            figure = view.staff.get_property('figure')
            assert [type(e).__name__ for e in figure.events] == ['Chord', 'Rest', 'Barline']
            # Enter the expected rhythm instead.
            while view.entries:
                assert press(page, 'BackSpace')
            for duration, is_rest in page.question.expected:
                if is_rest != view.rest_mode:
                    assert press(page, '0')
                assert press(page, accel[duration])
            assert press(page, 'Return')
            assert page.feedback is not None
            assert page.feedback.correct, page.feedback.title
            assert page.feedback.title == 'Correct — every beat right'
            assert 'beats right' in view.status.get_label()
        finally:
            get_settings().reset('exercise-settings')
            _close_live(window, services)


def check_calibration() -> None:
    """Calibrate tap timing in the preferences, save, reset."""
    from etude.audio.null import NullBackend
    from etude.ui.common import get_settings
    from etude.ui.dialogs.preferences import PreferencesDialog

    backend = NullBackend(available=True)
    window = new_window()
    try:
        prefs = PreferencesDialog(player=backend.play)
        prefs.present(window)
        pump()
        assert prefs.tap_timing_row.get_subtitle() == 'Not calibrated'
        assert not prefs.reset_latency_button.get_sensitive()
        prefs.tap_timing_row.emit('activated')
        page = prefs.calibration
        assert page is not None
        pump()
        page.start_button.emit('clicked')
        handle = backend.current
        assert handle is not None
        assert handle.spec.count_in == 4
        handle.started_at = 10.0
        for index, click in enumerate(page.clicks_ms):
            at = 10.0 + (click + 42 + (index % 3 - 1) * 4) / 1000
            if index % 2:
                page.keys.press(at)
            else:
                page.tap(at)
        backend.complete()
        pump()
        assert page.estimate is not None
        assert round(page.estimate.offset_ms) == 42
        assert 'after the clicks' in page.result.get_label()
        assert page.save_button.get_sensitive()
        page.save_button.emit('clicked')
        assert get_settings().get_int('audio-latency-ms') == 42
        assert prefs.tap_timing_row.get_subtitle() == 'Taps corrected by 42 ms'
        # Too few taps: no result.
        page.start()
        backend.current.started_at = 0.0
        page.tap(0.5)
        backend.complete()
        pump()
        assert page.estimate is None
        assert 'Not enough taps' in page.status.get_label()
        assert prefs.reset_latency_button.get_sensitive()
        prefs.reset_latency_button.emit('clicked')
        assert get_settings().get_int('audio-latency-ms') == 0
        prefs.force_close()
    finally:
        get_settings().reset('audio-latency-ms')
        window.destroy()


def check_style_css_parses() -> None:
    """GTK parses the whole stylesheet without errors (a broken rule silently drops
    every rule after it)."""
    from gi.repository import Gtk

    errors: list[str] = []
    provider = Gtk.CssProvider()
    provider.connect(
        'parsing-error', lambda _p, section, error: errors.append(f'{section}: {error.message}')
    )
    provider.load_from_resource('/fi/oikarinenotto/etude/style.css')
    assert not errors, errors


def _click_position(widget, position: int, slot: int = 0) -> None:
    """Click the staff input at a staff position, in widget pixels as GTK reports them."""
    view = widget.view
    display = view.display_list
    geometry = display.staves[0]
    ox, oy = view._origin()
    px = view.pixels_per_space
    events = widget.entry.slot_events()
    x = ox + display.event_x[0][events[min(slot, len(events) - 1)]] * px
    y = oy + geometry.y_of(position) * px
    assert view.staff_position_at(x, y) == (0, position), (view.staff_position_at(x, y), position)
    widget._on_motion(None, x, y)
    assert widget.hover == position
    widget._on_pressed(None, 1, x, y)


def check_staff_input_widget() -> None:
    """Clicks, hover and keys map to pitches at a wide and a phone width; Check submits;
    the reveal marks the notes; the accessible value names the cursor note."""
    from gi.repository import Gdk, Gtk

    from etude.core import Pitch
    from etude.exercises.base import StaffInputAnswer
    from etude.notation.spec import Chord, Clef, Head, Ink, StaffSpec
    from etude.ui.widgets.staff_input import StaffInputView

    for width in (900, 360):
        window = Gtk.Window(default_width=width, default_height=700)
        given = StaffSpec(clef=Clef.BASS, events=(Chord((Head(Pitch.parse('G2')),)),))
        widget = StaffInputView(StaffInputAnswer(Clef.BASS, slots=1, given=given))
        window.set_child(widget)
        window.present()
        pump()
        try:
            assert widget.view.get_width() <= width
            answers = []
            widget.connect('answered', lambda _w, v, found=answers: found.append(v))
            assert widget.entry.cursor == 0, 'the cursor starts on the given note'
            assert not widget.check_button.get_sensitive()
            assert not widget.activate_default()
            for position in (8, -3, 11, 2):
                _click_position(widget, position)
                assert widget.entry.notes[0] == Clef.BASS.pitch_at(position)
            assert widget.check_button.get_sensitive()
            assert widget.handle_key(Gdk.KEY_Up, Gdk.ModifierType(0))
            assert widget.entry.notes[0] == Pitch.parse('C3')
            assert widget.handle_key(Gdk.KEY_e, Gdk.ModifierType(0))
            assert widget.entry.notes[0] == Pitch.parse('E3')
            assert widget.handle_key(Gdk.KEY_minus, Gdk.ModifierType(0))
            assert widget.accidental_buttons[widget.entry.accidental].get_active()
            assert widget.entry.notes[0] == Pitch.parse('Eb3')
            assert widget.handle_key(Gdk.KEY_F, Gdk.ModifierType.SHIFT_MASK)
            assert widget.entry.notes[0] == Pitch.parse('F#3')
            assert widget.handle_key(Gdk.KEY_Up, Gdk.ModifierType.SHIFT_MASK)
            assert widget.entry.notes[0] == Pitch.parse('F#4')
            widget.accidental_buttons[widget.entry.accidental].set_active(False)
            assert widget.entry.notes[0] == Pitch.parse('F4')
            assert widget.handle_key(Gdk.KEY_BackSpace, Gdk.ModifierType(0))
            assert widget.entry.value() is None
            assert not widget.handle_key(Gdk.KEY_r, Gdk.ModifierType(0)), 'r is replay'
            assert not widget.handle_key(Gdk.KEY_Left, Gdk.ModifierType(0)), 'one slot only'
            _click_position(widget, 1)
            assert widget.activate_default()
            assert answers == [((Pitch.parse('A2'),),)]
            widget.reveal(((Pitch.parse('B2'),),), answers[0], False)
            inks = [h.ink for e in widget.view.figure.events for h in e.heads]
            assert inks == [Ink.FOREGROUND, Ink.ERROR, Ink.SUCCESS], inks
            assert not widget.check_button.get_sensitive()
            assert not widget.handle_key(Gdk.KEY_Up, Gdk.ModifierType(0)), 'locked'
        finally:
            window.destroy()


def _enter(page, pitch) -> None:
    """Write ``pitch`` with the keyboard only, as a learner would."""
    widget = page.answer_widget
    clef = widget.entry.clef
    assert press(page, pitch.letter.name.lower())
    target = clef.staff_position(pitch)
    while widget.entry.cursor < target:
        assert press(page, 'Up')
    while widget.entry.cursor > target:
        assert press(page, 'Down')
    if pitch.alter == 1:
        assert press(page, 'plus')
    elif pitch.alter == -1:
        assert press(page, 'minus')
    assert widget.entry.notes[0] == pitch, (widget.entry.notes, pitch)


def check_live_staff_input_sessions() -> None:
    """Real note-placement and interval-construction sessions answered with the staff
    input: keys, clicks, Enter to check, a wrong answer marked and explained."""
    import tempfile

    from etude.core import Pitch
    from etude.notation.spec import Ink
    from etude.ui.widgets.staff_input import StaffInputView

    with tempfile.TemporaryDirectory() as data_dir:
        window, services = _live_window(data_dir)
        try:
            for exercise_id in ('note-placement', 'interval-construction'):
                page = window.start_exercise(exercise_id)
                pump()
                widget = page.answer_widget
                assert isinstance(widget, StaffInputView), type(widget)
                (expected,) = page.question.expected[0]
                _enter(page, expected)
                assert press(page, 'Return')
                assert page.feedback is not None
                assert page.feedback.correct, page.feedback.title
                assert press(page, 'Return')
                assert page.feedback is None
                widget = page.answer_widget
                (expected,) = page.question.expected[0]
                position = widget.entry.clef.staff_position(expected)
                wrong = position + 1
                _click_position(widget, wrong)
                assert press(page, 'Return')
                assert page.feedback is not None
                assert not page.feedback.correct
                assert page.feedback_banner.has_css_class('feedback-error')
                inks = [h.ink for e in widget.view.figure.events for h in e.heads]
                assert inks[-2:] == [Ink.ERROR, Ink.SUCCESS], inks
                assert page.feedback.detail
                assert page.feedback.play_given is not None
                assert isinstance(expected, Pitch)
                assert press(page, 'Escape')
                pump()
        finally:
            _close_live(window, services)


CHECKS: list[Callable[[], None]] = [
    check_style_css_parses,
    check_window_and_sections,
    check_keysig_correct_then_next,
    check_interval_wrong,
    check_note_naming_piano,
    check_chips,
    check_scale_degree_and_ear,
    check_text_and_placeholders,
    check_progress,
    check_setup,
    check_dialogs,
    check_session_summary_flow,
    check_live_session,
    check_live_exercises_fit_and_compare,
    check_reveal_details,
    check_staff_input_widget,
    check_live_staff_input_sessions,
    check_today_preview,
    check_continue_banner_preview,
    check_progress_empty,
    check_live_new_learner,
    check_live_resume_session,
    check_live_today_review,
    check_lesson_preview,
    check_glossary_search,
    check_path_preview,
    check_live_lesson_and_glossary,
    check_live_path_unit_practice,
    check_live_placement_and_exam,
    check_path_pages_fit_narrow,
    check_tap_pad_flow,
    check_rhythm_input_keyboard,
    check_calibration,
]


def _children(widget):
    result = []
    child = widget.get_first_child()
    while child is not None:
        result.append(child)
        child = child.get_next_sibling()
    return result


def _variant(value: str):
    from gi.repository import GLib

    return GLib.Variant.new_string(value)


def run_all() -> list[str]:
    failures = []
    for check in CHECKS:
        try:
            check()
            print(f'ok   {check.__name__}')
        except Exception:
            failures.append(check.__name__)
            print(f'FAIL {check.__name__}')
            traceback.print_exc()
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    args = parser.parse_args()
    reason = unavailable_reason()
    if reason:
        print(f'skipped: {reason}')
        return SKIP
    with tempfile.TemporaryDirectory() as workdir:
        prepare(args.source_root.resolve(), Path(workdir))
        failures = run_all()
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
