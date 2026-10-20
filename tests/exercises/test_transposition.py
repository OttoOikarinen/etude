# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random

import pytest

from etude.core import Interval, KeySignature, Pitch
from etude.exercises.base import Question, StaffInputAnswer
from etude.exercises.families.transposition import (
    INSTRUMENTS,
    INTERVALS,
    Transposition,
    instrument_item,
    item_id,
    parse_item,
)
from etude.learning.model import ItemId
from etude.notation.spec import Chord as StaffChord
from etude.notation.spec import Clef, StaffSpec

TR = Transposition()
DEFAULTS = TR.default_settings()
ALL = {
    **DEFAULTS,
    'intervals': INTERVALS,
    'instruments': True,
    'instrument-direction': 'both',
    'max-accidentals': 7,
}
SEEDS = range(12)


def original(question: Question) -> list[Pitch]:
    figure = question.figure
    assert isinstance(figure, StaffSpec)
    return [e.heads[0].pitch for e in figure.events if isinstance(e, StaffChord)]


def answer(question: Question) -> list[Pitch]:
    assert isinstance(question.expected, tuple)
    return [chord[0] for chord in question.expected]


def staff_answer(question: Question) -> StaffInputAnswer:
    assert isinstance(question.answer, StaffInputAnswer)
    return question.answer


def test_item_ids() -> None:
    assert item_id('interval', 'up', 'M2') == 'transpose.interval.up.M2'
    assert instrument_item('f-horn', 'concert') == 'transpose.instrument.f-horn.concert'
    assert parse_item('transpose.key.down.m3') == ('key', 'down', 'm3')
    for bad in (
        'transpose.key.sideways.M2',
        'transpose.interval.up.P8',
        'transpose.instrument.oboe.concert',
    ):
        with pytest.raises(ValueError, match='not a'):
            parse_item(bad)


def test_items_follow_the_settings() -> None:
    items = list(TR.items(DEFAULTS))
    assert items[:4] == [
        'transpose.key.up.M2',
        'transpose.key.down.M2',
        'transpose.interval.up.M2',
        'transpose.interval.down.M2',
    ]
    assert not any('instrument' in i for i in items)
    assert TR.items(
        {**DEFAULTS, 'methods': ('interval',), 'intervals': ('P5',), 'direction': 'up'}
    ) == ['transpose.interval.up.P5']
    instruments = [i for i in TR.items(ALL) if 'instrument' in i]
    assert len(instruments) == 2 * len(INSTRUMENTS)
    assert TR.items({**DEFAULTS, 'instruments': True})[-3:] == [
        'transpose.instrument.bb-clarinet.concert',
        'transpose.instrument.f-horn.concert',
        'transpose.instrument.eb-alto-sax.concert',
    ]


@pytest.mark.parametrize('key', INTERVALS)
def test_every_note_moves_by_the_interval(key: str) -> None:
    interval = Interval.parse(key)
    for method in ('interval', 'key'):
        for direction in ('up', 'down'):
            item = item_id(method, direction, key)
            for seed in SEEDS:
                question = TR.generate(item, ALL, random.Random(seed))
                before, after = original(question), answer(question)
                assert 3 <= len(before) <= 6
                assert len(after) == len(before)
                assert staff_answer(question).slots == len(after)
                for a, b in zip(before, after, strict=True):
                    low, high = (a, b) if direction == 'up' else (b, a)
                    assert Interval.between(low, high) == interval
                # The melody's own intervals are kept, spelling included.
                for i in range(len(before) - 1):
                    lo, hi = sorted((before[i], before[i + 1]))
                    lo2, hi2 = sorted((after[i], after[i + 1]))
                    if lo != hi:
                        assert Interval.between(lo, hi) == Interval.between(lo2, hi2)


@pytest.mark.parametrize('key', INTERVALS)
def test_key_signatures(key: str) -> None:
    interval = Interval.parse(key)
    for direction in ('up', 'down'):
        for seed in SEEDS:
            by_key = TR.generate(item_id('key', direction, key), ALL, random.Random(seed))
            figure = by_key.figure
            assert isinstance(figure, StaffSpec)
            source, target = figure.key_signature, staff_answer(by_key).key_signature
            assert source is not None
            assert target is not None
            # The target signature is the source key's tonic moved by the interval.
            tonic = source.major_tonic.transpose(interval, down=direction == 'down')
            assert target == KeySignature.for_major(tonic)
            # Every note of the answer is diatonic in the new key, or the raised seventh.
            for pitch in answer(by_key):
                implied = target.alter_for(pitch.letter)
                assert pitch.alter in (implied, implied + 1)
            by_interval = TR.generate(item_id('interval', direction, key), ALL, random.Random(seed))
            assert by_interval.figure.key_signature is None  # type: ignore[union-attr]
            assert staff_answer(by_interval).key_signature is None


def test_accidentals_limit() -> None:
    settings = {**ALL, 'max-accidentals': 2}
    for item in TR.items(settings):
        for seed in range(4):
            question = TR.generate(item, settings, random.Random(seed))
            figure = question.figure
            assert isinstance(figure, StaffSpec)
            # Keys a minor second apart differ by five accidentals: then the limit is 3.
            limit = 3 if item.endswith('.m2') else 2
            for signature in (figure.key_signature, staff_answer(question).key_signature):
                if signature is not None:
                    assert signature.count <= limit
            assert all(abs(p.alter) <= 1 for p in original(question) + answer(question))


@pytest.mark.parametrize(
    ('instrument', 'interval', 'fifths'),
    [('bb-clarinet', 'M2', 2), ('f-horn', 'P5', 1), ('eb-alto-sax', 'M6', 3)],
)
def test_transposing_instruments(instrument: str, interval: str, fifths: int) -> None:
    step = Interval.parse(interval)
    for seed in SEEDS:
        concert = TR.generate(instrument_item(instrument, 'concert'), ALL, random.Random(seed))
        written, sounding = original(concert), answer(concert)
        assert all(
            w.transpose(step, down=True) == s for w, s in zip(written, sounding, strict=True)
        )
        written_signature = concert.figure.key_signature  # type: ignore[union-attr]
        concert_signature = staff_answer(concert).key_signature
        assert written_signature is not None
        assert concert_signature is not None
        # A B♭ part has two more sharps (fewer flats) than concert pitch, and so on.
        assert written_signature.fifths - concert_signature.fifths == fifths
        assert concert.figure.clef is Clef.TREBLE  # type: ignore[union-attr]
        assert concert.playback is not None
        assert [n.midi for n in concert.playback.notes] == [p.midi for p in sounding]

        part = TR.generate(instrument_item(instrument, 'written'), ALL, random.Random(seed))
        heard, to_write = original(part), answer(part)
        assert all(h.transpose(step) == w for h, w in zip(heard, to_write, strict=True))
        assert staff_answer(part).clef is Clef.TREBLE
        assert part.playback is not None
        assert [n.midi for n in part.playback.notes] == [p.midi for p in heard]


def test_melodies_fit_the_staff() -> None:
    for item in TR.items(ALL):
        for seed in range(4):
            question = TR.generate(item, ALL, random.Random(seed))
            figure = question.figure
            assert isinstance(figure, StaffSpec)
            target = staff_answer(question).clef
            for clef, pitches in ((figure.clef, original(question)), (target, answer(question))):
                positions = [clef.staff_position(p) for p in pitches]
                assert min(positions) >= -4
                assert max(positions) <= 12


def find(item: str, settings: dict[str, object] = ALL) -> Question:
    return TR.generate(ItemId(item), settings, random.Random(5))


def test_feedback_for_a_correct_answer() -> None:
    question = find('transpose.interval.up.M2')
    feedback = TR.grade(question, question.expected)
    assert feedback.correct
    assert feedback.score == 1
    assert feedback.title.startswith('Correct — ')
    assert 'Every note moves up a major second, two letter names and two semitones' in (
        feedback.detail
    )
    key_question = find('transpose.key.down.m3')
    detail = TR.grade(key_question, key_question.expected).detail
    assert 'moves down a minor third to' in detail
    assert 'keeps its scale degree' in detail
    assert key_question.context.startswith('From ')
    horn = find('transpose.instrument.f-horn.concert')
    detail = TR.grade(horn, horn.expected).detail
    assert detail.startswith('The horn in F sounds a perfect fifth lower than written')
    assert horn.prompt == 'Write this horn in F part at concert pitch'


def test_feedback_names_wrong_notes() -> None:
    question = find('transpose.interval.up.m3')
    notes = answer(question)
    first = notes[0]
    enharmonic = next(p for p in first.enharmonics(max_alter=2) if p != first)
    wrong_letter = Pitch.from_diatonic(notes[1].diatonic_index + 1, notes[1].midi + 2)
    given = ((enharmonic,), (wrong_letter,), *((p,) for p in notes[2:]))
    feedback = TR.grade(question, given)
    assert not feedback.correct
    assert feedback.score == pytest.approx((len(notes) - 2) / len(notes))
    assert 'Note 1: ' in feedback.detail
    assert 'sounds right, but the transposed note' in (feedback.detail)
    assert 'Note 2: ' in feedback.detail
    assert feedback.play_given is not None
    assert feedback.play_expected is not None
    accidental = Pitch(notes[2].letter, notes[2].alter + 1, notes[2].octave)
    given = (*((p,) for p in notes[:2]), (accidental,), *((p,) for p in notes[3:]))
    assert 'has the right letter name but needs' in TR.grade(question, given).detail
    assert TR.grade(question, ()).score == 0


def test_labels_and_confusables() -> None:
    assert TR.item_label(ItemId('transpose.key.up.M2')) == 'Major second up, into a key'
    assert TR.item_label(ItemId('transpose.interval.down.P4')) == 'Perfect fourth down, by interval'
    assert (
        TR.item_label(ItemId('transpose.instrument.bb-clarinet.concert'))
        == 'B♭ clarinet to concert pitch'
    )
    assert TR.confusables(ItemId('transpose.interval.up.M3')) == [
        'transpose.interval.up.m3',
        'transpose.interval.down.M3',
    ]
    assert TR.describe_settings(DEFAULTS) == 'Into keys · by intervals · 4 notes'
