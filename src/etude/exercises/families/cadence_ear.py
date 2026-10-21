# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Cadences by ear: hear a short chorale phrase and name the cadence that ends it.

A phrase starts on the tonic, moves through a pre-dominant or another chord,
and ends with the cadence:

* **authentic** V(7)–I, split behind a setting into **perfect** (both chords
  in root position, the tonic in the soprano) and **imperfect** (the soprano
  ends on the third or fifth, or the dominant is inverted: V6–I, vii°6–I);
* **half**: the phrase stops on V;
* **plagal**: IV–I;
* **deceptive**: V(7)–vi (VI in minor);
* **Phrygian half** (minor, behind a setting): iv6–V, the bass falling a
  half step (the voicer does not promise that step, so a Phrygian phrase is
  voiced again until its bass falls by a semitone).

The phrases are fixed templates (below), voiced in four parts by
:func:`etude.checkers.realize.realize` in the question's key, so every
question is played with correct voice leading. Items are cadence types, ``cadence.ear.deceptive``;
the key, mode, opening, soprano and instrument vary. The written
alternative is the phrase on a grand staff; after answering, the Roman
numerals appear under it with the cadence highlighted.

Templates follow Kostka & Payne, *Tonal Harmony*, ch. 10 ("Cadences"), and
Laitz, *The Complete Musician*, ch. 11–12: an inverted dominant is preceded
by the tonic or a chord that avoids an augmented leap in the bass (no IV–V6).
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from gettext import gettext as _
from gettext import pgettext
from typing import ClassVar

from ...audio.spec import PlaybackSpec
from ...checkers.realize import Voicing
from ...core import PitchName
from ...core.naming import key_name
from ...core.roman import RomanNumeral
from ...core.scale import Key, Mode
from ...learning.model import ItemId
from ..base import (
    BoolSetting,
    ChoiceAnswer,
    ExerciseDefinition,
    Family,
    Feedback,
    Modality,
    Option,
    Question,
    Setting,
)
from .four_part import (
    describe_keys,
    harmony_settings,
    mode_setting,
    modes,
    parse_numerals,
    phrase_figure,
    phrase_playback,
    pick_instrument,
    pick_key,
    progression_label,
    tempo_of,
    voice,
)
from .harmony import roman_label, satb_voices

AUTHENTIC = 'authentic'
PERFECT = 'perfect-authentic'
IMPERFECT = 'imperfect-authentic'
HALF = 'half'
PLAGAL = 'plagal'
DECEPTIVE = 'deceptive'
PHRYGIAN = 'phrygian'
TYPES = (AUTHENTIC, PERFECT, IMPERFECT, HALF, PLAGAL, DECEPTIVE, PHRYGIAN)


@dataclass(frozen=True, slots=True)
class Phrase:
    opening: str
    """Numerals before the cadence, ``'I-ii6'``."""
    cadence: str
    """The cadence's numerals, ``'V7-I'``."""
    soprano_last: tuple[int, ...] = ()
    """Scale degrees the soprano may end on; empty means any."""

    @property
    def numerals(self) -> tuple[RomanNumeral, ...]:
        return parse_numerals(f'{self.opening}-{self.cadence}')

    @property
    def cadence_length(self) -> int:
        return self.cadence.count('-') + 1


def _phrases(
    openings: Sequence[str], cadences: Sequence[str], soprano: tuple[int, ...] = ()
) -> tuple[Phrase, ...]:
    return tuple(Phrase(o, c, soprano) for o in openings for c in cadences)


_PRE_DOMINANT = {
    Mode.MAJOR: ('I-IV', 'I-ii6', 'I-vi-IV', 'I-vi-ii6'),
    Mode.MINOR: ('i-iv', 'i-iio6', 'i-VI-iv', 'i-VI-iio6'),
}
_DOMINANT_TONIC = {Mode.MAJOR: ('V-I', 'V7-I'), Mode.MINOR: ('V-i', 'V7-i')}
_INVERTED_DOMINANT = {
    Mode.MAJOR: (Phrase('I', 'V6-I'), Phrase('I-vi', 'V6-I'), Phrase('I-IV', 'viio6-I')),
    Mode.MINOR: (Phrase('i', 'V6-i'), Phrase('i-iv', 'viio6-i'), Phrase('i-VI-iv', 'viio6-i')),
}


def phrases(kind: str, mode: Mode) -> tuple[Phrase, ...]:
    """The phrase templates of a cadence type in a mode (empty: not in this mode)."""
    pre = _PRE_DOMINANT[mode]
    if kind == AUTHENTIC:
        return phrases(PERFECT, mode) + phrases(IMPERFECT, mode)
    if kind == PERFECT:
        return _phrases(pre, _DOMINANT_TONIC[mode], (1,))
    if kind == IMPERFECT:
        return _phrases(pre, _DOMINANT_TONIC[mode], (3, 5)) + _INVERTED_DOMINANT[mode]
    if kind == HALF:
        return _phrases(pre, ('V',))
    if kind == PLAGAL:
        if mode is Mode.MAJOR:
            return _phrases(('I-vi', 'I-I6', 'I-V6-I'), ('IV-I',))
        return _phrases(('i-VI', 'i-i6', 'i-V6-i'), ('iv-i',))
    if kind == DECEPTIVE:
        if mode is Mode.MAJOR:
            return _phrases(pre, ('V-vi', 'V7-vi'))
        return _phrases(pre, ('V-VI', 'V7-VI'))
    if kind == PHRYGIAN:
        return _phrases(('i-VI', 'i-i6', 'i-iv'), ('iv6-V',)) if mode is Mode.MINOR else ()
    raise ValueError(f'not a cadence type: {kind!r}')


def realize(phrase: Phrase, key: Key, rng: random.Random) -> tuple[Voicing, ...]:
    """The phrase in four parts; a Phrygian cadence with its bass falling a half step."""
    return voice(
        key,
        phrase.numerals,
        rng,
        soprano_last=[key.scale.degree(d) for d in phrase.soprano_last],
        falling_bass=phrase.cadence.startswith('iv6'),
    )


# Words --------------------------------------------------------------------------


def type_label(kind: str) -> str:
    ctx = 'cadence type'
    return {
        AUTHENTIC: pgettext(ctx, 'Authentic'),
        PERFECT: pgettext(ctx, 'Perfect authentic'),
        IMPERFECT: pgettext(ctx, 'Imperfect authentic'),
        HALF: pgettext(ctx, 'Half'),
        PLAGAL: pgettext(ctx, 'Plagal'),
        DECEPTIVE: pgettext(ctx, 'Deceptive'),
        PHRYGIAN: pgettext(ctx, 'Phrygian half'),
    }[kind]


def type_name(kind: str) -> str:
    """The full name, "deceptive cadence"."""
    ctx = 'cadence'
    return {
        AUTHENTIC: pgettext(ctx, 'authentic cadence'),
        PERFECT: pgettext(ctx, 'perfect authentic cadence'),
        IMPERFECT: pgettext(ctx, 'imperfect authentic cadence'),
        HALF: pgettext(ctx, 'half cadence'),
        PLAGAL: pgettext(ctx, 'plagal cadence'),
        DECEPTIVE: pgettext(ctx, 'deceptive cadence'),
        PHRYGIAN: pgettext(ctx, 'Phrygian half cadence'),
    }[kind]


def _indefinite(kind: str) -> str:
    # Translators: cadence names as in "the answer is a half cadence". Languages
    # without articles use the bare name.
    ctx = 'cadence with article'
    return {
        AUTHENTIC: pgettext(ctx, 'an authentic cadence'),
        PERFECT: pgettext(ctx, 'a perfect authentic cadence'),
        IMPERFECT: pgettext(ctx, 'an imperfect authentic cadence'),
        HALF: pgettext(ctx, 'a half cadence'),
        PLAGAL: pgettext(ctx, 'a plagal cadence'),
        DECEPTIVE: pgettext(ctx, 'a deceptive cadence'),
        PHRYGIAN: pgettext(ctx, 'a Phrygian half cadence'),
    }[kind]


def _shape(kind: str) -> str:
    """The option's second line: the chords a cadence type ends with."""
    return {
        AUTHENTIC: _('V → I'),
        PERFECT: _('V → I, tonic on top'),
        IMPERFECT: _('V → I, not as final'),
        HALF: _('Ends on V'),
        PLAGAL: _('IV → I'),
        DECEPTIVE: _('V → vi'),
        PHRYGIAN: _('iv6 → V in minor'),
    }[kind]


def character(kind: str) -> str:
    return {
        AUTHENTIC: _(
            'An authentic cadence goes from the dominant to the tonic: it sounds finished.'
        ),
        PERFECT: _(
            'A perfect authentic cadence goes from V to I with both chords in root position '
            'and the tonic in the soprano: the most final ending.'
        ),
        IMPERFECT: _(
            'An imperfect authentic cadence also goes from the dominant to the tonic, but the '
            'soprano ends on the third or fifth, or a chord is inverted: it sounds a little '
            'less final.'
        ),
        HALF: _('A half cadence stops on the dominant: it sounds open, like a question.'),
        PLAGAL: _(
            'A plagal cadence goes from the subdominant to the tonic: the soft “Amen” ending.'
        ),
        DECEPTIVE: _(
            'A deceptive cadence goes from V to vi instead of I: you expect the tonic, and the '
            'music turns aside.'
        ),
        PHRYGIAN: _(
            'A Phrygian half cadence goes from iv6 to V in minor: the bass falls a half step '
            'to the dominant.'
        ),
    }[kind]


_CONFUSABLE: dict[str, tuple[str, ...]] = {
    AUTHENTIC: (DECEPTIVE, HALF),
    PERFECT: (IMPERFECT, DECEPTIVE),
    IMPERFECT: (PERFECT, HALF),
    HALF: (PHRYGIAN, IMPERFECT, AUTHENTIC),
    PLAGAL: (AUTHENTIC, PERFECT),
    DECEPTIVE: (AUTHENTIC, PERFECT),
    PHRYGIAN: (HALF,),
}


def item_id(kind: str) -> ItemId:
    """``cadence.ear.deceptive``."""
    return ItemId(f'cadence.ear.{kind}')


def parse_item(item: str) -> str:
    parts = item.split('.')
    if len(parts) != 3 or parts[:2] != ['cadence', 'ear'] or parts[2] not in TYPES:
        raise ValueError(f'not a cadence item: {item!r}')
    return parts[2]


def _pool(settings: Mapping[str, object]) -> list[str]:
    authentic = [PERFECT, IMPERFECT] if settings.get('authentic-kinds', False) else [AUTHENTIC]
    pool = [*authentic, HALF, PLAGAL, DECEPTIVE]
    if settings.get('phrygian', False):
        pool.append(PHRYGIAN)
    return pool


def _options(settings: Mapping[str, object], kind: str) -> list[str]:
    """The cadences offered: the pool, adjusted so that an item outside the settings
    (an older review) is answerable and unambiguous: "authentic" never appears next
    to "perfect" and "imperfect authentic"."""
    pool = set(_pool(settings)) | {kind}
    if kind == AUTHENTIC:
        pool -= {PERFECT, IMPERFECT}
    elif kind in (PERFECT, IMPERFECT):
        pool = (pool - {AUTHENTIC}) | {PERFECT, IMPERFECT}
    return [k for k in TYPES if k in pool]


def _degree(key: Key, name: PitchName) -> int | None:
    degree = key.scale.degree_of(name)
    if degree is None and name == key.leading_tone:
        return 7
    return degree


class CadenceEar(ExerciseDefinition):
    id = 'cadence-ear'
    item_prefix = 'cadence.ear.'
    family = Family.EAR
    modality = Modality.EAR
    level = 2
    icon_name = 'cadence-ear-symbolic'
    glyph = 'V–I'
    settings: ClassVar[tuple[Setting, ...]] = (
        mode_setting(),
        BoolSetting(
            'authentic-kinds',
            _('Perfect and imperfect'),
            False,
            subtitle=_('Tell perfect authentic cadences from imperfect ones'),
        ),
        BoolSetting(
            'phrygian',
            _('Phrygian half cadence'),
            False,
            subtitle=_('iv6–V in minor keys'),
        ),
        *harmony_settings(),
    )

    @property
    def title(self) -> str:
        return _('Cadences — Ear')

    @property
    def description(self) -> str:
        return _('Hear how a phrase ends: authentic, half, plagal or deceptive.')

    @property
    def play_label(self) -> str:
        return _('Play phrase')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        kinds = (
            _('perfect and imperfect')
            if settings.get('authentic-kinds', False)
            else _('four cadences')
        )
        return _(' · ').join((describe_keys(settings), kinds))

    def item_label(self, item_id: ItemId) -> str:
        name = type_name(parse_item(item_id))
        # Translators: an item in "Weakest items", e.g. "Deceptive cadence (ear)".
        text = _('{cadence} (ear)').format(cadence=name)
        return text[:1].upper() + text[1:]

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        return [item_id(k) for k in _pool(settings)]

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        return [ItemId(f'cadence.ear.{k}') for k in _CONFUSABLE[parse_item(item_id)]]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        kind = parse_item(item_id)
        allowed = modes(settings)
        mode = Mode.MINOR if kind == PHRYGIAN else rng.choice(allowed)
        key = pick_key(mode, settings, rng)
        phrase = rng.choice(phrases(kind, mode))
        voicings = realize(phrase, key, rng)
        figure = phrase_figure(key, voicings)
        playback = phrase_playback(
            voicings, tempo=tempo_of(settings), instrument=pick_instrument(settings, rng)
        )
        pool = _options(settings, kind)
        options = tuple(Option(k, type_label(k), str(i + 1), _shape(k)) for i, k in enumerate(pool))
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Which cadence ends the phrase?'),
            answer=ChoiceAnswer(options),
            expected=kind,
            figure=figure,
            playback=playback,
            playback_is_question=True,
            playback_style_choice=False,
            written_alternative=figure,
            # Translators: the key of a question, e.g. "Key: D major".
            context=_('Key: {key}').format(key=key_name(key)),
            hint=_(
                'Listen to the last two chords: does the phrase come home, stop open or turn aside?'
            ),
            details={'key': str(key), 'opening': phrase.opening, 'cadence': phrase.cadence},
        )

    def grade(self, question: Question, given: object) -> Feedback:
        kind = str(question.expected)
        voicings = satb_voices(question.written_alternative)
        key = Key.parse(question.details['key'])
        phrase = Phrase(question.details['opening'], question.details['cadence'])
        numerals = phrase.numerals
        correct = str(given) == kind
        label = self.answer_label(question, kind)
        if correct:
            # Translators: e.g. "Correct — deceptive cadence".
            title = _('Correct — {answer}').format(answer=label)
        else:
            # Translators: e.g. "Not quite — the answer is a half cadence"; {answer}
            # already has its article.
            title = _('Not quite — the answer is {answer}').format(answer=_indefinite(kind))
        count = len(voicings)
        start = count - phrase.cadence_length
        if phrase.cadence_length == 1:
            # Translators: e.g. "Here the phrase stops on V in D major."
            ending = _('Here the phrase stops on {chords} in {key}.')
        else:
            # Translators: e.g. "Here the phrase ends V7–vi in D major."
            ending = _('Here the phrase ends {chords} in {key}.')
        sentences = [
            character(kind),
            ending.format(chords=progression_label(numerals[start:]), key=key_name(key)),
        ]
        soprano = _degree(key, voicings[-1][0].name)
        if kind in (PERFECT, IMPERFECT, AUTHENTIC) and soprano is not None:
            # Translators: e.g. "The soprano ends on scale degree 3."
            sentences.append(_('The soprano ends on scale degree {degree}.').format(degree=soprano))
        play_given = None
        if not correct and str(given) in TYPES:
            other = str(given)
            # Translators: e.g. "For comparison: A half cadence stops on the dominant …".
            sentences.append(_('For comparison: {text}').format(text=character(other)))
            play_given = self._comparison(question, key, phrase, other)
        figure = phrase_figure(
            key,
            voicings,
            labels=[roman_label(n) for n in numerals],
            highlight=range(start, count),
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
        if str(value) not in TYPES:
            return super().answer_label(question, value)
        return type_name(str(value))

    @staticmethod
    def _comparison(
        question: Question, key: Key, phrase: Phrase, other: str
    ) -> PlaybackSpec | None:
        """The learner's cadence in the same key, after the same opening when it can."""
        if not phrases(other, key.mode):
            key = Key(key.tonic, Mode.MINOR)
        candidates = phrases(other, key.mode)
        opening = phrase.opening.split('-')

        def shared(candidate: Phrase) -> int:
            count = 0
            for a, b in zip(candidate.opening.split('-'), opening, strict=False):
                if a != b:
                    break
                count += 1
            return count

        voicings = realize(max(candidates, key=shared), key, random.Random(0))
        playback = question.playback
        assert playback is not None
        return phrase_playback(voicings, tempo=playback.tempo, instrument=playback.instrument)


EXERCISES: tuple[ExerciseDefinition, ...] = (CadenceEar(),)
