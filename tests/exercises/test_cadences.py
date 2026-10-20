# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import itertools
import random

import pytest

from etude.checkers.voice_leading import Ranges
from etude.core import Chord
from etude.core.roman import RomanNumeral
from etude.core.scale import Key, Mode
from etude.exercises.base import ChoiceAnswer, Question
from etude.exercises.families.cadences import TYPES, CadencesStaff, item_id, parse_item
from etude.exercises.families.harmony import Voicing, chord_of, satb_voices
from etude.learning.model import ItemId
from etude.notation.spec import Chord as StaffChord
from etude.notation.spec import Ink, StaffSpec, SystemSpec

CAD = CadencesStaff()
DEFAULTS = CAD.default_settings()
ALL = {**DEFAULTS, 'phrygian': True, 'max-accidentals': 7}
SEEDS = range(25)
RANGES = Ranges()


def key_of(question: Question) -> Key:
    figure = question.figure
    assert isinstance(figure, SystemSpec)
    signature = figure.staves[0].key_signature
    assert signature is not None
    mode = parse_item(question.item_id)[0]
    tonic = signature.major_tonic if mode is Mode.MAJOR else signature.minor_tonic
    return Key(tonic, mode)


def analysis(question: Question) -> tuple[Key, list[Voicing], list[Chord], list[RomanNumeral]]:
    key = key_of(question)
    voices = satb_voices(question.figure)
    chords = [chord_of(sorted(v)) for v in voices]
    numerals = [RomanNumeral.analyze(c, key) for c in chords]
    assert all(n is not None for n in numerals)
    return key, voices, chords, [n for n in numerals if n is not None]


def questions(kind: str, mode: Mode, settings: dict[str, object] = ALL) -> list[Question]:
    return [CAD.generate(item_id(mode, kind), settings, random.Random(s)) for s in SEEDS]


def is_dominant(n: RomanNumeral) -> bool:
    return n.degree == 5 and n.quality.value in ('major', 'dominant-seventh')


def is_tonic(n: RomanNumeral) -> bool:
    return n.degree == 1 and n.quality.value in ('major', 'minor')


@pytest.mark.parametrize('mode', list(Mode))
def test_perfect_authentic(mode: Mode) -> None:
    for question in questions('pac', mode):
        key, voices, _chords, numerals = analysis(question)
        penult, final = numerals[-2:]
        assert is_dominant(penult)
        assert penult.inversion == 0
        assert is_tonic(final)
        assert final.inversion == 0
        assert voices[-1][0].name == key.tonic


@pytest.mark.parametrize('mode', list(Mode))
def test_imperfect_authentic(mode: Mode) -> None:
    inverted = 0
    for question in questions('iac', mode):
        key, voices, _chords, numerals = analysis(question)
        penult, final = numerals[-2:]
        assert is_tonic(final)
        assert final.inversion == 0
        assert is_dominant(penult) or (penult.degree == 7 and penult.inversion == 1)
        weak = penult.inversion != 0 or penult.degree == 7
        inverted += weak
        # Not a PAC: an inverted (or leading-tone) dominant, or no tonic in the soprano.
        assert weak or voices[-1][0].name != key.tonic
    assert inverted, 'some IACs use an inverted dominant'


def test_inverted_iac_setting() -> None:
    settings = {**ALL, 'inverted-iac': False}
    for question in questions('iac', Mode.MAJOR, settings):
        key, voices, _chords, numerals = analysis(question)
        assert numerals[-2].inversion == 0
        assert numerals[-2].degree == 5
        assert voices[-1][0].name != key.tonic


@pytest.mark.parametrize('mode', list(Mode))
def test_half_cadence_ends_on_root_position_dominant(mode: Mode) -> None:
    for question in questions('half', mode):
        numerals = analysis(question)[3]
        assert is_dominant(numerals[-1])
        assert numerals[-1].inversion == 0
        assert numerals[-1].quality.size == 3


def test_phrygian_half_cadence() -> None:
    for question in questions('phrygian', Mode.MINOR):
        key, voices, _chords, numerals = analysis(question)
        assert (numerals[-2].degree, numerals[-2].inversion) == (4, 1)
        assert numerals[-2].quality.value == 'minor'
        assert is_dominant(numerals[-1])
        assert numerals[-1].inversion == 0
        # The bass falls a half step from the lowered sixth degree to the dominant ...
        assert voices[-2][3].midi - voices[-1][3].midi == 1
        assert voices[-2][3].name == key.degree(6)
        # ... while the soprano rises a whole step from 4 to 5.
        assert voices[-1][0].midi - voices[-2][0].midi == 2
    with pytest.raises(ValueError, match='not a'):
        parse_item('cadence.staff.major.phrygian')


@pytest.mark.parametrize('mode', list(Mode))
def test_plagal(mode: Mode) -> None:
    for question in questions('plagal', mode):
        numerals = analysis(question)[3]
        assert (numerals[-2].degree, numerals[-2].inversion) == (4, 0)
        assert is_tonic(numerals[-1])
        assert numerals[-1].inversion == 0


@pytest.mark.parametrize('mode', list(Mode))
def test_deceptive(mode: Mode) -> None:
    for question in questions('deceptive', mode):
        key, voices, _chords, numerals = analysis(question)
        assert is_dominant(numerals[-2])
        assert numerals[-2].inversion == 0
        assert numerals[-1].degree == 6
        assert numerals[-1].inversion == 0
        # The leading tone rises to the tonic, which is doubled in vi (the third).
        for v in range(3):
            if voices[-2][v].name == key.leading_tone:
                assert voices[-1][v].name == key.tonic


def parallel(a: Voicing, b: Voicing) -> bool:
    for i in range(4):
        for j in range(i + 1, 4):
            if a[i] == b[i] or a[j] == b[j]:
                continue
            interval = (a[i].midi - a[j].midi) % 12
            if interval in (0, 7) and interval == (b[i].midi - b[j].midi) % 12:
                return True
    return False


@pytest.mark.parametrize('kind', TYPES)
def test_four_part_writing(kind: str) -> None:
    modes = (Mode.MINOR,) if kind == 'phrygian' else tuple(Mode)
    for mode in modes:
        for question in questions(kind, mode):
            key, voices, chords, _ = analysis(question)
            for voicing in voices:
                for voice, pitch in enumerate(voicing):
                    low, high = RANGES.of(voice)
                    assert low.midi <= pitch.midi <= high.midi
                s, a, t, b = voicing
                assert s.midi > a.midi > t.midi > b.midi
                assert s.midi - a.midi <= 12
                assert a.midi - t.midi <= 12
            for before, after in itertools.pairwise(voices):
                assert not parallel(before, after), question.item_id
                assert all(abs(x.midi - y.midi) <= 12 for x, y in zip(before, after, strict=True))
            for chord, voicing in zip(chords, voices, strict=True):
                if chord.quality.size == 3:
                    assert sum(p.name == key.leading_tone for p in voicing) <= 1


def test_question_shape() -> None:
    question = CAD.generate(ItemId('cadence.staff.major.pac'), DEFAULTS, random.Random(0))
    assert isinstance(question.answer, ChoiceAnswer)
    assert [o.key for o in question.answer.options] == list(TYPES[:5])
    assert question.context.startswith('Key: ')
    figure = question.figure
    assert isinstance(figure, SystemSpec)
    events = [e for e in figure.staves[0].events if isinstance(e, StaffChord)]
    assert 3 <= len(events) <= 5
    assert question.playback is not None
    assert len(question.playback.notes) == 4 * len(events)
    phrygian = CAD.generate(ItemId('cadence.staff.minor.half'), ALL, random.Random(0))
    assert isinstance(phrygian.answer, ChoiceAnswer)
    assert phrygian.answer.options[-1].key == 'phrygian'


def test_feedback_explains_and_contrasts() -> None:
    question = CAD.generate(ItemId('cadence.staff.major.pac'), DEFAULTS, random.Random(4))
    key = key_of(question)
    right = CAD.grade(question, 'pac')
    assert right.correct
    assert right.title == 'Correct — a perfect authentic cadence'
    assert f'with the tonic, {key.tonic.symbol}, in the soprano' in right.detail
    wrong = CAD.grade(question, 'iac')
    assert not wrong.correct
    assert wrong.title == 'Not quite — the answer is a perfect authentic cadence'
    assert 'An imperfect authentic cadence is V–I with the third or fifth' in wrong.detail
    figure = right.figure
    assert isinstance(figure, SystemSpec)
    bass = figure.staves[1]
    assert isinstance(bass, StaffSpec)
    labels = [e.label for e in bass.voices[0] if isinstance(e, StaffChord)]
    assert labels[-1] == 'I'
    assert labels[-2] in ('V', 'V7')
    inks = [e.ink for e in bass.voices[0] if isinstance(e, StaffChord)]
    assert inks[-2:] == [Ink.ACCENT, Ink.ACCENT]
    assert Ink.ACCENT not in inks[:-2]


def test_iac_explains_why_it_is_imperfect() -> None:
    for seed in SEEDS:
        question = CAD.generate(ItemId('cadence.staff.major.iac'), ALL, random.Random(seed))
        detail = CAD.grade(question, 'iac').detail
        assert 'imperfect' in detail
        numerals = analysis(question)[3]
        if numerals[-2].inversion or numerals[-2].degree == 7:
            assert 'Kostka–Payne' in detail
        else:
            assert 'not on the tonic' in detail


def test_items_settings_and_labels() -> None:
    items = list(CAD.items(DEFAULTS))
    assert items[:4] == [
        'cadence.staff.major.pac',
        'cadence.staff.minor.pac',
        'cadence.staff.major.half',
        'cadence.staff.minor.half',
    ]
    assert not any('phrygian' in i for i in items)
    assert 'cadence.staff.minor.phrygian' in CAD.items(ALL)
    assert 'cadence.staff.minor.phrygian' not in CAD.items({**ALL, 'mode': 'major'})
    assert CAD.items({**DEFAULTS, 'types': ('plagal',), 'mode': 'minor'}) == [
        'cadence.staff.minor.plagal'
    ]
    assert CAD.item_label(ItemId('cadence.staff.minor.deceptive')) == 'Deceptive cadence in minor'
    assert CAD.describe_settings(DEFAULTS) == 'Major and minor keys · 5 cadences'
    assert 'cadence.staff.major.iac' in CAD.confusables(ItemId('cadence.staff.major.pac'))
    assert CAD.confusables(ItemId('cadence.staff.minor.half')) == ['cadence.staff.minor.phrygian']
