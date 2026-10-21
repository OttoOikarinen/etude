# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The phrases the harmony ear exercises play pass the project's voice-leading
checker without an error.

Realising a phrase takes some 30 ms, so the test does not try every phrase in
every key and variant: each key checks a rotating share of the phrases, which
puts every phrase in several keys of each mode, in several variants."""

from __future__ import annotations

import random
from collections.abc import Iterator

import pytest

from etude.audio.spec import Instrument
from etude.checkers.realize import Voicing
from etude.checkers.voice_leading import Context, check, errors
from etude.core import KeySignature
from etude.core.roman import RomanNumeral
from etude.core.scale import Key, Mode
from etude.exercises.families import cadence_ear, progression_ear
from etude.exercises.families.four_part import (
    falls_by_semitone,
    lengths,
    numerals_text,
    parse_numerals,
    phrase_figure,
    phrase_playback,
    progression_label,
    voice,
)
from etude.exercises.families.harmony import satb_voices

KEYS = [
    Key(KeySignature(f).major_tonic if mode is Mode.MAJOR else KeySignature(f).minor_tonic, mode)
    for f in range(-6, 7)
    for mode in Mode
]
SHARE = 4
"""Each key checks every fourth phrase, starting at its own offset."""


def phrases(mode: Mode) -> list[tuple[str, cadence_ear.Phrase | None]]:
    """Every cadence template and every progression (with its changed versions)."""
    found: dict[str, cadence_ear.Phrase | None] = {}
    for kind in cadence_ear.TYPES:
        for phrase in cadence_ear.phrases(kind, mode):
            found.setdefault(f'{phrase.opening}-{phrase.cadence}/{phrase.soprano_last}', phrase)
    for progression in progression_ear.PROGRESSIONS:
        if progression_ear.mode_of(progression) is mode:
            found.setdefault(progression, None)
            for i, s in progression_ear.changes(progression):
                found.setdefault(progression_ear._with_change(progression, i, s), None)
    return list(found.items())


def phrases_in(
    key: Key, offset: int
) -> Iterator[tuple[str, tuple[RomanNumeral, ...], tuple[Voicing, ...]]]:
    rng = random.Random(offset)
    for index, (name, phrase) in enumerate(phrases(key.mode)):
        if index % SHARE != offset % SHARE:
            continue
        if phrase is not None:
            yield name, phrase.numerals, cadence_ear.realize(phrase, key, rng)
        else:
            numerals = parse_numerals(name)
            yield name, numerals, voice(key, numerals, rng)


@pytest.mark.parametrize('index', range(len(KEYS)), ids=lambda i: str(KEYS[i]))
def test_phrases_pass_the_voice_leading_checker(index: int) -> None:
    key = KEYS[index]
    count = 0
    for name, numerals, voicings in phrases_in(key, index // 2):
        chords = tuple(n.realize(key) for n in numerals)
        found = errors(check(voicings, Context(key, chords)))
        assert found == [], (name, str(key), [v.message for v in found])
        count += 1
    assert count >= 8


def test_every_phrase_is_checked_in_several_keys_of_each_mode() -> None:
    for mode in Mode:
        keys = [i for i, k in enumerate(KEYS) if k.mode is mode]
        for position in range(len(phrases(mode))):
            checked = [i for i in keys if (i // 2) % SHARE == position % SHARE]
            assert len(checked) >= 3


@pytest.mark.parametrize('key', [k for k in KEYS if k.mode is Mode.MINOR], ids=str)
def test_phrygian_bass_falls_a_half_step(key: Key) -> None:
    rng = random.Random(str(key))
    for phrase in cadence_ear.phrases(cadence_ear.PHRYGIAN, key.mode):
        voicings = cadence_ear.realize(phrase, key, rng)
        assert falls_by_semitone(voicings), (str(key), phrase)


def test_perfect_authentic_ends_with_the_tonic_on_top() -> None:
    for key in KEYS[:6]:
        for phrase in cadence_ear.phrases(cadence_ear.PERFECT, key.mode):
            voicings = cadence_ear.realize(phrase, key, random.Random(1))
            assert voicings[-1][0].name == key.tonic


def test_figure_and_playback_round_trip() -> None:
    key = Key.parse('f minor')
    numerals = parse_numerals('i-iv-V-i')
    voicings = voice(key, numerals, random.Random(2))
    figure = phrase_figure(key, voicings, labels=['i', 'iv', 'V', 'i'], highlight=[2, 3])
    assert satb_voices(figure) == list(voicings)
    playback = phrase_playback(voicings, tempo=90, instrument=Instrument.ORGAN)
    assert playback.instrument is Instrument.ORGAN
    assert playback.tempo == 90
    assert len(playback.notes) == 16
    assert playback.length == sum(lengths(4))


def test_numeral_texts_and_labels() -> None:
    numerals = parse_numerals('i-iio6-V7-i')
    assert numerals_text(numerals) == 'i-iio6-V7-i'
    assert progression_label(numerals) == 'i–ii°6–V7–i'
    assert progression_label(parse_numerals('I-V65-I')) == 'I–V6/5–I'
