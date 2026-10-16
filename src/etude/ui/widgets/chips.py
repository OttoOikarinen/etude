# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Several independent choices confirmed with Check (design 1f)."""

from __future__ import annotations

from collections.abc import Mapping
from gettext import gettext as _

from gi.repository import Adw, Gdk, Gtk

from ...core import PitchName
from ...exercises.base import ChipGroup, ChipsAnswer, Option
from ..common import accel_badge, keyval_matches, note_label, set_shortcut
from .base import AnswerWidget

_ACCIDENTAL_SUFFIX = {0: '', 1: '#', -1: 'b'}
_ACCIDENTAL_SYMBOL = {0: '♯ / ♭', 1: '♯', -1: '♭'}


class Chip(Gtk.ToggleButton):
    __gtype_name__ = 'EtudeChip'

    def __init__(self, option: Option) -> None:
        super().__init__()
        self.option = option
        self.add_css_class('pill')
        self.add_css_class('chip')
        box = Gtk.Box(spacing=6)
        # A letter chip whose key is its own letter needs no separate badge.
        if option.accel and option.accel.casefold() != option.label.casefold():
            box.append(accel_badge(option.accel))
        self.label = Gtk.Label(label=option.label)
        box.append(self.label)
        self._icon = Gtk.Image(visible=False, accessible_role=Gtk.AccessibleRole.PRESENTATION)
        box.append(self._icon)
        self.set_child(box)
        self.update_property([Gtk.AccessibleProperty.LABEL], [option.label])
        set_shortcut(self, option.accel)

    def mark(self, state: str) -> None:
        self.add_css_class(state)
        self._icon.set_from_icon_name(
            'object-select-symbolic' if state == 'success' else 'window-close-symbolic'
        )
        self._icon.set_visible(True)
        self.update_property(
            [Gtk.AccessibleProperty.DESCRIPTION],
            [_('Correct answer') if state == 'success' else _('Your answer, wrong')],
        )


class ChipGroups(AnswerWidget):
    """Renders a :class:`ChipsAnswer`.

    Emits ``answered`` with ``dict[group key, option key]`` when Check is pressed.
    For a group of natural note letters the widget adds a ♯ / ♭ chip; the value
    of that group is then the letter with ``'#'`` or ``'b'`` appended (``'Eb'``).
    """

    __gtype_name__ = 'EtudeChipGroups'

    def __init__(self, spec: ChipsAnswer) -> None:
        super().__init__(spacing=18)
        self.spec = spec
        self.chips: dict[str, dict[str, Chip]] = {}
        self._alter: dict[str, int] = {}
        self._accidental_chips: dict[str, Gtk.Button] = {}
        for group in spec.groups:
            self.append(self._build_group(group))

        footer = Gtk.Box(spacing=12)
        self.summary = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        self.summary.add_css_class('dim-label')
        footer.append(self.summary)
        self.check_button = Gtk.Button(sensitive=False)
        self.check_button.add_css_class('suggested-action')
        self.check_button.add_css_class('pill')
        check_box = Gtk.Box(spacing=8)
        check_box.append(Gtk.Label(label=_('Check')))
        check_box.append(accel_badge('↵'))
        self.check_button.set_child(check_box)
        self.check_button.update_property([Gtk.AccessibleProperty.LABEL], [_('Check')])
        set_shortcut(self.check_button, 'Return')
        self.check_button.connect('clicked', lambda _b: self.activate_default())
        footer.append(self.check_button)
        self.append(footer)
        self._update()

    def _build_group(self, group: ChipGroup) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        title = Gtk.Label(label=group.label, xalign=0)
        title.add_css_class('heading')
        box.append(title)
        wrap = Adw.WrapBox(child_spacing=6, line_spacing=6)
        wrap.update_property([Gtk.AccessibleProperty.LABEL], [group.label])
        self.chips[group.key] = {}
        first: Chip | None = None
        for option in group.options:
            chip = Chip(option)
            if first is None:
                first = chip
            else:
                chip.set_group(first)
            chip.connect('toggled', lambda _c: self._update())
            self.chips[group.key][option.key] = chip
            wrap.append(chip)
        if group.accidentals:
            self._alter[group.key] = 0
            accidental = Gtk.Button(label=_ACCIDENTAL_SYMBOL[0], tooltip_text=_('Sharp or flat'))
            accidental.add_css_class('pill')
            accidental.add_css_class('chip')
            accidental.connect('clicked', self._on_accidental, group)
            self._accidental_chips[group.key] = accidental
            wrap.append(accidental)
        box.append(wrap)
        return box

    def _on_accidental(self, button: Gtk.Button, group: ChipGroup) -> None:
        alter = {0: 1, 1: -1, -1: 0}[self._alter[group.key]]
        self._alter[group.key] = alter
        button.set_label(_ACCIDENTAL_SYMBOL[alter])
        for option in group.options:
            chip = self.chips[group.key][option.key]
            name = PitchName.parse(option.key)
            chip.label.set_label(note_label(PitchName(name.letter, alter)))
        self._update()

    def _selected(self, group: ChipGroup) -> Chip | None:
        return next((c for c in self.chips[group.key].values() if c.get_active()), None)

    def value(self) -> dict[str, str]:
        result = {}
        for group in self.spec.groups:
            chip = self._selected(group)
            if chip is not None:
                suffix = _ACCIDENTAL_SUFFIX[self._alter.get(group.key, 0)]
                result[group.key] = chip.option.key + suffix
        return result

    def _update(self) -> None:
        parts = []
        for group in self.spec.groups:
            chip = self._selected(group)
            parts.append(chip.label.get_label() if chip is not None else '…')
        # Translators: live summary of the chips chosen so far, e.g. "E, Minor, Root position".
        self.summary.set_label(_('Your answer so far: {answer}').format(answer=', '.join(parts)))
        complete = len(self.value()) == len(self.spec.groups)
        self.check_button.set_sensitive(complete and not self.locked)

    def handle_key(self, keyval: int, state: Gdk.ModifierType) -> bool:
        if self.locked or state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            return False
        for group in self.spec.groups:
            for option in group.options:
                if keyval_matches(keyval, option.accel):
                    self.chips[group.key][option.key].set_active(True)
                    return True
        return False

    def activate_default(self) -> bool:
        if self.locked or len(self.value()) != len(self.spec.groups):
            return False
        self.submit(self.value())
        self.check_button.set_sensitive(False)
        return True

    def reveal(self, expected: object, given: object, correct: bool) -> None:
        super().reveal(expected, given, correct)
        expected_map = expected if isinstance(expected, Mapping) else {}
        given_map = given if isinstance(given, Mapping) else {}
        for group in self.spec.groups:
            right = str(expected_map.get(group.key, ''))
            chosen = str(given_map.get(group.key, ''))
            chips = self.chips[group.key]
            if chosen != right and chosen in chips:
                chips[chosen].mark('error')
            if right in chips:
                chips[right].mark('success')
            for chip in chips.values():
                chip.set_can_target(False)
        self.check_button.set_sensitive(False)
