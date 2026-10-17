# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random

import pytest

from etude.core import Interval, PitchName
from etude.exercises.base import ChoiceAnswer
from etude.exercises.families.scales import (
    BASIC,
    MODES,
    PENTATONIC,
    ScalesEar,
    ScalesStaff,
    character,
    parse_ear_item,
    parse_staff_item,
    scale_for,
    spellable,
    staff_item,
    step_pattern,
    tonics_for,
)
from etude.notation.spec import Chord, StaffSpec, SystemSpec

STAFF = ScalesStaff()
EAR = ScalesEar()
ALL_TYPES = (*BASIC, *MODES, *PENTATONIC)

PATTERNS = {
    'major': 'whole, whole, half, whole, whole, whole, half',
    'natural-minor': 'whole, half, whole, whole, half, whole, whole',
    'harmonic-minor': 'whole, half, whole, whole, half, step and a half, half',
    'melodic-minor': 'whole, half, whole, whole, whole, whole, half',
    'dorian': 'whole, half, whole, whole, whole, half, whole',
    'phrygian': 'half, whole, whole, whole, half, whole, whole',
    'lydian': 'whole, whole, whole, half, whole, whole, half',
    'mixolydian': 'whole, whole, half, whole, whole, half, whole',
    'locrian': 'half, whole, whole, half, whole, whole, whole',
    'major-pentatonic': 'whole, whole, step and a half, whole, step and a half',
    'minor-pentatonic': 'step and a half, whole, whole, step and a half, whole',
}


@pytest.mark.parametrize('key', ALL_TYPES)
def test_every_tonic_spells_the_pattern(key: str) -> None:
    tonics = tonics_for(key)
    assert len(tonics) >= 10
    for tonic in tonics:
        scale = scale_for(tonic, key)
        assert spellable(scale)
        pitches = scale.pitches(4)
        assert step_pattern(pitches) == PATTERNS[key]
        assert pitches[-1] == tonic.at(5)
        if scale.type.size == 7:
            # Heptatonic scales use every letter once.
            assert len({p.letter for p in pitches[:7]}) == 7


def test_melodic_minor_descends_as_natural_minor() -> None:
    scale = scale_for(PitchName.parse('A'), 'melodic-minor')
    up = [str(n) for n in scale.names()]
    down = [str(n) for n in scale.names(descending=True)]
    assert up == ['A', 'B', 'C', 'D', 'E', 'F#', 'G#']
    assert down == ['A', 'B', 'C', 'D', 'E', 'F', 'G']


def test_harmonic_minor_on_c() -> None:
    scale = scale_for(PitchName.parse('C'), 'harmonic-minor')
    assert [str(n) for n in scale.names()] == ['C', 'D', 'Eb', 'F', 'G', 'Ab', 'B']
    assert 'raises the seventh degree of natural minor to B' in character(scale)
    assert 'step and a half from A♭' in character(scale)


def test_double_sharps_are_avoided() -> None:
    # G♯ harmonic minor needs F𝄪.
    assert PitchName.parse('G#') not in tonics_for('harmonic-minor')
    assert PitchName.parse('G#') in tonics_for('natural-minor')
    assert tonics_for('harmonic-minor', 0)  # falls back to the fewest accidentals


def test_staff_items_and_parsing() -> None:
    defaults = STAFF.default_settings()
    assert STAFF.items(defaults)[:2] == ['scale.staff.major', 'scale.staff.wrong.major']
    modes = STAFF.items({**defaults, 'modes': True, 'spot': False})
    assert modes == [staff_item(k) for k in (*BASIC, *MODES)]
    assert parse_staff_item('scale.staff.wrong.dorian') == ('dorian', True)
    with pytest.raises(ValueError, match='not a staff scale item'):
        parse_staff_item('scale.staff.major-pentatonic')


def test_identify_question_shows_one_octave() -> None:
    q = STAFF.generate('scale.staff.harmonic-minor', STAFF.default_settings(), random.Random(1))
    assert isinstance(q.figure, StaffSpec)
    pitches = [e.heads[0].pitch for e in q.figure.events if isinstance(e, Chord)]
    assert len(pitches) == 8
    assert Interval.between(pitches[6], pitches[7]).semitones == 1
    feedback = STAFF.grade(q, 'melodic-minor')
    assert not feedback.correct
    assert 'For comparison: Melodic minor raises' in feedback.detail
    assert feedback.play_given is not None
    assert STAFF.confusables('scale.staff.harmonic-minor')[0] == 'scale.staff.melodic-minor'


@pytest.mark.parametrize('seed', range(20))
def test_wrong_note_is_one_semitone_off(seed: int) -> None:
    settings = STAFF.default_settings()
    q = STAFF.generate('scale.staff.wrong.melodic-minor', settings, random.Random(seed))
    assert isinstance(q.answer, ChoiceAnswer)
    assert isinstance(q.figure, StaffSpec)
    shown = [e.heads[0].pitch for e in q.figure.events if isinstance(e, Chord)]
    scale = scale_for(shown[0].name, 'melodic-minor')
    right = scale.pitches(shown[0].octave)
    wrong = [i for i, (a, b) in enumerate(zip(shown, right, strict=True)) if a != b]
    assert len(wrong) == 1
    (index,) = wrong
    assert q.expected == str(index + 1)
    assert shown[index].letter == right[index].letter
    assert abs(shown[index].midi - right[index].midi) == 1
    assert str(shown[index].name) not in ('E#', 'B#', 'Fb', 'Cb')
    assert q.answer.targets[index] == q.expected
    feedback = STAFF.grade(q, q.expected)
    assert feedback.correct
    assert f'degree {index + 1} is' in feedback.detail


def test_ear_question_plays_up_and_down() -> None:
    settings = EAR.default_settings()
    q = EAR.generate('scale.ear.melodic-minor', settings, random.Random(0))
    assert q.playback is not None
    assert len(q.playback.notes) == 15
    assert q.playback_is_question
    assert not q.playback_style_choice
    assert q.context.startswith('Tonic: ')
    assert isinstance(q.written_alternative, SystemSpec), 'up and down on two staves'
    assert [len(s.events) for s in q.written_alternative.staves] == [8, 8]
    midis = [n.midi for n in q.playback.notes]
    assert midis[5] - midis[0] == 9  # raised sixth going up
    assert midis[9] - midis[14] == 8  # natural sixth coming down
    feedback = EAR.grade(q, 'harmonic-minor')
    assert feedback.play_given is not None
    assert len(feedback.play_given.notes) == 15
    ascending = EAR.generate('scale.ear.major', {**settings, 'direction': 'asc'}, random.Random(0))
    assert ascending.playback is not None
    assert len(ascending.playback.notes) == 8


def test_ear_pool_settings() -> None:
    settings = EAR.default_settings()
    assert [parse_ear_item(i) for i in EAR.items(settings)] == list(BASIC)
    everything = EAR.items({**settings, 'modes': True, 'pentatonic': True})
    assert len(everything) == len(ALL_TYPES)
