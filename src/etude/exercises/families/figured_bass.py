# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Figured bass: name the chord that a figured bass note stands for.

A bass note in a key is written with its figures under it; the learner
names the chord with the chips of *Chords — Staff* (root, quality and
inversion). We ask for the chord rather than its Roman numeral because
reading figures is a skill of its own: the figures give intervals above the
bass, and turning them into notes and stacking those in thirds is exactly
what root, quality and inversion check. Roman numerals have their own
exercise, and the explanation names the numeral too.

Items are figure patterns per mode: ``figbass.major.53`` (no figures),
``figbass.minor.6``, ``figbass.major.64``, ``figbass.major.7``, ``…65``,
``…43`` and ``…42``, plus patterns with an accidental,
``figbass.minor.53.raised3`` (a lone ♯ or ♮: V in minor),
``figbass.minor.6.raised6`` (♯6 or a slashed 6: vii°6 in minor),
``figbass.major.6.lowered3`` (6 over ♭: ii°6 borrowed from minor) and so on.
Key, bass register and the chord that fits the pattern vary per question.

Conventions (Kostka & Payne, *Tonal Harmony*, ch. 4; Open Music Theory,
"Figured bass"; :mod:`etude.core.figured_bass`):

* Notes follow the key signature unless a figure has an accidental, which
  gives the note's accidental: ♯ and ♮ raise, ♭ and ♮ lower. An accidental
  on its own refers to the third above the bass. A slashed 6 (6̸) means a
  raised sixth, as in Baroque scores.
* No figure means 5/3; 6 means 6/3, 7 means 7/5/3, 6/5 means 6/5/3, 4/3
  means 6/4/3 and 4/2 means 6/4/2. A figure with an accidental is always
  written, so V4/3 in minor is ♯6/4/3.
* Accidentals on the bass itself are written on the staff.

Questions avoid keys where a figure would need a double sharp or flat, where
the ♯ = "raise" and ♯ = "sharp" readings of older and newer texts disagree.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from gettext import gettext as _
from gettext import ngettext, pgettext
from typing import cast

from ...core import Chord, ChordQuality, FiguredBass, KeySignature, Letter, Pitch, PitchName
from ...core.naming import chord_name, key_name, pitch_name
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
from .chords import INVERSIONS, chord_playback, root_value
from .harmony import (
    MAX_ACCIDENTALS,
    SEVENTH_FIGURES,
    TRIAD_FIGURES,
    keys_within,
    limit_setting,
    modes_setting,
    roman_label,
)

_SHOWN = {
    '53': (),
    '6': (6,),
    '64': (6, 4),
    '7': (7,),
    '65': (6, 5),
    '43': (4, 3),
    '42': (4, 2),
}
"""Numbers written for each inversion when nothing is altered."""
_FIGURE_ORDER = (*TRIAD_FIGURES, *SEVENTH_FIGURES)
_SIGNS = {1: '♯', 0: '♮', -1: '♭'}
_ASCII_SIGNS = {1: '#', 0: 'n', -1: 'b'}
SLASH = '̸'
"""Combining long solidus overlay: ``'6' + SLASH`` is a slashed 6."""
_STAFF_LOW = -2
_STAFF_HIGH = 9

_QUALITY_KEYS = {
    ChordQuality.MAJOR: 'major',
    ChordQuality.MINOR: 'minor',
    ChordQuality.DIMINISHED: 'dim',
    ChordQuality.DOMINANT_SEVENTH: 'dom7',
    ChordQuality.MAJOR_SEVENTH: 'maj7',
    ChordQuality.MINOR_SEVENTH: 'min7',
    ChordQuality.HALF_DIMINISHED_SEVENTH: 'hdim7',
    ChordQuality.DIMINISHED_SEVENTH: 'dim7',
}
_QUALITIES = {v: k for k, v in _QUALITY_KEYS.items()}
_TRIAD_KEYS = ('major', 'minor', 'dim')
_SEVENTH_KEYS = ('dom7', 'maj7', 'min7', 'hdim7', 'dim7')


def _quality_label(key: str) -> str:
    ctx = 'chord quality, short'
    return {
        'major': pgettext(ctx, 'Major'),
        'minor': pgettext(ctx, 'Minor'),
        'dim': pgettext(ctx, 'Diminished'),
        'dom7': pgettext(ctx, 'Dominant 7th'),
        'maj7': pgettext(ctx, 'Major 7th'),
        'min7': pgettext(ctx, 'Minor 7th'),
        'hdim7': pgettext(ctx, 'Half-diminished'),
        'dim7': pgettext(ctx, 'Diminished 7th'),
    }[key]


def _inversion_chip(index: int) -> str:
    return (
        _('Root position'),
        pgettext('inversion', 'First'),
        pgettext('inversion', 'Second'),
        pgettext('inversion', 'Third'),
    )[index]


def _inversion_name(index: int) -> str:
    return (
        pgettext('inversion', 'root position'),
        pgettext('inversion', 'first inversion'),
        pgettext('inversion', 'second inversion'),
        pgettext('inversion', 'third inversion'),
    )[index]


def _ordinal(number: int) -> str:
    # Translators: an interval above the bass, as in "♯ raises the sixth above the bass".
    ctx = 'interval above the bass'
    return {
        2: pgettext(ctx, 'second'),
        3: pgettext(ctx, 'third'),
        4: pgettext(ctx, 'fourth'),
        5: pgettext(ctx, 'fifth'),
        6: pgettext(ctx, 'sixth'),
        7: pgettext(ctx, 'seventh'),
    }[number]


def _intervals_phrase(numbers: tuple[int, ...]) -> str:
    # Translators: the intervals a full figured-bass stack stands for, highest first.
    return {
        (5, 3): _('a fifth and a third'),
        (6, 3): _('a sixth and a third'),
        (6, 4): _('a sixth and a fourth'),
        (7, 5, 3): _('a seventh, a fifth and a third'),
        (6, 5, 3): _('a sixth, a fifth and a third'),
        (6, 4, 3): _('a sixth, a fourth and a third'),
        (6, 4, 2): _('a sixth, a fourth and a second'),
    }[numbers]


# Figures --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Alteration:
    """An upper note whose accidental differs from the key signature."""

    number: int
    """Interval number above the bass (2–7)."""
    alter: int
    """The note's accidental: 1 sharp, 0 natural, -1 flat."""
    raised: bool


@dataclass(frozen=True, slots=True)
class Figures:
    """The figured bass of a chord in a key."""

    inversion: str
    """``'53'``, ``'6'``, ``'64'``, ``'7'``, ``'65'``, ``'43'`` or ``'42'``."""
    alterations: tuple[Alteration, ...]

    @property
    def segment(self) -> str:
        """Item suffix: ``'6'`` or ``'6.raised6'``."""
        if not self.alterations:
            return self.inversion
        a = self.alterations[0]
        return f'{self.inversion}.{"raised" if a.raised else "lowered"}{a.number}'

    def entries(self, slashed: bool = False) -> list[tuple[int, str, str]]:
        """``(number, display text, ASCII text)`` per written figure, highest first."""
        written: dict[int, tuple[str, str]] = {n: (str(n), str(n)) for n in _SHOWN[self.inversion]}
        for a in self.alterations:
            sign, ascii_sign = _SIGNS[a.alter], _ASCII_SIGNS[a.alter]
            if a.number == 6 and a.raised and slashed:
                written[6] = ('6' + SLASH, '6\\')
            elif a.number == 3 and 3 not in written:
                written[3] = (sign, ascii_sign)
            else:
                written[a.number] = (sign + str(a.number), ascii_sign + str(a.number))
        return [(n, *written[n]) for n in sorted(written, reverse=True)]

    def label(self, slashed: bool = False) -> str | None:
        """The figures stacked as a chord label (lines separated by newlines)."""
        lines = [text for _, text, _ in self.entries(slashed)]
        return '\n'.join(lines) if lines else None

    def inline(self, slashed: bool = False) -> str:
        """The figures on one line, ``'♯6/4/3'``."""
        return '/'.join(text for _, text, _ in self.entries(slashed))

    def ascii(self, slashed: bool = False) -> str:
        """The figures as :meth:`etude.core.FiguredBass.parse` reads them."""
        return ' '.join(text for _, _, text in self.entries(slashed))


def figures_for(chord: Chord, key: Key) -> Figures:
    signature = key.signature
    bass = chord.bass
    alterations = []
    for name in chord.names_from_bass()[1:]:
        number = (name.letter - bass.letter) % 7 + 1
        implied = signature.alter_for(name.letter)
        if name.alter != implied:
            alterations.append(Alteration(number, name.alter, name.alter > implied))
    size = chord.quality.size
    inversion = (TRIAD_FIGURES if size == 3 else SEVENTH_FIGURES)[chord.inversion]
    return Figures(inversion, tuple(sorted(alterations, key=lambda a: -a.number)))


def _pool(key: Key, mixture: bool) -> list[Chord]:
    """Diatonic triads and seventh chords of ``key`` in every inversion; with
    ``mixture`` also iv, ii° and iiø7 borrowed from the parallel minor."""
    roots: list[Chord] = [key.triad(d) for d in range(1, 8)] + [key.seventh(d) for d in range(1, 8)]
    if mixture and key.mode is Mode.MAJOR:
        minor = key.parallel
        roots += [minor.triad(4), minor.triad(2), minor.seventh(2)]
    return [c.with_inversion(i) for c in roots for i in range(c.quality.size)]


@cache
def _candidates(key: Key, mixture: bool) -> dict[str, tuple[Chord, ...]]:
    """Item segment → chords of ``key`` written with that figure pattern."""
    found: dict[str, list[Chord]] = {}
    for chord in _pool(key, mixture):
        if any(abs(n.alter) > 1 for n in chord.names()):
            continue
        figures = figures_for(chord, key)
        if len(figures.alterations) > 1:
            continue
        found.setdefault(figures.segment, []).append(chord)
    return {k: tuple(v) for k, v in found.items()}


def _segment_order(segment: str) -> tuple[int, int, int, int]:
    parts = segment.split('.')
    figure = _FIGURE_ORDER.index(parts[0])
    if len(parts) == 1:
        return (0, 0, figure, 0)
    kind = 0 if parts[1].startswith('raised') else 1
    return (1, kind, figure, -int(parts[1][-1]))


@cache
def _segments(mode: Mode, mixture: bool) -> tuple[str, ...]:
    reference = Key(PitchName(Letter.A if mode is Mode.MINOR else Letter.C), mode)
    return tuple(sorted(_candidates(reference, mixture), key=_segment_order))


def item_id(mode: Mode, segment: str) -> ItemId:
    """``figbass.major.6`` or ``figbass.minor.43.raised6``."""
    return ItemId(f'figbass.{mode.value}.{segment}')


_MODES = {'major': Mode.MAJOR, 'minor': Mode.MINOR}


@cache
def parse_item(item: str) -> tuple[Mode, str]:
    """``(mode, figure segment)``, e.g. ``(MINOR, '43.raised6')``."""
    parts = item.split('.', 2)
    if len(parts) != 3 or parts[0] != 'figbass' or parts[1] not in _MODES:
        raise ValueError(f'not a figured-bass item: {item!r}')
    mode, segment = _MODES[parts[1]], parts[2]
    if segment not in _segments(mode, True):
        raise ValueError(f'not a figured-bass item: {item!r}')
    return mode, segment


def _is_seventh(segment: str) -> bool:
    return segment.split('.')[0] in SEVENTH_FIGURES


def _notes(names: Sequence[PitchName]) -> str:
    # Translators: separator between the notes of a chord, "E–G–B".
    return _('–').join(pitch_name(n) for n in names)


def _list(names: Sequence[PitchName]) -> str:
    # Translators: separator between listed notes, e.g. "F, A♭ and B♮" is built with it.
    return _(', ').join(pitch_name(n) for n in names)


class FiguredBassExercise(ExerciseDefinition):
    id = 'figured-bass'
    item_prefix = 'figbass.'
    family = Family.HARMONY
    modality = Modality.EYE
    level = 2
    icon_name = 'figured-bass-symbolic'
    glyph = '⁶₅'
    settings = (
        ChoiceSetting(
            'mode',
            _('Keys'),
            (
                Option('major', _('Major')),
                Option('minor', _('Minor')),
                Option('both', _('Major and minor')),
            ),
            'both',
        ),
        BoolSetting(
            'sevenths',
            _('Seventh chords'),
            True,
            subtitle=_('Figures 7, 6/5, 4/3 and 4/2'),
        ),
        BoolSetting(
            'accidentals',
            _('Accidentals in figures'),
            True,
            subtitle=_('♯ and ♮ that raise the leading tone in minor keys'),
        ),
        BoolSetting(
            'mixture',
            _('Borrowed chords'),
            False,
            subtitle=_('♭ and ♮ that lower a note: iv, ii° and iiø7 in major keys'),
        ),
        BoolSetting(
            'slashed',
            _('Slashed figures'),
            False,
            subtitle=_('Write some raised sixths as 6̸, as Baroque scores do'),
        ),
        IntSetting(
            'max-accidentals',
            _('Most accidentals'),
            4,
            0,
            MAX_ACCIDENTALS,
            subtitle=_('Largest number of sharps or flats in the key signature'),
        ),
    )

    @property
    def title(self) -> str:
        return _('Figured Bass')

    @property
    def description(self) -> str:
        return _('Name the chord that a bass note and its figures stand for.')

    @property
    def play_label(self) -> str:
        return _('Play chord')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        modes = modes_setting(settings, 'both')
        if modes == (Mode.MAJOR,):
            parts = [_('Major keys')]
        elif modes == (Mode.MINOR,):
            parts = [_('Minor keys')]
        else:
            parts = [_('Major and minor keys')]
        parts.append(
            _('triads and sevenths') if settings.get('sevenths', True) else _('triads')
        )
        if settings.get('accidentals', True) or settings.get('mixture', False):
            parts.append(_('accidentals'))
        limit = limit_setting(settings)
        parts.append(
            ngettext('up to {n} accidental', 'up to {n} accidentals', limit).format(n=limit)
        )
        # Translators: separator between the parts of an exercise subtitle.
        return _(' · ').join(parts)

    def item_label(self, item_id: ItemId) -> str:
        mode, segment = parse_item(item_id)
        reference = Key(PitchName(Letter.A if mode is Mode.MINOR else Letter.C), mode)
        chord = _candidates(reference, True)[segment][0]
        figures = figures_for(chord, reference).inline() or '5/3'
        if mode is Mode.MAJOR:
            # Translators: an item in "Weakest items", e.g. "Figures 6/5 in major".
            return _('Figures {figures} in major').format(figures=figures)
        # Translators: an item in "Weakest items", e.g. "Figures ♯6/4/3 in minor".
        return _('Figures {figures} in minor').format(figures=figures)

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        """Plain figures (5/3, 6, 6/4, then the seventh-chord figures), then figures
        that raise a note, then figures that lower one."""
        modes = modes_setting(settings, 'both')
        sevenths = bool(settings.get('sevenths', True))
        accidentals = bool(settings.get('accidentals', True))
        mixture = bool(settings.get('mixture', False))
        found: list[tuple[Mode, str]] = []
        for mode in modes:
            for segment in _segments(mode, mixture):
                if '.raised' in segment and not accidentals:
                    continue
                if not sevenths and _is_seventh(segment):
                    continue
                found.append((mode, segment))
        found.sort(key=lambda m: (_segment_order(m[1]), m[0] is Mode.MINOR))
        return [item_id(mode, segment) for mode, segment in found]

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        """Figures that differ by one number (6 and 6/4, 6/5 and 4/3, 4/3 and 4/2) and
        the same figures with and without an accidental."""
        mode, segment = parse_item(item_id)
        figure = segment.split('.')[0]
        neighbours = {
            '53': ('6',),
            '6': ('64', '53'),
            '64': ('6', '43'),
            '7': ('42', '65'),
            '65': ('43', '6'),
            '43': ('42', '65', '64'),
            '42': ('43', '7'),
        }[figure]
        found = [_item(mode, n) for n in neighbours]
        if '.' in segment:
            found.insert(0, _item(mode, figure))
        return found

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        mode, segment = parse_item(item_id)
        limit = limit_setting(settings)
        mixture = bool(settings.get('mixture', False)) or '.lowered' in segment
        fits = self._fits(segment, limit, mode, mixture)
        options = [
            (key, chord)
            for key in keys_within(MAX_ACCIDENTALS, (mode,))
            if key.signature.count <= limit or not fits
            for chord in _candidates(key, mixture).get(segment, ())
        ]
        key, chord = rng.choice(options)
        figures = figures_for(chord, key)
        slashed = (
            bool(settings.get('slashed', False))
            and any(a.number == 6 and a.raised for a in figures.alterations)
            and rng.random() < 0.5
        )
        bass = self._bass_pitch(chord.bass, rng)
        label = figures.label(slashed)
        description = _('Bass staff in {key}: {note} with the figures {figures}.').format(
            key=key_name(key),
            note=pitch_name(bass.name) + str(bass.octave),
            figures=figures.inline(slashed) or _('none'),
        )
        figure = StaffSpec(
            clef=Clef.BASS,
            key_signature=key.signature,
            events=(StaffChord((Head(bass),), label=label),),
            description=description,
        )

        sevenths = bool(settings.get('sevenths', True)) or _is_seventh(segment)
        quality_keys = (*_TRIAD_KEYS, *(_SEVENTH_KEYS if sevenths else ()))
        accels = '1234567890'
        qualities = tuple(
            Option(q, _quality_label(q), accels[i]) for i, q in enumerate(quality_keys)
        )
        inversion_count = 4 if sevenths else 3
        spare = 'qwtyuiop'
        inversions = tuple(
            Option(INVERSIONS[i], _inversion_chip(i), spare[i]) for i in range(inversion_count)
        )
        groups = (
            ChipGroup(
                'root',
                _('Root'),
                tuple(
                    Option(letter.name, pitch_name(PitchName(letter)), letter.name.lower())
                    for letter in Letter
                ),
                accidentals=True,
            ),
            ChipGroup('quality', _('Quality'), qualities),
            ChipGroup('inversion', _('Inversion'), inversions),
        )
        upper = self._upper(chord, bass)
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Which chord do the figures stand for?'),
            answer=ChipsAnswer(groups),
            expected={
                'root': root_value(chord.root),
                'quality': _QUALITY_KEYS[chord.quality],
                'inversion': INVERSIONS[chord.inversion],
            },
            figure=figure,
            playback=chord_playback((bass, *upper)),
            # Translators: context of a figured-bass question, e.g. "Key: C minor".
            context=_('Key: {key}').format(key=key_name(key)),
            hint=_(
                'Count the figures up from the bass, following the key signature; then stack '
                'the notes in thirds to find the root. No figures means 5/3.'
            ),
        )

    @staticmethod
    def _fits(segment: str, limit: int, mode: Mode, mixture: bool) -> bool:
        return any(segment in _candidates(key, mixture) for key in keys_within(limit, (mode,)))

    @staticmethod
    def _bass_pitch(name: PitchName, rng: random.Random) -> Pitch:
        options = [
            p
            for p in (name.at(o) for o in range(1, 5))
            if _STAFF_LOW <= Clef.BASS.staff_position(p) <= _STAFF_HIGH
        ]
        return rng.choice(options)

    @staticmethod
    def _upper(chord: Chord, bass: Pitch) -> tuple[Pitch, ...]:
        """The upper notes in close position, keyboard style, above middle C's B."""
        pitches: list[Pitch] = []
        floor = max(bass.midi, 59)
        for name in chord.names_from_bass()[1:]:
            octave = 3
            while name.at(octave).midi <= floor:
                octave += 1
            pitch = name.at(octave)
            pitches.append(pitch)
            floor = pitch.midi
        return tuple(pitches)

    def grade(self, question: Question, given: object) -> Feedback:
        expected = cast(Mapping[str, str], question.expected)
        key, chord, bass, slashed = self._read(question)
        given_map = given if isinstance(given, Mapping) else {}
        right = [str(given_map.get(k, '')) == v for k, v in expected.items()]
        correct = all(right)
        label = self.answer_label(question, expected)
        if correct:
            # Translators: e.g. "Correct — B diminished seventh, first inversion".
            title = _('Correct — {answer}').format(answer=label)
        else:
            # Translators: e.g. "Not quite — the answer is B diminished seventh, first inversion".
            title = _('Not quite — the answer is {answer}').format(answer=label)
        detail = self._explanation(key, chord, bass, slashed)
        if (
            str(given_map.get('root', '')) == expected['root']
            and str(given_map.get('inversion', '')) != expected['inversion']
        ):
            detail += ' ' + _(
                'Figures count up from the bass: the bass is the root only under 5/3 and 7.'
            )
        upper = self._upper(chord, bass)
        return Feedback(
            correct=correct,
            title=title,
            detail=detail,
            expected_label=label,
            score=sum(right) / len(right),
            figure=self._realization(question.figure, upper),
            play_expected=question.playback,
        )

    def _read(self, question: Question) -> tuple[Key, Chord, Pitch, bool]:
        expected = cast(Mapping[str, str], question.expected)
        figure = question.figure
        assert isinstance(figure, StaffSpec)
        event = figure.events[0]
        assert isinstance(event, StaffChord)
        bass = event.heads[0].pitch
        root = PitchName.parse(expected['root'])
        quality = _QUALITIES[expected['quality']]
        chord = Chord(root, quality, INVERSIONS.index(expected['inversion']))
        signature = figure.key_signature or KeySignature(0)
        mode = parse_item(question.item_id)[0]
        tonic = signature.major_tonic if mode is Mode.MAJOR else signature.minor_tonic
        slashed = SLASH in (event.label or '')
        return Key(tonic, mode), chord, bass, slashed

    def answer_label(self, question: Question, value: object) -> str:
        """``'B diminished seventh, first inversion'``."""
        if not isinstance(value, Mapping):
            return super().answer_label(question, value)
        try:
            root = PitchName.parse(str(value.get('root', '')))
            quality = _QUALITIES[str(value.get('quality', ''))]
            inversion = INVERSIONS.index(str(value.get('inversion', '')))
        except (KeyError, ValueError):
            return super().answer_label(question, value)
        # Translators: a chord and its inversion, e.g. "E minor triad, first inversion".
        return pgettext('chord and inversion', '{chord}, {inversion}').format(
            chord=chord_name(Chord(root, quality)), inversion=_inversion_name(inversion)
        )

    def serialize(self, value: object) -> str:
        if isinstance(value, Mapping):
            return ','.join(f'{k}={v}' for k, v in value.items())
        return str(value)

    @staticmethod
    def _explanation(key: Key, chord: Chord, bass: Pitch, slashed: bool) -> str:
        figures = figures_for(chord, key)
        signature = key.signature
        upper = chord.names_from_bass()[1:]
        expanded = FiguredBass.parse(figures.ascii(slashed)).expanded()
        numbers = tuple(f.number for f in expanded)
        by_number = {(n.letter - chord.bass.letter) % 7 + 1: n for n in upper}
        listed = [by_number[n] for n in numbers]
        bass_name = pitch_name(bass.name)
        if not figures.entries(slashed):
            sentences = [
                # Translators: e.g. "With no figures, G stands for 5/3: a fifth and a third
                # above it, D and B."
                _('With no figures, {bass} stands for 5/3: {intervals} above it, {notes}.').format(
                    bass=bass_name, intervals=_intervals_phrase(numbers), notes=_list(listed)
                )
            ]
        else:
            sentences = [
                # Translators: e.g. "Under D, the figures 6/5 mean a sixth, a fifth and a third
                # above the bass: B♮, A♭ and F."
                _('Under {bass}, the figures {figures} mean {intervals} above the bass: '
                  '{notes}.').format(
                    bass=bass_name,
                    figures=figures.inline(slashed),
                    intervals=_intervals_phrase(numbers),
                    notes=_list(listed),
                )
            ]
        for a in figures.alterations:
            note = by_number[a.number]
            plain = PitchName(note.letter, signature.alter_for(note.letter))
            if a.number == 6 and a.raised and slashed:
                sentences.append(
                    _('The slashed 6 raises the sixth, like ♯6: {plain} becomes {note}.').format(
                        plain=pitch_name(plain), note=pitch_name(note)
                    )
                )
                continue
            if a.raised:
                # Translators: e.g. "♮ raises the third above the bass from B♭ to B."
                text = _('{sign} raises the {interval} above the bass from {plain} to {note}.')
            else:
                # Translators: e.g. "♭ lowers the third above the bass from A to A♭."
                text = _('{sign} lowers the {interval} above the bass from {plain} to {note}.')
            sentences.append(
                text.format(
                    sign=_SIGNS[a.alter],
                    interval=_ordinal(a.number),
                    plain=pitch_name(plain),
                    note=pitch_name(note),
                )
            )
            if a.number == 3 and 3 not in _SHOWN[figures.inversion]:
                sentences.append(_('An accidental on its own belongs to the third.'))
        if chord.bass.alter != signature.alter_for(chord.bass.letter):
            sentences.append(
                _(
                    'The accidental of the bass, {bass}, is written on the staff; figures only '
                    'alter the notes above the bass.'
                ).format(bass=bass_name)
            )
        sentences.append(
            # Translators: e.g. "In thirds: B–D–F–A♭, B diminished seventh in first inversion."
            _('In thirds: {notes}, {chord} in {inversion}.').format(
                notes=_notes(chord.names()),
                chord=chord_name(chord),
                inversion=_inversion_name(chord.inversion),
            )
        )
        numeral = RomanNumeral.analyze(chord, key)
        if numeral is not None:
            sentences.append(
                # Translators: e.g. "In C minor that is vii°6/5."
                _('In {key} that is {numeral}.').format(
                    key=key_name(key), numeral=roman_label(numeral)
                )
            )
        return ' '.join(sentences)

    @staticmethod
    def _realization(figure: Figure | None, upper: Sequence[Pitch]) -> Figure | None:
        """The figured bass with the chord it stands for written above, keyboard style."""
        if not isinstance(figure, StaffSpec):
            return figure
        treble = StaffSpec(
            clef=Clef.TREBLE,
            key_signature=figure.key_signature,
            events=(StaffChord(tuple(Head(p, ink=Ink.ACCENT) for p in upper)),),
        )
        bass = StaffSpec(
            clef=figure.clef, key_signature=figure.key_signature, events=figure.events
        )
        return SystemSpec(staves=(treble, bass))


_item = item_id


EXERCISES: tuple[ExerciseDefinition, ...] = (FiguredBassExercise(),)
