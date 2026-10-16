# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Playback controls of an ear-training question (design 1e)."""

from __future__ import annotations

from gettext import ngettext

from gi.repository import Adw, GObject, Gtk

from ..common import ui_resource


@Gtk.Template(resource_path=ui_resource('widgets/ear-panel.ui'))
class EarPanel(Gtk.Box):
    """Big play button, replay, play count, context, playback mode and tempo.

    Emits ``play-requested(harmonic: bool, tempo: int)``; the exercise page
    turns that into a playback for the audio backend.
    """

    __gtype_name__ = 'EtudeEarPanel'
    __gsignals__ = {  # noqa: RUF012 (GObject API)
        'play-requested': (GObject.SignalFlags.RUN_FIRST, None, (bool, int)),
    }

    play_button: Gtk.Button = Gtk.Template.Child()
    replay_button: Gtk.Button = Gtk.Template.Child()
    played_label: Gtk.Label = Gtk.Template.Child()
    context_label: Gtk.Label = Gtk.Template.Child()
    mode_box: Gtk.Box = Gtk.Template.Child()
    mode_group: Adw.ToggleGroup = Gtk.Template.Child()
    tempo_spin: Gtk.SpinButton = Gtk.Template.Child()

    def __init__(
        self,
        context: str = '',
        tempo: int = 80,
        *,
        harmonic: bool = False,
        style_choice: bool = True,
        **kwargs: object,
    ) -> None:
        """``harmonic`` is how the question is written; ``style_choice`` offers the
        Melodic/Harmonic toggle (intervals), which some questions (chords) leave out."""
        super().__init__(**kwargs)
        self.play_count = 0
        self.mode_group.set_active_name('harmonic' if harmonic else 'melodic')
        self.mode_box.set_visible(style_choice)
        self.context_label.set_label(context)
        self.context_label.set_visible(bool(context))
        self.tempo_spin.set_value(tempo)
        self._update_count()

    @property
    def harmonic(self) -> bool:
        return self.mode_group.get_active_name() == 'harmonic'

    def play(self) -> None:
        """Request playback (the play button, R, or the page starting a question)."""
        self.play_count += 1
        self._update_count()
        self.emit('play-requested', self.harmonic, self.tempo_spin.get_value_as_int())

    def set_play_count(self, count: int) -> None:
        self.play_count = count
        self._update_count()

    def _update_count(self) -> None:
        self.played_label.set_label(
            ngettext('Played {n} time', 'Played {n} times', self.play_count).format(
                n=self.play_count
            )
        )

    @Gtk.Template.Callback()
    def _on_play_clicked(self, _button: Gtk.Button) -> None:
        self.play()
