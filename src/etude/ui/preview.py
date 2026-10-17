# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The design mockups' data: fixed exercises, statistics, questions and a session.

:class:`PreviewModel` is an :class:`~etude.ui.model.AppModel` that shows
exactly the numbers and questions of the design (1a–1j), so screenshots can
be compared with the mockups and UI tests have stable expectations. The
application itself uses :class:`~etude.ui.model.LiveModel`. Nothing here is
real data, and no code outside ``etude.ui`` and the UI tests may import it.
"""

from __future__ import annotations

import random
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from fractions import Fraction
from gettext import gettext as _

from ..audio.null import NullBackend, NullHandle
from ..audio.spec import PlaybackSpec
from ..content.loaders import parse_glossary, parse_lesson
from ..content.model import GlossaryEntry, Lesson
from ..core import KeySignature, Pitch, PitchName
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
    StaffInputAnswer,
    TextAnswer,
)
from ..exercises.families import rhythm
from ..learning.model import ItemId, SessionMode, SessionSummary
from ..notation.spec import Bracket, Chord, Clef, Head, Ink, StaffSpec
from .model import (
    ContinueData,
    DueExercise,
    ExerciseCardData,
    GlossaryData,
    LevelData,
    PathData,
    ProgressData,
    SessionOutcome,
    SessionSource,
    StreakData,
    TodayData,
    UnitData,
    WeakItem,
    exam_outcome,
    placement_outcome,
)

_RHYTHM = {d.id: d for d in rhythm.EXERCISES}

# Home -------------------------------------------------------------------------


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


def continue_data() -> ContinueData:
    return ContinueData('interval-ear', _('Intervals — by ear'), 7, 20, 0.64, '♪')


def streak() -> StreakData:
    return StreakData(12, True)


# Today ------------------------------------------------------------------------


def today() -> TodayData:
    """A learner with reviews due, in the middle of the day."""
    return TodayData(
        due=24,
        new=5,
        by_exercise=(
            DueExercise('interval-ear', _('Intervals — Ear'), '♪', 9),
            DueExercise('keysig', _('Key Signatures'), '♯', 6),
            DueExercise('chord-staff', _('Chords — Staff'), '♮', 5),
            DueExercise('scale-degree', _('Scale Degrees'), '♭', 4),
        ),
        answered_today=18,
        daily_goal=30,
        streak=12,
        goal_met=False,
        session_size=20,
    )


def caught_up_today() -> TodayData:
    """Nothing due, no new items left today, and the goal met."""
    return TodayData(
        due=0,
        new=0,
        by_exercise=(),
        answered_today=34,
        daily_goal=30,
        streak=12,
        goal_met=True,
        session_size=20,
    )


# Progress ---------------------------------------------------------------------


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


def empty_progress(period: str = 'week') -> ProgressData:
    """A brand-new learner: nothing answered yet."""
    if period == 'week':
        days = (_('Mon'), _('Tue'), _('Wed'), _('Thu'), _('Fri'), _('Sat'), _('Today'))
        answered = tuple((d, 0) for d in days)
    else:
        answered = ((_('This month'), 0),)
    return ProgressData(0, 0, None, None, 0, 0, (), answered, (), 0)


# The learning path -------------------------------------------------------------

_UNITS = (
    ('l1.staff', _('Staff, Clefs and Note Names'), _('Read notes in the treble and bass clefs.')),
    ('l1.rhythm', _('Note Values and Rests'), _('Whole, half, quarter and eighth notes.')),
    ('l1.meter', _('Beat and Time Signatures'), _('Pulse, bars, simple and compound time.')),
    ('l1.accidentals', _('Accidentals, Half Steps and Whole Steps'), _('Sharps, flats, naturals.')),
    ('l1.major', _('Major Scales and Keys'), _('The major scale and the circle of fifths.')),
    ('l1.minor', _('Minor Scales and Keys'), _('Natural, harmonic and melodic minor.')),
    ('l1.intervals', _('Intervals'), _('Number and quality, on the staff and by ear.')),
    ('l1.triads', _('Triads'), _('Major, minor, diminished and augmented triads.')),
)


def path(*, new_learner: bool = False) -> PathData:
    """Level 1 of a learner half-way through it, or of a brand-new learner."""
    units = []
    for number, (unit_id, title, summary) in enumerate(_UNITS):
        lesson = unit_id == 'l1.staff'
        items = {'l1.rhythm': 0, 'l1.meter': 0}.get(unit_id, 24 + 4 * number)
        if new_learner:
            mastered, unlocked, complete = 0, number == 0, False
        else:
            mastered = {'l1.staff': items, 'l1.accidentals': 22}.get(unit_id, 0)
            unlocked = number <= 3
            complete = unit_id in ('l1.staff', 'l1.rhythm', 'l1.meter')
        # Lesson-only units pass on the lock of the unit before them.
        previous = _UNITS[0][1] if new_learner else _UNITS[3][1]
        units.append(
            UnitData(
                id=unit_id,
                title=title,
                summary=summary,
                lesson_id='l1.staff' if lesson else None,
                lesson_title=title if lesson else '',
                lesson_summary=_('Five lines, two clefs and seven letters name any note.')
                if lesson
                else '',
                lesson_done=lesson and not new_learner,
                items=items,
                mastered=mastered,
                complete=complete,
                unlocked=unlocked,
                missing=() if unlocked else (previous,),
            )
        )
    level = LevelData(
        id='level1',
        number=1,
        title=_('Fundamentals'),
        description=_('Reading notes and rhythms, keys and scales, intervals and triads.'),
        units=tuple(units),
        exam_questions=30,
        exam_ready=False,
        passed=False,
    )
    return PathData((level,), placement_available=new_learner)


_GLOSSARY = """
<glossary>
  <entry id="staff" level="1"><term>staff</term>
    <gloss>the five lines music is written on</gloss>
    <def>Five horizontal lines and the four spaces between them. Notes are written on the
      lines and in the spaces; higher notes sound higher.</def>
    <see ref="clef"/><see ref="ledger-line"/></entry>
  <entry id="clef" level="1"><term>clef</term>
    <gloss>sign that fixes the notes of the staff</gloss>
    <def>A sign at the start of the staff that names one line. The
      <term ref="treble-clef">treble clef</term> marks <note>G4</note>.</def></entry>
  <entry id="treble-clef" level="1"><term>treble clef</term>
    <gloss>G clef: the second line is G above middle C</gloss>
    <def>The clef whose curl wraps around the second line, marking it as <note>G4</note>.</def>
    <figure play="as-written"><staff clef="treble">G4/w</staff></figure>
    <see ref="clef"/></entry>
  <entry id="ledger-line" level="1"><term>ledger line</term>
    <gloss>short extra line above or below the staff</gloss>
    <def>A short line that extends the staff for a single note above or below it.</def></entry>
  <entry id="octave" level="1"><term>octave</term>
    <gloss>the distance to the next note with the same letter</gloss>
    <def>From one note to the next with the same letter, such as <note>C4</note> to
      <note>C5</note>.</def></entry>
  <entry id="crescendo" level="1"><term>crescendo</term><foreign lang="it">crescendo</foreign>
    <gloss>gradually louder</gloss>
    <def>Getting gradually louder. The opposite is <term ref="diminuendo">diminuendo</term>.</def>
    <abbr>cresc.</abbr><see ref="diminuendo"/></entry>
  <entry id="diminuendo" level="1"><term>diminuendo</term><foreign lang="it">diminuendo</foreign>
    <gloss>gradually softer</gloss>
    <def>Getting gradually softer; also called decrescendo.</def>
    <abbr>dim.</abbr><see ref="crescendo"/></entry>
  <entry id="allegro" level="1"><term>fast</term><foreign lang="it">Allegro</foreign>
    <gloss>fast and lively</gloss><def>A fast, lively tempo.</def></entry>
  <entry id="lied" level="2"><term>art song</term><foreign lang="de">Lied</foreign>
    <gloss>a song for voice and piano</gloss>
    <def>A song for solo voice and piano, usually setting a poem.</def></entry>
</glossary>
"""

_LESSON = """
<lesson id="l1.staff">
  <title>Staff, Clefs and Note Names</title>
  <summary>Five lines, two clefs and seven letters are enough to name any note.</summary>
  <section>
    <title>The staff</title>
    <p>Music is written on a <term ref="staff">staff</term>: five lines with four spaces
      between them. A note sits either <em>on</em> a line or <em>in</em> a space.</p>
    <figure play="melodic" tempo="100">
      <staff clef="treble">E4 F4 G4 A4 B4 C5 D5 E5 F5</staff>
      <caption>Every line and space of the staff, from the bottom up.</caption>
    </figure>
    <list>
      <li>Lines and spaces are counted from the bottom up.</li>
      <li>After <note>G</note> the letters start again from <note>A</note>.</li>
    </list>
    <callout kind="tip"><p>Say the letters aloud as you climb the staff.</p></callout>
  </section>
  <section>
    <title>Clefs</title>
    <p>A <term ref="clef">clef</term> fixes which note belongs to which line. The
      <term ref="treble-clef">treble clef</term> marks <note>G4</note> on the second line.</p>
    <callout kind="remember"><p>Treble clef lines from the bottom: <note>E</note> <note>G</note>
      <note>B</note> <note>D</note> <note>F</note>.</p></callout>
    <callout kind="warning"><p>The bass clef marks <note>F3</note>, not <note>G</note>.</p>
    </callout>
    <worked>
      <title>Name the note on the fourth line of the treble staff</title>
      <step><p>Start from <note>G4</note> on the second line.</p></step>
      <step><p>Count up: <note>A4</note>, <note>B4</note>, <note>C5</note>.</p></step>
      <step><p>The fourth line comes next, so the note is <note>D5</note>.</p>
        <figure play="melodic"><staff clef="treble">G4 A4 B4 C5 *D5</staff></figure></step>
    </worked>
    <check id="middle-line">
      <prompt>Which note is on the middle line of the treble staff?</prompt>
      <figure><staff clef="treble">B4</staff>
        <description>Treble staff with one note on the middle line.</description></figure>
      <option key="a"><note>A4</note></option>
      <option key="b" correct="true"><note>B4</note></option>
      <option key="c"><note>C5</note></option>
      <explanation>From <note>G4</note> on the second line, the second space is
        <note>A4</note> and the middle line is <note>B4</note>.</explanation>
    </check>
  </section>
</lesson>
"""


def lesson() -> Lesson:
    """A short lesson with every kind of block (English sample content)."""
    return parse_lesson(ET.fromstring(_LESSON), 'preview lesson')


def glossary_entries() -> tuple[GlossaryEntry, ...]:
    entries = parse_glossary(ET.fromstring(_GLOSSARY), 'preview glossary')
    return tuple(sorted(entries, key=lambda e: e.headword.casefold()))


def glossary() -> GlossaryData:
    return GlossaryData(
        glossary_entries(),
        {1: _('Fundamentals'), 2: _('Diatonic Harmony')},
        vocabulary_available=True,
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
                ChipGroup('root', _('Root'), letters, accidentals=True),
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
    # The rhythm questions come from the real exercises, which also grade them.
    rhythm_input = _RHYTHM['rhythm-dictation'].generate(
        ItemId('rhythm.dictation.eighths'),
        {**_RHYTHM['rhythm-dictation'].default_settings(), 'meters': ('4/4',)},
        random.Random(2),
    )
    tap = _RHYTHM['rhythm-tap'].generate(
        ItemId('rhythm.tap.eighths'),
        {**_RHYTHM['rhythm-tap'].default_settings(), 'meters': ('4/4',), 'bars': 1},
        random.Random(2),
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
    if question.exercise_id in _RHYTHM:
        return _RHYTHM[question.exercise_id].grade(question, given)
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
    name: str = ''
    """Title of the session (a unit, an exam); the current exercise's title when empty."""
    outcome: SessionOutcome | None = None
    """What the session decides when it ends (exams and the placement test)."""

    @property
    def current(self) -> PreviewQuestion:
        return self.questions[self.keys[self.index % len(self.keys)]]

    @property
    def number(self) -> int:
        return self.start + self.index

    @property
    def accuracy(self) -> float:
        return self.correct / self.answered if self.answered else 0.0

    @property
    def title(self) -> str:
        return self.name or self.current.exercise_title

    def answer(self, given: object, *, response_ms: int = 0, hinted: bool = False) -> Feedback:
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

    def skip(self, *, response_ms: int = 0) -> Feedback:
        item = self.current
        self.answered += 1
        self.streak = 0
        self.mistakes.append(item.question.item_id)
        label = answer_label(item.question, item.question.expected)
        return Feedback(
            False, _('Skipped — the answer is {answer}').format(answer=label), item.detail
        )

    def answer_label(self, value: object) -> str:
        return answer_label(self.current.question, value)

    def advance(self) -> bool:
        """Move to the next question; ``False`` when the session is over."""
        if self.number >= self.total:
            return False
        self.index += 1
        return True

    def finish(self) -> SessionSummary:
        return self.summary()

    def again(self) -> PreviewSession:
        return PreviewSession(self.keys, start=1, total=self.total)

    def review_mistakes(self, summary: SessionSummary) -> PreviewSession:
        return PreviewSession(self.keys, start=1, total=max(1, len(summary.mistakes)))

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


# The preview model -------------------------------------------------------------------


class PreviewModel:
    """An :class:`~etude.ui.model.AppModel` with the design's fixed data."""

    def __init__(self, *, caught_up: bool = False) -> None:
        self.played: list[PlaybackSpec] = []
        """Playbacks requested so far; nothing is heard."""
        self.audio = NullBackend(available=True)
        self.started: list[tuple[SessionMode, str | None, tuple[ItemId, ...]]] = []
        self.caught_up = caught_up
        """Show the Today page's "All caught up" state and a brand-new learner's progress
        and path (with the placement test)."""
        self._continue: ContinueData | None = continue_data()
        self.completed_lessons: set[str] = set()
        self.path_started: list[tuple[str, str]] = []
        """Path sessions started: ``('unit', id)``, ``('exam', id)`` or ``('placement', '')``."""

    def exercise_cards(self) -> tuple[ExerciseCardData, ...]:
        return exercise_cards()

    def continue_data(self) -> ContinueData | None:
        return self._continue

    def streak(self) -> StreakData:
        return streak()

    def today(self) -> TodayData:
        return caught_up_today() if self.caught_up else today()

    def progress(self, period: str) -> ProgressData:
        return empty_progress(period) if self.caught_up else progress(period)

    def definition(self, exercise_id: str) -> ExerciseDefinition | None:
        return PreviewKeySignatures() if exercise_id == PreviewKeySignatures.id else None

    def start(
        self,
        mode: SessionMode,
        *,
        exercise_id: str | None = None,
        item_ids: tuple[ItemId, ...] = (),
    ) -> PreviewSession:
        self.started.append((mode, exercise_id, item_ids))
        self._continue = None
        questions = preview_questions()
        key = exercise_id if exercise_id in questions else 'interval-ear'
        return PreviewSession([key])

    def close_session(self, session: SessionSource) -> None:
        if isinstance(session, PreviewSession):
            item = session.current
            self._continue = ContinueData(
                item.question.exercise_id,
                item.exercise_title,
                session.number - 1,
                session.total,
                session.accuracy,
            )

    def resume(self) -> PreviewSession | None:
        if self._continue is None:
            return None
        self._continue = None
        return PreviewSession(['interval-ear'])

    def dismiss_continue(self) -> None:
        self._continue = None

    # The learning path

    def path(self) -> PathData:
        data = path(new_learner=self.caught_up)
        if not self.completed_lessons:
            return data
        levels = tuple(
            replace(
                level,
                units=tuple(
                    replace(u, lesson_done=u.lesson_done or u.lesson_id in self.completed_lessons)
                    for u in level.units
                ),
            )
            for level in data.levels
        )
        return PathData(levels, data.placement_available)

    def lesson(self, lesson_id: str) -> Lesson | None:
        return lesson() if lesson_id == 'l1.staff' else None

    def glossary(self) -> GlossaryData:
        return glossary()

    def glossary_entry(self, entry_id: str) -> GlossaryEntry | None:
        return next((e for e in glossary_entries() if e.id == entry_id), None)

    def complete_lesson(self, lesson_id: str) -> None:
        self.completed_lessons.add(lesson_id)

    def _path_session(
        self, kind: str, key: str, keys: list[str], **kwargs: object
    ) -> PreviewSession:
        self.path_started.append((kind, key))
        self._continue = None
        return PreviewSession(keys, start=1, **kwargs)  # type: ignore[arg-type]

    def start_unit(self, unit_id: str) -> PreviewSession:
        title = next(t for u, t, _s in _UNITS if u == unit_id)
        return self._path_session('unit', unit_id, ['note-naming'], name=title)

    def start_exam(self, level_id: str) -> PreviewSession:
        return self._path_session(
            'exam',
            level_id,
            ['keysig', 'note-naming', 'interval-staff'],
            total=30,
            name=_('Level {number} Exam').format(number=1),
            outcome=exam_outcome(1, 26, 30, complete=True),
        )

    def start_placement(self) -> PreviewSession:
        return self._path_session(
            'placement',
            '',
            ['note-naming', 'keysig'],
            total=15,
            name=_('Placement Test'),
            outcome=placement_outcome(3, _UNITS[3][1]),
        )

    def session_outcome(self, session: SessionSource) -> SessionOutcome | None:
        return session.outcome if isinstance(session, PreviewSession) else None

    @property
    def audio_available(self) -> bool:
        return True

    def new_question(self) -> None:
        pass

    def play(
        self,
        spec: PlaybackSpec,
        *,
        on_beat: Callable[[int], None] | None = None,
        on_finished: Callable[[], None] | None = None,
    ) -> NullHandle:
        """Nothing is heard; tests drive beats and the end with ``self.audio.complete()``."""
        self.played.append(spec)
        return self.audio.play(spec, on_beat=on_beat, on_finished=on_finished)

    def stop_audio(self) -> None:
        pass
