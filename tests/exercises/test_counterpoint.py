# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Counterpoint writing and errors: the musical facts behind the questions."""

from __future__ import annotations

import random
from fractions import Fraction

import pytest

from etude.checkers.cantus import signature
from etude.checkers.counterpoint import Rule, Severity, Species, check, errors
from etude.core import Interval, Meter, NoteValue, Pitch
from etude.exercises.base import ChoiceAnswer, StaffInputAnswer
from etude.exercises.families.counterpoint import (
    MAX_LISTED,
    MISTAKES,
    CounterpointErrors,
    CounterpointWriting,
    counterpoint_range,
    passage_of,
)
from etude.notation.spec import Chord, Ink, SystemSpec

WRITING = CounterpointWriting()
ERRORS = CounterpointErrors()


def chords(figure: SystemSpec, staff: int) -> list[Chord]:
    return [e for e in figure.staves[staff].events if isinstance(e, Chord)]


def test_items_in_teaching_order_and_settings() -> None:
    items = list(WRITING.items(WRITING.default_settings()))
    assert items[:3] == [
        'counterpoint.write.1.above',
        'counterpoint.write.1.below',
        'counterpoint.write.2.above',
    ]
    assert len(items) == 10
    only = WRITING.items({**WRITING.default_settings(), 'species': ('4',), 'position': 'below'})
    assert only == ['counterpoint.write.4.below']
    assert WRITING.item_label(items[2]) == 'Second species above'
    assert WRITING.confusables(items[2]) == ['counterpoint.write.2.below']
    assert [str(i) for i in ERRORS.items(ERRORS.default_settings())] == [
        f'counterpoint.error.{m.key}' for m in MISTAKES
    ]


@pytest.mark.parametrize('species', list(Species))
@pytest.mark.parametrize('above', [True, False])
def test_writing_questions(species: Species, above: bool) -> None:
    item = f'counterpoint.write.{species.value}.{"above" if above else "below"}'
    for seed in range(3):
        question = WRITING.generate(item, WRITING.default_settings(), random.Random(seed))
        answer = question.answer
        assert isinstance(answer, StaffInputAnswer)
        passage = passage_of(question.details)
        cp, cf = (0, 1) if above else (1, 0)
        assert answer.staves == (answer.clef, answer.staves[1])
        assert answer.given_voices == {cf: passage.cantus}
        assert answer.voice_rhythms[cp] == passage.rhythm.notes
        assert all(d.value is NoteValue.WHOLE for d in answer.voice_rhythms[cf])
        assert answer.meter == Meter(2, 2)
        assert answer.key_signature == signature(passage.mode)
        assert answer.voice_names[cp] == 'Counterpoint'
        assert answer.voice_names[cf] == 'Cantus firmus'
        # The model answer is correct, in the counterpoint's range, on the right side.
        assert not errors(check(passage.cantus, passage.line, passage.context))
        low, high = counterpoint_range(passage.cantus, above)
        assert all(low.midi <= p.midi <= high.midi for p in passage.line)
        if species is Species.FOURTH:
            assert passage.rhythm.rest is not None, 'the syncopation starts after a rest'
            assert sum(passage.rhythm.tied()) >= len(passage.cantus) - 4
        assert question.figure is None, 'the cantus is printed in the answer staff'
        assert question.playback is not None
        assert 'species' in question.context


def test_correct_answer_is_marked_in_success_ink() -> None:
    question = WRITING.generate('counterpoint.write.1.above', {}, random.Random(4))
    feedback = WRITING.grade(question, question.expected)
    assert feedback.correct
    assert feedback.score == 1.0
    assert isinstance(feedback.figure, SystemSpec)
    assert all(h.ink is Ink.SUCCESS for c in chords(feedback.figure, 0) for h in c.heads)
    assert feedback.play_given is not None
    assert feedback.play_expected is not None
    assert feedback.expected_label.startswith('A model answer: ')


def test_mistakes_are_marked_and_explained() -> None:
    question = WRITING.generate('counterpoint.write.1.above', {}, random.Random(5))
    passage = passage_of(question.details)
    # The counterpoint in parallel octaves with the cantus: a string of errors.
    octave = Interval.parse('P8')
    line = tuple(p.transpose(octave) for p in passage.cantus)
    feedback = WRITING.grade(question, (line, passage.cantus))
    assert not feedback.correct
    assert feedback.score is not None
    assert feedback.score < 0.5
    assert feedback.title.startswith('Not quite — ')
    assert 'Parallel octaves' in feedback.detail
    assert 'And ' in feedback.detail, 'only the first mistakes are spelled out'
    assert feedback.detail.count('.') >= MAX_LISTED
    figure = feedback.figure
    assert isinstance(figure, SystemSpec)
    notes = chords(figure, 0)
    assert any(h.ink is Ink.ERROR for c in notes for h in c.heads)
    labels = [c.label for c in notes if c.label]
    assert labels, 'mistakes carry a written mark, not colour alone'
    assert len(labels) <= MAX_LISTED
    assert all(c.ink is Ink.ERROR for c in notes if c.label)
    assert figure.description is not None
    assert 'Parallel octaves' in figure.description


def test_changing_the_cantus_or_leaving_notes_out_is_wrong() -> None:
    question = WRITING.generate('counterpoint.write.2.below', {}, random.Random(1))
    upper, lower = question.expected
    changed = ((*upper[:-1], upper[-1].transpose(Interval.parse('M2'))), lower)
    assert 'cantus firmus' in WRITING.grade(question, changed).title
    assert 'every note' in WRITING.grade(question, (upper, lower[:-1])).title


def test_fifth_species_rhythms_vary_and_end_with_the_cadence() -> None:
    rhythms = set()
    for seed in range(8):
        question = WRITING.generate('counterpoint.write.5.above', {}, random.Random(seed))
        passage = passage_of(question.details)
        rhythms.add(passage.rhythm)
        onsets = passage.rhythm.onsets
        assert onsets[-1] == len(passage.cantus) - 1
        assert passage.rhythm.tied()[-3]
        assert onsets[-2] == len(passage.cantus) - Fraction(3, 2)
    assert len(rhythms) > 4


def test_mode_and_accidental_settings() -> None:
    settings = {**WRITING.default_settings(), 'modes': ('phrygian',), 'max-accidentals': 0}
    for seed in range(4):
        question = WRITING.generate('counterpoint.write.1.below', settings, random.Random(seed))
        passage = passage_of(question.details)
        assert str(passage.mode) == 'E phrygian'
        assert passage.cantus[-1].name == passage.mode.tonic


@pytest.mark.parametrize('mistake', MISTAKES, ids=lambda m: m.key)
def test_each_mistake_is_the_only_error(mistake: object) -> None:
    from etude.exercises.families.counterpoint import Mistake

    assert isinstance(mistake, Mistake)
    item = f'counterpoint.error.{mistake.key}'
    for seed in range(4):
        question = ERRORS.generate(item, ERRORS.default_settings(), random.Random(seed))
        passage = passage_of(question.details)
        assert passage.species in mistake.species
        found = errors(check(passage.cantus, passage.line, passage.context))
        assert [v.rule for v in found] == [mistake.rule]
        answer = question.answer
        assert isinstance(answer, ChoiceAnswer)
        assert len({o.accel for o in answer.options}) == len(answer.options) == len(MISTAKES)
        assert isinstance(question.figure, SystemSpec)
        description = question.figure.description or ''
        assert 'Counterpoint' in description
        assert all(m.message not in description for m in found), 'no answer in the text'


def test_errors_feedback_marks_the_mistake() -> None:
    question = ERRORS.generate('counterpoint.error.parallel-fifths', {}, random.Random(2))
    right = ERRORS.grade(question, 'parallel-fifths')
    assert right.correct
    assert right.title == 'Correct — Parallel fifths'
    wrong = ERRORS.grade(question, 'unison')
    assert not wrong.correct
    assert 'Parallel fifths' in wrong.title
    figure = wrong.figure
    assert isinstance(figure, SystemSpec)
    passage = passage_of(question.details)
    staff = 0 if passage.above else 1
    marked = [c for c in chords(figure, staff) if c.label]
    assert [c.label for c in marked] == ['∥5']
    assert any(h.ink is Ink.ERROR for c in chords(figure, staff) for h in c.heads)
    assert 'Fifths' in wrong.detail or 'fifths' in wrong.detail


def test_leading_tone_mistake_uses_a_mode_with_ficta() -> None:
    settings = {**ERRORS.default_settings(), 'modes': ('ionian',)}
    question = ERRORS.generate('counterpoint.error.leading-tone', settings, random.Random(0))
    passage = passage_of(question.details)
    assert passage.mode.type.value in ('dorian', 'mixolydian', 'aeolian')
    found = check(passage.cantus, passage.line, passage.context)
    assert [v.rule for v in found if v.severity is Severity.ERROR] == [Rule.LEADING_TONE]


def test_passage_details_round_trip() -> None:
    question = WRITING.generate('counterpoint.write.4.below', {}, random.Random(3))
    passage = passage_of(question.details)
    assert passage.details() == question.details
    assert isinstance(Pitch.parse(question.details['cantus'].split()[0]), Pitch)
