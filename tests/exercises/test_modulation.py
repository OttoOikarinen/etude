# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Modulation and Sequences: keys, pivots, analysis and the chords clicked on the staff."""

from __future__ import annotations

import random

import pytest

from etude.checkers.phrases import SequenceKind, key_relation
from etude.core import Key
from etude.exercises.base import ChoiceAnswer
from etude.exercises.families.harmony import satb_voices
from etude.exercises.families.modulation import (
    Modulation,
    Sequences,
    chord_events,
    relation_text,
)
from etude.notation.layout import layout
from etude.notation.smufl import FontMetrics
from etude.notation.spec import Barline, BarStyle, SystemSpec
from etude.notation.spec import Chord as StaffChord

MODULATION = Modulation()
SEQUENCES = Sequences()


def test_relations_are_named() -> None:
    assert relation_text(Key.parse('C'), 'V') == 'V · dominant'
    assert relation_text(Key.parse('C'), 'vi') == 'vi · relative minor'
    assert relation_text(Key.parse('c'), 'III') == 'III · relative major'
    assert relation_text(Key.parse('C'), 'bVI') == '♭VI · chromatic mediant'
    assert relation_text(Key.parse('C'), 'bII') == '♭II · Neapolitan'
    assert relation_text(Key.parse('c'), '#iv') == '♯iv'


def test_items_follow_the_settings() -> None:
    default = MODULATION.items(MODULATION.default_settings())
    assert 'modulation.key.major.pivot.V' in default
    assert 'modulation.key.major.common-tone.bVI' in default
    assert 'modulation.pivot.major.V' in default
    assert not any('enharmonic' in item for item in default)
    # The relative major of a minor key has no new accidental to find the pivot by.
    assert 'modulation.pivot.minor.III' not in default
    assert 'modulation.key.minor.pivot.III' in default
    enharmonic = MODULATION.items({'techniques': ('enharmonic',), 'mode': 'minor'})
    assert enharmonic == [
        'modulation.key.minor.enharmonic-dim7',
        'modulation.key.minor.enharmonic-ger6',
    ]
    # Common tones from minor keys and the pivot question alone fall back to pivots.
    fallback = MODULATION.items(
        {'techniques': ('common-tone',), 'mode': 'minor', 'questions': ('key',)}
    )
    assert fallback
    assert all(item.startswith('modulation.key.minor.pivot.') for item in fallback)


def _last_chord_root(figure: object) -> str:
    return str(min(satb_voices(figure)[-1]).name)


@pytest.mark.parametrize(
    'item',
    [
        'modulation.key.major.pivot.V',
        'modulation.key.major.pivot.ii',
        'modulation.key.minor.pivot.III',
        'modulation.key.minor.direct.v',
        'modulation.key.major.common-tone.bVI',
        'modulation.key.major.enharmonic-dim7',
        'modulation.key.minor.enharmonic-ger6',
    ],
)
def test_the_phrase_ends_in_the_key_to_name(item: str) -> None:
    for seed in range(4):
        question = MODULATION.generate(item, {}, random.Random(seed))
        home = Key.parse(question.details['home'])
        new = Key.parse(question.details['new'])
        assert question.expected == key_relation(home, new)
        assert _last_chord_root(question.figure) == str(new.tonic)
        answer = question.answer
        assert isinstance(answer, ChoiceAnswer)
        names = [o.label for o in answer.options]
        assert len(set(names)) == len(names)
        assert all(o.description for o in answer.options)
        feedback = MODULATION.grade(question, question.expected)
        assert feedback.correct
        assert 'Analysis:' in feedback.detail


def test_direct_modulations_show_the_phrase_break() -> None:
    question = MODULATION.generate('modulation.key.major.direct.V', {}, random.Random(0))
    figure = question.figure
    assert isinstance(figure, SystemSpec)
    bars = [e for e in figure.staves[0].events if isinstance(e, Barline)]
    assert [b.style for b in bars] == [BarStyle.DOUBLE, BarStyle.FINAL]


def test_the_pivot_is_clicked_on_the_staff() -> None:
    metrics = FontMetrics.bravura()
    for seed in range(4):
        question = MODULATION.generate('modulation.pivot.major.V', {}, random.Random(seed))
        answer = question.answer
        assert isinstance(answer, ChoiceAnswer)
        assert answer.in_figure_order
        figure = question.figure
        assert isinstance(figure, SystemSpec)
        events = chord_events(figure)
        display = layout(figure, metrics)
        expected = str(question.expected)
        # A click on any note of the pivot chord, on either staff, answers with it.
        clicked = {
            answer.targets[r.event]
            for r in display.hit_regions
            if r.event in answer.targets and events[r.event] == int(expected)
        }
        assert clicked == {expected}
        heads = [r for r in display.hit_regions if r.head is not None and r.event in answer.targets]
        assert {r.staff for r in heads} == {0, 1}
        # The first and last chords are never the pivot and are not offered.
        assert '0' not in {o.key for o in answer.options}
        assert all(o.fixed_accel for o in answer.options)


def test_pivot_feedback_shows_both_keys_under_the_pivot() -> None:
    for seed in range(6):
        question = MODULATION.generate('modulation.pivot.minor.v', {}, random.Random(seed))
        pivot = int(str(question.expected))
        feedback = MODULATION.grade(question, question.expected)
        assert feedback.correct
        figure = feedback.figure
        assert isinstance(figure, SystemSpec)
        bass = [e for e in figure.staves[1].voices[0] if isinstance(e, StaffChord)]
        labels = [e.label or '' for e in bass]
        assert len(labels[pivot].split('\n')) == 2
        assert labels[0] in ('i', 'I')
        assert labels[-1].split('\n')[-1] in ('I', 'i')
        # Slashed figures stay on their line: V6/5, not V6 over 5.
        assert all(not line.isdigit() for label in labels for line in label.split('\n'))
        wrong = MODULATION.grade(question, str(pivot - 1))
        assert not wrong.correct
        assert f'Chord {pivot + 1} is the pivot' in wrong.detail


def test_sequences_are_named_and_explained() -> None:
    items = SEQUENCES.items({'mode': 'minor'})
    assert items == ['sequence.minor.descending-fifths', 'sequence.minor.descending-5-6']
    for kind in SequenceKind:
        question = SEQUENCES.generate(f'sequence.major.{kind.value}', {}, random.Random(0))
        assert question.expected == kind.value
        answer = question.answer
        assert isinstance(answer, ChoiceAnswer)
        assert len(answer.options) == len(SequenceKind)
        feedback = SEQUENCES.grade(question, question.expected)
        assert feedback.correct
        assert question.details['labels'].split('|')[0] == 'I'
