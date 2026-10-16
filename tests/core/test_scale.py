# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest
from hypothesis import given
from hypothesis import strategies as st

from etude.core import DegreeFunction, Key, KeySignature, Mode, PitchName, Scale, ScaleType


def names(text: str) -> tuple[PitchName, ...]:
    return tuple(PitchName.parse(t) for t in text.split())


def spelled(scale: Scale, *, descending: bool = False) -> str:
    return ' '.join(str(name) for name in scale.names(descending=descending))


@pytest.mark.parametrize(
    ('tonic', 'scale_type', 'expected'),
    [
        ('C', ScaleType.MAJOR, 'C D E F G A B'),
        ('F#', ScaleType.MAJOR, 'F# G# A# B C# D# E#'),
        ('Gb', ScaleType.MAJOR, 'Gb Ab Bb Cb Db Eb F'),
        ('A', ScaleType.NATURAL_MINOR, 'A B C D E F G'),
        ('G#', ScaleType.HARMONIC_MINOR, 'G# A# B C# D# E F##'),
        ('C', ScaleType.MELODIC_MINOR, 'C D Eb F G A B'),
        ('D', ScaleType.DORIAN, 'D E F G A B C'),
        ('E', ScaleType.PHRYGIAN, 'E F G A B C D'),
        ('F', ScaleType.LYDIAN, 'F G A B C D E'),
        ('G', ScaleType.MIXOLYDIAN, 'G A B C D E F'),
        ('A', ScaleType.AEOLIAN, 'A B C D E F G'),
        ('B', ScaleType.LOCRIAN, 'B C D E F G A'),
        ('Eb', ScaleType.IONIAN, 'Eb F G Ab Bb C D'),
        ('C', ScaleType.MAJOR_PENTATONIC, 'C D E G A'),
        ('A', ScaleType.MINOR_PENTATONIC, 'A C D E G'),
        ('C', ScaleType.BLUES, 'C Eb F Gb G Bb'),
        ('C', ScaleType.WHOLE_TONE, 'C D E F# G# A#'),
        ('C', ScaleType.CHROMATIC, 'C C# D D# E F F# G G# A A# B'),
        ('C', ScaleType.OCTATONIC_HALF_WHOLE, 'C Db Eb E F# G A Bb'),
        ('C', ScaleType.OCTATONIC_WHOLE_HALF, 'C D Eb F Gb Ab A B'),
    ],
)
def test_spelling(tonic: str, scale_type: ScaleType, expected: str) -> None:
    assert spelled(Scale(PitchName.parse(tonic), scale_type)) == expected


def test_descending_forms() -> None:
    melodic = Scale(PitchName.parse('A'), ScaleType.MELODIC_MINOR)
    assert spelled(melodic) == 'A B C D E F# G#'
    assert spelled(melodic, descending=True) == 'A B C D E F G'
    chromatic = Scale(PitchName.parse('C'), ScaleType.CHROMATIC)
    assert spelled(chromatic, descending=True) == 'C Db D Eb E F Gb G Ab A Bb B'
    major = Scale(PitchName.parse('C'), ScaleType.MAJOR)
    assert major.names(descending=True) == major.names()


def test_pitches() -> None:
    melodic = Scale(PitchName.parse('A'), ScaleType.MELODIC_MINOR)
    assert [str(p) for p in melodic.pitches(3)] == [
        'A3',
        'B3',
        'C4',
        'D4',
        'E4',
        'F#4',
        'G#4',
        'A4',
    ]
    assert [str(p) for p in melodic.pitches(3, descending=True)] == (
        ['A4', 'G4', 'F4', 'E4', 'D4', 'C4', 'B3', 'A3']
    )


def test_degrees() -> None:
    scale = Scale(PitchName.parse('E'), ScaleType.MAJOR)
    assert scale.degree(1) == PitchName.parse('E')
    assert scale.degree(7) == PitchName.parse('D#')
    assert scale.degree(9) == PitchName.parse('F#')
    assert scale.degree_of(PitchName.parse('G#')) == 3
    assert scale.degree_of(PitchName.parse('G')) is None
    assert PitchName.parse('A') in scale
    assert PitchName.parse('Ab') not in scale
    melodic = Scale(PitchName.parse('C'), ScaleType.MELODIC_MINOR)
    assert melodic.degree(6, descending=True) == PitchName.parse('Ab')
    assert melodic.degree_of(PitchName.parse('Bb'), descending=True) == 7
    assert PitchName.parse('Bb') in melodic
    with pytest.raises(ValueError, match='start at 1'):
        scale.degree(0)


def test_scale_type_properties() -> None:
    assert ScaleType.DORIAN.is_mode
    assert not ScaleType.MAJOR.is_mode
    assert ScaleType.MAJOR.is_diatonic
    assert not ScaleType.HARMONIC_MINOR.is_diatonic
    assert ScaleType.CHROMATIC.size == 12
    assert ScaleType.BLUES.size == 6
    assert str(Scale(PitchName.parse('D'), ScaleType.DORIAN)) == 'D dorian'


def test_unspellable_scale() -> None:
    with pytest.raises(ValueError, match='alteration'):
        Scale(PitchName.parse('B###'), ScaleType.LYDIAN)


@given(st.sampled_from(ScaleType), st.integers(-7, 7))
def test_semitone_pattern_is_independent_of_tonic(scale_type: ScaleType, fifths: int) -> None:
    tonic = PitchName.from_line_of_fifths(fifths)
    scale = Scale(tonic, scale_type)
    pattern = [(n.pitch_class - tonic.pitch_class) % 12 for n in scale.names()]
    assert pattern == [i.semitones % 12 for i in scale_type.intervals]
    assert len({n.pitch_class for n in scale.names()}) == scale_type.size
    if scale_type.size == 7:
        assert len({n.letter for n in scale.names()}) == 7


@given(st.sampled_from(ScaleType), st.integers(-5, 5))
def test_transpose(scale_type: ScaleType, fifths: int) -> None:
    from etude.core import Interval

    scale = Scale(PitchName.from_line_of_fifths(fifths), scale_type)
    fifth = Interval.parse('P5')
    assert scale.transpose(fifth).transpose(fifth, down=True) == scale


# Keys ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('text', 'tonic', 'mode'),
    [
        ('E major', 'E', Mode.MAJOR),
        ('c# minor', 'C#', Mode.MINOR),
        ('Bbm', 'Bb', Mode.MINOR),
        ('F', 'F', Mode.MAJOR),
        ('f', 'F', Mode.MINOR),
        ('AM', 'A', Mode.MAJOR),
        ('Gmaj', 'G', Mode.MAJOR),
        ('d min', 'D', Mode.MINOR),
    ],
)
def test_key_parse(text: str, tonic: str, mode: Mode) -> None:
    assert Key.parse(text) == Key(PitchName.parse(tonic), mode)


def test_key_parse_rejects() -> None:
    with pytest.raises(ValueError, match='not a key'):
        Key.parse('H major')


def test_key_relations() -> None:
    e_major = Key.parse('E')
    assert e_major.signature == KeySignature(4)
    assert e_major.relative == Key.parse('c#')
    assert e_major.parallel == Key.parse('e')
    assert Key.parse('c#').relative == e_major
    assert Key.parse('c').signature == KeySignature(-3)
    assert str(Key.parse('c#')) == 'c# minor'
    assert str(e_major) == 'E major'
    assert Key.parse('c').scale == Scale(PitchName.parse('C'), ScaleType.NATURAL_MINOR)
    assert Key.parse('c').leading_tone == PitchName.parse('B')
    assert Key.parse('C').raised(4) == PitchName.parse('F#')


def test_theoretical_key() -> None:
    key = Key.parse('G#')
    assert key.is_theoretical
    assert not Key.parse('C#').is_theoretical
    assert Key.parse('fb').is_theoretical
    with pytest.raises(ValueError, match='at most 7'):
        _ = key.signature


def chord_names(key: Key, size: int) -> list[str]:
    build = key.triad if size == 3 else key.seventh
    return [' '.join(str(n) for n in build(d).names()) for d in range(1, 8)]


def test_diatonic_triads() -> None:
    assert chord_names(Key.parse('D'), 3) == [
        'D F# A',
        'E G B',
        'F# A C#',
        'G B D',
        'A C# E',
        'B D F#',
        'C# E G',
    ]
    assert chord_names(Key.parse('c'), 3) == [
        'C Eb G',
        'D F Ab',
        'Eb G Bb',
        'F Ab C',
        'G B D',
        'Ab C Eb',
        'B D F',
    ]


def test_diatonic_sevenths() -> None:
    from etude.core import ChordQuality as Q

    major = [Key.parse('C').seventh(d).quality for d in range(1, 8)]
    assert major == [
        Q.MAJOR_SEVENTH,
        Q.MINOR_SEVENTH,
        Q.MINOR_SEVENTH,
        Q.MAJOR_SEVENTH,
        Q.DOMINANT_SEVENTH,
        Q.MINOR_SEVENTH,
        Q.HALF_DIMINISHED_SEVENTH,
    ]
    minor = [Key.parse('a').seventh(d).quality for d in range(1, 8)]
    assert minor == [
        Q.MINOR_SEVENTH,
        Q.HALF_DIMINISHED_SEVENTH,
        Q.MAJOR_SEVENTH,
        Q.MINOR_SEVENTH,
        Q.DOMINANT_SEVENTH,
        Q.MAJOR_SEVENTH,
        Q.DIMINISHED_SEVENTH,
    ]
    assert chord_names(Key.parse('a'), 4)[4] == 'E G# B D'
    with pytest.raises(ValueError, match='1–7'):
        Key.parse('C').triad(8)


def test_degree_functions() -> None:
    major, minor = Key.parse('C'), Key.parse('c')
    assert [major.degree_function(d) for d in range(1, 8)] == list(DegreeFunction)[:7]
    assert minor.degree_function(7) is DegreeFunction.SUBTONIC
    assert minor.function_of(PitchName.parse('Bb')) is DegreeFunction.SUBTONIC
    assert minor.function_of(PitchName.parse('B')) is DegreeFunction.LEADING_TONE
    assert minor.function_of(PitchName.parse('A')) is DegreeFunction.SUBMEDIANT
    assert minor.function_of(PitchName.parse('F#')) is None
    assert major.function_of(PitchName.parse('F')) is DegreeFunction.SUBDOMINANT
    assert major.function_of(PitchName.parse('Ab')) is None
    assert major.degree(5) == PitchName.parse('G')
    assert DegreeFunction.SUBTONIC.degree == 7
    with pytest.raises(ValueError, match='1–7'):
        major.degree_function(0)
