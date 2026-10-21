# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random

import pytest

from etude.core import Chord, ChordQuality, Interval
from etude.core.scale import Key, Mode
from etude.exercises.base import ChoiceAnswer
from etude.exercises.families import cadence_ear
from etude.exercises.families.cadence_ear import (
    AUTHENTIC,
    DECEPTIVE,
    HALF,
    IMPERFECT,
    PERFECT,
    PHRYGIAN,
    PLAGAL,
    TYPES,
    CadenceEar,
    phrases,
    realize,
)
from etude.exercises.families.harmony import satb_voices
from etude.notation.spec import SystemSpec

EXERCISE = CadenceEar()
KEYS = [Key.parse(k) for k in ('C major', 'E major', 'Bb major', 'a minor', 'f# minor', 'eb minor')]


def _last_two(kind: str, key: Key) -> list[tuple[Chord, Chord, tuple[str, ...]]]:
    result = []
    for phrase in phrases(kind, key.mode):
        chords = [n.realize(key) for n in phrase.numerals]
        voicings = realize(phrase, key, random.Random(0))
        result.append((chords[-2], chords[-1], tuple(str(p) for p in voicings[-1])))
    return result


@pytest.mark.parametrize('key', KEYS, ids=str)
def test_authentic_cadences_go_from_dominant_to_tonic(key: Key) -> None:
    dominant = key.tonic.transpose(Interval.parse('P5'))
    for kind in (AUTHENTIC, PERFECT, IMPERFECT):
        for before, last, _v in _last_two(kind, key):
            assert last.root == key.tonic
            assert last.inversion == 0
            assert key.leading_tone in before.names(), 'V or vii° before the tonic'
            assert before.root in (dominant, key.leading_tone)


@pytest.mark.parametrize('key', KEYS, ids=str)
def test_perfect_and_imperfect_authentic(key: Key) -> None:
    for phrase in phrases(PERFECT, key.mode):
        voicings = realize(phrase, key, random.Random(0))
        chords = [n.realize(key) for n in phrase.numerals]
        assert voicings[-1][0].name == key.tonic, 'PAC: tonic in the soprano'
        assert chords[-2].inversion == 0
        assert chords[-1].inversion == 0
    for phrase in phrases(IMPERFECT, key.mode):
        voicings = realize(phrase, key, random.Random(0))
        chords = [n.realize(key) for n in phrase.numerals]
        top = voicings[-1][0].name
        inverted = chords[-2].inversion != 0 or chords[-2].root == key.leading_tone
        assert inverted or top != key.tonic, 'IAC: soprano not on 1, or an inverted dominant'


@pytest.mark.parametrize('key', KEYS, ids=str)
def test_half_plagal_deceptive_and_phrygian(key: Key) -> None:
    for phrase in phrases(HALF, key.mode):
        last = phrase.numerals[-1]
        assert (last.degree, last.quality, last.inversion) == (5, ChordQuality.MAJOR, 0)
    for phrase in phrases(PLAGAL, key.mode):
        before, last = phrase.numerals[-2:]
        assert (before.degree, last.degree) == (4, 1)
    for phrase in phrases(DECEPTIVE, key.mode):
        before, last = phrase.numerals[-2:]
        assert (before.degree, last.degree) == (5, 6)
    if key.mode is Mode.MINOR:
        for phrase in phrases(PHRYGIAN, key.mode):
            voicings = realize(phrase, key, random.Random(0))
            before, last = phrase.numerals[-2:]
            assert (before.degree, before.inversion, last.degree) == (4, 1, 5)
            assert voicings[-2][3].midi - voicings[-1][3].midi == 1, 'bass falls a half step'
    else:
        assert phrases(PHRYGIAN, key.mode) == ()


def test_items_follow_the_settings() -> None:
    defaults = EXERCISE.default_settings()
    assert [i.split('.')[-1] for i in EXERCISE.items(defaults)] == [
        AUTHENTIC,
        HALF,
        PLAGAL,
        DECEPTIVE,
    ]
    split = {**defaults, 'authentic-kinds': True, 'phrygian': True}
    assert [i.split('.')[-1] for i in EXERCISE.items(split)] == [
        PERFECT,
        IMPERFECT,
        HALF,
        PLAGAL,
        DECEPTIVE,
        PHRYGIAN,
    ]
    assert 'cadence.ear.phrygian' in EXERCISE.confusables('cadence.ear.half')
    assert 'cadence.ear.imperfect-authentic' in EXERCISE.confusables(
        'cadence.ear.perfect-authentic'
    )


@pytest.mark.parametrize('kind', TYPES)
def test_questions_and_feedback(kind: str) -> None:
    settings = {**EXERCISE.default_settings(), 'mode': 'both', 'authentic-kinds': True}
    for seed in range(6):
        question = EXERCISE.generate(f'cadence.ear.{kind}', settings, random.Random(seed))
        assert isinstance(question.written_alternative, SystemSpec)
        assert not question.playback_style_choice
        key = Key.parse(question.details['key'])
        if kind == PHRYGIAN:
            assert key.mode is Mode.MINOR
        voicings = satb_voices(question.written_alternative)
        phrase = cadence_ear.Phrase(question.details['opening'], question.details['cadence'])
        assert len(phrase.numerals) == len(voicings)
        assert any(
            p.opening == phrase.opening and p.cadence == phrase.cadence
            for p in phrases(kind, key.mode)
        )
        assert question.playback is not None
        assert len(question.playback.notes) == 4 * len(voicings)
        assert isinstance(question.answer, ChoiceAnswer)
        right = EXERCISE.grade(question, kind)
        assert right.correct
        assert right.play_expected == question.playback
        assert isinstance(right.figure, SystemSpec)
        assert right.figure.staves[1].voices[0][0].label  # Roman numerals under the bass
        for option in question.answer.options:
            if option.key == kind:
                continue
            wrong = EXERCISE.grade(question, option.key)
            assert not wrong.correct
            assert wrong.play_given is not None
            assert wrong.play_given != question.playback
            assert 'For comparison' in wrong.detail


def test_explanation_names_the_cadence_chords() -> None:
    question = EXERCISE.generate('cadence.ear.deceptive', {'mode': 'major'}, random.Random(2))
    feedback = EXERCISE.grade(question, 'deceptive')
    assert feedback.title.startswith('Correct — deceptive cadence')
    assert '–vi in ' in feedback.detail
