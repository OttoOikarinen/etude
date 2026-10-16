# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random
from collections.abc import Iterator

import pytest

from etude.core import Interval, Pitch
from etude.core.naming import NamingConvention, set_default_convention
from etude.exercises.base import ChoiceAnswer, Question
from etude.exercises.families.intervals import (
    ALTERED,
    COMPOUND,
    SIMPLE,
    TEACHING_ORDER,
    IntervalsEar,
    IntervalsStaff,
    Notes,
    choose_options,
    ear_item,
    interval_figure,
    parse_ear_item,
    parse_staff_item,
    semitones,
    staff_item,
)
from etude.notation.a11y import describe
from etude.notation.spec import Chord, Clef, StaffSpec

STAFF = IntervalsStaff()
EAR = IntervalsEar()
STAFF_DEFAULTS = STAFF.default_settings()
EAR_DEFAULTS = EAR.default_settings()
ALL_STAFF = {**STAFF_DEFAULTS, 'altered': True, 'compound': True}
ALL_EAR = {**EAR_DEFAULTS, 'form': 'both', 'direction': 'both', 'compound': True}
SEEDS = range(12)
WORDS = (
    'zero',
    'one',
    'two',
    'three',
    'four',
    'five',
    'six',
    'seven',
    'eight',
    'nine',
    'ten',
    'eleven',
    'twelve',
    'thirteen',
    'fourteen',
    'fifteen',
    'sixteen',
    'seventeen',
    'eighteen',
    'nineteen',
    'twenty',
    'twenty-one',
    'twenty-two',
    'twenty-three',
    'twenty-four',
)


def staff_questions(key: str, settings: dict[str, object] | None = None) -> Iterator[Question]:
    for seed in SEEDS:
        yield STAFF.generate(staff_item(key), settings or ALL_STAFF, random.Random(seed))


def options(question: Question) -> list[str]:
    assert isinstance(question.answer, ChoiceAnswer)
    return [o.key for o in question.answer.options]


def labels(question: Question) -> list[str]:
    assert isinstance(question.answer, ChoiceAnswer)
    return [o.label for o in question.answer.options]


def midis(question: Question) -> list[int]:
    assert question.playback is not None
    return [n.midi for n in question.playback.notes]


def design_question(*, descending: bool = False, harmonic: bool = False) -> Question:
    """Design 1d: G4 and E5 on a treble staff, a major sixth."""
    g4, e5 = Pitch.parse('G4'), Pitch.parse('E5')
    first, second = (e5, g4) if descending else (g4, e5)
    figure = interval_figure(Clef.TREBLE, first, second, harmonic=harmonic)
    pool = list(SIMPLE)
    return Question(
        'interval-staff',
        staff_item('M6'),
        'Name the interval',
        ChoiceAnswer(choose_options(pool, 'M6', random.Random(0), spare=pool, written=True)),
        'M6',
        figure=figure,
        playback=Notes(first, second, harmonic).playback(),
    )


# Items --------------------------------------------------------------------------------


def test_staff_teaching_order() -> None:
    assert STAFF.items(STAFF_DEFAULTS) == [staff_item(k) for k in TEACHING_ORDER]
    assert TEACHING_ORDER[:3] == ('P5', 'P8', 'M3')
    assert TEACHING_ORDER[-1] == 'TT'
    assert set(TEACHING_ORDER) == set(SIMPLE)


def test_augmented_and_diminished_replace_the_tritone() -> None:
    items = STAFF.items({**STAFF_DEFAULTS, 'altered': True})
    keys = [parse_staff_item(i) for i in items]
    assert 'TT' not in keys
    assert keys[: len(TEACHING_ORDER) - 1] == list(TEACHING_ORDER[:-1])
    assert keys[len(TEACHING_ORDER) - 1 :] == list(ALTERED)
    assert keys[-len(ALTERED) :][:2] == ['A4', 'd5']


def test_compound_intervals_come_last() -> None:
    keys = [parse_staff_item(i) for i in STAFF.items(ALL_STAFF)]
    assert keys[-len(COMPOUND) :] == list(COMPOUND)


def test_pool_setting_limits_items() -> None:
    items = STAFF.items({**STAFF_DEFAULTS, 'intervals': ('m6', 'M6', 'P5')})
    assert items == ['interval.staff.P5', 'interval.staff.M6', 'interval.staff.m6']


def test_ear_items_carry_form_and_direction() -> None:
    items = EAR.items(EAR_DEFAULTS)
    assert items[0] == 'interval.ear.melodic.asc.P5'
    assert all(i.startswith('interval.ear.melodic.asc.') for i in items)
    every = EAR.items({**EAR_DEFAULTS, 'form': 'both', 'direction': 'both'})
    assert len(every) == 3 * len(SIMPLE)
    assert 'interval.ear.melodic.desc.m6' in every
    assert 'interval.ear.harmonic.TT' in every
    # Ascending first, then descending, then harmonic.
    assert every.index('interval.ear.melodic.desc.P5') == len(SIMPLE)
    assert every.index('interval.ear.harmonic.P5') == 2 * len(SIMPLE)


def test_harmonic_only_ignores_direction() -> None:
    items = EAR.items({**EAR_DEFAULTS, 'form': 'harmonic', 'direction': 'desc'})
    assert all(i.startswith('interval.ear.harmonic.') for i in items)


@pytest.mark.parametrize('key', [*SIMPLE, *COMPOUND, *ALTERED])
def test_staff_item_ids_round_trip(key: str) -> None:
    assert parse_staff_item(staff_item(key)) == key


@pytest.mark.parametrize('variant', ['melodic.asc', 'melodic.desc', 'harmonic'])
@pytest.mark.parametrize('key', [*SIMPLE, *COMPOUND])
def test_ear_item_ids_round_trip(variant: str, key: str) -> None:
    assert parse_ear_item(ear_item(variant, key)) == (variant, key)


@pytest.mark.parametrize(
    'text', ['interval.staff.X9', 'interval.staff', 'interval.ear.M6', 'keysig.major.0']
)
def test_bad_staff_items_are_rejected(text: str) -> None:
    with pytest.raises(ValueError, match='not a staff interval item'):
        parse_staff_item(text)


@pytest.mark.parametrize(
    'text',
    [
        'interval.ear.melodic.M6',
        'interval.ear.harmonic.A4',
        'interval.ear.melodic.up.m6',
        'interval.staff.M6',
    ],
)
def test_bad_ear_items_are_rejected(text: str) -> None:
    with pytest.raises(ValueError, match='not an ear interval item'):
        parse_ear_item(text)


# The design question -------------------------------------------------------------------


def test_design_question_1d() -> None:
    question = design_question()
    right = STAFF.grade(question, 'M6')
    assert right.correct
    assert right.title == 'Correct — major sixth'
    assert right.detail == 'G4 to E5 spans six letter names and nine semitones.'
    wrong = STAFF.grade(question, 'm6')
    assert not wrong.correct
    assert wrong.title == 'Not quite — the answer is a major sixth'
    assert wrong.detail.startswith('G4 to E5 spans six letter names and nine semitones.')
    assert 'A minor sixth has eight semitones.' in wrong.detail
    assert wrong.play_expected == question.playback
    assert wrong.play_given is not None
    assert [n.midi for n in wrong.play_given.notes] == [67, 75]


def test_design_options_appear_for_a_major_sixth() -> None:
    """Design 1d: Minor third … Minor seventh, with the tritone between fourth and fifth."""
    expected = [
        'Minor third',
        'Major third',
        'Perfect fourth',
        'Tritone',
        'Perfect fifth',
        'Minor sixth',
        'Major sixth',
        'Minor seventh',
    ]
    seen = [labels(q) for q in staff_questions('M6', STAFF_DEFAULTS)]
    assert expected in seen
    question = next(q for q in staff_questions('M6', STAFF_DEFAULTS) if labels(q) == expected)
    assert isinstance(question.answer, ChoiceAnswer)
    assert [o.accel for o in question.answer.options] == [str(n) for n in range(1, 9)]
    assert question.prompt == 'Name the interval'
    assert STAFF.play_label == 'Play interval'


def test_design_figure_is_two_stemless_notes_with_a_bracket() -> None:
    figure = design_question().figure
    assert isinstance(figure, StaffSpec)
    assert len(figure.events) == 2
    assert all(isinstance(e, Chord) and e.duration is None for e in figure.events)
    assert [(b.first, b.last, b.label) for b in figure.brackets] == [(0, 1, '?')]


def test_descending_explanation_names_the_direction() -> None:
    question = design_question(descending=True)
    detail = STAFF.grade(question, 'M6').detail
    assert detail == 'E5 down to G4 spans six letter names and nine semitones.'
    assert midis(question) == [76, 67]
    given = STAFF.grade(question, 'P5').play_given
    assert given is not None
    assert [n.midi for n in given.notes] == [76, 69]


def test_harmonic_figure_stacks_the_notes() -> None:
    question = design_question(harmonic=True)
    figure = question.figure
    assert isinstance(figure, StaffSpec)
    assert len(figure.events) == 1
    chord = figure.events[0]
    assert isinstance(chord, Chord)
    assert [h.pitch for h in chord.heads] == [Pitch.parse('G4'), Pitch.parse('E5')]
    assert [(b.first, b.last) for b in figure.brackets] == [(0, 0)]
    assert question.playback is not None
    assert {n.start for n in question.playback.notes} == {0}
    given = STAFF.grade(question, 'M7').play_given
    assert given is not None
    assert sorted(n.midi for n in given.notes) == [67, 78]
    assert {n.start for n in given.notes} == {0}


# Musical facts for every interval ---------------------------------------------------------


@pytest.mark.parametrize('key', [*SIMPLE, *COMPOUND, *ALTERED])
def test_staff_figures_spell_the_interval(key: str) -> None:
    settings = ALL_STAFF if key != 'TT' else {**STAFF_DEFAULTS, 'compound': True}
    for question in staff_questions(key, settings):
        notes = Notes.of(question.figure)
        written = notes.interval
        if key == 'TT':
            assert str(written) in {'A4', 'd5'}
        else:
            assert written == Interval.parse(key)
        assert notes.high.midi - notes.low.midi == semitones(key)
        letters = WORDS[written.number]
        steps = WORDS[written.semitones]
        detail = STAFF.grade(question, key).detail
        assert f'spans {letters} letter names and {steps} semitone' in detail
        assert sorted(midis(question)) == sorted([notes.first.midi, notes.second.midi])
        if not notes.harmonic:
            assert midis(question) == [notes.first.midi, notes.second.midi]


@pytest.mark.parametrize('key', COMPOUND)
def test_compound_explanation_reduces_to_a_simple_interval(key: str) -> None:
    question = next(staff_questions(key))
    detail = STAFF.grade(question, key).detail
    simple = {
        'm9': 'minor second',
        'M9': 'major second',
        'm10': 'minor third',
        'M10': 'major third',
        'P11': 'perfect fourth',
        'P12': 'perfect fifth',
        'm13': 'minor sixth',
        'M13': 'major sixth',
    }[key]
    assert f'is a {simple} plus an octave.' in detail


def test_augmented_fourth_and_diminished_fifth_are_told_apart() -> None:
    for question in staff_questions('A4'):
        notes = Notes.of(question.figure)
        assert notes.interval.number == 4
        assert 'd5' in options(question)
        assert 'TT' not in options(question)
        wrong = STAFF.grade(question, 'd5')
        assert wrong.title == 'Not quite — the answer is an augmented fourth'
        assert 'four letter names and six semitones' in wrong.detail
        assert 'A diminished fifth spans five letter names.' in wrong.detail
    for question in staff_questions('d5'):
        assert Notes.of(question.figure).interval.number == 5
        wrong = STAFF.grade(question, 'A4')
        assert 'An augmented fourth spans four letter names.' in wrong.detail


def test_the_tritone_is_written_both_ways_and_explained() -> None:
    spellings = set()
    for question in staff_questions('TT', STAFF_DEFAULTS):
        written = Notes.of(question.figure).interval
        spellings.add(str(written))
        assert 'A4' not in options(question)
        assert 'd5' not in options(question)
        detail = STAFF.grade(question, 'TT').detail
        if written.number == 4:
            assert 'this tritone is an augmented fourth' in detail
        else:
            assert 'this tritone is a diminished fifth' in detail
    assert spellings == {'A4', 'd5'}


def test_comparisons_use_semitones_for_the_same_number() -> None:
    question = next(staff_questions('m3', STAFF_DEFAULTS))
    assert 'A major third has four semitones.' in STAFF.grade(question, 'M3').detail
    if 'P5' in options(question):
        assert 'A perfect fifth spans five letter names.' in STAFF.grade(question, 'P5').detail


def test_directions_and_forms_follow_settings() -> None:
    seen = set()
    for form in ('melodic', 'harmonic'):
        for direction in ('asc', 'desc'):
            settings = {**STAFF_DEFAULTS, 'form': form, 'direction': direction}
            for question in staff_questions('P4', settings):
                notes = Notes.of(question.figure)
                assert notes.harmonic is (form == 'harmonic')
                if form == 'melodic':
                    assert notes.descending is (direction == 'desc')
                seen.add((notes.harmonic, notes.descending))
    assert seen == {(False, False), (False, True), (True, False)}


def test_clefs_vary_with_settings_and_notes_stay_near_the_staff() -> None:
    settings = {**ALL_STAFF, 'clefs': ('alto', 'tenor')}
    clefs = set()
    for key in (*SIMPLE, *COMPOUND, *ALTERED):
        if key == 'TT':
            continue
        for question in staff_questions(key, settings):
            figure = question.figure
            assert isinstance(figure, StaffSpec)
            clefs.add(figure.clef)
            notes = Notes.of(figure)
            for pitch in (notes.low, notes.high):
                assert -4 <= figure.clef.staff_position(pitch) <= 12
    assert clefs == {Clef.ALTO, Clef.TENOR}


def test_no_accidentals_setting_writes_naturals() -> None:
    settings = {**STAFF_DEFAULTS, 'accidentals': 'none'}
    for key in SIMPLE:
        for question in staff_questions(key, settings):
            notes = Notes.of(question.figure)
            assert notes.low.alter == notes.high.alter == 0


def test_augmented_second_falls_back_to_accidentals() -> None:
    settings = {**ALL_STAFF, 'accidentals': 'none'}
    for question in staff_questions('A2', settings):
        notes = Notes.of(question.figure)
        assert notes.interval == Interval.parse('A2')
        assert max(abs(notes.low.alter), abs(notes.high.alter)) == 1


def test_single_accidentals_stay_single() -> None:
    for key in (*SIMPLE, *COMPOUND, *ALTERED):
        if key == 'TT':
            continue
        for question in staff_questions(key):
            notes = Notes.of(question.figure)
            assert abs(notes.low.alter) <= 1
            assert abs(notes.high.alter) <= 1


# Options -------------------------------------------------------------------------------


def test_options_are_a_numbered_window_in_order_of_size() -> None:
    order = list(SIMPLE)
    for key in SIMPLE:
        for question in staff_questions(key, STAFF_DEFAULTS):
            keys = options(question)
            assert len(keys) == 8
            assert key in keys
            start = order.index(keys[0])
            assert keys == order[start : start + 8]


def test_answer_position_varies() -> None:
    positions = {options(q).index('M3') for q in staff_questions('M3', STAFF_DEFAULTS)}
    assert len(positions) > 2


def test_small_pools_are_padded_with_neighbours() -> None:
    settings = {**STAFF_DEFAULTS, 'intervals': ('P5',)}
    question = STAFF.generate(staff_item('P5'), settings, random.Random(0))
    keys = options(question)
    assert len(keys) == 4
    assert 'P5' in keys
    assert {'TT', 'm6'} <= set(keys)


def test_a_review_from_another_pool_still_offers_its_answer() -> None:
    """An A4 card can come due after "Augmented and diminished" was turned off."""
    question = STAFF.generate(staff_item('A4'), STAFF_DEFAULTS, random.Random(0))
    assert 'A4' in options(question)
    assert 'TT' not in options(question)


# The staff description -------------------------------------------------------------------


def test_description_names_the_notes_but_not_the_interval() -> None:
    """A screen-reader user needs both notes to work out the interval, exactly as a
    sighted learner reads them; the interval itself is never named."""
    question = design_question()
    assert question.figure is not None
    text = describe(question.figure)
    assert text == 'Treble staff with two notes, G4 then E5.'
    for key in (*SIMPLE, *COMPOUND, *ALTERED):
        settings = ALL_STAFF if key != 'TT' else STAFF_DEFAULTS
        for q in staff_questions(key, settings):
            assert q.figure is not None
            text = describe(q.figure).lower()
            for word in ('second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'octave'):
                assert word not in text
            assert 'tritone' not in text


def test_harmonic_description() -> None:
    figure = design_question(harmonic=True).figure
    assert figure is not None
    assert describe(figure) == 'Treble staff with two notes sounding together, G4 and E5.'


def test_note_names_follow_the_convention() -> None:
    set_default_convention(NamingConvention.GERMAN_NORDIC)
    try:
        b4, d6 = Pitch.parse('Bb4'), Pitch.parse('D6')
        figure = interval_figure(Clef.TREBLE, b4, d6, harmonic=False)
        assert figure.description == 'Treble staff with two notes, B4 then D6.'
        h4 = interval_figure(Clef.TREBLE, Pitch.parse('B4'), d6, harmonic=False)
        assert h4.description == 'Treble staff with two notes, H4 then D6.'
    finally:
        set_default_convention(NamingConvention.ENGLISH)


# By ear --------------------------------------------------------------------------------


def ear_questions(variant: str, key: str) -> Iterator[Question]:
    for seed in SEEDS:
        yield EAR.generate(ear_item(variant, key), ALL_EAR, random.Random(seed))


@pytest.mark.parametrize('variant', ['melodic.asc', 'melodic.desc', 'harmonic'])
@pytest.mark.parametrize('key', [*SIMPLE, *COMPOUND])
def test_ear_playback_is_the_interval(variant: str, key: str) -> None:
    for question in ear_questions(variant, key):
        assert question.playback_is_question
        assert question.figure is None
        assert question.written_alternative is not None
        notes = Notes.of(question.written_alternative)
        assert question.playback is not None
        played = question.playback.notes
        if variant == 'harmonic':
            assert notes.harmonic
            assert {n.start for n in played} == {0}
            assert sorted(n.midi for n in played) == [notes.low.midi, notes.high.midi]
        else:
            assert played[0].start < played[1].start
            assert [n.midi for n in played] == [notes.first.midi, notes.second.midi]
            assert notes.descending is (variant == 'melodic.desc')
        assert notes.high.midi - notes.low.midi == semitones(key)
        assert notes.low.midi >= 41
        assert notes.high.midi <= 84
        assert abs(notes.low.alter) <= 1
        assert abs(notes.high.alter) <= 1
        assert question.playback.instrument.name == 'PIANO'


def test_ear_context_names_the_first_or_lower_note() -> None:
    asc = next(ear_questions('melodic.asc', 'M3'))
    assert asc.written_alternative is not None
    low = Notes.of(asc.written_alternative).low
    assert asc.context == f'Root: {low.symbol}'
    desc = next(ear_questions('melodic.desc', 'M3'))
    assert desc.written_alternative is not None
    first = Notes.of(desc.written_alternative).first
    assert desc.context == f'First note: {first.symbol}'


def test_ear_feedback_lets_the_learner_compare() -> None:
    for question in ear_questions('melodic.desc', 'm6'):
        wrong = EAR.grade(question, 'M6')
        assert wrong.title == 'Not quite — the answer is a minor sixth'
        assert 'A major sixth has nine semitones.' in wrong.detail
        assert wrong.play_expected == question.playback
        assert wrong.play_given is not None
        first = question.playback.notes[0].midi if question.playback else 0
        assert [n.midi for n in wrong.play_given.notes] == [first, first - 9]
        right = EAR.grade(question, 'm6')
        assert right.correct
        assert right.title == 'Correct — minor sixth'
        assert right.play_given is None


def test_ear_tritone_explanation_describes_the_sound() -> None:
    question = next(ear_questions('harmonic', 'TT'))
    detail = EAR.grade(question, 'TT').detail
    assert 'six semitones' in detail
    assert 'splits the octave exactly in half' in detail
    wrong = EAR.grade(question, 'P5')
    assert 'A perfect fifth has seven semitones.' in wrong.detail


def test_ear_options_are_ordered_by_size() -> None:
    for key in SIMPLE:
        for question in ear_questions('melodic.asc', key):
            sizes = [semitones(k) for k in options(question)]
            assert sizes == sorted(sizes)
            assert len(sizes) == len(set(sizes)) == 8


def test_design_ear_options_appear() -> None:
    """Design 1e: Minor second … Minor sixth for a major third."""
    expected = [
        'Minor second',
        'Major second',
        'Minor third',
        'Major third',
        'Perfect fourth',
        'Tritone',
        'Perfect fifth',
        'Minor sixth',
    ]
    seen = [
        labels(EAR.generate(ear_item('melodic.asc', 'M3'), EAR_DEFAULTS, random.Random(seed)))
        for seed in range(40)
    ]
    assert expected in seen


# Chrome ---------------------------------------------------------------------------------


def test_metadata_matches_the_design() -> None:
    assert STAFF.title == 'Intervals — Staff'
    assert EAR.title == 'Intervals — Ear'
    assert STAFF.glyph == '♫'
    assert EAR.glyph == '♪'
    assert EAR.play_label == 'Play interval'


def test_describe_settings() -> None:
    assert STAFF.describe_settings({**STAFF_DEFAULTS, 'clefs': ('treble',)}) == 'Treble clef'
    assert STAFF.describe_settings(ALL_STAFF) == (
        'Mixed clefs · augmented and diminished · compound'
    )
    assert EAR.describe_settings(EAR_DEFAULTS) == 'Melodic · ascending'
    assert EAR.describe_settings({**EAR_DEFAULTS, 'form': 'harmonic'}) == 'Harmonic'


def test_item_labels() -> None:
    assert STAFF.item_label(staff_item('M6')) == 'Major sixth (staff)'
    assert EAR.item_label(ear_item('melodic.asc', 'm6')) == 'Minor sixth (ear, ascending)'
    assert EAR.item_label(ear_item('harmonic', 'TT')) == 'Tritone (ear, harmonic)'


def test_confusables_keep_the_variant() -> None:
    assert 'interval.ear.melodic.asc.M6' in EAR.confusables(ear_item('melodic.asc', 'm6'))
    assert 'interval.ear.harmonic.P5' in EAR.confusables(ear_item('harmonic', 'TT'))
    assert 'interval.staff.d5' in STAFF.confusables(staff_item('A4'))
    registry_items = set(EAR.items(ALL_EAR))
    for item in registry_items:
        assert set(EAR.confusables(item)) <= registry_items
