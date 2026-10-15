# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from etude.core import Interval, Letter, Pitch, PitchName


@pytest.mark.parametrize(
    ('text', 'letter', 'alter', 'octave', 'midi'),
    [
        ('C4', Letter.C, 0, 4, 60),
        ('A4', Letter.A, 0, 4, 69),
        ('f#5', Letter.F, 1, 5, 78),
        ('Bb3', Letter.B, -1, 3, 58),
        ('Fx4', Letter.F, 2, 4, 67),
        ('Ebb4', Letter.E, -2, 4, 62),
        ('B♯3', Letter.B, 1, 3, 60),
        ('C♭4', Letter.C, -1, 4, 59),
        ('C-1', Letter.C, 0, -1, 0),
        ('G9', Letter.G, 0, 9, 127),
    ],
)
def test_parse(text: str, letter: Letter, alter: int, octave: int, midi: int) -> None:
    pitch = Pitch.parse(text)
    assert (pitch.letter, pitch.alter, pitch.octave) == (letter, alter, octave)
    assert pitch.midi == midi


@pytest.mark.parametrize('text', ['', 'H4', 'C', '4', 'C#', 'Cbbbb4', 'C 4'])
def test_parse_rejects(text: str) -> None:
    with pytest.raises(ValueError, match='not a pitch'):
        Pitch.parse(text)


def test_alteration_range() -> None:
    with pytest.raises(ValueError, match='alteration'):
        Pitch(Letter.C, 4, 4)


def test_spelled_equality_and_enharmonics() -> None:
    c_sharp, d_flat = Pitch.parse('C#4'), Pitch.parse('Db4')
    assert c_sharp != d_flat
    assert c_sharp.is_enharmonic(d_flat)
    assert c_sharp.name.is_enharmonic(d_flat.name)


def test_ordering_is_by_sound_then_letter() -> None:
    pitches = [Pitch.parse(t) for t in ('D4', 'Db4', 'C#4', 'B3', 'Cb4')]
    assert [str(p) for p in sorted(pitches)] == ['B3', 'Cb4', 'C#4', 'Db4', 'D4']


def test_diatonic_index() -> None:
    assert Pitch.parse('C4').diatonic_index == 28
    assert Pitch.parse('B3').diatonic_index == 27
    assert Pitch.parse('Cb4').diatonic_index == 28


def test_frequency() -> None:
    assert Pitch.parse('A4').frequency() == pytest.approx(440.0)
    assert Pitch.parse('A5').frequency() == pytest.approx(880.0)
    assert Pitch.parse('C4').frequency() == pytest.approx(261.6256, rel=1e-6)


def test_display_forms() -> None:
    pitch = Pitch.parse('F#4')
    assert str(pitch) == 'F#4'
    assert pitch.symbol == 'F♯4'
    assert PitchName.parse('Bbb').symbol == 'B𝄫'


@pytest.mark.parametrize(
    ('start', 'interval', 'up', 'down'),
    [
        ('C4', 'M3', 'E4', 'Ab3'),
        ('G4', 'M6', 'E5', 'Bb3'),
        ('E4', 'P5', 'B4', 'A3'),
        ('F#4', 'A4', 'B#4', 'C4'),
        ('B3', 'd5', 'F4', 'E#3'),
        ('C4', 'P8', 'C5', 'C3'),
        ('D4', 'M10', 'F#5', 'Bb2'),
        ('C4', 'P1', 'C4', 'C4'),
    ],
)
def test_transpose(start: str, interval: str, up: str, down: str) -> None:
    pitch, iv = Pitch.parse(start), Interval.parse(interval)
    assert str(pitch.transpose(iv)) == up
    assert str(pitch.transpose(iv, down=True)) == down


@pytest.mark.parametrize(
    ('midi', 'sharps', 'flats'),
    [(60, 'C4', 'C4'), (61, 'C#4', 'Db4'), (70, 'A#4', 'Bb4'), (71, 'B4', 'B4'), (0, 'C-1', 'C-1')],
)
def test_from_midi(midi: int, sharps: str, flats: str) -> None:
    assert str(Pitch.from_midi(midi)) == sharps
    assert str(Pitch.from_midi(midi, prefer_flats=True)) == flats


@pytest.mark.parametrize(
    ('position', 'name'),
    [
        (0, 'C'),
        (1, 'G'),
        (-1, 'F'),
        (6, 'F#'),
        (7, 'C#'),
        (-2, 'Bb'),
        (-7, 'Cb'),
        (12, 'B#'),
        (13, 'F##'),
        (14, 'C##'),
    ],
)
def test_line_of_fifths(position: int, name: str) -> None:
    pitch_name = PitchName.from_line_of_fifths(position)
    assert str(pitch_name) == name
    assert pitch_name.line_of_fifths == position


def test_pitch_name_transpose() -> None:
    assert str(PitchName.parse('Eb').transpose(Interval.parse('M3'))) == 'G'
    assert PitchName.parse('A').at(3) == Pitch.parse('A3')
