# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The four-part voicer: every realisation it writes passes the checker."""

from __future__ import annotations

import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from etude.checkers.realize import RealisationError, bass_line, chords_of, realize
from etude.checkers.voice_leading import (
    BASS,
    SOPRANO,
    Context,
    Ranges,
    Severity,
    check,
    errors,
)
from etude.core import Key, Pitch, PitchName, RomanNumeral

C = Key.parse('C')

MAJOR = (
    'I V I',
    'I IV V I',
    'I vi IV V I',
    'I I6 IV V I',
    'I ii6 V I',
    'I IV Cad64 V I',
    'I IV V vi',
    'I viio6 I6',
    'I V7 I',
    'I V65 I',
    'I V43 I6',
    'I V42 I6',
    'I ii65 V7 I',
    'I ii7 V7 I',
    'I IV6 V6 I',
)
MINOR = (
    'i V i',
    'i iv V i',
    'i VI iv V i',
    'i i6 iv V i',
    'i iio6 V i',
    'i iv Cad64 V i',
    'i iv V VI',
    'i viio6 i6',
    'i V7 i',
    'i V65 i',
    'i V43 i6',
    'i V42 i6',
    'i iiø65 V7 i',
    'i viio7 i',
)
MAJOR_TONICS = ('C', 'G', 'D', 'A', 'E', 'F', 'Bb', 'Eb', 'Ab')
MINOR_TONICS = ('a', 'e', 'b', 'f#', 'c#', 'd', 'g', 'c', 'f')


def _assert_correct(
    chords: tuple[tuple[Pitch, ...], ...], numerals: list[str], key: Key, ranges: Ranges
) -> None:
    harmony = chords_of(numerals, key)
    found = errors(check(chords, Context(key, harmony, ranges)))
    assert found == [], [v.message for v in found]
    for chord, expected in zip(chords, harmony, strict=True):
        assert {p.name for p in chord} <= set(expected.names())
        assert chord[BASS].name == expected.bass


@settings(max_examples=150, deadline=None)
@given(
    minor=st.booleans(),
    index=st.integers(0, 100),
    tonic=st.integers(0, 8),
    seed=st.integers(0, 1_000_000),
)
def test_every_realisation_passes_the_checker(
    minor: bool, index: int, tonic: int, seed: int
) -> None:
    """Across keys, modes, inversions and seventh chords."""
    progressions = MINOR if minor else MAJOR
    numerals = progressions[index % len(progressions)].split()
    key = Key.parse((MINOR_TONICS if minor else MAJOR_TONICS)[tonic])
    chords = realize(numerals, key, random.Random(seed))
    _assert_correct(chords, numerals, key, Ranges())


@pytest.mark.parametrize('numerals', MAJOR + MINOR)
def test_each_progression_in_c(numerals: str) -> None:
    key = Key.parse('c' if numerals.startswith('i ') else 'C')
    for seed in range(5):
        _assert_correct(
            realize(numerals.split(), key, random.Random(seed)), numerals.split(), key, Ranges()
        )


def test_numerals_chords_and_text_are_the_same_request() -> None:
    text = ['I', 'ii65', 'V7', 'I']
    numerals = [RomanNumeral.parse(n) for n in text]
    spelled = [n.realize(C) for n in numerals]
    results = {realize(h, C, random.Random(3)) for h in (text, numerals, spelled)}
    assert len(results) == 1


def test_a_seed_gives_one_answer_and_seeds_vary() -> None:
    numerals = ['I', 'vi', 'IV', 'V', 'I']
    assert realize(numerals, C, random.Random(7)) == realize(numerals, C, random.Random(7))
    answers = {realize(numerals, C, random.Random(seed)) for seed in range(12)}
    assert len(answers) > 1
    assert realize(numerals, C) == realize(numerals, C), 'without rng: a fixed seed'


def test_soprano_constraint() -> None:
    # A perfect authentic cadence: the tonic on top of the final chord.
    tonic = PitchName.parse('C')
    for seed in range(10):
        chords = realize(
            ['I', 'IV', 'V', 'I'], C, random.Random(seed), soprano=[None] * 3 + [tonic]
        )
        assert chords[-1][SOPRANO].name == tonic
    exact = Pitch.parse('E5')
    chords = realize(['I', 'V', 'I'], C, random.Random(1), soprano=[exact, None, None])
    assert chords[0][SOPRANO] == exact


def test_given_bass() -> None:
    bass = tuple(Pitch.parse(n) for n in ('C3', 'F2', 'G2', 'C3'))
    chords = realize(['I', 'IV', 'V', 'I'], C, random.Random(2), bass=bass)
    assert tuple(c[BASS] for c in chords) == bass


def test_impossible_requests() -> None:
    with pytest.raises(RealisationError):
        realize(['I', 'V', 'I'], C, soprano=[PitchName.parse('C#'), None, None])
    with pytest.raises(RealisationError):
        realize(['I', 'V'], C, bass=(Pitch.parse('E3'), Pitch.parse('G2')))
    with pytest.raises(RealisationError):
        # The leading tone on top of V and again on top of I: it cannot rise.
        realize(['V', 'I'], C, soprano=[Pitch.parse('B4'), Pitch.parse('B4')])
    with pytest.raises(ValueError, match='one entry per chord'):
        realize(['I', 'V'], C, soprano=[None])
    with pytest.raises(ValueError, match='nothing'):
        realize([], C)
    assert issubclass(RealisationError, ValueError)


def test_bass_line_resolves_tendency_tones() -> None:
    for seed in range(20):
        rng = random.Random(seed)
        v42 = bass_line(chords_of(['I', 'V42', 'I6'], C), rng)
        assert v42[2].diatonic_index == v42[1].diatonic_index - 1, 'the seventh falls'
        v6 = bass_line(chords_of(['I', 'V6', 'I'], C), rng)
        assert v6[2].diatonic_index == v6[1].diatonic_index + 1, 'the leading tone rises'
        low, high = Ranges().bass
        assert all(low.midi <= p.midi <= high.midi for p in v42 + v6)


def test_realisations_prefer_complete_chords_and_few_warnings() -> None:
    warnings = 0
    for seed in range(20):
        chords = realize(['I', 'IV', 'V', 'I'], C, random.Random(seed))
        found = check(chords, Context(C, chords_of(['I', 'IV', 'V', 'I'], C)))
        warnings += sum(1 for v in found if v.severity is Severity.WARNING)
    assert warnings <= 5


# Textbook doubling (a preference of the voicer, not a rule of the checker) ----------


def _doubled(chord, voicing) -> set[int]:
    """Chord tones (0 root, 1 third, 2 fifth, 3 seventh) sung by more than one voice."""
    names = chord.names()
    return {i for i, name in enumerate(names) if sum(p.name == name for p in voicing) > 1}


def _voiced(numerals: str, tonic: str, seeds: int = 12):
    key = Key.parse(tonic)
    harmony = chords_of(numerals.split(), key)
    for seed in range(seeds):
        yield harmony, realize(harmony, key, random.Random(seed))


@pytest.mark.parametrize('tonic', ['C', 'Bb', 'a', 'f#'])
def test_root_position_triads_double_the_root(tonic: str) -> None:
    # K–P ch. 5: in root position, double the root.
    numerals = 'I IV V I' if tonic[0].isupper() else 'i iv V i'
    for harmony, chords in _voiced(numerals, tonic):
        for chord, voicing in zip(harmony, chords, strict=True):
            assert _doubled(chord, voicing) == {0}, voicing


@pytest.mark.parametrize(
    ('numerals', 'tonic'), [('I viio6 I6', 'C'), ('i iio6 V i', 'a'), ('i viio6 i6', 'd')]
)
def test_diminished_sixth_chords_double_the_bass(numerals: str, tonic: str) -> None:
    # K–P ch. 8: in ii°6 and vii°6 double the bass (the third), never the leading tone.
    key = Key.parse(tonic)
    for harmony, chords in _voiced(numerals, tonic):
        chord, voicing = harmony[1], chords[1]
        assert _doubled(chord, voicing) == {1}, voicing
        assert sum(p.name == key.leading_tone for p in voicing) <= 1


@pytest.mark.parametrize('tonic', ['G', 'c'])
def test_six_four_chords_double_the_bass(tonic: str) -> None:
    # K–P ch. 9: the cadential six-four doubles its bass (the fifth of the tonic triad).
    numerals = 'I IV Cad64 V I' if tonic.isupper() else 'i iv Cad64 V i'
    for harmony, chords in _voiced(numerals, tonic):
        assert _doubled(harmony[2], chords[2]) == {2}, chords[2]


@pytest.mark.parametrize('tonic', ['D', 'g'])
def test_deceptive_cadence_doubles_the_third_of_vi(tonic: str) -> None:
    # K–P ch. 6: in V–vi the leading tone rises and the third of vi is doubled.
    numerals = 'I IV V vi' if tonic.isupper() else 'i iv V VI'
    for harmony, chords in _voiced(numerals, tonic):
        assert _doubled(harmony[3], chords[3]) == {1}, chords[3]


def test_soprano_from_a_set_of_names() -> None:
    # An imperfect authentic cadence: 3̂ or 5̂ on top of the final tonic.
    key = Key.parse('F')
    allowed = {key.degree(3), key.degree(5)}
    tops = set()
    for seed in range(16):
        chords = realize(
            ['I', 'IV', 'V', 'I'], key, random.Random(seed), soprano=[None] * 3 + [allowed]
        )
        tops.add(chords[-1][SOPRANO].name)
    assert tops <= allowed
    assert tops, 'some answer'
    with pytest.raises(RealisationError):
        realize(['I', 'V'], key, soprano=[None, frozenset({PitchName.parse('Bb')})])


@pytest.mark.parametrize(
    ('numeral', 'tonic'), [('iiø7', 'c'), ('viio7', 'a'), ('ii7', 'C'), ('V7', 'G')]
)
def test_complete_seventh_chords(numeral: str, tonic: str) -> None:
    key = Key.parse(tonic)
    chord = RomanNumeral.parse(numeral).realize(key)
    for seed in range(10):
        (voicing,) = realize([chord], key, random.Random(seed), complete=True)
        assert {p.name for p in voicing} == set(chord.names())
    if numeral in ('iiø7', 'viio7'):
        # Without its diminished fifth the chord would read as another one: complete
        # voicings are preferred even when not required.
        for seed in range(10):
            (voicing,) = realize([chord], key, random.Random(seed))
            assert {p.name for p in voicing} == set(chord.names())


@pytest.mark.parametrize('tonic', ['a', 'e', 'b', 'f#', 'c#', 'd', 'g', 'c', 'f'])
def test_phrygian_bass_falls_the_half_step(tonic: str) -> None:
    for seed in range(15):
        key = Key.parse(tonic)
        chords = realize(['i', 'iv6', 'V'], key, random.Random(seed))
        assert chords[1][BASS].midi - chords[2][BASS].midi == 1, (tonic, seed, chords)
