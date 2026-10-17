# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tap a rhythm on Space, or on the pad with a mouse or a finger.

**Timing.** "Start" plays a count-in, then the bars of the rhythm with the
metronome clicking (``TapAnswer.click``) or silent. Beat lights follow the
playback's ``on_beat`` callbacks, so the task works without sound too.
Every tap is a ``time.monotonic()`` time:

* For key presses and pointer presses the GDK event's timestamp is mapped to
  the monotonic clock with :data:`etude.ui.timing.TAP_CLOCK`. The stamp is
  taken when the windowing system saw the input, so the time the event
  waited for the main loop (while beat lights were redrawn, say) does not
  count. Events without a stamp, such as an assistive technology activating
  the pad, use the time they arrive.
* The frame clock is not used: it would round taps to whole frames (17 ms).

A tap's value is its time minus ``PlaybackHandle.started_at`` (the moment
beat 0 is heard) minus the calibrated ``audio-latency-ms``, in
milliseconds. Taps during the count-in, more than half a beat before beat 0,
are ignored: many learners tap along with the count-in.

**Screen readers.** The count-in is not announced beat by beat: speech
lags by a few hundred milliseconds and would talk over the clicks the
learner needs to hear. The status line says what is happening ("Count-in",
"Tap now") and the result is announced as feedback.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from gettext import gettext as _
from gettext import ngettext

from gi.repository import Adw, Gdk, GLib, Graphene, Gsk, Gtk

from ...audio.backend import PlaybackHandle
from ...audio.latency import TapGrade, TapResult, grade_taps
from ...audio.metronome import pulses_per_bar
from ...audio.spec import PlaybackSpec
from ...exercises.base import TapAnswer
from ..common import accel_badge, set_shortcut
from ..timing import TAP_CLOCK, Player, latency_ms, silent_player
from .base import AnswerWidget

FLASH_MS = 110
DEADLINE_SLACK_MS = 1500
"""A take whose playback never reports its end (stopped by another playback)
ends this long after it should have."""

# libadwaita's standalone colours, light and dark.
_COLOURS = {
    'success': ('#1b8553', '#78e9ab'),
    'warning': ('#9c6e03', '#ffc252'),
    'error': ('#c01c28', '#ff938c'),
}


def _rgba(spec: str, alpha: float = 1.0) -> Gdk.RGBA:
    colour = Gdk.RGBA()
    colour.parse(spec)
    colour.alpha *= alpha
    return colour


def state_colour(state: str) -> Gdk.RGBA:
    dark = Adw.StyleManager.get_default().get_dark()
    return _rgba(_COLOURS[state][1 if dark else 0])


# Input -----------------------------------------------------------------------------


class TapKeys:
    """Space taps while ``widget`` is mapped, wherever the focus is in its window.

    The controller sits on the window in the capture phase, after the window's
    own shortcut controller (which leaves Space alone when the answer widget
    asks it to, see ``AnswerWidget.captures_space``). Holding Space taps once:
    key repeats are swallowed until it is released.
    """

    def __init__(
        self,
        widget: Gtk.Widget,
        on_tap: Callable[[float], None],
        enabled: Callable[[], bool] = lambda: True,
    ) -> None:
        self.widget = widget
        self.on_tap = on_tap
        self.enabled = enabled
        self._root: Gtk.Widget | None = None
        self._down = False
        self.controller = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        self.controller.connect('key-pressed', self._on_pressed)
        self.controller.connect('key-released', self._on_released)
        widget.connect('map', lambda *_a: self.attach())
        widget.connect('unmap', lambda *_a: self.detach())

    def attach(self) -> None:
        root = self.widget.get_root()
        if root is None or root is self._root:
            return
        self.detach()
        root.add_controller(self.controller)
        self._root = root

    def detach(self) -> None:
        if self._root is not None:
            self._root.remove_controller(self.controller)
            self._root = None
        self._down = False

    def _blocked(self) -> bool:
        root = self._root
        if root is None or not self.widget.get_mapped() or not self.enabled():
            return True
        dialog = getattr(root, 'get_visible_dialog', lambda: None)()
        if dialog is not None and not self.widget.is_ancestor(dialog):
            return True
        focus = root.get_focus() if isinstance(root, Gtk.Window) else None
        return isinstance(focus, Gtk.Text | Gtk.Editable)

    def _on_pressed(
        self, controller: Gtk.EventControllerKey, keyval: int, _code: int, state: Gdk.ModifierType
    ) -> bool:
        if keyval != Gdk.KEY_space:
            return False
        if state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            return False
        if self._blocked():
            return False
        if self._down:
            return True  # key repeat
        self._down = True
        event = controller.get_current_event()
        stamp = event.get_time() if event is not None else 0
        self.on_tap(TAP_CLOCK.to_monotonic(stamp, time.monotonic()))
        return True

    def _on_released(
        self, _controller: Gtk.EventControllerKey, keyval: int, _code: int, _state: object
    ) -> None:
        if keyval == Gdk.KEY_space:
            self._down = False

    def press(self, at: float | None = None) -> None:
        """Tap as if Space was pressed (tests)."""
        self.on_tap(time.monotonic() if at is None else at)


class TapButton(Gtk.Button):
    """The big pad: a press (not the release) taps, with the event's own timestamp."""

    __gtype_name__ = 'EtudeTapButton'

    def __init__(self, on_tap: Callable[[float], None]) -> None:
        super().__init__(hexpand=True)
        self.on_tap = on_tap
        self.add_css_class('tap-pad')
        box = Gtk.Box(spacing=10, halign=Gtk.Align.CENTER)
        # Translators: the big button the learner taps a rhythm on.
        label = Gtk.Label(label=_('Tap'))
        label.add_css_class('title-2')
        box.append(label)
        # Translators: the Space key, shown on the tap pad.
        box.append(accel_badge(_('Space')))
        self.set_child(box)
        self.update_property([Gtk.AccessibleProperty.LABEL], [_('Tap')])
        self.update_property(
            [Gtk.AccessibleProperty.DESCRIPTION],
            [_('Tap the rhythm here or with the Space key')],
        )
        set_shortcut(self, 'space')
        press = Gtk.GestureClick(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        press.connect('pressed', self._on_pressed)
        self.add_controller(press)
        # Keyboard and assistive-technology activation have no pointer press.
        self.connect('activate', lambda _b: self.on_tap(time.monotonic()))
        self._flash = 0

    def _on_pressed(self, gesture: Gtk.GestureClick, _n: int, _x: float, _y: float) -> None:
        event = gesture.get_current_event()
        stamp = event.get_time() if event is not None else 0
        self.on_tap(TAP_CLOCK.to_monotonic(stamp, time.monotonic()))

    def flash(self) -> None:
        """Visible confirmation of a tap."""
        self.add_css_class('tapped')
        if self._flash:
            GLib.source_remove(self._flash)
        self._flash = GLib.timeout_add(FLASH_MS, self._unflash)

    def _unflash(self) -> bool:
        self._flash = 0
        self.remove_css_class('tapped')
        return GLib.SOURCE_REMOVE


class BeatLights(Gtk.Box):
    """One numbered light per beat of a bar; the current beat is lit, the downbeat
    in the accent style."""

    __gtype_name__ = 'EtudeBeatLights'

    def __init__(self, count: int) -> None:
        super().__init__(spacing=10, halign=Gtk.Align.CENTER)
        self.add_css_class('beat-lights')
        self.update_property([Gtk.AccessibleProperty.LABEL], [_('Metronome')])
        self.lights: list[Gtk.Label] = []
        for number in range(1, count + 1):
            light = Gtk.Label(label=str(number), accessible_role=Gtk.AccessibleRole.PRESENTATION)
            light.add_css_class('beat-light')
            if number == 1:
                light.add_css_class('downbeat')
            self.lights.append(light)
            self.append(light)
        self.current: int | None = None

    def show_beat(self, index: int | None, *, count_in: bool = False) -> None:
        self.current = index
        for i, light in enumerate(self.lights):
            if i == index:
                light.add_css_class('lit')
            else:
                light.remove_css_class('lit')
        if count_in:
            self.add_css_class('count-in')
        else:
            self.remove_css_class('count-in')


# Results ----------------------------------------------------------------------------


def summary_text(result: TapResult) -> str:
    """E.g. "7 of 8 on time · average 23 ms late"."""
    total = len(result.matches)
    parts = [
        ngettext('{good} of {total} on time', '{good} of {total} on time', total).format(
            good=result.good, total=total
        )
    ]
    mean = result.mean_error_ms
    if mean is not None:
        ms = round(abs(mean))
        if ms < 5:
            parts.append(_('right on the beat on average'))
        elif mean > 0:
            parts.append(_('average {ms} ms late').format(ms=ms))
        else:
            parts.append(_('average {ms} ms early').format(ms=ms))
    if result.extra:
        parts.append(
            ngettext('{count} extra tap', '{count} extra taps', result.extra).format(
                count=result.extra
            )
        )
    return ' · '.join(parts)


def note_states(result: TapResult) -> list[tuple[str, str, str]]:
    """``(state, icon, text)`` for every note that was not right on time, and extra taps."""
    states = []
    for number, match in enumerate(result.matches, start=1):
        error = match.error_ms
        if match.grade is TapGrade.MISSED or error is None:
            # Translators: a rhythm note the learner did not tap, e.g. "Note 5 · missed".
            states.append(
                ('error', 'window-close-symbolic', _('Note {n} · missed').format(n=number))
            )
        elif match.grade is TapGrade.OK:
            ms = round(abs(error))
            if error > 0:
                text = _('Note {n} · {ms} ms late').format(n=number, ms=ms)
                icon = 'media-seek-forward-symbolic'
            else:
                text = _('Note {n} · {ms} ms early').format(n=number, ms=ms)
                icon = 'media-seek-backward-symbolic'
            states.append(('warning', icon, text))
    for _tap in result.extra_taps:
        states.append(('error', 'list-add-symbolic', _('Extra tap')))
    if not states:
        states.append(('success', 'object-select-symbolic', _('Every note on time')))
    return states


class TapTimeline(Gtk.Widget):
    """Expected onsets (rings on the line) against taps (dots above it), with
    lines that show how early or late each tap was."""

    __gtype_name__ = 'EtudeTapTimeline'

    HEIGHT = 64
    PAD = 14

    def __init__(self, result: TapResult, beat_ms: Sequence[float], bar_ms: Sequence[float]):
        super().__init__(accessible_role=Gtk.AccessibleRole.IMG, hexpand=True)
        self.result = result
        self.beat_ms = list(beat_ms)
        self.bar_ms = list(bar_ms)
        self.add_css_class('tap-timeline')
        times = [*self.beat_ms, *(m.onset_ms for m in result.matches), *result.extra_taps]
        times += [m.tap_ms for m in result.matches if m.tap_ms is not None]
        step = (self.beat_ms[1] - self.beat_ms[0]) if len(self.beat_ms) > 1 else 500.0
        self.start = min([*times, 0.0]) - step / 2
        self.end = max([*times, *self.bar_ms, 0.0]) + step / 4
        texts = [summary_text(result), *(text for _s, _i, text in note_states(result))]
        self.update_property([Gtk.AccessibleProperty.LABEL], ['. '.join(texts)])

    def do_measure(self, orientation: Gtk.Orientation, _for_size: int) -> tuple[int, int, int, int]:
        if orientation == Gtk.Orientation.HORIZONTAL:
            return 240, 600, -1, -1
        return self.HEIGHT, self.HEIGHT, -1, -1

    def _x(self, ms: float) -> float:
        width = max(1, self.get_width() - 2 * self.PAD)
        return self.PAD + (ms - self.start) / (self.end - self.start) * width

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        fg = self.get_color()
        dim = _rgba(fg.to_string(), 0.35)
        mid = self.HEIGHT * 0.62
        width = self.get_width()

        def rect(x: float, y: float, w: float, h: float, colour: Gdk.RGBA) -> None:
            snapshot.append_color(colour, Graphene.Rect().init(x, y, w, h))

        def dot(x: float, y: float, r: float, colour: Gdk.RGBA, ring: bool = False) -> None:
            bounds = Graphene.Rect().init(x - r, y - r, 2 * r, 2 * r)
            rounded = Gsk.RoundedRect()
            rounded.init_from_rect(bounds, r)
            if ring:
                snapshot.append_border(rounded, [2.0] * 4, [colour] * 4)
            else:
                snapshot.push_rounded_clip(rounded)
                snapshot.append_color(colour, bounds)
                snapshot.pop()

        rect(self.PAD / 2, mid - 0.5, width - self.PAD, 1, dim)
        for ms in self.beat_ms:
            rect(self._x(ms) - 0.5, mid - 5, 1, 10, dim)
        for ms in self.bar_ms:
            rect(self._x(ms) - 1, mid - 12, 2, 24, dim)
        top = mid - 22
        for match in self.result.matches:
            x = self._x(match.onset_ms)
            if match.tap_ms is None:
                dot(x, mid, 7, state_colour('error'), ring=True)
                continue
            colour = state_colour('success' if match.grade is TapGrade.GOOD else 'warning')
            tx = self._x(match.tap_ms)
            rect(min(x, tx), top - 1, abs(tx - x), 2, colour)
            rect(tx - 1, top, 2, mid - top - 6, colour)
            dot(tx, top, 5, colour)
            dot(x, mid, 6, fg, ring=True)
        for tap in self.result.extra_taps:
            tx = self._x(tap)
            colour = state_colour('error')
            rect(tx - 1, top, 2, mid - top - 6, colour)
            dot(tx, top, 5, colour)


class TapResultView(Gtk.Box):
    """The timeline, the summary line and a chip for every note that was off."""

    __gtype_name__ = 'EtudeTapResultView'

    def __init__(self, result: TapResult, beat_ms: Sequence[float], bar_ms: Sequence[float]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class('tap-result')
        self.timeline = TapTimeline(result, beat_ms, bar_ms)
        self.append(self.timeline)
        self.summary = Gtk.Label(label=summary_text(result), wrap=True)
        self.summary.add_css_class('heading')
        self.append(self.summary)
        self.chips = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            max_children_per_line=4,
            column_spacing=6,
            row_spacing=6,
            halign=Gtk.Align.CENTER,
        )
        for state, icon, text in note_states(result):
            chip = Gtk.Box(spacing=6)
            chip.add_css_class('tap-chip')
            chip.add_css_class(state)
            chip.append(Gtk.Image(icon_name=icon, accessible_role=Gtk.AccessibleRole.PRESENTATION))
            chip.append(Gtk.Label(label=text))
            self.chips.append(chip)
            chip.get_parent().set_focusable(False)
        self.append(self.chips)


# The answer widget ----------------------------------------------------------------------


class TapPadView(AnswerWidget):
    """Renders a :class:`TapAnswer`. Emits ``answered`` with ``tuple[float, ...]``: tap
    times in milliseconds relative to beat 0, latency-compensated."""

    __gtype_name__ = 'EtudeTapPadView'
    captures_space = True

    def __init__(self, spec: TapAnswer) -> None:
        super().__init__()
        self.spec = spec
        self.add_css_class('tap-area')
        self.state = 'idle'
        """``idle``, ``count-in`` or ``recording``."""
        self.taps: list[float] = []
        self.handle: PlaybackHandle | None = None
        self._take = 0
        self._latency = 0.0
        self._deadline = 0
        meter = spec.meter
        self.per_bar = pulses_per_bar(meter)
        self.bar_beats = meter.bar_length * 4
        self.beat_ms = 60_000.0 / spec.tempo * float(meter.pulse * 4)

        self.status = Gtk.Label(
            label=_('Press Start, listen to the count-in, then tap the rhythm.'),
            wrap=True,
            justify=Gtk.Justification.CENTER,
        )
        self.status.add_css_class('tap-status')
        self.append(self.status)
        self.lights = BeatLights(self.per_bar)
        self.append(self.lights)
        self.pad = TapButton(self.tap)
        self.append(self.pad)
        self.start_button = Gtk.Button(halign=Gtk.Align.CENTER)
        self.start_button.add_css_class('suggested-action')
        self.start_button.add_css_class('pill')
        box = Gtk.Box(spacing=8)
        self._start_label = Gtk.Label(label=_('Start'))
        box.append(self._start_label)
        box.append(accel_badge('↵'))
        self.start_button.set_child(box)
        self.start_button.update_property([Gtk.AccessibleProperty.LABEL], [_('Start')])
        set_shortcut(self.start_button, 'Return')
        self.start_button.connect('clicked', lambda _b: self.start())
        self.append(self.start_button)
        self.result_view: TapResultView | None = None
        self.keys = TapKeys(self, self.tap, enabled=lambda: not self.locked)
        self.connect('unmap', lambda *_a: self.cancel())

    # Takes

    def take_spec(self) -> PlaybackSpec:
        """A count-in, then the bars of the rhythm with the metronome only."""
        spec = self.spec
        return PlaybackSpec(
            (),
            spec.tempo,
            count_in=spec.count_in,
            click=spec.click,
            meter=spec.meter,
            duration=self.bar_beats * spec.bars,
        )

    def start(self) -> None:
        """Start (or restart) a take."""
        if self.locked:
            return
        self.cancel()
        self._take += 1
        take = self._take
        self.taps = []
        self._latency = latency_ms()
        spec = self.take_spec()
        player: Player = self.player or silent_player

        def on_beat(number: int) -> None:
            GLib.idle_add(self._on_beat, take, number)

        def on_finished() -> None:
            GLib.idle_add(self._on_finished, take)

        self.state = 'count-in'
        self.status.set_label(_('Count-in — get ready'))
        self._start_label.set_label(_('Restart'))
        self.start_button.update_property([Gtk.AccessibleProperty.LABEL], [_('Restart')])
        self.handle = player(spec, on_beat=on_beat, on_finished=on_finished)
        total_ms = spec.beats_to_ms(spec.length + spec.count_in * float(spec.meter.pulse * 4))
        self._deadline = GLib.timeout_add(
            round(total_ms) + DEADLINE_SLACK_MS, self._on_deadline, take
        )

    def cancel(self) -> None:
        """Stop a take without submitting it."""
        if self._deadline:
            GLib.source_remove(self._deadline)
            self._deadline = 0
        handle, self.handle = self.handle, None
        if handle is not None and self.state != 'idle':
            handle.stop()
        self._take += 1
        self.state = 'idle'
        self.lights.show_beat(None)

    def tap(self, at: float) -> None:
        """A tap at monotonic time ``at`` (seconds)."""
        if self.locked:
            return
        self.pad.flash()
        if self.state == 'idle' or self.handle is None:
            self.start()
            return
        relative = (at - self.handle.started_at) * 1000.0 - self._latency
        if relative < -self.beat_ms / 2:
            return  # tapping along with the count-in
        self.taps.append(relative)

    def _on_beat(self, take: int, number: int) -> bool:
        if take != self._take or self.state == 'idle':
            return GLib.SOURCE_REMOVE
        index = number % self.per_bar
        if number < 0:
            self.lights.show_beat(index, count_in=True)
            self.status.set_label(
                # Translators: shown during the count-in with the beat number, e.g.
                # "Count-in: 3".
                _('Count-in: {beat}').format(beat=index + 1)
            )
        else:
            if self.state != 'recording':
                self.state = 'recording'
            bar = number // self.per_bar + 1
            self.lights.show_beat(index)
            if self.spec.bars > 1:
                # Translators: shown while the learner taps, e.g. "Tap now — bar 1 of 2".
                text = _('Tap now — bar {bar} of {bars}').format(bar=bar, bars=self.spec.bars)
            else:
                text = _('Tap now')
            self.status.set_label(text)
        return GLib.SOURCE_REMOVE

    def _on_finished(self, take: int) -> bool:
        if take != self._take or self.state == 'idle':
            return GLib.SOURCE_REMOVE
        taps = tuple(self.taps)
        self.cancel()
        self._start_label.set_label(_('Start'))
        self.start_button.update_property([Gtk.AccessibleProperty.LABEL], [_('Start')])
        if not taps:
            self.status.set_label(_('No taps — press Start and tap with Space or on the pad.'))
            return GLib.SOURCE_REMOVE
        self.status.set_label(
            ngettext('Recorded {count} tap.', 'Recorded {count} taps.', len(taps)).format(
                count=len(taps)
            )
        )
        self.submit(taps)
        return GLib.SOURCE_REMOVE

    def _on_deadline(self, take: int) -> bool:
        self._deadline = 0
        self._on_finished(take)
        return GLib.SOURCE_REMOVE

    # AnswerWidget

    def activate_default(self) -> bool:
        if self.locked:
            return False
        self.start()
        return True

    def handle_key(self, keyval: int, state: Gdk.ModifierType) -> bool:
        # Replaying the example during a take would stop the take's metronome.
        return self.state != 'idle' and Gdk.keyval_to_lower(keyval) == Gdk.KEY_r

    def reveal(self, expected: object, given: object, correct: bool) -> None:
        super().reveal(expected, given, correct)
        self.cancel()
        onsets = [float(t) for t in expected] if isinstance(expected, tuple | list) else []
        taps = [float(t) for t in given] if isinstance(given, tuple | list) else []
        result = grade_taps(onsets, taps, tempo=self.spec.tempo)
        beats = self.per_bar * self.spec.bars
        beat_ms = [i * self.beat_ms for i in range(beats + 1)]
        bar_ms = [i * self.beat_ms * self.per_bar for i in range(1, self.spec.bars + 1)]
        self.pad.set_sensitive(False)
        self.start_button.set_visible(False)
        self.lights.set_visible(False)
        self.status.set_visible(False)
        self.result_view = TapResultView(result, beat_ms, bar_ms)
        self.append(self.result_view)
        self.pad.set_visible(False)
