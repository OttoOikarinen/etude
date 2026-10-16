# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Answer on an on-screen piano keyboard or with letter keys (design 1c, 3b)."""

from __future__ import annotations

from gettext import gettext as _

from gi.repository import Adw, Gdk, GObject, Gtk

from ...core import Pitch, PitchName
from ...core.pitch import Letter
from ...exercises.base import PianoAnswer
from ..common import keyval_letter, note_label, set_shortcut
from .base import AnswerWidget

_ACCIDENTAL_SYMBOLS = {0: '', 1: '♯', -1: '♭'}


class PianoKey(Gtk.Button):
    __gtype_name__ = 'EtudePianoKey'

    def __init__(self, pitch: Pitch) -> None:
        super().__init__(focus_on_click=False)
        self.pitch = pitch
        self.black = pitch.alter != 0
        self.add_css_class('piano-key')
        self.add_css_class('black' if self.black else 'white')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.END)
        self._icon = Gtk.Image(visible=False, accessible_role=Gtk.AccessibleRole.PRESENTATION)
        box.append(self._icon)
        if not self.black:
            box.append(Gtk.Label(label=note_label(pitch.name)))
            name = note_label(pitch.name)
        else:
            flat = Pitch.from_midi(pitch.midi, prefer_flats=True)
            name = f'{note_label(pitch.name)} / {note_label(flat.name)}'
        self.set_child(box)
        self.update_property([Gtk.AccessibleProperty.LABEL], [name])

    def mark(self, state: str | None) -> None:
        for css in ('success', 'error'):
            self.remove_css_class(css)
        if state is None:
            self._icon.set_visible(False)
            return
        self.add_css_class(state)
        self._icon.set_from_icon_name(
            'object-select-symbolic' if state == 'success' else 'window-close-symbolic'
        )
        self._icon.set_visible(True)
        self.update_property(
            [Gtk.AccessibleProperty.DESCRIPTION],
            [_('Correct answer') if state == 'success' else _('Your answer, wrong')],
        )


class PianoKeyboard(Gtk.Widget):
    """A custom-laid-out keyboard: white keys side by side, black keys on top.

    Keys are buttons, so they are focusable, accessible and styled by CSS (and
    so follow the accent colour and dark style). Emits ``key-activated`` with
    the :class:`~etude.core.Pitch` of a clicked key.
    """

    __gtype_name__ = 'EtudePianoKeyboard'
    __gsignals__ = {  # noqa: RUF012 (GObject API)
        'key-activated': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    def __init__(self, low: Pitch, high: Pitch) -> None:
        super().__init__(hexpand=True, accessible_role=Gtk.AccessibleRole.GROUP)
        self.add_css_class('piano-keyboard')
        self.update_property([Gtk.AccessibleProperty.LABEL], [_('Piano keyboard')])
        pitches = [Pitch.from_midi(m) for m in range(low.midi, high.midi + 1)]
        self.keys = [PianoKey(p) for p in pitches if p.alter == 0]
        self.keys += [PianoKey(p) for p in pitches if p.alter != 0]
        # White keys first so that black keys are drawn and picked on top.
        for key in self.keys:
            key.set_parent(self)
            key.connect('clicked', lambda k: self.emit('key-activated', k.pitch))
        self._white = [k for k in self.keys if not k.black]

    def do_dispose(self) -> None:
        child = self.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            child.unparent()
            child = following

    def do_get_request_mode(self) -> Gtk.SizeRequestMode:
        return Gtk.SizeRequestMode.CONSTANT_SIZE

    def do_measure(self, orientation: Gtk.Orientation, for_size: int) -> tuple[int, int, int, int]:
        if orientation == Gtk.Orientation.HORIZONTAL:
            return len(self._white) * 34, len(self._white) * 64, -1, -1
        return 120, 168, -1, -1

    def do_size_allocate(self, width: int, height: int, baseline: int) -> None:
        count = len(self._white)
        key_width = width / count
        edges = [round(i * key_width) for i in range(count + 1)]
        black_width = round(key_width * 0.6)
        black_height = round(height * 0.6)
        whites_before = 0
        for key in self.keys:
            if not key.black:
                index = self._white.index(key)
                rect = Gdk.Rectangle()
                rect.x, rect.y = edges[index], 0
                rect.width, rect.height = edges[index + 1] - edges[index], height
                key.size_allocate(rect, -1)
        for key in self.keys:
            if key.black:
                whites_before = sum(1 for w in self._white if w.pitch.midi < key.pitch.midi)
                rect = Gdk.Rectangle()
                rect.x = edges[whites_before] - black_width // 2
                rect.y, rect.width, rect.height = 0, black_width, black_height
                key.size_allocate(rect, -1)

    def find(self, value: Pitch | PitchName) -> PianoKey | None:
        for key in sorted(self.keys, key=lambda k: k.pitch.midi):
            if isinstance(value, Pitch) and key.pitch.midi == value.midi:
                return key
            if isinstance(value, PitchName) and key.pitch.pitch_class == value.pitch_class:
                return key
        return None

    def mark(self, value: Pitch | PitchName, state: str) -> None:
        key = self.find(value)
        if key is not None:
            key.mark(state)

    def clear_marks(self) -> None:
        for key in self.keys:
            key.mark(None)


class PianoAnswerView(AnswerWidget):
    """Renders a :class:`PianoAnswer`.

    Emits ``answered`` with a :class:`~etude.core.Pitch` when ``octave_matters``,
    otherwise with a :class:`~etude.core.PitchName`. Letter keys a–g answer, and
    Shift + letter gives the sharp. In the narrow layout the keyboard moves to a
    bottom sheet and letter buttons with a ♯ / ♭ toggle take its place.
    """

    __gtype_name__ = 'EtudePianoAnswerView'

    def __init__(self, spec: PianoAnswer) -> None:
        super().__init__()
        self.spec = spec
        self._alter = 0
        self._keyboards: list[PianoKeyboard] = []
        self._stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.append(self._stack)

        wide = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.keyboard = self._new_keyboard()
        wide.append(self.keyboard)
        if spec.letter_keys:
            hint = Gtk.Label(
                label=_('Type a–g to answer, or click a key. Shift + letter for sharps.'),
                wrap=True,
            )
            hint.add_css_class('dim-label')
            wide.append(hint)
        self._stack.add_named(wide, 'wide')

        compact = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        # Wraps on very narrow screens so that every button keeps a 48 px target.
        row = Adw.WrapBox(child_spacing=4, line_spacing=4, justify=Adw.JustifyMode.FILL)
        row.add_css_class('letter-row')
        self.letter_buttons: dict[Letter, Gtk.Button] = {}
        for letter in Letter:
            button = Gtk.Button(label=note_label(PitchName(letter)))
            button.add_css_class('answer-button')
            button.connect('clicked', self._on_letter_clicked, letter)
            set_shortcut(button, letter.name.lower())
            self.letter_buttons[letter] = button
            row.append(button)
        self._accidental = Gtk.Button(label='♯ / ♭', tooltip_text=_('Sharp or flat'))
        self._accidental.add_css_class('answer-button')
        self._accidental.connect('clicked', self._on_accidental_clicked)
        row.append(self._accidental)
        compact.append(row)
        show = Gtk.Button(label=_('Show piano keyboard'), halign=Gtk.Align.CENTER)
        show.add_css_class('pill')
        show.connect('clicked', lambda _b: self.emit('sheet-requested'))
        compact.append(show)
        self._stack.add_named(compact, 'compact')
        self._sheet: Gtk.Widget | None = None

    def _new_keyboard(self) -> PianoKeyboard:
        keyboard = PianoKeyboard(self.spec.low, self.spec.high)
        keyboard.connect('key-activated', lambda _k, pitch: self.submit(self._value(pitch)))
        self._keyboards.append(keyboard)
        return keyboard

    def _value(self, pitch: Pitch) -> Pitch | PitchName:
        return pitch if self.spec.octave_matters else pitch.name

    def _from_name(self, name: PitchName) -> Pitch | PitchName:
        if not self.spec.octave_matters:
            return name
        for octave in range(self.spec.low.octave, self.spec.high.octave + 1):
            pitch = name.at(octave)
            if self.spec.low <= pitch <= self.spec.high:
                return pitch
        return name.at(self.spec.low.octave)

    def _on_letter_clicked(self, _button: Gtk.Button, letter: Letter) -> None:
        self.submit(self._from_name(PitchName(letter, self._alter)))

    def _on_accidental_clicked(self, _button: Gtk.Button) -> None:
        self._alter = {0: 1, 1: -1, -1: 0}[self._alter]
        for letter, button in self.letter_buttons.items():
            button.set_label(note_label(PitchName(letter, self._alter)))
        self._accidental.set_label(_ACCIDENTAL_SYMBOLS[self._alter] or '♯ / ♭')

    def handle_key(self, keyval: int, state: Gdk.ModifierType) -> bool:
        if not self.spec.letter_keys or state & (
            Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK
        ):
            return False
        letter = keyval_letter(keyval)
        if letter is None or letter not in 'abcdefg':
            return False
        alter = 1 if state & Gdk.ModifierType.SHIFT_MASK else 0
        self.submit(self._from_name(PitchName(Letter[letter.upper()], alter)))
        return True

    def reveal(self, expected: object, given: object, correct: bool) -> None:
        super().reveal(expected, given, correct)
        for keyboard in self._keyboards:
            if not correct and isinstance(given, Pitch | PitchName):
                keyboard.mark(given, 'error')
            if isinstance(expected, Pitch | PitchName):
                keyboard.mark(expected, 'success')
        for letter, button in self.letter_buttons.items():
            name = PitchName(letter, self._alter)
            for value, css in ((given, 'error'), (expected, 'success')):
                value_name = value.name if isinstance(value, Pitch) else value
                if value_name == name and (css == 'success' or not correct):
                    self._mark_letter(button, css)

    @staticmethod
    def _mark_letter(button: Gtk.Button, css: str) -> None:
        """Colour, icon and accessible text on a letter button."""
        label = button.get_label() or ''
        button.add_css_class(css)
        box = Gtk.Box(spacing=4, halign=Gtk.Align.CENTER)
        icon = 'object-select-symbolic' if css == 'success' else 'window-close-symbolic'
        box.append(Gtk.Image(icon_name=icon, accessible_role=Gtk.AccessibleRole.PRESENTATION))
        box.append(Gtk.Label(label=label))
        button.set_child(box)
        button.update_property(
            [Gtk.AccessibleProperty.LABEL, Gtk.AccessibleProperty.DESCRIPTION],
            [label, _('Correct answer') if css == 'success' else _('Your answer, wrong')],
        )

    def set_compact(self, compact: bool) -> None:
        super().set_compact(compact)
        self._stack.set_visible_child_name('compact' if compact else 'wide')

    def get_sheet(self) -> Gtk.Widget:
        if self._sheet is None:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            box.add_css_class('piano-sheet')
            title = Gtk.Label(label=_('Piano Keyboard'))
            title.add_css_class('heading')
            box.append(title)
            box.append(self._new_keyboard())
            self._sheet = box
        return self._sheet
