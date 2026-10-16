# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest
from hypothesis import given
from hypothesis import strategies as st

from etude.core import Letter, Pitch, PitchName

names = st.builds(PitchName, st.sampled_from(Letter), st.integers(-2, 2))
pitches = st.builds(Pitch, st.sampled_from(Letter), st.integers(-2, 2), st.integers(0, 8))


def n(text: str) -> PitchName:
    return PitchName.parse(text)


@pytest.mark.parametrize(
    ('name', 'letter', 'expected'),
    [
        ('C#', Letter.D, 'Db'),
        ('B#', Letter.C, 'C'),
        ('C', Letter.B, 'B#'),
        ('E', Letter.F, 'Fb'),
        ('G', Letter.A, 'Abb'),
        ('F#', Letter.E, 'E##'),
    ],
)
def test_respell_name(name: str, letter: Letter, expected: str) -> None:
    assert n(name).respell(letter) == n(expected)


def test_respell_too_far() -> None:
    with pytest.raises(ValueError, match='alteration'):
        n('C').respell(Letter.G)


@pytest.mark.parametrize(
    ('pitch', 'letter', 'expected'),
    [
        ('C#4', Letter.D, 'Db4'),
        ('B#3', Letter.C, 'C4'),
        ('C4', Letter.B, 'B#3'),
        ('Cb4', Letter.B, 'B3'),
        ('B3', Letter.C, 'Cb4'),
    ],
)
def test_respell_pitch_keeps_octave_right(pitch: str, letter: Letter, expected: str) -> None:
    assert Pitch.parse(pitch).respell(letter) == Pitch.parse(expected)


@pytest.mark.parametrize(
    ('name', 'expected'),
    [
        ('B#', 'C'),
        ('Ebb', 'D'),
        ('Fb', 'E'),
        ('Db', 'Db'),
        ('C#', 'C#'),
        ('B##', 'C#'),
        ('G', 'G'),
        ('Fx', 'G'),
    ],
)
def test_simplest(name: str, expected: str) -> None:
    assert n(name).simplest() == n(expected)


def test_simplest_prefers_flats_on_request() -> None:
    assert n('B##').simplest(prefer_flats=True) == n('Db')
    assert Pitch.parse('B#3').simplest() == Pitch.parse('C4')


def test_enharmonics() -> None:
    assert n('C#').enharmonics() == (n('Db'), n('B##'))
    assert n('C').enharmonics() == (n('Dbb'), n('B#'))
    assert n('G#').enharmonics() == (n('Ab'),)
    assert [str(p) for p in Pitch.parse('C4').enharmonics()] == ['Dbb4', 'B#3']


@given(names, st.sampled_from(Letter))
def test_respell_is_enharmonic(name: PitchName, letter: Letter) -> None:
    try:
        other = name.respell(letter)
    except ValueError:
        return
    assert other.letter == letter
    assert other.is_enharmonic(name)


@given(pitches, st.sampled_from(Letter))
def test_pitch_respell_keeps_midi(pitch: Pitch, letter: Letter) -> None:
    try:
        other = pitch.respell(letter)
    except ValueError:
        return
    assert other.midi == pitch.midi
    assert other.letter == letter


@given(names)
def test_enharmonics_are_enharmonic(name: PitchName) -> None:
    assert all(other.is_enharmonic(name) and other != name for other in name.enharmonics())
    assert abs(name.simplest().alter) <= 1
