# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from etude.core import Interval, Pitch, Quality


@pytest.mark.parametrize(
    ('low', 'high', 'expected', 'semitones'),
    [
        ('C4', 'C4', 'P1', 0),
        ('C4', 'C#4', 'A1', 1),
        ('C4', 'Db4', 'm2', 1),
        ('C4', 'E4', 'M3', 4),
        ('C4', 'Eb4', 'm3', 3),
        ('F4', 'B4', 'A4', 6),
        ('B3', 'F4', 'd5', 6),
        ('G4', 'E5', 'M6', 9),
        ('E4', 'C5', 'm6', 8),
        ('C#4', 'Bb4', 'd7', 9),
        ('C4', 'C5', 'P8', 12),
        ('C4', 'D5', 'M9', 14),
        ('C4', 'E5', 'M10', 16),
        ('C4', 'C6', 'P15', 24),
        ('Cb4', 'G#4', 'AA5', 9),
        ('C#4', 'Gb4', 'dd5', 5),
    ],
)
def test_between(low: str, high: str, expected: str, semitones: int) -> None:
    interval = Interval.between(Pitch.parse(low), Pitch.parse(high))
    assert str(interval) == expected
    assert interval.semitones == semitones


def test_between_rejects_lower_spelling() -> None:
    with pytest.raises(ValueError, match='spelled below'):
        Interval.between(Pitch.parse('D4'), Pitch.parse('C4'))


def test_between_rejects_unnameable_size() -> None:
    with pytest.raises(ValueError, match='no interval quality'):
        Interval.between(Pitch.parse('Cbb4'), Pitch.parse('G##4'))


@pytest.mark.parametrize('text', ['P3', 'M5', 'm4', 'P0', 'X3', 'M', '3'])
def test_invalid(text: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 - several messages are valid here
        Interval.parse(text)


@pytest.mark.parametrize(
    ('interval', 'inverted'),
    [
        ('P1', 'P8'),
        ('m2', 'M7'),
        ('M3', 'm6'),
        ('P4', 'P5'),
        ('A4', 'd5'),
        ('AA5', 'dd4'),
        ('P8', 'P1'),
        ('M10', 'm6'),
    ],
)
def test_inverted(interval: str, inverted: str) -> None:
    assert str(Interval.parse(interval).inverted()) == inverted


@pytest.mark.parametrize(
    ('interval', 'simple'), [('M3', 'M3'), ('P8', 'P8'), ('M9', 'M2'), ('P15', 'P8'), ('m17', 'm3')]
)
def test_simple(interval: str, simple: str) -> None:
    assert str(Interval.parse(interval).simple()) == simple


def test_properties() -> None:
    tenth = Interval(Quality.MAJOR, 10)
    assert tenth.is_compound
    assert tenth.simple_number == 3
    assert tenth.octaves == 1
    assert not tenth.is_perfect_class
    assert not Interval.parse('P8').is_compound
