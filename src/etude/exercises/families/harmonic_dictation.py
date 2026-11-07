# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Harmonic dictation: hear a four-part phrase and write the Roman numeral of each chord.

The phrase is a chorale of three to six chords from :mod:`etude.checkers.phrases`:
a diatonic phrase (:func:`~etude.checkers.phrases.diatonic_phrase`) or one that
prepares and resolves a chromatic chord (:func:`~etude.checkers.phrases.
chromatic_phrase`). The key and the first chord, always the tonic, are given; the
learner chooses a numeral for every further chord from one row of chips per chord,
as in the harmonic dictations of Kostka–Payne's workbook, without the figures:
``V7`` stands for V7, V6/5, V4/3 and V4/2, ``vii°7/V`` for any inversion,
``Cad6/4`` for the cadential six-four, ``N`` for the Neapolitan. A setting shows
the bass notes as well (the bass line given, as dictation books begin).

Items are ``harmonic.dictation.<mode>.<group>``: the diatonic phrases, the
secondary functions of V (V/V, V7/V, vii°7/V, viiø7/V), the other secondary
functions, mode mixture (major keys only), the Neapolitan sixth and the augmented
sixths. Each item has a fixed vocabulary, every numeral its phrases can contain
(:func:`vocabulary`), so the chips tell nothing about the phrase played.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from enum import Enum
from functools import cache
from gettext import gettext as _
from gettext import ngettext
from typing import ClassVar, cast

from ...checkers.phrases import (
    CHROMATIC_CHORDS,
    DIATONIC_PHRASES,
    ChromaticChord,
    ChromaticFamily,
    Phrase,
    diatonic_phrase,
    phrase_numerals,
)
from ...checkers.realize import RealisationError, Voicing
from ...checkers.voice_leading import BASS
from ...core import ChordKind, ChordQuality, RomanNumeral
from ...core.naming import key_name, pitch_name
from ...core.scale import Key, Mode
from ...learning.model import ItemId
from ..base import (
    BoolSetting,
    ChipGroup,
    ChipsAnswer,
    ExerciseDefinition,
    Family,
    Feedback,
    Modality,
    MultiChoiceSetting,
    Option,
    Question,
    Setting,
)
from .chromatic import phrase_for
from .four_part import (
    harmony_settings,
    mode_setting,
    phrase_figure,
    phrase_playback,
    pick_instrument,
    tempo_of,
)
from .harmony import (
    is_neapolitan,
    keys_within,
    limit_setting,
    modes_setting,
    roman_label,
    satb_voices,
)

PREFIX = 'harmonic.dictation.'
_KEY_ATTEMPTS = 6
_MAX_EXPLAINED = 3


class Group(Enum):
    """The chords an item's phrases are about."""

    DIATONIC = 'diatonic'
    SECONDARY_OF_V = 'secondary-v'
    SECONDARY = 'secondary'
    MIXTURE = 'mixture'
    NEAPOLITAN = 'neapolitan'
    AUGMENTED_SIXTH = 'augmented-sixth'


GROUPS: dict[Mode, tuple[Group, ...]] = {
    Mode.MAJOR: tuple(Group),
    Mode.MINOR: tuple(g for g in Group if g is not Group.MIXTURE),
}
"""In teaching order. Mode mixture borrows from minor, so it is a major-key group."""

_FAMILIES = {
    Group.SECONDARY_OF_V: ChromaticFamily.SECONDARY,
    Group.SECONDARY: ChromaticFamily.SECONDARY,
    Group.MIXTURE: ChromaticFamily.MIXTURE,
    Group.NEAPOLITAN: ChromaticFamily.NEAPOLITAN,
    Group.AUGMENTED_SIXTH: ChromaticFamily.AUGMENTED_SIXTH,
}

_CONFUSABLE = {
    Group.DIATONIC: (Group.SECONDARY_OF_V, Group.MIXTURE),
    Group.SECONDARY_OF_V: (Group.SECONDARY,),
    Group.SECONDARY: (Group.SECONDARY_OF_V,),
    Group.MIXTURE: (Group.DIATONIC,),
    Group.NEAPOLITAN: (Group.AUGMENTED_SIXTH,),
    Group.AUGMENTED_SIXTH: (Group.NEAPOLITAN,),
}


def group_name(group: Group) -> str:
    names: dict[Group, Callable[[], str]] = {
        Group.DIATONIC: lambda: _('Diatonic chords'),
        Group.SECONDARY_OF_V: lambda: _('Secondary dominants of V'),
        Group.SECONDARY: lambda: _('Other secondary dominants'),
        Group.MIXTURE: lambda: _('Mode mixture'),
        Group.NEAPOLITAN: lambda: _('Neapolitan sixth'),
        Group.AUGMENTED_SIXTH: lambda: _('Augmented sixths'),
    }
    return names[group]()


def group_chords(group: Group, mode: Mode) -> tuple[ChromaticChord, ...]:
    """The chromatic chords whose phrases an item plays (none for diatonic phrases)."""
    if group is Group.DIATONIC:
        return ()
    found = []
    for chord in CHROMATIC_CHORDS:
        if chord.family is not _FAMILIES[group] or chord.mode is not mode:
            continue
        if group in (Group.SECONDARY_OF_V, Group.SECONDARY):
            of_v = str(chord.numeral.secondary) == 'V'
            if of_v != (group is Group.SECONDARY_OF_V):
                continue
        found.append(chord)
    return tuple(found)


# Chips -------------------------------------------------------------------------------------

_SIXTHS = {
    ChordQuality.ITALIAN_SIXTH: 'It+6',
    ChordQuality.FRENCH_SIXTH: 'Fr+6',
    ChordQuality.GERMAN_SIXTH: 'Ger+6',
    ChordQuality.DOUBLY_AUGMENTED_FOURTH: 'Ger+6',
}


def chord_key(numeral: RomanNumeral) -> str:
    """The chip of a chord: the numeral without figures, ASCII. ``'V7'`` for V6/5,
    ``'viio7/V'``, ``'Cad64'``, ``'N'`` for N6, ``'Ger+6'`` for either spelling."""
    if numeral.cadential:
        return 'Cad64'
    if numeral.quality.kind is ChordKind.AUGMENTED_SIXTH:
        return _SIXTHS[numeral.quality]
    if is_neapolitan(numeral):
        return 'N'
    text = str(RomanNumeral(numeral.degree, numeral.quality, 0, numeral.alter))
    if numeral.secondary is not None:
        text += '/' + chord_key(numeral.secondary)
    return text


def chip_label(key: str) -> str:
    """``'vii°7/V'``, ``'Cad6/4'``, ``'♭VI'``."""
    return roman_label(RomanNumeral.parse(key))


def _order(key: str) -> tuple[int, float, int, str]:
    """Diatonic degrees first (the cadential six-four before V), then chromatic
    chords by degree, secondary functions by their target, augmented sixths last."""
    numeral = RomanNumeral.parse(key)
    if numeral.cadential:
        return (0, 4.5, 0, key)
    if numeral.quality.kind is ChordKind.AUGMENTED_SIXTH:
        return (3, 6, 0, key)
    if numeral.secondary is not None:
        return (2, numeral.secondary.degree, numeral.degree, key)
    return (0 if numeral.alter == 0 else 1, numeral.degree, numeral.alter, key)


@cache
def vocabulary(group: Group, mode: Mode) -> tuple[str, ...]:
    """Every chip of an item: the keys of all numerals its phrases can contain."""
    if group is Group.DIATONIC:
        numerals = {
            RomanNumeral.parse(t) for text in DIATONIC_PHRASES[mode] for t in text.split('-')
        }
    else:
        numerals = {n for chord in group_chords(group, mode) for n in phrase_numerals(chord)}
    return tuple(sorted({chord_key(n) for n in numerals}, key=_order))


# Items -------------------------------------------------------------------------------------


def dictation_item(mode: Mode, group: Group) -> ItemId:
    """``harmonic.dictation.minor.neapolitan``."""
    return ItemId(f'{PREFIX}{mode.value}.{group.value}')


def parse_item(item: str) -> tuple[Mode, Group]:
    if not item.startswith(PREFIX):
        raise ValueError(f'not a harmonic dictation item: {item!r}')
    mode_text, _sep, group_text = item.removeprefix(PREFIX).partition('.')
    mode, group = Mode(mode_text), Group(group_text)
    if group not in GROUPS[mode]:
        raise ValueError(f'no {group.value} dictation in {mode.value}')
    return mode, group


def _selected(settings: Mapping[str, object]) -> list[Group]:
    value = settings.get('groups', [g.value for g in Group])
    chosen = (
        {str(v) for v in cast(Sequence[object], value)} if not isinstance(value, str) else {value}
    )
    return [g for g in Group if g.value in chosen] or list(Group)


def _modes(settings: Mapping[str, object]) -> tuple[Mode, ...]:
    return modes_setting(settings, 'both')


def _describe_keys(settings: Mapping[str, object]) -> str:
    chosen = _modes(settings)
    if len(chosen) == 2:
        return _('Major and minor keys')
    return _('Minor keys') if chosen[0] is Mode.MINOR else _('Major keys')


def _limit(settings: Mapping[str, object]) -> int:
    return min(6, limit_setting(settings, 4))


def _diatonic_for(mode: Mode, limit: int, rng: random.Random) -> Phrase:
    keys = keys_within(limit, (mode,))
    for _attempt in range(_KEY_ATTEMPTS):
        try:
            return diatonic_phrase(rng.choice(keys), rng)
        except RealisationError:
            continue
    # C major and A minor always work (tests voice every phrase there).
    return diatonic_phrase(keys_within(0, (mode,))[0], rng)


def _labels(numerals: Sequence[RomanNumeral]) -> list[str]:
    return [roman_label(n) for n in numerals]


def _hint(group: Group) -> str:
    hints: dict[Group, Callable[[], str]] = {
        Group.DIATONIC: lambda: _(
            'Sing the bass first, then hear the chord above it: a bass that falls a fifth '
            '(or rises a fourth) into the next chord is often V–I.'
        ),
        Group.SECONDARY_OF_V: lambda: _(
            'A note that rises by half step to the root of V is its leading tone (♯4̂): the '
            'chord before V is then V/V or vii°/V.'
        ),
        Group.SECONDARY: lambda: _(
            'A raised note that rises by half step into the next chord is a leading tone: the '
            'chord before is a secondary dominant of that chord.'
        ),
        Group.MIXTURE: lambda: _(
            'Listen for the darker colour of ♭6̂ and ♭3̂ borrowed from the minor key: iv, ii°, '
            '♭VI, ♭III.'
        ),
        Group.NEAPOLITAN: lambda: _(
            'The Neapolitan is a major chord a half step above the tonic, usually over 4̂ in the '
            'bass, and leads to V.'
        ),
        Group.AUGMENTED_SIXTH: lambda: _(
            'An augmented sixth opens outwards to an octave on 5̂: listen for ♭6̂ falling by half '
            'step in the bass.'
        ),
    }
    return hints[group]()


class HarmonicDictation(ExerciseDefinition):
    id = 'harmonic-dictation'
    item_prefix = PREFIX
    family = Family.EAR
    modality = Modality.EAR
    level = 3
    icon_name = 'harmonic-dictation-symbolic'
    glyph = 'I–V/V'
    settings: ClassVar[tuple[Setting, ...]] = (
        mode_setting('both'),
        MultiChoiceSetting(
            'groups',
            _('Chords'),
            tuple(Option(g.value, group_name(g)) for g in Group),
            tuple(g.value for g in Group),
            subtitle=_('Mode mixture is asked in major keys only'),
        ),
        BoolSetting(
            'bass',
            _('Show the bass'),
            False,
            subtitle=_('Give the bass notes with the key, as dictation books begin'),
        ),
        *harmony_settings(tempo=60),
    )

    @property
    def title(self) -> str:
        return _('Harmonic Dictation')

    @property
    def description(self) -> str:
        return _('Hear a four-part phrase and write the Roman numeral of every chord.')

    @property
    def play_label(self) -> str:
        return _('Play phrase')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        parts = []
        groups = _selected(settings)
        if len(groups) < len(Group):
            # Translators: separator in a list of chord groups in an exercise subtitle.
            parts.append(_(', ').join(group_name(g) for g in groups))
        parts.append(_describe_keys(settings))
        if settings.get('bass', False) is True:
            parts.append(_('bass given'))
        # Translators: separator between the parts of an exercise subtitle.
        return _(' · ').join(parts)

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        groups = _selected(settings)
        found = [
            dictation_item(mode, group)
            for mode in _modes(settings)
            for group in GROUPS[mode]
            if group in groups
        ]
        # Mode mixture alone in minor keys: fall back to every group of the mode.
        return found or [dictation_item(mode, g) for mode in _modes(settings) for g in GROUPS[mode]]

    def item_label(self, item_id: ItemId) -> str:
        mode, group = parse_item(item_id)
        mode_word = _('major') if mode is Mode.MAJOR else _('minor')
        # Translators: an item in "Weakest items", e.g. "Neapolitan sixth (minor, dictation)".
        return _('{group} ({mode}, dictation)').format(group=group_name(group), mode=mode_word)

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        mode, group = parse_item(item_id)
        return [dictation_item(mode, g) for g in _CONFUSABLE[group] if g in GROUPS[mode]]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        mode, group = parse_item(item_id)
        limit = _limit(settings)
        if group is Group.DIATONIC:
            phrase = _diatonic_for(mode, limit, rng)
        else:
            phrase = phrase_for(rng.choice(group_chords(group, mode)), limit, rng)
        key = phrase.key
        numerals = [r[-1].numeral for r in phrase.readings]
        keys = [chord_key(n) for n in numerals]
        words = vocabulary(group, mode)
        options = tuple(Option(k, chip_label(k)) for k in words)
        groups = tuple(
            # Translators: the heading of a row of chips, e.g. "Chord 2".
            ChipGroup(str(i + 1), _('Chord {number}').format(number=i + 1), options)
            for i in range(1, len(numerals))
        )
        figure = phrase_figure(key, phrase.voicings)
        # Translators: e.g. "Key: G major · chord 1: I".
        context = _('Key: {key} · chord 1: {numeral}').format(
            key=key_name(key), numeral=chip_label(keys[0])
        )
        if settings.get('bass', False) is True:
            # Translators: added to the context of a dictation, e.g. "bass G–C♯–D–G".
            context = _(' · ').join(
                (context, _('bass {notes}').format(notes=_bass(phrase.voicings)))
            )
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Write the Roman numeral of each chord'),
            answer=ChipsAnswer(groups),
            expected={str(i + 1): keys[i] for i in range(1, len(keys))},
            figure=figure,
            playback=phrase_playback(
                phrase.voicings,
                tempo=tempo_of(settings, 60),
                instrument=pick_instrument(settings, rng),
            ),
            playback_is_question=True,
            playback_style_choice=False,
            written_alternative=figure,
            context=context,
            hint=_hint(group),
            details={
                'key': str(key),
                'numerals': '|'.join(str(n) for n in numerals),
                'first': keys[0],
            },
        )

    def grade(self, question: Question, given: object) -> Feedback:
        expected = cast(Mapping[str, str], question.expected)
        given_map = given if isinstance(given, Mapping) else {}
        wrong = [k for k, v in expected.items() if str(given_map.get(k, '')) != v]
        correct = not wrong
        key = Key.parse(question.details['key'])
        numerals = [RomanNumeral.parse(t) for t in question.details['numerals'].split('|')]
        labels = _labels(numerals)
        phrase_text = '–'.join(labels)
        if correct:
            # Translators: e.g. "Correct — I–V6/5/V–V–I".
            title = _('Correct — {answer}').format(answer=phrase_text)
        else:
            # Translators: e.g. "Not quite — the phrase is I–V6/5/V–V–I".
            title = _('Not quite — the phrase is {answer}').format(answer=phrase_text)
        voicings = satb_voices(question.written_alternative)
        sentences = [
            # Translators: e.g. "You heard I–V6/5/V–V–I in G major; the bass moves G–C♯–D–G."
            _('You heard {phrase} in {key}; the bass moves {bass}.').format(
                phrase=phrase_text, key=key_name(key), bass=_bass(voicings)
            )
        ]
        for slot in wrong[:_MAX_EXPLAINED]:
            index = int(slot) - 1
            chosen = str(given_map.get(slot, ''))
            # Translators: e.g. "Chord 3 is V6/5/V, not V7."
            sentences.append(
                _('Chord {number} is {right}, not {given}.').format(
                    number=slot,
                    right=labels[index],
                    given=chip_label(chosen) if chosen else '?',
                )
            )
        if len(wrong) > _MAX_EXPLAINED:
            more = len(wrong) - _MAX_EXPLAINED
            sentences.append(
                ngettext('And {n} more chord.', 'And {n} more chords.', more).format(n=more)
            )
        return Feedback(
            correct=correct,
            title=title,
            detail=' '.join(sentences),
            expected_label=phrase_text,
            score=1 - len(wrong) / len(expected),
            figure=phrase_figure(
                key, voicings, labels=labels, highlight=[int(k) - 1 for k in wrong]
            ),
            play_expected=question.playback,
        )

    def answer_label(self, question: Question, value: object) -> str:
        if isinstance(value, Mapping):
            first = chip_label(question.details['first'])
            chosen = [
                chip_label(str(value[k])) if k in value else '?'
                for k in sorted(cast(Mapping[str, str], question.expected), key=int)
            ]
            return '–'.join((first, *chosen))
        return super().answer_label(question, value)

    def serialize(self, value: object) -> str:
        if isinstance(value, Mapping):
            return ','.join(f'{k}={v}' for k, v in value.items())
        return str(value)


def _bass(voicings: Sequence[Voicing]) -> str:
    return '–'.join(pitch_name(v[BASS].name) for v in voicings)


EXERCISES: tuple[ExerciseDefinition, ...] = (HarmonicDictation(),)
