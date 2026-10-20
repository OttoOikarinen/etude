# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import itertools
import random
from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from etude.core import Interval, Meter
from etude.core.scale import Mode
from etude.exercises.base import StaffInputAnswer
from etude.exercises.families.melodic_dictation import (
    GRAMMARS,
    MINOR,
    STEPS,
    VOCABULARY,
    MelodicDictation,
    degree_label,
    generate_melody,
    generate_rhythm,
    spell,
)
from etude.exercises.families.scale_degrees import key_for
from etude.notation.spec import StaffSpec

EXERCISE = MelodicDictation()


@settings(max_examples=300, deadline=None)
@given(
    vocabulary=st.sampled_from(VOCABULARY),
    length=st.integers(4, 16),
    seed=st.integers(0, 10_000),
)
def test_melodies_follow_the_tonal_grammar(vocabulary: str, length: int, seed: int) -> None:
    grammar = GRAMMARS[vocabulary]
    melody = generate_melody(grammar, length, random.Random(seed))
    assert len(melody) == length
    assert melody[0] % 7 in (0, 2, 4), 'starts on 1, 3 or 5'
    assert melody[-1] == 0, 'ends on the tonic'
    assert melody[-2] in (1, -1), 'approached from 2 or 7'
    assert all(grammar.low <= d <= grammar.high for d in melody)
    for index, (a, b) in enumerate(itertools.pairwise(melody)):
        leap = abs(b - a)
        assert leap <= 5, 'leaps of at most a sixth'
        if leap >= 2:
            assert any({a % 7, b % 7} <= triad for triad in grammar.triads), 'triad leaps'
            after = melody[index + 2] - b
            assert abs(after) == 1, 'a leap is followed by a step'
            assert (after > 0) != (b > a), 'in the opposite direction'
        if a % 7 == 6:
            assert b == a + 1, 'the leading tone resolves to the tonic'
    if vocabulary == STEPS:
        assert all(abs(b - a) <= 1 for a, b in itertools.pairwise(melody))
    if grammar.requirement is not None:
        assert grammar.requirement(melody)


@pytest.mark.parametrize('vocabulary', VOCABULARY)
def test_spelled_melodies_have_no_augmented_or_diminished_steps(vocabulary: str) -> None:
    grammar = GRAMMARS[vocabulary]
    for fifths in range(-6, 7):
        key = key_for(grammar.mode, fifths)
        melody = generate_melody(grammar, 12, random.Random(fifths))
        pitches = spell(key, key.tonic.at(4), melody)
        for a, b in itertools.pairwise(pitches):
            if a == b:
                continue
            low, high = sorted((a, b), key=lambda p: (p.diatonic_index, p.midi))
            assert Interval.between(low, high).quality.value in ('m', 'M', 'P'), f'{a}–{b}'
        if grammar.mode is Mode.MINOR:
            for index, (degree, pitch) in enumerate(zip(melody, pitches, strict=True)):
                if degree % 7 == 6:
                    assert pitch.name == key.leading_tone, 'raised 7'
                if degree % 7 == 5 and index + 1 < len(melody) and melody[index + 1] % 7 == 6:
                    assert pitch.name == key.raised(6), 'raised 6 on the way up'


def test_rhythm_fills_the_bars_and_ends_long() -> None:
    for meter in (Meter(2, 4), Meter(3, 4), Meter(4, 4)):
        for bars in (2, 3, 4):
            for seed in range(20):
                rhythm = generate_rhythm(meter, bars, seed % 2 == 0, random.Random(seed))
                assert sum(d.length for d in rhythm) == meter.bar_length * bars
                assert len(rhythm) >= 4
                assert rhythm[-1].quarter_length >= 1


@pytest.mark.parametrize('vocabulary', VOCABULARY)
def test_questions_give_the_first_note_and_the_rhythm(vocabulary: str) -> None:
    settings_ = {**EXERCISE.default_settings(), 'clef': 'both', 'rhythm': 'eighths', 'bars': 4}
    for seed in range(8):
        question = EXERCISE.generate(
            f'dictation.melody.{vocabulary}', settings_, random.Random(seed)
        )
        answer = question.answer
        assert isinstance(answer, StaffInputAnswer)
        assert isinstance(answer.given, StaffSpec)
        assert answer.slots == len(answer.rhythm) == len(question.expected)
        written = question.written_alternative
        assert isinstance(written, StaffSpec)
        assert written.meter is not None
        durations = [e.duration for e in written.events if hasattr(e, 'heads')]
        assert tuple(durations[1:]) == answer.rhythm
        assert sum(d.length for d in durations) == written.meter.bar_length * 4
        assert answer.key_signature == written.key_signature
        first = answer.given.events[0].heads[0].pitch
        pitches = [first, *(slot[0] for slot in question.expected)]
        assert written.key_signature is not None
        key = key_for(GRAMMARS[vocabulary].mode, written.key_signature.fifths)
        assert degree_label(key, pitches[0]) in ('1', '3', '5')
        assert pitches[-1].name == key.tonic
        positions = [answer.clef.staff_position(p) for p in pitches]
        assert min(positions) >= -3
        assert max(positions) <= 11, 'at most one ledger line'
        # The playback sets the key, clicks one bar, then plays the melody.
        assert question.playback is not None
        clicks = [n for n in question.playback.notes if n.percussion]
        assert len(clicks) == written.meter.beats
        melody = [n for n in question.playback.notes if n.start > clicks[-1].start]
        assert [n.midi for n in melody] == [p.midi for p in pitches]


def test_partial_credit_and_explanations() -> None:
    question = EXERCISE.generate(
        f'dictation.melody.{MINOR}', {**EXERCISE.default_settings(), 'bars': 4}, random.Random(4)
    )
    expected = list(question.expected)
    total = len(expected)
    up = expected[0][0].transpose(Interval.parse('P8'))
    wrong = EXERCISE.grade(question, ((up,), *expected[1:]))
    assert not wrong.correct
    assert wrong.score == pytest.approx((total - 1) / total)
    assert 'wrong octave' in wrong.detail
    assert wrong.title.startswith('Nearly')
    assert wrong.play_given is not None
    assert wrong.play_expected is not None
    assert [n.midi for n in wrong.play_given.notes][1] == up.midi
    respelled = expected[0][0].enharmonics(max_alter=2)[0]
    feedback = EXERCISE.grade(question, ((respelled,), *expected[1:]))
    assert 'another name' in feedback.detail
    nothing = EXERCISE.grade(question, ())
    assert nothing.score == 0
    assert nothing.title.startswith('Not quite')
    right = EXERCISE.grade(question, question.expected)
    assert right.correct
    assert right.score == 1
    assert 'scale degrees' in right.detail
    labels = [e.label for e in right.figure.events if hasattr(e, 'heads')]
    assert labels[0] in ('1', '3', '5')
    assert labels[-1] == '1'


def test_tempo_and_context_settings() -> None:
    settings_ = {**EXERCISE.default_settings(), 'tempo': 100, 'context': 'tonic'}
    question = EXERCISE.generate('dictation.melody.steps', settings_, random.Random(0))
    assert question.playback is not None
    assert question.playback.tempo == 100
    starts = sorted({n.start for n in question.playback.notes if not n.percussion})
    assert starts[0] == 0
    assert all(isinstance(s, Fraction) for s in starts)
    chord = [n for n in question.playback.notes if n.start == 0]
    assert len(chord) == 3, 'the tonic chord'
