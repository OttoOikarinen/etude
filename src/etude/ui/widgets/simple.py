# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Typed answers, placeholders for later input kinds, and the answer-widget factory."""

from __future__ import annotations

from gettext import gettext as _

from gi.repository import Gtk

from ...exercises.base import (
    AnswerSpec,
    ChipsAnswer,
    ChoiceAnswer,
    PianoAnswer,
    RhythmInputAnswer,
    StaffInputAnswer,
    TapAnswer,
    TextAnswer,
)
from ..common import accel_badge, set_shortcut
from .base import AnswerWidget
from .chips import ChipGroups
from .choice_grid import ChoiceGrid
from .piano import PianoAnswerView


class TextAnswerView(AnswerWidget):
    """Renders a :class:`TextAnswer`. Emits ``answered`` with the typed ``str``."""

    __gtype_name__ = 'EtudeTextAnswerView'

    def __init__(self, spec: TextAnswer) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.CENTER)
        self.spec = spec
        self.entry = Gtk.Entry(placeholder_text=spec.placeholder, width_chars=24)
        self.entry.update_property(
            [Gtk.AccessibleProperty.LABEL], [spec.placeholder or _('Answer')]
        )
        self.entry.connect('activate', lambda _e: self.activate_default())
        self.entry.connect('changed', lambda _e: self._update())
        self.append(self.entry)
        self.check_button = Gtk.Button(sensitive=False)
        self.check_button.add_css_class('suggested-action')
        box = Gtk.Box(spacing=8)
        box.append(Gtk.Label(label=_('Check')))
        box.append(accel_badge('↵'))
        self.check_button.set_child(box)
        self.check_button.update_property([Gtk.AccessibleProperty.LABEL], [_('Check')])
        set_shortcut(self.check_button, 'Return')
        self.check_button.connect('clicked', lambda _b: self.activate_default())
        self.append(self.check_button)

    def _update(self) -> None:
        self.check_button.set_sensitive(bool(self.entry.get_text().strip()) and not self.locked)

    def activate_default(self) -> bool:
        text = self.entry.get_text().strip()
        if self.locked or not text:
            return False
        self.submit(text)
        return True

    def reveal(self, expected: object, given: object, correct: bool) -> None:
        super().reveal(expected, given, correct)
        self.entry.set_editable(False)
        self.entry.add_css_class('success' if correct else 'error')
        self.check_button.set_sensitive(False)


class PlaceholderAnswerView(AnswerWidget):
    """Stands in for answer kinds that later waves implement."""

    __gtype_name__ = 'EtudePlaceholderAnswerView'

    def __init__(self, text: str) -> None:
        super().__init__()
        label = Gtk.Label(label=text, wrap=True, justify=Gtk.Justification.CENTER)
        label.add_css_class('dim-label')
        label.add_css_class('coming-later')
        self.append(label)


def create_answer_widget(spec: AnswerSpec) -> AnswerWidget:
    """The answer widget for one :data:`AnswerSpec`."""
    match spec:
        case ChoiceAnswer():
            return ChoiceGrid(spec)
        case PianoAnswer():
            return PianoAnswerView(spec)
        case ChipsAnswer():
            return ChipGroups(spec)
        case TextAnswer():
            return TextAnswerView(spec)
        case StaffInputAnswer():
            return PlaceholderAnswerView(_('Writing notes on the staff is coming later.'))
        case RhythmInputAnswer():
            return PlaceholderAnswerView(_('Building rhythms is coming later.'))
        case TapAnswer():
            return PlaceholderAnswerView(_('Tapping rhythms is coming later.'))
    raise TypeError(f'unsupported answer spec: {spec!r}')
