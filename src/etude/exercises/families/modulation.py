# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Modulation and sequences: read where a four-part phrase goes and how.

*Modulation* shows a phrase that leaves its key (from
:func:`etude.checkers.phrases.modulation`) with the home key's signature
throughout, as chorales are written, and asks either for the **new key**, each
option a key with its relation to the home key (G major, "V · dominant"), or for
the **pivot chord** of a pivot-chord modulation: the options are the chords in
the order of the figure, and clicking a chord on the staff picks it. The feedback
shows the analysis on two levels, as Kostka–Payne write it: the home key's
numerals up to the pivot, the new key's from the pivot on.

Items: ``modulation.key.<mode>.<technique>.<relation>`` for pivot-chord, direct
and common-tone modulations (``modulation.key.major.pivot.V``,
``modulation.key.major.common-tone.bVI``), ``modulation.key.<mode>.<technique>``
for the enharmonic ones (``enharmonic-dim7``, ``enharmonic-ger6``; a setting
turns them on), and ``modulation.pivot.<mode>.<relation>`` for finding the pivot.
Modulations from a minor key to its relative major are left out of the pivot
questions: the new key has no note the old one lacks, so the pivot cannot be told
from the chords before it.

*Sequences* shows a diatonic or chromatic sequence (from
:func:`etude.checkers.phrases.sequence`) and asks which: descending fifths,
descending fifths with secondary dominants, descending 5–6 (descending thirds) or
ascending 5–6. Items are ``sequence.<mode>.<kind>``.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from functools import cache
from gettext import gettext as _
from gettext import ngettext, pgettext
from typing import ClassVar, cast

from ...audio.spec import PlaybackSpec
from ...checkers.phrases import (
    CLOSELY_RELATED,
    SEQUENCES,
    Phrase,
    SequenceKind,
    Technique,
    enharmonic_keys,
    key_relation,
    modulation,
    modulation_targets,
    neapolitan_key,
    pivot_is_marked,
    related_key,
    sequence,
)
from ...checkers.realize import RealisationError, Voicing
from ...core import PitchName
from ...core.naming import key_name, pitch_name
from ...core.scale import Key, Mode
from ...learning.model import ItemId
from ...notation.spec import Barline, BarStyle, SystemSpec
from ...notation.spec import Chord as StaffChord
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
    Setting,
)
from .chromatic import phrase_durations, phrase_lengths, voices_description
from .harmony import (
    keys_within,
    limit_setting,
    modes_setting,
    progression_playback,
    roman_label,
    satb_voices,
)
from .harmony import satb_figure as _satb_figure

MAX_ACCIDENTALS = 5
_KEY_ATTEMPTS = 6


def _limit(settings: Mapping[str, object]) -> int:
    return min(MAX_ACCIDENTALS, limit_setting(settings, 3))


def _modes(settings: Mapping[str, object]) -> tuple[Mode, ...]:
    return modes_setting(settings, 'both')


def _mode_settings() -> tuple[Setting, ...]:
    return (
        ChoiceSetting(
            'mode',
            _('Home keys'),
            (
                Option('major', _('Major keys')),
                Option('minor', _('Minor keys')),
                Option('both', _('Major and minor')),
            ),
            'both',
        ),
        IntSetting(
            'max-accidentals',
            _('Most accidentals'),
            3,
            0,
            MAX_ACCIDENTALS,
            subtitle=_('Largest number of sharps or flats in the home key signature'),
        ),
    )


def _describe_keys(settings: Mapping[str, object]) -> list[str]:
    modes = _modes(settings)
    if modes == (Mode.MAJOR,):
        parts = [_('Major keys')]
    elif modes == (Mode.MINOR,):
        parts = [_('Minor keys')]
    else:
        parts = [_('Major and minor')]
    limit = _limit(settings)
    parts.append(ngettext('up to {n} accidental', 'up to {n} accidentals', limit).format(n=limit))
    return parts


def relation_label(relation: str) -> str:
    """``'bVI'`` → ``'♭VI'``."""
    return relation.replace('b', '♭').replace('#', '♯')


def relation_name(home: Key, relation: str) -> str | None:
    """The name of a closely related key's relation: "dominant", "relative minor" …"""
    names: dict[tuple[Mode, str], Callable[[], str]] = {
        (Mode.MAJOR, 'V'): lambda: _('dominant'),
        (Mode.MAJOR, 'IV'): lambda: _('subdominant'),
        (Mode.MAJOR, 'vi'): lambda: _('relative minor'),
        (Mode.MAJOR, 'ii'): lambda: _('supertonic'),
        (Mode.MAJOR, 'iii'): lambda: _('mediant'),
        (Mode.MINOR, 'III'): lambda: _('relative major'),
        (Mode.MINOR, 'v'): lambda: _('dominant'),
        (Mode.MINOR, 'iv'): lambda: _('subdominant'),
        (Mode.MINOR, 'VI'): lambda: _('submediant'),
        (Mode.MINOR, 'VII'): lambda: _('subtonic'),
        (Mode.MAJOR, 'bII'): lambda: _('Neapolitan'),
        (Mode.MINOR, 'bII'): lambda: _('Neapolitan'),
    }
    found = names.get((home.mode, relation))
    if found is not None:
        return found()
    if relation in ('III', 'bIII', 'VI', 'bVI'):
        return _('chromatic mediant')
    return None


def relation_text(home: Key, relation: str) -> str:
    """``'V · dominant'``, ``'♭VI · chromatic mediant'``, ``'♯iv'``."""
    name = relation_name(home, relation)
    label = relation_label(relation)
    # Translators: a key's relation to the home key, e.g. "V · dominant".
    return _('{numeral} · {name}').format(numeral=label, name=name) if name else label


def _technique_name(technique: Technique) -> str:
    names: dict[Technique, Callable[[], str]] = {
        Technique.PIVOT: lambda: _('Pivot chord'),
        Technique.DIRECT: lambda: _('Direct (phrase) modulation'),
        Technique.COMMON_TONE: lambda: _('Common tone'),
        Technique.ENHARMONIC_DIMINISHED: lambda: _('Enharmonic, through vii°7'),
        Technique.ENHARMONIC_GERMAN: lambda: _('Enharmonic, through Ger+6'),
    }
    return names[technique]()


# Figures -------------------------------------------------------------------------------


def phrase_figure(
    phrase: Phrase,
    *,
    labels: Sequence[str | None] = (),
    highlight: Sequence[int] = (),
    description: str,
) -> SystemSpec:
    """The phrase on a grand staff in the home key's signature, a double bar at its
    phrase breaks."""
    count = len(phrase.voicings)
    return _satb_figure(
        phrase.voicings,
        phrase.key.signature,
        durations=phrase_durations(count),
        labels=labels,
        highlight=highlight,
        final_bar=True,
        description=description,
        breaks=phrase.breaks,
    )


def phrase_playback(phrase: Phrase) -> PlaybackSpec:
    return progression_playback(phrase.voicings, phrase_lengths(len(phrase.voicings)), 72.0)


def chord_events(figure: SystemSpec) -> dict[int, int]:
    """Event index (any voice, either staff) → chord index, for clicking a chord."""
    found: dict[int, int] = {}
    staff = figure.staves[0]
    offset = 0
    for line in (staff.events, *staff.voices):
        chord = 0
        for index, event in enumerate(line):
            if isinstance(event, StaffChord):
                found[offset + index] = chord
                chord += 1
        offset += len(line)
    return found


def analysis_labels(phrase: Phrase) -> list[str]:
    """Two-level analysis: the home key's numerals up to the pivot, the new key's from
    the pivot (or the phrase break) on; a pivot gets both, one above the other."""
    labels = []
    for readings in phrase.readings:
        texts = [roman_label(r.numeral) for r in readings]
        if len(texts) == 1 and phrase.new_key is not None and readings[0].key == phrase.new_key:
            texts = ['', texts[0]]
        labels.append('\n'.join(texts))
    return labels


def _analysis_text(phrase: Phrase) -> str:
    """ "C major: I – V – I – vi; G major: ii – V – I"."""
    old: list[str] = []
    new: list[str] = []
    for readings in phrase.readings:
        for reading in readings:
            (new if reading.key == phrase.new_key else old).append(roman_label(reading.numeral))
    parts = [_('{key}: {numerals}').format(key=key_name(phrase.key), numerals=' – '.join(old))]
    if phrase.new_key is not None:
        parts.append(
            _('{key}: {numerals}').format(key=key_name(phrase.new_key), numerals=' – '.join(new))
        )
    # Translators: separator between the two keys of an analysis.
    return _('; ').join(parts)


# Modulation -----------------------------------------------------------------------------

_CONFUSABLE_RELATIONS = {
    'V': 'IV',
    'IV': 'V',
    'vi': 'iii',
    'iii': 'vi',
    'ii': 'vi',
    'III': 'VI',
    'VI': 'III',
    'v': 'iv',
    'iv': 'v',
    'VII': 'III',
    'bVI': 'VI',
    'bIII': 'III',
}
"""Keys learners mix up: the dominant and subdominant, the two mediants …"""
_KEY_TECHNIQUES = (Technique.PIVOT, Technique.DIRECT, Technique.COMMON_TONE)
_ENHARMONIC = (Technique.ENHARMONIC_DIMINISHED, Technique.ENHARMONIC_GERMAN)
_TECHNIQUE_SETTINGS = ('pivot', 'direct', 'common-tone', 'enharmonic')


def _techniques(settings: Mapping[str, object]) -> set[str]:
    chosen = settings.get('techniques', ('pivot', 'direct', 'common-tone'))
    values = set(cast(Sequence[str], chosen)) if isinstance(chosen, list | tuple) else set()
    return (values & set(_TECHNIQUE_SETTINGS)) or {'pivot'}


def _questions(settings: Mapping[str, object]) -> set[str]:
    chosen = settings.get('questions', ('key', 'pivot'))
    values = set(cast(Sequence[str], chosen)) if isinstance(chosen, list | tuple) else set()
    return (values & {'key', 'pivot'}) or {'key'}


@cache
def _relations(mode: Mode, technique: Technique) -> tuple[str, ...]:
    if technique is Technique.COMMON_TONE:
        return modulation_targets(Key(PitchName.parse('C'), mode), technique)
    return CLOSELY_RELATED[mode]


@cache
def _pivot_relations(mode: Mode) -> tuple[str, ...]:
    home = Key(PitchName.parse('C'), mode)
    return tuple(r for r in CLOSELY_RELATED[mode] if pivot_is_marked(home, related_key(home, r)))


def _parse_modulation_item(item: str) -> tuple[str, Mode, Technique | None, str | None]:
    """(question, mode, technique, relation); the pivot question has no technique."""
    parts = item.split('.')
    if len(parts) < 4 or parts[0] != 'modulation' or parts[2] not in ('major', 'minor'):
        raise ValueError(f'not a modulation item: {item!r}')
    mode = Mode(parts[2])
    if parts[1] == 'pivot' and len(parts) == 4 and parts[3] in _pivot_relations(mode):
        return 'pivot', mode, Technique.PIVOT, parts[3]
    if parts[1] == 'key':
        technique = Technique(parts[3])
        if technique in _ENHARMONIC and len(parts) == 4:
            return 'key', mode, technique, None
        if (
            technique in _KEY_TECHNIQUES
            and len(parts) == 5
            and parts[4] in _relations(mode, technique)
        ):
            return 'key', mode, technique, parts[4]
    raise ValueError(f'not a modulation item: {item!r}')


def _key_options(home: Key, technique: Technique, new: Key) -> list[tuple[str, Key]]:
    """(relation, key) of every option of a "which key" question."""
    if technique in (Technique.PIVOT, Technique.DIRECT):
        keys = [related_key(home, r) for r in CLOSELY_RELATED[home.mode]]
    elif technique is Technique.COMMON_TONE:
        keys = [related_key(home, r) for r in modulation_targets(home, technique)]
    elif technique is Technique.ENHARMONIC_DIMINISHED:
        keys = list(enharmonic_keys(home))
    else:
        dominant = Key(home.degree(5), Mode.MAJOR)
        submediant = related_key(home, 'bVI' if home.mode is Mode.MAJOR else 'VI')
        keys = [neapolitan_key(home), submediant, dominant, Key(home.degree(4), Mode.MINOR)]
    if new not in keys:  # pragma: no cover - the generators reach only these keys
        keys.append(new)
    return [(key_relation(home, k), k) for k in keys]


class Modulation(ExerciseDefinition):
    id = 'modulation'
    item_prefix = 'modulation.'
    family = Family.HARMONY
    modality = Modality.EYE
    level = 3
    icon_name = 'modulation-symbolic'
    glyph = '→'
    settings: ClassVar[tuple[Setting, ...]] = (
        *_mode_settings(),
        MultiChoiceSetting(
            'techniques',
            _('Modulations'),
            (
                Option('pivot', _('Pivot chord')),
                Option('direct', _('Direct (phrase) modulation')),
                Option('common-tone', _('Common tone (major keys)')),
                Option('enharmonic', _('Enharmonic: vii°7 and Ger+6')),
            ),
            ('pivot', 'direct', 'common-tone'),
        ),
        MultiChoiceSetting(
            'questions',
            _('Questions'),
            (
                Option('key', _('Name the new key')),
                Option('pivot', _('Find the pivot chord')),
            ),
            ('key', 'pivot'),
        ),
    )

    @property
    def title(self) -> str:
        return _('Modulation')

    @property
    def description(self) -> str:
        return _('Name the key a phrase modulates to, and find its pivot chord.')

    @property
    def play_label(self) -> str:
        return _('Play phrase')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        return _(' · ').join(_describe_keys(settings))

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        techniques = _techniques(settings)
        questions = _questions(settings)
        modes = _modes(settings)
        found: list[ItemId] = []
        if 'key' in questions:
            for technique in _KEY_TECHNIQUES:
                if technique.value not in techniques:
                    continue
                for mode in modes:
                    for relation in _relations(mode, technique):
                        found.append(
                            ItemId(f'modulation.key.{mode.value}.{technique.value}.{relation}')
                        )
            if 'enharmonic' in techniques:
                found += [
                    ItemId(f'modulation.key.{mode.value}.{technique.value}')
                    for technique in _ENHARMONIC
                    for mode in modes
                ]
        if 'pivot' in questions and 'pivot' in techniques:
            found += [
                ItemId(f'modulation.pivot.{mode.value}.{relation}')
                for mode in modes
                for relation in _pivot_relations(mode)
            ]
        if not found:  # minor keys and common tones only, or the pivot alone without it
            found = [
                ItemId(f'modulation.key.{mode.value}.pivot.{relation}')
                for mode in modes
                for relation in CLOSELY_RELATED[mode]
            ]
        return found

    def item_label(self, item_id: ItemId) -> str:
        question, mode, technique, relation = _parse_modulation_item(item_id)
        assert technique is not None
        mode_word = pgettext('mode', 'major') if mode is Mode.MAJOR else pgettext('mode', 'minor')
        if question == 'pivot':
            assert relation is not None
            # Translators: an item in "Weakest items", e.g. "Pivot chord to V from major".
            return _('Pivot chord to {relation} from {mode}').format(
                relation=relation_label(relation), mode=mode_word
            )
        if relation is None:
            # Translators: e.g. "Enharmonic, through vii°7, from minor".
            return _('{technique}, from {mode}').format(
                technique=_technique_name(technique), mode=mode_word
            )
        # Translators: e.g. "Pivot chord: to V from major".
        return _('{technique}: to {relation} from {mode}').format(
            technique=_technique_name(technique), relation=relation_label(relation), mode=mode_word
        )

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        question, mode, technique, relation = _parse_modulation_item(item_id)
        if question != 'key' or technique is None or relation is None:
            return []
        partner = _CONFUSABLE_RELATIONS.get(relation)
        if not partner or partner not in _relations(mode, technique):
            return []
        return [ItemId(f'modulation.key.{mode.value}.{technique.value}.{partner}')]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        question, mode, technique, relation = _parse_modulation_item(item_id)
        assert technique is not None
        phrase = _modulation_phrase(mode, technique, relation, _limit(settings), rng)
        home = phrase.key
        new = phrase.new_key
        assert new is not None
        details = {'home': str(home), 'new': str(new), 'technique': technique.value}
        if phrase.pivot is not None:
            details['pivot'] = str(phrase.pivot)
        # One label per chord; a pivot's two lines stay separated by a line break.
        details['labels'] = '|'.join(analysis_labels(phrase))
        details['analysis'] = _analysis_text(phrase)
        count = len(phrase.voicings)
        playback = phrase_playback(phrase)
        if question == 'pivot':
            assert phrase.pivot is not None
            figure = phrase_figure(
                phrase,
                description=_(
                    'Grand staff, beginning in {home} and ending in {new}, {n} chords. {voices}.'
                ).format(
                    home=key_name(home),
                    new=key_name(new),
                    n=count,
                    voices=voices_description(phrase.voicings),
                ),
            )
            options = tuple(
                Option(
                    str(i),
                    # Translators: an answer button naming a chord by its place, "Chord 3".
                    _('Chord {n}').format(n=i + 1),
                    accel=str(i + 1) if i < 9 else None,
                    fixed_accel=True,
                )
                for i in range(1, count - 1)
            )
            targets = {e: str(c) for e, c in chord_events(figure).items() if 0 < c < count - 1}
            return Question(
                exercise_id=self.id,
                item_id=item_id,
                prompt=_('Which chord is the pivot?'),
                answer=ChoiceAnswer(options, targets=targets, in_figure_order=True),
                expected=str(phrase.pivot),
                figure=figure,
                playback=playback,
                # Translators: e.g. "C major → G major".
                context=_('{home} → {new}').format(home=key_name(home), new=key_name(new)),
                details=details,
                hint=_(
                    'Find the first chord with a note the home key does not have; the pivot '
                    'is the chord just before it, a chord both keys share.'
                ),
            )
        options = tuple(
            Option(rel, key_name(key), accel=str(i + 1), description=relation_text(home, rel))
            for i, (rel, key) in enumerate(_key_options(home, technique, new))
        )
        figure = phrase_figure(
            phrase,
            description=_('Grand staff in {home}, {n} chords. {voices}.').format(
                home=key_name(home), n=count, voices=voices_description(phrase.voicings)
            ),
        )
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Which key does the phrase modulate to?'),
            answer=ChoiceAnswer(options),
            expected=key_relation(home, new),
            figure=figure,
            playback=playback,
            # Translators: e.g. "Begins in C major".
            context=_('Begins in {key}').format(key=key_name(home)),
            details=details,
            hint=_(
                'Look at the last chords: the cadence names the new key. Accidentals that '
                'are not in the key signature show which notes changed.'
            ),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        expected = str(question.expected)
        correct = str(given) == expected
        details = question.details
        home, new = Key.parse(details['home']), Key.parse(details['new'])
        technique = Technique(details['technique'])
        figure = question.figure
        assert isinstance(figure, SystemSpec)
        voicings = _voicings_of(figure)
        labels = details['labels'].split('|')
        pivot = int(details['pivot']) if 'pivot' in details else None
        if isinstance(question.answer, ChoiceAnswer) and question.answer.in_figure_order:
            label = _('Chord {n}').format(n=int(expected) + 1)
        else:
            label = key_name(new)
        if correct:
            title = _('Correct — {answer}').format(answer=label)
        else:
            title = _('Not quite — the answer is {answer}').format(answer=label)
        # Translators: the Roman numeral analysis of a phrase, e.g. "Analysis: C major: I –
        # V – I – vi; G major: ii – V – I."
        analysis = _('Analysis: {analysis}.').format(analysis=details['analysis'])
        detail = f'{_explain_modulation(home, new, technique, pivot)} {analysis}'
        answer_figure = _satb_figure(
            voicings,
            home.signature,
            durations=phrase_durations(len(voicings)),
            labels=labels,
            highlight=(pivot,) if pivot is not None else (),
            final_bar=True,
            breaks=_breaks_of(figure),
            description=_('Grand staff, analysed: {analysis}. {voices}.').format(
                analysis=details['analysis'], voices=voices_description(voicings)
            ),
        )
        return Feedback(
            correct=correct,
            title=title,
            detail=detail,
            expected_label=label,
            figure=answer_figure,
            play_expected=question.playback,
        )


def _voicings_of(figure: SystemSpec) -> list[Voicing]:
    return satb_voices(figure)


def _breaks_of(figure: SystemSpec) -> tuple[int, ...]:
    breaks = []
    chord = -1
    for event in figure.staves[0].events:
        if isinstance(event, StaffChord):
            chord += 1
        elif isinstance(event, Barline) and chord >= 0 and event.style is BarStyle.DOUBLE:
            breaks.append(chord)
    return tuple(breaks)


def _modulation_phrase(
    mode: Mode, technique: Technique, relation: str | None, limit: int, rng: random.Random
) -> Phrase:
    homes = keys_within(limit, (mode,))
    for _attempt in range(_KEY_ATTEMPTS):
        home = rng.choice(homes)
        targets = modulation_targets(home, technique)
        target = relation if relation is not None else rng.choice(targets)
        new = related_key(home, target)
        if new.is_theoretical:
            continue
        try:
            return modulation(home, technique, target, rng)
        except RealisationError:
            continue
    home = keys_within(0, (mode,))[0]
    target = relation if relation is not None else modulation_targets(home, technique)[0]
    return modulation(home, technique, target, rng)


def _explain_modulation(
    home: Key,
    new: Key,
    technique: Technique,
    pivot: int | None,
) -> str:
    relation = key_relation(home, new)
    first = _('The phrase moves from {home} to {new}, {relation}').format(
        home=key_name(home), new=key_name(new), relation=relation_text(home, relation)
    )
    if technique is Technique.PIVOT and pivot is not None:
        return (
            first
            + '. '
            + _(
                'Chord {n} is the pivot: a chord both keys share, the last one before the new '
                "key's accidentals appear."
            ).format(n=pivot + 1)
        )
    if technique is Technique.DIRECT:
        return (
            first
            + '. '
            + _(
                'A direct (phrase) modulation: the first phrase ends with a cadence in the home '
                'key, and the next one begins in the new key without a pivot.'
            )
        )
    if technique is Technique.COMMON_TONE:
        return (
            first
            + '. '
            + _(
                'A common-tone modulation: the note the two tonic triads share is held in the '
                'soprano while the harmony moves to the new key.'
            )
        )
    assert pivot is not None
    if technique is Technique.ENHARMONIC_DIMINISHED:
        return (
            first
            + '. '
            + _(
                'Chord {n} is an enharmonic pivot: the diminished seventh of the home key, '
                'respelled as vii°7 of the new key. Any note of a diminished seventh chord can '
                'become the leading tone.'
            ).format(n=pivot + 1)
        )
    return (
        first
        + '. '
        + _(
            'Chord {n} is an enharmonic pivot: the German sixth of the home key sounds like a '
            'dominant seventh, and resolves as V7 of the new key.'
        ).format(n=pivot + 1)
    )


# Sequences --------------------------------------------------------------------------------


def _sequence_name(kind: SequenceKind) -> str:
    names: dict[SequenceKind, Callable[[], str]] = {
        SequenceKind.DESCENDING_FIFTHS: lambda: _('Descending fifths'),
        SequenceKind.SECONDARY_DOMINANTS: lambda: _('Descending fifths with secondary dominants'),
        SequenceKind.DESCENDING_FIVE_SIX: lambda: _('Descending 5–6 (descending thirds)'),
        SequenceKind.ASCENDING_FIVE_SIX: lambda: _('Ascending 5–6'),
    }
    return names[kind]()


def _sequence_explanation(kind: SequenceKind, phrase: Phrase) -> str:
    roots = [pitch_name(r[-1].chord.root) for r in phrase.readings]
    bass = [pitch_name(v[3].name) for v in phrase.voicings]
    if kind is SequenceKind.DESCENDING_FIFTHS:
        return _('Each root is a fifth below the one before (a fourth above): {roots}.').format(
            roots='–'.join(roots)
        )
    if kind is SequenceKind.SECONDARY_DOMINANTS:
        return _(
            'Each chord is a dominant seventh of the next, its roots falling by fifths: '
            '{roots}. Each leading tone falls by a half step to become the next seventh.'
        ).format(roots='–'.join(roots))
    if kind is SequenceKind.DESCENDING_FIVE_SIX:
        return _(
            'The bass falls by step, {bass}, with a fifth and then a sixth above each pair: '
            'root position, then first inversion. The root-position chords fall by thirds.'
        ).format(bass='–'.join(bass))
    return _(
        'The bass rises by step, {bass}; over each bass note a fifth moves to a sixth: '
        'root position, then first inversion of the chord a third below.'
    ).format(bass='–'.join(bass))


def _parse_sequence_item(item: str) -> tuple[Mode, SequenceKind]:
    parts = item.split('.')
    if len(parts) != 3 or parts[0] != 'sequence' or parts[1] not in ('major', 'minor'):
        raise ValueError(f'not a sequence item: {item!r}')
    mode = Mode(parts[1])
    kind = SequenceKind(parts[2])
    if mode not in SEQUENCES[kind]:
        raise ValueError(f'not a sequence item: {item!r}')
    return mode, kind


class Sequences(ExerciseDefinition):
    id = 'sequences'
    item_prefix = 'sequence.'
    family = Family.HARMONY
    modality = Modality.EYE
    level = 3
    icon_name = 'sequences-symbolic'
    glyph = '⤵'
    settings: ClassVar[tuple[Setting, ...]] = _mode_settings()

    @property
    def title(self) -> str:
        return _('Sequences')

    @property
    def description(self) -> str:
        return _('Name the harmonic sequence of a four-part passage.')

    @property
    def play_label(self) -> str:
        return _('Play passage')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        return _(' · ').join(_describe_keys(settings))

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        modes = _modes(settings)
        return [
            ItemId(f'sequence.{mode.value}.{kind.value}')
            for kind in SequenceKind
            for mode in modes
            if mode in SEQUENCES[kind]
        ]

    def item_label(self, item_id: ItemId) -> str:
        mode, kind = _parse_sequence_item(item_id)
        word = pgettext('mode', 'major') if mode is Mode.MAJOR else pgettext('mode', 'minor')
        # Translators: an item in "Weakest items", e.g. "Ascending 5–6 in major".
        return _('{sequence} in {mode}').format(sequence=_sequence_name(kind), mode=word)

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        mode, kind = _parse_sequence_item(item_id)
        partner = {
            SequenceKind.DESCENDING_FIFTHS: SequenceKind.DESCENDING_FIVE_SIX,
            SequenceKind.DESCENDING_FIVE_SIX: SequenceKind.DESCENDING_FIFTHS,
            SequenceKind.SECONDARY_DOMINANTS: SequenceKind.DESCENDING_FIFTHS,
            SequenceKind.ASCENDING_FIVE_SIX: SequenceKind.DESCENDING_FIVE_SIX,
        }[kind]
        if mode not in SEQUENCES[partner]:
            return []
        return [ItemId(f'sequence.{mode.value}.{partner.value}')]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        mode, kind = _parse_sequence_item(item_id)
        keys = keys_within(_limit(settings), (mode,))
        phrase: Phrase | None = None
        for _attempt in range(_KEY_ATTEMPTS):
            try:
                phrase = sequence(kind, rng.choice(keys), rng)
                break
            except RealisationError:
                continue
        if phrase is None:
            phrase = sequence(kind, keys_within(0, (mode,))[0], rng)
        options = tuple(
            Option(k.value, _sequence_name(k), accel=str(i + 1)) for i, k in enumerate(SequenceKind)
        )
        labels = [roman_label(r[-1].numeral) for r in phrase.readings]
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Which sequence is this?'),
            answer=ChoiceAnswer(options),
            expected=kind.value,
            figure=phrase_figure(
                phrase,
                description=_('Grand staff in {key}, {n} chords. {voices}.').format(
                    key=key_name(phrase.key),
                    n=len(phrase.voicings),
                    voices=voices_description(phrase.voicings),
                ),
            ),
            playback=phrase_playback(phrase),
            context=_('Key: {key}').format(key=key_name(phrase.key)),
            details={
                'key': str(phrase.key),
                'labels': '|'.join(labels),
                'explanation': _sequence_explanation(kind, phrase),
            },
            hint=_(
                'Follow the bass and the roots: do they fall by fifths, or does the bass move '
                'by step with chords alternating between root position and first inversion?'
            ),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        expected = str(question.expected)
        correct = str(given) == expected
        label = _sequence_name(SequenceKind(expected))
        if correct:
            title = _('Correct — {answer}').format(answer=label)
        else:
            title = _('Not quite — the answer is {answer}').format(answer=label)
        key = Key.parse(question.details['key'])
        labels = question.details['labels'].split('|')
        figure = question.figure
        assert isinstance(figure, SystemSpec)
        voicings = _voicings_of(figure)
        detail = ' '.join(
            (
                question.details['explanation'],
                _('{key}: {numerals}.').format(key=key_name(key), numerals=' – '.join(labels)),
            )
        )
        return Feedback(
            correct=correct,
            title=title,
            detail=detail,
            expected_label=label,
            figure=_satb_figure(
                voicings,
                key.signature,
                durations=phrase_durations(len(voicings)),
                labels=labels,
                final_bar=True,
                description=_('Grand staff in {key}, analysed: {labels}. {voices}.').format(
                    key=key_name(key),
                    labels=' – '.join(labels),
                    voices=voices_description(voicings),
                ),
            ),
            play_expected=question.playback,
        )


EXERCISES: tuple[ExerciseDefinition, ...] = (Modulation(), Sequences())
