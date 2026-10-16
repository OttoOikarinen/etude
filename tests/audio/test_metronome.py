# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from etude.audio import metronome
from etude.audio.metronome import ACCENT_KEY, CLICK_KEY, Beat, beats, pulse_offsets
from etude.audio.null import NullBackend
from etude.audio.spec import PlaybackNote, PlaybackSpec
from etude.core import Meter

F = Fraction


def test_pulse_offsets() -> None:
    assert pulse_offsets(Meter(4, 4)) == (0, 1, 2, 3)
    assert pulse_offsets(Meter(6, 8)) == (0, F(3, 2))
    assert pulse_offsets(Meter(7, 8)) == (0, 1, 2)
    assert pulse_offsets(Meter(7, 8, (3, 2, 2))) == (0, F(3, 2), F(5, 2))
    assert pulse_offsets(Meter(2, 2)) == (0, 2)


def test_beats_without_meter_count_quarters() -> None:
    assert beats(None, 2, F(5, 2)) == (
        Beat(-2, F(-2), True),
        Beat(-1, F(-1), False),
        Beat(0, F(0), True),
        Beat(1, F(1), False),
        Beat(2, F(2), False),
    )
    assert beats(None, 0, F(0)) == ()


def test_beats_in_three_four_accent_downbeats() -> None:
    result = beats(Meter(3, 4), 3, F(6))
    assert [b.number for b in result] == [-3, -2, -1, 0, 1, 2, 3, 4, 5]
    assert [b.start for b in result] == list(range(-3, 6))
    assert [b.accent for b in result] == [True, False, False] * 3


def test_compound_meter_clicks_the_dotted_pulse() -> None:
    result = beats(Meter(6, 8), 2, F(3))
    assert [(b.number, b.start, b.accent) for b in result] == [
        (-2, F(-3), True),
        (-1, F(-3, 2), False),
        (0, F(0), True),
        (1, F(3, 2), False),
    ]


def test_irregular_meter_groups() -> None:
    result = beats(Meter(7, 8), 3, F(7, 2))
    assert [b.start for b in result] == [F(-7, 2), F(-5, 2), F(-3, 2), 0, 1, 2]
    assert [b.accent for b in result] == [True, False, False, True, False, False]


def test_partial_count_in_ends_on_the_barline() -> None:
    result = beats(Meter(4, 4), 2, F(0))
    assert [(b.start, b.accent) for b in result] == [(F(-2), False), (F(-1), False)]


def test_negative_count_in_is_rejected() -> None:
    with pytest.raises(ValueError, match='negative'):
        beats(None, -1, F(1))


@given(
    st.sampled_from([Meter(2, 4), Meter(3, 4), Meter(4, 4), Meter(6, 8), Meter(7, 8), Meter(9, 8)]),
    st.integers(0, 12),
    st.fractions(min_value=0, max_value=20),
)
def test_beats_properties(meter: Meter, count_in: int, length: Fraction) -> None:
    result = beats(meter, count_in, length)
    numbers = [b.number for b in result]
    assert numbers == list(range(-count_in, len(result) - count_in))
    starts = [b.start for b in result]
    assert starts == sorted(starts)
    assert all(b.start < 0 for b in result if b.number < 0)
    assert all(0 <= b.start < length for b in result if b.number >= 0)
    # Every beat in the bar falls on a pulse, and bar starts are accented.
    bar = metronome.bar_length(meter)
    for b in result:
        assert b.start % bar in pulse_offsets(meter)
        assert b.accent == (b.start % bar == 0)


def test_count_in_spec() -> None:
    spec = metronome.count_in(Meter(6, 8), 90, bars=2)
    assert spec.notes == ()
    assert spec.count_in == 4
    assert spec.meter == Meter(6, 8)
    assert spec.tempo == 90
    with pytest.raises(ValueError, match='bar'):
        metronome.count_in(Meter(4, 4), 90, bars=0)


def test_click_track_is_percussion_notes() -> None:
    spec = metronome.click_track(Meter(3, 4), 100, bars=2)
    assert [n.start for n in spec.notes] == list(range(6))
    assert [n.midi for n in spec.notes] == [ACCENT_KEY, CLICK_KEY, CLICK_KEY] * 2
    assert all(n.percussion for n in spec.notes)
    assert spec.notes[0].velocity > spec.notes[1].velocity
    assert spec.length == F(5) + metronome.CLICK_LENGTH
    with pytest.raises(ValueError, match='bar'):
        metronome.click_track(Meter(4, 4), 90, bars=0)


def test_click_note_at_explicit_start() -> None:
    note = metronome.click_note(Beat(-1, F(-1), False), start=F(2))
    assert note == PlaybackNote(CLICK_KEY, F(2), metronome.CLICK_LENGTH, 85, percussion=True)


def test_with_metronome() -> None:
    spec = PlaybackSpec((PlaybackNote(60, F(0), F(1)),))
    timed = metronome.with_metronome(spec, Meter(6, 8), count_in_bars=1, click=True)
    assert (timed.count_in, timed.click, timed.meter) == (2, True, Meter(6, 8))
    assert timed.notes == spec.notes
    with pytest.raises(ValueError, match='negative'):
        metronome.with_metronome(spec, Meter(4, 4), count_in_bars=-1)


def test_null_backend_counts_pulses_with_a_meter() -> None:
    backend = NullBackend()
    events: list[int] = []
    spec = PlaybackSpec((PlaybackNote(60, F(0), F(3)),), count_in=2, meter=Meter(6, 8))
    backend.play(spec, on_beat=events.append)
    backend.complete()
    assert events == [-2, -1, 0, 1]


def test_sequence_keeps_percussion_and_meter() -> None:
    clicks = metronome.click_track(Meter(2, 4), 80, bars=1)
    spec = PlaybackSpec.sequence(clicks, PlaybackSpec((PlaybackNote(60, F(0), F(1)),)))
    assert spec.meter == Meter(2, 4)
    assert [n.percussion for n in spec.notes] == [True, True, False]
