# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Interval construction: write an interval above or below a given note.

The staff shows one note and the prompt names an interval ("Write a major
sixth above G4"); the learner writes the other note with the staff input.
Items are spelled intervals per direction, ``interval.write.above.M6`` or
``interval.write.below.m3``; clef, register and the given note vary per
question (:func:`.intervals.place_interval` picks them, with sharps and
flats as the settings allow).

The answer must be right in spelling *and* sound. An enharmonic note (F♭5
for E5 above G4) sounds right but is the wrong interval on paper, so it is
wrong, and the explanation says so: "Right sound, wrong spelling: a major
sixth spans six letter names". Other wrong answers are named as the
interval they make, with the letter names and semitones that tell them
apart.

The tritone has no single spelling, so it is not asked; with "Augmented
and diminished" the augmented fourth and diminished fifth (and the other
altered intervals) join the pool.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from fractions import Fraction
from gettext import gettext as _
from typing import ClassVar, cast

from ...audio.spec import PlaybackSpec
from ...core import Interval, Letter, Pitch, PitchName
from ...core.naming import pitch_name
from ...learning.model import ItemId
from ...notation.spec import Chord, Clef, Head, StaffSpec
from ..base import (
    BoolSetting,
    ChoiceSetting,
    ExerciseDefinition,
    Family,
    Feedback,
    Modality,
    MultiChoiceSetting,
    Option,
    Question,
    Setting,
    StaffInputAnswer,
)
from .intervals import (
    ALTERED,
    CONFUSABLE,
    SIMPLE,
    TEACHING_ORDER,
    TRITONE,
    interval_label,
    interval_phrase,
    letter_count,
    note_label,
    number_word,
    place_interval,
    semitone_count,
    takes_an,
)
from .note_placement import staff_value_label, staff_value_text, written_note

_CLEFS = {
    'treble': Clef.TREBLE,
    'bass': Clef.BASS,
    'alto': Clef.ALTO,
    'tenor': Clef.TENOR,
}
WRITABLE = tuple(key for key in SIMPLE if key != TRITONE)
"""The simple intervals that have one spelling (the pool setting)."""
_ORDER = tuple(key for key in TEACHING_ORDER if key != TRITONE)
_DIRECTIONS = ('above', 'below')


def item_id(direction: str, key: str) -> ItemId:
    """``interval.write.above.M6`` or ``interval.write.below.m3``."""
    return ItemId(f'interval.write.{direction}.{key}')


def parse_item(item: str) -> tuple[str, str]:
    """``(direction, interval key)``; raises :class:`ValueError` for other ids."""
    parts = item.split('.')
    if (
        len(parts) != 4
        or parts[:2] != ['interval', 'write']
        or parts[2] not in _DIRECTIONS
        or parts[3] not in (*WRITABLE, *ALTERED)
    ):
        raise ValueError(f'not an interval-construction item: {item!r}')
    return parts[2], parts[3]


def _choice(settings: Mapping[str, object], key: str, allowed: Sequence[str], default: str) -> str:
    value = str(settings.get(key, default))
    return value if value in allowed else default


def _clefs(settings: Mapping[str, object]) -> list[Clef]:
    chosen = [_CLEFS[c] for c in cast(Sequence[str], settings.get('clefs', ())) if c in _CLEFS]
    return chosen or [Clef.TREBLE]


def _pool(settings: Mapping[str, object]) -> list[str]:
    chosen = settings.get('intervals', WRITABLE)
    keys = set(cast(Sequence[str], chosen)) if isinstance(chosen, list | tuple) else set(WRITABLE)
    pool = [key for key in _ORDER if key in keys] or list(_ORDER)
    if settings.get('altered'):
        pool += list(ALTERED)
    return pool


def _directions(settings: Mapping[str, object]) -> tuple[str, ...]:
    choice = _choice(settings, 'direction', ('above', 'below', 'both'), 'above')
    return _DIRECTIONS if choice == 'both' else (choice,)


def _prompt(key: str, direction: str, note: str) -> str:
    phrase = interval_phrase(key)
    if direction == 'above':
        if takes_an(key):
            # Translators: e.g. "Write an augmented fourth above F4". Used where English
            # needs "an"; translate it like the "a" form if your language has no such rule.
            template = _('Write an {interval} above {note}')
        else:
            # Translators: e.g. "Write a major sixth above G4".
            template = _('Write a {interval} above {note}')
    elif takes_an(key):
        # Translators: e.g. "Write an augmented fourth below B4"; see the "above" form.
        template = _('Write an {interval} below {note}')
    else:
        # Translators: e.g. "Write a minor third below E5".
        template = _('Write a {interval} below {note}')
    return template.format(interval=phrase, note=note)


def _letter_names(start: Pitch, number: int, *, up: bool) -> str:
    """The letter names counted from ``start``, e.g. "G A B C D E"."""
    step = 1 if up else -1
    letters = [Letter((start.letter + step * i) % 7) for i in range(number)]
    # Translators: separator between counted letter names, "G A B C D E".
    return _(' ').join(pitch_name(PitchName(letter)) for letter in letters)


class IntervalConstruction(ExerciseDefinition):
    id = 'interval-construction'
    item_prefix = 'interval.write.'
    family = Family.NOTATION
    modality = Modality.EYE
    level = 1
    icon_name = 'interval-construction-symbolic'
    glyph = '⇕'
    settings: ClassVar[tuple[Setting, ...]] = (
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
        MultiChoiceSetting(
            'intervals',
            _('Intervals'),
            tuple(Option(key, interval_label(key)) for key in WRITABLE),
            WRITABLE,
        ),
        ChoiceSetting(
            'direction',
            _('Direction'),
            (
                Option('above', _('Above the note')),
                Option('below', _('Below the note')),
                Option('both', _('Above and below')),
            ),
            'above',
        ),
        ChoiceSetting(
            'accidentals',
            _('Accidentals'),
            (
                Option('none', _('As few as possible')),
                Option('single', _('Sharps and flats')),
            ),
            'single',
            subtitle=_('On the given note and the answer'),
        ),
        BoolSetting(
            'altered',
            _('Augmented and diminished'),
            False,
            subtitle=_('Augmented fourths, diminished fifths and more'),
        ),
    )

    @property
    def title(self) -> str:
        return _('Interval Construction')

    @property
    def description(self) -> str:
        return _('Write an interval above or below a given note.')

    @property
    def play_label(self) -> str:
        return _('Play interval')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        clefs = _clefs(settings)
        names = {
            Clef.TREBLE: _('Treble clef'),
            Clef.BASS: _('Bass clef'),
            Clef.ALTO: _('Alto clef'),
            Clef.TENOR: _('Tenor clef'),
        }
        parts = [names[clefs[0]] if len(clefs) == 1 else _('Mixed clefs')]
        directions = _directions(settings)
        if directions == ('above',):
            parts.append(_('above'))
        elif directions == ('below',):
            parts.append(_('below'))
        else:
            parts.append(_('above and below'))
        if settings.get('altered'):
            parts.append(_('augmented and diminished'))
        # Translators: separator between the parts of an exercise subtitle.
        return _(' · ').join(parts)

    def item_label(self, item_id: ItemId) -> str:
        direction, key = parse_item(item_id)
        if direction == 'above':
            # Translators: an item in "Weakest items", e.g. "Major sixth above (write)".
            return _('{interval} above (write)').format(interval=interval_label(key))
        # Translators: an item in "Weakest items", e.g. "Minor third below (write)".
        return _('{interval} below (write)').format(interval=interval_label(key))

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        """Per direction (above first), stable intervals first, as in Intervals — Staff."""
        pool = _pool(settings)
        return [item_id(d, key) for d in _directions(settings) for key in pool]

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        """The other quality of the same number (m6 for M6), in the same direction."""
        direction, key = parse_item(item_id)
        return [
            ItemId(f'interval.write.{direction}.{partner}')
            for partner in CONFUSABLE.get(key, ())
            if partner != TRITONE
        ]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        direction, key = parse_item(item_id)
        clef = rng.choice(_clefs(settings))
        none = _choice(settings, 'accidentals', ('none', 'single'), 'single') == 'none'
        max_alter = 0 if none else 1
        low, high = place_interval(Interval.parse(key), clef, max_alter, rng)
        given, expected = (low, high) if direction == 'above' else (high, low)
        staff = StaffSpec(clef=clef, events=(Chord((Head(given),)),))
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_prompt(key, direction, note_label(given)),
            answer=StaffInputAnswer(clef=clef, slots=1, given=staff),
            expected=((expected,),),
            hint=_(
                'Count the letter names first, both notes included, for the number; then '
                'count semitones for the quality.'
            ),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        direction, key = parse_item(question.item_id)
        start = self._given_note(question)
        expected = written_note(question.expected)
        assert expected is not None
        written = written_note(given)
        correct = written == expected
        phrase = interval_phrase(key)
        label = note_label(expected)
        if correct:
            # Translators: e.g. "Correct — E5".
            title = _('Correct — {answer}').format(answer=label)
        else:
            # Translators: e.g. "Not quite — the answer is E5".
            title = _('Not quite — the answer is {answer}').format(answer=label)
        sentences: list[str] = []
        if written is not None and not correct:
            sentences.append(self._comparison(key, direction, start, expected, written))
        up = direction == 'above'
        interval = Interval.parse(key)
        sentences.append(
            # Translators: e.g. "Counting letter names up from G4: G A B C D E."
            (
                _('Counting letter names up from {note}: {letters}.')
                if up
                else _('Counting letter names down from {note}: {letters}.')
            ).format(note=note_label(start), letters=_letter_names(start, interval.number, up=up))
        )
        low, high = (start, expected) if up else (expected, start)
        sentences.append(
            # Translators: e.g. "G4 to E5 spans six letter names and nine semitones: a major
            # sixth."
            _('{low} to {high} spans {letters} and {semitones}: a {interval}.').format(
                low=note_label(low),
                high=note_label(high),
                letters=letter_count(interval.number),
                semitones=semitone_count(interval.semitones),
                interval=phrase,
            )
            if not takes_an(key)
            else _('{low} to {high} spans {letters} and {semitones}: an {interval}.').format(
                low=note_label(low),
                high=note_label(high),
                letters=letter_count(interval.number),
                semitones=semitone_count(interval.semitones),
                interval=phrase,
            )
        )
        return Feedback(
            correct=correct,
            title=title,
            detail=' '.join(sentences),
            expected_label=label,
            play_expected=PlaybackSpec.melodic([start, expected], note_length=Fraction(1)),
            play_given=(
                PlaybackSpec.melodic([start, written], note_length=Fraction(1))
                if written is not None and not correct
                else None
            ),
        )

    def answer_label(self, question: Question, value: object) -> str:
        return staff_value_label(value)

    def serialize(self, value: object) -> str:
        return staff_value_text(value)

    @staticmethod
    def _given_note(question: Question) -> Pitch:
        answer = question.answer
        assert isinstance(answer, StaffInputAnswer)
        assert isinstance(answer.given, StaffSpec)
        chord = answer.given.events[0]
        assert isinstance(chord, Chord)
        return chord.heads[0].pitch

    @staticmethod
    def _comparison(key: str, direction: str, start: Pitch, expected: Pitch, written: Pitch) -> str:
        """What the learner wrote instead, in terms of letter names and semitones."""
        interval = Interval.parse(key)
        if written.midi == expected.midi:
            # Translators: e.g. "Right sound, wrong spelling: a major sixth spans six letter
            # names, so the answer is written E5, not F♭5."
            template = (
                _(
                    'Right sound, wrong spelling: an {interval} spans {letters}, so the answer '
                    'is written {expected}, not {given}.'
                )
                if takes_an(key)
                else _(
                    'Right sound, wrong spelling: a {interval} spans {letters}, so the answer '
                    'is written {expected}, not {given}.'
                )
            )
            return template.format(
                interval=interval_phrase(key),
                letters=letter_count(interval.number),
                expected=note_label(expected),
                given=note_label(written),
            )
        up = direction == 'above'
        on_side = (
            written.diatonic_index > start.diatonic_index
            if up
            else written.diatonic_index < start.diatonic_index
        )
        if not on_side:
            text = _('{given} is not above {note}.') if up else _('{given} is not below {note}.')
            return text.format(given=note_label(written), note=note_label(start))
        low, high = (start, written) if up else (written, start)
        try:
            made = Interval.between(low, high)
            name = interval_phrase(str(made))
        except ValueError:
            # Translators: e.g. "G4 to F5 spans seven letter names." (an unusual interval)
            return _('{low} to {high} spans {letters}.').format(
                low=note_label(low),
                high=note_label(high),
                letters=letter_count(high.diatonic_index - low.diatonic_index + 1),
            )
        if made.number == interval.number:
            if takes_an(str(made)):
                # Translators: e.g. "E♯5 makes an augmented sixth: the right letter names, but
                # ten semitones instead of nine." {needed} is a number word. Used where English
                # needs "an".
                template = _(
                    '{given} makes an {made}: the right letter names, but {semitones} '
                    'instead of {needed}.'
                )
            else:
                # Translators: e.g. "E♭5 makes a minor sixth: the right letter names, but
                # eight semitones instead of nine." {needed} is a number word.
                template = _(
                    '{given} makes a {made}: the right letter names, but {semitones} '
                    'instead of {needed}.'
                )
            return template.format(
                given=note_label(written),
                made=name,
                semitones=semitone_count(made.semitones),
                needed=number_word(interval.semitones),
            )
        if takes_an(str(made)):
            # Translators: e.g. "C♯6 makes an augmented seventh, which spans seven letter
            # names." Used where English needs "an".
            template = _('{given} makes an {made}, which spans {letters}.')
        else:
            # Translators: e.g. "F5 makes a minor seventh, which spans seven letter names."
            template = _('{given} makes a {made}, which spans {letters}.')
        return template.format(
            given=note_label(written), made=name, letters=letter_count(made.number)
        )


EXERCISES: tuple[ExerciseDefinition, ...] = (IntervalConstruction(),)
