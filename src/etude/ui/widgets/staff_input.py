# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Write notes on a staff (construction exercises, later dictation and SATB).

The learner clicks a line or space, or moves a cursor note with the
keyboard, and confirms with Check. The state lives in
:class:`~etude.ui.widgets.staff_entry.StaffEntry`, which has no GTK code;
this module draws it with :class:`~etude.notation.widget.StaffView` and maps
pointer and keys onto it.

Keyboard: ↑ / ↓ move the note a staff step (Shift: an octave), a–g write that
letter nearest the cursor (Shift: sharp), ``+`` / ``#`` sharp, ``-`` flat,
``=`` natural, Backspace clears, ← / → change slot, Enter checks. The cursor
note is announced through the accessible value and description ("E4").
"""

from __future__ import annotations

from gettext import gettext as _

from gi.repository import Adw, Gdk, Gtk

from ...core import Pitch
from ...core.pitch import Letter
from ...exercises.base import StaffInputAnswer
from ...notation.spec import Clef, StaffSpec
from ...notation.widget import StaffView
from ..common import accel_badge, keyval_letter, set_shortcut, setting_bool
from ..figure import LARGE_SCALE, pitch_label
from .base import AnswerWidget
from .staff_entry import (
    MAX_POSITION,
    MIN_POSITION,
    Accidental,
    StaffEntry,
    Value,
    clamp,
)

STAFF_SPACE = 20.0
"""Larger than question figures: the staff is a target, a step is half a space."""
MAX_WIDTH = 440

_SHARP_KEYS = frozenset((Gdk.KEY_plus, Gdk.KEY_KP_Add, Gdk.KEY_numbersign))
_FLAT_KEYS = frozenset((Gdk.KEY_minus, Gdk.KEY_KP_Subtract))
_NATURAL_KEYS = frozenset((Gdk.KEY_equal,))
_UP_KEYS = frozenset((Gdk.KEY_Up, Gdk.KEY_KP_Up))
_DOWN_KEYS = frozenset((Gdk.KEY_Down, Gdk.KEY_KP_Down))
_CLEAR_KEYS = frozenset((Gdk.KEY_BackSpace, Gdk.KEY_Delete, Gdk.KEY_KP_Delete))


def _staff_name(clef: Clef) -> str:
    names = {
        Clef.TREBLE: _('Treble staff'),
        Clef.BASS: _('Bass staff'),
        Clef.ALTO: _('Alto staff'),
        Clef.TENOR: _('Tenor staff'),
    }
    return names.get(clef, _('Staff'))


def _names(pitches: list[Pitch]) -> str:
    # Translators: separator between note names in a list such as "G4, E5".
    return _(', ').join(pitch_label(p) for p in pitches)


class _StaffCanvas(Adw.Bin):
    """The focusable staff: the keyboard target and what screen readers announce."""

    __gtype_name__ = 'EtudeStaffCanvas'

    def __init__(self) -> None:
        super().__init__(focusable=True, accessible_role=Gtk.AccessibleRole.SLIDER)
        self.add_css_class('staff-input-canvas')
        self.add_css_class('figure-card')


class StaffInputView(AnswerWidget):
    """Renders a :class:`StaffInputAnswer`.

    Emits ``answered`` with ``tuple[tuple[Pitch, ...], ...]``, one chord per
    slot (a single note per slot at level 1), when Check or Enter is pressed.
    """

    __gtype_name__ = 'EtudeStaffInputView'

    def __init__(self, spec: StaffInputAnswer) -> None:
        super().__init__(spacing=12)
        self.spec = spec
        given = spec.given if isinstance(spec.given, StaffSpec) else None
        self.entry = StaffEntry(spec.clef, spec.key_signature, spec.slots or 1, given)
        self.hover: int | None = None

        self.view = StaffView(
            staff_space=STAFF_SPACE,
            scale=LARGE_SCALE if setting_bool('large-notation') else 1.0,
            fill_width=True,
            hexpand=True,
            focusable=False,
        )
        self.view.add_css_class('staff-view')
        self.view.set_pitch_namer(pitch_label)
        self.view.reserve_positions(MIN_POSITION, MAX_POSITION)
        click = Gtk.GestureClick.new()
        click.connect('pressed', self._on_pressed)
        self.view.add_controller(click)
        motion = Gtk.EventControllerMotion.new()
        motion.connect('motion', self._on_motion)
        motion.connect('leave', self._on_leave)
        self.view.add_controller(motion)

        self.canvas = _StaffCanvas()
        self.canvas.set_child(self.view)
        self.canvas.update_property(
            [
                Gtk.AccessibleProperty.LABEL,
                Gtk.AccessibleProperty.VALUE_MIN,
                Gtk.AccessibleProperty.VALUE_MAX,
            ],
            [_('Staff for your answer'), float(MIN_POSITION), float(MAX_POSITION)],
        )
        keys = Gtk.EventControllerKey.new()
        keys.connect('key-pressed', self._on_key)
        self.canvas.add_controller(keys)
        clamp_box = Adw.Clamp(maximum_size=MAX_WIDTH, child=self.canvas)
        self.append(clamp_box)

        # Accidental toggles, Clear and Check. Wraps at 400 px; every button is a 48 px
        # target in the narrow layout.
        tools = Adw.WrapBox(
            child_spacing=6, line_spacing=6, justify=Adw.JustifyMode.NONE, halign=Gtk.Align.CENTER
        )
        tools.add_css_class('staff-input-tools')
        self.accidental_buttons: dict[Accidental, Gtk.ToggleButton] = {}
        for accidental, symbol, accel, name in (
            (Accidental.SHARP, '♯', '+', _('Sharp')),
            (Accidental.NATURAL, '♮', '=', _('Natural')),
            (Accidental.FLAT, '♭', '−', _('Flat')),
        ):
            button = Gtk.ToggleButton(tooltip_text=name)
            button.add_css_class('answer-button')
            button.add_css_class('accidental-toggle')
            box = Gtk.Box(spacing=8)
            box.append(Gtk.Label(label=symbol))
            box.append(accel_badge(accel))
            button.set_child(box)
            button.update_property([Gtk.AccessibleProperty.LABEL], [name])
            set_shortcut(button, accel if accel != '−' else '-')
            button.connect('toggled', self._on_accidental_toggled, accidental)
            self.accidental_buttons[accidental] = button
            tools.append(button)
        self.clear_button = Gtk.Button(tooltip_text=_('Clear the note'))
        self.clear_button.add_css_class('answer-button')
        clear_box = Gtk.Box(spacing=8)
        clear_box.append(Gtk.Label(label=_('Clear')))
        clear_box.append(accel_badge('⌫'))
        self.clear_button.set_child(clear_box)
        self.clear_button.update_property([Gtk.AccessibleProperty.LABEL], [_('Clear')])
        set_shortcut(self.clear_button, 'BackSpace')
        self.clear_button.connect('clicked', lambda _b: self._clear())
        tools.append(self.clear_button)
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
        tools.append(self.check_button)
        self.append(tools)

        self.hint = Gtk.Label(
            label=_(
                'Click a line or space, or use ↑ ↓ and the letters a–g. '
                '+ sharp, − flat, = natural, Backspace clears.'
            ),
            wrap=True,
            justify=Gtk.Justification.CENTER,
        )
        self.hint.add_css_class('dim-label')
        self.hint.add_css_class('caption')
        self.append(self.hint)
        self._syncing = False
        self.refresh()

    # State → widgets

    def refresh(self) -> None:
        """Redraw the staff and update buttons and accessible state from the entry."""
        if self.locked:
            return
        self.view.figure = self.entry.figure(self.hover, description=self._description())
        self._syncing = True
        for accidental, button in self.accidental_buttons.items():
            button.set_active(self.entry.accidental is accidental)
        self._syncing = False
        note = self.entry.notes[self.entry.current]
        self.clear_button.set_sensitive(note is not None)
        self.check_button.set_sensitive(self.entry.complete)
        cursor = pitch_label(self.entry.cursor_pitch)
        if note is not None:
            text = pitch_label(note)
        else:
            # Translators: the staff input's cursor before a note is written, e.g.
            # "E4, not written yet".
            text = _('{note}, not written yet').format(note=cursor)
        self.canvas.update_property(
            [
                Gtk.AccessibleProperty.VALUE_NOW,
                Gtk.AccessibleProperty.VALUE_TEXT,
                Gtk.AccessibleProperty.DESCRIPTION,
            ],
            [float(self.entry.cursor), text, text],
        )

    def _description(self) -> str:
        parts = [_staff_name(self.entry.clef)]
        given = self.entry.given_pitches()
        if given:
            # Translators: part of the staff input's description, e.g. "Given: G4".
            parts.append(_('Given: {notes}').format(notes=_names(given)))
        written = [n for n in self.entry.notes if n is not None]
        if written:
            # Translators: part of the staff input's description, e.g. "Written: E5".
            parts.append(_('Written: {notes}').format(notes=_names(written)))
        else:
            parts.append(_('No note written yet'))
        # Translators: separator between the parts of the staff input's description.
        return _('. ').join(parts) + '.'

    # Editing

    def _clear(self) -> bool:
        if self.locked:
            return False
        cleared = self.entry.clear()
        self.refresh()
        return cleared

    def _on_accidental_toggled(self, button: Gtk.ToggleButton, accidental: Accidental) -> None:
        if self._syncing or self.locked:
            return
        self.entry.toggle_accidental(accidental)
        self.refresh()
        self.canvas.grab_focus()

    def _point(self, x: float, y: float) -> tuple[int, int | None] | None:
        """``(staff position, slot or None)`` under a pointer position on the view."""
        found = self.view.staff_position_at(x, y)
        if found is None:
            return None
        position = clamp(found[1])
        slot = None
        point = self.view.display_point(x, y)
        display = self.view.display_list
        if self.entry.slots > 1 and point is not None and display is not None:
            columns = display.event_x[0] if display.event_x else ()
            events = self.entry.slot_events()
            candidates = [(abs(columns[e] - point[0]), s) for s, e in enumerate(events)]
            if candidates:
                distance, nearest = min(candidates)
                if distance < 2.5:
                    slot = nearest
                elif point[0] > columns[events[-1]] and len(events) < self.entry.slots:
                    slot = len(events)
        return position, slot

    def _on_pressed(self, _gesture: Gtk.GestureClick, _n: int, x: float, y: float) -> None:
        if self.locked:
            return
        found = self._point(x, y)
        if found is None:
            return
        position, slot = found
        if slot is not None:
            self.entry.select(slot)
        self.entry.place(position)
        self.hover = None
        self.canvas.grab_focus()
        self.refresh()

    def _on_motion(self, _controller: Gtk.EventControllerMotion, x: float, y: float) -> None:
        if self.locked:
            return
        found = self._point(x, y)
        position = found[0] if found is not None else None
        if position != self.hover:
            self.hover = position
            self.refresh()

    def _on_leave(self, _controller: Gtk.EventControllerMotion) -> None:
        if self.hover is not None and not self.locked:
            self.hover = None
            self.refresh()

    def _on_key(
        self, _controller: Gtk.EventControllerKey, keyval: int, _code: int, state: Gdk.ModifierType
    ) -> bool:
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            return self.activate_default()
        return self.handle_key(keyval, state)

    # AnswerWidget

    def handle_key(self, keyval: int, state: Gdk.ModifierType) -> bool:
        if self.locked or state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            return False
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        entry = self.entry
        if keyval in _UP_KEYS or keyval in _DOWN_KEYS:
            step = 7 if shift else 1
            entry.move(step if keyval in _UP_KEYS else -step)
        elif keyval in (Gdk.KEY_Left, Gdk.KEY_KP_Left, Gdk.KEY_Right, Gdk.KEY_KP_Right):
            if entry.slots == 1:
                return False
            right = keyval in (Gdk.KEY_Right, Gdk.KEY_KP_Right)
            entry.select(entry.current + (1 if right else -1))
        elif keyval in _SHARP_KEYS:
            entry.toggle_accidental(Accidental.SHARP)
        elif keyval in _FLAT_KEYS:
            entry.toggle_accidental(Accidental.FLAT)
        elif keyval in _NATURAL_KEYS:
            entry.toggle_accidental(Accidental.NATURAL)
        elif keyval in _CLEAR_KEYS:
            entry.clear()
        else:
            letter = keyval_letter(keyval)
            if letter is None or letter not in 'abcdefg':
                return False
            entry.jump(Letter[letter.upper()], Accidental.SHARP if shift else None)
        self.hover = None
        self.refresh()
        return True

    def activate_default(self) -> bool:
        value = self.entry.value()
        if self.locked or value is None:
            return False
        self.submit(value)
        return True

    def reveal(self, expected: object, given: object, correct: bool) -> None:
        super().reveal(expected, given, correct)
        self.hover = None
        for button in (*self.accidental_buttons.values(), self.clear_button, self.check_button):
            button.set_sensitive(False)
        if not _is_value(expected):
            return
        marks = self.entry.marks(expected)
        if correct:
            text = _('Correct: {notes}').format(notes=_names([p for m in marks for p in m.given]))
        else:
            given_notes = [p for m in marks for p in m.given]
            right = _names([p for m in marks for p in m.expected])
            if given_notes:
                # Translators: accessible description of a checked staff answer, e.g.
                # "Your note: F5, wrong. The answer: E5."
                text = _('Your note: {given}, wrong. The answer: {expected}.').format(
                    given=_names(given_notes), expected=right
                )
            else:
                text = _('The answer: {expected}.').format(expected=right)
        self.view.figure = self.entry.reveal_figure(
            expected,
            # Marks, not words: they fit under notes at any width; the description says it.
            given_label='✗',
            expected_label='✓',
            description=f'{_staff_name(self.entry.clef)}. {text}',
        )
        self.canvas.update_property(
            [Gtk.AccessibleProperty.DESCRIPTION, Gtk.AccessibleProperty.VALUE_TEXT], [text, text]
        )

    def set_compact(self, compact: bool) -> None:
        super().set_compact(compact)
        self.hint.set_visible(not compact)

    def value(self) -> Value | None:
        return self.entry.value()


def _is_value(value: object) -> bool:
    return isinstance(value, tuple) and all(
        isinstance(chord, tuple) and all(isinstance(p, Pitch) for p in chord) for chord in value
    )
