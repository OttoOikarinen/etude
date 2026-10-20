# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Chord progressions by ear: hear a short progression in four parts and name it.

Items are progressions, ``progression.ear.I-vi-IV-V`` or
``progression.ear.i-VII-VI-V`` (ASCII numerals: ``o`` for °; upper case is
major, lower case minor, so the id also says the mode). They are the
progressions of common-practice and popular harmony that learners meet first
(Kostka & Payne, *Tonal Harmony*, ch. 7; Nobile, "Teaching popular music
harmony"): the I–IV–V–I and I–ii–V–I cadential models, ii–V–I, the
"doo-wop" I–vi–IV–V and I–vi–ii–V, the "axis" I–V–vi–IV, and in minor
i–iv–V–i, i–ii°⁶–V–i, i–VI–iv–V, the Andalusian i–VII–VI–V and the Aeolian
i–VI–III–VII.

Two tasks (setting ``task``):

* **Name it** (default): choose the progression among the selected ones in
  the same mode, labelled with proper symbols (ii°⁶, V⁷).
* **Spot the change**: the written progression is shown, and the one played
  differs in one chord (IV becomes ii, V becomes iii …); the learner picks the
  chord that differs.

Progressions are voiced by :mod:`.four_part` in the question's key with the
soprano starting on a varied chord tone; key, mode, instrument and tempo come
from the settings.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from fractions import Fraction
from gettext import gettext as _
from gettext import ngettext
from typing import ClassVar, cast

from ...audio.spec import PlaybackSpec
from ...core import Duration, NoteValue, PitchName
from ...core.naming import key_name, pitch_name
from ...core.roman import RomanNumeral
from ...core.scale import Key, Mode
from ...learning.model import ItemId
from ...notation.spec import Ink
from ..base import (
    ChoiceAnswer,
    ChoiceSetting,
    ExerciseDefinition,
    Family,
    Feedback,
    Modality,
    MultiChoiceSetting,
    Option,
    Question,
    Setting,
)
from .four_part import (
    NoVoicingError,
    Voicing,
    describe_keys,
    harmony_settings,
    key_of,
    mode_setting,
    modes,
    numeral_label,
    parse_numerals,
    pick_instrument,
    pick_key,
    progression_label,
    progression_playback,
    system_figure,
    tempo_of,
    voice_progression,
    voicings_of,
)

MAJOR = ('I-IV-V-I', 'I-ii-V-I', 'ii-V-I', 'I-vi-IV-V', 'I-vi-ii-V', 'I-V-vi-IV')
MINOR = ('i-iv-V-i', 'i-iio6-V-i', 'i-VI-iv-V', 'i-VII-VI-V', 'i-VI-III-VII')
PROGRESSIONS = (*MAJOR, *MINOR)
"""In teaching order."""

_CONFUSABLE: dict[str, tuple[str, ...]] = {
    'I-IV-V-I': ('I-ii-V-I',),
    'I-ii-V-I': ('I-IV-V-I', 'ii-V-I'),
    'ii-V-I': ('I-ii-V-I',),
    'I-vi-IV-V': ('I-vi-ii-V', 'I-V-vi-IV'),
    'I-vi-ii-V': ('I-vi-IV-V',),
    'I-V-vi-IV': ('I-vi-IV-V',),
    'i-iv-V-i': ('i-iio6-V-i',),
    'i-iio6-V-i': ('i-iv-V-i',),
    'i-VI-iv-V': ('i-VII-VI-V', 'i-VI-III-VII'),
    'i-VII-VI-V': ('i-VI-iv-V',),
    'i-VI-III-VII': ('i-VI-iv-V',),
}

# Chords that can stand in for a chord in "spot the change": the same function
# (ii for IV, iii or vii°⁶ for V) or a common-tone neighbour (vi for I or IV).
_SUBSTITUTES: dict[Mode, dict[str, tuple[str, ...]]] = {
    Mode.MAJOR: {
        'I': ('vi',),
        'ii': ('IV',),
        'IV': ('ii', 'vi'),
        'V': ('iii', 'viio6'),
        'vi': ('IV', 'iii'),
    },
    Mode.MINOR: {
        'i': ('VI',),
        'iio6': ('iv',),
        'iv': ('iio6', 'VI'),
        'V': ('VII',),
        'VI': ('iv', 'III'),
        'III': ('VI',),
        'VII': ('V',),
    },
}
_MIN_OPTIONS = 3

NAME = 'name'
CHANGE = 'change'


def mode_of(progression: str) -> Mode:
    return Mode.MAJOR if progression in MAJOR else Mode.MINOR


def item_id(progression: str) -> ItemId:
    """``progression.ear.I-vi-IV-V``."""
    return ItemId(f'progression.ear.{progression}')


def parse_item(item: str) -> str:
    prefix = 'progression.ear.'
    progression = item.removeprefix(prefix)
    if not item.startswith(prefix) or progression not in PROGRESSIONS:
        raise ValueError(f'not a progression item: {item!r}')
    return progression


def label(progression: str) -> str:
    """``'I–ii°⁶–V–I'``."""
    return progression_label(parse_numerals(progression))


def _selected(settings: Mapping[str, object]) -> list[str]:
    value = settings.get('progressions', PROGRESSIONS)
    chosen = (
        {str(v) for v in cast(Sequence[object], value)} if not isinstance(value, str) else {value}
    )
    allowed = modes(settings)
    pool = [p for p in PROGRESSIONS if p in chosen and mode_of(p) in allowed]
    return pool or [p for p in PROGRESSIONS if mode_of(p) in allowed]


def voiced(key: Key, numerals: tuple[RomanNumeral, ...], soprano: PitchName) -> tuple[Voicing, ...]:
    return voice_progression(key, numerals, frozenset((soprano,)), None)


def _realize(
    key: Key, numerals: tuple[RomanNumeral, ...], rng: random.Random
) -> tuple[Voicing, ...]:
    """A voicing whose soprano starts on a chord tone chosen at random."""
    tones = list(numerals[0].realize(key).names())
    rng.shuffle(tones)
    for tone in tones:
        try:
            return voiced(key, numerals, tone)
        except NoVoicingError:
            continue
    return voice_progression(key, numerals)


def changes(progression: str) -> list[tuple[int, str]]:
    """The (position, substitute) pairs of "spot the change": any chord after the
    first, replaced by one that differs from both neighbours."""
    chords = progression.split('-')
    result = []
    for index in range(1, len(chords)):
        before = chords[index - 1]
        after = chords[index + 1] if index + 1 < len(chords) else None
        for substitute in _SUBSTITUTES[mode_of(progression)].get(chords[index], ()):
            if substitute not in (before, after):
                result.append((index, substitute))
    return result


def _with_change(progression: str, index: int, substitute: str) -> str:
    chords = progression.split('-')
    chords[index] = substitute
    return '-'.join(chords)


def _voiced_like(
    key: Key, numerals: tuple[RomanNumeral, ...], like: Sequence[Voicing]
) -> tuple[Voicing, ...]:
    """``numerals`` voiced with the soprano starting where ``like`` starts, if it can."""
    try:
        return voiced(key, numerals, like[0][0].name)
    except NoVoicingError:
        return voice_progression(key, numerals)


def _playback_like(playback: PlaybackSpec, voicings: Sequence[Voicing]) -> PlaybackSpec:
    return progression_playback(
        voicings, _lengths(len(voicings)), tempo=playback.tempo, instrument=playback.instrument
    )


def _lengths(count: int) -> tuple[Fraction, ...]:
    return (*(Fraction(1),) * (count - 1), Fraction(2))


def _durations(count: int) -> tuple[Duration, ...]:
    return (*(Duration(NoteValue.QUARTER),) * (count - 1), Duration(NoteValue.HALF))


class ProgressionEar(ExerciseDefinition):
    id = 'progression-ear'
    item_prefix = 'progression.ear.'
    family = Family.EAR
    modality = Modality.EAR
    level = 2
    icon_name = 'progression-ear-symbolic'
    glyph = 'I–V'
    settings: ClassVar[tuple[Setting, ...]] = (
        mode_setting(),
        MultiChoiceSetting(
            'progressions',
            _('Progressions'),
            tuple(Option(p, label(p)) for p in PROGRESSIONS),
            PROGRESSIONS,
            subtitle=_('Only those in the chosen keys are asked'),
        ),
        ChoiceSetting(
            'task',
            _('Task'),
            (
                Option(NAME, _('Name the progression')),
                Option(CHANGE, _('Spot the changed chord')),
            ),
            NAME,
            subtitle=_('Or see a progression written and hear which chord is different'),
        ),
        *harmony_settings(),
    )

    @property
    def title(self) -> str:
        return _('Progressions — Ear')

    @property
    def description(self) -> str:
        return _('Recognise common chord progressions by ear.')

    @property
    def play_label(self) -> str:
        return _('Play progression')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        task = _('spot the change') if settings.get('task', NAME) == CHANGE else _('name it')
        return _(' · ').join((describe_keys(settings), task))

    def item_label(self, item_id: ItemId) -> str:
        # Translators: an item in "Weakest items", e.g. "I–vi–IV–V (ear)".
        return _('{progression} (ear)').format(progression=label(parse_item(item_id)))

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        return [item_id(p) for p in _selected(settings)]

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        return [ItemId(f'progression.ear.{p}') for p in _CONFUSABLE[parse_item(item_id)]]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        progression = parse_item(item_id)
        mode = mode_of(progression)
        key = pick_key(mode, settings, rng)
        instrument = pick_instrument(settings, rng)
        tempo = tempo_of(settings)
        context = _('Key: {key}').format(key=key_name(key))
        if settings.get('task', NAME) == CHANGE and changes(progression):
            index, substitute = rng.choice(changes(progression))
            heard = _with_change(progression, index, substitute)
            chords = progression.split('-')
            answer = ChoiceAnswer(
                tuple(
                    # Translators: the second line of an option, e.g. "Chord 2".
                    Option(
                        str(i + 1),
                        numeral_label(RomanNumeral.parse(c)),
                        str(i + 1),
                        _('Chord {number}').format(number=i + 1),
                    )
                    for i, c in enumerate(chords)
                )
            )
            expected = str(index + 1)
            prompt = _('Which chord is different from the written progression?')
            # Translators: e.g. "Key: C major · Written: I–IV–V–I".
            context = _('{key} · Written: {progression}').format(
                key=context, progression=label(progression)
            )
        else:
            heard = progression
            same_mode = [p for p in _selected(settings) if mode_of(p) is mode]
            pool = set(same_mode) | {progression}
            for other in (p for p in PROGRESSIONS if mode_of(p) is mode):
                if len(pool) >= _MIN_OPTIONS:
                    break
                pool.add(other)
            answer = ChoiceAnswer(
                tuple(
                    Option(p, label(p), str(i + 1))
                    for i, p in enumerate(p for p in PROGRESSIONS if p in pool)
                )
            )
            expected = progression
            prompt = _('Which progression do you hear?')
        voicings = _realize(key, parse_numerals(heard), rng)
        figure = system_figure(key, voicings, durations=_durations(len(voicings)))
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=prompt,
            answer=answer,
            expected=expected,
            figure=figure,
            playback=progression_playback(
                voicings, _lengths(len(voicings)), tempo=tempo, instrument=instrument
            ),
            playback_is_question=True,
            playback_style_choice=False,
            written_alternative=figure,
            context=context,
            hint=_('Follow the bass: does it step, or leap by a fourth or fifth?'),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        progression = parse_item(question.item_id)
        voicings = voicings_of(question.written_alternative)
        key = key_of(question.written_alternative)
        assert key is not None
        expected = str(question.expected)
        change = expected.isdigit()
        heard = self._heard(progression, key, voicings) if change else progression
        numerals = parse_numerals(heard)
        correct = str(given) == expected
        answer_text = self.answer_label(question, expected)
        if correct:
            # Translators: e.g. "Correct — I–vi–IV–V".
            title = _('Correct — {answer}').format(answer=answer_text)
        else:
            # Translators: e.g. "Not quite — the answer is I–vi–IV–V".
            title = _('Not quite — the answer is {answer}').format(answer=answer_text)
        sentences = [
            # Translators: e.g. "You heard I–vi–IV–V in G major: the bass moves G–E–C–D."
            _('You heard {progression} in {key}: the bass moves {bass}.').format(
                progression=progression_label(numerals),
                key=key_name(key),
                bass=_('–').join(pitch_name(v[3].name) for v in voicings),
            )
        ]
        playback = question.playback
        assert playback is not None
        play_given: PlaybackSpec | None = None
        inks = None
        if change:
            index = int(expected) - 1
            written = parse_numerals(progression)
            sentences.append(
                # Translators: e.g. "Chord 2 was ii instead of the written IV."
                _('Chord {number} was {heard} instead of the written {written}.').format(
                    number=index + 1,
                    heard=numeral_label(numerals[index]),
                    written=numeral_label(written[index]),
                )
            )
            inks = [Ink.ACCENT if i == index else Ink.FOREGROUND for i in range(len(voicings))]
            if not correct:
                play_given = _playback_like(playback, _voiced_like(key, written, voicings))
        elif not correct and str(given) in PROGRESSIONS:
            other = parse_numerals(str(given))
            other_key = Key(key.tonic, mode_of(str(given)))
            play_given = _playback_like(playback, _voiced_like(other_key, other, voicings))
            sentences.append(self._difference(numerals, other))
        figure = system_figure(
            key,
            voicings,
            durations=_durations(len(voicings)),
            labels=[numeral_label(n) for n in numerals],
            inks=inks,
        )
        return Feedback(
            correct=correct,
            title=title,
            detail=' '.join(sentences),
            expected_label=answer_text,
            figure=figure,
            play_expected=playback,
            play_given=play_given,
        )

    def answer_label(self, question: Question, value: object) -> str:
        text = str(value)
        if text in PROGRESSIONS:
            return label(text)
        if text.isdigit():
            chords = parse_item(question.item_id).split('-')
            index = int(text) - 1
            if 0 <= index < len(chords):
                # Translators: an answer in "spot the change", e.g. "chord 2 (IV)".
                return _('chord {number} ({numeral})').format(
                    number=index + 1, numeral=numeral_label(RomanNumeral.parse(chords[index]))
                )
        return super().answer_label(question, value)

    @staticmethod
    def _heard(progression: str, key: Key, voicings: Sequence[Voicing]) -> str:
        """Which changed progression a "spot the change" question played."""
        target = tuple(voicings)
        soprano = voicings[0][0].name
        for index, substitute in changes(progression):
            heard = _with_change(progression, index, substitute)
            numerals = parse_numerals(heard)
            try:
                if voiced(key, numerals, soprano) == target:
                    return heard
            except NoVoicingError:
                pass
            if voice_progression(key, numerals) == target:
                return heard
        raise ValueError(f'no change of {progression} was played')

    @staticmethod
    def _difference(heard: Sequence[RomanNumeral], chosen: Sequence[RomanNumeral]) -> str:
        """Where the learner's progression differs from the one played."""
        if len(heard) != len(chosen):
            # Translators: e.g. "Count the chords: you heard 4, your answer has 3."
            return ngettext(
                'Count the chords: you heard {count}, your answer has {chosen}.',
                'Count the chords: you heard {count}, your answer has {chosen}.',
                len(heard),
            ).format(count=len(heard), chosen=len(chosen))
        differing = [
            _('chord {number} is {heard}, not {chosen}').format(
                number=i + 1, heard=numeral_label(a), chosen=numeral_label(b)
            )
            for i, (a, b) in enumerate(zip(heard, chosen, strict=True))
            if a != b
        ]
        # Translators: e.g. "Compared with your answer: chord 2 is vi, not ii."
        return _('Compared with your answer: {differences}.').format(
            differences=_('; ').join(differing)
        )


EXERCISES: tuple[ExerciseDefinition, ...] = (ProgressionEar(),)
