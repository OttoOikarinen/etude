# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Algebraic laws of the pitch and interval model."""

from hypothesis import assume, given
from hypothesis import strategies as st

from etude.core import Interval, Letter, Pitch, PitchName, Quality

pitches = st.builds(
    Pitch,
    letter=st.sampled_from(Letter),
    alter=st.integers(-2, 2),
    octave=st.integers(1, 7),
)
simple_intervals = st.sampled_from(
    [
        Interval.parse(text)
        for text in (
            *('P1', 'A1', 'm2', 'M2', 'A2', 'd3', 'm3', 'M3', 'A3', 'd4', 'P4', 'A4'),
            *('d5', 'P5', 'A5', 'd6', 'm6', 'M6', 'A6', 'd7', 'm7', 'M7', 'd8', 'P8'),
        )
    ]
)
intervals = st.one_of(
    simple_intervals,
    st.builds(
        Interval, st.sampled_from([Quality.MINOR, Quality.MAJOR]), st.sampled_from([9, 10, 13])
    ),
    st.builds(Interval, st.just(Quality.PERFECT), st.sampled_from([11, 12, 15])),
)


@given(pitches)
def test_parse_round_trip(pitch: Pitch) -> None:
    assert Pitch.parse(str(pitch)) == pitch


@given(pitches, intervals)
def test_transpose_round_trip(pitch: Pitch, interval: Interval) -> None:
    assert pitch.transpose(interval).transpose(interval, down=True) == pitch


@given(pitches, intervals)
def test_transpose_then_measure(pitch: Pitch, interval: Interval) -> None:
    higher = pitch.transpose(interval)
    assume(abs(higher.alter) <= 2)
    assert Interval.between(pitch, higher) == interval


@given(pitches, intervals)
def test_semitones_match_midi(pitch: Pitch, interval: Interval) -> None:
    assert pitch.transpose(interval).midi - pitch.midi == interval.semitones


@given(simple_intervals)
def test_inversion_is_an_involution(interval: Interval) -> None:
    assert interval.inverted().inverted() == interval


@given(simple_intervals)
def test_inversion_complements_the_octave(interval: Interval) -> None:
    inverted = interval.inverted()
    assert interval.number + inverted.number == 9
    assert interval.semitones + inverted.semitones == 12


@given(st.integers(-21, 21))
def test_line_of_fifths_round_trip(position: int) -> None:
    assert PitchName.from_line_of_fifths(position).line_of_fifths == position


@given(st.integers(-14, 14))
def test_fifths_are_seven_semitones_apart(position: int) -> None:
    here = PitchName.from_line_of_fifths(position)
    there = PitchName.from_line_of_fifths(position + 1)
    assert (there.pitch_class - here.pitch_class) % 12 == 7
