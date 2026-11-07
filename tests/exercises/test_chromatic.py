# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Chromatic Chords and Chromatic Writing: the musical facts behind questions and grades."""

from __future__ import annotations

import random
from collections.abc import Mapping
from typing import cast

import pytest

from etude.checkers.realize import Voicing, chords_of, function_keys, realize
from etude.checkers.voice_leading import (
    ALTO,
    BASS,
    SOPRANO,
    TENOR,
    Context,
    Rule,
    Severity,
    check,
    errors,
)
from etude.core import Key, Pitch, RomanNumeral
from etude.exercises.base import ChipsAnswer, StaffInputAnswer
from etude.exercises.families.chromatic import (
    ChromaticChords,
    ChromaticWriting,
    chips_label,
    figures_key,
    numeral_key,
)
from etude.exercises.families.harmony import roman_label, satb_voices
from etude.notation.spec import Chord as StaffChord
from etude.notation.spec import Ink, SystemSpec

NAMING = ChromaticChords()
WRITING = ChromaticWriting()


@pytest.mark.parametrize(
    ('numeral', 'chips'),
    [
        ('V65/V', ('V', '65')),
        ('V/ii', ('V', '53')),
        ('viio7/V', ('viio', '7')),
        ('viiø43/V', ('viiø', '43')),
        ('iio6', ('iio', '6')),
        ('iiø65', ('iiø', '65')),
        ('bVI', ('bVI', '53')),
        ('viio7', ('viio', '7')),
        ('N6', ('N', '6')),
        ('It+6', ('It', '6')),
        ('Fr+6', ('Fr', '6')),
        ('Ger+6', ('Ger', '6')),
        ('Ger+6(#2)', ('Ger', '6')),
    ],
)
def test_chips_spell_the_kostka_payne_label(numeral: str, chips: tuple[str, str]) -> None:
    parsed = RomanNumeral.parse(numeral)
    assert (numeral_key(parsed), figures_key(parsed)) == chips
    target = parsed.secondary
    value = {'numeral': chips[0], 'figures': chips[1], 'target': str(target or 'none')}
    assert chips_label(value) == roman_label(parsed)


def test_labels_follow_kostka_payne() -> None:
    assert chips_label({'numeral': 'viio', 'figures': '65', 'target': 'V'}) == 'vii°6/5/V'
    assert chips_label({'numeral': 'N', 'figures': '6'}) == 'N6'
    assert chips_label({'numeral': 'Ger', 'figures': '6', 'target': 'none'}) == 'Ger+6'
    assert chips_label({'numeral': 'bVI', 'figures': '53'}) == '♭VI'


def test_items_follow_families_and_modes() -> None:
    every = NAMING.items(NAMING.default_settings())
    assert every[0] == 'chromatic.name.major.V/V'
    assert 'chromatic.name.minor.N6' in every
    assert 'chromatic.name.major.Ger+6' in every
    augmented = NAMING.items({'families': ('augmented-sixth',), 'mode': 'minor'})
    assert augmented == [
        'chromatic.name.minor.It+6',
        'chromatic.name.minor.Fr+6',
        'chromatic.name.minor.Ger+6',
    ]
    # Mixture is borrowed from minor into major: asked in minor, the major items stay.
    mixture = NAMING.items({'families': ('mixture',), 'mode': 'minor'})
    assert mixture
    assert all('.major.' in item for item in mixture)


def _question_chord_names(figure: object, focus: int) -> set[str]:
    return {str(p.name) for p in satb_voices(figure)[focus]}


@pytest.mark.parametrize('item', NAMING.items(NAMING.default_settings()))
def test_the_marked_chord_is_the_expected_one(item: str) -> None:
    settings = NAMING.default_settings()
    for seed in range(3):
        question = NAMING.generate(item, settings, random.Random(seed))
        key = Key.parse(question.details['key'])
        numeral = RomanNumeral.parse(question.details['numeral'])
        focus = int(question.details['focus'])
        chord = numeral.realize(key)
        names = _question_chord_names(question.figure, focus)
        tones = [str(n) for n in chord.names()]
        assert names <= set(tones), (item, question.details)
        # Root, third and any seventh are there; a root-position seventh chord may
        # omit its fifth, as in four-part writing.
        assert {tones[0], tones[1], *tones[3:]} <= names, (item, question.details)
        expected = cast(Mapping[str, str], question.expected)
        assert chips_label(expected) == roman_label(numeral)
        # Marked by text and by colour, never by colour alone.
        figure = question.figure
        assert isinstance(figure, SystemSpec)
        bass = [e for e in figure.staves[1].voices[0] if isinstance(e, StaffChord)]
        assert bass[focus].label == '?'
        assert bass[focus].ink is Ink.ACCENT
        assert f'chord {focus + 1}' in (figure.description or '')
        assert roman_label(numeral) not in (figure.description or '')


def test_the_target_chips_appear_with_secondary_dominants() -> None:
    question = NAMING.generate(
        'chromatic.name.major.N6', {'families': ('neapolitan',)}, random.Random(0)
    )
    answer = question.answer
    assert isinstance(answer, ChipsAnswer)
    assert [g.key for g in answer.groups] == ['numeral', 'figures']
    question = NAMING.generate('chromatic.name.major.V7/V', {}, random.Random(0))
    answer = question.answer
    assert isinstance(answer, ChipsAnswer)
    assert [g.key for g in answer.groups] == ['numeral', 'target', 'figures']


def test_feedback_explains_and_analyses_the_phrase() -> None:
    question = NAMING.generate('chromatic.name.minor.N6', {}, random.Random(2))
    expected = cast(Mapping[str, str], question.expected)
    right = NAMING.grade(question, expected)
    assert right.correct
    assert right.title.endswith('N6')
    assert 'Neapolitan' in right.detail
    figure = right.figure
    assert isinstance(figure, SystemSpec)
    labels = [e.label for e in figure.staves[1].voices[0] if isinstance(e, StaffChord)]
    assert 'N6' in labels
    wrong = NAMING.grade(question, {**expected, 'figures': '53'})
    assert not wrong.correct
    assert 'find the bass' in wrong.detail
    question = NAMING.generate('chromatic.name.major.V7/ii', {}, random.Random(1))
    expected = cast(Mapping[str, str], question.expected)
    wrong = NAMING.grade(question, {**expected, 'target': 'V'})
    assert not wrong.correct
    assert wrong.score is not None
    assert 0 < wrong.score < 1
    assert 'resolves to the chord it tonicizes' in wrong.detail


def test_augmented_sixth_feedback_names_the_spelling() -> None:
    details = set()
    for tonic_seed in range(30):
        question = NAMING.generate(
            'chromatic.name.major.Ger+6', {'max-accidentals': 4}, random.Random(tonic_seed)
        )
        feedback = NAMING.grade(question, question.expected)
        details.add('doubly augmented fourth' in feedback.detail)
    assert details == {True, False}


# Writing ----------------------------------------------------------------------------------


def _context(question_details: Mapping[str, str]) -> Context:
    key = Key.parse(question_details['key'])
    numerals = question_details['numerals'].split('-')
    return Context(key, chords_of(numerals, key), keys=function_keys(numerals, key))


@pytest.mark.parametrize('item', WRITING.items({'mode': 'both'}))
def test_model_answers_are_correct(item: str) -> None:
    for seed in range(3):
        question = WRITING.generate(item, {'mode': 'both'}, random.Random(seed))
        expected = cast(tuple[Voicing, ...], question.expected)
        assert errors(check(expected, _context(question.details))) == []
        assert WRITING.grade(question, expected).correct
        answer = question.answer
        assert isinstance(answer, StaffInputAnswer)
        assert answer.labels[-1] in ('I', 'i')


def test_the_german_sixth_may_be_written_with_sharp_two_in_major() -> None:
    settings = {'mode': 'major', 'task': 'upper'}
    question = WRITING.generate('chromatic.write.Ger+6', settings, random.Random(3))
    key = Key.parse(question.details['key'])
    expected = cast(tuple[Voicing, ...], question.expected)
    bass = [c[BASS] for c in expected]
    numerals = ['I', 'Ger+6(#2)', 'Cad64', 'V', 'I']
    sharp = realize(numerals, key, random.Random(0), bass=bass)
    assert any(p.name.alter > key.signature.alter_for(p.letter) for p in sharp[1])
    assert WRITING.grade(question, sharp).correct


def test_a_neapolitan_whose_root_rises_is_an_error() -> None:
    settings = {'mode': 'minor', 'task': 'upper'}
    question = WRITING.generate('chromatic.write.N6', settings, random.Random(0))
    key = Key.parse(question.details['key'])
    chords = [list(c) for c in cast(tuple[Voicing, ...], question.expected)]
    root = RomanNumeral.parse('N6').realize(key).root
    voice = next(v for v in (SOPRANO, ALTO, TENOR) if chords[1][v].name == root)
    flat = chords[1][voice]
    chords[2][voice] = Pitch(flat.letter, flat.alter + 1, flat.octave)  # ♭2̂ rises to ♮2̂
    given = tuple((c[0], c[1], c[2], c[3]) for c in chords)
    found = check(given, _context(question.details))
    assert (Rule.CHROMATIC_TONE, Severity.ERROR) in {(v.rule, v.severity) for v in found}
    feedback = WRITING.grade(question, given)
    assert not feedback.correct
    assert feedback.figure is not None
