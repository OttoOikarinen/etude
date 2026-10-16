# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Pick one option (design 1b, 1d, 1e, 1g)."""

from __future__ import annotations

import math
from gettext import gettext as _

from gi.repository import Gdk, Gtk

from ...exercises.base import ChoiceAnswer, Option
from ..common import accel_badge, keyval_matches, set_shortcut
from .base import AnswerWidget


def _columns(options: tuple[Option, ...]) -> int:
    count = len(options)
    if any(o.description for o in options):
        return min(count, 7)  # scale degrees: one row (design 1g)
    if count <= 4:
        return count
    return math.ceil(count / math.ceil(count / 4))


class ChoiceButton(Gtk.Button):
    """An option with its accelerator badge and, after answering, a state icon."""

    __gtype_name__ = 'EtudeChoiceButton'

    def __init__(self, option: Option) -> None:
        super().__init__()
        self.option = option
        self.add_css_class('answer-button')
        # Degree buttons (design 1g) stack "1" over "Tonic": the badge is the number.
        degree = bool(option.description) and option.label == option.accel
        if degree:
            self.add_css_class('degree')
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            main, secondary = option.description or '', None
        else:
            box = Gtk.Box(spacing=10)
            main, secondary = option.label, option.description
        if option.accel:
            badge = accel_badge(option.accel)
            badge.set_halign(Gtk.Align.CENTER)
            box.append(badge)
        text = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=not degree
        )
        self._label = Gtk.Label(label=main, xalign=0.5 if degree else 0, wrap=True)
        text.append(self._label)
        if secondary:
            caption = Gtk.Label(label=secondary, xalign=0)
            caption.add_css_class('caption')
            caption.add_css_class('dim-label')
            text.append(caption)
        box.append(text)
        self._icon = Gtk.Image(visible=False, accessible_role=Gtk.AccessibleRole.PRESENTATION)
        box.append(self._icon)
        self.set_child(box)
        accessible = f'{option.label}, {option.description}' if option.description else main
        self.update_property([Gtk.AccessibleProperty.LABEL], [accessible])
        set_shortcut(self, option.accel)

    def mark(self, state: str) -> None:
        """``'success'`` or ``'error'``: colour, icon and accessible text."""
        self.add_css_class(state)
        self._icon.set_from_icon_name(
            'object-select-symbolic' if state == 'success' else 'window-close-symbolic'
        )
        self._icon.set_visible(True)
        state_text = _('Correct answer') if state == 'success' else _('Your answer, wrong')
        self.update_property([Gtk.AccessibleProperty.DESCRIPTION], [state_text])
        self.set_tooltip_text(state_text)


class ChoiceGrid(AnswerWidget):
    """Renders a :class:`ChoiceAnswer`. Emits ``answered`` with the option key (``str``)."""

    __gtype_name__ = 'EtudeChoiceGrid'

    def __init__(self, spec: ChoiceAnswer, columns: int | None = None) -> None:
        super().__init__()
        self.spec = spec
        self.targets = dict(spec.targets)
        """Figure event index → option key; :meth:`select_target` answers by clicking a note."""
        self.buttons: dict[str, ChoiceButton] = {}
        self._flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=True,
            column_spacing=8,
            row_spacing=8,
            max_children_per_line=columns or _columns(spec.options),
            min_children_per_line=min(2, len(spec.options)),
        )
        self._flow.add_css_class('choice-grid')
        for option in spec.options:
            button = ChoiceButton(option)
            button.connect('clicked', self._on_clicked)
            self.buttons[option.key] = button
            self._flow.append(button)
            button.get_parent().set_focusable(False)
        self.append(self._flow)

    def _on_clicked(self, button: ChoiceButton) -> None:
        self.submit(button.option.key)

    def handle_key(self, keyval: int, state: Gdk.ModifierType) -> bool:
        if state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            return False
        for option in self.spec.options:
            if keyval_matches(keyval, option.accel):
                if not self.locked:
                    self.buttons[option.key].grab_focus()
                    self.submit(option.key)
                return True
        return False

    def select_target(self, event_index: int) -> bool:
        """Answer with the option mapped to a clicked figure event (design 1g)."""
        key = self.targets.get(event_index)
        if key is None:
            return False
        self.submit(key)
        return True

    def reveal(self, expected: object, given: object, correct: bool) -> None:
        super().reveal(expected, given, correct)
        if not correct and given in self.buttons:
            self.buttons[str(given)].mark('error')
        if expected in self.buttons:
            self.buttons[str(expected)].mark('success')

    def set_compact(self, compact: bool) -> None:
        super().set_compact(compact)
        count = len(self.spec.options)
        self._flow.set_max_children_per_line(
            min(2, count) if compact and count > 4 else _columns(self.spec.options)
        )
