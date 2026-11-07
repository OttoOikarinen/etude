# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Clef reading: write a melody from one clef in another at the same pitch.

The alto and tenor clefs are the C clefs of score reading: the viola reads the
alto clef, and the cello, bassoon and tenor trombone read the tenor clef in
their upper register (Adler, *The Study of Orchestration*). The C clef marks
middle C (C4): the middle line in the alto clef, the fourth line in the tenor
clef. The question shows a short melody in a key, with its key signature, and
the learner writes it on the staff input in the other clef at the same pitch,
under the same key signature. Grading is by pitch and spelling, note by note,
and an octave mistake is named as such.

Items are ``clef.rewrite.<from>-<to>``: the viola's alto clef to treble and
back, the tenor clef to bass and back, and the outer pairs alto to bass (the
viola's low register) and tenor to treble (the cello's high register).
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from fractions import Fraction
from gettext import gettext as _
from gettext import ngettext
from typing import ClassVar, cast

from ...audio.spec import PlaybackSpec
from ...core import Pitch
from ...core.naming import key_name, pitch_name
from ...core.scale import Key, Mode
from ...learning.model import ItemId
from ...notation.spec import Clef, StaffSpec
from ..base import (
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
from .harmony import MAX_ACCIDENTALS, keys_within, limit_setting
from .note_placement import staff_value_label, written_notes
from .transposition import fits_staff, melody, melody_steps, plain

PREFIX = 'clef.rewrite.'
PAIRS = ('alto-treble', 'treble-alto', 'tenor-bass', 'bass-tenor', 'alto-bass', 'tenor-treble')
"""In teaching order: the viola's clef first, then the tenor clef, then the outer pairs."""

_CLEFS = {'treble': Clef.TREBLE, 'bass': Clef.BASS, 'alto': Clef.ALTO, 'tenor': Clef.TENOR}
_CONFUSABLE = {
    'alto-treble': ('treble-alto', 'alto-bass'),
    'treble-alto': ('alto-treble',),
    'tenor-bass': ('bass-tenor', 'tenor-treble'),
    'bass-tenor': ('tenor-bass',),
    'alto-bass': ('alto-treble', 'tenor-bass'),
    'tenor-treble': ('tenor-bass', 'alto-treble'),
}
_ATTEMPTS = 300
_MAX_EXPLAINED = 3


def clef_name(clef: Clef) -> str:
    names: dict[Clef, Callable[[], str]] = {
        Clef.TREBLE: lambda: _('treble clef'),
        Clef.BASS: lambda: _('bass clef'),
        Clef.ALTO: lambda: _('alto clef'),
        Clef.TENOR: lambda: _('tenor clef'),
    }
    return names[clef]()


def pair_label(pair: str) -> str:
    """``'Alto clef → treble clef'``."""
    source, target = pair_clefs(pair)
    # Translators: a pair of clefs in the settings, e.g. "Alto clef → treble clef".
    text = _('{source} → {target}').format(source=clef_name(source), target=clef_name(target))
    return text[:1].upper() + text[1:]


def pair_clefs(pair: str) -> tuple[Clef, Clef]:
    source, _sep, target = pair.partition('-')
    return _CLEFS[source], _CLEFS[target]


def item_id(pair: str) -> ItemId:
    return ItemId(PREFIX + pair)


def parse_item(item: str) -> str:
    pair = item.removeprefix(PREFIX)
    if not item.startswith(PREFIX) or pair not in PAIRS:
        raise ValueError(f'not a clef reading item: {item!r}')
    return pair


def _selected(settings: Mapping[str, object]) -> list[str]:
    value = settings.get('pairs', PAIRS)
    chosen = (
        {str(v) for v in cast(Sequence[object], value)} if not isinstance(value, str) else {value}
    )
    return [p for p in PAIRS if p in chosen] or list(PAIRS)


def _length(settings: Mapping[str, object]) -> int:
    value = settings.get('notes', 5)
    return max(3, min(6, value if isinstance(value, int) else 5))


def middle_c_sentence(clef: Clef) -> str:
    """Where middle C is written in ``clef``."""
    sentences: dict[Clef, Callable[[], str]] = {
        Clef.TREBLE: lambda: _('In the treble clef middle C (C4) is one ledger line below.'),
        Clef.BASS: lambda: _('In the bass clef middle C (C4) is one ledger line above.'),
        Clef.ALTO: lambda: _('In the alto clef middle C (C4) is the middle line.'),
        Clef.TENOR: lambda: _('In the tenor clef middle C (C4) is the fourth line.'),
    }
    return sentences[clef]()


def _note(pitch: Pitch) -> str:
    return pitch_name(pitch.name) + str(pitch.octave)


class ClefReading(ExerciseDefinition):
    id = 'clef-reading'
    item_prefix = PREFIX
    family = Family.NOTATION
    modality = Modality.EYE
    level = 3
    icon_name = 'clef-reading-symbolic'
    glyph = '𝄡'
    settings: ClassVar[tuple[Setting, ...]] = (
        MultiChoiceSetting(
            'pairs',
            _('Clefs'),
            tuple(Option(p, pair_label(p)) for p in PAIRS),
            PAIRS,
        ),
        IntSetting('notes', _('Notes'), 5, 3, 6, subtitle=_('Length of the melody')),
        IntSetting(
            'max-accidentals',
            _('Most accidentals'),
            3,
            0,
            MAX_ACCIDENTALS,
            subtitle=_('Largest number of sharps or flats in the key signature'),
        ),
    )

    @property
    def title(self) -> str:
        return _('Clef Reading')

    @property
    def description(self) -> str:
        return _('Read the alto and tenor clefs: write a melody in another clef at the same pitch.')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        pairs = _selected(settings)
        if len(pairs) == len(PAIRS):
            parts = [_('Alto and tenor clefs')]
        else:
            # Translators: separator in a list of clef pairs in an exercise subtitle.
            parts = [_(', ').join(pair_label(p) for p in pairs)]
        length = _length(settings)
        parts.append(ngettext('{n} note', '{n} notes', length).format(n=length))
        # Translators: separator between the parts of an exercise subtitle.
        return _(' · ').join(parts)

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        return [item_id(p) for p in _selected(settings)]

    def item_label(self, item_id: ItemId) -> str:
        return pair_label(parse_item(item_id))

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        return [ItemId(PREFIX + p) for p in _CONFUSABLE[parse_item(item_id)]]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        pair = parse_item(item_id)
        source, target = pair_clefs(pair)
        key, pitches = _melody(source, target, settings, rng)
        figure = StaffSpec.notes(*pitches, clef=source, key_signature=key.signature)
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            # Translators: e.g. "Write the melody in the treble clef at the same pitch".
            prompt=_('Write the melody in the {clef} at the same pitch').format(
                clef=clef_name(target)
            ),
            answer=StaffInputAnswer(clef=target, key_signature=key.signature, slots=len(pitches)),
            expected=tuple((p,) for p in pitches),
            figure=figure,
            playback=PlaybackSpec.melodic(pitches, note_length=Fraction(1), tempo=100.0),
            # Translators: context of a clef reading question, e.g. "Key: G major".
            context=_('Key: {key}').format(key=key_name(key)),
            hint=middle_c_sentence(source if source in (Clef.ALTO, Clef.TENOR) else target),
            details={'key': str(key)},
        )

    def grade(self, question: Question, given: object) -> Feedback:
        pair = parse_item(question.item_id)
        source, target = pair_clefs(pair)
        expected = tuple(c[0] for c in cast(tuple[tuple[Pitch, ...], ...], question.expected))
        chords = written_notes(given)
        written = (
            tuple(c[0] for c in chords)
            if chords is not None and all(len(c) == 1 for c in chords)
            else None
        )
        correct = written == expected
        right = sum(w == e for w, e in zip(written, expected, strict=False)) if written else 0
        label = staff_value_label(question.expected)
        if correct:
            # Translators: e.g. "Correct — A4, B4, C♯5".
            title = _('Correct — {answer}').format(answer=label)
        else:
            # Translators: e.g. "Not quite — the answer is A4, B4, C♯5".
            title = _('Not quite — the answer is {answer}').format(answer=label)
        sentences = [
            middle_c_sentence(source),
            middle_c_sentence(target),
            # Translators: e.g. "The pitches stay the same: the first note is D4 in both clefs."
            _('The pitches stay the same: the first note is {note} in both clefs.').format(
                note=_note(expected[0])
            ),
        ]
        if written is not None and not correct:
            sentences += _mistakes(written, expected)
        return Feedback(
            correct=correct,
            title=title,
            detail=' '.join(sentences),
            expected_label=label,
            score=right / len(expected),
            play_expected=question.playback,
            play_given=(
                PlaybackSpec.melodic(written, note_length=Fraction(1), tempo=100.0)
                if written and not correct
                else None
            ),
        )

    def answer_label(self, question: Question, value: object) -> str:
        return staff_value_label(value)


def _melody(
    source: Clef, target: Clef, settings: Mapping[str, object], rng: random.Random
) -> tuple[Key, list[Pitch]]:
    """A key and a melody that fits both staves within one ledger line, or two when the
    clefs share little range (the tenor and bass clefs share about an octave)."""
    keys = keys_within(limit_setting(settings, 3), (Mode.MAJOR, Mode.MINOR))
    length = _length(settings)
    for attempt in range(_ATTEMPTS):
        key = rng.choice(keys)
        steps = melody_steps(length, rng)
        slack = 0 if attempt < 100 else 1 if attempt < 200 else 2
        options = [
            pitches
            for octave in range(1, 7)
            if plain(pitches := melody(key, steps, octave))
            and fits_staff(source, pitches, slack)
            and fits_staff(target, pitches, slack)
        ]
        if options:
            return key, rng.choice(options)
    raise AssertionError(f'no melody fits {source} and {target}')  # pragma: no cover


def _mistakes(written: Sequence[Pitch], expected: Sequence[Pitch]) -> list[str]:
    sentences = []
    wrong = [(i, w, e) for i, (w, e) in enumerate(zip(written, expected, strict=False)) if w != e]
    for index, w, e in wrong[:_MAX_EXPLAINED]:
        if w.name == e.name and w.midi == e.midi - 12:
            # Translators: e.g. "Note 2: G3 is an octave too low."
            text = _('Note {n}: {given} is an octave too low.')
        elif w.name == e.name and w.midi == e.midi + 12:
            text = _('Note {n}: {given} is an octave too high.')
        elif w.midi == e.midi:
            # Translators: e.g. "Note 3: G♭4 sounds right, but the note is spelled F♯4."
            text = _('Note {n}: {given} sounds right, but the note is spelled {expected}.')
        else:
            # Translators: e.g. "Note 4: B4 should be C♯5."
            text = _('Note {n}: {given} should be {expected}.')
        sentences.append(text.format(n=index + 1, given=_note(w), expected=_note(e)))
    if len(wrong) > _MAX_EXPLAINED:
        more = len(wrong) - _MAX_EXPLAINED
        sentences.append(
            ngettext('{n} more note is wrong.', '{n} more notes are wrong.', more).format(n=more)
        )
    return sentences


EXERCISES: tuple[ExerciseDefinition, ...] = (ClefReading(),)
