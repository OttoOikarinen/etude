# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The preferences dialog (``app.preferences``), bound to GSettings."""

from __future__ import annotations

from gi.repository import Adw, Gio, Gtk

from ..common import get_settings, ui_resource
from ..timing import Player
from .calibration import CalibrationPage, latency_text

BOUND = (
    ('daily-goal', 'daily_goal_row', 'value'),
    ('questions-per-session', 'questions_row', 'value'),
    ('timed-mode', 'timed_row', 'active'),
    ('reveal-after-mistake', 'reveal_row', 'active'),
    ('large-notation', 'large_notation_row', 'active'),
    ('written-alternative', 'written_alternative_row', 'active'),
    ('announce-feedback', 'announce_row', 'active'),
)

# Enum keys shown as combo rows; the row order matches the enum values in the schema.
ENUMS = (
    ('note-naming', 'note_naming_row'),
    ('instrument', 'instrument_row'),
)


@Gtk.Template(resource_path=ui_resource('dialogs/preferences.ui'))
class PreferencesDialog(Adw.PreferencesDialog):
    __gtype_name__ = 'EtudePreferencesDialog'

    note_naming_row: Adw.ComboRow = Gtk.Template.Child()
    instrument_row: Adw.ComboRow = Gtk.Template.Child()
    daily_goal_row: Adw.SpinRow = Gtk.Template.Child()
    questions_row: Adw.SpinRow = Gtk.Template.Child()
    timed_row: Adw.SwitchRow = Gtk.Template.Child()
    reveal_row: Adw.SwitchRow = Gtk.Template.Child()
    large_notation_row: Adw.SwitchRow = Gtk.Template.Child()
    written_alternative_row: Adw.SwitchRow = Gtk.Template.Child()
    announce_row: Adw.SwitchRow = Gtk.Template.Child()
    tap_timing_row: Adw.ActionRow = Gtk.Template.Child()
    reset_latency_button: Gtk.Button = Gtk.Template.Child()

    def __init__(
        self,
        settings: Gio.Settings | None = None,
        *,
        player: Player | None = None,
        **kwargs: object,
    ) -> None:
        """``player`` plays the calibration clicks; without one they are only shown."""
        super().__init__(**kwargs)
        self.settings = settings or get_settings()
        self.player = player
        self.calibration: CalibrationPage | None = None
        if self.settings is None:
            self.tap_timing_row.set_sensitive(False)
            return
        self._show_latency()
        latency_handler = self.settings.connect(
            'changed::audio-latency-ms', lambda *_a: self._show_latency()
        )
        settings_ = self.settings
        self.connect('closed', lambda *_a: settings_.disconnect(latency_handler))
        for key, attr, prop in BOUND:
            self.settings.bind(key, getattr(self, attr), prop, Gio.SettingsBindFlags.DEFAULT)
        for key, attr in ENUMS:
            self._bind_enum(key, getattr(self, attr))

    def _bind_enum(self, key: str, row: Adw.ComboRow) -> None:
        """Two-way binding of an enum key to a combo row's selected index."""
        assert self.settings is not None
        settings = self.settings
        row.set_selected(settings.get_enum(key))

        def on_selected(row: Adw.ComboRow, _pspec: object) -> None:
            if settings.get_enum(key) != row.get_selected():
                settings.set_enum(key, row.get_selected())

        def on_changed(settings: Gio.Settings, _key: str) -> None:
            if row.get_selected() != settings.get_enum(key):
                row.set_selected(settings.get_enum(key))

        row.connect('notify::selected', on_selected)
        handler = settings.connect(f'changed::{key}', on_changed)
        self.connect('closed', lambda *_a: settings.disconnect(handler))

    # Tap timing

    def _show_latency(self) -> None:
        assert self.settings is not None
        value = self.settings.get_int('audio-latency-ms')
        self.tap_timing_row.set_subtitle(latency_text(value))
        self.reset_latency_button.set_sensitive(value != 0)

    def open_calibration(self) -> CalibrationPage:
        self.calibration = CalibrationPage(self.settings, self.player)
        self.push_subpage(self.calibration)
        return self.calibration

    @Gtk.Template.Callback()
    def _on_calibrate_activated(self, _row: Adw.ActionRow) -> None:
        self.open_calibration()

    @Gtk.Template.Callback()
    def _on_reset_latency_clicked(self, _button: Gtk.Button) -> None:
        if self.settings is not None:
            self.settings.reset('audio-latency-ms')
