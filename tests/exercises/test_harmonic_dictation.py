# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Harmonic Dictation: items, chips, the phrases played and grading."""

from __future__ import annotations

import random

import pytest

from etude.core import Key, Mode, RomanNumeral
from etude.exercises.base import (
    ChipGroup,
    ChipsAnswer,
    Option,
    Question,
    shuffle_options,
)
from etude.exercises.families.harmonic_dictation import (
    GROUPS,
    Group,
    HarmonicDictation,
    chip_label,
    chord_key,
    dictation_item,
    group_chords,
    parse_item,
    vocabulary,
)
from etude.exercises.families.harmony import satb_voices
from etude.notation.spec import Ink, SystemSpec

DICTATION = HarmonicDictation()
ITEMS = [dictation_item(mode, group) for mode, groups in GROUPS.items() for group in groups]


def _numerals(question: Question) -> list[RomanNumeral]:
    return [RomanNumeral.parse(t) for t in question.details['numerals'].split('|')]


def test_items_follow_the_settings() -> None:
    default = DICTATION.items(DICTATION.default_settings())
    assert default == ITEMS
    assert len(default) == 11
    assert 'harmonic.dictation.minor.mixture' not in default
    minor = DICTATION.items({'mode': 'minor', 'groups': ('neapolitan', 'augmented-sixth')})
    assert minor == [
        'harmonic.dictation.minor.neapolitan',
        'harmonic.dictation.minor.augmented-sixth',
    ]
    # Mode mixture alone in minor keys falls back to every minor group.
    fallback = DICTATION.items({'mode': 'minor', 'groups': ('mixture',)})
    assert fallback == [i for i in ITEMS if '.minor.' in i]
    assert parse_item('harmonic.dictation.major.secondary-v') == (Mode.MAJOR, Group.SECONDARY_OF_V)
    with pytest.raises(ValueError, match='no mixture dictation in minor'):
        parse_item('harmonic.dictation.minor.mixture')


def test_secondary_groups_split_by_target() -> None:
    of_v = {c.id for c in group_chords(Group.SECONDARY_OF_V, Mode.MAJOR)}
    assert of_v == {'V/V', 'V7/V', 'viio7/V', 'viiø7/V'}
    others = {c.id for c in group_chords(Group.SECONDARY, Mode.MINOR)}
    assert others == {'V/iv', 'V7/iv', 'viio7/iv', 'V7/VI'}
    assert group_chords(Group.DIATONIC, Mode.MAJOR) == ()


@pytest.mark.parametrize(
    ('numeral', 'key', 'label'),
    [
        ('V65', 'V7', 'V7'),
        ('V6', 'V', 'V'),
        ('V65/V', 'V7/V', 'V7/V'),
        ('viio43/V', 'viio7/V', 'vii°7/V'),
        ('viiø7/V', 'viiø7/V', 'viiø7/V'),
        ('iio6', 'iio', 'ii°'),
        ('bVI', 'bVI', '♭VI'),
        ('Cad64', 'Cad64', 'Cad6/4'),
        ('N6', 'N', 'N'),
        ('Ger+6', 'Ger+6', 'Ger+6'),
        ('Ger+6(#2)', 'Ger+6', 'Ger+6'),
        ('It+6', 'It+6', 'It+6'),
    ],
)
def test_chips_are_numerals_without_figures(numeral: str, key: str, label: str) -> None:
    assert chord_key(RomanNumeral.parse(numeral)) == key
    assert chip_label(key) == label


def test_vocabularies_are_fixed_per_item() -> None:
    assert vocabulary(Group.DIATONIC, Mode.MAJOR) == (
        'I',
        'ii',
        'iii',
        'IV',
        'Cad64',
        'V',
        'V7',
        'vi',
        'viio',
    )
    assert vocabulary(Group.NEAPOLITAN, Mode.MINOR) == ('i', 'iv', 'Cad64', 'V', 'N', 'viio7/V')
    assert set(vocabulary(Group.AUGMENTED_SIXTH, Mode.MAJOR)) >= {'It+6', 'Fr+6', 'Ger+6', 'iv'}


@pytest.mark.parametrize('item', ITEMS)
def test_questions_ask_every_chord_after_the_tonic(item: str) -> None:
    mode, group = parse_item(item)
    words = vocabulary(group, mode)
    for seed in range(12):
        question = DICTATION.generate(item, DICTATION.default_settings(), random.Random(seed))
        numerals = _numerals(question)
        key = Key.parse(question.details['key'])
        assert key.mode is mode
        assert 3 <= len(numerals) <= 6
        assert chord_key(numerals[0]) == ('I' if mode is Mode.MAJOR else 'i')
        assert question.details['first'] == chord_key(numerals[0])
        answer = question.answer
        assert isinstance(answer, ChipsAnswer)
        assert [g.key for g in answer.groups] == [str(i) for i in range(2, len(numerals) + 1)]
        assert all([o.key for o in g.options] == list(words) for g in answer.groups)
        assert question.expected == {str(i + 1): chord_key(n) for i, n in enumerate(numerals) if i}
        # The written alternative is the phrase played, chord for chord.
        voicings = satb_voices(question.written_alternative)
        assert len(voicings) == len(numerals)
        for voicing, numeral in zip(voicings, numerals, strict=True):
            assert {p.name for p in voicing} <= set(numeral.realize(key).names())
        if group is not Group.DIATONIC:
            chromatic = {chord_key(c.numeral) for c in group_chords(group, mode)}
            assert chromatic & set(question.expected.values()), 'the chord the item is about'


def test_the_bass_is_given_on_request() -> None:
    item = 'harmonic.dictation.minor.neapolitan'
    plain = DICTATION.generate(item, {}, random.Random(4))
    given = DICTATION.generate(item, {'bass': True}, random.Random(4))
    assert plain.context.startswith('Key: ')
    assert 'chord 1: i' in plain.context
    assert 'bass' not in plain.context
    notes = given.context.rsplit(' · bass ', 1)[1].split('–')
    assert len(notes) == len(satb_voices(given.figure))
    assert DICTATION.describe_settings({'bass': True, 'groups': ('neapolitan',)}) == (
        'Neapolitan sixth · Major and minor keys · bass given'
    )


def test_grading_scores_each_chord_and_marks_the_wrong_ones() -> None:
    question = DICTATION.generate('harmonic.dictation.minor.neapolitan', {}, random.Random(4))
    expected = dict(question.expected)  # type: ignore[call-overload]
    assert DICTATION.grade(question, expected).score == 1
    slot = next(iter(expected))
    wrong = {**expected, slot: 'V7' if expected[slot] != 'V7' else 'V'}
    feedback = DICTATION.grade(question, wrong)
    assert not feedback.correct
    assert feedback.score == pytest.approx(1 - 1 / len(expected))
    labels = [chip_label(chord_key(n)) for n in _numerals(question)]
    assert feedback.title.startswith('Not quite — the phrase is i–')
    assert f'Chord {slot} is ' in feedback.detail
    assert 'the bass moves' in feedback.detail
    figure = feedback.figure
    assert isinstance(figure, SystemSpec)
    bass = figure.staves[1].voices[0]
    marked = [e for e in bass if getattr(e, 'label', None)]
    assert len(marked) == len(labels)
    accent = [i for i, e in enumerate(marked) if e.ink is Ink.ACCENT]
    assert accent == [int(slot) - 1]
    assert DICTATION.answer_label(question, wrong).startswith('i–')
    assert DICTATION.answer_label(question, {}).count('?') == len(expected)


def test_many_mistakes_are_summarised() -> None:
    question = DICTATION.generate('harmonic.dictation.major.diatonic', {}, random.Random(1))
    blank = {k: 'iii' if v != 'iii' else 'ii' for k, v in question.expected.items()}  # type: ignore[union-attr]
    feedback = DICTATION.grade(question, blank)
    assert feedback.score == 0
    if len(blank) > 3:
        assert 'more chord' in feedback.detail


def test_rows_of_the_same_chips_are_shuffled_alike() -> None:
    chips = tuple(Option(k, k) for k in ('I', 'ii', 'IV', 'V', 'vi'))
    other = tuple(Option(k, k) for k in ('a', 'b', 'c'))
    groups = (ChipGroup('2', 'Chord 2', chips), ChipGroup('3', 'Chord 3', chips))
    question = Question(
        exercise_id='x',
        item_id='x.y',
        prompt='?',
        answer=ChipsAnswer((*groups, ChipGroup('z', 'Other', other))),
        expected={'2': 'I', '3': 'V', 'z': 'a'},
    )
    orders = set()
    for seed in range(20):
        shown = shuffle_options(question, random.Random(seed)).answer
        assert isinstance(shown, ChipsAnswer)
        first, second, third = shown.groups
        assert first.options == second.options
        assert sorted(o.key for o in third.options) == ['a', 'b', 'c']
        orders.add(tuple(o.key for o in first.options))
    assert len(orders) > 1
