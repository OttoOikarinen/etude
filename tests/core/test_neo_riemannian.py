# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest
from hypothesis import given
from hypothesis import strategies as st

from etude.core import Chord, ChordQuality, PitchName
from etude.core.neo_riemannian import apply, expand, shortest_path, transform

MAJOR, MINOR = ChordQuality.MAJOR, ChordQuality.MINOR


def triad(text: str) -> Chord:
    """'C' is C major, 'c' is C minor."""
    return Chord(PitchName.parse(text), MAJOR if text[0].isupper() else MINOR)


@pytest.mark.parametrize(
    ('start', 'operations', 'expected'),
    [
        ('C', 'P', 'c'),
        ('C', 'L', 'e'),
        ('C', 'R', 'a'),
        ('c', 'P', 'C'),
        ('e', 'L', 'C'),
        ('a', 'R', 'C'),
        ('c', 'L', 'Ab'),
        ('c', 'R', 'Eb'),
        ('C', 'PL', 'Ab'),
        ('C', 'LR', 'G'),
        ('C', 'RL', 'F'),
        ('C', 'N', 'f'),
        ('C', 'S', 'c#'),
        ('C', 'H', 'g#'),
        ('C', 'PLR', 'f'),
        ('C', 'P L R', 'f'),
        ('C', '', 'C'),
    ],
)
def test_apply(start: str, operations: str, expected: str) -> None:
    assert apply(triad(start), operations) == triad(expected)


def test_expand() -> None:
    assert expand('NS') == 'RLPLPR'
    assert expand('h.p') == 'LPLP'
    with pytest.raises(ValueError, match='unknown transformation'):
        expand('PX')


def test_only_triads() -> None:
    with pytest.raises(ValueError, match='major and minor triads'):
        apply(Chord(PitchName.parse('C'), ChordQuality.DIMINISHED), 'P')
    with pytest.raises(ValueError, match='unknown transformation'):
        transform(triad('C'), 'N')


def test_inversion_is_dropped() -> None:
    assert apply(Chord(PitchName.parse('C'), MAJOR, 1), 'P') == triad('c')


@pytest.mark.parametrize(
    ('start', 'end', 'path'),
    [('C', 'C', ''), ('C', 'c', 'P'), ('C', 'Ab', 'PL'), ('C', 'eb', 'PRP'), ('C', 'Db', 'LPRP')],
)
def test_shortest_path(start: str, end: str, path: str) -> None:
    assert shortest_path(triad(start), triad(end)) == path


def test_long_chains_stay_spellable() -> None:
    assert apply(triad('C'), 'LR' * 12).root.pitch_class == 0
    assert apply(triad('F#'), 'LR' * 20).quality is MAJOR


triads = st.builds(
    lambda fifths, quality: Chord(PitchName.from_line_of_fifths(fifths), quality),
    st.integers(-7, 7),
    st.sampled_from([MAJOR, MINOR]),
)


@given(triads, st.sampled_from('PLR'))
def test_involutions(chord: Chord, operation: str) -> None:
    once = transform(chord, operation)
    assert transform(once, operation) == chord
    assert len(set(once.names()) & set(chord.names())) == 2


@given(triads, triads)
def test_shortest_path_reaches_target(start: Chord, end: Chord) -> None:
    path = shortest_path(start, end)
    result = apply(start, path)
    assert result.root.pitch_class == end.root.pitch_class
    assert result.quality is end.quality
    assert len(path) <= 6
