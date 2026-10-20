# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random
from collections.abc import Mapping

import pytest

from etude.core import Chord, ChordQuality, FiguredBass, PitchName
from etude.core.roman import RomanNumeral
from etude.core.scale import Key, Mode
from etude.exercises.base import ChipsAnswer, Question
from etude.exercises.families.chords import INVERSIONS
from etude.exercises.families.figured_bass import (
    SLASH,
    FiguredBassExercise,
    _candidates,
    figures_for,
    parse_item,
)
from etude.exercises.families.harmony import keys_within
from etude.learning.model import ItemId
from etude.notation.spec import Chord as StaffChord
from etude.notation.spec import StaffSpec, SystemSpec

FB = FiguredBassExercise()
DEFAULTS = FB.default_settings()
ALL = {**DEFAULTS, 'mixture': True, 'slashed': True, 'max-accidentals': 7}


def chord(key: Key, text: str) -> Chord:
    return RomanNumeral.parse(text).realize(key)


@pytest.mark.parametrize(
    ('numeral', 'label'),
    [
        ('I', None),
        ('I6', '6'),
        ('I64', '6\n4'),
        ('V7', '7'),
        ('V65', '6\n5'),
        ('V43', '4\n3'),
        ('V42', '4\n2'),
        ('ii6', '6'),
        ('viiø7', '7'),
    ],
)
def test_figures_per_inversion(numeral: str, label: str | None) -> None:
    key = Key.parse('C')
    assert figures_for(chord(key, numeral), key).label() == label


@pytest.mark.parametrize(
    ('key_text', 'numeral', 'label', 'inline'),
    [
        # Minor keys raise the leading tone with ♯ (natural in the signature) ...
        ('a', 'V', '♯', '♯'),
        ('a', 'V7', '7\n♯', '7/♯'),
        ('a', 'viio6', '♯6', '♯6'),
        ('a', 'V43', '♯6\n4\n3', '♯6/4/3'),
        ('a', 'V42', '♯4\n2', '♯4/2'),
        ('a', 'viio65', '♯6\n5', '♯6/5'),
        ('a', 'viio42', '4\n♯2', '4/♯2'),
        ('a', 'V64', '♯6\n4', '♯6/4'),
        # ... or with ♮ when the signature flattens it.
        ('c', 'V', '♮', '♮'),
        ('c', 'V7', '7\n♮', '7/♮'),
        ('g', 'V', '♯', '♯'),
        # The raised note in the bass is written on the staff, not in the figures.
        ('a', 'V6', '6', '6'),
        ('c', 'viio7', '7', '7'),
    ],
)
def test_figures_with_accidentals(key_text: str, numeral: str, label: str, inline: str) -> None:
    key = Key.parse(key_text)
    figures = figures_for(chord(key, numeral), key)
    assert figures.label() == label
    assert figures.inline() == inline


def test_lowering_figures_for_borrowed_chords() -> None:
    key = Key.parse('C')
    minor = key.parallel
    assert figures_for(minor.triad(4), key).label() == '♭'  # iv: F A♭ C
    assert figures_for(minor.triad(2).with_inversion(1), key).label() == '6\n♭'  # ii°6
    assert figures_for(minor.seventh(2), key).label() == '7\n♭5'  # iiø7
    a_major = Key.parse('A')
    assert figures_for(a_major.parallel.triad(4), a_major).label() == '♮'  # iv: D F♮ A


def test_slashed_sixth() -> None:
    key = Key.parse('a')
    figures = figures_for(chord(key, 'viio6'), key)
    assert figures.label(slashed=True) == '6' + SLASH
    assert figures.ascii(slashed=True) == '6\\'
    assert figures.label() == '♯6'


def test_figures_realize_to_the_chord_in_every_key() -> None:
    """The written figures, read by :mod:`etude.core.figured_bass`, give the chord."""
    for key in keys_within(7, (Mode.MAJOR, Mode.MINOR)):
        for candidates in _candidates(key, True).values():
            for c in candidates:
                figures = figures_for(c, key)
                for slashed in (False, True):
                    upper = FiguredBass.parse(figures.ascii(slashed)).realize(c.bass, key)
                    assert set(upper) | {c.bass} == set(c.names()), (key, c)
                    assert all(abs(n.alter) <= 1 for n in c.names())


def test_items() -> None:
    items = list(FB.items(DEFAULTS))
    assert items[:2] == ['figbass.major.53', 'figbass.minor.53']
    assert 'figbass.minor.43.raised6' in items
    assert not any('lowered' in i for i in items)
    assert any('lowered' in i for i in FB.items(ALL))
    plain = FB.items({**DEFAULTS, 'accidentals': False, 'sevenths': False})
    assert [i.split('.', 2)[2] for i in plain if i.startswith('figbass.major')] == ['53', '6', '64']
    assert all('raised' not in i for i in FB.items({**DEFAULTS, 'mode': 'major'}))
    for item in FB.items(ALL):
        assert parse_item(item)
    with pytest.raises(ValueError, match='not a'):
        parse_item('figbass.major.43.raised6')  # raised leading tones are minor-key items


QUALITIES = {
    'major': ChordQuality.MAJOR,
    'minor': ChordQuality.MINOR,
    'dim': ChordQuality.DIMINISHED,
    'dom7': ChordQuality.DOMINANT_SEVENTH,
    'maj7': ChordQuality.MAJOR_SEVENTH,
    'min7': ChordQuality.MINOR_SEVENTH,
    'hdim7': ChordQuality.HALF_DIMINISHED_SEVENTH,
    'dim7': ChordQuality.DIMINISHED_SEVENTH,
}


def chord_from(answer: Mapping[str, str]) -> Chord:
    return Chord(
        PitchName.parse(answer['root']),
        QUALITIES[answer['quality']],
        INVERSIONS.index(answer['inversion']),
    )


def expected(question: Question) -> Mapping[str, str]:
    assert isinstance(question.expected, Mapping)
    return question.expected


def key_of(question: Question) -> Key:
    figure = question.figure
    assert isinstance(figure, StaffSpec)
    assert figure.key_signature is not None
    mode = parse_item(question.item_id)[0]
    signature = figure.key_signature
    return Key(signature.major_tonic if mode is Mode.MAJOR else signature.minor_tonic, mode)


def test_questions_show_the_figures_of_the_expected_chord() -> None:
    for item in FB.items(ALL):
        for seed in range(4):
            question = FB.generate(item, ALL, random.Random(seed))
            figure = question.figure
            assert isinstance(figure, StaffSpec)
            event = figure.events[0]
            assert isinstance(event, StaffChord)
            answer = expected(question)
            c = chord_from(answer)
            key = key_of(question)
            assert event.heads[0].pitch.name == c.bass
            figures = figures_for(c, key)
            assert figures.segment == parse_item(item)[1]
            assert event.label in (figures.label(), figures.label(slashed=True))
            # The bass staff's description names the figures, not the chord.
            assert figure.description is not None
            assert 'inversion' not in figure.description
            assert (figures.inline() or 'without figures') in figure.description or SLASH in (
                event.label or ''
            )


def test_answer_groups() -> None:
    question = FB.generate(ItemId('figbass.minor.43.raised6'), DEFAULTS, random.Random(0))
    assert isinstance(question.answer, ChipsAnswer)
    root, quality, inversion = question.answer.groups
    assert root.accidentals
    assert len(quality.options) == 8
    assert [o.key for o in inversion.options] == list(INVERSIONS)
    triads = FB.generate(
        ItemId('figbass.major.6'), {**DEFAULTS, 'sevenths': False}, random.Random(0)
    )
    assert isinstance(triads.answer, ChipsAnswer)
    assert len(triads.answer.groups[1].options) == 3
    assert len(triads.answer.groups[2].options) == 3


def find(item: str, key: Key, settings: Mapping[str, object] = ALL) -> Question:
    for seed in range(400):
        question = FB.generate(ItemId(item), settings, random.Random(seed))
        if key_of(question) == key:
            return question
    raise AssertionError(f'no question for {item} in {key}')


def test_explanation_of_a_raised_sixth() -> None:
    question = find('figbass.minor.65.raised6', Key.parse('c'), {**ALL, 'slashed': False})
    feedback = FB.grade(question, expected(question))
    assert feedback.correct
    assert feedback.title == 'Correct — B diminished seventh, first inversion'
    assert 'Under D, the figures ♮6/5 mean a sixth, a fifth and a third above the bass: ' in (
        feedback.detail
    )
    assert 'B, A♭, F' in feedback.detail
    assert '♮ raises the sixth above the bass from B♭ to B.' in feedback.detail
    assert 'In thirds: B–D–F–A♭, B diminished seventh in first inversion.' in feedback.detail
    assert 'In C minor that is vii°6/5.' in feedback.detail


def test_explanation_of_a_lone_accidental_and_no_figures() -> None:
    question = find('figbass.minor.53.raised3', Key.parse('a'))
    detail = FB.grade(question, expected(question)).detail
    assert '♯ raises the third above the bass from G to G♯.' in detail
    assert 'An accidental on its own belongs to the third.' in detail
    assert 'In A minor that is V.' in detail
    sixth = find('figbass.major.6', Key.parse('C'))
    assert 'the figure 6 means a sixth and a third above the bass' in (
        FB.grade(sixth, expected(sixth)).detail
    )
    plain = find('figbass.major.53', Key.parse('C'))
    assert 'With no figures' in FB.grade(plain, expected(plain)).detail


def test_explanation_of_a_bass_accidental_and_a_slashed_six() -> None:
    question = find('figbass.minor.6', Key.parse('a'), {**ALL, 'sevenths': False})
    detail = FB.grade(question, expected(question)).detail
    if expected(question)['root'] == 'E':  # V6, with G♯ in the bass
        assert 'The accidental of the bass, G♯, is written on the staff' in detail
    for seed in range(40):
        slashed = FB.generate(ItemId('figbass.minor.6.raised6'), ALL, random.Random(seed))
        event = slashed.figure.events[0]  # type: ignore[union-attr]
        if SLASH in (event.label or ''):  # type: ignore[union-attr]
            assert 'The slashed 6 raises the sixth, like ♯6' in FB.grade(slashed, None).detail
            break
    else:
        raise AssertionError('no slashed sixth')


def test_wrong_answer_feedback_and_realization() -> None:
    question = find('figbass.major.64', Key.parse('C'))
    answer = dict(expected(question))
    wrong = {**answer, 'inversion': 'root'}
    feedback = FB.grade(question, wrong)
    assert not feedback.correct
    assert feedback.score == pytest.approx(2 / 3)
    assert 'the bass is the root only under 5/3 and 7' in feedback.detail
    figure = feedback.figure
    assert isinstance(figure, SystemSpec)
    upper = figure.staves[0].events[0]
    assert isinstance(upper, StaffChord)
    bass = figure.staves[1].events[0]
    assert isinstance(bass, StaffChord)
    assert bass.label == '6\n4'
    names = {h.pitch.name for h in upper.heads} | {bass.heads[0].pitch.name}
    assert names == set(chord_from(answer).names())


def test_labels_and_confusables() -> None:
    assert FB.item_label(ItemId('figbass.minor.43.raised6')) == 'Figures ♯6/4/3 in minor'
    assert FB.item_label(ItemId('figbass.major.53')) == 'Figures 5/3 in major'
    assert FB.confusables(ItemId('figbass.major.43'))[0] == 'figbass.major.42'
    assert FB.confusables(ItemId('figbass.minor.7.raised3'))[0] == 'figbass.minor.7'
    assert FB.describe_settings(DEFAULTS) == (
        'Major and minor keys · triads and sevenths · accidentals · up to 4 accidentals'
    )
