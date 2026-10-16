# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Small helpers shared by pages and widgets: settings, badges, formatting."""

from __future__ import annotations

from functools import cache
from gettext import gettext as _

from gi.repository import Gdk, Gio, Gtk

from ..core import PitchName

APP_ID = 'fi.oikarinenotto.etude'
RESOURCE_PATH = '/fi/oikarinenotto/etude'


@cache
def get_settings() -> Gio.Settings | None:
    """The application settings, or ``None`` when the schema is not installed.

    ``Gio.Settings`` aborts the process for an unknown schema, so look it up first:
    running from a source tree without compiled schemas must not crash.
    """
    source = Gio.SettingsSchemaSource.get_default()
    if source is None or source.lookup(APP_ID, True) is None:
        return None
    return Gio.Settings(schema_id=APP_ID)


def setting_bool(key: str, default: bool = False) -> bool:
    settings = get_settings()
    return settings.get_boolean(key) if settings is not None else default


def ui_resource(name: str) -> str:
    """Resource path of a file in ``src/etude/ui/``."""
    return f'{RESOURCE_PATH}/ui/{name}'


# Keyboard accelerators -------------------------------------------------------


def accel_badge(accel: str) -> Gtk.Label:
    """The small monospace key label shown on every answer control."""
    # The control announces the shortcut through KEY_SHORTCUTS instead.
    badge = Gtk.Label(
        label=accel, valign=Gtk.Align.CENTER, accessible_role=Gtk.AccessibleRole.PRESENTATION
    )
    badge.add_css_class('accel-badge')
    return badge


def set_shortcut(widget: Gtk.Widget, accel: str | None) -> None:
    if accel:
        widget.update_property([Gtk.AccessibleProperty.KEY_SHORTCUTS], [accel])


_KEYPAD = {getattr(Gdk, f'KEY_KP_{n}'): getattr(Gdk, f'KEY_{n}') for n in range(10)}


def normalize_keyval(keyval: int) -> int:
    """Lower-case letters and map keypad digits to ordinary digits."""
    keyval = _KEYPAD.get(keyval, keyval)
    return Gdk.keyval_to_lower(keyval)


def keyval_matches(keyval: int, accel: str | None) -> bool:
    """True when ``keyval`` is the single-key accelerator ``accel`` (``'1'``, ``'R'``…)."""
    if not accel or len(accel) != 1:
        return False
    expected = Gdk.unicode_to_keyval(ord(accel.lower()))
    return normalize_keyval(keyval) == expected


def keyval_letter(keyval: int) -> str | None:
    """The lower-case letter a–z typed with ``keyval``, if any."""
    char = chr(Gdk.keyval_to_unicode(normalize_keyval(keyval)) or 0)
    return char if 'a' <= char <= 'z' else None


def is_enter(keyval: int) -> bool:
    return keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_ISO_Enter)


# Formatting -------------------------------------------------------------------


def format_percent(value: float) -> str:
    """``0.94`` → ``'94%'`` (the percent sign placement is translatable)."""
    # Translators: a percentage, e.g. "94%". Use your language's spacing and sign.
    return _('{percent}%').format(percent=round(value * 100))


def format_clock(seconds: int) -> str:
    """Timer text, e.g. ``'04:12'``."""
    minutes, seconds = divmod(max(0, seconds), 60)
    return f'{minutes:02d}:{seconds:02d}'


def format_duration(ms: int) -> str:
    """Short duration, e.g. ``'4:12'``."""
    minutes, seconds = divmod(max(0, ms) // 1000, 60)
    return f'{minutes}:{seconds:02d}'


def note_label(name: PitchName) -> str:
    """Display name of a note.

    W2: switch to the user's note naming convention (``note-naming`` key) once the
    theory core's naming helpers land; W1 shows English names with Unicode accidentals.
    """
    return name.symbol
