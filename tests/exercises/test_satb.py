# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Four-part writing and spot the error: the musical facts behind the questions."""

from __future__ import annotations

import random

import pytest

from etude.checkers.realize import chords_of
from etude.checkers.voice_leading import BASS, SOPRANO, Context, check, errors
from etude.core import Interval, Key, Pitch, RomanNumeral
from etude.exercises.base import ChoiceAnswer, StaffInputAnswer
from etude.exercises.families.harmony import roman_label
from etude.exercises.families.satb import (
    MAX_LISTED,
    MISTAKES,
    PROGRESSIONS,
    FourPartWriting,
    SpotTheError,
    passage_figure,
    passage_of,
    question_key,
    tonic_key,
)
from etude.notation.spec import Chord, Ink, SystemSpec

WRITING = FourPartWriting()
SPOTTING = SpotTheError()
P = Pitch.parse
C_MAJOR = {**WRITING.default_settings(), 'mode': 'major', 'max-accidentals': 0}


def heads(figure: SystemSpec) -> list[tuple[Pitch, Ink]]:
    found = []
    for staff in figure.staves:
        for line in (staff.events, *staff.voices):
            found += [(h.pitch, h.ink) for e in line if isinstance(e, Chord) for h in e.heads]
    return found


def test_items_go_from_triads_to_sevenths() -> None:
    items = list(WRITING.items(WRITING.default_settings()))
    assert items[0] == 'satb.write.I-V-I'
    assert items.index('satb.write.I-IV-V-I') < items.index('satb.write.V7-I')
    assert {'satb.write.ii6-V-I', 'satb.write.deceptive'} <= set(items)
    without = WRITING.items({**WRITING.default_settings(), 'sevenths': False})
    assert 'satb.write.V7-I' not in without
    assert all(len(p.major) in (3, 4, 5) and len(p.major) == len(p.minor) for p in PROGRESSIONS)


@pytest.mark.parametrize(
    ('numeral', 'label'),
    [('V65', 'V6/5'), ('viio6', 'vii°6'), ('Cad64', 'Cad6/4'), ('ii6', 'ii6'), ('iiø65', 'iiø6/5')],
)
def test_numeral_labels_read_back(numeral: str, label: str) -> None:
    parsed = RomanNumeral.parse(numeral)
    assert roman_label(parsed) == label
    key = Key.parse('G')
    assert RomanNumeral.parse(label).realize(key) == parsed.realize(key)


def test_tonic_key() -> None:
    assert tonic_key((P('C5'), P('G4'), P('E4'), P('C3'))) == Key.parse('C')
    assert tonic_key((P('C5'), P('C5'), P('Eb4'), P('C3'))) == Key.parse('c')
    assert tonic_key((P('B4'), P('F#4'), P('D4'), P('B2'))) == Key.parse('b')


@pytest.mark.parametrize('item', list(WRITING.items(WRITING.default_settings())))
def test_writing_questions(item: str) -> None:
    for seed in range(6):
        for task in ('inner', 'upper'):
            settings = {**WRITING.default_settings(), 'task': task}
            question = WRITING.generate(item, settings, random.Random(seed))
            answer = question.answer
            assert isinstance(answer, StaffInputAnswer)
            assert answer.voices == 4
            assert len(answer.staves) == 2
            assert set(answer.given_voices) == ({SOPRANO, BASS} if task == 'inner' else {BASS})
            key = question_key(question)
            assert key == tonic_key(question.expected[0])
            harmony = tuple(RomanNumeral.parse(label).realize(key) for label in answer.labels)
            assert errors(check(question.expected, Context(key, harmony))) == []
            assert answer.key_signature == key.signature
            assert WRITING.grade(question, question.expected).score == 1.0


def _broken(question, *, want_errors: bool):
    """A single changed note of the expected answer that has errors (or only warnings)."""
    answer = question.answer
    key = question_key(question)
    harmony = tuple(RomanNumeral.parse(label).realize(key) for label in answer.labels)
    for slot, chord in enumerate(question.expected):
        for voice in range(4):
            if voice in answer.given_voices:
                continue
            for name in harmony[slot].names():
                for octave in (3, 4, 5):
                    changed = list(chord)
                    changed[voice] = name.at(octave)
                    value = (
                        *question.expected[:slot],
                        tuple(changed),
                        *question.expected[slot + 1 :],
                    )
                    found = check(value, Context(key, harmony))
                    has_errors = bool(errors(found))
                    if has_errors == want_errors and (want_errors or found):
                        return value, found
    return None


def test_wrong_answers_are_marked_on_the_staff() -> None:
    question = WRITING.generate('satb.write.I-IV-V-I', C_MAJOR, random.Random(1))
    value, found = _broken(question, want_errors=True)
    feedback = WRITING.grade(question, value)
    assert not feedback.correct
    assert feedback.score is not None
    assert 0.0 <= feedback.score < 1.0
    for violation in errors(found)[:MAX_LISTED]:
        assert violation.message in feedback.detail
    assert isinstance(feedback.figure, SystemSpec)
    inks = [ink for _p, ink in heads(feedback.figure)]
    assert Ink.ERROR in inks
    assert feedback.play_given is not None
    assert feedback.play_expected is not None


def test_warnings_are_shown_but_not_penalised() -> None:
    for seed in range(30):
        question = WRITING.generate('satb.write.I-IV-V-I', C_MAJOR, random.Random(seed))
        broken = _broken(question, want_errors=False)
        if broken is None:
            continue
        value, found = broken
        feedback = WRITING.grade(question, value)
        assert feedback.correct
        assert feedback.score == 1.0
        assert 'Worth noticing' in feedback.detail
        assert all(v.message in feedback.detail for v in found)
        return
    pytest.fail('no answer with only warnings found')


def test_printed_voices_and_malformed_answers() -> None:
    question = WRITING.generate('satb.write.V7-I', C_MAJOR, random.Random(2))
    chords = list(question.expected)
    first = list(chords[0])
    first[BASS] = first[BASS].transpose(Interval.parse('P8'), down=True)
    chords[0] = tuple(first)
    assert not WRITING.grade(question, tuple(chords)).correct
    assert not WRITING.grade(question, ()).correct
    assert not WRITING.grade(question, question.expected[:-1]).correct
    assert not WRITING.grade(question, tuple(c[:3] for c in question.expected)).correct


@pytest.mark.parametrize('mistake', MISTAKES, ids=lambda m: m.key)
def test_spot_the_error_has_exactly_one_mistake(mistake) -> None:
    for seed in range(5):
        question = SPOTTING.generate(
            f'satb.error.{mistake.key}', SPOTTING.default_settings(), random.Random(seed)
        )
        chords, labels = passage_of(question.figure)
        assert 2 <= len(chords) <= 4
        key = question_key(question)
        found = errors(check(chords, Context(key, chords_of(labels, key))))
        assert [v.rule for v in found] == [mistake.rule]
        if mistake.key == 'doubled-leading-tone':
            assert all(chords[found[0].slot][v].name == key.leading_tone for v in found[0].voices)
        assert isinstance(question.answer, ChoiceAnswer)
        assert question.expected == mistake.key
        feedback = SPOTTING.grade(question, mistake.key)
        assert feedback.correct
        assert found[0].message in feedback.detail
        marked = [p for p, ink in heads(feedback.figure) if ink is Ink.ERROR]
        assert marked, 'the mistake is marked on the staff'
        wrong = next(o.key for o in question.answer.options if o.key != mistake.key)
        assert not SPOTTING.grade(question, wrong).correct


def test_passage_figure_round_trip() -> None:
    chords = (
        (P('C5'), P('G4'), P('E4'), P('C3')),
        (P('B4'), P('G4'), P('D4'), P('G2')),
    )
    figure = passage_figure(chords, Key.parse('C'), ('I', 'V'))
    assert passage_of(figure) == (chords, ('I', 'V'))
    assert isinstance(figure, SystemSpec)
    upper, lower = figure.staves
    assert len(upper.voices) == 1
    assert len(lower.voices) == 1


def test_confusables_and_labels() -> None:
    assert WRITING.confusables('satb.write.deceptive') == ['satb.write.I-IV-V-I']
    assert 'Deceptive cadence' in WRITING.item_label('satb.write.deceptive')
    assert SPOTTING.confusables('satb.error.parallel-fifths') == ['satb.error.parallel-octaves']
    assert 'Parallel fifths' in SPOTTING.item_label('satb.error.parallel-fifths')
    with pytest.raises(ValueError, match='not a four-part writing item'):
        WRITING.item_label('satb.write.nonsense')


def _label_boxes(figure: SystemSpec) -> list[tuple[float, float, float, float]]:
    from etude.notation.displaylist import TextItem
    from etude.notation.layout import item_bounds, layout
    from etude.notation.smufl import FontMetrics

    metrics = FontMetrics.bravura()
    display = layout(figure, metrics)
    return [item_bounds(i, metrics) for i in display.items if isinstance(i, TextItem)]


def test_mistake_marks_never_overlap() -> None:
    """An answer full of mistakes (every voice a step off): the marks under the treble
    staff are capped to the listed mistakes, and no two labels overlap."""
    for seed in range(8):
        question = WRITING.generate('satb.write.I-vi-IV-V-I', C_MAJOR, random.Random(seed))
        answer = question.answer
        wrong = []
        for chord in question.expected:
            changed = list(chord)
            for voice in range(4):
                if voice not in answer.given_voices:
                    changed[voice] = Pitch.from_diatonic(
                        chord[voice].diatonic_index + 1, chord[voice].midi + 2
                    )
            wrong.append(tuple(changed))
        feedback = WRITING.grade(question, tuple(wrong))
        assert not feedback.correct
        figure = feedback.figure
        assert isinstance(figure, SystemSpec)
        marks = [e.label for e in figure.staves[0].events if isinstance(e, Chord) and e.label]
        assert 0 < len(' '.join(marks).split()) <= MAX_LISTED
        boxes = _label_boxes(figure)
        for i, (x0, y0, x1, y1) in enumerate(boxes):
            for a0, b0, a1, b1 in boxes[i + 1 :]:
                assert x1 <= a0 or a1 <= x0 or y1 <= b0 or b1 <= y0, 'labels overlap'
