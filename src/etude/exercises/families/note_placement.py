# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Note placement: write a named note on the staff.

The reverse of :mod:`note naming <.note_naming>`: the prompt names a note
("Write F4 on the staff") and the learner writes it with the staff input.
Items are a clef and a written pitch, ``place.treble.F4`` or
``place.bass.Bb2``, in the same teaching order as note naming (the clef's
landmark outwards, then ledger lines, then sharps and flats), because
finding a position on a staff is learned one position at a time too.

Grading is by exact spelling and octave: G♭4 is not F♯4 on a staff. The
explanation says where the note sits and, for a wrong answer, how far the
learner's note is from it ("G4 is one step too high"), or that only the
accidental or the octave is wrong.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from fractions import Fraction
from gettext import gettext as _
from gettext import ngettext

from ...audio.spec import PlaybackSpec
from ...core import Pitch, PitchName
from ...core.naming import pitch_name
from ...learning.model import ItemId
from ...notation.spec import Clef
from ..base import (
    BoolSetting,
    ExerciseDefinition,
    Family,
    Feedback,
    IntSetting,
    Modality,
    MultiChoiceSetting,
    Option,
    Question,
    StaffInputAnswer,
)
from .intervals import number_word
from .note_naming import (
    MAX_LEDGER_LINES,
    WHITE_KEY_ACCIDENTALS,
    NoteNaming,
    counting_from_staff,
    full_name,
    landmark_sentence,
    ledger_lines,
    reading_hint,
    staff_mnemonic,
    where_on_staff,
)

_CLEFS = {
    'treble': Clef.TREBLE,
    'bass': Clef.BASS,
    'alto': Clef.ALTO,
    'tenor': Clef.TENOR,
}
_TOP_LINE = 8


# Staff answers, shared with interval construction -------------------------------------


def written_notes(value: object) -> tuple[tuple[Pitch, ...], ...] | None:
    """A staff-input answer value, or ``None`` if ``value`` is not one."""
    if not isinstance(value, tuple):
        return None
    chords: list[tuple[Pitch, ...]] = []
    for chord in value:
        if not isinstance(chord, tuple) or not all(isinstance(p, Pitch) for p in chord):
            return None
        chords.append(chord)
    return tuple(chords)


def written_note(value: object) -> Pitch | None:
    """The one note of a single-slot staff answer, or ``None``."""
    chords = written_notes(value)
    if chords is None or len(chords) != 1 or len(chords[0]) != 1:
        return None
    return chords[0][0]


def staff_value_text(value: object) -> str:
    """``'E5'``, or ``'C4 E4 | G4'`` for several slots and chords (attempt log)."""
    chords = written_notes(value)
    if chords is None:
        return str(value)
    return ' | '.join(' '.join(str(p) for p in chord) for chord in chords)


def staff_value_label(value: object) -> str:
    """The notes of a staff answer in the learner's naming convention, e.g. "F♯4"."""
    chords = written_notes(value)
    if chords is None:
        return str(value)
    # Translators: separator between written notes, e.g. "C4, E4".
    return _(', ').join(full_name(p) for chord in chords for p in chord)


# Items -------------------------------------------------------------------------------


def item_id(clef: Clef, pitch: Pitch) -> ItemId:
    """``place.treble.F4``, ``place.bass.Bb2``."""
    return ItemId(f'place.{clef.value}.{pitch}')


def parse_item(item: str) -> tuple[Clef, Pitch]:
    """Inverse of :func:`item_id`; raises :class:`ValueError` for other ids."""
    parts = item.split('.')
    if len(parts) != 3 or parts[0] != 'place' or parts[1] not in _CLEFS:
        raise ValueError(f'not a note-placement item: {item!r}')
    clef = _CLEFS[parts[1]]
    try:
        pitch = Pitch.parse(parts[2])
    except ValueError:
        raise ValueError(f'not a note-placement item: {item!r}') from None
    if (
        str(pitch) != parts[2]
        or abs(pitch.alter) > 1
        or pitch.name in WHITE_KEY_ACCIDENTALS
        or ledger_lines(clef.staff_position(pitch)) > MAX_LEDGER_LINES
    ):
        raise ValueError(f'not a note-placement item: {item!r}')
    return clef, pitch


def _steps(count: int, *, higher: bool) -> str:
    if higher:
        # Translators: e.g. "You wrote G4, one step too high." {count} is a number word.
        return ngettext(
            'You wrote {given}, {count} step too high.',
            'You wrote {given}, {count} steps too high.',
            count,
        )
    return ngettext(
        'You wrote {given}, {count} step too low.',
        'You wrote {given}, {count} steps too low.',
        count,
    )


def compare_written(pitch: Pitch, written: Pitch) -> str:
    """How a wrong note differs from ``pitch``: accidental, spelling, octave or position."""
    note, given = full_name(pitch), full_name(written)
    if written.diatonic_index == pitch.diatonic_index:
        if pitch.alter > 0:
            text = _('{given} is on the right line or space, but {note} needs a sharp.')
        elif pitch.alter < 0:
            text = _('{given} is on the right line or space, but {note} needs a flat.')
        else:
            text = _('{given} is on the right line or space, but {note} has no sharp or flat.')
        return text.format(given=given, note=note)
    if written.midi == pitch.midi:
        return _(
            '{given} is the same key on the piano, but {note} is written with the letter {letter}.'
        ).format(given=given, note=note, letter=pitch_name(PitchName(pitch.letter)))
    if written.letter == pitch.letter:
        return _('{given} has the right letter in the wrong octave.').format(given=given)
    difference = written.diatonic_index - pitch.diatonic_index
    return _steps(abs(difference), higher=difference > 0).format(
        given=given, count=number_word(abs(difference))
    )


# The exercise ------------------------------------------------------------------------


class NotePlacement(ExerciseDefinition):
    id = 'note-placement'
    item_prefix = 'place.'
    family = Family.NOTATION
    modality = Modality.EYE
    level = 1
    icon_name = 'note-placement-symbolic'
    glyph = '✎'
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
            'ledger-lines',
            _('Ledger lines'),
            1,
            0,
            MAX_LEDGER_LINES,
            subtitle=_('Most ledger lines above or below the staff'),
        ),
        BoolSetting(
            'accidentals',
            _('Sharps and flats'),
            False,
            subtitle=_('Also write notes with an accidental'),
        ),
    )

    @property
    def title(self) -> str:
        return _('Note Placement')

    @property
    def description(self) -> str:
        return _('Write named notes on the staff.')

    @property
    def play_label(self) -> str:
        return _('Play note')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        return NoteNaming().describe_settings(settings)

    def item_label(self, item_id: ItemId) -> str:
        clef, pitch = parse_item(item_id)
        templates = {
            # Translators: an item in "Weakest items", e.g. "Write F4 — treble clef".
            Clef.TREBLE: _('Write {note} — treble clef'),
            Clef.BASS: _('Write {note} — bass clef'),
            Clef.ALTO: _('Write {note} — alto clef'),
            Clef.TENOR: _('Write {note} — tenor clef'),
        }
        return templates[clef].format(note=full_name(pitch))

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        """The note-naming order: landmarks outwards, ledger lines, then accidentals."""
        reading = NoteNaming().items({**settings, 'octave': False})
        return [ItemId('place.' + item.removeprefix('note.')) for item in reading]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        clef, pitch = parse_item(item_id)
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            # Translators: e.g. "Write F♯4 on the staff".
            prompt=_('Write {note} on the staff').format(note=full_name(pitch)),
            answer=StaffInputAnswer(clef=clef, slots=1),
            expected=((pitch,),),
            hint=reading_hint(clef, pitch),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        clef, pitch = parse_item(question.item_id)
        written = written_note(given)
        correct = written == pitch
        label = full_name(pitch)
        if correct:
            # Translators: e.g. "Correct — F4".
            title = _('Correct — {answer}').format(answer=label)
        else:
            # Translators: e.g. "Not quite — the answer is F4".
            title = _('Not quite — the answer is {answer}').format(answer=label)
        sentences = []
        if not correct and written is not None:
            sentences.append(compare_written(pitch, written))
        sentences.extend(self._explanation(clef, pitch))
        return Feedback(
            correct=correct,
            title=title,
            detail=' '.join(sentences),
            expected_label=label,
            play_expected=PlaybackSpec.melodic([pitch], note_length=Fraction(2)),
            play_given=(
                PlaybackSpec.melodic([written], note_length=Fraction(2))
                if written is not None and not correct
                else None
            ),
        )

    def answer_label(self, question: Question, value: object) -> str:
        return staff_value_label(value)

    def serialize(self, value: object) -> str:
        return staff_value_text(value)

    @staticmethod
    def _explanation(clef: Clef, pitch: Pitch) -> list[str]:
        natural = Pitch(pitch.letter, 0, pitch.octave)
        sentences = [where_on_staff(clef, natural)]
        position = clef.staff_position(pitch)
        if 0 <= position <= _TOP_LINE:
            sentences.append(staff_mnemonic(clef, lines=position % 2 == 0))
        else:
            sentences.append(counting_from_staff(clef, natural))
        landmark = landmark_sentence(clef, natural)
        if landmark:
            sentences.append(landmark)
        if pitch.alter > 0:
            sentences.append(
                _('A sharp before the note raises {natural} a semitone to {note}.').format(
                    natural=full_name(natural), note=full_name(pitch)
                )
            )
        elif pitch.alter < 0:
            sentences.append(
                _('A flat before the note lowers {natural} a semitone to {note}.').format(
                    natural=full_name(natural), note=full_name(pitch)
                )
            )
        return sentences


EXERCISES: tuple[ExerciseDefinition, ...] = (NotePlacement(),)
