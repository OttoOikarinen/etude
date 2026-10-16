# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random
from collections.abc import Mapping

import pytest

from etude.audio.spec import Instrument
from etude.core import Chord, ChordQuality, Letter, Pitch, PitchName
from etude.exercises.base import ChipsAnswer, ChoiceAnswer, Question
from etude.exercises.families.chords import (
    INVERSIONS,
    ChordQualityEar,
    ChordsStaff,
    chord_playback,
    ear_item,
    parse_ear_item,
    parse_staff_item,
    root_value,
    staff_item,
    voicing,
)
from etude.learning.model import ItemId
from etude.notation.a11y import describe
from etude.notation.spec import Chord as Chord_
from etude.notation.spec import Clef, Figure, Ink, StaffSpec

STAFF = ChordsStaff()
EAR = ChordQualityEar()
STAFF_DEFAULTS = STAFF.default_settings()
EAR_DEFAULTS = EAR.default_settings()
ALL_STAFF = {**STAFF_DEFAULTS, 'sevenths': True, 'roots': 'all'}

QUALITIES = {
    'major': ChordQuality.MAJOR,
    'minor': ChordQuality.MINOR,
    'dim': ChordQuality.DIMINISHED,
    'aug': ChordQuality.AUGMENTED,
    'dom7': ChordQuality.DOMINANT_SEVENTH,
    'maj7': ChordQuality.MAJOR_SEVENTH,
    'min7': ChordQuality.MINOR_SEVENTH,
    'hdim7': ChordQuality.HALF_DIMINISHED_SEVENTH,
    'dim7': ChordQuality.DIMINISHED_SEVENTH,
}


def figure_pitches(figure: Figure | None) -> list[Pitch]:
    assert isinstance(figure, StaffSpec)
    return [
        head.pitch for event in figure.events if isinstance(event, Chord_) for head in event.heads
    ]


def staff_pitches(question: Question) -> list[Pitch]:
    return figure_pitches(question.figure)


def expected_map(question: Question) -> Mapping[str, str]:
    assert isinstance(question.expected, Mapping)
    return question.expected


def chord_of(question: Question) -> Chord:
    quality, inversion = parse_staff_item(question.item_id)
    root = PitchName.parse(expected_map(question)['root'])
    return Chord(root, QUALITIES[quality], inversion)


def find_question(item: str, settings: Mapping[str, object], **wanted: object) -> Question:
    """The first seeded question whose expected answer and clef match ``wanted``."""
    clef = wanted.pop('clef', None)
    for seed in range(500):
        question = STAFF.generate(item, settings, random.Random(seed))
        expected = expected_map(question)
        figure = question.figure
        assert isinstance(figure, StaffSpec)
        if all(expected.get(k) == v for k, v in wanted.items()) and clef in (None, figure.clef):
            return question
    raise AssertionError(f'no question for {item} with {wanted}')


# Items -------------------------------------------------------------------------------


def test_item_ids_round_trip() -> None:
    for quality, chord_quality in QUALITIES.items():
        for inversion in range(chord_quality.size):
            assert parse_staff_item(staff_item(quality, inversion)) == (quality, inversion)
        assert parse_ear_item(ear_item(quality)) == quality


@pytest.mark.parametrize(
    'text',
    ['chord.staff.minor.third', 'chord.staff.sus4.root', 'chord.staff.minor', 'chord.ear.x'],
)
def test_bad_item_ids_are_rejected(text: str) -> None:
    parse = parse_ear_item if text.startswith('chord.ear.') else parse_staff_item
    with pytest.raises(ValueError, match='not a chord item'):
        parse(text)


def test_teaching_order() -> None:
    """Major and minor in root position, their inversions, then dim/aug, then sevenths."""
    items = STAFF.items({**STAFF_DEFAULTS, 'sevenths': True})
    assert items[:8] == [
        'chord.staff.major.root',
        'chord.staff.minor.root',
        'chord.staff.major.first',
        'chord.staff.minor.first',
        'chord.staff.major.second',
        'chord.staff.minor.second',
        'chord.staff.dim.root',
        'chord.staff.aug.root',
    ]
    assert items[12:14] == ['chord.staff.dom7.root', 'chord.staff.maj7.root']
    assert items[-1] == 'chord.staff.dim7.third'
    assert len(items) == 4 * 3 + 5 * 4


def test_root_position_only() -> None:
    settings = {**STAFF_DEFAULTS, 'inversions': False}
    items = STAFF.items(settings)
    assert items == [
        'chord.staff.major.root',
        'chord.staff.minor.root',
        'chord.staff.dim.root',
        'chord.staff.aug.root',
    ]
    question = STAFF.generate(items[0], settings, random.Random(0))
    assert isinstance(question.answer, ChipsAnswer)
    assert [g.key for g in question.answer.groups] == ['root', 'quality']
    assert set(expected_map(question)) == {'root', 'quality'}


def test_items_outside_the_settings_still_generate() -> None:
    """A review of an inverted seventh chord after sevenths and inversions were turned off."""
    settings = {**STAFF_DEFAULTS, 'inversions': False}
    question = STAFF.generate('chord.staff.dom7.third', settings, random.Random(0))
    assert isinstance(question.answer, ChipsAnswer)
    keys = {g.key: [o.key for o in g.options] for g in question.answer.groups}
    assert 'dom7' in keys['quality']
    assert keys['inversion'] == list(INVERSIONS)
    assert STAFF.grade(question, question.expected).correct


# The design question (1f) --------------------------------------------------------------


def test_design_question() -> None:
    """Design 1f: E minor in root position on a treble staff, answered with chips."""
    settings = {**STAFF_DEFAULTS, 'clefs': ('treble',)}
    question = find_question('chord.staff.minor.root', settings, root='E')
    assert question.prompt == 'Name the chord'
    assert question.expected == {'root': 'E', 'quality': 'minor', 'inversion': 'root'}
    assert [p.name for p in staff_pitches(question)] == [PitchName.parse(n) for n in 'EGB']

    answer = question.answer
    assert isinstance(answer, ChipsAnswer)
    root, quality, inversion = answer.groups
    assert (root.key, root.label, root.accidentals) == ('root', 'Root', True)
    assert [(o.key, o.label, o.accel) for o in root.options] == [
        (letter.name, letter.name, letter.name.lower()) for letter in Letter
    ]
    assert (quality.key, quality.label) == ('quality', 'Quality')
    assert [(o.key, o.label, o.accel) for o in quality.options] == [
        ('major', 'Major', '1'),
        ('minor', 'Minor', '2'),
        ('dim', 'Diminished', '3'),
        ('aug', 'Augmented', '4'),
    ]
    assert (inversion.key, inversion.label) == ('inversion', 'Inversion')
    assert [(o.key, o.label, o.accel) for o in inversion.options] == [
        ('root', 'Root position', '5'),
        ('first', 'First', '6'),
        ('second', 'Second', '7'),
    ]

    feedback = STAFF.grade(question, {'root': 'E', 'quality': 'minor', 'inversion': 'root'})
    assert feedback.correct
    assert feedback.score == 1
    assert feedback.title == 'Correct — E minor triad, root position'
    assert feedback.detail == (
        'E–G–B: a minor third and a perfect fifth above E. '
        'The root, E, is in the bass: root position.'
    )
    assert STAFF.play_label == 'Play chord'
    assert STAFF.describe_settings(settings) == 'Treble clef · triads'


@pytest.mark.parametrize('settings', [STAFF_DEFAULTS, ALL_STAFF])
def test_accelerators_are_unique_across_groups(settings: Mapping[str, object]) -> None:
    question = STAFF.generate('chord.staff.major.root', settings, random.Random(0))
    assert isinstance(question.answer, ChipsAnswer)
    accels = [o.accel for g in question.answer.groups for o in g.options]
    assert None not in accels
    assert len(accels) == len(set(accels))
    # The root letters are a–g; the other groups must not steal them (or R, replay).
    others = [o.accel for g in question.answer.groups[1:] for o in g.options]
    assert not set(others) & set('abcdefgr')


def test_seventh_chords_offer_a_third_inversion() -> None:
    question = STAFF.generate('chord.staff.min7.third', ALL_STAFF, random.Random(0))
    assert isinstance(question.answer, ChipsAnswer)
    _root, quality, inversion = question.answer.groups
    assert [o.key for o in quality.options] == list(QUALITIES)
    assert [o.accel for o in quality.options] == [str(n) for n in range(1, 10)]
    assert [o.key for o in inversion.options] == list(INVERSIONS)
    assert [o.label for o in quality.options][4:] == [
        'Dominant 7th',
        'Major 7th',
        'Minor 7th',
        'Half-diminished',
        'Diminished 7th',
    ]


# Musical facts ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('root', 'quality', 'notes'),
    [
        ('Bb', ChordQuality.DIMINISHED, 'Bb Db Fb'),
        ('C', ChordQuality.AUGMENTED, 'C E G#'),
        ('Ab', ChordQuality.AUGMENTED, 'Ab C E'),
        ('G#', ChordQuality.AUGMENTED, 'G# B# D##'),
        ('F#', ChordQuality.HALF_DIMINISHED_SEVENTH, 'F# A C E'),
        ('Db', ChordQuality.DIMINISHED_SEVENTH, 'Db Fb Abb Cbb'),
        ('E', ChordQuality.DOMINANT_SEVENTH, 'E G# B D'),
        ('Eb', ChordQuality.MAJOR_SEVENTH, 'Eb G Bb D'),
        ('C#', ChordQuality.MINOR, 'C# E G#'),
    ],
)
def test_spelling(root: str, quality: ChordQuality, notes: str) -> None:
    """The staff shows chord tones spelled from the root, whatever the inversion."""
    key = next(k for k, q in QUALITIES.items() if q is quality)
    wanted = {PitchName.parse(n) for n in notes.split()}
    for inversion in range(quality.size):
        item = staff_item(key, inversion)
        question = find_question(item, ALL_STAFF, root=root)
        names = [p.name for p in staff_pitches(question)]
        assert set(names) == wanted
        assert len(names) == quality.size


@pytest.mark.parametrize('key', list(QUALITIES))
def test_every_question_shows_its_chord(key: str) -> None:
    """Notes, bass, register and spelling of every inversion, voicing and clef."""
    quality = QUALITIES[key]
    settings = {**ALL_STAFF, 'open': True, 'clefs': ('treble', 'bass', 'alto', 'tenor')}
    for inversion in range(quality.size):
        for seed in range(40):
            question = STAFF.generate(staff_item(key, inversion), settings, random.Random(seed))
            chord = chord_of(question)
            pitches = staff_pitches(question)
            assert sorted(map(str, (p.name for p in pitches))) == sorted(map(str, chord.names()))
            assert all(abs(p.alter) <= 2 for p in pitches)
            assert min(pitches) == pitches[0]
            assert pitches[0].name == chord.bass
            assert pitches == sorted(pitches)
            figure = question.figure
            assert isinstance(figure, StaffSpec)
            positions = [figure.clef.staff_position(p) for p in pitches]
            assert min(positions) >= -3, 'at most one ledger line below'
            assert max(positions) <= 11, 'at most one ledger line above'


def test_roots_follow_the_setting() -> None:
    def roots(choice: str) -> set[str]:
        settings = {**STAFF_DEFAULTS, 'roots': choice}
        return {
            expected_map(STAFF.generate('chord.staff.major.root', settings, random.Random(s)))[
                'root'
            ]
            for s in range(300)
        }

    assert roots('natural') == set('CDEFGAB')
    common = roots('common')
    assert {'Bb', 'F#', 'Eb', 'C#'} <= common
    assert not common & {'E#', 'B#', 'Fb', 'Cb'}
    assert {'E#', 'Cb'} & roots('all')


def test_open_position_spreads_the_chord() -> None:
    c_major = Chord(PitchName.parse('C'), ChordQuality.MAJOR)
    assert [str(p) for p in voicing(c_major, 3)] == [
        str(Pitch.parse(n)) for n in ('C3', 'E3', 'G3')
    ]
    assert voicing(c_major, 3, open_position=True) == tuple(
        Pitch.parse(n) for n in ('C3', 'G3', 'E4')
    )
    seventh = Chord(PitchName.parse('C'), ChordQuality.MAJOR_SEVENTH, 1)
    assert voicing(seventh, 3, open_position=True) == tuple(
        Pitch.parse(n) for n in ('E3', 'B3', 'C4', 'G4')
    )
    spans = set()
    settings = {**STAFF_DEFAULTS, 'open': True}
    for seed in range(30):
        pitches = staff_pitches(
            STAFF.generate('chord.staff.major.root', settings, random.Random(seed))
        )
        spans.add(pitches[-1].midi - pitches[0].midi > 12)
    assert spans == {True, False}, 'open position mixes open and close chords'


def test_key_signatures() -> None:
    settings = {**STAFF_DEFAULTS, 'key-signature': True, 'clefs': ('treble',)}
    question = find_question('chord.staff.major.root', settings, root='D')
    figure = question.figure
    assert isinstance(figure, StaffSpec)
    assert figure.key_signature is not None
    # D major has F♯: the chosen signature supplies it.
    assert figure.key_signature.alter_for(Letter.F) == 1
    detail = STAFF.grade(question, question.expected).detail
    assert detail.endswith('The key signature supplies F♯.')
    plain = STAFF.generate('chord.staff.major.root', STAFF_DEFAULTS, random.Random(0)).figure
    assert isinstance(plain, StaffSpec)
    assert plain.key_signature is None


def test_clefs_follow_the_setting() -> None:
    settings = {**STAFF_DEFAULTS, 'clefs': ('alto', 'tenor')}
    clefs = set()
    for seed in range(20):
        figure = STAFF.generate('chord.staff.minor.first', settings, random.Random(seed)).figure
        assert isinstance(figure, StaffSpec)
        clefs.add(figure.clef)
    assert clefs == {Clef.ALTO, Clef.TENOR}


# Grading -------------------------------------------------------------------------------


def test_partial_credit() -> None:
    question = find_question('chord.staff.dim.first', STAFF_DEFAULTS, root='Bb')
    right = {'root': 'Bb', 'quality': 'dim', 'inversion': 'first'}
    assert question.expected == right

    one_wrong = STAFF.grade(question, {**right, 'quality': 'minor'})
    assert not one_wrong.correct
    assert one_wrong.score == pytest.approx(2 / 3)
    assert one_wrong.title == 'Not quite — the answer is B♭ diminished triad, first inversion'

    # Spelling matters: B is not B♭.
    two_wrong = STAFF.grade(question, {**right, 'root': 'B', 'inversion': 'root'})
    assert not two_wrong.correct
    assert two_wrong.score == pytest.approx(1 / 3)

    nothing = STAFF.grade(question, {'root': 'C', 'quality': 'aug', 'inversion': 'second'})
    assert nothing.score == 0
    assert not STAFF.grade(question, {}).correct
    assert not STAFF.grade(question, 'garbage').correct


def test_feedback_explains_inversions() -> None:
    question = find_question('chord.staff.dim.first', STAFF_DEFAULTS, root='Bb')
    assert STAFF.grade(question, question.expected).detail == (
        'B♭–D♭–F♭: a minor third and a diminished fifth above B♭. '
        'The third, D♭, is in the bass: first inversion.'
    )
    question = find_question('chord.staff.dom7.third', ALL_STAFF, root='G')
    assert STAFF.grade(question, question.expected).detail == (
        'G–B–D–F: a major third, a perfect fifth and a minor seventh above G. '
        'The seventh, F, is in the bass: third inversion.'
    )
    question = find_question('chord.staff.aug.second', STAFF_DEFAULTS, root='C')
    assert STAFF.grade(question, question.expected).detail.startswith(
        'C–E–G♯: a major third and an augmented fifth above C. The fifth, G♯, is in the bass'
    )


def test_feedback_figure_marks_the_root() -> None:
    question = find_question('chord.staff.major.second', STAFF_DEFAULTS, root='F')
    figure = STAFF.grade(question, question.expected).figure
    assert isinstance(figure, StaffSpec)
    heads = [h for event in figure.events for h in event.heads]  # type: ignore[union-attr]
    assert [h.pitch.name for h in heads if h.ink is Ink.ACCENT] == [PitchName.parse('F')]
    assert [h.pitch for h in heads] == staff_pitches(question)


def test_answer_label() -> None:
    question = STAFF.generate('chord.staff.minor.root', STAFF_DEFAULTS, random.Random(0))
    label = STAFF.answer_label
    assert label(question, {'root': 'E', 'quality': 'minor', 'inversion': 'root'}) == (
        'E minor triad, root position'
    )
    assert label(question, {'root': 'Bb', 'quality': 'dom7', 'inversion': 'third'}) == (
        'B♭ dominant seventh, third inversion'
    )
    assert label(question, {'root': 'F#', 'quality': 'hdim7', 'inversion': 'second'}) == (
        'F♯ half-diminished seventh, second inversion'
    )
    assert label(question, {'root': 'E', 'quality': 'minor'}) == 'E minor triad'
    # Incomplete answers fall back to option labels instead of failing.
    assert label(question, {'root': 'E', 'quality': 'nonsense', 'inversion': 'root'})
    assert STAFF.serialize(question.expected).startswith('root=')


def test_item_labels() -> None:
    assert STAFF.item_label(ItemId('chord.staff.dim.first')) == (
        'Diminished triad, first inversion (staff)'
    )
    assert EAR.item_label(ItemId('chord.ear.dim7')) == 'Diminished seventh (ear)'


# Sound and accessibility ------------------------------------------------------------------


def test_playback_is_the_chord_broken_then_block() -> None:
    question = find_question('chord.staff.minor.root', STAFF_DEFAULTS, root='E')
    pitches = staff_pitches(question)
    midis = [p.midi for p in pitches]
    assert question.playback is not None
    notes = question.playback.notes
    broken, block = notes[: len(midis)], notes[len(midis) :]
    assert [n.midi for n in broken] == midis
    assert [n.start for n in broken] == sorted({n.start for n in broken})
    assert sorted(n.midi for n in block) == midis
    assert len({n.start for n in block}) == 1
    assert block[0].start > broken[-1].start
    assert {n.start for n in chord_playback(pitches, style='block').notes} == {0}


def test_screen_readers_hear_the_notes() -> None:
    """Listing the notes is equivalent to seeing them: the learner still names the chord."""
    question = find_question('chord.staff.minor.root', STAFF_DEFAULTS, root='E', clef=Clef.TREBLE)
    names = [str(p) for p in staff_pitches(question)]
    assert describe(question.figure) == f'Treble staff. One chord: {", ".join(names)}.'  # type: ignore[arg-type]


# Chips values ---------------------------------------------------------------------------


def test_expected_roots_use_the_chips_format() -> None:
    """The chips widget reports the option key plus '#' or 'b' (``ChipGroups.value``)."""
    assert root_value(PitchName.parse('E')) == 'E'
    assert root_value(PitchName.parse('F#')) == 'F#'
    assert root_value(PitchName.parse('Bb')) == 'Bb'
    for item in STAFF.items(ALL_STAFF):
        for seed in range(5):
            question = STAFF.generate(item, ALL_STAFF, random.Random(seed))
            assert isinstance(question.answer, ChipsAnswer)
            root = expected_map(question)['root']
            letters = {o.key for o in question.answer.groups[0].options}
            assert root[0] in letters
            assert root[1:] in ('', '#', 'b')


@pytest.fixture(scope='module')
def gtk() -> object:
    gi = pytest.importorskip('gi')
    try:
        gi.require_version('Gtk', '4.0')
        gi.require_version('Gdk', '4.0')
        gi.require_version('Adw', '1')
        from gi.repository import Adw, Gtk
    except (ImportError, ValueError) as error:
        pytest.skip(f'GTK 4 and libadwaita are not available: {error}')
    if not Gtk.init_check():
        pytest.skip('no display')
    Adw.init()
    return Gtk


@pytest.mark.gtk
def test_the_chips_widget_produces_the_expected_values(gtk: object) -> None:
    """The keyboard flow of design 1f (letter, digit, digit, Enter) plus the ♯ / ♭ chip
    yields exactly the expected mapping, for every quality and inversion."""
    from gi.repository import Gdk

    from etude.ui.widgets.chips import ChipGroups

    clicks = {'': 0, '#': 1, 'b': 2}
    for item in STAFF.items(ALL_STAFF):
        for seed in range(3):
            question = STAFF.generate(item, ALL_STAFF, random.Random(seed))
            assert isinstance(question.answer, ChipsAnswer)
            expected = expected_map(question)
            widget = ChipGroups(question.answer)
            answered: list[object] = []
            widget.connect('answered', lambda _w, value, out=answered: out.append(value))
            state = Gdk.ModifierType(0)
            for group in question.answer.groups:
                chosen = expected[group.key]
                key = chosen[0] if group.accidentals else chosen
                accel = next(o.accel for o in group.options if o.key == key)
                assert accel is not None
                assert widget.handle_key(Gdk.unicode_to_keyval(ord(accel)), state)
                if group.accidentals:
                    for _ in range(clicks[chosen[1:]]):
                        widget._accidental_chips[group.key].emit('clicked')
            assert widget.activate_default()
            assert answered == [dict(expected)]
            assert STAFF.grade(question, answered[0]).correct


# Chord Quality — Ear --------------------------------------------------------------------


def test_ear_items() -> None:
    assert EAR.items(EAR_DEFAULTS) == [
        'chord.ear.major',
        'chord.ear.minor',
        'chord.ear.dim',
        'chord.ear.aug',
    ]
    assert EAR.items({**EAR_DEFAULTS, 'sevenths': True})[4:] == [
        'chord.ear.dom7',
        'chord.ear.maj7',
        'chord.ear.min7',
        'chord.ear.hdim7',
        'chord.ear.dim7',
    ]


def test_ear_question() -> None:
    question = EAR.generate(ear_item('minor'), EAR_DEFAULTS, random.Random(3))
    assert question.prompt == 'Which chord do you hear?'
    assert question.playback_is_question
    assert question.written_alternative is not None
    assert isinstance(question.answer, ChoiceAnswer)
    assert [(o.key, o.label, o.accel) for o in question.answer.options] == [
        ('major', 'Major', '1'),
        ('minor', 'Minor', '2'),
        ('dim', 'Diminished', '3'),
        ('aug', 'Augmented', '4'),
    ]
    assert question.expected == 'minor'
    pitches = figure_pitches(question.written_alternative)
    assert question.figure == question.written_alternative
    assert question.context == f'Root: {pitches[0].name.symbol}{pitches[0].octave}'
    chord = Chord.identify(pitches)[0]
    assert chord.quality is ChordQuality.MINOR
    assert chord.inversion == 0
    assert 48 <= pitches[0].midi <= 60
    assert question.playback is not None
    assert {n.midi for n in question.playback.notes} == {p.midi for p in pitches}
    assert question.playback.instrument is Instrument.PIANO
    assert EAR.describe_settings(EAR_DEFAULTS) == 'Triads · broken, then block'


def test_ear_feedback_compares_answers() -> None:
    question = EAR.generate(ear_item('dim'), EAR_DEFAULTS, random.Random(0))
    pitches = figure_pitches(question.written_alternative)
    right = EAR.grade(question, 'dim')
    assert right.correct
    assert right.title == 'Correct — diminished triad'
    assert right.play_expected == question.playback
    assert right.play_given is None

    wrong = EAR.grade(question, 'minor')
    assert not wrong.correct
    assert wrong.title == 'Not quite — the answer is a diminished triad'
    assert 'For comparison: A minor triad' in wrong.detail
    assert wrong.play_given is not None
    given = sorted({n.midi for n in wrong.play_given.notes})
    # Same root and register; the fifth is a semitone higher.
    assert given[0] == pitches[0].midi
    assert given == sorted([pitches[0].midi, pitches[1].midi, pitches[2].midi + 1])
    assert EAR.answer_label(question, 'aug') == 'augmented triad'
    assert EAR.grade(question, 'aug').title == 'Not quite — the answer is a diminished triad'


def test_ear_inversions_and_instruments_vary() -> None:
    settings = {**EAR_DEFAULTS, 'inversions': True, 'instrument': 'varied', 'sevenths': True}
    inversions = set()
    instruments = set()
    for seed in range(60):
        question = EAR.generate(ear_item('dom7'), settings, random.Random(seed))
        pitches = figure_pitches(question.written_alternative)
        chord = next(
            c for c in Chord.identify(pitches) if c.quality is ChordQuality.DOMINANT_SEVENTH
        )
        inversions.add(chord.inversion)
        assert question.playback is not None
        instruments.add(question.playback.instrument)
        if chord.inversion:
            assert question.context.startswith('Lowest note: ')
        # The learner's answer is played the same way (here: broken, then block).
        given = EAR.grade(question, 'major').play_given
        assert given is not None
        assert given.instrument is question.playback.instrument
        assert len(given.notes) == 6
    assert inversions == {0, 1, 2, 3}
    assert len(instruments) > 1


@pytest.mark.parametrize('style', ['block', 'broken', 'both'])
def test_ear_playback_styles(style: str) -> None:
    question = EAR.generate(ear_item('aug'), {**EAR_DEFAULTS, 'style': style}, random.Random(1))
    assert question.playback is not None
    starts = [n.start for n in question.playback.notes]
    if style == 'block':
        assert set(starts) == {0}
    elif style == 'broken':
        assert len(set(starts)) == 3
    else:
        assert len(starts) == 6
    given = EAR.grade(question, 'major').play_given
    assert given is not None
    assert len(given.notes) == len(question.playback.notes)
