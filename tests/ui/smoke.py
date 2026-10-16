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
    for key in ('construction', 'rhythm-dictation', 'rhythm-tap'):
        page.show_question(questions[key].question, number=1, total=5)
        assert type(page.answer_widget).__name__ == 'PlaceholderAnswerView'


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


CHECKS: list[Callable[[], None]] = [
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
