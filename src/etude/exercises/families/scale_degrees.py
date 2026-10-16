# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Scale degrees: the number and name of a note within a key (design 1g).

Two kinds of item per mode and degree:

* ``degree.major.5``, *identify*: a key signature with one highlighted
  note and the key named beside the staff; the learner answers with the
  degree (``1``–``7``, labelled Tonic … Leading as in the design).
* ``degree.major.find.5``, *find*: the seven notes of the scale in a
  shuffled order; the prompt names a degree ("Which note is the
  dominant?") and the learner clicks that note on the staff or picks its
  name. This is where the design's "click the note on the staff" belongs:
  in an identify question the only note on the staff is the highlighted
  one, so clicking it could not be a choice.

Both directions are scheduled separately because knowing that A is the
fifth of D major and finding the dominant of D major are different
retrievals. Keys, clefs and registers vary per question within the
settings, so the learner learns the degree, not one picture.

Minor keys use the natural minor scale of the key signature, as
:meth:`etude.core.Key.degree_function` does: the seventh degree is the
subtonic, a whole step below the tonic. Explanations add that raised a
semitone it becomes the leading tone.

Teaching order is the primary degrees first (tonic, dominant,
subdominant), then mediant, supertonic, submediant and the seventh; each
identify item is followed by its find item.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from fractions import Fraction
from gettext import gettext as _
from gettext import ngettext
from typing import cast

from ...audio.spec import PlaybackSpec
from ...core import DegreeFunction, KeySignature, Pitch
from ...core.naming import degree_name, degree_short_name, key_name, pitch_name
from ...core.scale import Key, Mode
from ...learning.model import ItemId
from ...notation.spec import Chord, Clef, Head, Ink, StaffSpec
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
)

MAX_ACCIDENTALS = 7
TEACHING_ORDER = (1, 5, 4, 3, 2, 6, 7)
_CLEFS = {
    'treble': Clef.TREBLE,
    'bass': Clef.BASS,
    'alto': Clef.ALTO,
    'tenor': Clef.TENOR,
}
_MODES = {m.value: m for m in Mode}
_TOP_LINE = 8
_FIND = 'find'


# Items -------------------------------------------------------------------------


def item_id(mode: Mode, degree: int, *, find: bool = False) -> ItemId:
    """``degree.major.5`` (identify) or ``degree.minor.find.3`` (find on the staff)."""
    middle = f'{_FIND}.' if find else ''
    return ItemId(f'degree.{mode.value}.{middle}{degree}')


def parse_item(item: str) -> tuple[Mode, int, bool]:
    """Inverse of :func:`item_id`: ``(mode, degree, find)``; raises :class:`ValueError`."""
    parts = item.split('.')
    find = len(parts) == 4 and parts[2] == _FIND
    if (
        len(parts) not in (3, 4)
        or (len(parts) == 4 and not find)
        or parts[0] != 'degree'
        or parts[1] not in _MODES
        or parts[-1] not in {str(n) for n in range(1, 8)}
    ):
        raise ValueError(f'not a scale-degree item: {item!r}')
    return _MODES[parts[1]], int(parts[-1]), find


def key_for(mode: Mode, fifths: int) -> Key:
    signature = KeySignature(fifths)
    tonic = signature.major_tonic if mode is Mode.MAJOR else signature.minor_tonic
    return Key(tonic, mode)


# Settings ----------------------------------------------------------------------


def _modes(settings: Mapping[str, object]) -> tuple[Mode, ...]:
    choice = settings.get('mode', 'major')
    if choice == 'minor':
        return (Mode.MINOR,)
    if choice == 'both':
        return (Mode.MAJOR, Mode.MINOR)
    return (Mode.MAJOR,)


def _limit(settings: Mapping[str, object]) -> int:
    value = settings.get('max-accidentals', 4)
    return max(0, min(MAX_ACCIDENTALS, int(cast(int, value))))


def _clefs(settings: Mapping[str, object]) -> list[Clef]:
    chosen = [_CLEFS[c] for c in cast(Sequence[str], settings.get('clefs', ())) if c in _CLEFS]
    return chosen or [Clef.TREBLE]


# Phrases -----------------------------------------------------------------------
# Whole sentences per degree, so translators never assemble grammar from parts.


def answer_phrase(function: DegreeFunction) -> str:
    """How a degree answer reads in feedback: "5, the dominant" (design 1g)."""
    phrases = {
        # Translators: a scale-degree answer, as in "Correct — 1, the tonic".
        DegreeFunction.TONIC: _('1, the tonic'),
        DegreeFunction.SUPERTONIC: _('2, the supertonic'),
        DegreeFunction.MEDIANT: _('3, the mediant'),
        DegreeFunction.SUBDOMINANT: _('4, the subdominant'),
        DegreeFunction.DOMINANT: _('5, the dominant'),
        DegreeFunction.SUBMEDIANT: _('6, the submediant'),
        DegreeFunction.LEADING_TONE: _('7, the leading tone'),
        DegreeFunction.SUBTONIC: _('7, the subtonic'),
    }
    return phrases[function]


def _find_prompt(function: DegreeFunction) -> str:
    prompts = {
        DegreeFunction.TONIC: _('Which note is the tonic?'),
        DegreeFunction.SUPERTONIC: _('Which note is the supertonic?'),
        DegreeFunction.MEDIANT: _('Which note is the mediant?'),
        DegreeFunction.SUBDOMINANT: _('Which note is the subdominant?'),
        DegreeFunction.DOMINANT: _('Which note is the dominant?'),
        DegreeFunction.SUBMEDIANT: _('Which note is the submediant?'),
        DegreeFunction.LEADING_TONE: _('Which note is the leading tone?'),
        DegreeFunction.SUBTONIC: _('Which note is the subtonic?'),
    }
    return prompts[function]


def _explanation(key: Key, degree: int) -> str:
    """E.g. "In D major, A is the fifth degree: the dominant, a fifth above the tonic."."""
    function = key.degree_function(degree)
    templates = {
        DegreeFunction.TONIC: _('In {key}, {note} is the first degree: the tonic, the home note.'),
        DegreeFunction.SUPERTONIC: _(
            'In {key}, {note} is the second degree: the supertonic, a step above the tonic.'
        ),
        DegreeFunction.MEDIANT: _(
            'In {key}, {note} is the third degree: the mediant, halfway from the tonic to the '
            'dominant.'
        ),
        DegreeFunction.SUBDOMINANT: _(
            'In {key}, {note} is the fourth degree: the subdominant, a fifth below the tonic.'
        ),
        DegreeFunction.DOMINANT: _(
            'In {key}, {note} is the fifth degree: the dominant, a fifth above the tonic.'
        ),
        DegreeFunction.SUBMEDIANT: _(
            'In {key}, {note} is the sixth degree: the submediant, a third below the tonic.'
        ),
        DegreeFunction.LEADING_TONE: _(
            'In {key}, {note} is the seventh degree: the leading tone, a semitone below the tonic.'
        ),
        DegreeFunction.SUBTONIC: _(
            'In {key}, {note} is the seventh degree: the subtonic, a whole step below the '
            'tonic. Raised to {raised}, it becomes the leading tone.'
        ),
    }
    return templates[function].format(
        key=key_name(key),
        note=pitch_name(key.degree(degree)),
        raised=pitch_name(key.leading_tone),
    )


# Registers ---------------------------------------------------------------------


def _octaves(clef: Clef, low: int, high: int, fits: list[Pitch]) -> list[int]:
    """Octave shifts (relative to ``fits``) that keep every pitch between staff
    positions ``low`` and ``high``."""
    shifts = []
    for shift in range(-4, 5):
        positions = [clef.staff_position(Pitch(p.letter, p.alter, p.octave + shift)) for p in fits]
        if low <= min(positions) and max(positions) <= high:
            shifts.append(shift)
    return shifts


def _shift(pitches: Sequence[Pitch], octaves: int) -> list[Pitch]:
    return [Pitch(p.letter, p.alter, p.octave + octaves) for p in pitches]


def _scale_up_to(key: Key, degree: int, note: Pitch) -> list[Pitch]:
    """The scale from the tonic at or below ``note`` up to it (``degree`` notes)."""
    tonic_octave = note.octave
    if key.tonic.at(tonic_octave).diatonic_index > note.diatonic_index:
        tonic_octave -= 1
    return list(key.scale.pitches(tonic_octave)[:degree])


class ScaleDegrees(ExerciseDefinition):
    id = 'scale-degree'
    item_prefix = 'degree.'
    family = Family.HARMONY
    modality = Modality.EYE
    level = 1
    icon_name = 'scale-degree-symbolic'
    glyph = '♭'
    settings = (
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
        IntSetting(
            'max-accidentals',
            _('Most accidentals'),
            4,
            0,
            MAX_ACCIDENTALS,
            subtitle=_('Largest number of sharps or flats in the key signature'),
        ),
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
        BoolSetting(
            'find',
            _('Find degrees on the staff'),
            True,
            subtitle=_('Also click the note that is a named degree'),
        ),
    )

    @property
    def title(self) -> str:
        return _('Scale Degrees')

    @property
    def description(self) -> str:
        return _('Find the degree of a note within a key.')

    @property
    def play_label(self) -> str:
        return _('Play scale')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        modes = _modes(settings)
        if len(modes) == 2:
            keys = _('Major and minor keys')
        elif modes[0] is Mode.MINOR:
            keys = _('Minor keys')
        else:
            keys = _('Major keys')
        limit = _limit(settings)
        accidentals = ngettext('up to {n} accidental', 'up to {n} accidentals', limit).format(
            n=limit
        )
        return f'{keys} · {accidentals}'

    def item_label(self, item_id: ItemId) -> str:
        mode, degree, find = parse_item(item_id)
        name = degree_name(key_for(mode, 0).degree_function(degree))
        if find:
            if mode is Mode.MAJOR:
                # Translators: an item in "Weakest items", e.g. "Dominant on the staff — major".
                return _('{degree} on the staff — major').format(degree=name)
            return _('{degree} on the staff — minor').format(degree=name)
        if mode is Mode.MAJOR:
            # Translators: an item in "Weakest items", e.g. "Dominant — major".
            return _('{degree} — major').format(degree=name)
        return _('{degree} — minor').format(degree=name)

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        """Per mode, the primary degrees first; each identify item before its find item."""
        find = bool(settings.get('find', True))
        kinds = (False, True) if find else (False,)
        return [
            item_id(mode, degree, find=kind)
            for mode in _modes(settings)
            for degree in TEACHING_ORDER
            for kind in kinds
        ]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        mode, degree, find = parse_item(item_id)
        limit = _limit(settings)
        key = key_for(mode, rng.randint(-limit, limit))
        clef = rng.choice(_clefs(settings))
        if find:
            return self._find_question(item_id, key, degree, clef, rng)
        return self._identify_question(item_id, key, degree, clef, rng)

    def _identify_question(
        self, item_id: ItemId, key: Key, degree: int, clef: Clef, rng: random.Random
    ) -> Question:
        note = key.degree(degree).at(4)
        # On the staff, or just touching it, with the tonic below it at most one ledger
        # line away, so the worked answer (the scale up to the note) stays readable.
        candidates = [
            s
            for s in _octaves(clef, -1, _TOP_LINE + 1, [note])
            if clef.staff_position(_scale_up_to(key, degree, _shift([note], s)[0])[0]) >= -3
        ]
        note = _shift([note], rng.choice(candidates))[0]
        options = tuple(
            Option(str(n), str(n), str(n), degree_short_name(key.degree_function(n)))
            for n in range(1, 8)
        )
        tonic = _scale_up_to(key, 1, note)[0]
        playback = PlaybackSpec.sequence(
            self._scale_playback(key, tonic.octave),
            PlaybackSpec.melodic([note], note_length=Fraction(1)),
        )
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Which scale degree is highlighted?'),
            answer=ChoiceAnswer(options),
            expected=str(degree),
            figure=StaffSpec(
                clef=clef,
                key_signature=key.signature,
                events=(Chord((Head(note, ink=Ink.ACCENT, halo=True),)),),
            ),
            playback=playback,
            # Translators: the key of a scale-degree question, e.g. "Key: D major".
            context=_('Key: {key}').format(key=key_name(key)),
            hint=_('Count up the scale from the tonic, {tonic}, to the highlighted note.').format(
                tonic=pitch_name(key.tonic)
            ),
        )

    def _find_question(
        self, item_id: ItemId, key: Key, degree: int, clef: Clef, rng: random.Random
    ) -> Question:
        scale = list(key.scale.pitches(4)[:7])
        scale = _shift(scale, rng.choice(_octaves(clef, -2, _TOP_LINE + 2, scale)))
        order = rng.sample(range(7), 7)
        events = tuple(Chord((Head(scale[i]),)) for i in order)
        # Options follow the staff from left to right. Their accelerators are note
        # letters, not numbers: a number badge would read as a degree.
        options = tuple(
            Option(str(i + 1), pitch_name(scale[i].name), accel=scale[i].letter.name.lower())
            for i in order
        )
        targets = {slot: str(i + 1) for slot, i in enumerate(order)}
        function = key.degree_function(degree)
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_find_prompt(function),
            answer=ChoiceAnswer(options, targets=targets),
            expected=str(degree),
            figure=StaffSpec(clef=clef, key_signature=key.signature, events=events),
            playback=self._scale_playback(key, scale[0].octave),
            context=_('Key: {key}').format(key=key_name(key)),
            # Translators: e.g. "Dominant: degree 5. Count up the scale from the tonic, D."
            hint=_('{degree}: degree {number}. Count up the scale from the tonic, {tonic}.').format(
                degree=degree_name(function), number=degree, tonic=pitch_name(key.tonic)
            ),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        mode, degree, find = parse_item(question.item_id)
        figure = question.figure
        assert isinstance(figure, StaffSpec)
        assert figure.key_signature is not None
        key = key_for(mode, figure.key_signature.fifths)
        expected = str(question.expected)
        correct = str(given) == expected
        label = self.answer_label(question, expected)
        if correct:
            # Translators: e.g. "Correct — 5, the dominant".
            title = _('Correct — {answer}').format(answer=label)
        else:
            # Translators: e.g. "Not quite — the answer is 5, the dominant".
            title = _('Not quite — the answer is {answer}').format(answer=label)
        sentences = [_explanation(key, degree)]
        given_degree = int(str(given)) if str(given) in {str(n) for n in range(1, 8)} else None
        if not correct and given_degree is not None:
            note = pitch_name(key.degree(given_degree))
            if find:
                text = _('{note} is degree {number} of {key}.')
            else:
                text = _('Degree {number} of {key} is {note}.')
            sentences.append(text.format(note=note, number=given_degree, key=key_name(key)))
        return Feedback(
            correct=correct,
            title=title,
            detail=' '.join(sentences),
            expected_label=label,
            figure=self._worked_figure(figure, key, degree, find),
            play_expected=question.playback,
        )

    def answer_label(self, question: Question, value: object) -> str:
        """Identify answers read "5, the dominant"; find answers are note names."""
        mode, _degree, find = parse_item(question.item_id)
        text = str(value)
        if find or text not in {str(n) for n in range(1, 8)}:
            return super().answer_label(question, value)
        return answer_phrase(key_for(mode, 0).degree_function(int(text)))

    def serialize(self, value: object) -> str:
        return str(value)

    # Figures and sound

    @staticmethod
    def _worked_figure(figure: StaffSpec, key: Key, degree: int, find: bool) -> StaffSpec:
        """The answer worked out: degree numbers under the notes, the answer highlighted."""
        pitches = [e.heads[0].pitch for e in figure.events if isinstance(e, Chord)]
        if not find:
            pitches = _scale_up_to(key, degree, pitches[0])
        numbers = [key.scale.degree_of(p.name) or 0 for p in pitches]
        events = tuple(
            Chord(
                (Head(p, ink=Ink.ACCENT, halo=True) if n == degree else Head(p),),
                label=str(n),
            )
            for n, p in zip(numbers, pitches, strict=True)
        )
        return StaffSpec(clef=figure.clef, key_signature=figure.key_signature, events=events)

    @staticmethod
    def _scale_playback(key: Key, octave: int) -> PlaybackSpec:
        """The key's scale from the written tonic, up an octave (eye and ear together)."""
        pitches = key.scale.pitches(octave)
        return PlaybackSpec.melodic(pitches, note_length=Fraction(1, 2), tempo=100.0)


EXERCISES: tuple[ExerciseDefinition, ...] = (ScaleDegrees(),)
