# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Note naming: read one note in treble, bass, alto or tenor clef (design 1c).

Items are a clef and a written pitch, ``note.treble.F4``, ``note.bass.A2``
or, with accidentals, ``note.treble.F#4``: what a learner has to recognise
is a position on a particular staff, and those are learned one by one
(the top space of the bass staff is not known because the bottom line is).

Teaching order follows how notes are usually taught. Each clef starts at
its landmark, the line the clef itself marks (treble G4, bass F3, alto and
tenor middle C), and spreads out over the staff and the two notes that
touch it from outside; then come the ledger lines, one at a time; then the
same positions with a sharp or a flat. Clefs are interleaved rank by rank,
so a learner who reads two clefs meets both from the start.

The figure's description says which staff is shown but never the note:
the automatic description would read the answer to a screen reader.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from fractions import Fraction
from gettext import gettext as _
from gettext import ngettext
from typing import cast

from ...audio.spec import PlaybackSpec
from ...core import Pitch, PitchName
from ...core.naming import pitch_name
from ...core.pitch import Letter
from ...learning.model import ItemId
from ...notation.spec import Chord, Clef, Head, StaffSpec
from ..base import (
    BoolSetting,
    ExerciseDefinition,
    Family,
    Feedback,
    IntSetting,
    Modality,
    MultiChoiceSetting,
    Option,
    PianoAnswer,
    Question,
)

MAX_LEDGER_LINES = 3
_CLEFS = {
    'treble': Clef.TREBLE,
    'bass': Clef.BASS,
    'alto': Clef.ALTO,
    'tenor': Clef.TENOR,
}
# The line each clef marks: the G clef curls around G4, the F clef's dots
# surround F3, and the C clef centres on middle C.
LANDMARKS = {
    Clef.TREBLE: Pitch(Letter.G, 0, 4),
    Clef.BASS: Pitch(Letter.F, 0, 3),
    Clef.ALTO: Pitch(Letter.C, 0, 4),
    Clef.TENOR: Pitch(Letter.C, 0, 4),
}
_TOP_LINE = 8
# Sharps and flats that land on a white key (E♯, B♯, C♭, F♭) are spelling
# exercises, not reading ones: the piano answer could not tell them apart.
WHITE_KEY_ACCIDENTALS = frozenset(
    {
        PitchName(Letter.E, 1),
        PitchName(Letter.B, 1),
        PitchName(Letter.C, -1),
        PitchName(Letter.F, -1),
    }
)
_MIDDLE_C = Pitch(Letter.C, 0, 4)


# Items -------------------------------------------------------------------------


def item_id(clef: Clef, pitch: Pitch) -> ItemId:
    """``note.treble.F4``, ``note.bass.Bb2``, ``note.alto.C#4``."""
    return ItemId(f'note.{clef.value}.{pitch}')


def parse_item(item: str) -> tuple[Clef, Pitch]:
    """Inverse of :func:`item_id`; raises :class:`ValueError` for other ids."""
    parts = item.split('.')
    if len(parts) != 3 or parts[0] != 'note' or parts[1] not in _CLEFS:
        raise ValueError(f'not a note-naming item: {item!r}')
    clef = _CLEFS[parts[1]]
    try:
        pitch = Pitch.parse(parts[2])
    except ValueError:
        raise ValueError(f'not a note-naming item: {item!r}') from None
    position = clef.staff_position(pitch)
    if (
        str(pitch) != parts[2]
        or abs(pitch.alter) > 1
        or pitch.name in WHITE_KEY_ACCIDENTALS
        or ledger_lines(position) > MAX_LEDGER_LINES
    ):
        raise ValueError(f'not a note-naming item: {item!r}')
    return clef, pitch


def ledger_lines(position: int) -> int:
    """Ledger lines a note at ``position`` needs (0 on the staff and just outside it)."""
    if position < 0:
        return -position // 2
    return max(0, position - _TOP_LINE) // 2


def positions_in_order(clef: Clef, ledger: int) -> list[int]:
    """Staff positions of one clef in teaching order (see the module docstring)."""
    landmark = clef.staff_position(LANDMARKS[clef])
    staff = sorted(range(-1, _TOP_LINE + 2), key=lambda p: (abs(p - landmark), p < landmark))
    for count in range(1, ledger + 1):
        # The ledger line itself before the space beyond it, below before above
        # (the first line below the treble staff is middle C).
        staff += [-2 * count, _TOP_LINE + 2 * count, -2 * count - 1, _TOP_LINE + 2 * count + 1]
    return staff


def keyboard_range(pitch: Pitch) -> tuple[Pitch, Pitch]:
    """The two-octave keyboard for naming ``pitch`` with its octave.

    C3–C5 whenever the note fits, so middle C sits in the middle of the
    keyboard and the learner can find octaves from it (the keys show no octave
    numbers); notes outside it get the two octaves next to it.
    """
    if pitch < Pitch(Letter.C, 0, 3):
        low = Pitch(Letter.C, 0, pitch.octave)
    elif pitch > Pitch(Letter.C, 0, 5):
        low = Pitch(Letter.C, 0, pitch.octave - 1)
    else:
        low = Pitch(Letter.C, 0, 3)
    return low, Pitch(Letter.C, 0, low.octave + 2)


def interleave(columns: Sequence[Sequence[ItemId]]) -> list[ItemId]:
    longest = max((len(c) for c in columns), default=0)
    return [c[i] for i in range(longest) for c in columns if i < len(c)]


# Settings ----------------------------------------------------------------------


def _clefs(settings: Mapping[str, object]) -> list[Clef]:
    chosen = [_CLEFS[c] for c in cast(Sequence[str], settings.get('clefs', ())) if c in _CLEFS]
    return chosen or [Clef.TREBLE]


def _ledger(settings: Mapping[str, object]) -> int:
    value = settings.get('ledger-lines', 1)
    return max(0, min(MAX_LEDGER_LINES, int(cast(int, value))))


def _with_accidentals(settings: Mapping[str, object]) -> bool:
    return bool(settings.get('accidentals', False))


def _octave_matters(settings: Mapping[str, object]) -> bool:
    return bool(settings.get('octave', False))


# Names -------------------------------------------------------------------------


def full_name(pitch: Pitch) -> str:
    """``'F♯4'`` in the learner's naming convention."""
    return pitch_name(pitch.name) + str(pitch.octave)


def _names(pitches: Sequence[Pitch], *, octave: bool = False) -> str:
    # Translators: separator between note names in a list such as "F A C E".
    separator = _(' ')
    return separator.join(full_name(p) if octave else pitch_name(p.name) for p in pitches)


def _staff_name(clef: Clef) -> str:
    # Translators: the {staff} of sentences such as "F4 is in the first space of the
    # treble staff."
    names = {
        Clef.TREBLE: _('the treble staff'),
        Clef.BASS: _('the bass staff'),
        Clef.ALTO: _('the alto staff'),
        Clef.TENOR: _('the tenor staff'),
    }
    return names[clef]


def _clef_label(clef: Clef) -> str:
    names = {
        Clef.TREBLE: _('Treble clef'),
        Clef.BASS: _('Bass clef'),
        Clef.ALTO: _('Alto clef'),
        Clef.TENOR: _('Tenor clef'),
    }
    return names[clef]


def staff_mnemonic(clef: Clef, lines: bool) -> str:
    """The note names of the lines or spaces of a staff, as in design 1c's hint."""
    start = 0 if lines else 1
    notes = _names([clef.pitch_at(p) for p in range(start, _TOP_LINE + 1, 2)])
    if lines:
        templates = {
            Clef.TREBLE: _('Lines of the treble staff are {notes} from the bottom up.'),
            Clef.BASS: _('Lines of the bass staff are {notes} from the bottom up.'),
            Clef.ALTO: _('Lines of the alto staff are {notes} from the bottom up.'),
            Clef.TENOR: _('Lines of the tenor staff are {notes} from the bottom up.'),
        }
    else:
        templates = {
            Clef.TREBLE: _('Spaces of the treble staff spell {notes} from the bottom up.'),
            Clef.BASS: _('Spaces of the bass staff are {notes} from the bottom up.'),
            Clef.ALTO: _('Spaces of the alto staff are {notes} from the bottom up.'),
            Clef.TENOR: _('Spaces of the tenor staff are {notes} from the bottom up.'),
        }
    return templates[clef].format(notes=notes)


def where_on_staff(clef: Clef, pitch: Pitch) -> str:
    """Where the note sits, e.g. "F4 is in the first space of the treble staff."."""
    position = clef.staff_position(pitch)
    note, staff = full_name(pitch), _staff_name(clef)
    if 0 <= position <= _TOP_LINE:
        if position % 2 == 0:
            lines = {
                1: _('{note} is on the bottom line of {staff}.'),
                2: _('{note} is on the second line of {staff}.'),
                3: _('{note} is on the middle line of {staff}.'),
                4: _('{note} is on the fourth line of {staff}.'),
                5: _('{note} is on the top line of {staff}.'),
            }
            return lines[position // 2 + 1].format(note=note, staff=staff)
        spaces = {
            1: _('{note} is in the first space of {staff}.'),
            2: _('{note} is in the second space of {staff}.'),
            3: _('{note} is in the third space of {staff}.'),
            4: _('{note} is in the top space of {staff}.'),
        }
        return spaces[position // 2 + 1].format(note=note, staff=staff)
    if position == -1:
        return _('{note} sits just below {staff}, under the bottom line.').format(
            note=note, staff=staff
        )
    if position == _TOP_LINE + 1:
        return _('{note} sits just above {staff}, over the top line.').format(
            note=note, staff=staff
        )
    count = ledger_lines(position)
    below = position < 0
    on_line = position % 2 == 0
    if below and on_line:
        templates = {
            1: _('{note} is on the first ledger line below {staff}.'),
            2: _('{note} is on the second ledger line below {staff}.'),
            3: _('{note} is on the third ledger line below {staff}.'),
        }
    elif below:
        templates = {
            1: _('{note} is in the space under the first ledger line below {staff}.'),
            2: _('{note} is in the space under the second ledger line below {staff}.'),
            3: _('{note} is in the space under the third ledger line below {staff}.'),
        }
    elif on_line:
        templates = {
            1: _('{note} is on the first ledger line above {staff}.'),
            2: _('{note} is on the second ledger line above {staff}.'),
            3: _('{note} is on the third ledger line above {staff}.'),
        }
    else:
        templates = {
            1: _('{note} is in the space over the first ledger line above {staff}.'),
            2: _('{note} is in the space over the second ledger line above {staff}.'),
            3: _('{note} is in the space over the third ledger line above {staff}.'),
        }
    return templates[count].format(note=note, staff=staff)


def counting_from_staff(clef: Clef, pitch: Pitch) -> str:
    """A worked count from the nearest outer line, for notes outside the staff."""
    position = clef.staff_position(pitch)
    if position < 0:
        steps = [clef.pitch_at(p) for p in range(0, position - 1, -1)]
        # Translators: {notes} is a list such as "E4 D4 C4".
        return _('Counting down from the bottom line: {notes}.').format(
            notes=_names(steps, octave=True)
        )
    steps = [clef.pitch_at(p) for p in range(_TOP_LINE, position + 1)]
    # Translators: {notes} is a list such as "F5 G5 A5".
    return _('Counting up from the top line: {notes}.').format(notes=_names(steps, octave=True))


def landmark_sentence(clef: Clef, natural: Pitch) -> str:
    """The clef's own line, or middle C, named as a reference point."""
    if natural != LANDMARKS[clef]:
        if natural == _MIDDLE_C:
            return _('{note} is middle C.').format(note=full_name(natural))
        return ''
    note = full_name(natural)
    if clef is Clef.TREBLE:
        return _('The treble clef curls around this line: it marks {note}.').format(note=note)
    if clef is Clef.BASS:
        return _('The two dots of the bass clef surround this line: it marks {note}.').format(
            note=note
        )
    return _('The C clef centres on this line: it marks middle C, {note}.').format(note=note)


def reading_hint(clef: Clef, pitch: Pitch) -> str:
    """Where to start reading: the staff's lines or spaces, or counting from its edge."""
    position = clef.staff_position(pitch)
    if 0 <= position <= _TOP_LINE:
        return staff_mnemonic(clef, lines=position % 2 == 0)
    if position < 0:
        return _(
            'Below the staff, lines and spaces keep alternating down from the bottom line, {note}.'
        ).format(note=full_name(clef.pitch_at(0)))
    return _(
        'Above the staff, lines and spaces keep alternating up from the top line, {note}.'
    ).format(note=full_name(clef.pitch_at(_TOP_LINE)))


# The exercise ------------------------------------------------------------------


class NoteNaming(ExerciseDefinition):
    id = 'note-naming'
    item_prefix = 'note.'
    family = Family.NOTATION
    modality = Modality.EYE
    level = 1
    icon_name = 'note-symbolic'
    glyph = '♩'
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
            subtitle=_('Also read notes with an accidental'),
        ),
        BoolSetting(
            'octave',
            _('Name the octave'),
            False,
            subtitle=_('Answer on the keyboard in the right octave'),
        ),
    )

    @property
    def title(self) -> str:
        return _('Note Naming')

    @property
    def description(self) -> str:
        return _('Read notes in treble, bass and C clefs.')

    @property
    def play_label(self) -> str:
        return _('Play note')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        clefs = _clefs(settings)
        clef_text = _clef_label(clefs[0]) if len(clefs) == 1 else _('Mixed clefs')
        ledger = _ledger(settings)
        if ledger == 0:
            ledger_text = _('no ledger lines')
        else:
            ledger_text = ngettext(
                'up to {n} ledger line', 'up to {n} ledger lines', ledger
            ).format(n=ledger)
        parts = [clef_text, ledger_text]
        if _with_accidentals(settings):
            parts.append(_('sharps and flats'))
        return ' · '.join(parts)

    def item_label(self, item_id: ItemId) -> str:
        clef, pitch = parse_item(item_id)
        templates = {
            # Translators: an item in "Weakest items", e.g. "F4 — treble clef".
            Clef.TREBLE: _('{note} — treble clef'),
            Clef.BASS: _('{note} — bass clef'),
            Clef.ALTO: _('{note} — alto clef'),
            Clef.TENOR: _('{note} — tenor clef'),
        }
        return templates[clef].format(note=full_name(pitch))

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        """Naturals clef by clef from each landmark outwards, then ledger lines, then
        accidentals; clefs interleaved rank by rank."""
        ledger = _ledger(settings)
        clefs = _clefs(settings)
        staff_count = _TOP_LINE + 3
        naturals = {c: [c.pitch_at(p) for p in positions_in_order(c, ledger)] for c in clefs}
        order = interleave([[item_id(c, p) for p in naturals[c][:staff_count]] for c in clefs])
        order += interleave([[item_id(c, p) for p in naturals[c][staff_count:]] for c in clefs])
        if _with_accidentals(settings):
            altered = [
                [
                    item_id(c, p)
                    for natural in naturals[c]
                    for alter in (1, -1)
                    if (p := Pitch(natural.letter, alter, natural.octave)).name
                    not in WHITE_KEY_ACCIDENTALS
                ]
                for c in clefs
            ]
            order += interleave(altered)
        return order

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        clef, pitch = parse_item(item_id)
        octave_matters = _octave_matters(settings)
        if octave_matters:
            low, high = keyboard_range(pitch)
            expected: Pitch | PitchName = pitch
        else:
            low, high = Pitch(Letter.C, 0, 4), Pitch(Letter.C, 0, 5)
            expected = pitch.name
        descriptions = {
            Clef.TREBLE: _('Treble staff with one note.'),
            Clef.BASS: _('Bass staff with one note.'),
            Clef.ALTO: _('Alto staff with one note.'),
            Clef.TENOR: _('Tenor staff with one note.'),
        }
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Name this note'),
            answer=PianoAnswer(low, high, octave_matters=octave_matters),
            expected=expected,
            figure=StaffSpec(
                clef=clef, events=(Chord((Head(pitch),)),), description=descriptions[clef]
            ),
            hint=reading_hint(clef, pitch),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        clef, pitch = parse_item(question.item_id)
        label = full_name(pitch)
        correct = self._matches(pitch, given, octave=isinstance(question.expected, Pitch))
        if correct:
            # Translators: e.g. "Correct — F4".
            title = _('Correct — {answer}').format(answer=label)
        else:
            # Translators: e.g. "Not quite — the answer is F4".
            title = _('Not quite — the answer is {answer}').format(answer=label)
        return Feedback(
            correct=correct,
            title=title,
            detail=self._explanation(clef, pitch, given, correct),
            expected_label=label,
            play_expected=PlaybackSpec.melodic([pitch], note_length=Fraction(2)),
        )

    def answer_label(self, question: Question, value: object) -> str:
        """The written note with its octave ("F4") when the answer is that note."""
        pitch = parse_item(question.item_id)[1]
        if value == question.expected:
            return full_name(pitch)
        return super().answer_label(question, value)

    def serialize(self, value: object) -> str:
        return str(value)

    # Grading

    @staticmethod
    def _matches(pitch: Pitch, given: object, *, octave: bool) -> bool:
        """Same spelling, or the other name of the same black key.

        A click on a black key cannot say whether the learner meant A♯ or B♭,
        so a sharp is accepted for a flat (and the other way round) when both
        are black-key names. A natural is never accepted for an accidental.
        """
        if octave:
            if not isinstance(given, Pitch):
                return False
            if given == pitch:
                return True
            return pitch.alter != 0 and given.alter != 0 and given.midi == pitch.midi
        name = given.name if isinstance(given, Pitch) else given
        if not isinstance(name, PitchName):
            return False
        if name == pitch.name:
            return True
        return pitch.alter != 0 and name.alter != 0 and name.pitch_class == pitch.pitch_class

    # Explanations

    @staticmethod
    def _explanation(clef: Clef, pitch: Pitch, given: object, correct: bool) -> str:
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
                _('The sharp raises {natural} a semitone to {note}.').format(
                    natural=full_name(natural), note=full_name(pitch)
                )
            )
        elif pitch.alter < 0:
            sentences.append(
                _('The flat lowers {natural} a semitone to {note}.').format(
                    natural=full_name(natural), note=full_name(pitch)
                )
            )
        given_name = given.name if isinstance(given, Pitch) else given
        if correct and isinstance(given_name, PitchName) and given_name != pitch.name:
            sentences.append(
                _('{given} is the same key on the piano, but this note is written {note}.').format(
                    given=pitch_name(given_name), note=pitch_name(pitch.name)
                )
            )
        elif not correct and isinstance(given, Pitch) and given_name == pitch.name:
            sentences.append(
                _('Right letter, wrong octave: octave numbers start again at every C.')
            )
            if natural != _MIDDLE_C:
                sentences.append(
                    _('Middle C, in the middle of the keyboard, is {middle_c}.').format(
                        middle_c=full_name(_MIDDLE_C)
                    )
                )
        return ' '.join(sentences)


EXERCISES: tuple[ExerciseDefinition, ...] = (NoteNaming(),)
