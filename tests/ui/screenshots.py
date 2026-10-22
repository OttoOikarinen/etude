#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Render every screen of the design to PNG files for visual review.

Not a test: run it by hand inside the GNOME SDK, for example::

    flatpak run --filesystem=<parent of the checkout> --socket=wayland \\
        --socket=fallback-x11 --share=ipc --device=dri --command=python3 \\
        org.gnome.Sdk//51 tests/ui/screenshots.py --output build/screenshots

Each screen is shown in a window, rendered through ``Gtk.WidgetPaintable`` and
saved with ``Gsk.Renderer.render_texture().save_to_png()``; the window is
closed straight away.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('etude_ui_smoke', HERE / 'smoke.py')
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)

WIDE = (1180, 760)
NARROW = (400, 820)


def wait(ms: int) -> None:
    from gi.repository import GLib

    loop = GLib.MainLoop()
    GLib.timeout_add(ms, loop.quit)
    loop.run()


def render(window, path: Path) -> None:
    from gi.repository import Graphene, Gsk, Gtk

    wait(450)
    width, height = window.get_width(), window.get_height()
    paintable = Gtk.WidgetPaintable.new(window)
    snapshot = Gtk.Snapshot()
    paintable.snapshot(snapshot, width, height)
    node = snapshot.to_node()
    if node is None:
        print(f'nothing to render for {path.name}')
        return
    renderer = window.get_renderer()
    if renderer is None:
        renderer = Gsk.CairoRenderer()
        renderer.realize_for_display(window.get_display())
    texture = renderer.render_texture(node, Graphene.Rect().init(0, 0, width, height))
    texture.save_to_png(str(path))
    print(path)


def scroll_to(page, fraction: float) -> None:
    """Scroll a lesson page to ``fraction`` of its length (0 = top, 1 = bottom)."""
    adjustment = page.scroller.get_vadjustment()
    wait(200)
    span = adjustment.get_upper() - adjustment.get_page_size()
    adjustment.set_value(max(0.0, span * fraction))


def shoot_lesson(window, out: Path, prefix: str, name: str) -> None:
    """A lesson from the top, its worked example and its checks (one answered)."""
    page = window.open_lesson('l1.staff')
    wait(300)  # the page slides in
    render(window, out / f'{prefix}-lesson-{name}.png')
    for worked in page.worked:
        worked.reveal_next()
    if page.checks:
        check = page.checks[0]
        wrong = next(o.key for o in check.check.options if not o.correct)
        check.choose(wrong)
    scroll_to(page, 0.55)
    render(window, out / f'{prefix}-lesson-middle-{name}.png')
    scroll_to(page, 1.0)
    render(window, out / f'{prefix}-lesson-end-{name}.png')
    window.nav_view.pop_to_tag('main')


def shoot_path_pages(window, out: Path, prefix: str, name: str, *, entry: str) -> None:
    for section in ('path', 'theory', 'glossary'):
        window.show_section(section)
        render(window, out / f'{prefix}-{section}-{name}.png')
    dialog = window.show_glossary_entry(entry)
    render(window, out / f'{prefix}-glossary-entry-{name}.png')
    dialog.force_close()
    shoot_lesson(window, out, prefix, name)


def window_at(size: tuple[int, int], model=None):
    from etude.ui.preview import PreviewModel
    from etude.window import EtudeWindow

    window = EtudeWindow(model if model is not None else PreviewModel())
    window.set_default_size(*size)
    window.present()
    wait(300)
    return window


def shoot(out: Path, scheme: str, size: tuple[int, int], suffix: str) -> None:
    from gi.repository import Adw

    from etude.ui import preview

    style = Adw.StyleManager.get_default()
    style.set_color_scheme(
        Adw.ColorScheme.FORCE_DARK if scheme == 'dark' else Adw.ColorScheme.FORCE_LIGHT
    )
    name = f'{scheme}{suffix}'

    def answered(page, key: str, value=None, wrong: bool = False):
        questions = preview.preview_questions()
        item = questions[key]
        given = (
            item.sample_wrong if wrong else (value if value is not None else item.question.expected)
        )
        page._shown_at -= 1.8  # the design shows "Answered in 1.8 s."
        page.answer_widget.submit(given)

    # Empty states: nothing due, the goal met, a brand-new learner's progress
    from etude.ui.preview import PreviewModel

    window = window_at(size, PreviewModel(caught_up=True))
    window.show_section('today')
    render(window, out / f'1k-today-caught-up-{name}.png')
    window.show_section('progress')
    render(window, out / f'1h-progress-empty-{name}.png')
    window.show_section('path')
    render(window, out / f'4a-path-new-{name}.png')
    window.destroy()

    # 4 the learning path: curriculum map, lessons, glossary
    window = window_at(size)
    shoot_path_pages(window, out, '4', name, entry='crescendo')
    window.show_section('path')
    window.path_page.unit_cards['l1.major'].practise_button.emit('clicked')
    render(window, out / f'4-path-confirm-{name}.png')
    window.confirm_dialog.force_close()
    window.path_page.exam_cards['level1'].button.emit('clicked')
    window.confirm_dialog.emit('response', 'practise')
    controller = window.controller
    controller.session.index = controller.session.total
    summary = controller.finish()
    render(window, out / f'4-exam-summary-{name}.png')
    summary.force_close()
    window.destroy()

    # 1a / 3a home
    window = window_at(size)
    render(window, out / f'1a-home-{name}.png')
    window.show_section('progress')
    render(window, out / f'1h-progress-{name}.png')
    window.show_section('today')
    render(window, out / f'1k-today-{name}.png')
    window.show_section('all')
    # 1j setup
    window.open_setup('keysig')
    render(window, out / f'1j-setup-{name}.png')
    # 1b key signature question
    page = window.start_exercise('keysig', replace=True)
    page.set_elapsed(252)
    render(window, out / f'1b-keysig-question-{name}.png')
    # 1c note naming, correct
    page = window.start_exercise('note-naming')
    page.set_elapsed(252)
    if size == NARROW:
        render(window, out / f'3b-note-naming-{name}.png')
        page.answer_widget.emit('sheet-requested')
        render(window, out / f'3b-piano-sheet-{name}.png')
        page.bottom_sheet.set_open(False)
    answered(page, 'note-naming')
    render(window, out / f'1c-note-correct-{name}.png')
    # 1d interval, wrong
    page = window.start_exercise('interval-staff')
    page.set_elapsed(252)
    answered(page, 'interval-staff', wrong=True)
    render(window, out / f'1d-interval-wrong-{name}.png')
    if size == WIDE:
        # 1e ear
        page = window.start_exercise('interval-ear')
        page.set_elapsed(252)
        render(window, out / f'1e-ear-{name}.png')
        # 1f chips, partly answered
        page = window.start_exercise('chord-staff')
        page.set_elapsed(252)
        chips = page.answer_widget
        chips.chips['root']['E'].set_active(True)
        chips.chips['quality']['minor'].set_active(True)
        chips.chips['inversion']['root'].set_active(True)
        render(window, out / f'1f-chips-{name}.png')
        # 1g scale degree
        page = window.start_exercise('scale-degree')
        page.set_elapsed(252)
        render(window, out / f'1g-degree-{name}.png')
        # Text answer
        page = window.start_exercise('vocabulary')
        render(window, out / f'1x-text-{name}.png')
    # 1i summary
    page = window.start_exercise('keysig')
    from etude.ui.dialogs.session_summary import create_session_summary_dialog

    dialog = create_session_summary_dialog(
        preview.sample_summary(), 'Key Signatures · 20 questions · Treble clef'
    )
    dialog.present(window)
    render(window, out / f'1i-summary-{name}.png')
    dialog.force_close()
    if size == WIDE:
        from etude.ui.dialogs.preferences import PreferencesDialog

        prefs = PreferencesDialog()
        prefs.present(window)
        render(window, out / f'1l-preferences-{name}.png')
        page = prefs.open_calibration()
        render(window, out / f'1n-calibration-{name}.png')
        page.start()
        page._on_beat(page._run, 2)
        render(window, out / f'1n-calibration-running-{name}.png')
        page.stop()
        prefs.force_close()
        from gi.repository import Gtk

        builder = Gtk.Builder.new_from_resource('/fi/oikarinenotto/etude/shortcuts-dialog.ui')
        shortcuts = builder.get_object('shortcuts_dialog')
        shortcuts.present(window)
        render(window, out / f'1m-shortcuts-{name}.png')
        shortcuts.force_close()
    window.destroy()


def rhythm_shots(window, page, pattern) -> None:
    """A take in progress (count-in, then the bar), and a sloppy take's timeline."""
    pad = page.answer_widget
    pad.start()
    pad._on_beat(pad._take, -2)
    render(window, Path(str(pattern).format('count-in')))
    pad._on_beat(pad._take, 1)
    pad.pad.flash()
    render(window, Path(str(pattern).format('tapping')))
    pad.cancel()
    taps = [t + (60 if i % 3 == 1 else -15) for i, t in enumerate(page.question.expected)]
    del taps[-1]
    taps.append(taps[-1] + 180)
    pad.submit(tuple(taps))
    render(window, Path(str(pattern).format('wrong')))


def entry_shots(window, page, pattern) -> None:
    """A half-entered rhythm, then a wrong one."""
    view = page.answer_widget
    expected = list(page.question.expected)
    for duration, is_rest in expected[: max(1, len(expected) // 2)]:
        view.rest_button.set_active(is_rest)
        view.add(duration)
    render(window, Path(str(pattern).format('entering')))
    while view.entries:
        view.undo()
    view.rest_button.set_active(False)
    while not view.full:
        fitting = [b.duration for b in view.buttons if view.can_add(b.duration)]
        view.add(fitting[len(fitting) // 2])
    view.activate_default()
    render(window, Path(str(pattern).format('wrong')))


def four_part_shots(window, page, pattern) -> None:
    """Enter a four-part answer whose top written voice doubles the bottom voice in
    octaves (parallel octaves and more), render it being written and checked."""
    from etude.core import Interval

    widget = page.answer_widget
    entry = widget.entry
    expected = page.question.expected
    free = entry.editable_voices
    top, bottom = free[0], max(range(entry.voices))
    for voice in free:
        entry.set_voice(voice)
        for slot, chord in enumerate(expected):
            pitch = chord[voice]
            if voice == top:
                pitch = chord[bottom].transpose(Interval.parse('P15'))
                if pitch.midi > 79:
                    pitch = chord[bottom].transpose(Interval.parse('P8'))
            entry.select(slot)
            entry.place(entry.voice_clef.staff_position(pitch))
    entry.set_voice(free[-1])
    widget.refresh()
    render(window, Path(str(pattern).format('entering')))
    widget.activate_default()
    render(window, Path(str(pattern).format('wrong')))


def counterpoint_shots(window, page, pattern) -> None:
    """Write half of the model counterpoint (the input as the learner sees it while
    writing), then the whole line with every third note a step too high, checked."""
    from etude.core import Interval

    widget = page.answer_widget
    entry = widget.entry
    voice = entry.editable_voices[0]
    line = page.question.expected[voice]
    for slot, pitch in enumerate(line[: len(line) // 2]):
        entry.select(slot)
        entry.place(entry.voice_clef.staff_position(pitch))
    entry.select(len(line) // 2)
    widget.refresh()
    render(window, Path(str(pattern).format('entering')))
    for slot, pitch in enumerate(line):
        if slot % 3 == 1:
            pitch = pitch.transpose(Interval.parse('M2'))
        entry.select(slot)
        entry.place(entry.voice_clef.staff_position(pitch))
    widget.refresh()
    widget.activate_default()
    render(window, Path(str(pattern).format('wrong')))


def shoot_live(out: Path, exercise_ids: list[str] | None, seed: int) -> None:
    """Real exercises from the registry against a throw-away database: the first
    question, a correct answer and (for choice answers) a wrong one, light and dark."""
    import random

    from gi.repository import Adw

    from etude.audio.null import NullBackend
    from etude.exercises.base import (
        ChoiceAnswer,
        RhythmInputAnswer,
        StaffInputAnswer,
        TapAnswer,
    )
    from etude.services import Services
    from etude.ui.common import get_settings
    from etude.ui.model import LiveModel
    from etude.window import EtudeWindow

    style = Adw.StyleManager.get_default()

    def set_scheme(scheme: str) -> None:
        style.set_color_scheme(
            Adw.ColorScheme.FORCE_DARK if scheme == 'dark' else Adw.ColorScheme.FORCE_LIGHT
        )

    def sections(window, prefix: str, scheme: str) -> None:
        render(window, out / f'{prefix}-home-{scheme}.png')
        for section in ('today', 'progress', 'path'):
            window.show_section(section)
            render(window, out / f'{prefix}-{section}-{scheme}.png')
        window.show_section('all')

    with tempfile.TemporaryDirectory() as data_dir:
        services = Services.open(Path(data_dir))
        services._audio = NullBackend()
        services.rng.seed(seed)
        ids = exercise_ids or list(services.registry.exercise_ids())
        # A brand-new learner: empty states with real data.
        for scheme, size, suffix in (
            ('light', WIDE, ''),
            ('dark', WIDE, ''),
            ('light', NARROW, '-narrow'),
        ):
            set_scheme(scheme)
            window = EtudeWindow(LiveModel(services, get_settings()))
            window.set_default_size(*size)
            window.present()
            wait(300)
            sections(window, 'live-new', scheme + suffix)
            shoot_path_pages(window, out, 'live', scheme + suffix, entry='crescendo')
            window.destroy()
        for scheme, size, suffix in (
            ('light', WIDE, ''),
            ('dark', WIDE, ''),
            ('light', NARROW, '-narrow'),
        ):
            scheme_name = scheme
            scheme += suffix
            set_scheme(scheme_name)
            model = LiveModel(services, get_settings())
            window = EtudeWindow(model)
            window.set_default_size(*size)
            window.present()
            wait(300)
            for exercise_id in ids:
                page = window.start_exercise(exercise_id, replace=True)
                if page is None:
                    print(f'{exercise_id}: nothing to practise')
                    continue
                render(window, out / f'live-{exercise_id}-question-{scheme}.png')
                page.answer_widget.submit(page.question.expected)
                render(window, out / f'live-{exercise_id}-correct-{scheme}.png')
                window.controller.next()
                answer = page.question.answer
                if isinstance(answer, ChoiceAnswer):
                    wrong = random.Random(seed).choice(
                        [o.key for o in answer.options if o.key != page.question.expected]
                    )
                    page.answer_widget.submit(wrong)
                    render(window, out / f'live-{exercise_id}-wrong-{scheme}.png')
                elif isinstance(answer, TapAnswer):
                    rhythm_shots(window, page, out / f'live-{exercise_id}-{{}}-{scheme}.png')
                elif isinstance(answer, RhythmInputAnswer):
                    entry_shots(window, page, out / f'live-{exercise_id}-{{}}-{scheme}.png')
                elif isinstance(answer, StaffInputAnswer) and answer.voice_rhythms:
                    counterpoint_shots(window, page, out / f'live-{exercise_id}-{{}}-{scheme}.png')
                elif isinstance(answer, StaffInputAnswer) and answer.voices > 1:
                    # A filled-in four-part answer with mistakes: the highest written
                    # voice doubles the lowest one in octaves, then it is checked.
                    four_part_shots(window, page, out / f'live-{exercise_id}-{{}}-{scheme}.png')
                elif isinstance(answer, StaffInputAnswer):
                    # Write a wrong note with a real click, then check it.
                    widget = page.answer_widget
                    (expected,) = page.question.expected[0]
                    position = widget.entry.clef.staff_position(expected) + 1
                    smoke._click_position(widget, position)
                    # The other notes of a dictation right, so the answer can be checked.
                    for slot, chord in enumerate(page.question.expected[1:], start=1):
                        widget.entry.select(slot)
                        widget.entry.place(widget.entry.clef.staff_position(chord[0]))
                        widget.entry.notes[slot] = chord[0]
                    widget.entry.select(0)
                    widget.refresh()
                    render(window, out / f'live-{exercise_id}-entering-{scheme}.png')
                    widget.activate_default()
                    render(window, out / f'live-{exercise_id}-wrong-{scheme}.png')
            # Leave the last session unfinished: the Continue banner offers it.
            window.nav_view.pop_to_tag('main')
            sections(window, 'live-after', scheme)
            model.shutdown()
            window.destroy()
        services.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('build/screenshots'))
    parser.add_argument('--only', choices=('light', 'dark', 'narrow'), action='append')
    parser.add_argument(
        '--live',
        nargs='*',
        metavar='EXERCISE',
        help='shoot real exercises (all registered ones when no id is given)',
    )
    parser.add_argument('--seed', type=int, default=1)
    args = parser.parse_args()
    reason = smoke.unavailable_reason()
    if reason:
        print(f'cannot render: {reason}')
        return 1
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as workdir:
        smoke.prepare(smoke.ROOT, Path(workdir))
        smoke.load_css()
        if args.live is not None:
            shoot_live(args.output, args.live, args.seed)
            return 0
        runs = {
            'light': ('light', WIDE, ''),
            'dark': ('dark', WIDE, ''),
            'narrow': ('light', NARROW, '-narrow'),
        }
        for key in args.only or runs:
            shoot(args.output, *runs[key])
        shoot(args.output, 'dark', NARROW, '-narrow') if not args.only else None
    return 0


if __name__ == '__main__':
    sys.exit(main())
