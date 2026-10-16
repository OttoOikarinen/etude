# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random

import pytest

from etude.core import KeySignature, Pitch
from etude.core.scale import Key, Mode
from etude.exercises.base import ChoiceAnswer, Question
from etude.exercises.families.scale_degrees import (
    TEACHING_ORDER,
    ScaleDegrees,
    item_id,
    key_for,
    parse_item,
)
from etude.notation.a11y import describe
from etude.notation.spec import Chord, Clef, Ink, StaffSpec

EXERCISE = ScaleDegrees()
DEFAULTS = EXERCISE.default_settings()
BOTH = {**DEFAULTS, 'mode': 'both', 'max-accidentals': 7, 'clefs': ('treble', 'bass', 'alto')}


def heads(q: Question) -> list[Pitch]:
    assert isinstance(q.figure, StaffSpec)
    return [e.heads[0].pitch for e in q.figure.events if isinstance(e, Chord)]


def key_of(q: Question) -> Key:
    assert isinstance(q.figure, StaffSpec)
    assert q.figure.key_signature is not None
    return key_for(parse_item(q.item_id)[0], q.figure.key_signature.fifths)


def find_question(item: str, settings: dict[str, object], fifths: int, clef: Clef) -> Question:
    """The first seeded question in the given key and clef."""
    for seed in range(500):
        q = EXERCISE.generate(item, settings, random.Random(seed))
        assert isinstance(q.figure, StaffSpec)
        if q.figure.key_signature == KeySignature(fifths) and q.figure.clef is clef:
            return q
    raise AssertionError('no such question')


@pytest.mark.parametrize('mode', list(Mode))
@pytest.mark.parametrize('degree', range(1, 8))
@pytest.mark.parametrize('find', [False, True])
def test_item_ids_round_trip(mode: Mode, degree: int, find: bool) -> None:
    assert parse_item(item_id(mode, degree, find=find)) == (mode, degree, find)


@pytest.mark.parametrize(
    'text',
    [
        'degree.major.8',
        'degree.major.0',
        'degree.dorian.1',
        'degree.major.seek.1',
        'keysig.major.0',
    ],
)
def test_bad_item_ids_are_rejected(text: str) -> None:
    with pytest.raises(ValueError, match='not a scale-degree item'):
        parse_item(text)


def test_design_question() -> None:
    """Design 1g: A highlighted in D major, degree buttons Tonic … Leading."""
    q = find_question('degree.major.5', {**DEFAULTS, 'clefs': ('treble',)}, 2, Clef.TREBLE)
    assert q.prompt == 'Which scale degree is highlighted?'
    assert q.context == 'Key: D major'
    assert isinstance(q.answer, ChoiceAnswer)
    assert [(o.key, o.label, o.accel) for o in q.answer.options] == [
        (str(n), str(n), str(n)) for n in range(1, 8)
    ]
    assert [o.description for o in q.answer.options] == [
        'Tonic',
        'Supert.',
        'Mediant',
        'Subdom.',
        'Dominant',
        'Submed.',
        'Leading',
    ]
    assert q.expected == '5'
    assert isinstance(q.figure, StaffSpec)
    (event,) = q.figure.events
    assert isinstance(event, Chord)
    (head,) = event.heads
    assert head.pitch.name == Pitch.parse('A4').name
    assert head.ink is Ink.ACCENT
    assert head.halo
    # The only note is the highlighted one: clicking it must not answer.
    assert not q.answer.targets

    right = EXERCISE.grade(q, '5')
    assert right.title == 'Correct — 5, the dominant'
    assert right.detail.startswith('In D major, A is the fifth degree: the dominant')
    wrong = EXERCISE.grade(q, '4')
    assert wrong.title == 'Not quite — the answer is 5, the dominant'
    assert 'Degree 4 of D major is G.' in wrong.detail


def test_highlighted_note_is_the_degree() -> None:
    for item in EXERCISE.items({**BOTH, 'find': False}):
        degree = parse_item(item)[1]
        for seed in range(10):
            q = EXERCISE.generate(item, BOTH, random.Random(seed))
            (pitch,) = heads(q)
            assert pitch.name == key_of(q).degree(degree)
            assert isinstance(q.figure, StaffSpec)
            assert -1 <= q.figure.clef.staff_position(pitch) <= 9


def test_keys_vary_within_the_settings() -> None:
    signatures = set()
    for seed in range(60):
        q = EXERCISE.generate(
            'degree.major.3', {**DEFAULTS, 'max-accidentals': 2}, random.Random(seed)
        )
        assert isinstance(q.figure, StaffSpec)
        assert q.figure.key_signature is not None
        signatures.add(q.figure.key_signature.fifths)
    assert signatures == {-2, -1, 0, 1, 2}


def test_find_question_maps_every_note_to_its_degree() -> None:
    for item in [i for i in EXERCISE.items(BOTH) if parse_item(i)[2]]:
        degree = parse_item(item)[1]
        for seed in range(10):
            q = EXERCISE.generate(item, BOTH, random.Random(seed))
            key = key_of(q)
            pitches = heads(q)
            assert {p.name for p in pitches} == set(key.scale.names())
            assert isinstance(q.answer, ChoiceAnswer)
            for slot, pitch in enumerate(pitches):
                assert q.answer.targets[slot] == str(key.scale.degree_of(pitch.name))
            # Options follow the staff from left to right, with letter accelerators.
            assert [o.accel for o in q.answer.options] == [p.letter.name.lower() for p in pitches]
            assert [q.answer.targets[s] for s in range(7)] == [o.key for o in q.answer.options]
            assert q.expected == str(degree)
            assert isinstance(q.figure, StaffSpec)
            positions = [q.figure.clef.staff_position(p) for p in pitches]
            assert min(positions) >= -2
            assert max(positions) <= 10


def test_find_design_wording() -> None:
    q = find_question('degree.major.find.5', {**DEFAULTS, 'clefs': ('treble',)}, 2, Clef.TREBLE)
    assert q.prompt == 'Which note is the dominant?'
    assert q.context == 'Key: D major'
    assert q.hint == 'Dominant: degree 5. Count up the scale from the tonic, D.'
    assert isinstance(q.answer, ChoiceAnswer)
    labels = {o.key: o.label for o in q.answer.options}
    assert labels['5'] == 'A'
    assert labels['7'] == 'C♯'
    right = EXERCISE.grade(q, '5')
    assert right.title == 'Correct — A'
    wrong = EXERCISE.grade(q, '4')
    assert 'G is degree 4 of D major.' in wrong.detail


def test_minor_seventh_is_the_subtonic() -> None:
    q = find_question('degree.minor.7', {**DEFAULTS, 'mode': 'minor'}, 0, Clef.TREBLE)
    assert isinstance(q.answer, ChoiceAnswer)
    assert q.answer.options[6].description == 'Subtonic'
    (pitch,) = heads(q)
    assert pitch.name == Pitch.parse('G4').name
    feedback = EXERCISE.grade(q, '7')
    assert feedback.title == 'Correct — 7, the subtonic'
    assert 'In A minor, G is the seventh degree: the subtonic' in feedback.detail
    assert 'Raised to G♯, it becomes the leading tone.' in feedback.detail


@pytest.mark.parametrize(
    ('degree', 'phrase'),
    [
        (1, 'the tonic'),
        (2, 'the supertonic, a step above the tonic'),
        (3, 'the mediant'),
        (4, 'the subdominant, a fifth below the tonic'),
        (6, 'the submediant, a third below the tonic'),
        (7, 'the leading tone, a semitone below the tonic'),
    ],
)
def test_explanations_name_the_function(degree: int, phrase: str) -> None:
    q = find_question(f'degree.major.{degree}', DEFAULTS, -3, Clef.BASS)
    note = key_for(Mode.MAJOR, -3).degree(degree)
    detail = EXERCISE.grade(q, str(degree)).detail
    assert detail.startswith(f'In E♭ major, {note.symbol} is the ')
    assert phrase in detail


def test_worked_figure_counts_up_from_the_tonic() -> None:
    q = find_question('degree.major.5', {**DEFAULTS, 'clefs': ('treble',)}, 2, Clef.TREBLE)
    figure = EXERCISE.grade(q, '4').figure
    assert isinstance(figure, StaffSpec)
    events = [e for e in figure.events if isinstance(e, Chord)]
    assert [e.label for e in events] == ['1', '2', '3', '4', '5']
    assert [e.heads[0].pitch.symbol[:-1] for e in events] == ['D', 'E', 'F♯', 'G', 'A']
    assert [e.heads[0].halo for e in events] == [False] * 4 + [True]
    assert events[-1].heads[0].pitch == heads(q)[0]


def test_question_figures_do_not_show_the_answer() -> None:
    for item in EXERCISE.items(BOTH):
        q = EXERCISE.generate(item, BOTH, random.Random(3))
        assert isinstance(q.figure, StaffSpec)
        assert all(isinstance(e, Chord) and e.label is None for e in q.figure.events)
        text = describe(q.figure)
        assert 'Labels' not in text
        if parse_item(item)[2]:
            assert 'Highlighted' not in text


def test_playback_is_the_scale_then_the_note() -> None:
    q = find_question('degree.major.5', {**DEFAULTS, 'clefs': ('treble',)}, 2, Clef.TREBLE)
    assert q.playback is not None
    midis = [n.midi for n in q.playback.notes]
    (pitch,) = heads(q)
    assert len(midis) == 9
    assert midis[-1] == pitch.midi
    assert midis[4] == pitch.midi  # the written A is the fifth of the scale played
    assert midis[7] - midis[0] == 12
    assert EXERCISE.play_label == 'Play scale'


def test_teaching_order() -> None:
    assert TEACHING_ORDER == (1, 5, 4, 3, 2, 6, 7)
    items = EXERCISE.items({**DEFAULTS, 'mode': 'both'})
    assert items[:4] == [
        'degree.major.1',
        'degree.major.find.1',
        'degree.major.5',
        'degree.major.find.5',
    ]
    assert items.index('degree.major.find.7') < items.index('degree.minor.1')
    assert len(items) == 28
    identify_only = EXERCISE.items({**DEFAULTS, 'find': False})
    assert identify_only == [f'degree.major.{n}' for n in TEACHING_ORDER]


def test_labels() -> None:
    assert EXERCISE.item_label('degree.major.5') == 'Dominant — major'
    assert EXERCISE.item_label('degree.minor.find.7') == 'Subtonic on the staff — minor'
    assert EXERCISE.describe_settings(DEFAULTS) == 'Major keys · up to 4 accidentals'
    assert (
        EXERCISE.describe_settings({**DEFAULTS, 'mode': 'both', 'max-accidentals': 1})
        == 'Major and minor keys · up to 1 accidental'
    )
