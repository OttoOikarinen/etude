# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The banner shown after answering (design 1c, 1d, 2b)."""

from __future__ import annotations

from gettext import gettext as _

from gi.repository import Adw, GObject, Gtk

from ...exercises.base import Feedback
from ..common import setting_bool, ui_resource


@Gtk.Template(resource_path=ui_resource('widgets/feedback.ui'))
class FeedbackBanner(Gtk.Box):
    """Shows a :class:`Feedback` with colour, icon and text, and announces it.

    Signals: ``next`` (Next ↵ pressed) and ``play`` (the play button, e.g.
    "Play interval", pressed).
    """

    __gtype_name__ = 'EtudeFeedbackBanner'
    __gsignals__ = {  # noqa: RUF012 (GObject API)
        'next': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'play': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    icon: Gtk.Image = Gtk.Template.Child()
    title: Gtk.Label = Gtk.Template.Child()
    detail: Gtk.Label = Gtk.Template.Child()
    play_button: Gtk.Button = Gtk.Template.Child()
    play_content: Adw.ButtonContent = Gtk.Template.Child()
    next_button: Gtk.Button = Gtk.Template.Child()
    actions: Gtk.Box = Gtk.Template.Child()

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.feedback: Feedback | None = None

    def show_feedback(
        self,
        feedback: Feedback,
        *,
        response_ms: int | None = None,
        play_label: str | None = None,
        announce: bool | None = None,
    ) -> None:
        """Display ``feedback``.

        ``play_label`` names the play button ("Play interval"); it is shown when the
        feedback carries ``play_expected``. ``announce`` defaults to the
        ``announce-feedback`` setting.
        """
        self.feedback = feedback
        # Not Adwaita's .success/.error classes: those recolour every child, buttons included.
        state, other = (
            ('feedback-success', 'feedback-error')
            if feedback.correct
            else ('feedback-error', 'feedback-success')
        )
        self.remove_css_class(other)
        self.add_css_class(state)
        self.icon.set_from_icon_name(
            'object-select-symbolic' if feedback.correct else 'dialog-error-symbolic'
        )
        self.title.set_label(feedback.title)
        detail = feedback.detail
        if response_ms is not None:
            # Translators: appended to the feedback, e.g. "Answered in 1.8 s."
            timing = _('Answered in {seconds} s.').format(seconds=f'{response_ms / 1000:.1f}')
            detail = f'{detail} {timing}'.strip()
        self.detail.set_label(detail)
        self.detail.set_visible(bool(detail))
        self.play_button.set_visible(feedback.play_expected is not None)
        self.play_content.set_label(play_label or _('Play answer'))
        if announce is None:
            announce = setting_bool('announce-feedback', True)
        if announce:
            self.announce(
                f'{feedback.title}. {detail}'.strip(),
                Gtk.AccessibleAnnouncementPriority.MEDIUM,
            )

    def set_compact(self, compact: bool) -> None:
        """Narrow layout: the buttons go below the text."""
        self.set_orientation(Gtk.Orientation.VERTICAL if compact else Gtk.Orientation.HORIZONTAL)
        self.actions.set_halign(Gtk.Align.END if compact else Gtk.Align.FILL)

    @Gtk.Template.Callback()
    def _on_next_clicked(self, _button: Gtk.Button) -> None:
        self.emit('next')

    @Gtk.Template.Callback()
    def _on_play_clicked(self, _button: Gtk.Button) -> None:
        self.emit('play')
