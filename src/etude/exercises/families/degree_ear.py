# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Scale degrees by ear: hear a key, then one note, and name its degree.

A cadence (I–IV–V–I, or i–iv–V–i in minor) or the scale establishes the
key; then one note sounds and the learner answers with its degree, 1–7,
labelled with the degree names as in the eye exercise (design 1g). Items
are per mode and degree, ``degree-ear.major.5`` or ``degree-ear.minor.3``
(not ``degree.ear…``: the eye exercise owns ``degree.``). The key, register
and the octave of the note vary per question.

Minor keys use the natural minor scale, as :mod:`.scale_degrees` does: the
seventh degree is the subtonic. The cadence's dominant chord still has the
raised leading tone, because that is how minor keys establish themselves;
the explanation names both.

The written alternative is the key signature with the note highlighted
and the key named in the context line.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from fractions import Fraction
from gettext import gettext as _
from typing import ClassVar

from ...audio.spec import PlaybackNote, PlaybackSpec
from ...core import Pitch
from ...core.naming import degree_name, degree_short_name, key_name, pitch_name
from ...core.scale import Key, Mode
from ...learning.model import ItemId
from ...notation.spec import Chord, Clef, Head, Ink, StaffSpec
from ..base import (
    ChoiceAnswer,
    ChoiceSetting,
    ExerciseDefinition,
    Family,
    Feedback,
    Modality,
    Option,
    Question,
    Setting,
)
from .scale_degrees import TEACHING_ORDER, answer_phrase, degree_explanation, key_for

_MODES = {m.value: m for m in Mode}
_MAX_FIFTHS = 4
"""Keys with up to four sharps or flats: the register matters here, not the spelling."""
_TONIC_RANGE = (55, 66)
"""MIDI range of the tonic: G3 to F♯4."""
_CADENCE = (1, 4, 5, 1)
_CONFUSABLE: dict[int, tuple[int, ...]] = {
    1: (5, 3),
    2: (7, 3),
    3: (6, 2),
    4: (5, 3),
    5: (4, 1),
    6: (3, 5),
    7: (2, 1),
}


def item_id(mode: Mode, degree: int) -> ItemId:
    """``degree-ear.major.5``."""
    return ItemId(f'degree-ear.{mode.value}.{degree}')


def parse_item(item: str) -> tuple[Mode, int]:
    parts = item.split('.')
    if (
        len(parts) != 3
        or parts[0] != 'degree-ear'
        or parts[1] not in _MODES
        or parts[2] not in {str(n) for n in range(1, 8)}
    ):
        raise ValueError(f'not a scale-degree ear item: {item!r}')
    return _MODES[parts[1]], int(parts[2])


def _modes(settings: Mapping[str, object]) -> tuple[Mode, ...]:
    choice = settings.get('mode', 'major')
    if choice == 'minor':
        return (Mode.MINOR,)
    if choice == 'both':
        return (Mode.MAJOR, Mode.MINOR)
    return (Mode.MAJOR,)


def tonic_pitch(key: Key) -> Pitch:
    return next(
        key.tonic.at(o)
        for o in range(1, 7)
        if _TONIC_RANGE[0] <= key.tonic.at(o).midi <= _TONIC_RANGE[1]
    )


def cadence(key: Key, tonic: Pitch) -> PlaybackSpec:
    """I–IV–V–I in close position over the root, each chord one beat, the last two."""
    notes: list[PlaybackNote] = []
    for index, degree in enumerate(_CADENCE):
        chord = key.triad(degree)
        octave = tonic.octave
        pitches = list(chord.pitches(octave))
        if pitches[0].midi > tonic.midi + 5:
            pitches = list(chord.pitches(octave - 1))
        bass = Pitch(pitches[0].letter, pitches[0].alter, pitches[0].octave - 1)
        length = Fraction(2) if index == len(_CADENCE) - 1 else Fraction(1)
        for pitch in (bass, *pitches):
            notes.append(PlaybackNote(pitch.midi, Fraction(index), length))
    return PlaybackSpec(tuple(notes), tempo=80.0)


def scale_context(key: Key, tonic: Pitch) -> PlaybackSpec:
    return PlaybackSpec.melodic(
        key.scale.pitches(tonic.octave), note_length=Fraction(1, 2), tempo=80.0
    )


def degree_note(key: Key, degree: int, tonic: Pitch, rng: random.Random) -> Pitch:
    """The degree within a fifth below to an octave above the tonic."""
    name = key.degree(degree)
    candidates = [
        name.at(o) for o in range(1, 8) if tonic.midi - 7 <= name.at(o).midi <= tonic.midi + 12
    ]
    return rng.choice(candidates)


class DegreeEar(ExerciseDefinition):
    id = 'degree-ear'
    item_prefix = 'degree-ear.'
    family = Family.EAR
    modality = Modality.EAR
    level = 1
    icon_name = 'degree-ear-symbolic'
    glyph = '5̂'
    settings: ClassVar[tuple[Setting, ...]] = (
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
        ChoiceSetting(
            'context',
            _('Key set by'),
            (
                Option('cadence', _('Chords: I–IV–V–I')),
                Option('scale', _('The scale')),
            ),
            'cadence',
        ),
    )

    @property
    def title(self) -> str:
        return _('Scale Degrees — Ear')

    @property
    def description(self) -> str:
        return _('Hear a key, then a note, and name its degree.')

    @property
    def play_label(self) -> str:
        return _('Play')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        modes = _modes(settings)
        if len(modes) == 2:
            keys = _('Major and minor keys')
        elif modes[0] is Mode.MINOR:
            keys = _('Minor keys')
        else:
            keys = _('Major keys')
        context = _('cadence') if settings.get('context', 'cadence') != 'scale' else _('scale')
        return _(' · ').join((keys, context))

    def item_label(self, item_id: ItemId) -> str:
        mode, degree = parse_item(item_id)
        name = degree_name(key_for(mode, 0).degree_function(degree))
        if mode is Mode.MAJOR:
            # Translators: an item in "Weakest items", e.g. "Dominant — major (ear)".
            return _('{degree} — major (ear)').format(degree=name)
        # Translators: an item in "Weakest items", e.g. "Mediant — minor (ear)".
        return _('{degree} — minor (ear)').format(degree=name)

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        return [item_id(m, d) for m in _modes(settings) for d in TEACHING_ORDER]

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        mode, degree = parse_item(item_id)
        return [ItemId(f'degree-ear.{mode.value}.{d}') for d in _CONFUSABLE[degree]]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        mode, degree = parse_item(item_id)
        key = key_for(mode, rng.randint(-_MAX_FIFTHS, _MAX_FIFTHS))
        tonic = tonic_pitch(key)
        note = degree_note(key, degree, tonic, rng)
        use_scale = settings.get('context', 'cadence') == 'scale'
        context = scale_context(key, tonic) if use_scale else cadence(key, tonic)
        playback = PlaybackSpec.sequence(
            context, PlaybackSpec.melodic([note], note_length=Fraction(2))
        )
        options = tuple(
            Option(str(n), str(n), str(n), degree_short_name(key.degree_function(n)))
            for n in range(1, 8)
        )
        clef = Clef.TREBLE if note.midi >= 57 else Clef.BASS
        figure = StaffSpec(
            clef=clef,
            key_signature=key.signature,
            events=(Chord((Head(note, ink=Ink.ACCENT, halo=True),)),),
        )
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Which scale degree is the last note?'),
            answer=ChoiceAnswer(options),
            expected=str(degree),
            playback=playback,
            playback_is_question=True,
            playback_style_choice=False,
            written_alternative=figure,
            # Translators: the key of a scale-degree question, e.g. "Key: D major".
            context=_('Key: {key}').format(key=key_name(key)),
            hint=_('Sing from the note down to the tonic and count the steps.'),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        mode, degree = parse_item(question.item_id)
        figure = question.written_alternative
        assert isinstance(figure, StaffSpec)
        assert figure.key_signature is not None
        key = key_for(mode, figure.key_signature.fifths)
        chord = figure.events[0]
        assert isinstance(chord, Chord)
        note = chord.heads[0].pitch
        expected = str(question.expected)
        correct = str(given) == expected
        label = self.answer_label(question, expected)
        if correct:
            # Translators: e.g. "Correct — 5, the dominant".
            title = _('Correct — {answer}').format(answer=label)
        else:
            # Translators: e.g. "Not quite — the answer is 5, the dominant".
            title = _('Not quite — the answer is {answer}').format(answer=label)
        sentences = [degree_explanation(key, degree)]
        play_given = None
        if not correct and str(given) in {str(n) for n in range(1, 8)}:
            other = int(str(given))
            sentences.append(
                _('Degree {number} of {key} is {note}.').format(
                    number=other, key=key_name(key), note=pitch_name(key.degree(other))
                )
            )
            tonic = tonic_pitch(key)
            context = question.playback
            assert context is not None
            given_note = min(
                (key.degree(other).at(o) for o in range(1, 8)),
                key=lambda p: abs(p.midi - note.midi),
            )
            use_scale = len({n.start for n in context.notes}) > len(_CADENCE) + 1
            play_given = PlaybackSpec.sequence(
                scale_context(key, tonic) if use_scale else cadence(key, tonic),
                PlaybackSpec.melodic([given_note], note_length=Fraction(2)),
            )
        return Feedback(
            correct=correct,
            title=title,
            detail=' '.join(sentences),
            expected_label=label,
            figure=figure,
            play_expected=question.playback,
            play_given=play_given,
        )

    def answer_label(self, question: Question, value: object) -> str:
        mode, _degree = parse_item(question.item_id)
        text = str(value)
        if text not in {str(n) for n in range(1, 8)}:
            return super().answer_label(question, value)
        return answer_phrase(key_for(mode, 0).degree_function(int(text)))

    def serialize(self, value: object) -> str:
        return str(value)


EXERCISES: tuple[ExerciseDefinition, ...] = (DegreeEar(),)
