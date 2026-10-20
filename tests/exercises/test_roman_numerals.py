# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random
from collections.abc import Mapping

import pytest

from etude.core import Chord, ChordQuality, PitchName
from etude.core.roman import RomanNumeral
from etude.core.scale import Key, Mode
from etude.exercises.base import ChipsAnswer, Question
from etude.exercises.families.roman_numerals import (
    RomanNumerals,
    chord_in_figure,
    item_id,
    parse_item,
)
from etude.learning.model import ItemId
from etude.notation.spec import StaffSpec, SystemSpec

RN = RomanNumerals()
DEFAULTS = RN.default_settings()
EVERYTHING = {**DEFAULTS, 'mode': 'both', 'sevenths': 'all', 'max-accidentals': 7}
Q = ChordQuality


def key_of(question: Question) -> Key:
    figure = question.figure
    signature = (
        figure.staves[0].key_signature if isinstance(figure, SystemSpec) else figure.key_signature
    )
    assert signature is not None
    mode = parse_item(question.item_id)[0]
    tonic = signature.major_tonic if mode is Mode.MAJOR else signature.minor_tonic
    return Key(tonic, mode)


def expected(question: Question) -> Mapping[str, str]:
    assert isinstance(question.expected, Mapping)
    return question.expected


def test_item_ids_round_trip() -> None:
    assert item_id(Mode.MAJOR, 5, True, 1) == 'roman.major.V7.65'
    assert item_id(Mode.MINOR, 2, True, 0) == 'roman.minor.iiø7.7'
    assert item_id(Mode.MINOR, 7, False, 1) == 'roman.minor.viio.6'
    assert item_id(Mode.MAJOR, 1, True, 3) == 'roman.major.IM7.42'
    assert item_id(Mode.MINOR, 3, False, 0) == 'roman.minor.III.53'
    for item in RN.items(EVERYTHING):
        assert item_id(*parse_item(item)) == item
    for bad in ('roman.major.V.7', 'roman.dorian.I.53', 'roman.major.VII.53', 'roman.minor.v.53'):
        with pytest.raises(ValueError, match='not a'):
            parse_item(bad)


def test_teaching_order() -> None:
    items = list(RN.items(DEFAULTS))
    assert items[:3] == ['roman.major.I.53', 'roman.major.IV.53', 'roman.major.V.53']
    assert items.index('roman.major.I.6') < items.index('roman.major.ii.53')
    assert items.index('roman.major.vi.64') < items.index('roman.major.V7.7')
    assert not any('ii7' in i for i in items)  # default: only V7 among the sevenths
    every = list(RN.items(EVERYTHING))
    assert every.index('roman.major.V7.42') < every.index('roman.major.ii7.7')
    assert 'roman.minor.viio7.42' in every


def test_settings_limit_items() -> None:
    triads = RN.items({**DEFAULTS, 'sevenths': 'none'})
    assert all(i.split('.')[3] in ('53', '6', '64') for i in triads)
    root = RN.items({**EVERYTHING, 'inversions': False})
    assert {i.split('.')[3] for i in root} == {'53', '7'}
    assert all(i.startswith('roman.minor.') for i in RN.items({**DEFAULTS, 'mode': 'minor'}))


# The diatonic numerals of Kostka & Payne, with the qualities they stand for.
MAJOR = {
    'I': Q.MAJOR, 'ii': Q.MINOR, 'iii': Q.MINOR, 'IV': Q.MAJOR, 'V': Q.MAJOR, 'vi': Q.MINOR,
    'viio': Q.DIMINISHED, 'IM7': Q.MAJOR_SEVENTH, 'ii7': Q.MINOR_SEVENTH,
    'iii7': Q.MINOR_SEVENTH, 'IVM7': Q.MAJOR_SEVENTH, 'V7': Q.DOMINANT_SEVENTH,
    'vi7': Q.MINOR_SEVENTH, 'viiø7': Q.HALF_DIMINISHED_SEVENTH,
}  # fmt: skip
MINOR = {
    'i': Q.MINOR, 'iio': Q.DIMINISHED, 'III': Q.MAJOR, 'iv': Q.MINOR, 'V': Q.MAJOR,
    'VI': Q.MAJOR, 'viio': Q.DIMINISHED, 'i7': Q.MINOR_SEVENTH,
    'iiø7': Q.HALF_DIMINISHED_SEVENTH, 'IIIM7': Q.MAJOR_SEVENTH, 'iv7': Q.MINOR_SEVENTH,
    'V7': Q.DOMINANT_SEVENTH, 'VIM7': Q.MAJOR_SEVENTH, 'viio7': Q.DIMINISHED_SEVENTH,
}  # fmt: skip


def test_items_cover_the_diatonic_numerals_of_both_modes() -> None:
    items = RN.items(EVERYTHING)
    for mode, table in (('major', MAJOR), ('minor', MINOR)):
        numerals = {i.split('.')[2] for i in items if i.split('.')[1] == mode}
        assert numerals == set(table)


@pytest.mark.parametrize('voicing', ['close', 'satb'])
def test_written_chord_is_the_numeral_in_the_key(voicing: str) -> None:
    settings = {**EVERYTHING, 'voicing': voicing}
    for item in RN.items(settings):
        mode, degree, _seventh, inversion = parse_item(item)
        table = MAJOR if mode is Mode.MAJOR else MINOR
        for seed in range(3):
            question = RN.generate(item, settings, random.Random(seed))
            key = key_of(question)
            chord = chord_in_figure(question.figure)
            numeral = item.split('.')[2]
            assert chord.quality is table[numeral], item
            assert chord.inversion == inversion
            assert chord.root == key.degree(degree) or (
                degree == 7 and chord.root == key.leading_tone
            )
            analysis = RomanNumeral.analyze(chord, key)
            assert analysis is not None
            assert analysis.degree == degree
            assert analysis.inversion == inversion
            assert RN.answer_label(question, expected(question)) in (
                analysis.symbol.replace('65', '6/5')
                .replace('64', '6/4')
                .replace('43', '4/3')
                .replace('42', '4/2'),
            )
            assert isinstance(question.figure, SystemSpec if voicing == 'satb' else StaffSpec)


def test_minor_numerals_use_the_raised_leading_tone() -> None:
    a_minor = Key.parse('a')
    g_sharp = PitchName.parse('G#')
    for text in ('V', 'V7', 'viio', 'viio7'):
        item = ItemId(f'roman.minor.{text}.{"7" if "7" in text else "53"}')
        for seed in range(20):
            question = RN.generate(item, {**DEFAULTS, 'max-accidentals': 0}, random.Random(seed))
            assert key_of(question) == a_minor
            assert g_sharp in chord_in_figure(question.figure).names()
    # III in minor is built on the natural minor: C major in A minor, not augmented.
    question = RN.generate(
        ItemId('roman.minor.III.53'), {**DEFAULTS, 'max-accidentals': 0}, random.Random(0)
    )
    assert chord_in_figure(question.figure) == Chord(PitchName.parse('C'), Q.MAJOR)


def test_answer_chips_and_labels() -> None:
    question = RN.generate(ItemId('roman.major.V7.65'), DEFAULTS, random.Random(1))
    assert isinstance(question.answer, ChipsAnswer)
    numerals, figures = question.answer.groups
    assert [o.label for o in numerals.options] == ['I', 'ii', 'iii', 'IV', 'V', 'vi', 'vii°']
    assert [o.label for o in figures.options] == [
        'None (5/3)', '6', '6/4', '7', '6/5', '4/3', '4/2'
    ]  # fmt: skip
    assert expected(question) == {'numeral': '5', 'figures': '65'}
    assert RN.answer_label(question, expected(question)) == 'V6/5'
    minor = RN.generate(
        ItemId('roman.minor.iio.6'), {**DEFAULTS, 'sevenths': 'none'}, random.Random(0)
    )
    assert isinstance(minor.answer, ChipsAnswer)
    assert [o.label for o in minor.answer.groups[0].options] == [
        'i', 'ii°', 'III', 'iv', 'V', 'VI', 'vii°'
    ]  # fmt: skip
    assert len(minor.answer.groups[1].options) == 3
    assert RN.answer_label(minor, expected(minor)) == 'ii°6'


def test_feedback_names_key_chord_and_inversion() -> None:
    settings = {**DEFAULTS, 'max-accidentals': 7, 'voicing': 'close'}
    for seed in range(200):
        question = RN.generate(ItemId('roman.major.V7.42'), settings, random.Random(seed))
        if key_of(question) == Key.parse('D'):
            break
    else:
        raise AssertionError('no question in D major')
    feedback = RN.grade(question, expected(question))
    assert feedback.correct
    assert feedback.title == 'Correct — V4/2'
    assert 'In D major, A–C♯–E–G (A dominant seventh)' in feedback.detail
    assert 'scale degree 5 (Dominant): V7' in feedback.detail
    assert 'The seventh, G, is in the bass, so the figures are 4/2: V4/2.' in feedback.detail
    wrong = RN.grade(question, {'numeral': '5', 'figures': '65'})
    assert not wrong.correct
    assert wrong.score == 0.5
    assert 'Figures count intervals above the bass' in wrong.detail
    assert wrong.title == 'Not quite — the answer is V4/2'


def test_feedback_figure_labels_the_numeral() -> None:
    for voicing in ('close', 'satb'):
        question = RN.generate(
            ItemId('roman.minor.viio.6'), {**DEFAULTS, 'voicing': voicing}, random.Random(3)
        )
        figure = RN.grade(question, expected(question)).figure
        staff = figure.staves[1] if isinstance(figure, SystemSpec) else figure
        assert isinstance(staff, StaffSpec)
        assert [getattr(e, 'label', None) for e in staff.events] == ['vii°6']


def test_confusables() -> None:
    assert 'roman.major.IV.53' in RN.confusables(ItemId('roman.major.ii.6'))
    assert 'roman.major.V.53' in RN.confusables(ItemId('roman.major.iii.6'))
    assert 'roman.major.ii.53' in RN.confusables(ItemId('roman.major.viio.6'))
    assert set(RN.confusables(ItemId('roman.major.V.6'))) >= {
        'roman.major.V.53',
        'roman.major.V.64',
        'roman.major.V7.65',
    }


def test_item_labels_and_settings_text() -> None:
    assert RN.item_label(ItemId('roman.major.V7.65')) == 'V6/5 in major'
    assert RN.item_label(ItemId('roman.minor.viio.53')) == 'vii° in minor'
    assert RN.describe_settings(DEFAULTS) == 'Major keys · triads and V7 · up to 4 accidentals'
