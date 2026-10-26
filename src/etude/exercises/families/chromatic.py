# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Chromatic harmony on the staff: name a chromatic chord in a phrase, and write one.

*Chromatic Chords* shows a short four-part phrase in a key (from
:func:`etude.checkers.phrases.chromatic_phrase`) with one chord marked by a question
mark and the accent colour, and asks for its Roman numeral as Kostka–Payne write it.
The learner answers with chips that make up the label: the **numeral** (V, vii°, viiø
for secondary functions; iv, ii°, iiø, ♭III, ♭VI, ♭VII, vii° for mixture; N for the
Neapolitan; It+, Fr+, Ger+ for the augmented sixths), the **target** of a secondary
function (/ii, /V …, or none) and the **figures** (none, 6, 6/4, 7, 6/5, 4/3, 4/2):
vii° + 6/5 + /V = vii°6/5/V, N + 6 = N6, Ger+ + 6 = Ger+6. The target group appears
only while secondary functions are practised.

Items are chord × mode (``chromatic.name.major.V7/V``, ``chromatic.name.minor.N6``,
``chromatic.name.major.Ger+6``), in the order of :data:`~etude.checkers.phrases.
CHROMATIC_CHORDS`; key, inversion, phrase and voicing vary.

*Chromatic Writing* gives a bass with Roman numerals of a chromatic progression
(V6/5/V–V, vii°7/V–V, N6–V–i, Ger+6–Cad6/4–V–i, ♭VI in major …) and asks for the
upper voices, graded by the voice-leading checker with its chromatic rules, exactly
as Four-Part Writing is (:func:`.satb.grade_four_part`). In major the Ger+6 may be
written with ♭3̂ or ♯2̂. Items are ``chromatic.write.<progression>``.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from gettext import gettext as _
from gettext import ngettext, pgettext
from typing import ClassVar, cast

from ...checkers.phrases import (
    CHROMATIC_CHORDS,
    ChromaticChord,
    ChromaticFamily,
    Phrase,
    chromatic_chord,
    chromatic_phrase,
    voiced,
)
from ...checkers.realize import RealisationError, Voicing, chords_of, function_keys
from ...checkers.voice_leading import BASS, SOPRANO, Context, voice_title
from ...core import Chord, ChordKind, ChordQuality, Duration, NoteValue, Pitch, RomanNumeral
from ...core.naming import chord_name, key_name, pitch_name
from ...core.scale import Key, Mode
from ...learning.model import ItemId
from ...notation.spec import Clef, SystemSpec
from ..base import (
    ChipGroup,
    ChipsAnswer,
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
    StaffInputAnswer,
)
from .harmony import (
    SEVENTH_FIGURES,
    TRIAD_FIGURES,
    figure_text,
    keys_within,
    limit_setting,
    modes_setting,
    progression_playback,
    roman_label,
    satb_figure,
    satb_voices,
)
from .roman_numerals import inversion_sentence
from .satb import STAVES, VOICE_STAVES, chords_text, grade_four_part, note_text

MAX_ACCIDENTALS = 6
_QUARTER = Duration(NoteValue.QUARTER)
_HALF = Duration(NoteValue.HALF)
_KEY_ATTEMPTS = 6


def _mode_word(mode: Mode) -> str:
    return pgettext('mode', 'major') if mode is Mode.MAJOR else pgettext('mode', 'minor')


def _family_name(family: ChromaticFamily) -> str:
    names: dict[ChromaticFamily, Callable[[], str]] = {
        ChromaticFamily.SECONDARY: lambda: _('Secondary dominants'),
        ChromaticFamily.MIXTURE: lambda: _('Mode mixture'),
        ChromaticFamily.NEAPOLITAN: lambda: _('Neapolitan sixth'),
        ChromaticFamily.AUGMENTED_SIXTH: lambda: _('Augmented sixths'),
    }
    return names[family]()


def _settings_modes(settings: Mapping[str, object]) -> tuple[Mode, ...]:
    return modes_setting(settings, 'both')


def _limit(settings: Mapping[str, object]) -> int:
    return min(MAX_ACCIDENTALS, limit_setting(settings, 3))


def _common_settings() -> tuple[Setting, ...]:
    return (
        ChoiceSetting(
            'mode',
            _('Keys'),
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
            subtitle=_('Largest number of sharps or flats in the key signature'),
        ),
    )


def _describe_keys(settings: Mapping[str, object]) -> list[str]:
    modes = _settings_modes(settings)
    if modes == (Mode.MAJOR,):
        parts = [_('Major keys')]
    elif modes == (Mode.MINOR,):
        parts = [_('Minor keys')]
    else:
        parts = [_('Major and minor')]
    limit = _limit(settings)
    parts.append(ngettext('up to {n} accidental', 'up to {n} accidentals', limit).format(n=limit))
    return parts


def _spellable(chords: Sequence[Chord]) -> bool:
    return all(abs(n.alter) <= 2 for chord in chords for n in chord.names())


def phrase_durations(count: int) -> tuple[Duration, ...]:
    """Quarter notes, the last chord a half note."""
    return (*(_QUARTER,) * (count - 1), _HALF)


def phrase_lengths(count: int) -> tuple[Fraction, ...]:
    return tuple(d.quarter_length for d in phrase_durations(count))


def voices_description(voicings: Sequence[Voicing]) -> str:
    """Each voice's notes, for a figure's accessible description."""
    # Translators: separator between the voices of a described passage.
    return _('. ').join(
        f'{voice_title(voice)}: ' + ', '.join(note_text(c[voice]) for c in voicings)
        for voice in range(4)
    )


# Chromatic chords: the chips ------------------------------------------------------------

_NUMERALS: dict[str, Callable[[], str]] = {
    'V': lambda: 'V',
    'viio': lambda: 'vii°',
    'viiø': lambda: 'viiø',
    'iv': lambda: 'iv',
    'iio': lambda: 'ii°',
    'iiø': lambda: 'iiø',
    'bIII': lambda: '♭III',
    'bVI': lambda: '♭VI',
    'bVII': lambda: '♭VII',
    # Translators: the Neapolitan's numeral, as in "N6"; Kostka–Payne write N.
    'N': lambda: pgettext('roman numeral', 'N'),
    # Translators: the Italian, French and German augmented sixths as in "It+6".
    'It': lambda: pgettext('roman numeral', 'It+'),
    'Fr': lambda: pgettext('roman numeral', 'Fr+'),
    'Ger': lambda: pgettext('roman numeral', 'Ger+'),
}
_FAMILY_NUMERALS = {
    ChromaticFamily.SECONDARY: ('V', 'viio', 'viiø'),
    ChromaticFamily.MIXTURE: ('iv', 'iio', 'iiø', 'bIII', 'bVI', 'bVII', 'viio'),
    ChromaticFamily.NEAPOLITAN: ('N',),
    ChromaticFamily.AUGMENTED_SIXTH: ('It', 'Fr', 'Ger'),
}
_TARGETS = {
    Mode.MAJOR: ('ii', 'iii', 'IV', 'V', 'vi'),
    Mode.MINOR: ('III', 'iv', 'V', 'VI', 'VII'),
}
_NO_TARGET = 'none'
_FIGURES = (*TRIAD_FIGURES, *SEVENTH_FIGURES)


def numeral_key(numeral: RomanNumeral) -> str:
    """The numeral chip of a chromatic numeral: ``'V'`` for V6/5/V, ``'viio'`` for
    vii°7/V, ``'bVI'``, ``'N'``, ``'Ger'``."""
    quality = numeral.quality
    if quality.kind is ChordKind.AUGMENTED_SIXTH:
        return {
            ChordQuality.ITALIAN_SIXTH: 'It',
            ChordQuality.FRENCH_SIXTH: 'Fr',
        }.get(quality, 'Ger')
    if (numeral.degree, numeral.alter, quality) == (2, -1, ChordQuality.MAJOR):
        return 'N'
    text = str(RomanNumeral(numeral.degree, quality, 0, numeral.alter))
    return text.removesuffix('7')


def figures_key(numeral: RomanNumeral) -> str:
    """The figures chip: ``'65'``, ``'53'`` for root-position triads, ``'6'`` for N6 and
    the augmented sixths."""
    if numeral.quality.kind is ChordKind.AUGMENTED_SIXTH:
        return '6'
    if numeral.quality.kind is ChordKind.SEVENTH:
        return SEVENTH_FIGURES[numeral.inversion]
    return TRIAD_FIGURES[numeral.inversion]


def _expected(numeral: RomanNumeral, secondary: bool) -> dict[str, str]:
    value = {'numeral': numeral_key(numeral), 'figures': figures_key(numeral)}
    if secondary:
        target = numeral.secondary
        value['target'] = str(target) if target is not None else _NO_TARGET
    return value


def chips_label(value: Mapping[str, object]) -> str:
    """The label the chips spell: numeral, figures and target, ``'vii°6/5/V'``."""
    numeral = _NUMERALS.get(str(value.get('numeral', '')), lambda: '?')()
    figures = figure_text(str(value.get('figures', '')))
    target = str(value.get('target', _NO_TARGET))
    text = numeral + figures
    if target != _NO_TARGET:
        text += '/' + roman_label(RomanNumeral.parse(target))
    return text


def _families(settings: Mapping[str, object]) -> tuple[ChromaticFamily, ...]:
    chosen = settings.get('families', tuple(f.value for f in ChromaticFamily))
    values = set(cast(Sequence[str], chosen)) if isinstance(chosen, list | tuple) else set()
    found = tuple(f for f in ChromaticFamily if f.value in values)
    return found or tuple(ChromaticFamily)


def name_item(chord: ChromaticChord) -> ItemId:
    return ItemId(f'chromatic.name.{chord.mode.value}.{chord.id}')


def parse_name_item(item: str) -> ChromaticChord:
    parts = item.split('.', 3)
    if len(parts) != 4 or parts[:2] != ['chromatic', 'name'] or parts[2] not in ('major', 'minor'):
        raise ValueError(f'not a chromatic chord item: {item!r}')
    return chromatic_chord(parts[3], Mode(parts[2]))


def chord_label(chord: ChromaticChord) -> str:
    """``'V7/V'``, ``'vii°7/ii'``, ``'N6'``, ``'Ger+6'``, ``'♭VI'``."""
    return roman_label(chord.numeral)


_CONFUSABLE_CHORDS = {
    'V/V': ('V7/V',),
    'V7/V': ('viio7/V', 'V/V'),
    'viio7/V': ('V7/V', 'viiø7/V'),
    'viiø7/V': ('viio7/V',),
    'V/ii': ('V7/ii',),
    'V7/ii': ('viio7/ii', 'V/ii'),
    'viio7/ii': ('V7/ii',),
    'V/vi': ('V7/vi',),
    'V7/vi': ('viio7/vi', 'V/vi'),
    'viio7/vi': ('V7/vi',),
    'V/iv': ('V7/iv',),
    'V7/iv': ('viio7/iv', 'V/iv', 'V7/IV'),
    'viio7/iv': ('V7/iv',),
    'iv': ('iio', 'bVI'),
    'iio': ('iiø7', 'iv'),
    'iiø7': ('iio',),
    'bVI': ('bIII', 'iv'),
    'bIII': ('bVI', 'bVII'),
    'bVII': ('bIII',),
    'viio7': ('viio7/V',),
    'N6': ('It+6',),
    'It+6': ('Fr+6', 'Ger+6'),
    'Fr+6': ('It+6', 'Ger+6'),
    'Ger+6': ('Fr+6', 'It+6'),
}


class ChromaticChords(ExerciseDefinition):
    id = 'chromatic-chords'
    item_prefix = 'chromatic.name.'
    family = Family.HARMONY
    modality = Modality.EYE
    level = 3
    icon_name = 'chromatic-chords-symbolic'
    glyph = '♭II'
    settings: ClassVar[tuple[Setting, ...]] = (
        MultiChoiceSetting(
            'families',
            _('Chords'),
            tuple(Option(f.value, _family_name(f)) for f in ChromaticFamily),
            tuple(f.value for f in ChromaticFamily),
        ),
        *_common_settings(),
    )

    @property
    def title(self) -> str:
        return _('Chromatic Chords')

    @property
    def description(self) -> str:
        return _(
            'Name secondary dominants, borrowed chords, the Neapolitan and augmented sixths '
            'in a phrase.'
        )

    @property
    def play_label(self) -> str:
        return _('Play phrase')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        families = _families(settings)
        parts = []
        if len(families) < len(ChromaticFamily):
            # Translators: separator in a list of chord families in an exercise subtitle.
            parts.append(_(', ').join(_family_name(f) for f in families))
        parts += _describe_keys(settings)
        # Translators: separator between the parts of an exercise subtitle.
        return _(' · ').join(parts)

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        families = _families(settings)
        modes = _settings_modes(settings)
        chosen = [c for c in CHROMATIC_CHORDS if c.family in families and c.mode in modes]
        if not chosen:  # mixture alone in minor keys: mixture is a major-key topic
            chosen = [c for c in CHROMATIC_CHORDS if c.family in families]
        return [name_item(c) for c in chosen]

    def item_label(self, item_id: ItemId) -> str:
        chord = parse_name_item(item_id)
        # Translators: an item in "Weakest items", e.g. "V7/V in major".
        return _('{chord} in {mode}').format(chord=chord_label(chord), mode=_mode_word(chord.mode))

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        chord = parse_name_item(item_id)
        found = []
        for other in _CONFUSABLE_CHORDS.get(chord.id, ()):
            try:
                found.append(name_item(chromatic_chord(other, chord.mode)))
            except ValueError:
                continue
        return found

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        chord = parse_name_item(item_id)
        phrase = _phrase_for(chord, _limit(settings), rng)
        key = phrase.key
        focus = phrase.focus
        assert focus is not None
        numeral = phrase.readings[focus][-1].numeral
        # The chips of the families practised (an older item keeps its own family);
        # mixture is a major-key topic.
        families = set(_families(settings)) | {chord.family}
        if chord.mode is Mode.MINOR:
            families.discard(ChromaticFamily.MIXTURE)
        secondary = ChromaticFamily.SECONDARY in families
        numerals = tuple(
            dict.fromkeys(n for f in ChromaticFamily if f in families for n in _FAMILY_NUMERALS[f])
        )
        groups = [
            ChipGroup('numeral', _('Numeral'), tuple(Option(n, _NUMERALS[n]()) for n in numerals))
        ]
        if secondary:
            targets = (_NO_TARGET, *_TARGETS[chord.mode])
            groups.append(
                ChipGroup(
                    'target',
                    _('Target'),
                    tuple(
                        Option(
                            t,
                            pgettext('secondary target', 'None')
                            if t == _NO_TARGET
                            else '/' + roman_label(RomanNumeral.parse(t)),
                        )
                        for t in targets
                    ),
                )
            )
        groups.append(
            ChipGroup(
                'figures',
                _('Figures'),
                tuple(
                    Option(f, figure_text(f) or pgettext('roman figures', 'None (5/3)'))
                    for f in _FIGURES
                ),
            )
        )
        labels = tuple(roman_label(r[-1].numeral) for r in phrase.readings)
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            # Translators: the chord to name is marked with a question mark on the staff.
            prompt=_('Name the chord marked ?'),
            answer=ChipsAnswer(tuple(groups)),
            expected=_expected(numeral, secondary),
            figure=_question_figure(phrase),
            playback=progression_playback(
                phrase.voicings, phrase_lengths(len(phrase.voicings)), tempo=72.0
            ),
            # Translators: context of a chromatic chord question, e.g. "Key: C minor · chord 3".
            context=_('Key: {key} · chord {n}').format(key=key_name(key), n=focus + 1),
            details={
                'key': str(key),
                'numeral': str(numeral),
                'focus': str(focus),
                'labels': '|'.join(labels),
            },
            hint=_(
                'Spell the chord and find the notes that are not in the key. A raised note '
                'that leads up to the next chord suggests a secondary dominant; ♭6̂ with ♯4̂ '
                'is an augmented sixth; ♭2̂ in a major triad is the Neapolitan.'
            ),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        expected = cast(Mapping[str, str], question.expected)
        given_map = given if isinstance(given, Mapping) else {}
        right = [str(given_map.get(k, '')) == v for k, v in expected.items()]
        correct = all(right)
        label = chips_label(expected)
        if correct:
            # Translators: e.g. "Correct — vii°6/5/V".
            title = _('Correct — {answer}').format(answer=label)
        else:
            # Translators: e.g. "Not quite — the answer is vii°6/5/V".
            title = _('Not quite — the answer is {answer}').format(answer=label)
        key = Key.parse(question.details['key'])
        numeral = RomanNumeral.parse(question.details['numeral'])
        focus = int(question.details['focus'])
        voicings = satb_voices(question.figure)
        detail = _explanation(key, numeral, focus, voicings, given_map, expected)
        return Feedback(
            correct=correct,
            title=title,
            detail=detail,
            expected_label=label,
            score=sum(right) / len(right),
            figure=_answer_figure(key, voicings, question.details['labels'].split('|'), focus),
            play_expected=question.playback,
        )

    def answer_label(self, question: Question, value: object) -> str:
        if isinstance(value, Mapping):
            return chips_label(value)
        return super().answer_label(question, value)

    def serialize(self, value: object) -> str:
        if isinstance(value, Mapping):
            return ','.join(f'{k}={v}' for k, v in value.items())
        return str(value)


def _phrase_for(chord: ChromaticChord, limit: int, rng: random.Random) -> Phrase:
    """A phrase around ``chord`` in a key with at most ``limit`` accidentals whose notes
    need no more than double sharps or flats."""
    keys = keys_within(limit, (chord.mode,))
    failure: Exception | None = None
    for _attempt in range(_KEY_ATTEMPTS):
        key = rng.choice(keys)
        try:
            phrase = chromatic_phrase(chord, key, rng)
        except RealisationError as error:
            failure = error  # a key with many accidentals: try another
            continue
        if _spellable(phrase.chords):
            return phrase
    # C major and A minor always work (tests voice every chord there).
    del failure
    return chromatic_phrase(chord, keys_within(0, (chord.mode,))[0], rng)


def _question_figure(phrase: Phrase) -> SystemSpec:
    focus = phrase.focus
    assert focus is not None
    count = len(phrase.voicings)
    labels: list[str | None] = [None] * count
    labels[focus] = '?'
    description = _(
        'Grand staff in {key}, {n} chords; chord {focus}, marked with a question mark, is '
        'the chord to name. {voices}.'
    ).format(
        key=key_name(phrase.key),
        n=count,
        focus=focus + 1,
        voices=voices_description(phrase.voicings),
    )
    return satb_figure(
        phrase.voicings,
        phrase.key.signature,
        durations=phrase_durations(count),
        labels=labels,
        highlight=(focus,),
        final_bar=True,
        description=description,
    )


def _answer_figure(
    key: Key, voicings: Sequence[Voicing], labels: Sequence[str], focus: int
) -> SystemSpec:
    description = _('Grand staff in {key}, analysed: {labels}. {voices}.').format(
        key=key_name(key),
        labels=' – '.join(labels),
        voices=voices_description(voicings),
    )
    return satb_figure(
        voicings,
        key.signature,
        durations=phrase_durations(len(voicings)),
        labels=labels,
        highlight=(focus,),
        final_bar=True,
        description=description,
    )


def _notes(chord: Chord) -> str:
    # Translators: separator between the notes of a chord, "E–G–B".
    return _('–').join(pitch_name(n) for n in chord.names())


def _explanation(
    key: Key,
    numeral: RomanNumeral,
    focus: int,
    voicings: Sequence[Voicing],
    given: Mapping[object, object],
    expected: Mapping[str, str],
) -> str:
    chord = numeral.realize(key)
    label = roman_label(numeral)
    sentences = [
        # Translators: e.g. "In C major, chord 3 is F♯–A–C–E♭ (F♯ diminished seventh):
        # vii°6/5/V."
        _('In {key}, chord {n} is {notes} ({chord}): {numeral}.').format(
            key=key_name(key),
            n=focus + 1,
            notes=_notes(chord),
            chord=chord_name(chord),
            numeral=label,
        ),
        _family_sentence(key, numeral, chord),
    ]
    if chord.quality.kind in (ChordKind.TRIAD, ChordKind.SEVENTH):
        sentences.append(inversion_sentence(chord, label))
    if str(given.get('target', expected.get('target', ''))) != expected.get('target', ''):
        sentences.append(
            _(
                'Look where the chord leads: a secondary dominant or leading-tone chord '
                'resolves to the chord it tonicizes, as V and vii° resolve to I.'
            )
        )
    elif (
        str(given.get('numeral', '')) == expected['numeral']
        and str(given.get('figures', '')) != expected['figures']
    ):
        sentences.append(
            _('Figures count intervals above the bass, not the root: find the bass first.')
        )
    return ' '.join(sentences)


def _family_sentence(key: Key, numeral: RomanNumeral, chord: Chord) -> str:
    tones = chord.names()
    target = numeral.secondary
    if numeral.quality.kind is ChordKind.AUGMENTED_SIXTH:
        low, high = tones[0], tones[-1]
        dominant = key.degree(5)
        text = _(
            'An augmented sixth chord: {low} (♭6̂) in the bass and {high} (♯4̂) above it '
            'form an augmented sixth that expands outward to the octave on {dominant}. The '
            'It+6 adds only the tonic, the Fr+6 also 2̂, the Ger+6 ♭3̂.'
        ).format(low=pitch_name(low), high=pitch_name(high), dominant=pitch_name(dominant))
        if numeral.quality is ChordQuality.DOUBLY_AUGMENTED_FOURTH:
            text += ' ' + _(
                'Here ♭3̂ is spelled {note} (♯2̂), a doubly augmented fourth above the bass, '
                'because it rises to the third of the cadential six-four.'
            ).format(note=pitch_name(tones[2]))
        return text
    if target is not None:
        local = numeral.tonicized_key(key)
        goal = roman_label(target)
        if numeral.degree == 7:
            return _(
                'A secondary leading-tone chord: it is built on {root}, the leading tone of '
                '{tonic}, and leads to {goal}.'
            ).format(root=pitch_name(chord.root), tonic=pitch_name(local.tonic), goal=goal)
        return _(
            'A secondary dominant: the dominant of {goal} ({tonic}). Its third, {third}, is '
            'the leading tone of {tonic} and rises to it.'
        ).format(goal=goal, tonic=pitch_name(local.tonic), third=pitch_name(tones[1]))
    if (numeral.degree, numeral.alter, numeral.quality) == (2, -1, ChordQuality.MAJOR):
        return _(
            'The Neapolitan sixth: the major triad on the lowered second degree, {root}, '
            'usually with its third, {third}, in the bass (doubled). {root} falls to the '
            'leading tone or the tonic.'
        ).format(root=pitch_name(chord.root), third=pitch_name(tones[1]))
    parallel = Key(key.tonic, Mode.MINOR)
    borrowed = [n for n in tones if n not in key.scale.names()]
    return ngettext(
        'Borrowed from {minor} (mode mixture): {notes} is a lowered scale degree of the '
        'parallel minor.',
        'Borrowed from {minor} (mode mixture): {notes} are lowered scale degrees of the '
        'parallel minor.',
        len(borrowed),
    ).format(
        minor=key_name(parallel),
        # Translators: separator between note names in a list such as "A♭, E♭".
        notes=_(', ').join(pitch_name(n) for n in borrowed),
    )


# Chromatic writing ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Writing:
    key: str
    """Item segment, e.g. ``'N6'``."""
    major: tuple[str, ...] | None
    minor: tuple[str, ...] | None

    def modes(self) -> tuple[Mode, ...]:
        return tuple(
            m for m, n in ((Mode.MAJOR, self.major), (Mode.MINOR, self.minor)) if n is not None
        )

    def numerals(self, mode: Mode) -> tuple[str, ...]:
        found = self.major if mode is Mode.MAJOR else self.minor
        assert found is not None
        return found


WRITINGS = (
    Writing('V65/V', ('I', 'V65/V', 'V', 'I'), ('i', 'V65/V', 'V', 'i')),
    Writing('V7/V-Cad64', ('I', 'V7/V', 'Cad64', 'V', 'I'), ('i', 'V7/V', 'Cad64', 'V', 'i')),
    Writing('viio7/V', ('I', 'viio7/V', 'V', 'I'), ('i', 'viio7/V', 'V', 'i')),
    Writing('V7/IV', ('I', 'V7/IV', 'IV', 'V', 'I'), ('i', 'V7/iv', 'iv', 'V', 'i')),
    Writing('V7/ii', ('I', 'V7/ii', 'ii', 'V', 'I'), None),
    Writing('V/vi', ('I', 'V/vi', 'vi', 'ii6', 'V', 'I'), None),
    Writing('iv', ('I', 'iv6', 'V', 'I'), None),
    Writing('iio65', ('I', 'iiø65', 'V', 'I'), None),
    Writing('bVI', ('I', 'bVI', 'iv', 'V', 'I'), None),
    Writing('N6', ('I', 'N6', 'V', 'I'), ('i', 'N6', 'V', 'i')),
    Writing('N6-Cad64', ('I', 'N6', 'Cad64', 'V', 'I'), ('i', 'N6', 'Cad64', 'V', 'i')),
    Writing('It+6', ('I', 'iv6', 'It+6', 'V', 'I'), ('i', 'iv6', 'It+6', 'V', 'i')),
    Writing('Fr+6', ('I', 'Fr+6', 'V', 'I'), ('i', 'Fr+6', 'V', 'i')),
    Writing('Ger+6', ('I', 'Ger+6', 'Cad64', 'V', 'I'), ('i', 'Ger+6', 'Cad64', 'V', 'i')),
)
"""In teaching order: secondary functions, mixture, the Neapolitan, augmented sixths."""
_BY_KEY = {w.key: w for w in WRITINGS}


def _writing_title(key: str) -> str:
    titles: dict[str, Callable[[], str]] = {
        'V65/V': lambda: _('Secondary dominant'),
        'V7/V-Cad64': lambda: _('V7/V and the cadential six-four'),
        'viio7/V': lambda: _('Secondary leading-tone chord'),
        'V7/IV': lambda: _('Dominant of the subdominant'),
        'V7/ii': lambda: _('Dominant of the supertonic'),
        'V/vi': lambda: _('Dominant of the submediant'),
        'iv': lambda: _('Borrowed iv'),
        'iio65': lambda: _('Borrowed iiø6/5'),
        'bVI': lambda: _('Borrowed ♭VI'),
        'N6': lambda: _('Neapolitan sixth'),
        'N6-Cad64': lambda: _('Neapolitan and the cadential six-four'),
        'It+6': lambda: _('Italian sixth'),
        'Fr+6': lambda: _('French sixth'),
        'Ger+6': lambda: _('German sixth'),
    }
    return titles[key]()


def _writing_hint(writing: Writing) -> str:
    if writing.key.startswith('N6'):
        return _(
            'Double the bass of the N6, its third. Let ♭2̂ fall: to the leading tone in V, or '
            'to the tonic in the cadential six-four.'
        )
    if writing.key.endswith('+6'):
        return _(
            'In the augmented sixth, ♭6̂ falls and ♯4̂ rises by half step to the octave on 5̂; '
            'do not double either. After a Ger+6 the cadential six-four avoids parallel '
            'fifths.'
        )
    if writing.key in ('iv', 'iio65', 'bVI'):
        return _(
            'Borrowed chords are voiced like their diatonic forms; do not double the lowered '
            'notes, and let them fall.'
        )
    return _(
        'The raised note of a secondary dominant is a temporary leading tone: do not double '
        'it, and let it rise to the root of the chord it tonicizes. Sevenths fall by step.'
    )


def _parse_write(item_id: str) -> Writing:
    prefix = 'chromatic.write.'
    if not item_id.startswith(prefix) or item_id[len(prefix) :] not in _BY_KEY:
        raise ValueError(f'not a chromatic writing item: {item_id!r}')
    return _BY_KEY[item_id[len(prefix) :]]


def _writing_context(key: Key, numerals: Sequence[str]) -> Callable[[Sequence[Voicing]], Context]:
    """The checker's context for an answer: the numerals' chords and keys, with a Ger+6
    in major read in the spelling the learner chose (♭3̂ or ♯2̂)."""

    def context(chords: Sequence[Voicing]) -> Context:
        texts = list(numerals)
        for index, text in enumerate(texts):
            if text == 'Ger+6' and key.mode is Mode.MAJOR and index < len(chords):
                swapped = RomanNumeral.parse('Ger+6(#2)').realize(key)
                if swapped.names()[2] in {p.name for p in chords[index]}:
                    texts[index] = str(RomanNumeral.parse('Ger+6(#2)'))
        return Context(key, chords_of(texts, key), keys=function_keys(texts, key))

    return context


class ChromaticWriting(ExerciseDefinition):
    id = 'chromatic-writing'
    item_prefix = 'chromatic.write.'
    family = Family.HARMONY
    modality = Modality.EYE
    level = 3
    icon_name = 'chromatic-writing-symbolic'
    glyph = '+6'
    settings: ClassVar[tuple[Setting, ...]] = (
        *_common_settings(),
        ChoiceSetting(
            'task',
            _('Voices to write'),
            (
                Option('inner', _('Alto and tenor')),
                Option('upper', _('Soprano, alto and tenor')),
                Option('both', _('Both')),
            ),
            'both',
            subtitle=_('The bass is always given; with alto and tenor, the soprano too'),
        ),
    )

    @property
    def title(self) -> str:
        return _('Chromatic Writing')

    @property
    def description(self) -> str:
        return _(
            'Write secondary dominants, borrowed chords, the Neapolitan and augmented '
            'sixths in four parts.'
        )

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        parts = _describe_keys(settings)
        task = str(settings.get('task', 'both'))
        if task == 'inner':
            parts.append(_('alto and tenor'))
        elif task == 'upper':
            parts.append(_('soprano, alto and tenor'))
        return _(' · ').join(parts)

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        modes = set(_settings_modes(settings))
        return [ItemId(f'chromatic.write.{w.key}') for w in WRITINGS if modes & set(w.modes())]

    def item_label(self, item_id: ItemId) -> str:
        writing = _parse_write(item_id)
        mode = writing.modes()[0]
        labels = [roman_label(RomanNumeral.parse(n)) for n in writing.numerals(mode)]
        # Translators: an item in "Weakest items", e.g. "Neapolitan sixth: i – N6 – V – i".
        return _('{title}: {progression}').format(
            title=_writing_title(writing.key), progression=' – '.join(labels)
        )

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        pairs = {
            'V65/V': 'viio7/V',
            'viio7/V': 'V65/V',
            'N6': 'N6-Cad64',
            'N6-Cad64': 'N6',
            'It+6': 'Fr+6',
            'Fr+6': 'Ger+6',
            'Ger+6': 'Fr+6',
        }
        partner = pairs.get(_parse_write(item_id).key)
        return [ItemId(f'chromatic.write.{partner}')] if partner else []

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        writing = _parse_write(item_id)
        modes = [m for m in _settings_modes(settings) if m in writing.modes()]
        mode = rng.choice(modes or list(writing.modes()))
        numerals = writing.numerals(mode)
        keys = keys_within(_limit(settings), (mode,))
        chords: tuple[Voicing, ...] = ()
        key = keys[0]
        for attempt in range(_KEY_ATTEMPTS + 1):
            key = rng.choice(keys) if attempt < _KEY_ATTEMPTS else keys_within(0, (mode,))[0]
            if not _spellable(chords_of(numerals, key)):
                continue
            try:
                chords = voiced(numerals, key, rng.randrange(1 << 16))
                break
            except RealisationError:
                continue
        labels = tuple(roman_label(RomanNumeral.parse(n)) for n in numerals)
        task = str(settings.get('task', 'both'))
        if task not in ('inner', 'upper'):
            task = rng.choice(('inner', 'upper'))
        given: dict[int, tuple[Pitch, ...]] = {BASS: tuple(c[BASS] for c in chords)}
        name = key_name(key)
        if task == 'inner':
            given[SOPRANO] = tuple(c[SOPRANO] for c in chords)
            # Translators: e.g. "Write the alto and tenor in G major".
            prompt = _('Write the alto and tenor in {key}').format(key=name)
        else:
            # Translators: e.g. "Write soprano, alto and tenor above the bass in G major".
            prompt = _('Write soprano, alto and tenor above the bass in {key}').format(key=name)
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=prompt,
            answer=StaffInputAnswer(
                clef=Clef.TREBLE,
                key_signature=key.signature,
                slots=len(chords),
                voices=4,
                staves=STAVES,
                voice_staves=VOICE_STAVES,
                given_voices=given,
                labels=labels,
            ),
            expected=tuple(chords),
            context=' – '.join(labels),
            details={'key': str(key), 'numerals': '-'.join(numerals)},
            hint=_writing_hint(writing),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        key = Key.parse(question.details['key'])
        numerals = question.details['numerals'].split('-')
        return grade_four_part(question, given, _writing_context(key, numerals))

    def answer_label(self, question: Question, value: object) -> str:
        if isinstance(value, tuple) and all(
            isinstance(c, tuple) and len(c) == 4 and all(isinstance(p, Pitch) for p in c)
            for c in value
        ):
            return chords_text(cast(Sequence[Voicing], value))
        return str(value)

    def serialize(self, value: object) -> str:
        if isinstance(value, tuple) and all(isinstance(c, tuple) for c in value):
            return ' | '.join(' '.join(str(p) for p in chord) for chord in value)
        return str(value)


EXERCISES: tuple[ExerciseDefinition, ...] = (ChromaticChords(), ChromaticWriting())
