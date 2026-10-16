# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest
from hypothesis import given
from hypothesis import strategies as st

from etude.core import (
    Chord,
    Figure,
    FigureAccidental,
    FiguredBass,
    Key,
    KeySignature,
    PitchName,
)
from etude.core.figured_bass import figures_for_inversion


def above(figures: str, bass: str, key: str) -> str:
    result = FiguredBass.parse(figures).realize(PitchName.parse(bass), Key.parse(key))
    return ' '.join(str(n) for n in result)


@pytest.mark.parametrize(
    ('figures', 'bass', 'key', 'expected'),
    [
        ('', 'C', 'C', 'E G'),
        ('5/3', 'C', 'C', 'E G'),
        ('6', 'E', 'C', 'G C'),
        ('6/4', 'G', 'C', 'C E'),
        ('64', 'G', 'C', 'C E'),
        ('7', 'G', 'C', 'B D F'),
        ('6/5', 'B', 'C', 'D F G'),
        ('65', 'B', 'C', 'D F G'),
        ('4/3', 'D', 'C', 'F G B'),
        ('4/2', 'F', 'C', 'G B D'),
        ('2', 'F', 'C', 'G B D'),
        ('#', 'G', 'c', 'B D'),
        ('7 #', 'G', 'c', 'B D F'),
        ('6/5', 'B', 'c', 'D F G'),
        ('4/2', 'C', 'G', 'D F# A'),
        ('b6', 'C', 'C', 'E Ab'),
        ('♮', 'G', 'F', 'B D'),
        ('#3', 'G', 'F', 'B D'),
        ('n', 'D', 'Bb', 'F A'),
        ('6\\', 'A', 'C', 'C F#'),
        ('6+', 'A', 'C', 'C F#'),
        ('6̸', 'A', 'C', 'C F#'),
        ('#6', 'Ab', 'c', 'C F#'),
        ('6#', 'Ab', 'c', 'C F#'),
        ('6 #', 'E', 'C', 'G# C'),
        ('9', 'C', 'C', 'E G D'),
        ('4', 'G', 'C', 'C D'),
        ('8 5', 'C', 'C', 'G C'),
    ],
)
def test_realize(figures: str, bass: str, key: str, expected: str) -> None:
    assert above(figures, bass, key) == expected


def test_realize_with_signature() -> None:
    figured = FiguredBass.parse('6')
    assert figured.realize(PitchName.parse('E'), KeySignature(-1)) == (
        PitchName.parse('G'),
        PitchName.parse('C'),
    )


def test_parse_structure() -> None:
    assert FiguredBass.parse('6/5').figures == (Figure(6), Figure(5))
    assert FiguredBass.parse('#').figures == (Figure(3, FigureAccidental.SHARP),)
    assert FiguredBass.parse('6\\').figures == (Figure(6, FigureAccidental.RAISED),)
    assert [str(f) for f in FiguredBass.parse('4/3').expanded()] == ['6', '4', '3']


@pytest.mark.parametrize(
    ('text', 'canonical'),
    [('65', '6/5'), ('#6', '#6'), ('6#', '#6'), ('', ''), ('6\\', '6+'), ('b7 ♮', 'b7/♮3')],
)
def test_format(text: str, canonical: str) -> None:
    assert str(FiguredBass.parse(text)) == canonical
    assert FiguredBass.parse(canonical) == FiguredBass.parse(text)


@pytest.mark.parametrize('text', ['x', '6x', '#6#', '#6\\', '66', '6 ?', '1', 'h'])
def test_parse_rejects(text: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 - several messages are valid here
        FiguredBass.parse(text)


def test_accidental_symbols() -> None:
    assert [a.symbol for a in FigureAccidental] == ['♯', '♭', '♮', '+']


def test_figures_for_inversion() -> None:
    assert str(figures_for_inversion(3, 0)) == ''
    assert str(figures_for_inversion(4, 2)) == '4/3'
    with pytest.raises(ValueError, match='no inversion figure'):
        figures_for_inversion(5, 0)


@given(
    st.integers(-6, 6),
    st.integers(1, 7),
    st.data(),
)
def test_figures_realize_diatonic_chords(fifths: int, degree: int, data: st.DataObject) -> None:
    key = Key(PitchName.from_line_of_fifths(fifths))
    chord: Chord = data.draw(st.sampled_from([key.triad(degree), key.seventh(degree)]))
    inversion = data.draw(st.integers(0, chord.quality.size - 1))
    chord = chord.with_inversion(inversion)
    figured = figures_for_inversion(chord.quality.size, inversion)
    assert set(figured.realize(chord.bass, key)) | {chord.bass} == set(chord.names())
