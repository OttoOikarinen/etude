# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Transposition: write a short melody at another pitch level.

The question figure shows a melody of three to six notes; the learner writes
it transposed on the staff input below, one note per slot. Three kinds of
items:

* **By interval**, ``transpose.interval.up.M2``: no key signatures, so every
  note is spelled with its own accidental. Each note moves by the same
  spelled interval: a major second up from E is F♯, never G♭.
* **Into a key**, ``transpose.key.down.m3``: the melody and the answer staff
  carry key signatures (the answer's is given) and the prompt names the new
  key; every note keeps its scale degree.
* **Transposing instruments**, ``transpose.instrument.bb-clarinet.concert``
  (written part → concert pitch) and ``….written`` (concert pitch → written
  part), behind a setting. A B♭ clarinet sounds a major second lower than
  written, a horn in F a perfect fifth lower and an E♭ alto saxophone a
  major sixth lower (Adler, *The Study of Orchestration*); written parts use
  the treble clef and key signatures, the concert-pitch staff the clef that
  fits.

Grading is by exact spelling and octave, note by note; the explanation names
the interval, the keys and each wrong note.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from functools import cache
from gettext import gettext as _
from gettext import ngettext, pgettext
from typing import cast

from ...audio.spec import PlaybackSpec
from ...core import Interval, Pitch, PitchName
from ...core.naming import key_name, pitch_name
from ...core.scale import Key, Mode
from ...learning.model import ItemId
from ...notation.spec import Chord as StaffChord
from ...notation.spec import Clef, StaffSpec
from ..base import (
    BoolSetting,
    ChoiceSetting,
    ExerciseDefinition,
    Family,
    Feedback,
    IntSetting,
    Modality,
    MultiChoiceSetting,
    Option,
    Question,
    StaffInputAnswer,
)
from .harmony import MAX_ACCIDENTALS, keys_within, limit_setting
from .intervals import interval_label, interval_phrase, letter_count, semitone_count, takes_an
from .note_placement import staff_value_label, staff_value_text, written_notes

INTERVALS = ('m2', 'M2', 'm3', 'M3', 'P4', 'P5', 'm6', 'M6')
"""The intervals a melody may be transposed by (the pool setting)."""
_DEFAULT_INTERVALS = ('M2', 'm3', 'M3', 'P4', 'P5')
_TEACHING_ORDER = ('M2', 'P5', 'P4', 'm3', 'M3', 'm2', 'M6', 'm6')
_DIRECTIONS = ('up', 'down')
_METHODS = ('key', 'interval')


@dataclass(frozen=True, slots=True)
class Instrument:
    key: str
    """Item segment, e.g. ``'bb-clarinet'``."""
    pitch: PitchName
    """The instrument's pitch (B♭ for a B♭ clarinet)."""
    interval: Interval
    """How far below the written note it sounds."""


INSTRUMENTS = (
    Instrument('bb-clarinet', PitchName.parse('Bb'), Interval.parse('M2')),
    Instrument('f-horn', PitchName.parse('F'), Interval.parse('P5')),
    Instrument('eb-alto-sax', PitchName.parse('Eb'), Interval.parse('M6')),
)
_INSTRUMENTS = {i.key: i for i in INSTRUMENTS}
_TARGETS = ('concert', 'written')
_CLEFS = {'treble': Clef.TREBLE, 'bass': Clef.BASS}
_LOW, _HIGH = -2, 10
"""Staff positions a melody may use: one ledger line below or above."""


def instrument_name(instrument: Instrument) -> str:
    note = pitch_name(instrument.pitch)
    if instrument.key == 'bb-clarinet':
        # Translators: an instrument; {note} is its pitch, e.g. "B♭ clarinet"
        # (German "B-Klarinette").
        return pgettext('instrument', '{note} clarinet').format(note=note)
    if instrument.key == 'f-horn':
        # Translators: an instrument; {note} is its pitch, e.g. "horn in F".
        return pgettext('instrument', 'horn in {note}').format(note=note)
    # Translators: an instrument; {note} is its pitch, e.g. "E♭ alto saxophone".
    return pgettext('instrument', '{note} alto saxophone').format(note=note)


def _with_article(key: str) -> str:
    if takes_an(key):
        # Translators: an interval with its indefinite article, "an augmented fourth".
        return _('an {interval}').format(interval=interval_phrase(key))
    # Translators: an interval with its indefinite article, "a major second".
    return _('a {interval}').format(interval=interval_phrase(key))


# Items ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Item:
    method: str
    """``'interval'``, ``'key'`` or ``'instrument'``."""
    interval: Interval
    up: bool
    instrument: Instrument | None = None
    target: str = ''
    """For instruments: ``'concert'`` or ``'written'``."""


def item_id(method: str, direction: str, segment: str) -> ItemId:
    """``transpose.interval.up.M2``, ``transpose.key.down.m3`` or
    ``transpose.instrument.bb-clarinet.concert``."""
    return ItemId(f'transpose.{method}.{direction}.{segment}')


_item_id = item_id


def instrument_item(instrument: str, target: str) -> ItemId:
    return ItemId(f'transpose.instrument.{instrument}.{target}')


@cache
def _parse(item: str) -> _Item:
    parts = item.split('.')
    if len(parts) != 4 or parts[0] != 'transpose':
        raise ValueError(f'not a transposition item: {item!r}')
    method = parts[1]
    if method in _METHODS and parts[2] in _DIRECTIONS and parts[3] in INTERVALS:
        return _Item(method, Interval.parse(parts[3]), parts[2] == 'up')
    if method == 'instrument' and parts[2] in _INSTRUMENTS and parts[3] in _TARGETS:
        instrument = _INSTRUMENTS[parts[2]]
        # Written → concert goes down; concert → written goes up.
        return _Item(method, instrument.interval, parts[3] == 'written', instrument, parts[3])
    raise ValueError(f'not a transposition item: {item!r}')


def parse_item(item: str) -> tuple[str, str, str]:
    """``(method, direction or instrument, interval or target)``."""
    _parse(item)
    method, second, third = item.split('.')[1:]
    return method, second, third


# Settings helpers ------------------------------------------------------------------------


def _choice(settings: Mapping[str, object], key: str, allowed: Sequence[str], default: str) -> str:
    value = str(settings.get(key, default))
    return value if value in allowed else default


def _selected(
    settings: Mapping[str, object], key: str, allowed: Sequence[str], default: Sequence[str]
) -> list[str]:
    chosen = settings.get(key, default)
    keys = set(cast(Sequence[str], chosen)) if isinstance(chosen, list | tuple) else set(default)
    return [k for k in allowed if k in keys] or list(default)


def _length(settings: Mapping[str, object]) -> int:
    value = settings.get('notes', 4)
    return max(3, min(6, value if isinstance(value, int) else 4))


# Melodies -----------------------------------------------------------------------------------

_STEPS = (-1, 1, -1, 1, -2, 2, -1, 1, 3, -3, 4, -2, 2)


def _melody_steps(length: int, rng: random.Random) -> list[int]:
    """Scale steps from the tonic (0): mostly steps, some leaps, within a ninth."""
    steps = [rng.choice((0, 2, 4))]
    while len(steps) < length:
        nxt = steps[-1] + rng.choice(_STEPS)
        if -3 <= nxt <= 8:
            steps.append(nxt)
    return steps


def _melody(key: Key, steps: Sequence[int], octave: int) -> list[Pitch]:
    scale = key.scale.pitches(octave)
    pitches = []
    for index, step in enumerate(steps):
        shift, degree = divmod(step, 7)
        p = scale[degree]
        alter = p.alter
        rising_to_tonic = index + 1 < len(steps) and steps[index + 1] == step + 1
        if key.mode is Mode.MINOR and degree == 6 and rising_to_tonic:
            alter += 1  # the raised leading tone of the harmonic minor
        pitches.append(Pitch(p.letter, alter, p.octave + shift))
    return pitches


def _fits(clef: Clef, pitches: Sequence[Pitch], slack: int = 0) -> bool:
    positions = [clef.staff_position(p) for p in pitches]
    return _LOW - slack <= min(positions) and max(positions) <= _HIGH + slack


def _moved(pitches: Sequence[Pitch], interval: Interval, up: bool) -> list[Pitch]:
    return [p.transpose(interval, down=not up) for p in pitches]


def _plain(pitches: Sequence[Pitch]) -> bool:
    return all(abs(p.alter) <= 1 for p in pitches)


@dataclass(frozen=True, slots=True)
class _Setup:
    original: tuple[Pitch, ...]
    expected: tuple[Pitch, ...]
    source_key: Key
    target_key: Key
    source_clef: Clef
    target_clef: Clef


class Transposition(ExerciseDefinition):
    id = 'transposition'
    item_prefix = 'transpose.'
    family = Family.NOTATION
    modality = Modality.EYE
    level = 2
    icon_name = 'transposition-symbolic'
    glyph = '⤴'
    settings = (
        MultiChoiceSetting(
            'methods',
            _('Transpose'),
            (
                Option('key', _('Into a key, with key signatures')),
                Option('interval', _('By an interval, with accidentals')),
            ),
            _METHODS,
        ),
        MultiChoiceSetting(
            'intervals',
            _('Intervals'),
            tuple(Option(key, interval_label(key)) for key in INTERVALS),
            _DEFAULT_INTERVALS,
        ),
        ChoiceSetting(
            'direction',
            _('Direction'),
            (
                Option('up', _('Up')),
                Option('down', _('Down')),
                Option('both', _('Up and down')),
            ),
            'both',
        ),
        BoolSetting(
            'instruments',
            _('Transposing instruments'),
            False,
            subtitle=_('B♭ clarinet, horn in F and E♭ alto saxophone'),
        ),
        ChoiceSetting(
            'instrument-direction',
            _('Instrument parts'),
            (
                Option('to-concert', _('Written part to concert pitch')),
                Option('to-written', _('Concert pitch to written part')),
                Option('both', _('Both ways')),
            ),
            'to-concert',
        ),
        MultiChoiceSetting(
            'clefs',
            _('Clefs'),
            (Option('treble', _('Treble')), Option('bass', _('Bass'))),
            ('treble', 'bass'),
            subtitle=_('For melodies transposed by an interval or into a key'),
        ),
        IntSetting('notes', _('Notes'), 4, 3, 6, subtitle=_('Length of the melody')),
        IntSetting(
            'max-accidentals',
            _('Most accidentals'),
            4,
            0,
            MAX_ACCIDENTALS,
            subtitle=_('Largest number of sharps or flats in either key'),
        ),
    )

    @property
    def title(self) -> str:
        return _('Transposition')

    @property
    def description(self) -> str:
        return _('Write a melody at another pitch, in another key or for another instrument.')

    @property
    def play_label(self) -> str:
        return _('Play melody')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        methods = _selected(settings, 'methods', _METHODS, _METHODS)
        parts = []
        if 'key' in methods:
            parts.append(_('into keys'))
        if 'interval' in methods:
            parts.append(_('by intervals'))
        if settings.get('instruments', False):
            parts.append(_('instruments'))
        length = _length(settings)
        parts.append(ngettext('{n} note', '{n} notes', length).format(n=length))
        text = _(' · ').join(parts)
        return text[:1].upper() + text[1:]

    def item_label(self, item_id: ItemId) -> str:
        item = _parse(item_id)
        if item.instrument is not None:
            name = instrument_name(item.instrument)
            if item.target == 'concert':
                # Translators: an item in "Weakest items", e.g. "B♭ clarinet to concert pitch".
                return _('{instrument} to concert pitch').format(instrument=name)
            # Translators: an item in "Weakest items", e.g. "Concert pitch to horn in F".
            return _('Concert pitch to {instrument}').format(instrument=name)
        label = interval_label(str(item.interval))
        if item.method == 'key':
            if item.up:
                # Translators: an item in "Weakest items", e.g. "Major second up, into a key".
                return _('{interval} up, into a key').format(interval=label)
            return _('{interval} down, into a key').format(interval=label)
        if item.up:
            # Translators: an item in "Weakest items", e.g. "Major second up, by interval".
            return _('{interval} up, by interval').format(interval=label)
        return _('{interval} down, by interval').format(interval=label)

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        """Per interval (major second, fifth, fourth, thirds, …): into a key first (each
        note keeps its degree), then by interval; then the instruments."""
        intervals = _selected(settings, 'intervals', INTERVALS, _DEFAULT_INTERVALS)
        methods = _selected(settings, 'methods', _METHODS, _METHODS)
        direction = _choice(settings, 'direction', ('up', 'down', 'both'), 'both')
        directions = _DIRECTIONS if direction == 'both' else (direction,)
        found = [
            item_id(method, d, key)
            for key in _TEACHING_ORDER
            if key in intervals
            for method in _METHODS
            if method in methods
            for d in directions
        ]
        if settings.get('instruments', False):
            way = _choice(
                settings, 'instrument-direction', ('to-concert', 'to-written', 'both'), 'to-concert'
            )
            targets = {'to-concert': ('concert',), 'to-written': ('written',)}.get(way, _TARGETS)
            found += [instrument_item(i.key, t) for i in INSTRUMENTS for t in targets]
        return found

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        """The other quality of the same interval (m3 and M3), the other direction, and
        for instruments the other direction of the same instrument."""
        item = _parse(item_id)
        if item.instrument is not None:
            other = 'written' if item.target == 'concert' else 'concert'
            return [instrument_item(item.instrument.key, other)]
        key = str(item.interval)
        direction = 'up' if item.up else 'down'
        partners = {
            'm2': 'M2',
            'M2': 'm2',
            'm3': 'M3',
            'M3': 'm3',
            'm6': 'M6',
            'M6': 'm6',
            'P4': 'P5',
            'P5': 'P4',
        }
        return [
            _item_id(item.method, direction, partners[key]),
            _item_id(item.method, 'down' if item.up else 'up', key),
        ]

    # Questions

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        item = _parse(item_id)
        setup = self._setup(item, settings, rng)
        with_signatures = item.method != 'interval'
        source_signature = setup.source_key.signature if with_signatures else None
        target_signature = setup.target_key.signature if with_signatures else None
        figure = StaffSpec.notes(
            *setup.original, clef=setup.source_clef, key_signature=source_signature
        )
        sounding = setup.expected if item.target == 'concert' else setup.original
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=self._prompt(item, setup),
            answer=StaffInputAnswer(
                clef=setup.target_clef,
                key_signature=target_signature,
                slots=len(setup.expected),
            ),
            expected=tuple((p,) for p in setup.expected),
            figure=figure,
            playback=PlaybackSpec.melodic(sounding, note_length=Fraction(1), tempo=100.0),
            context=self._context(item, setup),
            hint=self._hint(item),
            details={'source-key': str(setup.source_key), 'target-key': str(setup.target_key)},
        )

    def _setup(self, item: _Item, settings: Mapping[str, object], rng: random.Random) -> _Setup:
        limit = limit_setting(settings)
        length = _length(settings)
        clefs = [_CLEFS[c] for c in _selected(settings, 'clefs', tuple(_CLEFS), tuple(_CLEFS))]
        pairs = self._key_pairs(item, limit)
        for attempt in range(200):
            source, target = rng.choice(pairs)
            steps = _melody_steps(length, rng)
            if item.instrument is None:
                source_clefs = target_clefs = [rng.choice(clefs)]
            elif item.target == 'concert':
                source_clefs, target_clefs = [Clef.TREBLE], [Clef.TREBLE, Clef.BASS]
            else:
                source_clefs, target_clefs = [Clef.TREBLE, Clef.BASS], [Clef.TREBLE]
            slack = 0 if attempt < 150 else 2
            options = []
            for octave in range(1, 7):
                original = _melody(source, steps, octave)
                moved = _moved(original, item.interval, item.up)
                if not (_plain(original) and _plain(moved)):
                    continue
                for source_clef in source_clefs:
                    for target_clef in target_clefs:
                        if _fits(source_clef, original, slack) and _fits(target_clef, moved, slack):
                            options.append((original, moved, source_clef, target_clef))
            if options:
                if item.instrument is not None:
                    # Concert pitch goes on the treble staff when it fits.
                    treble = [o for o in options if Clef.BASS not in (o[2], o[3])]
                    options = treble or options
                original, moved, source_clef, target_clef = rng.choice(options)
                return _Setup(
                    tuple(original), tuple(moved), source, target, source_clef, target_clef
                )
        raise AssertionError(f'no melody fits for {item}')  # pragma: no cover

    @staticmethod
    def _key_pairs(item: _Item, limit: int) -> list[tuple[Key, Key]]:
        """(source key, target key) pairs; keys within ``limit`` if any pair allows."""
        pairs = []
        for source in keys_within(MAX_ACCIDENTALS, (Mode.MAJOR, Mode.MINOR)):
            tonic = source.tonic.transpose(item.interval, down=not item.up)
            target = Key(tonic, source.mode)
            if target.is_theoretical:
                continue
            pairs.append((source, target))

        def worst(pair: tuple[Key, Key]) -> int:
            return max(pair[0].signature.count, pair[1].signature.count)

        within = [p for p in pairs if worst(p) <= limit]
        if within:
            return within
        least = min(worst(p) for p in pairs)
        return [p for p in pairs if worst(p) == least]

    @staticmethod
    def _prompt(item: _Item, setup: _Setup) -> str:
        interval = _with_article(str(item.interval))
        if item.instrument is not None:
            name = instrument_name(item.instrument)
            if item.target == 'concert':
                # Translators: e.g. "Write this B♭ clarinet part at concert pitch".
                return _('Write this {instrument} part at concert pitch').format(instrument=name)
            # Translators: e.g. "Write this concert-pitch melody for horn in F".
            return _('Write this concert-pitch melody for {instrument}').format(instrument=name)
        if item.method == 'key':
            if item.up:
                # Translators: e.g. "Write the melody in A major, a major second higher".
                text = _('Write the melody in {key}, {interval} higher')
            else:
                text = _('Write the melody in {key}, {interval} lower')
            return text.format(key=key_name(setup.target_key), interval=interval)
        if item.up:
            # Translators: e.g. "Write the melody a major second higher".
            return _('Write the melody {interval} higher').format(interval=interval)
        return _('Write the melody {interval} lower').format(interval=interval)

    @staticmethod
    def _context(item: _Item, setup: _Setup) -> str:
        if item.method == 'interval':
            return ''
        if item.instrument is not None and item.target == 'written':
            # Translators: context of a transposition question, e.g. "Concert pitch: D major".
            return _('Concert pitch: {key}').format(key=key_name(setup.source_key))
        if item.instrument is not None:
            # Translators: context of a transposition question, e.g. "Written in E major".
            return _('Written in {key}').format(key=key_name(setup.source_key))
        # Translators: context of a transposition question, e.g. "From G major to A major".
        return _('From {source} to {target}').format(
            source=key_name(setup.source_key), target=key_name(setup.target_key)
        )

    @staticmethod
    def _hint(item: _Item) -> str:
        if item.instrument is not None:
            return _(
                'A transposing instrument is named after the concert pitch of its written C: '
                'a B♭ clarinet playing a written C sounds B♭.'
            )
        if item.method == 'key':
            return _(
                'Each note keeps its scale degree: find the degree, then write it in the new key.'
            )
        return _(
            'Move every note by the same interval: count letter names for the number, '
            'then semitones for the quality.'
        )

    # Grading

    def grade(self, question: Question, given: object) -> Feedback:
        item = _parse(question.item_id)
        expected = tuple(
            chord[0] for chord in cast(tuple[tuple[Pitch, ...], ...], question.expected)
        )
        original = self._original(question)
        chords = written_notes(given)
        written = (
            tuple(c[0] for c in chords)
            if chords is not None and all(len(c) == 1 for c in chords)
            else None
        )
        correct = written == expected
        right = sum(w == e for w, e in zip(written, expected, strict=False)) if written else 0
        label = staff_value_label(question.expected)
        if correct:
            # Translators: e.g. "Correct — A4, B4, C♯5".
            title = _('Correct — {answer}').format(answer=label)
        else:
            # Translators: e.g. "Not quite — the answer is A4, B4, C♯5".
            title = _('Not quite — the answer is {answer}').format(answer=label)
        sentences = [self._method(item, question, original, expected)]
        if written is not None and not correct:
            sentences += self._mistakes(written, expected)
        return Feedback(
            correct=correct,
            title=title,
            detail=' '.join(sentences),
            expected_label=label,
            score=right / len(expected),
            play_expected=PlaybackSpec.melodic(expected, note_length=Fraction(1), tempo=100.0),
            play_given=(
                PlaybackSpec.melodic(written, note_length=Fraction(1), tempo=100.0)
                if written and not correct
                else None
            ),
        )

    @staticmethod
    def _original(question: Question) -> tuple[Pitch, ...]:
        figure = question.figure
        assert isinstance(figure, StaffSpec)
        return tuple(e.heads[0].pitch for e in figure.events if isinstance(e, StaffChord))

    def _method(
        self,
        item: _Item,
        question: Question,
        original: Sequence[Pitch],
        expected: Sequence[Pitch],
    ) -> str:
        key = str(item.interval)
        interval = _with_article(key)
        first, target = original[0], expected[0]
        example = _('{note} becomes {target}').format(note=_note(first), target=_note(target))
        source_key, target_key = self._key_names(question)
        if item.instrument is not None:
            name = instrument_name(item.instrument)
            if item.target == 'concert':
                # Translators: e.g. "A B♭ clarinet sounds a major second lower than written, so
                # the part written in E major sounds in D major: E5 becomes D5."
                return _(
                    'The {instrument} sounds {interval} lower than written, so the part written '
                    'in {source} sounds in {target}: {example}.'
                ).format(
                    instrument=name,
                    interval=interval,
                    source=source_key,
                    target=target_key,
                    example=example,
                )
            return _(
                'The {instrument} sounds {interval} lower than written, so its part is written '
                '{interval} higher than concert pitch: {source} becomes {target}, and {example}.'
            ).format(
                instrument=name,
                interval=interval,
                source=source_key,
                target=target_key,
                example=example,
            )
        spans = _('{letters} and {semitones}').format(
            letters=letter_count(item.interval.number),
            semitones=semitone_count(item.interval.semitones),
        )
        if item.method == 'key':
            text = (
                _(
                    '{source} moves up {interval} to {target}. Every note keeps its scale degree: '
                    '{example}.'
                )
                if item.up
                else _(
                    '{source} moves down {interval} to {target}. Every note keeps its scale '
                    'degree: {example}.'
                )
            )
            return text.format(
                source=source_key, target=target_key, interval=interval, example=example
            )
        text = (
            # Translators: e.g. "Every note moves up a major second, two letter names and two
            # semitones: E4 becomes F♯4."
            _('Every note moves up {interval}, {spans}: {example}.')
            if item.up
            else _('Every note moves down {interval}, {spans}: {example}.')
        )
        return text.format(interval=interval, spans=spans, example=example)

    @staticmethod
    def _key_names(question: Question) -> tuple[str, str]:
        """Names of the source and target keys, stored with the question."""
        keys = [question.details.get(k) for k in ('source-key', 'target-key')]
        if keys[0] is None or keys[1] is None:
            return '', ''
        return key_name(Key.parse(keys[0])), key_name(Key.parse(keys[1]))

    @staticmethod
    def _mistakes(written: Sequence[Pitch], expected: Sequence[Pitch]) -> list[str]:
        sentences = []
        wrong = [
            (i, w, e) for i, (w, e) in enumerate(zip(written, expected, strict=False)) if w != e
        ]
        for index, w, e in wrong[:3]:
            if w.midi == e.midi:
                # Translators: e.g. "Note 3: G♭4 sounds right, but the transposed note is
                # spelled F♯4."
                text = _(
                    'Note {n}: {given} sounds right, but the transposed note is spelled {expected}.'
                )
            elif w.diatonic_index == e.diatonic_index:
                # Translators: e.g. "Note 2: F4 has the right letter name but needs F♯4."
                text = _('Note {n}: {given} has the right letter name but needs {expected}.')
            else:
                # Translators: e.g. "Note 4: B4 should be C♯5."
                text = _('Note {n}: {given} should be {expected}.')
            sentences.append(text.format(n=index + 1, given=_note(w), expected=_note(e)))
        if len(wrong) > 3:
            sentences.append(
                ngettext(
                    '{n} more note is wrong.', '{n} more notes are wrong.', len(wrong) - 3
                ).format(n=len(wrong) - 3)
            )
        return sentences

    def answer_label(self, question: Question, value: object) -> str:
        return staff_value_label(value)

    def serialize(self, value: object) -> str:
        return staff_value_text(value)


def _note(pitch: Pitch) -> str:
    return pitch_name(pitch.name) + str(pitch.octave)


EXERCISES: tuple[ExerciseDefinition, ...] = (Transposition(),)
