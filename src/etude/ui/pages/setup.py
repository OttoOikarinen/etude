# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Exercise setup (design 1j), generated from an exercise's ``settings``.

"Question pool" rows come from the exercise and are stored per exercise in the
``exercise-settings`` key; the "Session" and "Accessibility" rows are bound to
application-wide GSettings keys.
"""

from __future__ import annotations

from collections.abc import Mapping
from gettext import gettext as _
from gettext import ngettext

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from ...exercises.base import (
    BoolSetting,
    ChoiceSetting,
    ExerciseDefinition,
    IntSetting,
    MultiChoiceSetting,
    Setting,
)
from ..common import get_settings, ui_resource

SESSION_BINDINGS = (
    ('questions-per-session', 'questions_row', 'value'),
    ('timed-mode', 'timed_row', 'active'),
    ('reveal-after-mistake', 'reveal_row', 'active'),
    ('large-notation', 'large_notation_row', 'active'),
    ('written-alternative', 'written_alternative_row', 'active'),
    ('announce-feedback', 'announce_row', 'active'),
)


def to_variant(value: object) -> GLib.Variant:
    """GVariant for one exercise setting value (stored in ``exercise-settings``)."""
    if isinstance(value, bool):
        return GLib.Variant('b', value)
    if isinstance(value, int):
        return GLib.Variant('i', value)
    if isinstance(value, str):
        return GLib.Variant('s', value)
    if isinstance(value, list | tuple):
        return GLib.Variant('as', [str(v) for v in value])
    raise TypeError(f'unsupported setting value: {value!r}')


def load_exercise_settings(settings: Gio.Settings | None, exercise_id: str) -> dict[str, object]:
    if settings is None:
        return {}
    stored = settings.get_value('exercise-settings').unpack()
    return dict(stored.get(exercise_id, {}))


def save_exercise_settings(
    settings: Gio.Settings | None, exercise_id: str, values: Mapping[str, object]
) -> None:
    if settings is None:
        return
    stored = settings.get_value('exercise-settings').unpack()
    stored[exercise_id] = dict(values)
    variant = GLib.Variant(
        'a{sa{sv}}',
        {ex: {k: to_variant(v) for k, v in vals.items()} for ex, vals in stored.items()},
    )
    settings.set_value('exercise-settings', variant)


def _valid(setting: Setting, value: object) -> bool:
    match setting:
        case BoolSetting():
            return isinstance(value, bool)
        case IntSetting():
            return isinstance(value, int) and setting.minimum <= value <= setting.maximum
        case ChoiceSetting():
            return value in {o.key for o in setting.options}
        case MultiChoiceSetting():
            keys = {o.key for o in setting.options}
            return isinstance(value, list | tuple) and all(v in keys for v in value)
    return False


@Gtk.Template(resource_path=ui_resource('pages/setup.ui'))
class SetupPage(Adw.NavigationPage):
    """Signal: ``start(exercise_id, settings: dict)``."""

    __gtype_name__ = 'EtudeSetupPage'
    __gsignals__ = {  # noqa: RUF012 (GObject API)
        'start': (GObject.SignalFlags.RUN_FIRST, None, (str, object)),
    }

    start_button: Gtk.Button = Gtk.Template.Child()
    preferences_page: Adw.PreferencesPage = Gtk.Template.Child()
    pool_group: Adw.PreferencesGroup = Gtk.Template.Child()
    questions_row: Adw.SpinRow = Gtk.Template.Child()
    timed_row: Adw.SwitchRow = Gtk.Template.Child()
    reveal_row: Adw.SwitchRow = Gtk.Template.Child()
    large_notation_row: Adw.SwitchRow = Gtk.Template.Child()
    written_alternative_row: Adw.SwitchRow = Gtk.Template.Child()
    announce_row: Adw.SwitchRow = Gtk.Template.Child()

    def __init__(self, exercise: ExerciseDefinition, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.exercise = exercise
        # Translators: title of the setup page, e.g. "Key Signatures — setup".
        self.set_title(_('{exercise} — Setup').format(exercise=exercise.title))
        self.settings = get_settings()
        stored = load_exercise_settings(self.settings, exercise.id)
        self.values: dict[str, object] = {}
        for setting in exercise.settings:
            value = stored.get(setting.key, setting.default)
            if not _valid(setting, value):
                value = setting.default
            self.values[setting.key] = list(value) if isinstance(value, tuple) else value
        self.rows: dict[str, Adw.PreferencesRow] = {}
        for setting in exercise.settings:
            row = self._build_row(setting)
            self.rows[setting.key] = row
            self.pool_group.add(row)
        self.pool_group.set_visible(bool(exercise.settings))
        if self.settings is not None:
            for key, attr, prop in SESSION_BINDINGS:
                self.settings.bind(key, getattr(self, attr), prop, Gio.SettingsBindFlags.DEFAULT)

    # Rows ---------------------------------------------------------------------------

    def _build_row(self, setting: Setting) -> Adw.PreferencesRow:
        match setting:
            case IntSetting():
                row = Adw.SpinRow.new_with_range(setting.minimum, setting.maximum, 1)
                row.set_value(int(self.values[setting.key]))  # type: ignore[call-overload]
                row.connect('notify::value', self._on_int_changed, setting)
            case BoolSetting():
                row = Adw.SwitchRow(active=bool(self.values[setting.key]))
                row.connect('notify::active', self._on_bool_changed, setting)
            case ChoiceSetting():
                labels = Gtk.StringList.new([o.label for o in setting.options])
                keys = [o.key for o in setting.options]
                row = Adw.ComboRow(model=labels)
                row.set_selected(keys.index(str(self.values[setting.key])))
                row.connect('notify::selected', self._on_choice_changed, setting)
            case MultiChoiceSetting():
                row = self._build_multi_row(setting)
        row.set_title(setting.title)
        if setting.subtitle and not isinstance(setting, MultiChoiceSetting):
            row.set_subtitle(setting.subtitle)  # type: ignore[attr-defined]
        return row

    def _build_multi_row(self, setting: MultiChoiceSetting) -> Adw.ExpanderRow:
        row = Adw.ExpanderRow(subtitle=setting.subtitle)
        count = Gtk.Label()
        count.add_css_class('dim-label')
        row.add_suffix(count)
        selected = self.values[setting.key]
        checks: dict[str, Gtk.CheckButton] = {}
        for option in setting.options:
            check = Gtk.CheckButton(
                active=option.key in selected,
                valign=Gtk.Align.CENTER,  # type: ignore[operator]
            )
            option_row = Adw.ActionRow(title=option.label, activatable_widget=check)
            option_row.add_prefix(check)
            check.connect('toggled', self._on_multi_toggled, setting, checks, count)
            checks[option.key] = check
            row.add_row(option_row)
        self._update_count(count, len(selected))  # type: ignore[arg-type]
        return row

    @staticmethod
    def _update_count(label: Gtk.Label, count: int) -> None:
        # Translators: summary of a multiple-choice setting, e.g. "2 selected".
        label.set_label(ngettext('{n} selected', '{n} selected', count).format(n=count))

    # Handlers -----------------------------------------------------------------------

    def _store(self, key: str, value: object) -> None:
        self.values[key] = value
        save_exercise_settings(self.settings, self.exercise.id, self.values)

    def _on_int_changed(self, row: Adw.SpinRow, _pspec: object, setting: IntSetting) -> None:
        self._store(setting.key, int(row.get_value()))

    def _on_bool_changed(self, row: Adw.SwitchRow, _pspec: object, setting: BoolSetting) -> None:
        self._store(setting.key, row.get_active())

    def _on_choice_changed(self, row: Adw.ComboRow, _pspec: object, setting: ChoiceSetting):
        self._store(setting.key, setting.options[row.get_selected()].key)

    def _on_multi_toggled(
        self,
        check: Gtk.CheckButton,
        setting: MultiChoiceSetting,
        checks: dict[str, Gtk.CheckButton],
        count: Gtk.Label,
    ) -> None:
        selected = [o.key for o in setting.options if checks[o.key].get_active()]
        if len(selected) < setting.minimum:
            check.set_active(True)  # keep at least ``minimum`` options
            return
        self._update_count(count, len(selected))
        self._store(setting.key, selected)

    @Gtk.Template.Callback()
    def _on_start_clicked(self, _button: Gtk.Button) -> None:
        self.emit('start', self.exercise.id, dict(self.values))
