# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random

import pytest

from etude.core import Pitch, PitchName
from etude.exercises.base import PianoAnswer
from etude.exercises.families.note_naming import (
    NoteNaming,
    item_id,
    keyboard_range,
    ledger_lines,
    parse_item,
)
from etude.notation.a11y import describe
from etude.notation.spec import Chord, Clef, StaffSpec

EXERCISE = NoteNaming()
DEFAULTS = EXERCISE.default_settings()
EVERYTHING = {
    **DEFAULTS,
    'clefs': ('treble', 'bass', 'alto', 'tenor'),
    'ledger-lines': 3,
    'accidentals': True,
}
READING_CLEFS = (Clef.TREBLE, Clef.BASS, Clef.ALTO, Clef.TENOR)


def question(item: str, settings: dict[str, object] | None = None, seed: int = 0):
    return EXERCISE.generate(item, settings or DEFAULTS, random.Random(seed))


@pytest.mark.parametrize('clef', READING_CLEFS)
def test_item_ids_round_trip(clef: Clef) -> None:
    for position in range(-7, 16):
        for alter in (-1, 0, 1):
            pitch = clef.pitch_at(position, alter)
            if str(pitch.name) in ('E#', 'B#', 'Cb', 'Fb'):
                continue
            assert parse_item(item_id(clef, pitch)) == (clef, pitch)


@pytest.mark.parametrize(
    'text',
    [
        'note.treble.E#4',  # a white key: a spelling question, not a reading one
        'note.treble.Cb5',
        'note.treble.C2',  # far beyond three ledger lines
        'note.treble.Fx4',
        'note.treble.f4',  # not the canonical spelling
        'note.soprano.C4',
        'note.treble',
        'keysig.major.0',
    ],
)
def test_bad_item_ids_are_rejected(text: str) -> None:
    with pytest.raises(ValueError, match='not a note-naming item'):
        parse_item(text)


@pytest.mark.parametrize(
    ('position', 'count'),
    [(-7, 3), (-6, 3), (-3, 1), (-2, 1), (-1, 0), (0, 0), (8, 0), (9, 0), (10, 1), (15, 3)],
)
def test_ledger_lines(position: int, count: int) -> None:
    assert ledger_lines(position) == count


def test_design_question() -> None:
    """Design 1c: F4 in the treble clef, answered on a C4–C5 keyboard."""
    q = question('note.treble.F4')
    assert q.prompt == 'Name this note'
    assert q.answer == PianoAnswer(Pitch.parse('C4'), Pitch.parse('C5'))
    assert q.expected == PitchName.parse('F')
    assert isinstance(q.figure, StaffSpec)
    assert q.figure.clef is Clef.TREBLE
    assert q.figure.events == (Chord((q.figure.events[0].heads[0],)),)
    assert q.figure.events[0].heads[0].pitch == Pitch.parse('F4')
    assert q.figure.description == 'Treble staff with one note.'
    assert q.hint == 'Spaces of the treble staff spell F A C E from the bottom up.'
    assert q.playback is None  # design 1c has no play button while asking


def test_design_feedback() -> None:
    q = question('note.treble.F4')
    right = EXERCISE.grade(q, PitchName.parse('F'))
    assert right.correct
    assert right.title == 'Correct — F4'
    assert right.detail.startswith('F4 is in the first space of the treble staff.')
    assert right.figure is None  # design 1c keeps the question's staff
    assert right.play_expected is not None
    assert [n.midi for n in right.play_expected.notes] == [65]
    wrong = EXERCISE.grade(q, PitchName.parse('A'))
    assert not wrong.correct
    assert wrong.title == 'Not quite — the answer is F4'
    assert EXERCISE.answer_label(q, q.expected) == 'F4'
    assert EXERCISE.answer_label(q, PitchName.parse('A')) == 'A'


def test_descriptions_never_name_the_note() -> None:
    for item in EXERCISE.items(EVERYTHING):
        q = question(item, EVERYTHING)
        clef, pitch = parse_item(item)
        assert isinstance(q.figure, StaffSpec)
        text = describe(q.figure)
        assert text == q.figure.description
        assert text == f'{clef.value.capitalize()} staff with one note.'
        assert str(pitch) not in text
        assert pitch.symbol not in text


@pytest.mark.parametrize(
    ('item', 'facts'),
    [
        ('note.treble.G4', ['on the second line', 'treble clef curls around this line']),
        ('note.treble.E4', ['on the bottom line', 'are E G B D F']),
        ('note.treble.F5', ['on the top line']),
        ('note.treble.C4', ['first ledger line below', 'E4 D4 C4', 'C4 is middle C']),
        ('note.treble.B3', ['space under the first ledger line', 'E4 D4 C4 B3']),
        ('note.treble.A5', ['first ledger line above', 'F5 G5 A5']),
        ('note.treble.D4', ['just below the treble staff']),
        ('note.bass.F3', ['fourth line of the bass staff', 'two dots of the bass clef']),
        ('note.bass.A2', ['first space of the bass staff', 'are A C E G']),
        ('note.bass.C4', ['first ledger line above the bass staff', 'middle C']),
        ('note.alto.C4', ['middle line of the alto staff', 'C clef centres', 'F A C E G']),
        ('note.tenor.C4', ['fourth line of the tenor staff', 'C clef centres', 'D F A C E']),
        ('note.tenor.E3', ['first space of the tenor staff', 'E G B D']),
    ],
)
def test_explanations(item: str, facts: list[str]) -> None:
    q = question(item, EVERYTHING)
    detail = EXERCISE.grade(q, q.expected).detail
    for fact in facts:
        assert fact in detail


def test_accidental_explanation() -> None:
    q = question('note.treble.F#4', EVERYTHING)
    detail = EXERCISE.grade(q, PitchName.parse('F#')).detail
    assert 'F4 is in the first space' in detail
    assert 'The sharp raises F4 a semitone to F♯4.' in detail
    q = question('note.alto.Bb3', EVERYTHING)
    assert 'The flat lowers B3 a semitone to B♭3.' in EXERCISE.grade(q, q.expected).detail


def test_black_key_names_are_interchangeable() -> None:
    """A click on a black key yields a sharp, so A♯ answers a written B♭."""
    q = question('note.treble.Bb4', EVERYTHING)
    feedback = EXERCISE.grade(q, PitchName.parse('A#'))
    assert feedback.correct
    assert feedback.title == 'Correct — B♭4'
    assert 'A♯ is the same key on the piano, but this note is written B♭.' in feedback.detail
    assert not EXERCISE.grade(q, PitchName.parse('B')).correct
    natural = question('note.treble.F4', EVERYTHING)
    assert not EXERCISE.grade(natural, PitchName.parse('E#')).correct


def test_octave_setting() -> None:
    settings = {**DEFAULTS, 'octave': True}
    q = question('note.treble.F4', settings)
    assert isinstance(q.answer, PianoAnswer)
    assert q.answer.octave_matters
    assert q.expected == Pitch.parse('F4')
    assert EXERCISE.grade(q, Pitch.parse('F4')).correct
    wrong = EXERCISE.grade(q, Pitch.parse('F5'))
    assert not wrong.correct
    assert 'Right letter, wrong octave' in wrong.detail
    assert 'Middle C, in the middle of the keyboard, is C4.' in wrong.detail


@pytest.mark.parametrize(
    ('pitch', 'low', 'high'),
    [
        ('F4', 'C3', 'C5'),
        ('C5', 'C3', 'C5'),
        ('C3', 'C3', 'C5'),
        ('B2', 'C2', 'C4'),
        ('A1', 'C1', 'C3'),
        ('D5', 'C4', 'C6'),
        ('F6', 'C5', 'C7'),
        ('C6', 'C5', 'C7'),
    ],
)
def test_keyboard_range_keeps_middle_c_in_the_middle(pitch: str, low: str, high: str) -> None:
    assert keyboard_range(Pitch.parse(pitch)) == (Pitch.parse(low), Pitch.parse(high))


def test_every_item_fits_its_keyboard() -> None:
    settings = {**EVERYTHING, 'octave': True}
    for item in EXERCISE.items(settings):
        q = question(item, settings)
        assert isinstance(q.answer, PianoAnswer)
        assert isinstance(q.expected, Pitch)
        assert q.answer.low <= q.expected <= q.answer.high


def test_teaching_order_starts_at_the_landmarks() -> None:
    items = EXERCISE.items(DEFAULTS)
    assert items[:4] == ['note.treble.G4', 'note.bass.F3', 'note.treble.A4', 'note.bass.G3']
    alto_tenor = EXERCISE.items({**DEFAULTS, 'clefs': ('alto', 'tenor')})
    assert alto_tenor[:2] == ['note.alto.C4', 'note.tenor.C4']


def test_staff_before_ledger_lines_before_accidentals() -> None:
    items = EXERCISE.items(EVERYTHING)
    ledger = [ledger_lines(c.staff_position(p)) for c, p in map(parse_item, items)]
    altered = [parse_item(i)[1].alter != 0 for i in items]
    first_accidental = altered.index(True)
    assert not any(altered[:first_accidental])
    assert all(altered[first_accidental:])
    naturals = ledger[:first_accidental]
    assert naturals == sorted(naturals)
    # Middle C is the first ledger-line note of the treble clef.
    treble_ledger = [i for i in items if i.startswith('note.treble.') and ledger[items.index(i)]]
    assert treble_ledger[0] == 'note.treble.C4'


def test_item_counts() -> None:
    assert len(EXERCISE.items({**DEFAULTS, 'clefs': ('treble',), 'ledger-lines': 0})) == 11
    assert len(EXERCISE.items({**DEFAULTS, 'clefs': ('treble',), 'ledger-lines': 1})) == 15
    with_accidentals = EXERCISE.items(
        {**DEFAULTS, 'clefs': ('treble',), 'ledger-lines': 0, 'accidentals': True}
    )
    # D4–G5 with a sharp and a flat each, except E♯ and B♯ (three) and F♭ and C♭ (three).
    assert 'note.treble.E#4' not in with_accidentals
    assert 'note.treble.Fb4' not in with_accidentals
    assert 'note.treble.Eb4' in with_accidentals
    assert len(with_accidentals) == 11 + 22 - 6


def test_labels() -> None:
    assert EXERCISE.item_label('note.treble.F#4') == 'F♯4 — treble clef'
    assert EXERCISE.item_label('note.bass.A2') == 'A2 — bass clef'
    assert EXERCISE.play_label == 'Play note'
    assert EXERCISE.describe_settings(DEFAULTS) == 'Mixed clefs · up to 1 ledger line'
    assert (
        EXERCISE.describe_settings({**DEFAULTS, 'clefs': ('alto',), 'ledger-lines': 0})
        == 'Alto clef · no ledger lines'
    )
