# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Four-part (SATB) harmony: write a progression, and find the mistake in one.

*Four-Part Writing* gives a bass with Roman numerals on a grand staff and asks
for the upper voices: soprano, alto and tenor, or alto and tenor between a
given soprano and bass. Any correct realisation is right: the answer is
graded by the voice-leading checker (:mod:`etude.checkers.voice_leading`).
No error and the right chords make it correct; warnings are shown but not
penalised; the score is the share of chords without an error. Items are
progressions in teaching order, from I–V–I to seventh chords
(``satb.write.I-IV-V-I``, ``satb.write.ii6-V-I``, ``satb.write.V7-I``,
``satb.write.deceptive`` …); key, mode, bass line and task vary.

*Spot the Error* shows a short correct passage with exactly one mistake put in
(generated from a correct realisation and verified with the checker) and asks
what is wrong. Items are mistakes (``satb.error.parallel-fifths`` …); the
feedback marks the notes on the staff and says why the rule matters.
Answering is by choice only: clicking chords is not used, since a mistake
such as parallel fifths spans two chords.

Model answers come from :mod:`etude.checkers.realize`.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from gettext import gettext as _
from gettext import ngettext
from typing import ClassVar, cast

from ...audio.spec import PlaybackSpec
from ...checkers.realize import RealisationError, Voicing, chords_of, realize
from ...checkers.voice_leading import (
    ALTO,
    BASS,
    SOPRANO,
    TENOR,
    Context,
    Ranges,
    Rule,
    Severity,
    Violation,
    check,
    rule_mark,
    rule_name,
    rule_reason,
    scan,
    voice_title,
)
from ...core import Chord, Duration, Interval, NoteValue, Pitch, RomanNumeral
from ...core.naming import key_name, pitch_name
from ...core.scale import Key, Mode
from ...learning.model import ItemId
from ...notation.spec import Chord as StaffChord
from ...notation.spec import Clef, Ink, SystemSpec
from ..base import (
    BoolSetting,
    ChoiceAnswer,
    ChoiceSetting,
    ExerciseDefinition,
    Family,
    Feedback,
    IntSetting,
    Modality,
    MultiChoiceSetting,
    Option,
    Question,
    Setting,
    StaffInputAnswer,
)
from .harmony import (
    MAX_ACCIDENTALS,
    keys_within,
    limit_setting,
    modes_setting,
    progression_playback,
    roman_label,
    satb_figure,
    satb_voices,
)

STAVES = (Clef.TREBLE, Clef.BASS)
VOICE_STAVES = (0, 0, 1, 1)
QUARTER = Duration(NoteValue.QUARTER)
MAX_LISTED = 3
"""Mistakes spelled out in feedback; the staff marks all of them."""
_MAX_ATTEMPTS = 40


# Progressions -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Progression:
    key: str
    """Item segment, e.g. ``'I-IV-V-I'``."""
    major: tuple[str, ...]
    minor: tuple[str, ...]

    @property
    def sevenths(self) -> bool:
        return any('7' in n or n[-2:] in ('65', '43', '42') for n in self.major)

    def numerals(self, mode: Mode) -> tuple[RomanNumeral, ...]:
        names = self.major if mode is Mode.MAJOR else self.minor
        return tuple(RomanNumeral.parse(n) for n in names)


PROGRESSIONS = (
    Progression('I-V-I', ('I', 'V', 'I'), ('i', 'V', 'i')),
    Progression('I-IV-I', ('I', 'IV', 'I'), ('i', 'iv', 'i')),
    Progression('I-IV-V-I', ('I', 'IV', 'V', 'I'), ('i', 'iv', 'V', 'i')),
    Progression('I-vi-IV-V-I', ('I', 'vi', 'IV', 'V', 'I'), ('i', 'VI', 'iv', 'V', 'i')),
    Progression('I6', ('I', 'I6', 'IV', 'V', 'I'), ('i', 'i6', 'iv', 'V', 'i')),
    Progression('ii6-V-I', ('I', 'ii6', 'V', 'I'), ('i', 'iio6', 'V', 'i')),
    Progression('cadential-64', ('I', 'IV', 'Cad64', 'V', 'I'), ('i', 'iv', 'Cad64', 'V', 'i')),
    Progression('deceptive', ('I', 'IV', 'V', 'vi'), ('i', 'iv', 'V', 'VI')),
    Progression('viio6', ('I', 'viio6', 'I6'), ('i', 'viio6', 'i6')),
    Progression('V7-I', ('I', 'V7', 'I'), ('i', 'V7', 'i')),
    Progression('V65-I', ('I', 'V65', 'I'), ('i', 'V65', 'i')),
    Progression('V43-I6', ('I', 'V43', 'I6'), ('i', 'V43', 'i6')),
    Progression('V42-I6', ('I', 'V42', 'I6'), ('i', 'V42', 'i6')),
    Progression('ii65-V7-I', ('I', 'ii65', 'V7', 'I'), ('i', 'iiø65', 'V7', 'i')),
)
"""In teaching order: root-position triads, inversions, then seventh chords."""
_BY_KEY = {p.key: p for p in PROGRESSIONS}


def progression_text(labels: Sequence[str]) -> str:
    return ' – '.join(labels)


def _pick_key(settings: Mapping[str, object], rng: random.Random) -> Key:
    return rng.choice(keys_within(limit_setting(settings, 3), modes_setting(settings, 'both')))


def question_key(question: Question) -> Key:
    """The key a question was asked in (kept in :attr:`Question.details`)."""
    return Key.parse(question.details['key'])


def tonic_key(chord: Sequence[Pitch]) -> Key:
    """The key of a passage from its first chord, a root-position tonic triad."""
    bass = min(chord)
    for pitch in chord:
        if (pitch.letter - bass.letter) % 7 == 2:
            third = Interval.between(bass, Pitch(pitch.letter, pitch.alter, bass.octave + 1))
            third = third.simple()
            mode = Mode.MAJOR if third == Interval.parse('M3') else Mode.MINOR
            return Key(bass.name, mode)
    return Key(bass.name)


def harmony_of(labels: Sequence[str], key: Key) -> tuple[Chord, ...]:
    return tuple(RomanNumeral.parse(label).realize(key) for label in labels)


def note_text(pitch: Pitch) -> str:
    return pitch_name(pitch.name) + str(pitch.octave)


def chords_text(chords: Sequence[Sequence[Pitch]]) -> str:
    # Translators: separator between the chords of a four-part answer in feedback.
    return _(' | ').join(' '.join(note_text(p) for p in chord) for chord in chords)


def passage_figure(
    chords: Sequence[Sequence[Pitch]],
    key: Key,
    labels: Sequence[str],
    *,
    inks: Mapping[tuple[int, int], Ink] | None = None,
    marks: Mapping[int, str] | None = None,
    description: str | None = None,
    breaks: Sequence[int] = (),
) -> SystemSpec:
    """Four voices on a grand staff in quarter notes, numerals under the bass.

    ``inks`` colours notes by ``(voice, slot)``; ``marks`` writes a short text under
    the upper staff at a slot (the rule a mistake breaks), in error ink; ``breaks``
    draws a double bar after those slots.
    """
    voicings = [(c[0], c[1], c[2], c[3]) for c in chords]
    return satb_figure(
        voicings,
        key.signature,
        durations=(QUARTER,) * len(chords),
        labels=labels,
        inks=inks,
        marks=marks,
        description=description,
        breaks=breaks,
    )


def passage_playback(chords: Sequence[Sequence[Pitch]]) -> PlaybackSpec:
    return progression_playback(chords, tempo=72.0)


def _realisation(
    progression: Progression, key: Key, rng: random.Random
) -> tuple[tuple[Chord, ...], tuple[Voicing, ...]]:
    harmony = chords_of(progression.numerals(key.mode), key)
    return harmony, realize(harmony, key, rng)


def _marked(
    chords: Sequence[Sequence[Pitch]],
    violations: Sequence[Violation],
    *,
    given: frozenset[int] = frozenset(),
    correct_ink: bool = False,
) -> tuple[dict[tuple[int, int], Ink], dict[int, str]]:
    """Inks and marks for an answer: the notes of every error in error ink, and a short
    mark under the treble staff for the errors the feedback lists (the first
    :data:`MAX_LISTED`), merged into one label per chord."""
    inks: dict[tuple[int, int], Ink] = {}
    if correct_ink:
        for slot in range(len(chords)):
            for voice in range(4):
                if voice not in given:
                    inks[voice, slot] = Ink.SUCCESS
    marks: dict[int, list[str]] = {}
    errors = [v for v in violations if v.severity is Severity.ERROR]
    for violation in errors:
        for slot in violation.slots:
            for voice in violation.voices:
                inks[voice, slot] = Ink.ERROR
    for violation in errors[:MAX_LISTED]:
        mark = rule_mark(violation.rule)
        if mark not in marks.setdefault(violation.slot, []):
            marks[violation.slot].append(mark)
    return inks, {slot: ' '.join(m) for slot, m in marks.items()}


def _settings_common() -> tuple[Setting, ...]:
    return (
        ChoiceSetting(
            'mode',
            _('Keys'),
            (
                Option('major', _('Major keys')),
                Option('minor', _('Minor keys')),
                Option('both', _('Major and minor')),
            ),
            'both',
        ),
        IntSetting(
            'max-accidentals',
            _('Most accidentals'),
            3,
            0,
            MAX_ACCIDENTALS,
            subtitle=_('Largest number of sharps or flats in the key signature'),
        ),
    )


def _describe(settings: Mapping[str, object]) -> list[str]:
    modes = modes_setting(settings, 'both')
    if modes == (Mode.MAJOR,):
        parts = [_('Major keys')]
    elif modes == (Mode.MINOR,):
        parts = [_('Minor keys')]
    else:
        parts = [_('Major and minor')]
    limit = limit_setting(settings, 3)
    parts.append(ngettext('up to {n} accidental', 'up to {n} accidentals', limit).format(n=limit))
    return parts


# Four-part writing --------------------------------------------------------------------


def _progression_title(key: str) -> str:
    titles: dict[str, Callable[[], str]] = {
        'I-V-I': lambda: _('Tonic and dominant'),
        'I-IV-I': lambda: _('Tonic and subdominant'),
        'I-IV-V-I': lambda: _('Authentic cadence'),
        'I-vi-IV-V-I': lambda: _('Submediant'),
        'I6': lambda: _('First-inversion tonic'),
        'ii6-V-I': lambda: _('Supertonic six'),
        'cadential-64': lambda: _('Cadential six-four'),
        'deceptive': lambda: _('Deceptive cadence'),
        'viio6': lambda: _('Leading-tone triad'),
        'V7-I': lambda: _('Dominant seventh'),
        'V65-I': lambda: _('V6/5'),
        'V43-I6': lambda: _('V4/3'),
        'V42-I6': lambda: _('V4/2'),
        'ii65-V7-I': lambda: _('Supertonic seventh'),
    }
    return titles[key]()


class FourPartWriting(ExerciseDefinition):
    id = 'satb-writing'
    item_prefix = 'satb.write.'
    family = Family.HARMONY
    modality = Modality.EYE
    level = 2
    icon_name = 'satb-writing-symbolic'
    glyph = '𝄢'
    settings: ClassVar[tuple[Setting, ...]] = (
        *_settings_common(),
        ChoiceSetting(
            'task',
            _('Voices to write'),
            (
                Option('inner', _('Alto and tenor')),
                Option('upper', _('Soprano, alto and tenor')),
                Option('both', _('Both')),
            ),
            'both',
            subtitle=_('The bass is always given; with alto and tenor, the soprano too'),
        ),
        BoolSetting('sevenths', _('Seventh chords'), True),
    )

    @property
    def title(self) -> str:
        return _('Four-Part Writing')

    @property
    def description(self) -> str:
        return _('Write the upper voices of a progression over a given bass.')

    @property
    def play_label(self) -> str:
        return _('Play')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        parts = _describe(settings)
        task = str(settings.get('task', 'both'))
        if task == 'inner':
            parts.append(_('alto and tenor'))
        elif task == 'upper':
            parts.append(_('soprano, alto and tenor'))
        # Translators: separator between the parts of an exercise subtitle.
        return _(' · ').join(parts)

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        sevenths = bool(settings.get('sevenths', True))
        return [ItemId(f'satb.write.{p.key}') for p in PROGRESSIONS if sevenths or not p.sevenths]

    def item_label(self, item_id: ItemId) -> str:
        progression = _parse_write(item_id)
        labels = [roman_label(n) for n in progression.numerals(Mode.MAJOR)]
        # Translators: an item in "Weakest items", e.g. "Authentic cadence: I – IV – V – I".
        return _('{title}: {progression}').format(
            title=_progression_title(progression.key), progression=progression_text(labels)
        )

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        pairs = {
            'I-IV-V-I': 'deceptive',
            'deceptive': 'I-IV-V-I',
            'V65-I': 'V43-I6',
            'V43-I6': 'V42-I6',
            'V42-I6': 'V43-I6',
        }
        partner = pairs.get(_parse_write(item_id).key)
        return [ItemId(f'satb.write.{partner}')] if partner else []

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        progression = _parse_write(item_id)
        key = _pick_key(settings, rng)
        _harmony, chords = _realisation(progression, key, rng)
        labels = tuple(roman_label(n) for n in progression.numerals(key.mode))
        task = str(settings.get('task', 'both'))
        if task not in ('inner', 'upper'):
            task = rng.choice(('inner', 'upper'))
        given: dict[int, tuple[Pitch, ...]] = {BASS: tuple(c[BASS] for c in chords)}
        name = key_name(key)
        if task == 'inner':
            given[SOPRANO] = tuple(c[SOPRANO] for c in chords)
            # Translators: e.g. "Write the alto and tenor in G major".
            prompt = _('Write the alto and tenor in {key}').format(key=name)
        else:
            # Translators: e.g. "Write soprano, alto and tenor above the bass in G major".
            prompt = _('Write soprano, alto and tenor above the bass in {key}').format(key=name)
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=prompt,
            answer=StaffInputAnswer(
                clef=Clef.TREBLE,
                key_signature=key.signature,
                slots=len(chords),
                voices=4,
                staves=STAVES,
                voice_staves=VOICE_STAVES,
                given_voices=given,
                labels=labels,
            ),
            expected=tuple(chords),
            context=progression_text(labels),
            details={'key': str(key)},
            hint=_(
                'Spell each chord first. Double the root of root-position chords, keep '
                'common tones in the same voice, and move the other voices to the nearest '
                'chord tone.'
            ),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        answer = question.answer
        assert isinstance(answer, StaffInputAnswer)
        key = question_key(question)
        return grade_four_part(question, given, Context(key, harmony_of(answer.labels, key)))

    def answer_label(self, question: Question, value: object) -> str:
        chords = _four_part(value, None)
        return chords_text(chords) if chords is not None else str(value)

    def serialize(self, value: object) -> str:
        chords = _four_part(value, None)
        if chords is None:
            return str(value)
        return ' | '.join(' '.join(str(p) for p in chord) for chord in chords)


def grade_four_part(
    question: Question,
    given: object,
    context: Context | Callable[[Sequence[Voicing]], Context],
    *,
    breaks: Sequence[int] = (),
) -> Feedback:
    """Grade a four-part answer to a :class:`StaffInputAnswer` question with the checker:
    correct without errors, warnings mentioned, the score the share of chords without
    an error, the first :data:`MAX_LISTED` mistakes explained and every one marked on
    the learner's staff. ``context`` may depend on the answer (a chord the numeral allows
    two spellings of); ``breaks`` are the double bars of the figure."""
    answer = question.answer
    assert isinstance(answer, StaffInputAnswer)
    expected = cast(tuple[Voicing, ...], question.expected)
    play_expected = passage_playback(expected)
    chords = _four_part(given, len(expected))
    if chords is None:
        return Feedback(
            correct=False,
            title=_('Not quite — write every voice of every chord'),
            detail=_('Each chord needs a soprano, alto, tenor and bass.'),
            expected_label=chords_text(expected),
            score=0.0,
            play_expected=play_expected,
        )
    for voice, pitches in answer.given_voices.items():
        if tuple(c[voice] for c in chords) != tuple(pitches):
            return Feedback(
                correct=False,
                title=_('Not quite — the printed voices must stay as they are'),
                detail=_('Write only the voices that are not printed.'),
                expected_label=chords_text(expected),
                score=0.0,
                play_expected=play_expected,
            )
    if callable(context):
        context = context(chords)
    key = context.key
    assert key is not None
    violations = check(chords, context)
    errors = [v for v in violations if v.severity is Severity.ERROR]
    warnings = [v for v in violations if v.severity is Severity.WARNING]
    wrong_slots = {v.slot for v in errors}
    score = 1.0 - len(wrong_slots) / len(chords)
    correct = not errors
    if correct:
        title = _('Correct — no voice-leading errors')
    else:
        title = ngettext(
            'Not quite — {n} voice-leading error',
            'Not quite — {n} voice-leading errors',
            len(errors),
        ).format(n=len(errors))
    shown = errors[:MAX_LISTED]
    sentences: list[str] = [f'{v.message}.' for v in shown]
    if len(errors) > len(shown):
        more = len(errors) - len(shown)
        # Translators: after the first few voice-leading mistakes, e.g. "And 3 more."
        sentences.append(ngettext('And {n} more.', 'And {n} more.', more).format(n=more))
    reasons = list(dict.fromkeys(rule_reason(v.rule) for v in errors))
    sentences += reasons[:2]
    if warnings:
        # Translators: introduces voice-leading weaknesses that are not counted as
        # mistakes, e.g. "Worth noticing: The tenor leaps more than a fourth …".
        sentences.append(
            _('Worth noticing: {items}').format(
                items=' '.join(f'{w.message}.' for w in warnings[:MAX_LISTED])
            )
        )
    if correct and not warnings:
        sentences.append(_('Every chord is complete, well spaced and smoothly connected.'))
    inks, marks = _marked(
        chords, violations, given=frozenset(answer.given_voices), correct_ink=correct
    )
    figure = passage_figure(
        chords,
        key,
        answer.labels,
        inks=inks,
        marks=marks,
        description=_figure_description(chords, errors, key),
        breaks=breaks,
    )
    return Feedback(
        correct=correct,
        title=title,
        detail=' '.join(sentences),
        expected_label=chords_text(expected),
        score=score,
        figure=figure,
        play_expected=play_expected,
        play_given=passage_playback(chords),
    )


def _figure_description(
    chords: Sequence[Sequence[Pitch]], errors: Sequence[Violation], key: Key
) -> str:
    parts = [_('Grand staff in {key}').format(key=key_name(key))]
    for voice in range(4):
        parts.append(f'{voice_title(voice)}: ' + ', '.join(note_text(c[voice]) for c in chords))
    parts += [v.message for v in errors]
    return _('. ').join(parts) + '.'


def _four_part(value: object, length: int | None) -> tuple[Voicing, ...] | None:
    if not isinstance(value, tuple) or not value:
        return None
    if length is not None and len(value) != length:
        return None
    chords: list[Voicing] = []
    for chord in value:
        if (
            not isinstance(chord, tuple)
            or len(chord) != 4
            or not all(isinstance(p, Pitch) for p in chord)
        ):
            return None
        chords.append((chord[0], chord[1], chord[2], chord[3]))
    return tuple(chords)


def _parse_write(item_id: str) -> Progression:
    prefix = 'satb.write.'
    if not item_id.startswith(prefix) or item_id[len(prefix) :] not in _BY_KEY:
        raise ValueError(f'not a four-part writing item: {item_id!r}')
    return _BY_KEY[item_id[len(prefix) :]]


# Spot the error -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Mistake:
    key: str
    rule: Rule
    progressions: tuple[str, ...]
    """Progressions a passage with this mistake is made from."""


_TRIADS = ('I-IV-V-I', 'I-V-I', 'I-IV-I', 'ii6-V-I', 'deceptive', 'viio6')
_SEVENTHS = ('V7-I', 'ii65-V7-I', 'V65-I', 'V42-I6')
MISTAKES = (
    Mistake('parallel-fifths', Rule.PARALLEL_FIFTHS, _TRIADS),
    Mistake('parallel-octaves', Rule.PARALLEL_OCTAVES, _TRIADS),
    Mistake('crossing', Rule.CROSSING, _TRIADS),
    Mistake('spacing', Rule.SPACING, _TRIADS),
    Mistake('doubled-leading-tone', Rule.WRONG_DOUBLING, ('I-V-I', 'I-IV-V-I', 'ii6-V-I')),
    Mistake('leading-tone', Rule.LEADING_TONE, ('I-V-I', 'I-IV-V-I', 'ii6-V-I', 'V7-I')),
    Mistake('seventh', Rule.CHORDAL_SEVENTH, _SEVENTHS),
)
_MISTAKES = {m.key: m for m in MISTAKES}
_CONFUSABLE_MISTAKES = {
    'parallel-fifths': ('parallel-octaves',),
    'parallel-octaves': ('parallel-fifths',),
    'crossing': ('spacing',),
    'spacing': ('crossing',),
    'doubled-leading-tone': ('leading-tone',),
    'leading-tone': ('doubled-leading-tone', 'seventh'),
    'seventh': ('leading-tone',),
}


def _mistake_label(key: str) -> str:
    if key == 'doubled-leading-tone':
        return _('Doubled leading tone')
    return rule_name(_MISTAKES[key].rule)


def _alternatives(chord: Voicing, harmony: Chord, voice: int, ranges: Ranges) -> list[Pitch]:
    """The other chord tones ``voice`` could sing in ``chord``, within its range."""
    low, high = ranges.of(voice)
    return [
        name.at(octave)
        for name in harmony.names()
        for octave in range(low.octave, high.octave + 1)
        if low.midi <= name.at(octave).midi <= high.midi and name.at(octave) != chord[voice]
    ]


def _mutations(
    chords: Sequence[Voicing], harmony: Sequence[Chord], ranges: Ranges, *, pairs: bool = False
) -> list[tuple[Voicing, ...]]:
    """Every passage with one upper-voice note changed to another chord tone, or two
    adjacent upper voices swapped in one chord; with ``pairs``, two upper-voice notes
    of one chord changed (a seventh that rises needs another voice to take its place)."""
    found: list[tuple[Voicing, ...]] = []
    upper_voices = (SOPRANO, ALTO, TENOR)
    for slot, chord in enumerate(chords):
        if pairs:
            for first, second in ((SOPRANO, ALTO), (SOPRANO, TENOR), (ALTO, TENOR)):
                for a in _alternatives(chord, harmony[slot], first, ranges):
                    for b in _alternatives(chord, harmony[slot], second, ranges):
                        changed = list(chord)
                        changed[first], changed[second] = a, b
                        found.append(_replace(chords, slot, changed))
            continue
        for voice in upper_voices:
            for pitch in _alternatives(chord, harmony[slot], voice, ranges):
                changed = list(chord)
                changed[voice] = pitch
                found.append(_replace(chords, slot, changed))
        for upper in (SOPRANO, ALTO):
            if chord[upper] != chord[upper + 1]:
                swapped = list(chord)
                swapped[upper], swapped[upper + 1] = chord[upper + 1], chord[upper]
                found.append(_replace(chords, slot, swapped))
    return found


def _replace(chords: Sequence[Voicing], slot: int, chord: list[Pitch]) -> tuple[Voicing, ...]:
    voicing: Voicing = (chord[0], chord[1], chord[2], chord[3])
    return (*chords[:slot], voicing, *chords[slot + 1 :])


def _is_example(mistake: Mistake, violations: Sequence[Violation]) -> bool:
    """Exactly one error, and it breaks the mistake's rule."""
    errors = [v for v in violations if v.severity is Severity.ERROR]
    return len(errors) == 1 and errors[0].rule is mistake.rule


def make_mistake(
    mistake: Mistake, key: Key, rng: random.Random
) -> tuple[Progression, tuple[Voicing, ...], Violation]:
    """A correct passage with exactly one ``mistake`` put in, and the violation."""
    ranges = Ranges()
    for _attempt in range(_MAX_ATTEMPTS):
        progression = _BY_KEY[rng.choice(mistake.progressions)]
        harmony, chords = _realisation(progression, key, rng)
        context = Context(key, harmony, ranges)
        candidates: list[tuple[tuple[Voicing, ...], bool]] = []
        for pairs in (False, True):
            for passage in _mutations(chords, harmony, ranges, pairs=pairs):
                violations = scan(passage, context)
                if not _is_example(mistake, violations):
                    continue
                if mistake.key == 'doubled-leading-tone' and not _doubles_leading_tone(
                    passage, violations, key
                ):
                    continue
                no_warnings = all(v.severity is Severity.ERROR for v in violations)
                candidates.append((passage, no_warnings))
            if candidates:
                break
        if not candidates:
            continue
        clean = [p for p, ok in candidates if ok]
        passage = rng.choice(clean or [p for p, _ok in candidates])
        violation = next(v for v in check(passage, context) if v.severity is Severity.ERROR)
        return progression, passage, violation
    raise RealisationError(f'no example of {mistake.key} in {key}')  # pragma: no cover


def _doubles_leading_tone(
    passage: Sequence[Voicing], violations: Sequence[Violation], key: Key
) -> bool:
    error = next(v for v in violations if v.severity is Severity.ERROR)
    return all(passage[error.slot][v].name == key.leading_tone for v in error.voices)


def passage_of(figure: object) -> tuple[tuple[Voicing, ...], tuple[str, ...]]:
    """The chords and numerals of a passage figure made by :func:`passage_figure`."""
    assert isinstance(figure, SystemSpec)
    bass = figure.staves[1].voices[0]
    labels = tuple(e.label or '' for e in bass if isinstance(e, StaffChord))
    return tuple(satb_voices(figure)), labels


class SpotTheError(ExerciseDefinition):
    id = 'satb-errors'
    item_prefix = 'satb.error.'
    family = Family.HARMONY
    modality = Modality.EYE
    level = 2
    icon_name = 'satb-errors-symbolic'
    glyph = '∥'
    settings: ClassVar[tuple[Setting, ...]] = (
        *_settings_common(),
        MultiChoiceSetting(
            'mistakes',
            _('Mistakes'),
            tuple(Option(m.key, _mistake_label(m.key)) for m in MISTAKES),
            tuple(m.key for m in MISTAKES),
            minimum=2,
        ),
    )

    @property
    def title(self) -> str:
        return _('Spot the Error')

    @property
    def description(self) -> str:
        return _('Find the voice-leading mistake in a four-part passage.')

    @property
    def play_label(self) -> str:
        return _('Play passage')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        return _(' · ').join(_describe(settings))

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        chosen = settings.get('mistakes', tuple(_MISTAKES))
        keys = set(cast(Sequence[str], chosen)) if isinstance(chosen, list | tuple) else set()
        selected = [m.key for m in MISTAKES if m.key in keys] or [m.key for m in MISTAKES]
        return [ItemId(f'satb.error.{key}') for key in selected]

    def item_label(self, item_id: ItemId) -> str:
        # Translators: an item in "Weakest items", e.g. "Parallel fifths (spot the error)".
        return _('{mistake} (spot the error)').format(
            mistake=_mistake_label(_parse_error(item_id).key)
        )

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        key = _parse_error(item_id).key
        return [ItemId(f'satb.error.{k}') for k in _CONFUSABLE_MISTAKES.get(key, ())]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        mistake = _parse_error(item_id)
        key = _pick_key(settings, rng)
        progression, passage, _violation = make_mistake(mistake, key, rng)
        labels = tuple(roman_label(n) for n in progression.numerals(key.mode))
        options = tuple(
            Option(m.key, _mistake_label(m.key), accel=str(index + 1))
            for index, m in enumerate(MISTAKES)
        )
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Which mistake is in this passage?'),
            answer=ChoiceAnswer(options),
            expected=mistake.key,
            figure=passage_figure(passage, key, labels),
            playback=passage_playback(passage),
            context=key_name(key),
            details={'key': str(key)},
            hint=_(
                'Compare each pair of voices from chord to chord, then look at each chord '
                'on its own: spacing, doubling, the leading tone and sevenths.'
            ),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        chords, labels = passage_of(question.figure)
        key = question_key(question)
        context = Context(key, harmony_of(labels, key))
        violation = next(v for v in check(chords, context) if v.severity is Severity.ERROR)
        expected = str(question.expected)
        correct = given == expected
        label = _mistake_label(expected)
        if correct:
            # Translators: e.g. "Correct — parallel fifths".
            title = _('Correct — {mistake}').format(mistake=label)
        else:
            # Translators: e.g. "Not quite — the mistake is parallel fifths".
            title = _('Not quite — the mistake is: {mistake}').format(mistake=label)
        inks, marks = _marked(chords, [violation])
        figure = passage_figure(
            chords,
            key,
            labels,
            inks=inks,
            marks=marks,
            description=_figure_description(chords, [violation], key),
        )
        return Feedback(
            correct=correct,
            title=title,
            detail=f'{violation.message}. {rule_reason(violation.rule)}',
            expected_label=label,
            figure=figure,
            play_expected=passage_playback(chords),
        )


def _parse_error(item_id: str) -> Mistake:
    prefix = 'satb.error.'
    if not item_id.startswith(prefix) or item_id[len(prefix) :] not in _MISTAKES:
        raise ValueError(f'not a spot-the-error item: {item_id!r}')
    return _MISTAKES[item_id[len(prefix) :]]


EXERCISES: tuple[ExerciseDefinition, ...] = (FourPartWriting(), SpotTheError())
