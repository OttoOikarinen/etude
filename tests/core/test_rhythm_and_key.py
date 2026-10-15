# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

from fractions import Fraction

import pytest

from etude.core import Duration, KeySignature, Letter, Meter, NoteValue, PitchName, Tuplet


@pytest.mark.parametrize(
    ('duration', 'length'),
    [
        (Duration(NoteValue.QUARTER), Fraction(1, 4)),
        (Duration(NoteValue.QUARTER, dots=1), Fraction(3, 8)),
        (Duration(NoteValue.HALF, dots=2), Fraction(7, 8)),
        (Duration(NoteValue.EIGHTH, tuplet=Tuplet(3, 2)), Fraction(1, 12)),
        (Duration(NoteValue.SIXTEENTH, tuplet=Tuplet(5, 4)), Fraction(1, 20)),
        (Duration(NoteValue.BREVE), Fraction(2)),
    ],
)
def test_duration_length(duration: Duration, length: Fraction) -> None:
    assert duration.length == length
    assert duration.quarter_length == length * 4


def test_duration_validation() -> None:
    with pytest.raises(ValueError, match='dots'):
        Duration(NoteValue.QUARTER, dots=4)
    with pytest.raises(ValueError, match='tuplet'):
        Tuplet(0, 2)


@pytest.mark.parametrize(
    ('text', 'compound', 'groups', 'pulse', 'bar'),
    [
        ('4/4', False, (1, 1, 1, 1), Fraction(1, 4), Fraction(1)),
        ('3/4', False, (1, 1, 1), Fraction(1, 4), Fraction(3, 4)),
        ('2/2', False, (1, 1), Fraction(1, 2), Fraction(1)),
        ('6/8', True, (3, 3), Fraction(3, 8), Fraction(3, 4)),
        ('12/8', True, (3, 3, 3, 3), Fraction(3, 8), Fraction(3, 2)),
        ('3/8', False, (1, 1, 1), Fraction(1, 8), Fraction(3, 8)),
        ('5/8', False, (2, 3), Fraction(1, 8), Fraction(5, 8)),
        ('7/8', False, (2, 2, 3), Fraction(1, 8), Fraction(7, 8)),
    ],
)
def test_meter(
    text: str, compound: bool, groups: tuple[int, ...], pulse: Fraction, bar: Fraction
) -> None:
    meter = Meter.parse(text)
    assert str(meter) == text
    assert meter.is_compound is compound
    assert meter.groups == groups
    assert meter.pulse == pulse
    assert meter.bar_length == bar


def test_meter_explicit_grouping() -> None:
    meter = Meter(7, 8, grouping=(3, 2, 2))
    assert meter.groups == (3, 2, 2)
    assert not meter.is_compound
    with pytest.raises(ValueError, match='add up'):
        Meter(7, 8, grouping=(3, 3))


def test_meter_validation() -> None:
    with pytest.raises(ValueError, match='beat unit'):
        Meter(3, 3)
    with pytest.raises(ValueError, match='at least one beat'):
        Meter(0, 4)


@pytest.mark.parametrize(
    ('fifths', 'accidentals', 'major', 'minor'),
    [
        (0, '', 'C', 'A'),
        (1, 'F#', 'G', 'E'),
        (4, 'F# C# G# D#', 'E', 'C#'),
        (7, 'F# C# G# D# A# E# B#', 'C#', 'A#'),
        (-1, 'Bb', 'F', 'D'),
        (-3, 'Bb Eb Ab', 'Eb', 'C'),
        (-6, 'Bb Eb Ab Db Gb Cb', 'Gb', 'Eb'),
        (-7, 'Bb Eb Ab Db Gb Cb Fb', 'Cb', 'Ab'),
    ],
)
def test_key_signature(fifths: int, accidentals: str, major: str, minor: str) -> None:
    signature = KeySignature(fifths)
    assert ' '.join(str(a) for a in signature.accidentals) == accidentals
    assert str(signature.major_tonic) == major
    assert str(signature.minor_tonic) == minor
    assert KeySignature.for_major(PitchName.parse(major)) == signature
    assert KeySignature.for_minor(PitchName.parse(minor)) == signature
    assert signature.count == abs(fifths)


def test_key_signature_alterations() -> None:
    d_major = KeySignature(2)
    assert d_major.alter_for(Letter.F) == 1
    assert d_major.alter_for(Letter.C) == 1
    assert d_major.alter_for(Letter.G) == 0
    assert KeySignature(-2).alter_for(Letter.E) == -1
    assert KeySignature(-2).alter_for(Letter.A) == 0


def test_theoretical_keys_are_rejected() -> None:
    with pytest.raises(ValueError, match='at most 7'):
        KeySignature.for_major(PitchName.parse('G#'))
