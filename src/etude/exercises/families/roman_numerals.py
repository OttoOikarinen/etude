# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Roman numerals: label a chord in a key with its numeral and inversion figures.

A diatonic chord is written in a key, in close position on one staff or in
four parts on a grand staff, and the key is named. The learner answers with
two chip groups: the **numeral** (I ii iii IV V vi vii° in major, i ii° III
iv V VI vii° in minor, where case and sign give the triad's quality) and the
**figures** (none, 6 or 6/4 for a triad; 7, 6/5, 4/3 or 4/2 for a seventh
chord). Two groups rather than numeral, seventh and inversion: the figures
already say whether there is a seventh, and the two groups are exactly the
two parts of a written numeral, V + 6/5 = V6/5.

Items are numeral × figures × mode, ``roman.major.V.53``,
``roman.major.V7.65``, ``roman.minor.iiø7.7``, ``roman.minor.viio.6``.
Teaching order: primary triads in root position, their inversions, the
secondary triads, V7 and its inversions, then the other seventh chords.

Conventions follow Kostka & Payne, *Tonal Harmony* (ch. 4–5) and
:mod:`etude.core.roman`: minor keys use the harmonic minor for V, V7, vii°
and vii°7 and the natural minor otherwise (i7, iiø7, IIIM7, iv7, VIM7);
major seventh chords are written with M (IM7, IVM7); figures are written with
slashes (V6/5), and root-position triads have no figures.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from functools import cache
from gettext import gettext as _
from gettext import ngettext, pgettext
from typing import cast

from ...core import Chord, ChordQuality, KeySignature, Pitch
from ...core.naming import chord_name, degree_name, key_name, pitch_name
from ...core.roman import RomanNumeral
from ...core.scale import Key, Mode
from ...learning.model import ItemId
from ...notation.spec import Chord as StaffChord
from ...notation.spec import Clef, Figure, Head, Ink, StaffSpec, SystemSpec
from ..base import (
    BoolSetting,
    ChipGroup,
    ChipsAnswer,
    ChoiceSetting,
    ExerciseDefinition,
    Family,
    Feedback,
    IntSetting,
    Modality,
    Option,
    Question,
)
from .chords import chord_playback
from .harmony import (
    MAX_ACCIDENTALS,
    SEVENTH_FIGURES,
    TRIAD_FIGURES,
    Satb,
    best_voicing,
    chord_of,
    figure_text,
    key_from_signature,
    keys_within,
    limit_setting,
    modes_setting,
    numeral_base,
    roman_label,
    satb_figure,
    satb_voices,
)

_MODES = {'major': Mode.MAJOR, 'minor': Mode.MINOR}
_STAFF_LOW = -2
_STAFF_HIGH = 10


@cache
def diatonic(key: Key, degree: int, seventh: bool) -> Chord:
    """The diatonic triad or seventh chord on ``degree`` in root position (cached)."""
    return key.seventh(degree) if seventh else key.triad(degree)


@cache
def _numeral(mode: Mode, degree: int, seventh: bool) -> RomanNumeral:
    """The diatonic numeral on ``degree`` in root position (from a key on C)."""
    key = Key(Key.parse('C').tonic, mode)
    chord = diatonic(key, degree, seventh)
    numeral = RomanNumeral.analyze(chord, key)
    assert numeral is not None
    return numeral


@cache
def _numeral_key(mode: Mode, degree: int, seventh: bool) -> str:
    """Item segment: ``'V'``, ``'viio'``, ``'V7'``, ``'iiø7'``, ``'IM7'``."""
    return str(_numeral(mode, degree, seventh))


_DEGREES = range(1, 8)
_PRIMARY = (1, 4, 5)
_SECONDARY = (2, 6, 3, 7)
_OTHER_SEVENTHS = (2, 7, 4, 6, 1, 3)
"""Predominant and leading-tone sevenths first (ii7, viiø7), as in Kostka–Payne ch. 13–15."""


def item_id(mode: Mode, degree: int, seventh: bool, inversion: int) -> ItemId:
    figures = SEVENTH_FIGURES if seventh else TRIAD_FIGURES
    return ItemId(f'roman.{mode.value}.{_numeral_key(mode, degree, seventh)}.{figures[inversion]}')


@cache
def parse_item(item: str) -> tuple[Mode, int, bool, int]:
    """``(mode, degree, seventh, inversion)``; raises :class:`ValueError` for other ids."""
    parts = item.split('.')
    if len(parts) != 4 or parts[0] != 'roman' or parts[1] not in _MODES:
        raise ValueError(f'not a Roman numeral item: {item!r}')
    mode = _MODES[parts[1]]
    for seventh, figures in ((False, TRIAD_FIGURES), (True, SEVENTH_FIGURES)):
        if parts[3] not in figures:
            continue
        for degree in _DEGREES:
            if _numeral_key(mode, degree, seventh) == parts[2]:
                return mode, degree, seventh, figures.index(parts[3])
    raise ValueError(f'not a Roman numeral item: {item!r}')


def _sevenths(settings: Mapping[str, object]) -> str:
    value = str(settings.get('sevenths', 'dominant'))
    return value if value in ('none', 'dominant', 'all') else 'dominant'


def _voicing(settings: Mapping[str, object]) -> str:
    value = str(settings.get('voicing', 'mixed'))
    return value if value in ('close', 'satb', 'mixed') else 'mixed'


def _mode_name(mode: Mode) -> str:
    return pgettext('mode', 'major') if mode is Mode.MAJOR else pgettext('mode', 'minor')


def _fit_close(chord: Chord, rng: random.Random) -> tuple[Clef, tuple[Pitch, ...]]:
    """The chord in close position on a treble or bass staff, within one ledger line."""
    options = []
    for clef in (Clef.TREBLE, Clef.BASS):
        for octave in range(1, 6):
            pitches = chord.pitches(octave)
            positions = [clef.staff_position(p) for p in pitches]
            if _STAFF_LOW <= min(positions) and max(positions) <= _STAFF_HIGH:
                options.append((clef, pitches))
    return rng.choice(options)


def _inversion_sentence(chord: Chord, label: str) -> str:
    bass = pitch_name(chord.bass)
    if chord.quality.size == 4:
        sentences = (
            # Translators: {bass} is a note name, {numeral} a Roman numeral such as "V7".
            _('The root, {bass}, is in the bass: {numeral}.'),
            # Translators: e.g. "The third, C♯, is in the bass, so the figures are 6/5: V6/5."
            _('The third, {bass}, is in the bass, so the figures are 6/5: {numeral}.'),
            _('The fifth, {bass}, is in the bass, so the figures are 4/3: {numeral}.'),
            _('The seventh, {bass}, is in the bass, so the figures are 4/2: {numeral}.'),
        )
    else:
        sentences = (
            # Translators: a root-position triad has no figures; {numeral} is e.g. "IV".
            _('The root, {bass}, is in the bass: root position, {numeral}.'),
            # Translators: e.g. "The third, F♯, is in the bass, so the figure is 6: I6."
            _('The third, {bass}, is in the bass, so the figure is 6: {numeral}.'),
            _('The fifth, {bass}, is in the bass, so the figures are 6/4: {numeral}.'),
        )
    return sentences[chord.inversion].format(bass=bass, numeral=label)


def _notes(chord: Chord) -> str:
    # Translators: separator between the notes of a chord, "E–G–B".
    return _('–').join(pitch_name(n) for n in chord.names())


class RomanNumerals(ExerciseDefinition):
    id = 'roman-numerals'
    item_prefix = 'roman.'
    family = Family.HARMONY
    modality = Modality.EYE
    level = 2
    icon_name = 'roman-numerals-symbolic'
    glyph = 'V⁷'
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
        ChoiceSetting(
            'sevenths',
            _('Seventh chords'),
            (
                Option('none', _('Triads only')),
                Option('dominant', _('Dominant seventh')),
                Option('all', _('All diatonic sevenths')),
            ),
            'dominant',
        ),
        BoolSetting(
            'inversions',
            _('Inversions'),
            True,
            subtitle=_('Chords with the third, fifth or seventh in the bass'),
        ),
        IntSetting(
            'max-accidentals',
            _('Most accidentals'),
            4,
            0,
            MAX_ACCIDENTALS,
            subtitle=_('Largest number of sharps or flats in the key signature'),
        ),
        ChoiceSetting(
            'voicing',
            _('Voicing'),
            (
                Option('close', _('Close position on one staff')),
                Option('satb', _('Four voices on a grand staff')),
                Option('mixed', _('Both')),
            ),
            'mixed',
        ),
    )

    @property
    def title(self) -> str:
        return _('Roman Numerals')

    @property
    def description(self) -> str:
        return _('Label chords in a key with Roman numerals and inversion figures.')

    @property
    def play_label(self) -> str:
        return _('Play chord')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        modes = modes_setting(settings)
        if modes == (Mode.MAJOR,):
            parts = [_('Major keys')]
        elif modes == (Mode.MINOR,):
            parts = [_('Minor keys')]
        else:
            parts = [_('Major and minor keys')]
        sevenths = _sevenths(settings)
        if sevenths == 'none':
            parts.append(_('triads'))
        elif sevenths == 'dominant':
            parts.append(_('triads and V7'))
        else:
            parts.append(_('triads and sevenths'))
        limit = limit_setting(settings)
        parts.append(
            ngettext('up to {n} accidental', 'up to {n} accidentals', limit).format(n=limit)
        )
        # Translators: separator between the parts of an exercise subtitle.
        return _(' · ').join(parts)

    def item_label(self, item_id: ItemId) -> str:
        mode, degree, seventh, inversion = parse_item(item_id)
        numeral = _numeral(mode, degree, seventh)
        label = roman_label(RomanNumeral(degree, numeral.quality, inversion, numeral.alter))
        if mode is Mode.MAJOR:
            # Translators: an item in "Weakest items", e.g. "V6/5 in major".
            return _('{numeral} in major').format(numeral=label)
        # Translators: an item in "Weakest items", e.g. "iiø4/3 in minor".
        return _('{numeral} in minor').format(numeral=label)

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        """Primary triads, their inversions, secondary triads (root position, then
        inverted), V7 and its inversions, then the other seventh chords."""
        modes = modes_setting(settings)
        inverted = bool(settings.get('inversions', True))
        sevenths = _sevenths(settings)
        triad_inversions = range(1, 3) if inverted else range(0)
        seventh_inversions = range(4) if inverted else range(1)
        stages: list[list[tuple[int, bool, int]]] = [
            [(d, False, 0) for d in _PRIMARY],
            [(d, False, i) for i in triad_inversions for d in _PRIMARY],
            [(d, False, 0) for d in _SECONDARY],
            [(d, False, i) for i in triad_inversions for d in _SECONDARY],
        ]
        if sevenths != 'none':
            stages.append([(5, True, i) for i in seventh_inversions])
        if sevenths == 'all':
            stages.append([(d, True, i) for d in _OTHER_SEVENTHS for i in seventh_inversions])
        return [
            item_id(mode, degree, seventh, inversion)
            for stage in stages
            for degree, seventh, inversion in stage
            for mode in modes
        ]

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        """The same chord in another inversion, the triad or seventh chord on the same
        degree, and chords over the same bass that share two tones (ii6 and IV, vii°6
        and ii, iii6 and V)."""
        mode, degree, seventh, inversion = parse_item(item_id)
        key = Key(Key.parse('C').tonic, mode)
        chord = self._chord(key, degree, seventh, inversion)
        found: list[ItemId] = []
        size = 4 if seventh else 3
        for other in (inversion - 1, inversion + 1):
            if 0 <= other < size:
                found.append(self._item(mode, degree, seventh, other))
        if inversion < 3:
            found.append(self._item(mode, degree, not seventh, inversion))
        for other_degree in _DEGREES:
            for other_inversion in range(3):
                if other_degree == degree:
                    continue
                candidate = self._chord(key, other_degree, False, other_inversion)
                shared = set(candidate.names()) & set(chord.names())
                if candidate.bass == chord.bass and len(shared) >= 2:
                    found.append(self._item(mode, other_degree, False, other_inversion))
        return list(dict.fromkeys(found))

    @staticmethod
    def _item(mode: Mode, degree: int, seventh: bool, inversion: int) -> ItemId:
        return item_id(mode, degree, seventh, inversion)

    @staticmethod
    def _chord(key: Key, degree: int, seventh: bool, inversion: int) -> Chord:
        return diatonic(key, degree, seventh).with_inversion(inversion)

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        mode, degree, seventh, inversion = parse_item(item_id)
        limit = limit_setting(settings)
        key = rng.choice(
            [k for k in keys_within(limit, (mode,)) if self._spellable(k, degree, seventh)]
        )
        chord = self._chord(key, degree, seventh, inversion)
        voicing = _voicing(settings)
        if voicing == 'mixed':
            voicing = rng.choice(('close', 'satb'))
        figure: Figure
        if voicing == 'satb':
            voices = best_voicing(chord, key, rng)
            figure = satb_figure(Satb((voices,), key.signature))
            pitches: Sequence[Pitch] = sorted(voices)
        else:
            clef, pitches = _fit_close(chord, rng)
            figure = StaffSpec(
                clef=clef,
                key_signature=key.signature,
                events=(StaffChord(tuple(Head(p) for p in pitches)),),
            )

        # Items outside the current settings (an older review) keep their own options.
        sevenths = _sevenths(settings) != 'none' or seventh
        numerals = tuple(
            Option(str(d), _numeral(mode, d, False).symbol, str(d)) for d in _DEGREES
        )
        figure_keys = (*TRIAD_FIGURES, *(SEVENTH_FIGURES if sevenths else ()))
        accels = '890qwty'
        figure_options = tuple(
            Option(f, figure_text(f) or pgettext('roman figures', 'None (5/3)'), accels[i])
            for i, f in enumerate(figure_keys)
        )
        figures = SEVENTH_FIGURES if seventh else TRIAD_FIGURES
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Name the Roman numeral'),
            answer=ChipsAnswer(
                (
                    ChipGroup('numeral', _('Numeral'), numerals),
                    ChipGroup('figures', _('Figures'), figure_options),
                )
            ),
            expected={'numeral': str(degree), 'figures': figures[inversion]},
            figure=figure,
            playback=chord_playback(pitches),
            # Translators: context of a Roman numeral question, e.g. "Key: D major".
            context=_('Key: {key}').format(key=key_name(key)),
            hint=_(
                'Stack the notes in thirds to find the root and its scale degree; then see '
                'which chord tone is in the bass.'
            ),
        )

    @staticmethod
    def _spellable(key: Key, degree: int, seventh: bool) -> bool:
        return all(abs(n.alter) <= 2 for n in diatonic(key, degree, seventh).names())

    def grade(self, question: Question, given: object) -> Feedback:
        expected = cast(Mapping[str, str], question.expected)
        mode, degree, seventh, inversion = parse_item(question.item_id)
        key = self._key(question, mode)
        chord = self._chord(key, degree, seventh, inversion)
        given_map = given if isinstance(given, Mapping) else {}
        right = [str(given_map.get(k, '')) == v for k, v in expected.items()]
        correct = all(right)
        label = self.answer_label(question, expected)
        if correct:
            # Translators: e.g. "Correct — V6/5".
            title = _('Correct — {answer}').format(answer=label)
        else:
            # Translators: e.g. "Not quite — the answer is V6/5".
            title = _('Not quite — the answer is {answer}').format(answer=label)
        return Feedback(
            correct=correct,
            title=title,
            detail=self._explanation(key, chord, given_map, expected),
            expected_label=label,
            score=sum(right) / len(right),
            figure=self._annotated(question.figure, label),
            play_expected=question.playback,
        )

    @staticmethod
    def _key(question: Question, mode: Mode) -> Key:
        figure = question.figure
        if isinstance(figure, SystemSpec):
            signature = figure.staves[0].key_signature
        elif isinstance(figure, StaffSpec):
            signature = figure.key_signature
        else:
            signature = KeySignature(0)
        return key_from_signature(signature, mode)

    def answer_label(self, question: Question, value: object) -> str:
        """The numeral as written: ``'V6/5'``, ``'vii°'``, ``'IV6/4'``."""
        if not isinstance(value, Mapping):
            return super().answer_label(question, value)
        mode = parse_item(question.item_id)[0]
        try:
            degree = int(str(value.get('numeral', '')))
            figures = str(value.get('figures', ''))
            seventh = figures in SEVENTH_FIGURES
            inversion = (SEVENTH_FIGURES if seventh else TRIAD_FIGURES).index(figures)
            numeral = _numeral(mode, degree, seventh)
        except (ValueError, AssertionError):
            return super().answer_label(question, value)
        return roman_label(RomanNumeral(degree, numeral.quality, inversion, numeral.alter))

    def serialize(self, value: object) -> str:
        if isinstance(value, Mapping):
            return ','.join(f'{k}={v}' for k, v in value.items())
        return str(value)

    def _explanation(
        self,
        key: Key,
        chord: Chord,
        given: Mapping[object, object],
        expected: Mapping[str, str],
    ) -> str:
        numeral = RomanNumeral.analyze(chord, key)
        assert numeral is not None
        label = roman_label(numeral)
        function = key.function_of(chord.root)
        degree_text = degree_name(function) if function is not None else ''
        sentences = [
            # Translators: e.g. "In D major, A–C♯–E–G (A dominant seventh) is built on scale
            # degree 5 (Dominant): V7." {chord} is a chord name such as "A dominant seventh".
            _('In {key}, {notes} ({chord}) is built on scale degree {degree} ({function}): '
              '{numeral}.')
            .format(
                key=key_name(key),
                notes=_notes(chord),
                chord=chord_name(chord),
                degree=numeral.degree,
                function=degree_text,
                numeral=numeral_base(numeral),
            ),
            _inversion_sentence(chord, label),
        ]
        if chord.quality in (ChordQuality.MAJOR, ChordQuality.DOMINANT_SEVENTH):
            case = _('A major triad is written with an upper-case numeral.')
        elif chord.quality in (ChordQuality.MINOR, ChordQuality.MINOR_SEVENTH):
            case = _('A minor triad is written with a lower-case numeral.')
        elif chord.quality is ChordQuality.HALF_DIMINISHED_SEVENTH:
            case = _('A diminished triad with a minor seventh is half-diminished: ø.')
        elif chord.quality is ChordQuality.DIMINISHED_SEVENTH:
            case = _('A diminished triad with a diminished seventh is fully diminished: °7.')
        elif chord.quality is ChordQuality.DIMINISHED:
            case = _('A diminished triad is written lower-case with °.')
        else:
            case = _('A major seventh above the root is written M: {numeral}.').format(
                numeral=numeral_base(numeral)
            )
        sentences.append(case)
        if key.mode is Mode.MINOR and key.leading_tone in chord.names():
            sentences.append(
                # Translators: e.g. "In minor, V uses the raised leading tone, B♮."
                _('In minor, this chord uses the raised leading tone, {note}.').format(
                    note=pitch_name(key.leading_tone)
                )
            )
        if str(given.get('numeral', '')) == expected['numeral'] and str(
            given.get('figures', '')
        ) != expected['figures']:
            sentences.append(
                _('Figures count intervals above the bass, not the root: find the bass first.')
            )
        return ' '.join(sentences)

    @staticmethod
    def _annotated(figure: Figure | None, label: str) -> Figure | None:
        """The question's chord with its numeral written under it."""
        if isinstance(figure, StaffSpec):
            events = tuple(
                StaffChord(e.heads, e.duration, label=label, ink=Ink.ACCENT)
                if isinstance(e, StaffChord)
                else e
                for e in figure.events
            )
            return StaffSpec(
                clef=figure.clef,
                key_signature=figure.key_signature,
                events=events,
                description=figure.description,
            )
        if isinstance(figure, SystemSpec):
            voices = satb_voices(figure)
            signature = figure.staves[0].key_signature
            return satb_figure(Satb(tuple(voices), signature), labels=(label,))
        return figure


def chord_in_figure(figure: Figure | None) -> Chord:
    """The chord written in a question figure (tests and feedback)."""
    if isinstance(figure, SystemSpec):
        return chord_of(sorted(satb_voices(figure)[0]))
    assert isinstance(figure, StaffSpec)
    pitches = [h.pitch for e in figure.events if isinstance(e, StaffChord) for h in e.heads]
    return chord_of(sorted(pitches))


EXERCISES: tuple[ExerciseDefinition, ...] = (RomanNumerals(),)
