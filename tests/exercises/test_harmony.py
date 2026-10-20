# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random

import pytest

from etude.checkers.voice_leading import Ranges
from etude.core import Chord, ChordQuality, Duration, NoteValue, Pitch, PitchName
from etude.core.roman import RomanNumeral
from etude.core.scale import Key, Mode
from etude.exercises.families.harmony import (
    chord_of,
    figure_text,
    keys_within,
    roman_label,
    satb_durations,
    satb_figure,
    satb_voices,
    voice_progression,
    voicings,
)

RANGES = Ranges()


def test_figure_text_writes_figures_with_slashes() -> None:
    assert figure_text('53') == ''
    assert figure_text('6') == '6'
    assert figure_text('64') == '6/4'
    assert figure_text('65') == '6/5'
    assert figure_text('43') == '4/3'
    assert figure_text('42') == '4/2'


@pytest.mark.parametrize(
    ('text', 'label'),
    [
        ('V65', 'V6/5'),
        ('viio7', 'vii°7'),
        ('viiø43', 'viiø4/3'),
        ('IV', 'IV'),
        ('I64', 'I6/4'),
        ('IM7', 'IM7'),
        ('V7/V', 'V7/V'),
        ('V65/V', 'V6/5/V'),
        ('viio42/ii', 'vii°4/2/ii'),
        ('bII6', '♭II6'),
        ('Ger+6', 'Ger+6'),
    ],
)
def test_roman_label(text: str, label: str) -> None:
    assert roman_label(RomanNumeral.parse(text)) == label


def test_keys_within_counts_signatures() -> None:
    assert [str(k) for k in keys_within(0, (Mode.MAJOR, Mode.MINOR))] == ['C major', 'a minor']
    keys = keys_within(2, (Mode.MAJOR,))
    assert {str(k.tonic) for k in keys} == {'Bb', 'F', 'C', 'G', 'D'}
    assert len(keys_within(7, (Mode.MAJOR, Mode.MINOR))) == 30


def in_range(pitch: Pitch, voice: int) -> bool:
    low, high = RANGES.of(voice)
    return low.midi <= pitch.midi <= high.midi


@pytest.mark.parametrize('text', ['I', 'V6', 'viio6', 'ii64', 'V7', 'viiø42', 'iii64'])
def test_voicings_follow_ranges_spacing_and_doubling(text: str) -> None:
    key = Key.parse('D')
    chord = RomanNumeral.parse(text).realize(key)
    options = voicings(chord, key)
    assert options
    for voicing, _penalty in options:
        s, a, t, b = voicing
        assert all(in_range(p, v) for v, p in enumerate(voicing))
        assert s.midi > a.midi > t.midi > b.midi
        assert s.midi - a.midi <= 12
        assert a.midi - t.midi <= 12
        assert b.name == chord.bass
        assert {p.name for p in voicing} <= set(chord.names())
        # The leading tone is never doubled.
        assert sum(p.name == key.leading_tone for p in voicing) <= 1
        if chord.quality.size == 4 and chord.inversion:
            assert {p.name for p in voicing} == set(chord.names())


def test_preferred_doublings() -> None:
    key = Key.parse('C')

    def best(text: str) -> set[PitchName]:
        chord = RomanNumeral.parse(text).realize(key)
        doubled = set()
        for voicing, penalty in voicings(chord, key):
            if penalty == 0:
                names = [p.name for p in voicing]
                doubled |= {n for n in names if names.count(n) == 2}
        return doubled

    assert best('I') == {PitchName.parse('C')}  # root position: the root
    assert best('viio6') == {PitchName.parse('D')}  # diminished first inversion: the third
    assert best('I64') == {PitchName.parse('G')}  # six-four: the bass


def parallels(a: tuple[Pitch, ...], b: tuple[Pitch, ...]) -> bool:
    for i in range(4):
        for j in range(i + 1, 4):
            if a[i] == b[i] or a[j] == b[j]:
                continue
            first = (a[i].midi - a[j].midi) % 12
            if first in (0, 7) and first == (b[i].midi - b[j].midi) % 12:
                return True
    return False


PROGRESSIONS = [
    ('C', 'I IV V I'),
    ('c', 'i iio6 V7 i'),
    ('D', 'I ii6 V vi'),
    ('a', 'i iv iv6 V'),
    ('Eb', 'I vi ii6 V7 I'),
    ('g', 'i iv V VI'),
    ('F', 'I V6 I IV I'),
    ('b', 'i VI iio6 V i'),
]


@pytest.mark.parametrize(('key_text', 'numerals'), PROGRESSIONS)
def test_voice_progression_has_no_parallels_and_resolves_tendency_tones(
    key_text: str, numerals: str
) -> None:
    key = Key.parse(key_text)
    chords = [RomanNumeral.parse(n).realize(key) for n in numerals.split()]
    for seed in range(15):
        voices = voice_progression(chords, key, random.Random(seed))
        for before, after, chord in zip(voices, voices[1:], chords, strict=False):
            assert not parallels(before, after), (key_text, numerals, seed)
            for upper in range(3):  # no overlap
                assert after[upper + 1].midi <= before[upper].midi
                assert after[upper].midi >= before[upper + 1].midi
            if chord.quality.size == 4:
                seventh = chord.names()[3]
                for v in range(4):
                    if before[v].name == seventh:
                        assert after[v].diatonic_index == before[v].diatonic_index - 1
            if before[0].name == key.leading_tone and key.tonic in [p.name for p in after]:
                assert after[0].name == key.tonic


def test_soprano_constraint_is_kept() -> None:
    key = Key.parse('G')
    chords = [RomanNumeral.parse(n).realize(key) for n in ['I', 'IV', 'V', 'I']]
    for seed in range(10):
        voices = voice_progression(chords, key, random.Random(seed), soprano={3: {key.tonic}})
        assert voices[-1][0].name == key.tonic


def test_chord_of_reads_complete_and_incomplete_chords() -> None:
    def pitches(text: str) -> list[Pitch]:
        return [Pitch.parse(p) for p in text.split()]

    assert chord_of(pitches('E3 G3 C4')) == Chord(PitchName.parse('C'), ChordQuality.MAJOR, 1)
    # V7 without its fifth, and a tonic with a tripled root and no fifth.
    assert chord_of(pitches('G2 G3 B3 F4')) == Chord(
        PitchName.parse('G'), ChordQuality.DOMINANT_SEVENTH
    )
    assert chord_of(pitches('C3 C4 E4 C5')) == Chord(PitchName.parse('C'), ChordQuality.MAJOR)


def test_satb_figure_round_trips() -> None:
    voices = ((Pitch.parse('C5'), Pitch.parse('G4'), Pitch.parse('E4'), Pitch.parse('C3')),)
    for durations in ((), (Duration(NoteValue.HALF),)):
        figure = satb_figure(voices, None, durations=durations, labels=('I',), highlight=(0,))
        assert satb_voices(figure) == list(voices)
        assert satb_durations(figure) == durations
