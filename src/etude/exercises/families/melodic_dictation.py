# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Melodic dictation: hear a short tonal melody and write its pitches.

The key is set first (I–IV–V–I, the scale or the tonic chord), one bar of
clicks gives the pulse, and the melody follows: two to four bars in 2/4,
3/4 or 4/4. The first note is printed; the learner writes the others into
the given rhythm on the staff (``StaffInputAnswer.rhythm``).

Melodies come from a small tonal grammar, after the melodic principles that
sight-singing and dictation texts teach (Karpinski, *Manual for Ear Training
and Sight Singing*, ch. 2–5; Ottman & Rogers, *Music for Sight Singing*):

* start on 1̂, 3̂ or 5̂; end on 1̂, approached by step from 2̂ or 7̂;
* mostly steps; a leap (at most a sixth) is followed by a step in the
  opposite direction, and leaps join tones of one triad (the tonic triad,
  and from the "dominant leaps" vocabulary on the dominant triad too), so
  there are no tritones or augmented intervals;
* the leading tone resolves to the tonic;
* in minor, 7̂ is raised (it always resolves up) and 6̂ is raised when it
  rises to 7̂ (melodic minor), so no augmented second appears;
* the melody stays within the vocabulary's range and on the staff with at
  most one ledger line.

Items are melodic vocabularies in teaching order:
``dictation.melody.steps`` (1̂–6̂ by step), ``.tonic-triad-leaps``,
``.leading-tone`` (around the tonic, 5̣–6̂, with 7̣–1̂),
``.dominant-leaps`` and ``.minor``. Key, clef, meter, rhythm, register and
instrument vary.

Every note is graded: ``score`` is the fraction of notes written right, and
the answer counts as correct only when all of them are. (A melody with one
wrong note out of eight would pass a 0.8 threshold, but writing a melody
down means writing every note; the score still rates near misses as hard
rather than forgotten.)
"""

from __future__ import annotations

import itertools
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from gettext import gettext as _
from gettext import ngettext
from typing import ClassVar, cast

from ...audio.spec import Instrument, PlaybackNote, PlaybackSpec
from ...core import Duration, Letter, Meter, NoteValue, Pitch
from ...core.naming import key_name, pitch_name
from ...core.scale import Key, Mode
from ...learning.model import ItemId
from ...notation.spec import Barline, BarStyle, Chord, Clef, Event, Head, Ink, StaffSpec
from ..base import (
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
from .degree_ear import cadence, scale_context, tonic_pitch
from .rhythm import WOODBLOCK, can_start
from .scale_degrees import key_for

STEPS = 'steps'
TONIC_LEAPS = 'tonic-triad-leaps'
LEADING_TONE = 'leading-tone'
DOMINANT_LEAPS = 'dominant-leaps'
MINOR = 'minor'

Q = Duration(NoteValue.QUARTER)
H = Duration(NoteValue.HALF)
E = Duration(NoteValue.EIGHTH)
QD = Duration(NoteValue.QUARTER, 1)
HD = Duration(NoteValue.HALF, 1)

_TONIC_TRIAD = frozenset({0, 2, 4})
_DOMINANT_TRIAD = frozenset({4, 6, 1})
_MAX_LEAP = 5
"""Diatonic steps: a sixth."""
_NODE_BUDGET = 20_000
_MIN_NOTES = 4
_METERS = {'2/4': Meter(2, 4), '3/4': Meter(3, 4), '4/4': Meter(4, 4)}


@dataclass(frozen=True, slots=True)
class Grammar:
    """The melodic vocabulary of an item. Degrees are diatonic steps from the
    tonic: 0 is 1̂, -1 the leading tone below, 4 is 5̂, 7 the upper tonic."""

    mode: Mode
    low: int
    high: int
    triads: tuple[frozenset[int], ...]
    """Leaps join two tones of one of these triads (scale degrees mod 7, 0-based)."""
    penultimate: tuple[int, ...]
    requirement: Callable[[Sequence[int]], bool] | None = None

    def contains(self, degree: int) -> bool:
        return self.low <= degree <= self.high

    @property
    def starts(self) -> list[int]:
        return [d for d in range(self.low, self.high + 1) if d % 7 in _TONIC_TRIAD]


def _is_leap(a: int, b: int) -> bool:
    return abs(a - b) >= 2


def _has_leap(melody: Sequence[int]) -> bool:
    return any(_is_leap(a, b) for a, b in itertools.pairwise(melody))


def _has_leading_tone(melody: Sequence[int]) -> bool:
    return any(d % 7 == 6 for d in melody)


def _has_dominant_leap(melody: Sequence[int]) -> bool:
    return any(
        _is_leap(a, b) and {a % 7, b % 7} <= _DOMINANT_TRIAD and not {a % 7, b % 7} <= _TONIC_TRIAD
        for a, b in itertools.pairwise(melody)
    )


GRAMMARS: dict[str, Grammar] = {
    STEPS: Grammar(Mode.MAJOR, 0, 5, (), (1,)),
    TONIC_LEAPS: Grammar(Mode.MAJOR, 0, 7, (_TONIC_TRIAD,), (1,), _has_leap),
    LEADING_TONE: Grammar(Mode.MAJOR, -3, 5, (_TONIC_TRIAD,), (1, -1), _has_leading_tone),
    DOMINANT_LEAPS: Grammar(
        Mode.MAJOR, -3, 7, (_TONIC_TRIAD, _DOMINANT_TRIAD), (1, -1), _has_dominant_leap
    ),
    MINOR: Grammar(Mode.MINOR, -3, 7, (_TONIC_TRIAD,), (1, -1)),
}
VOCABULARY = tuple(GRAMMARS)
"""In teaching order."""


def _moves(grammar: Grammar, melody: Sequence[int]) -> list[tuple[int, float]]:
    """Possible next degrees with their weights."""
    current = melody[-1]
    forced: int | None = None
    if current % 7 == 6:
        forced = current + 1  # the leading tone resolves to the tonic
    if len(melody) >= 2 and _is_leap(melody[-2], current):
        back = current - 1 if current > melody[-2] else current + 1
        if forced is not None and forced != back:
            return []  # a leap up to the leading tone could not step back down
        forced = back
    if forced is not None:
        return [(forced, 1.0)] if grammar.contains(forced) else []
    result = [(current + step, 3.0) for step in (-1, 1)]
    if len(melody) < 2 or melody[-2] != current:
        result.append((current, 0.3))
    for triad in grammar.triads:
        if current % 7 not in triad:
            continue
        for target in range(current - _MAX_LEAP, current + _MAX_LEAP + 1):
            if _is_leap(current, target) and target % 7 in triad:
                result.append((target, 1.5))
    seen: dict[int, float] = {}
    for degree, weight in result:
        if grammar.contains(degree):
            seen[degree] = max(weight, seen.get(degree, 0.0))
    return list(seen.items())


def generate_melody(grammar: Grammar, length: int, rng: random.Random) -> tuple[int, ...]:
    """A melody of ``length`` degrees obeying ``grammar``, found by a randomised
    depth-first search."""
    if length < 3:
        raise ValueError('a melody needs at least three notes')
    budget = [_NODE_BUDGET]

    def ordered(options: list[tuple[int, float]]) -> list[int]:
        keyed = [(rng.random() ** (1.0 / weight), degree) for degree, weight in options]
        return [degree for _k, degree in sorted(keyed, reverse=True)]

    def search(melody: list[int]) -> list[int] | None:
        budget[0] -= 1
        if budget[0] < 0:
            return None
        position = len(melody)
        if position == length:
            if grammar.requirement is None or grammar.requirement(melody):
                return melody
            return None
        options = _moves(grammar, melody)
        if position == length - 1:
            options = [(d, w) for d, w in options if d == 0]
        elif position == length - 2:
            options = [(d, w) for d, w in options if d in grammar.penultimate]
        else:
            remaining = length - 2 - position
            options = [
                (d, w)
                for d, w in options
                if min(abs(d - p) for p in grammar.penultimate) <= _MAX_LEAP * remaining + 1
            ]
        for degree in ordered(options):
            found = search([*melody, degree])
            if found is not None:
                return found
        return None

    for start in ordered([(d, 2.0 if d % 7 == 0 else 1.0) for d in grammar.starts]):
        found = search([start])
        if found is not None:
            return tuple(found)
    raise ValueError(f'no melody of {length} notes in this vocabulary')


def spell(key: Key, tonic: Pitch, melody: Sequence[int]) -> tuple[Pitch, ...]:
    """The degrees as pitches above ``tonic``: raised 7̂, and 6̂ before it, in minor."""
    result = []
    for index, degree in enumerate(melody):
        step = degree % 7
        name = key.degree(step + 1)
        if key.mode is Mode.MINOR:
            following = melody[index + 1] % 7 if index + 1 < len(melody) else None
            if step == 6:
                name = key.leading_tone
            elif step == 5 and following == 6:
                name = key.raised(6)
        octave, letter = divmod(tonic.diatonic_index + degree, 7)
        result.append(Pitch(Letter(letter), name.alter, octave))
    return tuple(result)


# Rhythm ----------------------------------------------------------------------------

_Cell = tuple[Duration, ...]


def _cells(eighths: bool) -> list[tuple[_Cell, int]]:
    cells: list[tuple[_Cell, int]] = [((Q,), 1), ((H,), 2)]
    if eighths:
        cells += [((E, E), 1), ((QD, E), 2)]
    return cells


def _fill(
    beats: int, per_bar: int, start: int, eighths: bool, rng: random.Random
) -> list[Duration]:
    result: list[Duration] = []
    index = start
    while index < start + beats:
        free = start + beats - index
        options = [
            (cell, size)
            for cell, size in _cells(eighths)
            if size <= free and can_start(size, index, per_bar)
        ]
        weights = [1.0 if size == 1 else 0.5 for _c, size in options]
        cell, size = rng.choices(options, weights)[0]
        result.extend(cell)
        index += size
    return result


def generate_rhythm(meter: Meter, bars: int, eighths: bool, rng: random.Random) -> list[Duration]:
    """``bars`` bars of quarter-beat cells; the last bar ends on a long note."""
    per_bar = meter.beats
    best: list[Duration] = []
    for _attempt in range(30):
        rhythm: list[Duration] = []
        for _bar in range(bars - 1):
            rhythm += _fill(per_bar, per_bar, 0, eighths, rng)
        if per_bar == 3:
            rhythm += rng.choice([[HD], [*_fill(1, 3, 0, eighths, rng), H]])
        elif per_bar == 2:
            rhythm += rng.choice([[H], [Q, Q]])
        else:
            rhythm += [*_fill(2, 4, 0, eighths, rng), H]
        if len(rhythm) >= _MIN_NOTES:
            return rhythm
        if len(rhythm) > len(best):
            best = rhythm
    return best


def melody_events(
    pitches: Sequence[Pitch],
    rhythm: Sequence[Duration],
    meter: Meter,
    *,
    inks: Sequence[Ink] | None = None,
    labels: Sequence[str] | None = None,
) -> tuple[Event, ...]:
    events: list[Event] = []
    filled = Fraction(0)
    for index, (pitch, duration) in enumerate(zip(pitches, rhythm, strict=True)):
        ink = inks[index] if inks is not None else Ink.FOREGROUND
        label = labels[index] if labels is not None else None
        events.append(Chord((Head(pitch, ink=ink),), duration, label=label, ink=ink))
        filled += duration.length
        if filled % meter.bar_length == 0:
            last = index == len(pitches) - 1
            events.append(Barline(BarStyle.FINAL if last else BarStyle.SINGLE))
    return tuple(events)


def melody_playback(
    pitches: Sequence[Pitch],
    rhythm: Sequence[Duration],
    *,
    tempo: float,
    instrument: Instrument,
    offset: Fraction = Fraction(0),
) -> list[PlaybackNote]:
    notes = []
    start = offset
    for pitch, duration in zip(pitches, rhythm, strict=True):
        length = duration.quarter_length
        notes.append(PlaybackNote(pitch.midi, start, length * Fraction(9, 10), 90))
        start += length
    return notes


def _clicks(meter: Meter) -> list[PlaybackNote]:
    return [
        PlaybackNote(WOODBLOCK, Fraction(beat), Fraction(1, 4), 100 if beat == 0 else 70, True)
        for beat in range(meter.beats)
    ]


# Settings --------------------------------------------------------------------------


def _int(settings: Mapping[str, object], key: str, default: int, low: int, high: int) -> int:
    value = settings.get(key, default)
    number = int(value) if isinstance(value, int | float) else default
    return max(low, min(high, number))


def _meters(settings: Mapping[str, object]) -> list[Meter]:
    value = settings.get('meters', ('3/4', '4/4'))
    chosen = [value] if isinstance(value, str) else [str(v) for v in cast(Sequence[object], value)]
    return [_METERS[k] for k in _METERS if k in chosen] or [_METERS['4/4']]


def _clefs(settings: Mapping[str, object]) -> list[Clef]:
    choice = settings.get('clef', 'treble')
    if choice == 'bass':
        return [Clef.BASS]
    if choice == 'both':
        return [Clef.TREBLE, Clef.BASS]
    return [Clef.TREBLE]


STAFF_LOW = -3
"""Lowest staff position with one ledger line (the space below it)."""
STAFF_HIGH = 11


def compose(
    key: Key, grammar: Grammar, length: int, clef: Clef, rng: random.Random
) -> tuple[Pitch, ...]:
    """A melody of ``length`` notes that stays on the staff with at most one ledger
    line: the tonic's octave is chosen first, and the grammar's range narrowed to the
    degrees that fit, preferring the octave that leaves the widest range."""
    options = []
    for octave in range(1, 7):
        tonic = key.tonic.at(octave)
        position = clef.staff_position(tonic)
        low = max(grammar.low, STAFF_LOW - position)
        high = min(grammar.high, STAFF_HIGH - position)
        if low <= 0 <= high and any(low <= d <= high for d in grammar.penultimate):
            narrowed = replace(grammar, low=low, high=high)
            options.append((high - low + rng.random(), tonic, narrowed))
    for _width, tonic, narrowed in sorted(options, key=lambda o: o[0], reverse=True):
        try:
            melody = generate_melody(narrowed, length, rng)
        except ValueError:
            continue
        # The same melody in the octave that needs the fewest ledger lines.
        placements = []
        for octave in range(1, 7):
            pitches = spell(key, key.tonic.at(octave), melody)
            positions = [clef.staff_position(p) for p in pitches]
            if min(positions) >= STAFF_LOW and max(positions) <= STAFF_HIGH:
                ledgers = sum(1 for p in positions if p < -1 or p > 9)
                placements.append((ledgers, octave != tonic.octave, pitches))
        return min(placements, key=lambda p: (p[0], p[1]))[2]
    raise ValueError(f'no melody fits the {clef.value} staff in {key}')


def item_id(vocabulary: str) -> ItemId:
    """``dictation.melody.leading-tone``."""
    return ItemId(f'dictation.melody.{vocabulary}')


def parse_item(item: str) -> str:
    vocabulary = item.removeprefix('dictation.melody.')
    if not item.startswith('dictation.melody.') or vocabulary not in GRAMMARS:
        raise ValueError(f'not a melodic dictation item: {item!r}')
    return vocabulary


def vocabulary_name(vocabulary: str) -> str:
    return {
        STEPS: _('Stepwise melodies'),
        TONIC_LEAPS: _('Leaps in the tonic triad'),
        LEADING_TONE: _('Melodies with the leading tone'),
        DOMINANT_LEAPS: _('Leaps in the dominant triad'),
        MINOR: _('Melodies in minor'),
    }[vocabulary]


def _hint(vocabulary: str) -> str:
    return {
        STEPS: _('The melody moves by step: follow it up and down the scale from the first note.'),
        TONIC_LEAPS: _('Leaps land on 1, 3 or 5: sing the tonic chord to find them.'),
        LEADING_TONE: _('The note just below the tonic is the leading tone: it pulls up to 1.'),
        DOMINANT_LEAPS: _('Leaps may outline the dominant chord: 5, 7 and 2.'),
        MINOR: _(
            'In minor, 7 is raised to lead to the tonic, and 6 is raised on the way up to it.'
        ),
    }[vocabulary]


def degree_label(key: Key, pitch: Pitch) -> str:
    """The scale degree a pitch is written on, ``'1'``–``'7'``."""
    return str((pitch.letter - key.tonic.letter) % 7 + 1)


def _note(pitch: Pitch) -> str:
    return pitch_name(pitch.name) + str(pitch.octave)


def _as_pitches(value: object) -> list[Pitch | None]:
    """The first pitch of every slot of a staff answer; ``None`` for anything else."""
    if not isinstance(value, tuple | list):
        return []
    result: list[Pitch | None] = []
    for slot in value:
        if isinstance(slot, tuple | list) and slot and isinstance(slot[0], Pitch):
            result.append(slot[0])
        else:
            result.append(None)
    return result


class MelodicDictation(ExerciseDefinition):
    id = 'melodic-dictation'
    item_prefix = 'dictation.melody.'
    family = Family.EAR
    modality = Modality.EAR
    level = 2
    icon_name = 'melodic-dictation-symbolic'
    glyph = '♫'
    settings: ClassVar[tuple[Setting, ...]] = (
        IntSetting(
            'accidentals',
            _('Key signatures'),
            3,
            0,
            6,
            subtitle=_('Keys with up to this many sharps or flats'),
        ),
        ChoiceSetting(
            'clef',
            _('Clef'),
            (
                Option('treble', _('Treble')),
                Option('bass', _('Bass')),
                Option('both', _('Treble and bass')),
            ),
            'treble',
        ),
        MultiChoiceSetting(
            'meters',
            _('Time signatures'),
            (Option('2/4', _('2/4')), Option('3/4', _('3/4')), Option('4/4', _('4/4'))),
            ('3/4', '4/4'),
        ),
        IntSetting('bars', _('Bars'), 2, 2, 4),
        ChoiceSetting(
            'rhythm',
            _('Rhythm'),
            (
                Option('quarters', _('Quarter and half notes')),
                Option('eighths', _('With eighths and dotted quarters')),
            ),
            'quarters',
        ),
        ChoiceSetting(
            'context',
            _('Key set by'),
            (
                Option('cadence', _('Chords: I–IV–V–I')),
                Option('scale', _('The scale')),
                Option('tonic', _('The tonic chord')),
            ),
            'cadence',
        ),
        IntSetting('tempo', _('Tempo'), 72, 50, 120, subtitle=_('Beats per minute')),
        ChoiceSetting(
            'instrument',
            _('Instrument'),
            (Option('piano', _('Piano')), Option('varied', _('Varied'))),
            'piano',
        ),
    )

    @property
    def title(self) -> str:
        return _('Melodic Dictation')

    @property
    def description(self) -> str:
        return _('Hear a short melody and write it on the staff.')

    @property
    def play_label(self) -> str:
        return _('Play melody')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        bars = _int(settings, 'bars', 2, 2, 4)
        bar_text = ngettext('{count} bar', '{count} bars', bars).format(count=bars)
        meters = ', '.join(str(m) for m in _meters(settings))
        return _(' · ').join((meters, bar_text))

    def item_label(self, item_id: ItemId) -> str:
        # Translators: an item in "Weakest items", e.g. "Stepwise melodies — dictation".
        return _('{melodies} — dictation').format(melodies=vocabulary_name(parse_item(item_id)))

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        return [item_id(v) for v in VOCABULARY]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        vocabulary = parse_item(item_id)
        grammar = GRAMMARS[vocabulary]
        limit = _int(settings, 'accidentals', 3, 0, 6)
        key = key_for(grammar.mode, rng.randint(-limit, limit))
        meter = rng.choice(_meters(settings))
        bars = _int(settings, 'bars', 2, 2, 4)
        rhythm = generate_rhythm(meter, bars, settings.get('rhythm') == 'eighths', rng)
        clef = rng.choice(_clefs(settings))
        pitches = compose(key, grammar, len(rhythm), clef, rng)
        signature = key.signature
        tempo = float(_int(settings, 'tempo', 72, 50, 120))
        instrument = (
            rng.choice((Instrument.PIANO, Instrument.FLUTE, Instrument.STRINGS, Instrument.ORGAN))
            if settings.get('instrument') == 'varied'
            else Instrument.PIANO
        )
        context = self._context(key, str(settings.get('context', 'cadence')))
        context = replace(context, tempo=tempo, instrument=instrument)
        bar_beats = Fraction(meter.beats)
        melody = PlaybackSpec(
            (
                *_clicks(meter),
                *melody_playback(
                    pitches, rhythm, tempo=tempo, instrument=instrument, offset=bar_beats
                ),
            )
        )
        playback = PlaybackSpec.sequence(context, melody)
        written = StaffSpec(
            clef=clef,
            key_signature=signature,
            meter=meter,
            events=melody_events(pitches, rhythm, meter),
        )
        given = StaffSpec(
            clef=clef,
            key_signature=signature,
            meter=meter,
            events=(Chord((Head(pitches[0]),), rhythm[0]),),
        )
        count = len(pitches)
        bar_text = ngettext('{count} bar', '{count} bars', bars).format(count=bars)
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Write the melody you hear'),
            answer=StaffInputAnswer(
                clef=clef,
                key_signature=signature,
                slots=count - 1,
                given=given,
                rhythm=tuple(rhythm[1:]),
            ),
            expected=tuple((p,) for p in pitches[1:]),
            figure=written,
            playback=playback,
            playback_is_question=True,
            playback_style_choice=False,
            # As in rhythm dictation, the written alternative is the melody itself:
            # without sound the learner copies and reads instead of hearing.
            written_alternative=written,
            # Translators: e.g. "D major · 3/4 · 2 bars".
            context=_('{key} · {meter} · {bars}').format(
                key=key_name(key), meter=meter, bars=bar_text
            ),
            hint=_hint(vocabulary),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        answer = question.answer
        assert isinstance(answer, StaffInputAnswer)
        figure = question.written_alternative
        assert isinstance(figure, StaffSpec)
        assert figure.meter is not None
        expected = [slot[0] for slot in cast(tuple[tuple[Pitch, ...], ...], question.expected)]
        written = _as_pitches(given)
        written += [None] * (len(expected) - len(written))
        matches = [w == e for w, e in zip(written, expected, strict=False)]
        if len(written) > len(expected):
            matches[-1] = False
        right, total = sum(matches), len(expected)
        score = right / total
        correct = right == total and len(written) == total
        if correct:
            title = _('Correct — every note right')
        elif score >= 0.75:
            title = ngettext(
                'Nearly — {right} of {total} note right',
                'Nearly — {right} of {total} notes right',
                total,
            ).format(right=right, total=total)
        else:
            title = ngettext(
                'Not quite — {right} of {total} note right',
                'Not quite — {right} of {total} notes right',
                total,
            ).format(right=right, total=total)
        melody = [self._first(question), *expected]
        key = self._key(question)
        degrees = [degree_label(key, p) for p in melody]
        sentences: list[str] = []
        for index, (ok, wrote, right_pitch) in enumerate(
            zip(matches, written, expected, strict=False)
        ):
            if ok:
                continue
            if len(sentences) == 3:
                break
            sentences.append(self._mistake(index + 2, right_pitch, wrote, degrees[index + 1]))
        # Translators: e.g. "The melody in scale degrees: 1 2 3 2 1."
        sentences.append(
            _('The melody in scale degrees: {degrees}.').format(degrees=' '.join(degrees))
        )
        rhythm = [e.duration for e in figure.events if isinstance(e, Chord) and e.duration]
        inks = [Ink.FOREGROUND] + [Ink.FOREGROUND if ok else Ink.ACCENT for ok in matches]
        playback = question.playback
        assert playback is not None
        play_expected = PlaybackSpec(
            tuple(
                melody_playback(
                    melody, rhythm, tempo=playback.tempo, instrument=playback.instrument
                )
            ),
            playback.tempo,
            playback.instrument,
        )
        play_given = None
        if any(w is not None for w in written[:total]):
            heard = [melody[0], *written[:total]]
            notes = [
                n
                for n, pitch in zip(
                    melody_playback(
                        [p or melody[0] for p in heard],
                        rhythm,
                        tempo=playback.tempo,
                        instrument=playback.instrument,
                    ),
                    heard,
                    strict=True,
                )
                if pitch is not None
            ]
            play_given = PlaybackSpec(tuple(notes), playback.tempo, playback.instrument)
        return Feedback(
            correct=correct,
            title=title,
            detail=' '.join(sentences),
            expected_label=self.answer_label(question, question.expected),
            score=score,
            figure=replace(
                figure,
                events=melody_events(melody, rhythm, figure.meter, inks=inks, labels=degrees),
                description=None,
            ),
            play_expected=play_expected,
            play_given=play_given,
        )

    def answer_label(self, question: Question, value: object) -> str:
        pitches = _as_pitches(value)
        if not pitches:
            return _('Nothing written')
        # Translators: separator between note names in a list such as "G4, E5".
        return _(', ').join(_note(p) if p is not None else '?' for p in pitches)

    def serialize(self, value: object) -> str:
        return ' '.join(str(p) if p is not None else '-' for p in _as_pitches(value))

    # Helpers

    @staticmethod
    def _context(key: Key, kind: str) -> PlaybackSpec:
        tonic = tonic_pitch(key)
        if kind == 'scale':
            return scale_context(key, tonic)
        if kind == 'tonic':
            triad = key.triad(1).pitches(tonic.octave)
            return PlaybackSpec.harmonic(triad, length=Fraction(2))
        return cadence(key, tonic)

    @staticmethod
    def _first(question: Question) -> Pitch:
        answer = question.answer
        assert isinstance(answer, StaffInputAnswer)
        assert isinstance(answer.given, StaffSpec)
        event = answer.given.events[0]
        assert isinstance(event, Chord)
        return event.heads[0].pitch

    @staticmethod
    def _key(question: Question) -> Key:
        mode = GRAMMARS[parse_item(question.item_id)].mode
        answer = question.answer
        assert isinstance(answer, StaffInputAnswer)
        assert answer.key_signature is not None
        return key_for(mode, answer.key_signature.fifths)

    @staticmethod
    def _mistake(number: int, right: Pitch, wrote: Pitch | None, degree: str) -> str:
        if wrote is None:
            # Translators: e.g. "Note 3 is E4 (scale degree 3); nothing was written."
            return _(
                'Note {number} is {right} (scale degree {degree}); nothing was written.'
            ).format(number=number, right=_note(right), degree=degree)
        if wrote.midi == right.midi:
            # Translators: e.g. "Note 3 is F♯4; you wrote G♭4, the same key with another name."
            return _(
                'Note {number} is {right}; you wrote {wrote}, the same key with another name.'
            ).format(number=number, right=_note(right), wrote=_note(wrote))
        if wrote.name == right.name:
            # Translators: e.g. "Note 3 is E4; you wrote E5, in the wrong octave."
            return _('Note {number} is {right}; you wrote {wrote}, in the wrong octave.').format(
                number=number, right=_note(right), wrote=_note(wrote)
            )
        # Translators: e.g. "Note 3 is E4 (scale degree 3); you wrote F4."
        return _('Note {number} is {right} (scale degree {degree}); you wrote {wrote}.').format(
            number=number, right=_note(right), degree=degree, wrote=_note(wrote)
        )


EXERCISES: tuple[ExerciseDefinition, ...] = (MelodicDictation(),)
