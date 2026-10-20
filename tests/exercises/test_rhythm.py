# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random
from dataclasses import replace
from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from etude.audio.metronome import beats
from etude.audio.schedule import EventKind, build_schedule
from etude.core import Duration, Meter, NoteValue
from etude.exercises.base import ChoiceAnswer, RhythmInputAnswer, TapAnswer
from etude.exercises.families.rhythm import (
    COMPOUND_CELLS,
    DICTATION_DEFAULT,
    ED,
    METERS,
    QD,
    SIMPLE_CELLS,
    TAP_DEFAULT,
    D,
    E,
    H,
    MeterByEar,
    NoteValues,
    Q,
    RhythmDictation,
    RhythmTap,
    S,
    T,
    Vocabulary,
    W,
    as_rhythm,
    beat_matches,
    can_start,
    cell_pulses,
    generate_rhythm,
    note,
    onsets,
    palette_for,
    rest,
    rhythm_figure,
    rhythm_length,
    rhythm_words,
    serialize_rhythm,
    sound_grid,
    split_bars,
)
from etude.learning.rating import PARTIAL_CREDIT_PASS
from etude.notation.spec import Barline, BarStyle, Chord, Clef, Ink, Rest, StaffSpec

TAP = RhythmTap()
DICTATION = RhythmDictation()
VALUES = NoteValues()
METER_EAR = MeterByEar()
ALL_METERS = [*METERS.values(), Meter(9, 8), Meter(12, 8)]


# Generating rhythms ---------------------------------------------------------------


@settings(max_examples=300, deadline=None)
@given(
    vocabulary=st.sampled_from(list(Vocabulary)),
    meter=st.sampled_from(ALL_METERS),
    bars=st.integers(1, 2),
    seed=st.integers(0, 10_000),
)
def test_bars_are_always_full(vocabulary: Vocabulary, meter: Meter, bars: int, seed: int) -> None:
    rhythm = generate_rhythm(vocabulary, meter, bars, random.Random(seed))
    assert rhythm_length(rhythm) == meter.bar_length * bars
    split = split_bars(rhythm, meter)
    assert len(split) == bars
    for bar in split:
        assert rhythm_length(bar) == meter.bar_length, 'no note crosses a bar line'
        assert any(not is_rest for _d, is_rest in bar), 'every bar has a note'


@settings(max_examples=200, deadline=None)
@given(
    vocabulary=st.sampled_from(list(Vocabulary)),
    meter=st.sampled_from(ALL_METERS),
    seed=st.integers(0, 10_000),
)
def test_durations_are_valid_and_from_the_vocabulary(
    vocabulary: Vocabulary, meter: Meter, seed: int
) -> None:
    rhythm = generate_rhythm(vocabulary, meter, 2, random.Random(seed))
    table = COMPOUND_CELLS if meter.is_compound else SIMPLE_CELLS
    focal, fillers = table[vocabulary]
    allowed = {event for cell in (*focal, *fillers) for event in cell}
    for event in rhythm:
        assert event in allowed
        assert event[0].tuplet is None or vocabulary is Vocabulary.TRIPLETS
    # The practised figure appears somewhere.
    text = serialize_rhythm(rhythm)
    assert any(serialize_rhythm(cell) in text for cell in focal)


@settings(max_examples=200, deadline=None)
@given(
    vocabulary=st.sampled_from(list(Vocabulary)),
    meter=st.sampled_from(ALL_METERS),
    seed=st.integers(0, 10_000),
)
def test_cells_start_on_beats_and_keep_the_middle_of_the_bar_visible(
    vocabulary: Vocabulary, meter: Meter, seed: int
) -> None:
    rhythm = generate_rhythm(vocabulary, meter, 2, random.Random(seed))
    half = meter.bar_length / 2
    position = Fraction(0)
    for duration, _is_rest in rhythm:
        start, end = position % meter.bar_length, position % meter.bar_length + duration.length
        if len(meter.groups) % 2 == 0 and vocabulary is not Vocabulary.SYNCOPATION:
            # Only a note from the downbeat may hold over the middle of an even bar.
            assert not (start < half < end) or start == 0, serialize_rhythm(rhythm)
        if meter.is_compound and vocabulary is not Vocabulary.SYNCOPATION:
            # Nothing crosses a dotted-quarter beat except notes that start on one.
            pulse = meter.pulse
            crosses = start // pulse != (end - Fraction(1, 1024)) // pulse
            assert not crosses or start % pulse == 0, serialize_rhythm(rhythm)
        position += duration.length


def test_every_cell_fills_whole_beats() -> None:
    for meter, table in ((Meter(4, 4), SIMPLE_CELLS), (Meter(6, 8), COMPOUND_CELLS)):
        for focal, fillers in table.values():
            for cell in (*focal, *fillers):
                assert cell_pulses(cell, meter) is not None, cell


def test_alignment_rules() -> None:
    assert can_start(2, 0, 4)
    assert can_start(2, 2, 4)
    assert not can_start(2, 1, 4)
    assert can_start(2, 1, 3)
    assert not can_start(2, 1, 2)
    assert can_start(3, 0, 3)
    assert not can_start(3, 1, 4)
    assert can_start(4, 0, 4)
    assert not can_start(4, 0, 3)


def test_generation_is_deterministic_for_a_seed() -> None:
    a = generate_rhythm(Vocabulary.SIXTEENTHS, Meter(4, 4), 2, random.Random(7))
    b = generate_rhythm(Vocabulary.SIXTEENTHS, Meter(4, 4), 2, random.Random(7))
    assert a == b


def test_irregular_meters_are_refused() -> None:
    with pytest.raises(ValueError, match='irregular'):
        generate_rhythm(Vocabulary.EIGHTHS, Meter(7, 8), 1, random.Random(0))


def test_onsets_skip_rests() -> None:
    rhythm = (note(Q), rest(E), note(E), note(H))
    assert onsets(rhythm) == (0, Fraction(3, 2), 2)


def test_figure_is_a_one_line_percussion_staff_with_bar_lines() -> None:
    rhythm = (note(H), note(H), note(Q), rest(Q), note(H))
    figure = rhythm_figure(rhythm, Meter(4, 4))
    assert figure.clef is Clef.PERCUSSION
    assert figure.lines == 1
    assert figure.meter == Meter(4, 4)
    kinds = [type(e).__name__ for e in figure.events]
    assert kinds == ['Chord', 'Chord', 'Barline', 'Chord', 'Rest', 'Chord', 'Barline']
    assert figure.events[2] == Barline(BarStyle.SINGLE)
    assert figure.events[-1] == Barline(BarStyle.FINAL)
    assert figure.description == (
        'Rhythm in 4/4 time: half note, half note, bar line, quarter note, quarter rest, half note.'
    )


def test_words_and_serialisation() -> None:
    rhythm = (note(QD), note(E), rest(H))
    assert rhythm_words(rhythm) == 'dotted quarter note, eighth note, half rest'
    assert serialize_rhythm(rhythm) == '4. 8 r2'


# Tapping ------------------------------------------------------------------------------


def tap_question(item: str = 'rhythm.tap.eighths', seed: int = 3, **settings: object):
    return TAP.generate(item, {**TAP.default_settings(), **settings}, random.Random(seed))


def test_tap_question_matches_its_rhythm() -> None:
    question = tap_question(meters=('3/4',), **{'tempo-min': 60, 'tempo-max': 60})
    answer = question.answer
    assert isinstance(answer, TapAnswer)
    assert answer.meter == Meter(3, 4)
    assert answer.tempo == 60
    assert answer.count_in == 3
    assert answer.bars == 2
    assert answer.click
    assert question.context == '3/4 · ♩ = 60'
    figure = question.figure
    assert isinstance(figure, StaffSpec)
    assert figure.lines == 1
    # At 60 BPM a quarter beat is one second.
    playback = question.playback
    assert playback is not None
    expected = [float(n.start) * 1000 for n in playback.notes]
    assert list(question.expected) == pytest.approx(expected)
    assert all(n.percussion and n.midi == 76 for n in playback.notes)
    assert playback.count_in == 3
    assert playback.length == 6  # two bars of 3/4, even when the rhythm ends on a rest


def test_compound_tempo_counts_dotted_quarters() -> None:
    question = tap_question(meters=('6/8',), **{'tempo-min': 60, 'tempo-max': 60})
    answer = question.answer
    assert isinstance(answer, TapAnswer)
    assert answer.tempo == 90  # 60 dotted quarters a minute
    assert answer.count_in == 2
    assert question.context == '6/8 · ♩. = 60'


def test_tap_tempo_range_is_ordered_either_way() -> None:
    question = tap_question(**{'tempo-min': 100, 'tempo-max': 60})
    assert 60 <= question.answer.tempo <= 100


def test_perfect_taps() -> None:
    question = tap_question()
    feedback = TAP.grade(question, question.expected)
    assert feedback.correct
    assert feedback.score == 1.0
    assert feedback.title == 'Correct — every note on time'
    figure = feedback.figure
    assert isinstance(figure, StaffSpec)
    inks = {e.ink for e in figure.events if isinstance(e, Chord)}
    assert inks == {Ink.SUCCESS}


def test_slightly_late_taps_get_partial_credit() -> None:
    question = tap_question(**{'tempo-min': 80, 'tempo-max': 80})
    taps = list(question.expected)
    taps[2] += 70  # outside ±50 ms, inside ±100 ms
    feedback = TAP.grade(question, tuple(taps))
    total = len(taps)
    assert feedback.score == pytest.approx((total - 0.5) / total)
    assert feedback.correct == (feedback.score >= PARTIAL_CREDIT_PASS)
    assert f'{total - 1} of {total} notes on time' in feedback.title
    assert 'A little late: note 3.' in feedback.detail


def test_early_missing_and_extra_taps_are_explained() -> None:
    question = tap_question(**{'tempo-min': 80, 'tempo-max': 80})
    taps = list(question.expected)
    taps[0] -= 70
    del taps[3]
    taps.append(taps[-1] + 230)  # an extra tap between notes
    feedback = TAP.grade(question, tuple(sorted(taps)))
    assert 'A little early: note 1.' in feedback.detail
    assert 'No tap near note 4.' in feedback.detail
    assert '1 tap matched no note.' in feedback.detail
    figure = feedback.figure
    assert isinstance(figure, StaffSpec)
    chords = [e for e in figure.events if isinstance(e, Chord)]
    assert chords[3].ink is Ink.ERROR


def test_consistently_late_taps_mention_the_tendency() -> None:
    question = tap_question(**{'tempo-min': 80, 'tempo-max': 80})
    feedback = TAP.grade(question, tuple(t + 40 for t in question.expected))
    assert feedback.score == 1.0
    assert 'On average you tapped 40 ms late' in feedback.detail


def test_one_missed_note_of_four_is_not_enough() -> None:
    question = tap_question('rhythm.tap.quarters', bars=1, meters=('4/4',))
    assert len(question.expected) == 4
    feedback = TAP.grade(question, question.expected[:3])
    assert feedback.score == 0.75
    assert not feedback.correct
    assert feedback.title.startswith('Not quite — 3 of 4 notes on time')


def test_no_taps_and_junk_are_wrong() -> None:
    question = tap_question()
    for junk in ((), None, 'nonsense', (True, 'x')):
        feedback = TAP.grade(question, junk)
        assert not feedback.correct
        assert feedback.score == 0.0


def test_windows_scale_with_tempo() -> None:
    slow = tap_question('rhythm.tap.quarters', **{'tempo-min': 60, 'tempo-max': 60})
    fast = tap_question('rhythm.tap.quarters', **{'tempo-min': 160, 'tempo-max': 160})
    late = 45.0
    assert TAP.grade(slow, tuple(t + late for t in slow.expected)).score == 1.0
    assert TAP.grade(fast, tuple(t + late for t in fast.expected)).score < 1.0


def test_tap_labels_and_log() -> None:
    question = tap_question('rhythm.tap.quarters', bars=1, meters=('2/4',))
    assert TAP.answer_label(question, question.expected) == 'Quarter note, quarter note'
    assert TAP.answer_label(question, (1.0, 2.0, 3.0)) == '3 taps'
    assert TAP.serialize((12.4, 512.6)) == '12 513'
    feedback = TAP.grade(question, (10.0, 760.0))
    assert feedback.play_given is not None
    assert feedback.play_given.count_in == question.playback.count_in


def test_tap_items_and_settings_text() -> None:
    items = TAP.items(TAP.default_settings())
    assert items[0] == 'rhythm.tap.quarters'
    assert 'rhythm.tap.syncopation' not in items
    assert TAP.describe_settings(TAP.default_settings()) == '2/4, 3/4, 4/4 · 70–90 BPM'
    assert TAP.item_label('rhythm.tap.eighths') == 'Eighth notes — tapping'
    with pytest.raises(ValueError, match='polka'):
        TAP.generate('rhythm.tap.polka', TAP.default_settings(), random.Random(0))


def test_tap_phase_spec_counts_beats_through_the_bars() -> None:
    """What the tap pad plays: a count-in and the bars with the metronome only."""
    question = tap_question(meters=('4/4',), bars=2)
    answer = question.answer
    assert isinstance(answer, TapAnswer)
    from etude.audio.spec import PlaybackSpec

    spec = PlaybackSpec(
        (),
        answer.tempo,
        count_in=answer.count_in,
        click=answer.click,
        meter=answer.meter,
        duration=answer.meter.bar_length * 4 * answer.bars,
    )
    numbers = [b.number for b in beats(spec.meter, spec.count_in, spec.length)]
    assert numbers == [-4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7]
    schedule = build_schedule(spec)
    clicks = [e for e in schedule.events if e.kind is EventKind.NOTE_ON]
    assert len(clicks) == 12


# Dictation ------------------------------------------------------------------------------


def dictation_question(item: str = 'rhythm.dictation.eighths', seed: int = 1, **settings: object):
    defaults = DICTATION.default_settings()
    return DICTATION.generate(item, {**defaults, **settings}, random.Random(seed))


def test_dictation_question() -> None:
    question = dictation_question(meters=('4/4',))
    answer = question.answer
    assert isinstance(answer, RhythmInputAnswer)
    assert answer.meter == Meter(4, 4)
    assert answer.bars == 1
    assert question.playback_is_question
    assert not question.playback_style_choice
    assert question.written_alternative == rhythm_figure(question.expected, Meter(4, 4))
    durations = {d for d, _r in question.expected}
    assert durations <= set(answer.palette)
    assert list(answer.palette) == sorted(answer.palette, key=lambda d: -d.length)
    playback = question.playback
    assert playback is not None
    assert playback.count_in == 4
    assert playback.length == 4
    assert not any(n.percussion for n in playback.notes)


def test_palette() -> None:
    simple = palette_for([Vocabulary.EIGHTHS], Meter(2, 4))
    assert simple == (H, Q, E)
    assert W in palette_for([Vocabulary.HALVES], Meter(4, 4))
    assert W not in palette_for([Vocabulary.HALVES], Meter(3, 4))
    assert S in palette_for([Vocabulary.SIXTEENTHS], Meter(4, 4))
    assert QD in palette_for([Vocabulary.EIGHTHS], Meter(6, 8))


def test_sound_grid() -> None:
    assert ''.join(sound_grid((note(Q), note(E), rest(E)), 8)) == 'ASSSASRR'
    assert ''.join(sound_grid((note(Q),), 8)) == 'ASSS----'


def test_dictation_partial_credit_per_beat() -> None:
    expected = (note(Q), note(E), note(E), note(H))
    meter = Meter(4, 4)
    assert beat_matches(expected, expected, meter, 1) == [True] * 4
    # A quarter instead of two eighths: beat 2 is wrong, the rest still lines up.
    assert beat_matches(expected, (note(Q), note(Q), note(H)), meter, 1) == [
        True,
        False,
        True,
        True,
    ]
    # Two quarters instead of the half note: beat 3 sounds the same, beat 4 has an
    # attack that the half note does not.
    assert beat_matches(expected, (note(Q), note(E), note(E), note(Q), note(Q)), meter, 1) == [
        True,
        True,
        True,
        False,
    ]
    # Unfinished answers lose the beats they did not write.
    assert beat_matches(expected, (note(Q),), meter, 1) == [True, False, False, False]


def test_rests_that_sound_the_same_are_accepted() -> None:
    meter = Meter(4, 4)
    expected = (note(H), rest(H))
    assert beat_matches(expected, (note(H), rest(Q), rest(Q)), meter, 1) == [True] * 4
    # A note followed by a rest does not sound like a longer note.
    assert beat_matches((note(Q),) * 4, (note(E), rest(E), *(note(Q),) * 3), meter, 1)[0] is False


def test_dictation_grading() -> None:
    question = dictation_question('rhythm.dictation.halves', meters=('4/4',), bars=2)
    right = DICTATION.grade(question, question.expected)
    assert right.correct
    assert right.score == 1.0
    assert right.title == 'Correct — every beat right'
    # One beat of eight changed: still a pass (partial credit), but not perfect.
    expected = (note(H), note(Q), note(Q), note(W))
    question = replace(question, expected=expected)
    nearly = DICTATION.grade(question, (note(H), note(Q), note(E), note(E), note(W)))
    assert nearly.score == pytest.approx(7 / 8)
    assert nearly.correct
    assert nearly.title.startswith('Nearly — 7 of 8 beats right')
    assert 'Beat 4: you heard quarter note; you wrote eighth note, eighth note.' in nearly.detail
    wrong = DICTATION.grade(question, ())
    assert not wrong.correct
    assert wrong.score == 0.0
    assert 'you wrote nothing' in wrong.detail
    assert wrong.play_given is None


def test_dictation_feedback_marks_the_beats() -> None:
    question = dictation_question('rhythm.dictation.eighths', meters=('2/4',), seed=4)
    expected = question.expected
    feedback = DICTATION.grade(question, ((Duration(NoteValue.HALF), False),))
    figure = feedback.figure
    assert isinstance(figure, StaffSpec)
    marks = [e.ink for e in figure.events if isinstance(e, Chord | Rest)]
    assert len(marks) == len(expected)
    assert Ink.ERROR in marks
    assert 'Beat ' in feedback.detail
    assert feedback.play_given is not None


def test_dictation_values_and_labels() -> None:
    question = dictation_question(meters=('2/4',))
    assert as_rhythm([(Q, False), (Q, True)]) == ((Q, False), (Q, True))
    assert as_rhythm([(Q, 'no')]) == ()
    assert DICTATION.answer_label(question, ()) == 'Nothing written'
    assert DICTATION.serialize(((Q, False), (E, True), (E, False))) == '4 r8 8'
    assert DICTATION.item_label('rhythm.dictation.rests') == 'Rests — dictation'
    assert 'rhythm.dictation.quarters' not in DICTATION.items(DICTATION.default_settings())


# Note values -------------------------------------------------------------------------------


def test_note_value_questions_hide_the_answer_from_screen_readers() -> None:
    for item in VALUES.items(VALUES.default_settings()):
        question = VALUES.generate(item, VALUES.default_settings(), random.Random(0))
        figure = question.figure
        assert isinstance(figure, StaffSpec)
        assert figure.description is not None
        assert 'note' not in figure.description.replace('note symbol', '')
        assert isinstance(question.answer, ChoiceAnswer)


@pytest.mark.parametrize(
    ('item', 'expected'),
    [
        ('notevalue.beats.whole', '4'),
        ('notevalue.beats.dotted-half', '3'),
        ('notevalue.beats.dotted-quarter', '3/2'),
        ('notevalue.beats.eighth', '1/2'),
        ('notevalue.beats.dotted-eighth', '3/4'),
        ('notevalue.beats.sixteenth', '1/4'),
    ],
)
def test_beats_in_four_four(item: str, expected: str) -> None:
    question = VALUES.generate(item, VALUES.default_settings(), random.Random(0))
    assert question.expected == expected
    assert isinstance(question.figure, StaffSpec)
    assert question.figure.meter == Meter(4, 4)


def test_note_value_figures_and_feedback() -> None:
    question = VALUES.generate('notevalue.rest.half', VALUES.default_settings(), random.Random(0))
    assert isinstance(question.figure, StaffSpec)
    assert question.figure.events == (Rest(H),)
    labels = [o.label for o in question.answer.options]
    assert labels == ['Whole rest', 'Half rest', 'Quarter rest', 'Eighth rest', 'Sixteenth rest']
    feedback = VALUES.grade(question, 'whole')
    assert feedback.title == 'Not quite — the answer is half rest'
    assert 'sits on top of a line' in feedback.detail
    assert VALUES.confusables('notevalue.rest.half') == ('notevalue.rest.whole',)
    dotted = VALUES.generate(
        'notevalue.note.dotted-half', VALUES.default_settings(), random.Random(0)
    )
    assert (
        'The dot adds half the value of the half note: 3 beats'
        in VALUES.grade(dotted, 'dotted-half').detail
    )
    # The playback holds the value after a count-in, with the click running.
    playback = question.playback
    assert playback is not None
    assert not playback.notes
    assert playback.length == 2


def test_note_value_settings_narrow_the_items() -> None:
    items = VALUES.items({'kinds': ('rests',), 'dotted': True, 'sixteenths': False})
    assert items == [
        'notevalue.rest.whole',
        'notevalue.rest.half',
        'notevalue.rest.quarter',
        'notevalue.rest.eighth',
    ]
    items = VALUES.items({'kinds': ('notes',), 'dotted': False, 'sixteenths': True})
    assert 'notevalue.note.dotted-half' not in items


# Meter by ear ---------------------------------------------------------------------------------


@pytest.mark.parametrize('kind', ['duple', 'triple', 'quadruple'])
def test_meter_playback_stresses_the_downbeats(kind: str) -> None:
    question = METER_EAR.generate(
        f'meter.ear.{kind}', METER_EAR.default_settings(), random.Random(2)
    )
    playback = question.playback
    assert playback is not None
    assert playback.count_in == 0, 'a count-in would give the meter away'
    meter = playback.meter
    assert meter is not None
    bar = meter.bar_length * 4
    drums = [n.start for n in playback.notes if n.midi == 36]
    assert drums == [bar * i for i in range(4)]
    alternative = question.written_alternative
    assert isinstance(alternative, StaffSpec)
    assert alternative.meter is None, 'the time signature would give the answer away'
    assert sum(isinstance(e, Barline) for e in alternative.events) == 4
    feedback = METER_EAR.grade(question, kind)
    assert feedback.correct
    assert isinstance(feedback.figure, StaffSpec)
    assert feedback.figure.meter == meter
    assert [o.accel for o in question.answer.options] == ['2', '3', '4']


def test_compound_meter_choice() -> None:
    settings = {**METER_EAR.default_settings(), 'compound': True}
    assert len(METER_EAR.items(settings)) == 6
    question = METER_EAR.generate('meter.ear.compound-duple', settings, random.Random(0))
    assert len(question.answer.options) == 6
    feedback = METER_EAR.grade(question, 'duple')
    assert not feedback.correct
    assert 'three eighths' in feedback.detail


# Level 2: dotted eighths, triplets, duplets and 9/8, 12/8 -------------------------------


def test_level_two_vocabulary_keeps_level_one_ids_and_defaults() -> None:
    assert [v.value for v in Vocabulary][:7] == [
        'quarters',
        'halves',
        'eighths',
        'rests',
        'dotted-quarter',
        'sixteenths',
        'syncopation',
    ]
    assert Vocabulary.DOTTED_EIGHTH.value == 'dotted-eighth'
    assert Vocabulary.TRIPLETS.value == 'triplets'
    for vocabulary in ('syncopation', 'dotted-eighth', 'triplets'):
        assert vocabulary not in TAP_DEFAULT
        assert vocabulary not in DICTATION_DEFAULT
    assert 'rhythm.tap.triplets' in TAP.items({'vocabulary': ('triplets',)})
    assert 'rhythm.dictation.dotted-eighth' in DICTATION.items({'vocabulary': ('dotted-eighth',)})


def test_triplets_fill_a_beat_and_duplets_a_dotted_quarter() -> None:
    assert rhythm_length((note(T),) * 3) == Fraction(1, 4)
    assert rhythm_length((note(D),) * 2) == Fraction(3, 8)
    assert rhythm_length((note(ED), note(S))) == Fraction(1, 4)
    rhythm = generate_rhythm(Vocabulary.TRIPLETS, Meter(6, 8), 1, random.Random(1))
    assert note(D) in rhythm
    assert note(T) not in rhythm
    rhythm = generate_rhythm(Vocabulary.TRIPLETS, Meter(4, 4), 1, random.Random(1))
    assert note(T) in rhythm
    assert note(D) not in rhythm


def test_triplet_names_and_serialisation() -> None:
    assert rhythm_words((note(T), note(T), note(T))) == (
        'triplet eighth note, triplet eighth note, triplet eighth note'
    )
    assert serialize_rhythm((note(T), note(D), note(ED), note(S))) == '8/3 8/2 8. 16'


def test_triplet_dictation_is_graded_on_a_finer_grid() -> None:
    meter = Meter(2, 4)
    expected = (note(T), note(T), note(T), note(Q))
    assert beat_matches(expected, expected, meter, 1) == [True, True]
    eighths = (note(E), note(E), note(Q))
    assert beat_matches(expected, eighths, meter, 1) == [False, True]
    # Without tuplets the sixteenth grid is unchanged.
    assert ''.join(sound_grid((note(ED), note(S)), 4)) == 'ASSA'


def test_compound_meters_are_offered() -> None:
    assert METERS['9/8'] == Meter(9, 8)
    assert METERS['12/8'] == Meter(12, 8)
    question = DICTATION.generate(
        'rhythm.dictation.triplets',
        {**DICTATION.default_settings(), 'meters': ('12/8',)},
        random.Random(0),
    )
    assert isinstance(question.answer, RhythmInputAnswer)
    assert question.answer.meter == Meter(12, 8)
    assert D in question.answer.palette
    assert DICTATION.grade(question, question.expected).correct
