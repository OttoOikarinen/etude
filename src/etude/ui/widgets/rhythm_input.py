# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Build a rhythm from a palette of durations (rhythm dictation).

The rhythm is engraved as it is entered, on a one-line staff with bar
lines. A duration that does not fit in what is left of the current bar is
disabled (ties across bar lines are not needed at level 1), so every
answer is made of full bars.

Keyboard: the digits pick durations (longest first), 0 switches between
notes and rests (as in MuseScore; R replays the question in ear
exercises), Backspace removes the last entry and Enter checks a finished
rhythm.
"""

from __future__ import annotations

import math
from fractions import Fraction
from gettext import gettext as _
from gettext import ngettext

from gi.repository import Gdk, Graphene, Gtk

from ...core import Duration, NoteValue
from ...exercises.base import RhythmInputAnswer
from ...exercises.families.rhythm import (
    Rhythm,
    beat_matches,
    describe_rhythm,
    duration_name,
    rhythm_events,
    rhythm_length,
    sentence_case,
)
from ...notation.spec import Clef, Ink, StaffSpec
from ...notation.widget import register_font
from ..common import accel_badge, keyval_matches, set_shortcut
from ..figure import create_figure_widget
from .base import AnswerWidget

REST_KEY = '0'

# SMuFL code points (Bravura) of individual notes and rests, and the dot.
_NOTE_GLYPHS = {
    NoteValue.WHOLE: '',
    NoteValue.HALF: '',
    NoteValue.QUARTER: '',
    NoteValue.EIGHTH: '',
    NoteValue.SIXTEENTH: '',
}
_REST_GLYPHS = {
    NoteValue.WHOLE: '',
    NoteValue.HALF: '',
    NoteValue.QUARTER: '',
    NoteValue.EIGHTH: '',
    NoteValue.SIXTEENTH: '',
}
_DOT = ''


_FRACTIONS = {Fraction(1, 4): '¼', Fraction(1, 2): '½', Fraction(3, 4): '¾'}


def beats_text(beats: Fraction) -> str:
    """``3`` → ``'3'``, ``3/2`` → ``'1½'``, ``1/4`` → ``'¼'``."""
    whole, part = divmod(beats, 1)
    if part == 0:
        return str(int(whole))
    symbol = _FRACTIONS.get(part)
    if symbol is None:
        return f'{float(beats):g}'
    return f'{int(whole)}{symbol}' if whole else symbol


def glyph_markup(duration: Duration, is_rest: bool) -> str:
    glyphs = _REST_GLYPHS if is_rest else _NOTE_GLYPHS
    text = glyphs.get(duration.value, '?') + (' ' + _DOT) * duration.dots
    return f'<span font_family="Bravura" size="200%">{text}</span>'


class GlyphView(Gtk.Widget):
    """Draws Bravura text centred on its ink: a label would reserve Bravura's line
    box, several staff spaces taller than a note."""

    __gtype_name__ = 'EtudeGlyphView'
    SIZE = 40

    def __init__(self) -> None:
        super().__init__(accessible_role=Gtk.AccessibleRole.PRESENTATION)
        self.markup = ''

    def set_markup(self, markup: str) -> None:
        self.markup = markup
        self.queue_draw()

    def do_measure(
        self, _orientation: Gtk.Orientation, _for_size: int
    ) -> tuple[int, int, int, int]:
        return self.SIZE, self.SIZE, -1, -1

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        layout = self.create_pango_layout(None)
        layout.set_markup(self.markup, -1)
        ink, _logical = layout.get_pixel_extents()
        x = (self.get_width() - ink.width) / 2 - ink.x
        y = (self.get_height() - ink.height) / 2 - ink.y
        snapshot.save()
        snapshot.translate(Graphene.Point().init(x, y))
        snapshot.append_layout(layout, self.get_color())
        snapshot.restore()


class DurationButton(Gtk.Button):
    __gtype_name__ = 'EtudeDurationButton'

    def __init__(self, duration: Duration, accel: str | None) -> None:
        super().__init__()
        self.duration = duration
        self.accel = accel
        self.add_css_class('duration-button')
        box = Gtk.Box(spacing=8)
        if accel:
            box.append(accel_badge(accel))
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        self.glyph = GlyphView()
        column.append(self.glyph)
        self.caption = Gtk.Label(
            wrap=True,
            max_width_chars=9,
            justify=Gtk.Justification.CENTER,
            accessible_role=Gtk.AccessibleRole.PRESENTATION,
        )
        self.caption.add_css_class('caption')
        column.append(self.caption)
        box.append(column)
        self.set_child(box)
        set_shortcut(self, accel)
        self.show_kind(False)

    def show_kind(self, rest: bool) -> None:
        self.glyph.set_markup(glyph_markup(self.duration, rest))
        name = sentence_case(duration_name(self.duration, rest))
        self.caption.set_label(name)
        self.update_property([Gtk.AccessibleProperty.LABEL], [name])
        self.set_tooltip_text(name)


class RhythmInputView(AnswerWidget):
    """Renders a :class:`RhythmInputAnswer`. Emits ``answered`` with
    ``tuple[tuple[Duration, bool], ...]`` (``True`` marks a rest)."""

    __gtype_name__ = 'EtudeRhythmInputView'

    def __init__(self, spec: RhythmInputAnswer) -> None:
        super().__init__()
        register_font()
        self.spec = spec
        self.entries: list[tuple[Duration, bool]] = []
        self.rest_mode = False
        self.total = spec.meter.bar_length * spec.bars

        self.staff = create_figure_widget(self._figure())
        frame = Gtk.Box(halign=Gtk.Align.CENTER)
        frame.add_css_class('figure-card')
        frame.add_css_class('rhythm-entry')
        frame.append(self.staff)
        self.append(frame)
        self.status = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.status.add_css_class('dim-label')
        self.append(self.status)

        self.palette = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=True,
            column_spacing=8,
            row_spacing=8,
            max_children_per_line=len(spec.palette) or 1,
            min_children_per_line=min(3, len(spec.palette) or 1),
            halign=Gtk.Align.CENTER,
        )
        self.palette.add_css_class('duration-palette')
        self.palette.update_property([Gtk.AccessibleProperty.LABEL], [_('Durations')])
        self.buttons: list[DurationButton] = []
        for index, duration in enumerate(spec.palette):
            button = DurationButton(duration, str(index + 1) if index < 9 else None)
            button.connect('clicked', lambda b: self.add(b.duration))
            self.buttons.append(button)
            self.palette.append(button)
            button.get_parent().set_focusable(False)
        self.append(self.palette)

        self.tools = tools = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        self.rest_button = Gtk.ToggleButton()
        rest_box = Gtk.Box(spacing=8)
        rest_box.append(accel_badge(REST_KEY))
        # Translators: toggles the duration buttons between notes and rests.
        rest_box.append(Gtk.Label(label=_('Rest')))
        self.rest_button.set_child(rest_box)
        self.rest_button.update_property([Gtk.AccessibleProperty.LABEL], [_('Rest')])
        set_shortcut(self.rest_button, REST_KEY)
        self.rest_button.connect('toggled', self._on_rest_toggled)
        tools.append(self.rest_button)
        self.undo_button = Gtk.Button()
        undo_box = Gtk.Box(spacing=8)
        undo_box.append(accel_badge('⌫'))
        undo_box.append(Gtk.Label(label=_('Undo')))
        self.undo_button.set_child(undo_box)
        self.undo_button.update_property([Gtk.AccessibleProperty.LABEL], [_('Undo')])
        set_shortcut(self.undo_button, 'BackSpace')
        self.undo_button.connect('clicked', lambda _b: self.undo())
        tools.append(self.undo_button)
        self.check_button = Gtk.Button()
        self.check_button.add_css_class('suggested-action')
        check_box = Gtk.Box(spacing=8)
        check_box.append(Gtk.Label(label=_('Check')))
        check_box.append(accel_badge('↵'))
        self.check_button.set_child(check_box)
        self.check_button.update_property([Gtk.AccessibleProperty.LABEL], [_('Check')])
        set_shortcut(self.check_button, 'Return')
        self.check_button.connect('clicked', lambda _b: self.activate_default())
        tools.append(self.check_button)
        self.append(tools)
        self._update()

    # Editing

    @property
    def rhythm(self) -> Rhythm:
        return tuple(self.entries)

    @property
    def filled(self) -> Fraction:
        return rhythm_length(self.entries)

    @property
    def full(self) -> bool:
        return self.filled >= self.total

    def room(self) -> Fraction:
        """What is left of the current bar, in whole notes."""
        if self.full:
            return Fraction(0)
        bar = self.spec.meter.bar_length
        return bar - self.filled % bar

    def can_add(self, duration: Duration) -> bool:
        return not self.locked and duration.length <= self.room()

    def add(self, duration: Duration) -> bool:
        if not self.can_add(duration):
            self.error_bell()
            return False
        self.entries.append((duration, self.rest_mode))
        self._update()
        return True

    def undo(self) -> bool:
        if self.locked or not self.entries:
            return False
        self.entries.pop()
        self._update()
        return True

    def toggle_rest(self) -> None:
        self.rest_button.set_active(not self.rest_button.get_active())

    def error_bell(self) -> None:
        display = Gdk.Display.get_default()
        if display is not None:
            display.beep()

    def _on_rest_toggled(self, button: Gtk.ToggleButton) -> None:
        self.rest_mode = button.get_active()
        for duration_button in self.buttons:
            duration_button.show_kind(self.rest_mode)

    # Display

    def _figure(self, inks: list[Ink] | None = None) -> StaffSpec:
        rhythm = tuple(self.entries)
        meter = self.spec.meter
        if rhythm:
            description = describe_rhythm(rhythm, meter)
        else:
            # Translators: the empty staff of the rhythm entry, e.g. "Empty bar of 4/4.".
            description = ngettext(
                'Empty bar of {meter}.', '{count} empty bars of {meter}.', self.spec.bars
            ).format(meter=meter, count=self.spec.bars)
        return StaffSpec(
            clef=Clef.PERCUSSION,
            lines=1,
            meter=meter,
            events=rhythm_events(rhythm, meter, inks, final=True),
            description=description,
        )

    def _update(self) -> None:
        self.staff.set_property('figure', self._figure())
        for button in self.buttons:
            button.set_sensitive(self.can_add(button.duration))
        self.undo_button.set_sensitive(bool(self.entries) and not self.locked)
        self.check_button.set_sensitive(self.full and not self.locked)
        if self.full:
            self.status.set_label(_('All bars are full — check your answer.'))
            return
        bar = self.spec.meter.bar_length
        number = int(self.filled // bar) + 1
        beats = self.room() / self.spec.meter.pulse
        # Translators: progress of the rhythm entry, e.g. "Bar 1 of 2 · 3 beats left".
        self.status.set_label(
            ngettext(
                'Bar {bar} of {bars} · {left} beat left',
                'Bar {bar} of {bars} · {left} beats left',
                math.ceil(beats),
            ).format(bar=number, bars=self.spec.bars, left=beats_text(beats))
        )

    # AnswerWidget

    def handle_key(self, keyval: int, state: Gdk.ModifierType) -> bool:
        if state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            return False
        if keyval == Gdk.KEY_BackSpace:
            self.undo()
            return True
        if self.locked:
            return False
        if keyval_matches(keyval, REST_KEY):
            self.toggle_rest()
            return True
        for button in self.buttons:
            if keyval_matches(keyval, button.accel):
                self.add(button.duration)
                return True
        return False

    def activate_default(self) -> bool:
        if self.locked or not self.full:
            return False
        self.submit(tuple(self.entries))
        return True

    def reveal(self, expected: object, given: object, correct: bool) -> None:
        super().reveal(expected, given, correct)
        expected_rhythm = tuple(expected) if isinstance(expected, tuple) else ()
        matches = beat_matches(expected_rhythm, self.rhythm, self.spec.meter, self.spec.bars)
        inks = []
        position = Fraction(0)
        for duration, _rest in self.entries:
            beat = int(position / self.spec.meter.pulse)
            inks.append(Ink.SUCCESS if beat < len(matches) and matches[beat] else Ink.ERROR)
            position += duration.length
        self.staff.set_property('figure', self._figure(inks))
        # Only the marked rhythm stays: the controls have done their job.
        self.palette.set_visible(False)
        self.tools.set_visible(False)
        right = sum(matches)
        self.status.set_label(
            # Translators: shown under the learner's rhythm after checking it.
            ngettext(
                'Your rhythm: {right} of {total} beat right; wrong beats are marked in red.',
                'Your rhythm: {right} of {total} beats right; wrong beats are marked in red.',
                len(matches),
            ).format(right=right, total=len(matches))
        )
