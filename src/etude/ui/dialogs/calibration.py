# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Calibrate tap timing (Preferences → Rhythm).

Etude plays a count-in and then sixteen clicks; the learner taps along on
Space or on the pad. :func:`etude.audio.latency.estimate_offset` measures how
far the taps lag the clicks (sound output and keyboard delays the backend
does not know about, and the learner's own habit), and the result is stored
in ``audio-latency-ms``, which the tap pad subtracts from every tap.
Without sound the clicks are shown by the beat lights only, so the
measurement then covers seeing rather than hearing the beat, which is what
a learner without sound taps against too.
"""

from __future__ import annotations

import dataclasses
from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, Gtk

from ...audio.backend import PlaybackHandle
from ...audio.latency import LatencyEstimate, NotEnoughTapsError, estimate_offset
from ...audio.metronome import click_track
from ...audio.spec import PlaybackSpec
from ...core import Meter
from ..common import accel_badge, set_shortcut
from ..timing import Player, silent_player
from ..widgets.tap_pad import BeatLights, TapButton, TapKeys

METER = Meter(4, 4)
TEMPO = 96.0
BARS = 4
LIMIT_MS = 500
"""The range of the ``audio-latency-ms`` key."""


def calibration_spec() -> PlaybackSpec:
    """A bar of count-in, then ``BARS`` bars of clicks to tap along with."""
    return dataclasses.replace(click_track(METER, TEMPO, bars=BARS), count_in=4)


def describe_estimate(estimate: LatencyEstimate) -> str:
    ms = round(estimate.offset_ms)
    spread = round(estimate.spread_ms)
    if ms > 0:
        # Translators: the result of tap calibration, e.g. "Your taps come 42 ms after the
        # clicks (spread ±12 ms)."
        text = _('Your taps come {ms} ms after the clicks (spread ±{spread} ms).')
    elif ms < 0:
        text = _('Your taps come {ms} ms before the clicks (spread ±{spread} ms).')
    else:
        text = _('Your taps land right on the clicks (spread ±{spread} ms).')
    text = text.format(ms=abs(ms), spread=spread)
    if not estimate.is_reliable():
        text += ' ' + _('The taps were uneven: try again for a steadier result, or save anyway.')
    return text


def latency_text(ms: int) -> str:
    if ms == 0:
        return _('Not calibrated')
    # Translators: the stored tap timing correction, e.g. "Taps corrected by 42 ms".
    return _('Taps corrected by {ms} ms').format(ms=ms)


class CalibrationPage(Adw.NavigationPage):
    """Pushed onto the preferences dialog as a subpage."""

    __gtype_name__ = 'EtudeCalibrationPage'

    def __init__(self, settings: Gio.Settings | None, player: Player | None = None) -> None:
        super().__init__(title=_('Calibrate Tap Timing'), tag='calibration')
        self.settings = settings
        self.player: Player = player or silent_player
        self.spec = calibration_spec()
        self.clicks_ms = [self.spec.beats_to_ms(n.start) for n in self.spec.notes]
        self.handle: PlaybackHandle | None = None
        self.taps: list[float] = []
        self.estimate: LatencyEstimate | None = None
        self.running = False
        self._run = 0

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        box.add_css_class('calibration-body')
        intro = Gtk.Label(
            label=_(
                'Listen to four clicks, then tap along with the next sixteen, on Space or on '
                'the pad. Etude measures how late or early your taps arrive and corrects them '
                'in rhythm exercises.'
            ),
            wrap=True,
            justify=Gtk.Justification.CENTER,
        )
        box.append(intro)
        self.lights = BeatLights(4)
        box.append(self.lights)
        self.status = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.status.add_css_class('tap-status')
        box.append(self.status)
        self.pad = TapButton(self.tap)
        box.append(self.pad)
        buttons = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        self.start_button = Gtk.Button()
        self.start_button.add_css_class('pill')
        start_box = Gtk.Box(spacing=8)
        self._start_label = Gtk.Label(label=_('Start'))
        start_box.append(self._start_label)
        start_box.append(accel_badge('↵'))
        self.start_button.set_child(start_box)
        self.start_button.update_property([Gtk.AccessibleProperty.LABEL], [_('Start')])
        set_shortcut(self.start_button, 'Return')
        self.start_button.connect('clicked', lambda _b: self.start())
        buttons.append(self.start_button)
        self.save_button = Gtk.Button(label=_('Save'), sensitive=False)
        self.save_button.add_css_class('pill')
        self.save_button.connect('clicked', lambda _b: self.save())
        buttons.append(self.save_button)
        box.append(buttons)
        self.result = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.result.add_css_class('heading')
        box.append(self.result)
        clamp = Adw.Clamp(maximum_size=520, child=box)
        scrolled = Gtk.ScrolledWindow(
            child=clamp, hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True
        )
        toolbar.set_content(scrolled)
        self.set_child(toolbar)
        self.keys = TapKeys(self, self.tap, enabled=lambda: True)
        self.start_button.add_css_class('suggested-action')
        self.connect('hiding', lambda *_a: self.stop())
        self.connect('unmap', lambda *_a: self.stop())
        self.connect('shown', lambda *_a: self.start_button.grab_focus())
        self._show_current()

    def _show_current(self) -> None:
        value = self.settings.get_int('audio-latency-ms') if self.settings is not None else 0
        self.status.set_label(latency_text(value))

    # Running

    def start(self) -> None:
        self.stop()
        self._run += 1
        run = self._run
        self.taps = []
        self.estimate = None
        self.running = True
        self.save_button.set_sensitive(False)
        self.save_button.remove_css_class('suggested-action')
        self.start_button.add_css_class('suggested-action')
        self.result.set_label('')
        self.status.set_label(_('Listen…'))
        self._start_label.set_label(_('Restart'))
        self.start_button.update_property([Gtk.AccessibleProperty.LABEL], [_('Restart')])
        self.handle = self.player(
            self.spec,
            on_beat=lambda n: GLib.idle_add(self._on_beat, run, n),
            on_finished=lambda: GLib.idle_add(self._on_finished, run),
        )

    def stop(self) -> None:
        if self.running and self.handle is not None:
            self.handle.stop()
        self.running = False
        self._run += 1
        self.lights.show_beat(None)

    def tap(self, at: float) -> None:
        self.pad.flash()
        if not self.running or self.handle is None:
            self.start()
            return
        relative = (at - self.handle.started_at) * 1000.0
        if relative > -self.spec.beats_to_ms(0.5):
            self.taps.append(relative)

    def _on_beat(self, run: int, number: int) -> bool:
        if run != self._run:
            return GLib.SOURCE_REMOVE
        self.lights.show_beat(number % 4, count_in=number < 0)
        if number < 0:
            self.status.set_label(_('Count-in: {beat}').format(beat=number % 4 + 1))
        else:
            # Translators: progress of the calibration, e.g. "Tap along — click 3 of 16".
            self.status.set_label(
                _('Tap along — click {n} of {total}').format(
                    n=number + 1, total=len(self.clicks_ms)
                )
            )
        return GLib.SOURCE_REMOVE

    def _on_finished(self, run: int) -> bool:
        if run != self._run:
            return GLib.SOURCE_REMOVE
        self.running = False
        self.handle = None
        self.lights.show_beat(None)
        self._start_label.set_label(_('Try Again'))
        self.start_button.update_property([Gtk.AccessibleProperty.LABEL], [_('Try Again')])
        try:
            self.estimate = estimate = estimate_offset(self.clicks_ms, self.taps)
        except NotEnoughTapsError:
            self.status.set_label(_('Not enough taps matched the clicks.'))
            self.result.set_label(_('Tap once for every click, in time with it, and try again.'))
            self.announce(self.result.get_label(), Gtk.AccessibleAnnouncementPriority.MEDIUM)
            return GLib.SOURCE_REMOVE
        self.status.set_label(_('Done'))
        self.result.set_label(describe_estimate(estimate))
        self.save_button.set_sensitive(True)
        if estimate.is_reliable():
            self.start_button.remove_css_class('suggested-action')
            self.save_button.add_css_class('suggested-action')
        self.announce(self.result.get_label(), Gtk.AccessibleAnnouncementPriority.MEDIUM)
        return GLib.SOURCE_REMOVE

    def save(self) -> None:
        if self.estimate is None:
            return
        value = max(-LIMIT_MS, min(LIMIT_MS, round(self.estimate.offset_ms)))
        if self.settings is not None:
            self.settings.set_int('audio-latency-ms', value)
        self.save_button.set_sensitive(False)
        if value:
            # Translators: confirmation after saving, e.g. "Saved: taps are corrected by 42 ms.".
            text = _('Saved: taps are corrected by {ms} ms.').format(ms=value)
        else:
            text = _('Saved: taps need no correction.')
        self.result.set_label(text)
        self._show_current()
        self.announce(self.result.get_label(), Gtk.AccessibleAnnouncementPriority.MEDIUM)
