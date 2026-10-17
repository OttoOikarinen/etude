# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Integration tests against the real FluidSynth library and SoundFont.

Skipped unless both are found: set ``ETUDE_FLUIDSYNTH_LIB`` and
``ETUDE_SOUNDFONT`` or install them where :mod:`etude.audio.service`
looks. Audio is rendered offline with ``fluid_synth_write_float``;
nothing is sent to the speakers.
"""

from __future__ import annotations

import os
import time
from array import array
from collections.abc import Iterator
from fractions import Fraction
from pathlib import Path

import pytest

from etude.audio import metronome, service
from etude.audio.fluid_backend import LEAD_MS, FluidSynthBackend
from etude.audio.fluidsynth import FluidSynthError, SoundFontError
from etude.audio.null import NullBackend
from etude.audio.spec import Instrument, PlaybackNote, PlaybackSpec
from etude.core import Meter

pytestmark = pytest.mark.audio

F = Fraction
RATE = 48_000
LIBRARY = os.environ.get(service.LIBRARY_ENV) or None
SOUNDFONT = service.soundfont_path()
TIMING_TOLERANCE_MS = 3.0


def _skip_reason() -> str | None:
    if not SOUNDFONT.is_file():
        return f'SoundFont not found: {SOUNDFONT}'
    try:
        FluidSynthBackend(SOUNDFONT, library=LIBRARY, audio_driver=None).close()
    except FluidSynthError as error:
        return str(error)
    return None


_REASON = _skip_reason()
if _REASON is not None:
    pytest.skip(_REASON, allow_module_level=True)


@pytest.fixture
def backend() -> Iterator[FluidSynthBackend]:
    backend = FluidSynthBackend(SOUNDFONT, library=LIBRARY, audio_driver=None)
    yield backend
    backend.close()


def render_seconds(backend: FluidSynthBackend, seconds: float) -> array[float]:
    """Render in 10 ms chunks (like an audio driver) and return the left+right peak signal."""
    chunk = RATE // 100
    out = array('f')
    for _ in range(round(seconds * 100)):
        left, right = backend.render(chunk)
        out.extend(max(abs(a), abs(b)) for a, b in zip(left, right, strict=True))
    return out


def onsets(signal: array[float], *, threshold: float = 0.01, quiet_ms: float = 30) -> list[int]:
    """Frames where the signal first exceeds ``threshold`` after ``quiet_ms`` below it."""
    quiet = round(quiet_ms * RATE / 1000)
    result: list[int] = []
    last_loud = -quiet
    for i, x in enumerate(signal):
        if x > threshold:
            if i - last_loud >= quiet:
                result.append(i)
            last_loud = i
    return result


def chord(instrument: Instrument, velocity: int = 90) -> PlaybackSpec:
    return PlaybackSpec(
        tuple(PlaybackNote(m, F(0), F(2), velocity) for m in (48, 60, 64, 67)),
        instrument=instrument,
    )


@pytest.mark.parametrize('instrument', list(Instrument), ids=lambda i: i.name.lower())
def test_chord_is_audible_and_does_not_clip(
    backend: FluidSynthBackend, instrument: Instrument
) -> None:
    backend.play(chord(instrument))
    peak = max(render_seconds(backend, 2.5))
    print(f'{instrument.name}: four-note chord at velocity 90 peaks at {peak:.3f}')
    assert 0.1 < peak < 0.6


def test_loudest_case_still_does_not_clip(backend: FluidSynthBackend) -> None:
    notes = tuple(PlaybackNote(m, F(0), F(2), 127) for m in (36, 48, 55, 60, 64, 67, 72))
    for instrument in Instrument:
        backend.play(PlaybackSpec(notes, instrument=instrument))
        assert max(render_seconds(backend, 2.5)) < 1.0


def test_sequencer_places_onsets_on_time(backend: FluidSynthBackend) -> None:
    # Wood-block clicks have sharp attacks; a triplet checks per-event rounding.
    starts = [F(0), F(1), F(2), F(7, 3), F(8, 3), F(4)]
    spec = PlaybackSpec(
        tuple(PlaybackNote(metronome.CLICK_KEY, s, F(1, 4), 100, percussion=True) for s in starts),
        tempo=100,
        count_in=2,
        meter=Meter(2, 4),
    )
    render_seconds(backend, 0.1)  # the sequencer clock is not at zero
    first_frame = backend.tick_to_frame(backend.tick)
    handle = backend.play(spec)
    signal = render_seconds(backend, 5.0)
    found = [first_frame + i for i in onsets(signal)]
    count_in = [spec.beats_to_ms(F(n)) for n in (-2, -1)]
    expected_ms = count_in + [spec.beats_to_ms(s) for s in starts]
    expected = [backend.tick_to_frame(handle.origin_tick) + ms * RATE / 1000 for ms in expected_ms]
    assert len(found) == len(expected), (found, expected)
    errors_ms = [(f - e) * 1000 / RATE for f, e in zip(found, expected, strict=True)]
    print('onset errors (ms):', ', '.join(f'{e:+.2f}' for e in errors_ms))
    assert all(abs(e) <= TIMING_TOLERANCE_MS for e in errors_ms), errors_ms


def test_callbacks_run_in_order(backend: FluidSynthBackend) -> None:
    events: list[object] = []
    spec = PlaybackSpec(
        (PlaybackNote(60, F(0), F(1)), PlaybackNote(64, F(1), F(1))), tempo=240, count_in=2
    )
    handle = backend.play(spec, on_beat=events.append, on_finished=lambda: events.append('done'))
    render_seconds(backend, 0.5)
    assert events[:2] == [-2, -1]
    render_seconds(backend, 1.5)
    assert events == [-2, -1, 0, 1, 'done']
    assert handle.finished


def test_tap_phase_counts_and_clicks_through_its_duration(backend: FluidSynthBackend) -> None:
    """The tap pad's playback: a count-in, then bars with only the metronome. Beat
    callbacks come when their clicks sound, and the end comes after the bars."""
    spec = PlaybackSpec((), tempo=120, count_in=4, click=True, meter=Meter(4, 4), duration=F(4))
    render_seconds(backend, 0.1)
    first_frame = backend.tick_to_frame(backend.tick)
    beats: list[tuple[int, int]] = []
    finished: list[int] = []
    handle = backend.play(
        spec,
        on_beat=lambda n: beats.append((n, backend.tick)),
        on_finished=lambda: finished.append(backend.tick),
    )
    signal = render_seconds(backend, 5.0)
    assert [n for n, _tick in beats] == list(range(-4, 4))
    for number, tick in beats:
        assert abs(tick - (handle.origin_tick + spec.beats_to_ms(number))) <= 1
    found = [first_frame + i for i in onsets(signal)]
    expected = [
        backend.tick_to_frame(handle.origin_tick) + spec.beats_to_ms(n) * RATE / 1000
        for n in range(-4, 4)
    ]
    assert len(found) == len(expected), (found, expected)
    errors_ms = [(f - e) * 1000 / RATE for f, e in zip(found, expected, strict=True)]
    print('tap-phase click errors (ms):', ', '.join(f'{e:+.2f}' for e in errors_ms))
    assert all(abs(e) <= TIMING_TOLERANCE_MS for e in errors_ms), errors_ms
    assert finished
    assert finished[0] - handle.origin_tick >= spec.beats_to_ms(4)


def test_started_at_is_beat_zero(backend: FluidSynthBackend) -> None:
    spec = PlaybackSpec((PlaybackNote(60, F(0), F(1)),), tempo=120, count_in=4)
    before = time.monotonic()
    handle = backend.play(spec)
    after = time.monotonic()
    lead = (LEAD_MS + 2000) / 1000
    assert before + lead - 0.002 <= handle.started_at <= after + lead + 0.002


def test_stop_cancels_pending_notes_and_callbacks(backend: FluidSynthBackend) -> None:
    events: list[object] = []
    spec = PlaybackSpec(tuple(PlaybackNote(60 + i, F(i), F(1)) for i in range(8)), tempo=120)
    handle = backend.play(spec, on_beat=events.append, on_finished=lambda: events.append('done'))
    render_seconds(backend, 0.6)
    handle.stop()
    handle.stop()  # idempotent
    beats_heard = list(events)
    render_seconds(backend, 1.0)  # release tail
    assert max(render_seconds(backend, 2.0)) < 0.005
    assert events == beats_heard
    assert 'done' not in events


def test_new_playback_replaces_the_old(backend: FluidSynthBackend) -> None:
    events: list[str] = []
    long = PlaybackSpec(tuple(PlaybackNote(60, F(i), F(1)) for i in range(8)))
    backend.play(long, on_finished=lambda: events.append('first'))
    render_seconds(backend, 0.3)
    backend.play(chord(Instrument.STRINGS), on_finished=lambda: events.append('second'))
    render_seconds(backend, 3.0)
    assert events == ['second']


def test_callbacks_may_start_the_next_playback(backend: FluidSynthBackend) -> None:
    events: list[str] = []
    second = PlaybackSpec((PlaybackNote(67, F(0), F(1, 2)),), tempo=240)

    def chain() -> None:
        events.append('first')
        backend.play(second, on_finished=lambda: events.append('second'))

    backend.play(PlaybackSpec((PlaybackNote(60, F(0), F(1, 2)),), tempo=240), on_finished=chain)
    render_seconds(backend, 2.0)
    assert events == ['first', 'second']


def test_backend_stop_and_close(backend: FluidSynthBackend) -> None:
    events: list[str] = []
    backend.play(chord(Instrument.ORGAN), on_finished=lambda: events.append('done'))
    render_seconds(backend, 0.2)
    backend.stop()
    render_seconds(backend, 3.0)
    assert events == []
    assert backend.available
    assert backend.output_latency_ms == 0
    backend.close()
    assert not backend.available
    backend.close()  # idempotent
    with pytest.raises(RuntimeError, match='closed'):
        backend.play(chord(Instrument.PIANO))


def test_missing_soundfont(tmp_path: Path) -> None:
    with pytest.raises(SoundFontError, match='not found'):
        FluidSynthBackend(tmp_path / 'none.sf2', library=LIBRARY, audio_driver=None)
    broken = tmp_path / 'broken.sf2'
    broken.write_bytes(b'RIFF' + bytes(64))
    with pytest.raises(SoundFontError, match='cannot load'):
        FluidSynthBackend(broken, library=LIBRARY, audio_driver=None)


def test_service_falls_back_when_the_soundfont_is_missing(tmp_path: Path) -> None:
    environ = {service.SOUNDFONT_ENV: str(tmp_path / 'none.sf2')}
    if LIBRARY:
        environ[service.LIBRARY_ENV] = LIBRARY
    assert isinstance(service.create_backend(environ), NullBackend)


def test_service_opens_the_sound_server() -> None:
    """Opens the PulseAudio driver; plays nothing."""
    backend = service.create_backend()
    try:
        if isinstance(backend, NullBackend):
            pytest.skip('no sound server reachable')
        assert backend.available
        # 256 frames × 3 periods at 48 kHz.
        assert backend.output_latency_ms == pytest.approx(16.0)
    finally:
        backend.close()
