# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import itertools

import pytest
from hypothesis import given
from hypothesis import strategies as st

from etude.core import Chord, ChordKind, ChordQuality, Interval, Pitch, PitchName

Q = ChordQuality


def chord(root: str, quality: ChordQuality, inversion: int = 0) -> Chord:
    return Chord(PitchName.parse(root), quality, inversion)


def text(items: tuple[object, ...]) -> str:
    return ' '.join(str(i) for i in items)


@pytest.mark.parametrize(
    ('root', 'quality', 'expected'),
    [
        ('C', Q.MAJOR, 'C E G'),
        ('F#', Q.MINOR, 'F# A C#'),
        ('B', Q.DIMINISHED, 'B D F'),
        ('Ab', Q.AUGMENTED, 'Ab C E'),
        ('D', Q.SUS2, 'D E A'),
        ('D', Q.SUS4, 'D G A'),
        ('G', Q.DOMINANT_SEVENTH, 'G B D F'),
        ('Eb', Q.MAJOR_SEVENTH, 'Eb G Bb D'),
        ('E', Q.MINOR_SEVENTH, 'E G B D'),
        ('B', Q.HALF_DIMINISHED_SEVENTH, 'B D F A'),
        ('C#', Q.DIMINISHED_SEVENTH, 'C# E G Bb'),
        ('C', Q.DIMINISHED_SEVENTH, 'C Eb Gb Bbb'),
        ('A', Q.MINOR_MAJOR_SEVENTH, 'A C E G#'),
        ('C', Q.AUGMENTED_MAJOR_SEVENTH, 'C E G# B'),
        ('C', Q.AUGMENTED_SEVENTH, 'C E G# Bb'),
        ('C', Q.DOMINANT_THIRTEENTH, 'C E G Bb D A'),
        ('C', Q.MINOR_ELEVENTH, 'C Eb G Bb D F'),
        ('G', Q.ALTERED, 'G B F Ab A# C# Eb'),
        ('Ab', Q.ITALIAN_SIXTH, 'Ab C F#'),
        ('Ab', Q.FRENCH_SIXTH, 'Ab C D F#'),
        ('Ab', Q.GERMAN_SIXTH, 'Ab C Eb F#'),
    ],
)
def test_spelling(root: str, quality: ChordQuality, expected: str) -> None:
    assert text(chord(root, quality).names()) == expected


def test_qualities_have_distinct_structures() -> None:
    structures = [q.intervals for q in ChordQuality]
    assert len(set(structures)) == len(structures)
    for quality in ChordQuality:
        numbers = [i.number for i in quality.intervals]
        assert numbers == sorted(numbers), quality


def test_kinds_and_sizes() -> None:
    assert Q.MAJOR.kind is ChordKind.TRIAD
    assert Q.DOMINANT_SEVENTH.kind is ChordKind.SEVENTH
    assert Q.SIX_NINE.kind is ChordKind.ADDED
    assert Q.ALTERED.kind is ChordKind.EXTENDED
    assert Q.GERMAN_SIXTH.kind is ChordKind.AUGMENTED_SIXTH
    assert Q.DOMINANT_THIRTEENTH.size == 6
    assert Q.MAJOR.is_tertian
    assert not Q.SUS4.is_tertian
    assert not Q.DOMINANT_NINTH.is_tertian
    assert Q.MAJOR.pitch_classes == frozenset({0, 4, 7})


def test_bass_and_inversions() -> None:
    c7 = chord('C', Q.DOMINANT_SEVENTH, 3)
    assert c7.bass == PitchName.parse('Bb')
    assert text(c7.names_from_bass()) == 'Bb C E G'
    assert str(c7) == 'C:dominant-seventh/Bb'
    assert str(chord('C', Q.MAJOR)) == 'C:major'
    with pytest.raises(ValueError, match='no inversion 3'):
        chord('C', Q.MAJOR, 3)
    assert chord('C', Q.MAJOR).with_inversion(1).bass == PitchName.parse('E')
    assert PitchName.parse('E') in chord('C', Q.MAJOR)


@pytest.mark.parametrize(
    ('quality', 'figures'),
    [(Q.MAJOR, ['5/3', '6', '6/4']), (Q.DIMINISHED_SEVENTH, ['7', '6/5', '4/3', '4/2'])],
)
def test_figures(quality: ChordQuality, figures: list[str]) -> None:
    assert [chord('D', quality, i).figures for i in range(quality.size)] == figures


def test_no_figures_outside_common_practice() -> None:
    assert chord('C', Q.DOMINANT_NINTH).figures is None
    assert chord('C', Q.SUS4).figures is None
    assert chord('Ab', Q.GERMAN_SIXTH).figures is None


@pytest.mark.parametrize(
    ('root', 'quality', 'inversion', 'octave', 'expected'),
    [
        ('C', Q.MAJOR, 0, 4, 'C4 E4 G4'),
        ('C', Q.MAJOR, 1, 4, 'E4 G4 C5'),
        ('C', Q.MAJOR, 2, 3, 'G3 C4 E4'),
        ('G', Q.DOMINANT_SEVENTH, 3, 3, 'F3 G3 B3 D4'),
        ('C', Q.DOMINANT_NINTH, 0, 3, 'C3 E3 G3 Bb3 D4'),
        ('B', Q.DIMINISHED_SEVENTH, 0, 3, 'B3 D4 F4 Ab4'),
        ('C', Q.ALTERED, 0, 4, 'C4 E4 Bb4 Db5 D#5 F#5 Ab5'),
        ('B#', Q.MAJOR, 0, 3, 'B#3 D##4 F##4'),
    ],
)
def test_close_position(
    root: str, quality: ChordQuality, inversion: int, octave: int, expected: str
) -> None:
    assert text(chord(root, quality, inversion).pitches(octave)) == expected


def test_identify() -> None:
    def ident(spelling: str) -> list[str]:
        return [str(c) for c in Chord.identify([Pitch.parse(t) for t in spelling.split()])]

    assert ident('E4 G4 C5') == ['C:major/E']
    assert ident('C4 E4 G4 A4') == ['C:major-sixth', 'A:minor-seventh/C']
    assert ident('C4 E4 G#4') == ['C:augmented']
    assert ident('C4 E4 Ab4') == ['Ab:augmented/C']
    assert ident('C4 Eb4 Gb4 Bbb4') == ['C:diminished-seventh']
    assert ident('Ab3 C4 D4 F#4') == ['Ab:french-sixth', 'D:dominant-seventh-flat-five/Ab']
    assert ident('C4 G4 C5 E5') == ['C:major']
    assert ident('C4 D4 E4') == []
    assert Chord.identify([]) == []
    by_name = Chord.identify([PitchName.parse(t) for t in ['G', 'C', 'E']])
    assert by_name == [chord('C', Q.MAJOR, 2)]


def test_transpose_and_enharmonic() -> None:
    c = chord('C', Q.MINOR, 1)
    assert c.transpose(Interval.parse('M3')) == chord('E', Q.MINOR, 1)
    assert c.transpose(Interval.parse('M2'), down=True) == chord('Bb', Q.MINOR, 1)
    assert chord('Ab', Q.GERMAN_SIXTH).is_enharmonic(chord('Ab', Q.DOMINANT_SEVENTH))
    assert not chord('C', Q.MAJOR).is_enharmonic(chord('C', Q.MAJOR, 1))


def test_unspellable() -> None:
    with pytest.raises(ValueError, match='alteration'):
        chord('B##', Q.AUGMENTED_SEVENTH)


chords = st.builds(
    lambda fifths, quality, data: Chord(
        PitchName.from_line_of_fifths(fifths), quality, data.draw(st.integers(0, quality.size - 1))
    ),
    st.integers(-7, 7),
    st.sampled_from(ChordQuality),
    st.data(),
)


@given(chords, st.integers(1, 5))
def test_identify_finds_the_chord(subject: Chord, octave: int) -> None:
    try:
        pitches = subject.pitches(octave)
    except ValueError:
        return
    assert subject in Chord.identify(pitches)
    assert Chord.identify(pitches)[0].inversion == 0 or subject.inversion != 0


@given(chords, st.integers(1, 5))
def test_close_position_is_ascending_and_compact(subject: Chord, octave: int) -> None:
    pitches = subject.pitches(octave)
    assert pitches[0].name == subject.bass
    assert all(a.midi < b.midi for a, b in itertools.pairwise(pitches))
    assert {p.name for p in pitches} == set(subject.names())
