# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Key signatures: name the major or minor key from its signature (design 1b).

Items are signatures per mode, ``keysig.major.4s``, ``keysig.minor.2b`` and
``keysig.major.0``; the clef is a surface variation chosen per question, so
the learner learns the signature, not one picture of it. The options are the
keys whose signatures use the same kind of accidental, which keeps the
choice about counting and ordering accidentals rather than spotting sharps
versus flats.

This module is the reference exercise: docs/ADDING_EXERCISES.md walks
through it.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from fractions import Fraction
from gettext import gettext as _
from gettext import ngettext
from typing import cast

from ...audio.spec import PlaybackSpec
from ...core import KeySignature, Pitch
from ...core.naming import key_name, pitch_name
from ...core.scale import Key, Mode
from ...learning.model import ItemId
from ...notation.spec import Clef, StaffSpec
from ..base import (
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
_CLEFS = {
    'treble': Clef.TREBLE,
    'bass': Clef.BASS,
    'alto': Clef.ALTO,
    'tenor': Clef.TENOR,
}
# Octave in which the key's scale is played, per mode, so it sits mid-range.
_SCALE_OCTAVE = 4


def item_id(mode: Mode, fifths: int) -> ItemId:
    """``keysig.major.4s``, ``keysig.minor.3b`` or ``keysig.major.0``."""
    count = '0' if fifths == 0 else f'{abs(fifths)}{"s" if fifths > 0 else "b"}'
    return ItemId(f'keysig.{mode.value}.{count}')


def parse_item(item: str) -> tuple[Mode, int]:
    """Inverse of :func:`item_id`; raises :class:`ValueError` for other ids."""
    parts = item.split('.')
    modes = {m.value: m for m in Mode}
    if len(parts) != 3 or parts[0] != 'keysig' or parts[1] not in modes:
        raise ValueError(f'not a key signature item: {item!r}')
    mode, count = modes[parts[1]], parts[2]
    if count == '0':
        return mode, 0
    number, kind = count[:-1], count[-1]
    if kind not in 'sb' or not number.isdigit() or not 1 <= int(number) <= MAX_ACCIDENTALS:
        raise ValueError(f'not a key signature item: {item!r}')
    return mode, int(number) if kind == 's' else -int(number)


def key_for(mode: Mode, fifths: int) -> Key:
    signature = KeySignature(fifths)
    tonic = signature.major_tonic if mode is Mode.MAJOR else signature.minor_tonic
    return Key(tonic, mode)


def _modes(settings: Mapping[str, object]) -> tuple[Mode, ...]:
    choice = settings.get('mode', 'major')
    if choice == 'minor':
        return (Mode.MINOR,)
    if choice == 'both':
        return (Mode.MAJOR, Mode.MINOR)
    return (Mode.MAJOR,)


def _limit(settings: Mapping[str, object]) -> int:
    value = settings.get('max-accidentals', 5)
    return max(0, min(MAX_ACCIDENTALS, int(cast(int, value))))


def _accidental_list(signature: KeySignature) -> str:
    # Translators: separator between the accidentals of a key signature, "F♯ C♯ G♯".
    return _(' ').join(pitch_name(name) for name in signature.accidentals)


class KeySignatures(ExerciseDefinition):
    id = 'keysig'
    item_prefix = 'keysig.'
    family = Family.NOTATION
    modality = Modality.EYE
    level = 1
    icon_name = 'keysig-symbolic'
    glyph = '♯'
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
            MAX_ACCIDENTALS,
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
    )

    @property
    def title(self) -> str:
        return _('Key Signatures')

    @property
    def description(self) -> str:
        return _('Name the major or minor key from its signature.')

    @property
    def play_label(self) -> str:
        return _('Play scale')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        clefs = [c for c in cast(Sequence[str], settings.get('clefs', ())) if c in _CLEFS]
        names = {
            'treble': _('Treble clef'),
            'bass': _('Bass clef'),
            'alto': _('Alto clef'),
            'tenor': _('Tenor clef'),
        }
        clef_text = names[clefs[0]] if len(clefs) == 1 else _('Mixed clefs')
        limit = _limit(settings)
        accidentals = ngettext('up to {n} accidental', 'up to {n} accidentals', limit).format(
            n=limit
        )
        return f'{clef_text} · {accidentals}'

    def item_label(self, item_id: ItemId) -> str:
        mode, fifths = parse_item(item_id)
        # Translators: an item in "Weakest items", e.g. "E major — key signature".
        return _('{key} — key signature').format(key=key_name(key_for(mode, fifths)))

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        """C first, then one more sharp and one more flat at a time."""
        limit = _limit(settings)
        order = [0] + [f for n in range(1, limit + 1) for f in (n, -n)]
        return [item_id(mode, fifths) for mode in _modes(settings) for fifths in order]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        mode, fifths = parse_item(item_id)
        limit = max(_limit(settings), abs(fifths))
        clefs = [c for c in cast(Sequence[str], settings.get('clefs', ())) if c in _CLEFS]
        clef = _CLEFS[rng.choice(clefs or ['treble'])]

        # C plus every signature with the same kind of accidental, in order.
        side = 1 if fifths > 0 else -1 if fifths < 0 else rng.choice((1, -1))
        signatures = [0] + [side * n for n in range(1, limit + 1)]
        options = tuple(
            Option(str(f), key_name(key_for(mode, f)), accel=str(i + 1) if i < 9 else None)
            for i, f in enumerate(signatures)
        )
        key = key_for(mode, fifths)
        prompt = (
            _('Which major key is written here?')
            if mode is Mode.MAJOR
            else _('Which minor key is written here?')
        )
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=prompt,
            answer=ChoiceAnswer(options),
            expected=str(fifths),
            figure=StaffSpec(clef=clef, key_signature=KeySignature(fifths)),
            playback=self._scale_playback(key),
            hint=self._hint(mode, fifths),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        expected = int(str(question.expected))
        mode = parse_item(question.item_id)[0]
        key = key_for(mode, expected)
        label = key_name(key)
        correct = str(given) == question.expected
        if correct:
            # Translators: e.g. "Correct — E major".
            title = _('Correct — {answer}').format(answer=label)
        else:
            # Translators: e.g. "Not quite — the answer is E major".
            title = _('Not quite — the answer is {answer}').format(answer=label)
        return Feedback(
            correct=correct,
            title=title,
            detail=self._explanation(mode, expected),
            expected_label=label,
            play_expected=question.playback,
        )

    def serialize(self, value: object) -> str:
        return str(value)

    # Explanations

    @staticmethod
    def _hint(mode: Mode, fifths: int) -> str:
        if fifths > 0:
            hint = _('The last sharp is the leading note: the major tonic is a semitone above it.')
        elif fifths < -1:
            hint = _('The second-to-last flat names the major key.')
        elif fifths == -1:
            hint = _('One flat, B♭, belongs to F major.')
        else:
            hint = _('No sharps or flats: C major or A minor.')
        if mode is Mode.MINOR and fifths != 0:
            hint = _('{hint} The relative minor is a minor third below.').format(hint=hint)
        return hint

    @staticmethod
    def _explanation(mode: Mode, fifths: int) -> str:
        signature = KeySignature(fifths)
        major = key_name(key_for(Mode.MAJOR, fifths))
        if fifths == 0:
            return _('No sharps or flats is the signature of C major and A minor.')
        names = _accidental_list(signature)
        count = signature.count
        if fifths > 0:
            last = pitch_name(signature.accidentals[-1])
            text = ngettext(
                '{count} sharp: {names}. The last sharp, {last}, is the leading note of {major}.',
                '{count} sharps: {names}. The last sharp, {last}, is the leading note of {major}.',
                count,
            ).format(count=count, names=names, last=last, major=major)
        elif fifths == -1:
            text = _('One flat: B♭. It is the signature of F major.')
        else:
            second_last = pitch_name(signature.accidentals[-2])
            text = ngettext(
                '{count} flat: {names}. The second-to-last flat, {flat}, names {major}.',
                '{count} flats: {names}. The second-to-last flat, {flat}, names {major}.',
                count,
            ).format(count=count, names=names, flat=second_last, major=major)
        if mode is Mode.MINOR:
            minor = key_name(key_for(Mode.MINOR, fifths))
            text = _('{text} Its relative minor, a minor third lower, is {minor}.').format(
                text=text, minor=minor
            )
        return text

    @staticmethod
    def _scale_playback(key: Key) -> PlaybackSpec:
        """The key's scale, up an octave, so eye and ear meet (dual coding)."""
        pitches: Sequence[Pitch] = key.scale.pitches(_SCALE_OCTAVE)
        if pitches and pitches[0].midi > 66:
            pitches = key.scale.pitches(_SCALE_OCTAVE - 1)
        return PlaybackSpec.melodic(pitches, note_length=Fraction(1, 2), tempo=100.0)


EXERCISES: tuple[ExerciseDefinition, ...] = (KeySignatures(),)
