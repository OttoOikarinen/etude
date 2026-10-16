# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest
from hypothesis import given
from hypothesis import strategies as st

from etude.core import Chord, ChordQuality, ChordSymbol, PitchName

Q = ChordQuality


@pytest.mark.parametrize(
    ('text', 'canonical', 'symbol', 'tones'),
    [
        ('C', 'C', 'C', 'C E G'),
        ('Cm', 'Cm', 'Cm', 'C Eb G'),
        ('Cmin', 'Cm', 'Cm', 'C Eb G'),
        ('C-', 'Cm', 'Cm', 'C Eb G'),
        ('Cmaj7', 'Cmaj7', 'Cmaj7', 'C E G B'),
        ('CM7', 'Cmaj7', 'Cmaj7', 'C E G B'),
        ('CΔ', 'Cmaj7', 'Cmaj7', 'C E G B'),
        ('CΔ7', 'Cmaj7', 'Cmaj7', 'C E G B'),
        ('C^7', 'Cmaj7', 'Cmaj7', 'C E G B'),
        ('Cma7', 'Cmaj7', 'Cmaj7', 'C E G B'),
        ('C7', 'C7', 'C7', 'C E G Bb'),
        ('Cø7', 'Cm7b5', 'Cø7', 'C Eb Gb Bb'),
        ('Cø', 'Cm7b5', 'Cø7', 'C Eb Gb Bb'),
        ('Cm7b5', 'Cm7b5', 'Cø7', 'C Eb Gb Bb'),
        ('C-7b5', 'Cm7b5', 'Cø7', 'C Eb Gb Bb'),
        ('Cmi7(♭5)', 'Cm7b5', 'Cø7', 'C Eb Gb Bb'),
        ('Cm7-5', 'Cm7b5', 'Cø7', 'C Eb Gb Bb'),
        ('Co7', 'Cdim7', 'C°7', 'C Eb Gb Bbb'),
        ('C°7', 'Cdim7', 'C°7', 'C Eb Gb Bbb'),
        ('Cdim', 'Cdim', 'C°', 'C Eb Gb'),
        ('Co', 'Cdim', 'C°', 'C Eb Gb'),
        ('C+', 'Caug', 'C+', 'C E G#'),
        ('C(#5)', 'Caug', 'C+', 'C E G#'),
        ('C7#9', 'C7#9', 'C7♯9', 'C E G Bb D#'),
        ('C7(#9)', 'C7#9', 'C7♯9', 'C E G Bb D#'),
        ('C7-9', 'C7b9', 'C7♭9', 'C E G Bb Db'),
        ('C7+5', 'C7#5', 'C7♯5', 'C E G# Bb'),
        ('C+7', 'C7#5', 'C7♯5', 'C E G# Bb'),
        ('Caug7', 'C7#5', 'C7♯5', 'C E G# Bb'),
        ('C13', 'C13', 'C13', 'C E G Bb D A'),
        ('Csus', 'Csus4', 'Csus4', 'C F G'),
        ('Csus2', 'Csus2', 'Csus2', 'C D G'),
        ('C6', 'C6', 'C6', 'C E G A'),
        ('C69', 'C69', 'C6/9', 'C E G A D'),
        ('C6/9', 'C69', 'C6/9', 'C E G A D'),
        ('CmM7', 'Cm(maj7)', 'Cm(maj7)', 'C Eb G B'),
        ('C-Δ7', 'Cm(maj7)', 'Cm(maj7)', 'C Eb G B'),
        ('Cmaj7#5', 'Cmaj7#5', 'Cmaj7♯5', 'C E G# B'),
        ('C+maj7', 'Cmaj7#5', 'Cmaj7♯5', 'C E G# B'),
        ('Cadd9', 'Cadd9', 'Cadd9', 'C E G D'),
        ('Cmadd9', 'Cm(add9)', 'Cm(add9)', 'C Eb G D'),
        ('C7sus', 'C7sus4', 'C7sus4', 'C F G Bb'),
        ('C7b5', 'C7b5', 'C7♭5', 'C E Gb Bb'),
        ('C11', 'C11', 'C11', 'C E G Bb D F'),
        ('C7alt', 'C7alt', 'C7alt', 'C E Bb Db D# F# Ab'),
        ('F#m7b5', 'F#m7b5', 'F♯ø7', 'F# A C E'),
        ('Bb13#11', 'Bb13#11', 'B♭13♯11', 'Bb D F Ab C E G'),
        ('Cb9', 'Cb9', 'C♭9', 'Cb Eb Gb Bbb Db'),
        ('E♭maj9', 'Ebmaj9', 'E♭maj9', 'Eb G Bb D F'),
        ('CM', 'C', 'C', 'C E G'),
    ],
)
def test_parse(text: str, canonical: str, symbol: str, tones: str) -> None:
    parsed = ChordSymbol.parse(text)
    assert str(parsed) == canonical
    assert parsed.symbol == symbol
    assert ' '.join(str(n) for n in parsed.to_chord().names()) == tones
    assert ChordSymbol.parse(canonical) == parsed
    assert ChordSymbol.parse(symbol) == parsed


def test_slash_chords() -> None:
    first = ChordSymbol.parse('C/E')
    assert first.to_chord() == Chord(PitchName.parse('C'), Q.MAJOR, 1)
    assert str(first) == 'C/E'
    assert ChordSymbol.parse('Am7/G').to_chord().inversion == 3
    assert ChordSymbol.parse('C69/E').bass == PitchName.parse('E')
    assert ChordSymbol.parse('C/C').bass is None
    assert ChordSymbol.parse('F#/A#').symbol == 'F♯/A♯'
    pedal = ChordSymbol.parse('C/D')
    assert pedal.chord_without_bass == Chord(PitchName.parse('C'), Q.MAJOR)
    with pytest.raises(ValueError, match='not a chord tone'):
        pedal.to_chord()


@pytest.mark.parametrize('text', ['', 'H7', 'c', 'Cxyz', 'C7#9b13', 'Cmaj7/', 'C/H'])
def test_parse_rejects(text: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 - several messages are valid here
        ChordSymbol.parse(text)


def test_no_symbol_for_augmented_sixths() -> None:
    with pytest.raises(ValueError, match='no chord symbol'):
        ChordSymbol(PitchName.parse('Ab'), Q.GERMAN_SIXTH)


symbol_qualities = [q for q in ChordQuality if q.kind.value != 'augmented-sixth']


@given(st.integers(-6, 6), st.sampled_from(symbol_qualities), st.data())
def test_round_trip(fifths: int, quality: ChordQuality, data: st.DataObject) -> None:
    root = PitchName.from_line_of_fifths(fifths)
    inversion = data.draw(st.integers(0, quality.size - 1))
    try:
        chord = Chord(root, quality, inversion)
    except ValueError:
        return
    symbol = ChordSymbol.from_chord(chord)
    assert ChordSymbol.parse(str(symbol)) == symbol
    assert ChordSymbol.parse(symbol.symbol) == symbol
    assert symbol.to_chord() == chord
