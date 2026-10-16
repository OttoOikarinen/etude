# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""STUB DATA FOR W1 — fake exercises, statistics, questions and a fake session.

The W1 UI shell is built against this module so that every screen of the
design can be shown and tested before the learning engine, storage and the
real exercises exist. W2 replaces every use of this module with the
exercise registry (:mod:`etude.exercises.registry`), the session builder and
the statistics of :mod:`etude.learning`. Nothing here is real data, and no
code outside ``etude.ui`` may import it.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from gettext import gettext as _

from ..audio.spec import PlaybackSpec
from ..core import KeySignature, Meter, Pitch, PitchName
from ..core.pitch import Letter
from ..exercises.base import (
    BoolSetting,
    ChipGroup,
    ChipsAnswer,
    ChoiceAnswer,
    ChoiceSetting,
    ExerciseDefinition,
    Family,
    Feedback,
    IntSetting,
    Modality,
    MultiChoiceSetting,
    Option,
    PianoAnswer,
    Question,
    RhythmInputAnswer,
    StaffInputAnswer,
    TapAnswer,
    TextAnswer,
)
from ..learning.model import ItemId, SessionSummary
from ..notation.spec import Bracket, Chord, Clef, Head, Ink, StaffSpec

# Home -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExerciseCardData:
    """What the home page shows for one exercise. W2: from the registry and statistics."""

    id: str
    title: str
    description: str
    family: Family
    glyph: str
    """Short symbol drawn in the icon tile (W2: the exercise's ``icon_name``)."""
    accuracy: float | None
    sessions: int
    recency: int
    """Lower = practised more recently; used by "Sort: Recent"."""


def exercise_cards() -> tuple[ExerciseCardData, ...]:
    return (
        ExerciseCardData(
            'keysig',
            _('Key Signatures'),
            _('Name the major or minor key from its signature.'),
            Family.NOTATION,
            '♯',
            0.94,
            18,
            1,
        ),
        ExerciseCardData(
            'note-naming',
            _('Note Naming'),
            _('Read notes in treble, bass and C clefs.'),
            Family.NOTATION,
            '♩',
            0.91,
            24,
            2,
        ),
        ExerciseCardData(
            'interval-staff',
            _('Intervals — Staff'),
            _('Identify intervals written on the staff.'),
            Family.NOTATION,
            '♫',
            0.78,
            11,
            4,
        ),
        ExerciseCardData(
            'interval-ear',
            _('Intervals — Ear'),
            _('Recognise intervals by ear, melodic or harmonic.'),
            Family.EAR,
            '♪',
            0.64,
            6,
            0,
        ),
        ExerciseCardData(
            'chord-staff',
            _('Chords — Staff'),
            _('Name triads and sevenths with their inversion.'),
            Family.HARMONY,
            '♮',
            0.71,
            9,
            3,
        ),
        ExerciseCardData(
            'scale-degree',
            _('Scale Degrees'),
            _('Find the degree of a note within a key.'),
            Family.HARMONY,
            '♭',
            0.82,
            14,
            5,
        ),
    )


@dataclass(frozen=True, slots=True)
class ContinueData:
    exercise_id: str
    title: str
    answered: int
    total: int
    accuracy: float


def continue_data() -> ContinueData:
    return ContinueData('interval-ear', _('Intervals — by ear'), 7, 20, 0.64)


@dataclass(frozen=True, slots=True)
class StreakData:
    days: int
    practised_today: bool


def streak() -> StreakData:
    return StreakData(12, True)


# Progress ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WeakItem:
    title: str
    accuracy: float
    item_id: ItemId


@dataclass(frozen=True, slots=True)
class ProgressData:
    streak: int
    longest_streak: int
    accuracy: float
    accuracy_change: int
    """Percentage points compared with the previous period."""
    minutes: int
    sessions: int
    by_exercise: tuple[tuple[str, float], ...]
    answered: tuple[tuple[str, int], ...]
    """Questions answered per day (or week); the last entry is the current one."""
    weakest: tuple[WeakItem, ...]
    drill_count: int


def progress(period: str = 'week') -> ProgressData:
    """``period`` is ``'week'``, ``'month'`` or ``'all'``."""
    cards = exercise_cards()
    weakest = (
        WeakItem(_('Minor sixth (ear)'), 0.41, ItemId('interval.ear.melodic.asc.m6')),
        WeakItem(_('Tritone (ear)'), 0.48, ItemId('interval.ear.melodic.asc.TT')),
        WeakItem(_('Diminished triad'), 0.57, ItemId('chord.triad.dim')),
        WeakItem(_('6 flats — key signature'), 0.62, ItemId('keysig.major.6b')),
    )
    days = (_('Mon'), _('Tue'), _('Wed'), _('Thu'), _('Fri'), _('Sat'), _('Today'))
    if period == 'month':
        return ProgressData(
            12,
            19,
            0.84,
            2,
            11 * 60 + 5,
            37,
            tuple((c.title, max(0.0, (c.accuracy or 0) - 0.03)) for c in cards),
            tuple(
                zip(
                    (_('Week 1'), _('Week 2'), _('Week 3'), _('This week')),
                    (180, 214, 160, 250),
                    strict=True,
                )
            ),
            weakest,
            15,
        )
    if period == 'all':
        return ProgressData(
            12,
            19,
            0.81,
            0,
            41 * 60 + 30,
            128,
            tuple((c.title, max(0.0, (c.accuracy or 0) - 0.06)) for c in cards),
            tuple(
                zip(
                    (_('Jun'), _('Jul'), _('Aug'), _('Sep'), _('This month')),
                    (420, 610, 380, 720, 520),
                    strict=True,
                )
            ),
            weakest,
            15,
        )
    return ProgressData(
        12,
        19,
        0.87,
        4,
        2 * 60 + 48,
        9,
        tuple((c.title, c.accuracy or 0) for c in cards),
        tuple(zip(days, (32, 45, 28, 51, 38, 22, 34), strict=True)),
        weakest,
        15,
    )


# Questions ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PreviewQuestion:
    """A stub question plus the page chrome that W2 derives from the exercise."""

    key: str
    exercise_title: str
    settings_text: str
    modality: Modality
    question: Question
    correct_title: str
    """E.g. "Correct — F4"."""
    wrong_title: str
    """E.g. "Not quite — the answer is a major sixth"."""
    detail: str
    play_label: str | None = None
    sample_wrong: object = None
    """A wrong answer, used by the screenshot script and tests."""


def _intervals() -> tuple[Option, ...]:
    names = (
        ('m2', _('Minor second')),
        ('M2', _('Major second')),
        ('m3', _('Minor third')),
        ('M3', _('Major third')),
        ('P4', _('Perfect fourth')),
        ('TT', _('Tritone')),
        ('P5', _('Perfect fifth')),
        ('m6', _('Minor sixth')),
        ('M6', _('Major sixth')),
        ('m7', _('Minor seventh')),
    )
    return tuple(Option(k, label) for k, label in names)


def _numbered(options: Sequence[Option]) -> tuple[Option, ...]:
    return tuple(
        Option(o.key, o.label, str(i), o.description) for i, o in enumerate(options, start=1)
    )


def preview_questions() -> dict[str, PreviewQuestion]:
    treble = _('Treble clef')
    intervals = _intervals()

    keysig_options = _numbered(
        [
            Option(k, label)
            for k, label in (
                ('C', _('C major')),
                ('G', _('G major')),
                ('D', _('D major')),
                ('A', _('A major')),
                ('E', _('E major')),
                ('B', _('B major')),
                ('F#', _('F♯ major')),
                ('C#', _('C♯ major')),
            )
        ]
    )
    keysig = Question(
        'keysig',
        ItemId('keysig.major.4s'),
        _('Which major key is written here?'),
        ChoiceAnswer(keysig_options),
        'E',
        figure=StaffSpec(
            key_signature=KeySignature(4),
            description=_('Treble staff with a key signature of four sharps.'),
        ),
        hint=_('The last sharp is the leading note: the tonic is a semitone above it.'),
    )

    note = Question(
        'note-naming',
        ItemId('note.treble.F4'),
        _('Name this note'),
        PianoAnswer(Pitch.parse('C4'), Pitch.parse('C5')),
        PitchName(Letter.F),
        figure=StaffSpec.notes('F4', description=_('Treble staff with one note.')),
        hint=_('Spaces of the treble staff spell F A C E from the bottom up.'),
    )

    interval_staff_options = _numbered(
        [o for o in intervals if o.key in ('m3', 'M3', 'P4', 'P5', 'm6', 'M6', 'm7', 'TT')]
    )
    interval_staff = Question(
        'interval-staff',
        ItemId('interval.staff.M6'),
        _('Name the interval'),
        ChoiceAnswer(interval_staff_options),
        'M6',
        figure=StaffSpec(
            events=(Chord((Head(Pitch.parse('G4')),)), Chord((Head(Pitch.parse('E5')),))),
            brackets=(Bracket(0, 1, '?'),),
            description=_('Treble staff with two notes, G4 and E5.'),
        ),
        playback=PlaybackSpec.melodic([Pitch.parse('G4'), Pitch.parse('E5')]),
    )

    ear_options = _numbered(
        [o for o in intervals if o.key in ('m2', 'M2', 'm3', 'M3', 'P4', 'TT', 'P5', 'm6')]
    )
    interval_ear = Question(
        'interval-ear',
        ItemId('interval.ear.melodic.asc.M3'),
        _('Which interval do you hear?'),
        ChoiceAnswer(ear_options),
        'M3',
        playback=PlaybackSpec.melodic([Pitch.parse('C4'), Pitch.parse('E4')]),
        playback_is_question=True,
        written_alternative=StaffSpec.notes(
            'C4', 'E4', description=_('Treble staff with two notes, C4 and E4.')
        ),
        context=_('Root: C4'),
    )

    letters = tuple(Option(letter.name, letter.name, letter.name.lower()) for letter in Letter)
    chord = Question(
        'chord-staff',
        ItemId('chord.triad.minor.root'),
        _('Name the chord'),
        ChipsAnswer(
            (
                ChipGroup('root', _('Root'), letters),
                ChipGroup(
                    'quality',
                    _('Quality'),
                    _numbered(
                        [
                            Option('major', _('Major')),
                            Option('minor', _('Minor')),
                            Option('diminished', _('Diminished')),
                            Option('augmented', _('Augmented')),
                            Option('dominant7', _('Dominant 7th')),
                        ]
                    ),
                ),
                ChipGroup(
                    'inversion',
                    _('Inversion'),
                    (
                        Option('root', _('Root position'), '6'),
                        Option('first', _('First'), '7'),
                        Option('second', _('Second'), '8'),
                    ),
                ),
            )
        ),
        {'root': 'E', 'quality': 'minor', 'inversion': 'root'},
        figure=StaffSpec(
            events=(Chord(tuple(Head(Pitch.parse(p)) for p in ('E4', 'G4', 'B4'))),),
            description=_('Treble staff with a three-note chord.'),
        ),
        playback=PlaybackSpec.harmonic([Pitch.parse(p) for p in ('E4', 'G4', 'B4')]),
    )

    degree_names = (
        _('Tonic'),
        _('Supert.'),
        _('Mediant'),
        _('Subdom.'),
        _('Dominant'),
        _('Submed.'),
        _('Leading'),
    )
    degree = Question(
        'scale-degree',
        ItemId('degree.major.5'),
        _('Which scale degree is highlighted?'),
        ChoiceAnswer(
            tuple(
                Option(str(i), str(i), str(i), name) for i, name in enumerate(degree_names, start=1)
            ),
            targets={0: '5'},
        ),
        '5',
        figure=StaffSpec(
            key_signature=KeySignature(2),
            events=(Chord((Head(Pitch.parse('A4'), ink=Ink.ACCENT, halo=True),)),),
            description=_('Treble staff in D major with one highlighted note.'),
        ),
        playback=PlaybackSpec.melodic(
            [Pitch.parse(p) for p in ('D4', 'E4', 'F#4', 'G4', 'A4', 'B4', 'C#5', 'D5')],
            note_length=Fraction(1, 2),
        ),
    )

    vocab = Question(
        'vocabulary',
        ItemId('vocab.term.crescendo'),
        _('Which term means “gradually getting louder”?'),
        TextAnswer(placeholder=_('Type the term')),
        'crescendo',
    )

    staff_input = Question(
        'construction',
        ItemId('build.triad.F'),
        _('Write an F major triad'),
        StaffInputAnswer(Clef.TREBLE, slots=1),
        (),
    )
    rhythm_input = Question(
        'rhythm-dictation',
        ItemId('rhythm.dictation.1'),
        _('Write the rhythm you hear'),
        RhythmInputAnswer(Meter(4, 4), 1, ()),
        (),
    )
    tap = Question(
        'rhythm-tap',
        ItemId('rhythm.tap.1'),
        _('Tap the rhythm'),
        TapAnswer(Meter(4, 4), 80.0, 4),
        (),
    )

    eye = Modality.EYE
    accidentals = _('up to 5 accidentals')
    items = [
        PreviewQuestion(
            'keysig',
            _('Key Signatures'),
            f'{treble} · {accidentals}',
            eye,
            keysig,
            _('Correct — E major'),
            _('Not quite — the answer is E major'),
            _('Four sharps: F♯ C♯ G♯ D♯. The last sharp, D♯, is the leading note of E.'),
            sample_wrong='A',
        ),
        PreviewQuestion(
            'note-naming',
            _('Note Naming'),
            treble,
            eye,
            note,
            _('Correct — F4'),
            _('Not quite — the answer is F4'),
            _('First space of the treble staff.'),
            sample_wrong=PitchName(Letter.A),
        ),
        PreviewQuestion(
            'interval-staff',
            _('Intervals — Staff'),
            treble,
            eye,
            interval_staff,
            _('Correct — major sixth'),
            _('Not quite — the answer is a major sixth'),
            _('G4 to E5 spans six letter names and nine semitones.'),
            play_label=_('Play interval'),
            sample_wrong='m6',
        ),
        PreviewQuestion(
            'interval-ear',
            _('Intervals — Ear'),
            _('Melodic · ascending'),
            Modality.EAR,
            interval_ear,
            _('Correct — major third'),
            _('Not quite — the answer is a major third'),
            _('C4 to E4 spans three letter names and four semitones.'),
            play_label=_('Play interval'),
            sample_wrong='m3',
        ),
        PreviewQuestion(
            'chord-staff',
            _('Chords — Staff'),
            f'{treble} · {_("triads")}',
            eye,
            chord,
            _('Correct — E minor, root position'),
            _('Not quite — the answer is E minor, root position'),
            _('E G B: a minor third and a perfect fifth above E, with E in the bass.'),
            play_label=_('Play chord'),
            sample_wrong={'root': 'E', 'quality': 'major', 'inversion': 'root'},
        ),
        PreviewQuestion(
            'scale-degree',
            _('Scale Degrees'),
            _('D major'),
            eye,
            degree,
            _('Correct — 5, the dominant'),
            _('Not quite — the answer is 5, the dominant'),
            _('A is the fifth note of the D major scale.'),
            play_label=_('Play scale'),
            sample_wrong='4',
        ),
        PreviewQuestion(
            'vocabulary',
            _('Vocabulary'),
            _('Dynamics'),
            eye,
            vocab,
            _('Correct — crescendo'),
            _('Not quite — the answer is crescendo'),
            _('Crescendo, abbreviated cresc., is the opposite of diminuendo.'),
            sample_wrong='forte',
        ),
        PreviewQuestion(
            'construction',
            _('Chord Construction'),
            treble,
            eye,
            staff_input,
            '',
            '',
            '',
        ),
        PreviewQuestion(
            'rhythm-dictation',
            _('Rhythm Dictation'),
            '4/4',
            Modality.EAR,
            rhythm_input,
            '',
            '',
            '',
        ),
        PreviewQuestion(
            'rhythm-tap',
            _('Rhythm Tapping'),
            '4/4',
            Modality.TAP,
            tap,
            '',
            '',
            '',
        ),
    ]
    return {item.key: item for item in items}


def answer_label(question: Question, value: object) -> str:
    """Human-readable form of an answer value. W2: the exercise provides this."""
    answer = question.answer
    if isinstance(answer, ChoiceAnswer):
        return next((o.label for o in answer.options if o.key == value), str(value))
    if isinstance(answer, ChipsAnswer) and isinstance(value, Mapping):
        labels = []
        for group in answer.groups:
            key = str(value.get(group.key, ''))
            labels.append(next((o.label for o in group.options if o.key == key), key))
        return ' '.join(labels)
    if isinstance(value, PitchName | Pitch):
        return value.symbol
    return str(value)


def grade(item: PreviewQuestion, given: object) -> Feedback:
    """Stub grading by equality. W2: ``ExerciseDefinition.grade``."""
    question = item.question
    expected = question.expected
    if isinstance(question.answer, PianoAnswer):
        correct = (given.name if isinstance(given, Pitch) else given) == expected
    elif isinstance(question.answer, TextAnswer):
        correct = str(given).strip().casefold() == str(expected).casefold()
    else:
        correct = given == expected
    title = item.correct_title if correct else item.wrong_title
    play = question.playback if item.play_label else None
    return Feedback(
        correct,
        title,
        item.detail,
        expected_label=answer_label(question, expected),
        play_expected=play,
    )


# A stub session ------------------------------------------------------------------


@dataclass
class PreviewSession:
    """Walks through stub questions like a session would. W2: the session runner."""

    keys: Sequence[str]
    total: int = 20
    start: int = 7
    """Display the first question as number ``start`` (the design shows "7 of 20")."""
    questions: dict[str, PreviewQuestion] = field(default_factory=preview_questions)
    index: int = 0
    streak: int = 6
    best_today: int = 11
    answered: int = 12
    correct: int = 11
    best_streak: int = 6
    mistakes: list[ItemId] = field(default_factory=list)

    @property
    def current(self) -> PreviewQuestion:
        return self.questions[self.keys[self.index % len(self.keys)]]

    @property
    def number(self) -> int:
        return self.start + self.index

    @property
    def accuracy(self) -> float:
        return self.correct / self.answered if self.answered else 0.0

    def answer(self, given: object) -> Feedback:
        feedback = grade(self.current, given)
        self.answered += 1
        if feedback.correct:
            self.correct += 1
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
            self.best_today = max(self.best_today, self.streak)
        else:
            self.streak = 0
            self.mistakes.append(self.current.question.item_id)
        return feedback

    def advance(self) -> bool:
        """Move to the next question; ``False`` when the session is over."""
        if self.number >= self.total:
            return False
        self.index += 1
        return True

    def summary(self) -> SessionSummary:
        return SessionSummary(
            total=self.answered,
            correct=self.correct,
            duration_ms=252_000,
            best_streak=self.best_streak,
            personal_best=self.best_streak >= 11,
            mistakes=tuple(self.mistakes),
        )


def sample_summary() -> SessionSummary:
    """Design 1i."""
    return SessionSummary(
        total=20,
        correct=18,
        duration_ms=252_000,
        best_streak=11,
        personal_best=True,
        mistakes=(ItemId('keysig.major.6b'), ItemId('keysig.minor.5s')),
    )


# A stub exercise definition (for the generated setup page, design 1j) -----------


class PreviewKeySignatures(ExerciseDefinition):
    id = 'keysig'
    item_prefix = 'keysig.'
    family = Family.NOTATION
    modality = Modality.EYE
    level = 1
    icon_name = 'keysig-symbolic'
    settings = (
        MultiChoiceSetting(
            'clefs',
            _('Clefs'),
            (
                Option('treble', _('Treble')),
                Option('bass', _('Bass')),
                Option('alto', _('Alto')),
                Option('tenor', _('Tenor')),
            ),
            ('treble', 'bass'),
        ),
        IntSetting(
            'max-accidentals',
            _('Most accidentals'),
            5,
            0,
            7,
            subtitle=_('Largest number of sharps or flats in a signature'),
        ),
        ChoiceSetting(
            'mode',
            _('Keys'),
            (
                Option('major', _('Major')),
                Option('minor', _('Minor')),
                Option('both', _('Major and minor')),
            ),
            'major',
        ),
        BoolSetting(
            'ask-relative',
            _('Ask for the relative key'),
            False,
            subtitle=_('Follow each answer with its relative major or minor'),
        ),
    )

    @property
    def title(self) -> str:
        return _('Key Signatures')

    @property
    def description(self) -> str:
        return _('Name the major or minor key from its signature.')

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        return [ItemId('keysig.major.4s')]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        return preview_questions()['keysig'].question

    def grade(self, question: Question, given: object) -> Feedback:
        return grade(preview_questions()['keysig'], given)
