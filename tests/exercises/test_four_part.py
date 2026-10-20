# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Every phrase the harmony ear exercises play, in every key, obeys the voice-leading
rules. The checks here are written independently of :mod:`four_part` (which also
enforces them), so a bug in the generator cannot hide itself."""

from __future__ import annotations

import itertools
from collections.abc import Iterator, Sequence

import pytest

from etude.core import Chord, ChordKind, Duration, Interval, KeySignature, NoteValue, Pitch
from etude.core.roman import RomanNumeral
from etude.core.scale import Key, Mode
from etude.exercises.families import cadence_ear, progression_ear
from etude.exercises.families.four_part import (
    figure_text,
    key_of,
    numeral_label,
    parse_numerals,
    progression_label,
    system_figure,
    voice_progression,
    voicings_of,
)

KEYS = [
    Key(KeySignature(f).major_tonic if mode is Mode.MAJOR else KeySignature(f).minor_tonic, mode)
    for f in range(-6, 7)
    for mode in Mode
]
RANGES = {0: (60, 79), 1: (55, 74), 2: (48, 67), 3: (40, 60)}


def phrases_in(key: Key) -> Iterator[tuple[str, tuple[RomanNumeral, ...], Sequence[Pitch]]]:
    for kind in cadence_ear.TYPES:
        for phrase in cadence_ear.phrases(kind, key.mode):
            yield kind, phrase.numerals, cadence_ear.realize(phrase, key)
    for progression in progression_ear.PROGRESSIONS:
        if progression_ear.mode_of(progression) is not key.mode:
            continue
        variants = [progression] + [
            progression_ear._with_change(progression, i, s)
            for i, s in progression_ear.changes(progression)
        ]
        for text in variants:
            numerals = parse_numerals(text)
            voiced = 0
            for tone in numerals[0].realize(key).names():
                try:
                    voicings = progression_ear.voiced(key, numerals, tone)
                except ValueError:
                    continue
                voiced += 1
                yield text, numerals, voicings
            assert voiced, f'{text} cannot be voiced in {key}'


def check_chord(voicing: Sequence[Pitch], chord: Chord, key: Key) -> None:
    soprano, alto, tenor, bass = voicing
    for voice, pitch in enumerate(voicing):
        low, high = RANGES[voice]
        assert low <= pitch.midi <= high, f'voice {voice} out of range: {pitch}'
    assert soprano.midi > alto.midi > tenor.midi > bass.midi, 'voices cross'
    assert soprano.midi - alto.midi <= 12
    assert alto.midi - tenor.midi <= 12
    names = [p.name for p in voicing]
    tones = chord.names()
    assert set(names) <= set(tones), 'only chord tones'
    assert bass.name == chord.bass, 'the bass gives the inversion'
    assert tones[0] in names
    assert tones[1] in names
    if chord.quality.kind is ChordKind.SEVENTH:
        assert names.count(tones[3]) == 1, 'the seventh is present and not doubled'
    if key.leading_tone in tones:
        assert names.count(key.leading_tone) <= 1, 'the leading tone is never doubled'


def check_motion(
    before: Sequence[Pitch], after: Sequence[Pitch], first: Chord, second: Chord, key: Key
) -> None:
    for i, j in itertools.combinations(range(4), 2):
        moved = before[i] != after[i] and before[j] != after[j]
        old = (before[i].midi - before[j].midi) % 12
        new = (after[i].midi - after[j].midi) % 12
        assert not (moved and old == new and new in (0, 7)), (
            f'parallel {"octaves" if new == 0 else "fifths"} between voices {i} and {j}'
        )
    for voice in range(4):
        a, b = before[voice], after[voice]
        leap = abs(b.midi - a.midi)
        assert leap <= (12 if voice == 3 else 7)
        if a != b:
            low, high = sorted((a, b), key=lambda p: (p.diatonic_index, p.midi))
            quality = Interval.between(low, high).quality.value
            assert quality in ('m', 'M', 'P'), f'augmented or diminished leap {a}–{b}'
    resolves = (
        key.leading_tone in first.names()
        and key.tonic in second.names()
        and key.leading_tone not in second.names()
    )
    for a, b in zip(before, after, strict=True):
        if resolves and a.name == key.leading_tone:
            assert b.name == key.tonic, 'the leading tone resolves to the tonic'
            assert b.midi == a.midi + 1, 'the leading tone rises'
    if first.quality.kind is ChordKind.SEVENTH:
        seventh = first.names()[3]
        for a, b in zip(before, after, strict=True):
            if a.name == seventh:
                assert 1 <= a.midi - b.midi <= 2, 'the seventh falls by step'


@pytest.mark.parametrize('key', KEYS, ids=str)
def test_every_phrase_follows_the_voice_leading_rules(key: Key) -> None:
    count = 0
    for _name, numerals, voicings in phrases_in(key):
        chords = [n.realize(key) for n in numerals]
        assert len(voicings) == len(chords)
        for voicing, chord in zip(voicings, chords, strict=True):
            check_chord(voicing, chord, key)
        for step in range(1, len(voicings)):
            check_motion(voicings[step - 1], voicings[step], chords[step - 1], chords[step], key)
        count += 1
    assert count > 20


def test_parallel_fifths_are_never_chosen_even_when_smoothest() -> None:
    # I–ii in root position invites parallel fifths and octaves when all voices
    # move up by step; the result must avoid them.
    key = Key.parse('C major')
    voicings = voice_progression(key, parse_numerals('I-ii-V-I'))
    for a, b in itertools.pairwise(voicings):
        for i, j in itertools.combinations(range(4), 2):
            old = (a[i].midi - a[j].midi) % 12
            new = (b[i].midi - b[j].midi) % 12
            assert not (a[i] != b[i] and a[j] != b[j] and old == new and new in (0, 7))


def test_soprano_constraints() -> None:
    key = Key.parse('D major')
    perfect = voice_progression(key, parse_numerals('I-IV-V-I'), None, frozenset({key.tonic}))
    assert perfect[-1][0].name == key.tonic


def test_figure_round_trip() -> None:
    key = Key.parse('f minor')
    voicings = voice_progression(key, parse_numerals('i-iv-V-i'))
    durations = (Duration(NoteValue.QUARTER),) * 4
    figure = system_figure(key, voicings, durations=durations)
    assert voicings_of(figure) == list(voicings)
    assert key_of(figure) == key
    major = Key.parse('A major')
    figure = system_figure(
        major, voice_progression(major, parse_numerals('ii-V-I')), durations=durations[:3]
    )
    assert key_of(figure) == major


def test_numeral_labels_use_proper_symbols() -> None:
    assert numeral_label(RomanNumeral.parse('iio6')) == 'ii°⁶'
    assert numeral_label(RomanNumeral.parse('V7')) == 'V⁷'
    assert numeral_label(RomanNumeral.parse('V65')) == 'V⁶₅'
    assert numeral_label(RomanNumeral.parse('iv6')) == 'iv⁶'
    assert numeral_label(RomanNumeral.parse('bVI')) == '♭VI'
    assert numeral_label(RomanNumeral.parse('V7/V')) == 'V⁷/V'
    assert numeral_label(RomanNumeral.parse('viio7')) == 'vii°⁷'
    assert progression_label(parse_numerals('i-VII-VI-V')) == 'i–VII–VI–V'
    assert figure_text('42') == '⁴₂'
