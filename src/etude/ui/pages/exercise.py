# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The generic exercise page (design 1b–1g, 2b, 3b).

The page renders any :class:`~etude.exercises.base.Question` and knows nothing
about sessions, scheduling or grading: a controller (W1: the stub session in
:mod:`etude.ui.preview`; W2: the session runner) calls :meth:`show_question`,
listens to ``answered``, grades, and calls :meth:`show_feedback`.
"""

from __future__ import annotations

import dataclasses
import time
from fractions import Fraction
from gettext import gettext as _

from gi.repository import Adw, Gdk, GLib, GObject, Gtk

from ...audio.spec import PlaybackSpec
from ...exercises.base import Feedback, Modality, Question
from ..common import (
    format_clock,
    format_percent,
    is_enter,
    normalize_keyval,
    setting_bool,
    ui_resource,
)
from ..figure import create_figure_widget
from ..timing import Player
from ..widgets.base import AnswerWidget
from ..widgets.ear_panel import EarPanel
from ..widgets.feedback import FeedbackBanner
from ..widgets.simple import create_answer_widget


def is_harmonic(spec: PlaybackSpec) -> bool:
    """Whether every note of a playback of several notes starts together."""
    return len(spec.notes) > 1 and len({n.start for n in spec.notes}) == 1


def adjust_playback(spec: PlaybackSpec, *, harmonic: bool, tempo: int) -> PlaybackSpec:
    """Apply the ear panel's Melodic/Harmonic and tempo choices to a playback.

    Harmonic sounds each pitch once, together; melodic spreads a harmonic
    playback upwards one beat per note and leaves a melodic one as written.
    """
    notes = spec.notes
    if harmonic and not is_harmonic(spec) and notes:
        length = max(n.length for n in notes)
        unique = {n.midi: n for n in notes}.values()
        notes = tuple(dataclasses.replace(n, start=Fraction(0), length=length) for n in unique)
    elif not harmonic and is_harmonic(spec):
        ordered = sorted(notes, key=lambda n: n.midi)
        notes = tuple(
            dataclasses.replace(n, start=Fraction(i), length=Fraction(1))
            for i, n in enumerate(ordered)
        )
    return dataclasses.replace(spec, notes=notes, tempo=float(tempo))


@Gtk.Template(resource_path=ui_resource('pages/exercise.ui'))
class ExercisePage(Adw.NavigationPage):
    """Signals:

    * ``answered(value)``: the learner answered; :attr:`response_ms` holds the time.
    * ``next-requested``, ``skip-requested``, ``hint-requested``, ``close-requested``.
    * ``play-requested(spec)``: play this :class:`PlaybackSpec` (W1: nothing plays).
    """

    __gtype_name__ = 'EtudeExercisePage'
    __gsignals__ = {  # noqa: RUF012 (GObject API)
        'answered': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        'next-requested': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'skip-requested': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'hint-requested': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'close-requested': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'play-requested': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    window_title: Adw.WindowTitle = Gtk.Template.Child()
    close_button: Gtk.Button = Gtk.Template.Child()
    pause_button: Gtk.ToggleButton = Gtk.Template.Child()
    show_staff_button: Gtk.ToggleButton = Gtk.Template.Child()
    play_button: Gtk.Button = Gtk.Template.Child()
    play_content: Adw.ButtonContent = Gtk.Template.Child()
    bottom_sheet: Adw.BottomSheet = Gtk.Template.Child()
    state_stack: Gtk.Stack = Gtk.Template.Child()
    body: Gtk.Box = Gtk.Template.Child()
    prompt_label: Gtk.Label = Gtk.Template.Child()
    figure_slot: Adw.Bin = Gtk.Template.Child()
    context_label: Gtk.Label = Gtk.Template.Child()
    answer_slot: Adw.Bin = Gtk.Template.Child()
    hint_revealer: Gtk.Revealer = Gtk.Template.Child()
    hint_label: Gtk.Label = Gtk.Template.Child()
    feedback_revealer: Gtk.Revealer = Gtk.Template.Child()
    feedback_banner: FeedbackBanner = Gtk.Template.Child()
    aux_box: Gtk.Box = Gtk.Template.Child()
    hint_button: Gtk.Button = Gtk.Template.Child()
    skip_badge: Gtk.Label = Gtk.Template.Child()
    skip_button: Gtk.Button = Gtk.Template.Child()
    sheet_bin: Adw.Bin = Gtk.Template.Child()
    stats_bar: Gtk.Box = Gtk.Template.Child()
    streak_icon: Gtk.Image = Gtk.Template.Child()
    streak_label: Gtk.Label = Gtk.Template.Child()
    accuracy_label: Gtk.Label = Gtk.Template.Child()
    timer_label: Gtk.Label = Gtk.Template.Child()

    compact = GObject.Property(type=bool, default=False)

    def __init__(self, exercise_title: str, modality: Modality = Modality.EYE, **kwargs: object):
        super().__init__(**kwargs)
        self.set_title(exercise_title)
        self.window_title.set_title(exercise_title)
        self.modality = modality
        self.question: Question | None = None
        self.answer_widget: AnswerWidget | None = None
        self.ear_panel: EarPanel | None = None
        self.feedback: Feedback | None = None
        self.response_ms = 0
        self.elapsed = 0
        self._number = 0
        self._total = 0
        self._settings_text = ''
        self._shown_at = 0.0
        self._timer = 0
        self._figure_holder = self._new_figure_holder()
        self.audio_available = True
        """Without sound, ear questions show their written alternative."""
        self.player: Player | None = None
        """Plays with beat callbacks for answer widgets that need them (rhythm tapping)."""
        self._play_label = _('Play')
        self._stats: tuple[int, int, float | None, bool] = (0, 0, None, False)
        self.connect('notify::compact', lambda *_a: self._apply_compact())
        self.feedback_revealer.connect('notify::child-revealed', self._on_feedback_revealed)
        self.connect('map', lambda *_a: self._start_timer())
        self.connect('unmap', lambda *_a: self._stop_timer())
        self.set_stats(0, 0, None)
        self.timer_label.set_label(format_clock(0))

    # Questions ------------------------------------------------------------------

    def show_question(
        self,
        question: Question,
        *,
        number: int,
        total: int,
        settings_text: str = '',
        play_label: str | None = None,
    ) -> None:
        """Render ``question``. ``play_label`` ("Play chord") names the header play
        button of eye exercises that have a playback."""
        self.question = question
        self.feedback = None
        self._number, self._total, self._settings_text = number, total, settings_text
        self._update_subtitle()
        self.prompt_label.set_label(question.prompt)
        self.feedback_revealer.set_reveal_child(False)
        self.hint_revealer.set_reveal_child(False)
        self.hint_label.set_label(question.hint or '')
        self.hint_button.set_visible(question.hint is not None)
        self.aux_box.set_visible(True)

        ear = question.playback_is_question
        self.show_staff_button.set_visible(ear)
        self.show_staff_button.set_active(False)
        self.pause_button.set_visible(not ear)
        eye_playback = question.playback is not None and not ear
        self.play_button.set_visible(eye_playback)
        self._play_label = play_label or _('Play')
        self.play_content.set_label('' if self.compact else self._play_label)
        self.play_button.set_tooltip_text(self._play_label)

        self.ear_panel = None
        figure_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        if ear:
            playback = question.playback
            self.ear_panel = EarPanel(
                context=question.context,
                tempo=round(playback.tempo) if playback is not None else 80,
                harmonic=playback is not None and is_harmonic(playback),
                style_choice=question.playback_style_choice,
            )
            self.ear_panel.connect('play-requested', self._on_ear_play)
            figure_box.append(self.ear_panel)
        self._figure_holder = self._new_figure_holder()
        figure_box.append(self._figure_holder)
        self.figure_slot.set_child(figure_box)
        self._update_figure()

        self.context_label.set_label(question.context)
        self.context_label.set_visible(bool(question.context) and not ear)

        self.answer_widget = create_answer_widget(question.answer)
        self.answer_widget.player = self.player
        # Space taps rhythms instead of skipping.
        taps = self.answer_widget.captures_space
        self.skip_badge.set_visible(not taps)
        if taps:
            self.skip_button.reset_property(Gtk.AccessibleProperty.KEY_SHORTCUTS)
        else:
            self.skip_button.update_property([Gtk.AccessibleProperty.KEY_SHORTCUTS], ['space'])
        self.answer_widget.connect('answered', self._on_answered)
        self.answer_widget.connect('sheet-requested', self._on_sheet_requested)
        self.answer_widget.set_compact(self.compact)
        self.answer_slot.set_child(self.answer_widget)
        self.bottom_sheet.set_open(False)
        self.bottom_sheet.set_can_open(False)
        self.sheet_bin.set_child(None)
        self._shown_at = time.monotonic()
        if self.ear_panel is not None:
            GLib.idle_add(self._autoplay, self.ear_panel)

    def _autoplay(self, panel: EarPanel) -> bool:
        if panel is self.ear_panel and self.feedback is None:
            panel.play()
        return GLib.SOURCE_REMOVE

    def _update_figure(self) -> None:
        question = self.question
        if question is None:
            return
        figure = question.figure
        if self.feedback is not None and self.feedback.figure is not None:
            figure = self.feedback.figure
        if question.playback_is_question:
            visible = (
                self.feedback is not None
                or self.show_staff_button.get_active()
                or setting_bool('written-alternative')
                or not self.audio_available
            )
            figure = (figure or question.written_alternative) if visible else None
        widget = create_figure_widget(figure)
        widget.connect('head-activated', self._on_head_activated)
        self._figure_holder.set_child(widget)
        self._figure_holder.set_visible(figure is not None)

    @staticmethod
    def _new_figure_holder() -> Adw.Bin:
        holder = Adw.Bin()
        holder.add_css_class('figure-card')
        return holder

    def _on_head_activated(self, _view: Gtk.Widget, _staff: int, event: int, _head: int) -> None:
        """Clicking a note answers questions that ask for one (design 1g)."""
        select = getattr(self.answer_widget, 'select_target', None)
        if select is not None and self.feedback is None:
            select(event)

    def _update_subtitle(self) -> None:
        if self.compact:
            # Translators: compact question counter, e.g. "12 / 20".
            subtitle = _('{number} / {total}').format(number=self._number, total=self._total)
        else:
            # Translators: e.g. "Question 7 of 20".
            subtitle = _('Question {number} of {total}').format(
                number=self._number, total=self._total
            )
            if self._settings_text:
                subtitle = f'{subtitle} · {self._settings_text}'
        self.window_title.set_subtitle(subtitle)

    def _apply_compact(self) -> None:
        if self.compact:
            self.add_css_class('compact')
        else:
            self.remove_css_class('compact')
        self._update_subtitle()
        self.feedback_banner.set_compact(self.compact)
        self.play_content.set_label('' if self.compact else self._play_label)
        self._render_stats()
        if self.answer_widget is not None:
            self.answer_widget.set_compact(self.compact)
        if not self.compact:
            self.bottom_sheet.set_open(False)

    # Answering --------------------------------------------------------------------

    def _on_answered(self, _widget: AnswerWidget, value: object) -> None:
        self.stop_clock()
        self.emit('answered', value)

    def _on_feedback_revealed(self, revealer: Gtk.Revealer, _pspec: object) -> None:
        if revealer.get_child_revealed() and self.feedback is not None:
            self.feedback_banner.next_button.grab_focus()

    def stop_clock(self) -> None:
        """Record the response time of the current question in :attr:`response_ms`."""
        self.response_ms = int((time.monotonic() - self._shown_at) * 1000)

    def show_feedback(self, feedback: Feedback, given: object, play_label: str | None = None):
        """Show the graded answer: mark the answer widget and reveal the banner."""
        self.feedback = feedback
        expected = self.question.expected if self.question is not None else None
        if self.answer_widget is not None:
            self.answer_widget.locked = True
            self.answer_widget.reveal(expected, given, feedback.correct)
        self.feedback_banner.show_feedback(
            feedback, response_ms=self.response_ms, play_label=play_label
        )
        self.feedback_revealer.set_reveal_child(True)
        self.aux_box.set_visible(False)
        self._update_figure()
        # Focus Next once the banner is fully revealed: focusing it scrolls the page so
        # that the explanation is in view, which it cannot do while the revealer is closed.
        if self.feedback_revealer.get_child_revealed():
            self.feedback_banner.next_button.grab_focus()

    def set_stats(
        self, streak: int, best_today: int, accuracy: float | None, streak_reset: bool = False
    ) -> None:
        self._stats = (streak, best_today, accuracy, streak_reset)
        self._render_stats()

    def _render_stats(self) -> None:
        streak, best_today, accuracy, streak_reset = self._stats
        if streak_reset:
            self.streak_label.set_label(_('Streak reset'))
            self.streak_icon.set_from_icon_name('dialog-error-symbolic')
            self.stats_bar.add_css_class('streak-reset')
        else:
            if self.compact:
                # Translators: compact footer of the exercise page, e.g. "Streak 6".
                text = _('Streak {streak}').format(streak=streak)
            else:
                # Translators: footer of the exercise page, e.g. "Streak 6 · Best today 11".
                text = _('Streak {streak} · Best today {best}').format(
                    streak=streak, best=best_today
                )
            self.streak_label.set_label(text)
            self.streak_icon.set_from_icon_name('starred-symbolic')
            self.stats_bar.remove_css_class('streak-reset')
        # Translators: e.g. "Accuracy 92%".
        self.accuracy_label.set_label(
            _('Accuracy {percent}').format(
                percent=format_percent(accuracy) if accuracy is not None else '—'
            )
        )

    # Keyboard -----------------------------------------------------------------------

    def handle_key(self, keyval: int, state: Gdk.ModifierType) -> bool:
        """Page-wide accelerators; the window forwards key presses here."""
        if keyval == Gdk.KEY_Escape:
            self.emit('close-requested')
            return True
        if self.pause_button.get_active() or self.question is None:
            return False
        if state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            return False
        key = normalize_keyval(keyval)
        if self.feedback is not None:
            if is_enter(keyval):
                self.emit('next-requested')
                return True
            if key == Gdk.KEY_r:
                return self._replay()
            return False
        if is_enter(keyval):
            return self.answer_widget is not None and self.answer_widget.activate_default()
        if keyval == Gdk.KEY_space:
            if self.answer_widget is not None and self.answer_widget.captures_space:
                return False  # the answer widget taps with Space (see TapKeys)
            self.emit('skip-requested')
            return True
        if keyval == Gdk.KEY_question:
            self._on_hint_clicked(self.hint_button)
            return True
        if self.answer_widget is not None and self.answer_widget.handle_key(keyval, state):
            return True
        if key == Gdk.KEY_r:
            return self._replay()
        return False

    def _replay(self) -> bool:
        if self.ear_panel is not None:
            self.ear_panel.play()
            return True
        if self.play_button.get_visible():
            self._on_play_clicked(self.play_button)
            return True
        return False

    # Timer --------------------------------------------------------------------------

    def _start_timer(self) -> None:
        if not self._timer:
            self._timer = GLib.timeout_add_seconds(1, self._tick)

    def _stop_timer(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def _tick(self) -> bool:
        if not self.pause_button.get_active():
            self.elapsed += 1
            self.timer_label.set_label(format_clock(self.elapsed))
        return GLib.SOURCE_CONTINUE

    def set_elapsed(self, seconds: int) -> None:
        self.elapsed = seconds
        self.timer_label.set_label(format_clock(seconds))

    # Signal handlers ------------------------------------------------------------------

    def _on_ear_play(self, _panel: EarPanel, harmonic: bool, tempo: int) -> None:
        if self.question is not None and self.question.playback is not None:
            spec = adjust_playback(self.question.playback, harmonic=harmonic, tempo=tempo)
            self.emit('play-requested', spec)

    def _on_sheet_requested(self, widget: AnswerWidget) -> None:
        sheet = widget.get_sheet()
        if sheet is None:
            return
        self.sheet_bin.set_child(sheet)
        self.bottom_sheet.set_can_open(True)
        self.bottom_sheet.set_open(True)

    @Gtk.Template.Callback()
    def _on_close_clicked(self, _button: Gtk.Button) -> None:
        self.emit('close-requested')

    @Gtk.Template.Callback()
    def _on_pause_toggled(self, button: Gtk.ToggleButton) -> None:
        paused = button.get_active()
        self.state_stack.set_visible_child_name('paused' if paused else 'question')
        button.set_icon_name(
            'media-playback-start-symbolic' if paused else 'media-playback-pause-symbolic'
        )
        button.set_tooltip_text(_('Resume') if paused else _('Pause'))

    @Gtk.Template.Callback()
    def _on_resume_clicked(self, _button: Gtk.Button) -> None:
        self.pause_button.set_active(False)

    @Gtk.Template.Callback()
    def _on_show_staff_toggled(self, _button: Gtk.ToggleButton) -> None:
        self._update_figure()

    @Gtk.Template.Callback()
    def _on_play_clicked(self, _button: Gtk.Button) -> None:
        if self.question is not None and self.question.playback is not None:
            self.emit('play-requested', self.question.playback)

    @Gtk.Template.Callback()
    def _on_feedback_play(self, banner: FeedbackBanner) -> None:
        if self.feedback is not None and self.feedback.play_expected is not None:
            self.emit('play-requested', self.feedback.play_expected)

    @Gtk.Template.Callback()
    def _on_feedback_play_given(self, banner: FeedbackBanner) -> None:
        if self.feedback is not None and self.feedback.play_given is not None:
            self.emit('play-requested', self.feedback.play_given)

    @Gtk.Template.Callback()
    def _on_next(self, _banner: FeedbackBanner) -> None:
        self.emit('next-requested')

    @Gtk.Template.Callback()
    def _on_skip_clicked(self, _button: Gtk.Button) -> None:
        self.emit('skip-requested')

    @Gtk.Template.Callback()
    def _on_hint_clicked(self, _button: Gtk.Button) -> None:
        if self.question is not None and self.question.hint:
            self.hint_revealer.set_reveal_child(True)
            self.emit('hint-requested')
