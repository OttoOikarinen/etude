# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Rhythm: tap a written rhythm, write down a heard one, name note values and
hear the meter.

Rhythms are built beat by beat from *cells*, small figures that fill one or
more felt beats (``♪♪`` fills a quarter-note beat, ``♩. ♪`` two of them).
Cells start only where they keep the beat visible (a half note in 4/4
starts on beat 1 or 3), so every bar is full and beams follow the meter's
beat groups. The items of the tapping and dictation exercises are the
rhythmic *vocabulary* a rhythm practises (eighths, dotted quarters, rests…):
the meter, tempo and the other cells around the practised one vary from
question to question.

Tapped rhythms are graded with :func:`etude.audio.latency.grade_taps`; the
learner's taps arrive latency-compensated (see ``etude.ui.widgets.tap_pad``).
Dictation is graded beat by beat on a sixteenth-note grid of attacks,
sustains and silences, so rhythms that sound the same (a half rest or two
quarter rests) count as the same answer.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping, Sequence
from enum import Enum
from fractions import Fraction
from gettext import gettext as _
from gettext import ngettext
from typing import cast

from ...audio.latency import TapGrade, TapResult, grade_taps
from ...audio.spec import PlaybackNote, PlaybackSpec
from ...core import Duration, Meter, NoteValue, Pitch
from ...learning.model import ItemId
from ...learning.rating import PARTIAL_CREDIT_PASS
from ...notation.spec import Barline, BarStyle, Chord, Clef, Event, Head, Ink, Rest, StaffSpec
from ..base import (
    BoolSetting,
    ChoiceAnswer,
    ExerciseDefinition,
    Family,
    Feedback,
    IntSetting,
    Modality,
    MultiChoiceSetting,
    Option,
    Question,
    RhythmInputAnswer,
    TapAnswer,
)

RhythmEvent = tuple[Duration, bool]
"""A note or, when the flag is set, a rest."""
Rhythm = tuple[RhythmEvent, ...]

W = Duration(NoteValue.WHOLE)
H = Duration(NoteValue.HALF)
Q = Duration(NoteValue.QUARTER)
E = Duration(NoteValue.EIGHTH)
S = Duration(NoteValue.SIXTEENTH)
WD = Duration(NoteValue.WHOLE, 1)
HD = Duration(NoteValue.HALF, 1)
QD = Duration(NoteValue.QUARTER, 1)
ED = Duration(NoteValue.EIGHTH, 1)

LINE_PITCH = Pitch.parse('E4')
"""Pitch written on the line of a one-line percussion staff."""
WOODBLOCK = 76
"""GM percussion key of a high wood block."""
GRID = Fraction(1, 16)
"""Dictation is compared on a grid of sixteenths."""
MAX_TRIES = 50


def note(duration: Duration) -> RhythmEvent:
    return (duration, False)


def rest(duration: Duration) -> RhythmEvent:
    return (duration, True)


# Vocabulary --------------------------------------------------------------------


class Vocabulary(Enum):
    """What a rhythm practises, in teaching order. Values are item id parts."""

    QUARTERS = 'quarters'
    HALVES = 'halves'
    EIGHTHS = 'eighths'
    RESTS = 'rests'
    DOTTED = 'dotted-quarter'
    SIXTEENTHS = 'sixteenths'
    SYNCOPATION = 'syncopation'


def _cells(*cells: Sequence[Duration | RhythmEvent]) -> tuple[Rhythm, ...]:
    return tuple(tuple(e if isinstance(e, tuple) else note(e) for e in cell) for cell in cells)


# Per vocabulary: the cells it practises (one appears in every rhythm) and the
# familiar cells that fill the rest of the bars. Simple meters count quarter
# beats, compound meters dotted-quarter beats.
SIMPLE_CELLS: dict[Vocabulary, tuple[tuple[Rhythm, ...], tuple[Rhythm, ...]]] = {
    Vocabulary.QUARTERS: (_cells((Q,)), _cells((Q,))),
    Vocabulary.HALVES: (_cells((H,), (HD,), (W,)), _cells((Q,))),
    Vocabulary.EIGHTHS: (_cells((E, E)), _cells((Q,), (H,))),
    Vocabulary.RESTS: (
        _cells((rest(Q),), (rest(H),), (rest(E), E), (E, rest(E))),
        _cells((Q,), (E, E), (H,)),
    ),
    Vocabulary.DOTTED: (_cells((QD, E)), _cells((Q,), (E, E), (H,))),
    Vocabulary.SIXTEENTHS: (_cells((S, S, S, S), (E, S, S), (S, S, E)), _cells((Q,), (E, E))),
    Vocabulary.SYNCOPATION: (_cells((E, Q, E), (Q, H, Q)), _cells((Q,), (E, E))),
}
COMPOUND_CELLS: dict[Vocabulary, tuple[tuple[Rhythm, ...], tuple[Rhythm, ...]]] = {
    Vocabulary.QUARTERS: (_cells((QD,)), _cells((QD,))),
    Vocabulary.HALVES: (_cells((HD,), (WD,)), _cells((QD,))),
    Vocabulary.EIGHTHS: (_cells((E, E, E), (Q, E)), _cells((QD,))),
    Vocabulary.RESTS: (
        _cells((rest(QD),), (Q, rest(E)), (rest(E), E, E)),
        _cells((QD,), (E, E, E), (Q, E)),
    ),
    Vocabulary.DOTTED: (_cells((ED, S, E)), _cells((QD,), (E, E, E), (Q, E))),
    Vocabulary.SIXTEENTHS: (
        _cells((S, S, E, E), (E, S, S, E), (E, E, S, S)),
        _cells((QD,), (E, E, E), (Q, E)),
    ),
    Vocabulary.SYNCOPATION: (_cells((E, Q)), _cells((QD,), (E, E, E))),
}


def vocabulary_name(vocabulary: Vocabulary) -> str:
    match vocabulary:
        case Vocabulary.QUARTERS:
            return _('Quarter notes')
        case Vocabulary.HALVES:
            return _('Half and whole notes')
        case Vocabulary.EIGHTHS:
            return _('Eighth notes')
        case Vocabulary.RESTS:
            return _('Rests')
        case Vocabulary.DOTTED:
            return _('Dotted rhythms')
        case Vocabulary.SIXTEENTHS:
            return _('Sixteenth notes')
        case Vocabulary.SYNCOPATION:
            return _('Syncopation')


def _vocabulary_options(choices: Iterable[Vocabulary]) -> tuple[Option, ...]:
    return tuple(Option(v.value, vocabulary_name(v)) for v in choices)


def _vocabulary_hint(vocabulary: Vocabulary) -> str:
    match vocabulary:
        case Vocabulary.QUARTERS:
            return _('One sound on every beat: count “1, 2, 3, 4” and tap with each number.')
        case Vocabulary.HALVES:
            return _('A half note lasts two beats: tap on the first and keep counting.')
        case Vocabulary.EIGHTHS:
            return _('Two eighths share one beat: count “1 and 2 and” and tap on both.')
        case Vocabulary.RESTS:
            return _('Rests are counted silently: keep the beat going, but do not tap.')
        case Vocabulary.DOTTED:
            return _('A dot adds half the value: a dotted quarter lasts a beat and a half.')
        case Vocabulary.SIXTEENTHS:
            return _('Four sixteenths fill one beat: count “1 e and a”.')
        case Vocabulary.SYNCOPATION:
            return _('Syncopated notes start between beats: count the “and” out loud.')


# Meters ------------------------------------------------------------------------

METERS = {'2/4': Meter(2, 4), '3/4': Meter(3, 4), '4/4': Meter(4, 4), '6/8': Meter(6, 8)}


def _meter_options() -> tuple[Option, ...]:
    return (
        Option('2/4', _('2/4')),
        Option('3/4', _('3/4')),
        Option('4/4', _('4/4')),
        # Translators: a time signature option; compound time has dotted-quarter beats.
        Option('6/8', _('6/8 (compound)')),
    )


def pulses_per_bar(meter: Meter) -> int:
    return len(meter.groups)


def quarter_tempo(meter: Meter, beats_per_minute: float) -> float:
    """Quarter notes per minute when ``meter``'s felt beats go at ``beats_per_minute``."""
    return beats_per_minute * float(meter.pulse * 4)


def _selected(settings: Mapping[str, object], key: str, default: Sequence[str]) -> list[str]:
    value = settings.get(key, default)
    if isinstance(value, str):
        value = (value,)
    return [str(v) for v in cast(Sequence[object], value)]


def _meters(settings: Mapping[str, object], default: Sequence[str]) -> list[Meter]:
    return [METERS[k] for k in _selected(settings, 'meters', default) if k in METERS] or [
        METERS['4/4']
    ]


def _int(settings: Mapping[str, object], key: str, default: int) -> int:
    value = settings.get(key, default)
    return int(cast(int, value)) if isinstance(value, int | float | str) else default


def _tempo_range(settings: Mapping[str, object], low: int, high: int) -> tuple[int, int]:
    a, b = _int(settings, 'tempo-min', low), _int(settings, 'tempo-max', high)
    return (a, b) if a <= b else (b, a)


def _bars(settings: Mapping[str, object], default: int) -> int:
    return max(1, min(2, _int(settings, 'bars', default)))


def _tempo_settings(low: int, high: int) -> tuple[IntSetting, IntSetting]:
    return (
        IntSetting('tempo-min', _('Slowest tempo'), low, 40, 160, subtitle=_('Beats per minute')),
        IntSetting('tempo-max', _('Fastest tempo'), high, 40, 160, subtitle=_('Beats per minute')),
    )


def _describe_meters_and_tempo(meters: Sequence[Meter], tempo: tuple[int, int]) -> str:
    names = ', '.join(str(m) for m in meters)
    low, high = tempo
    if low == high:
        # Translators: e.g. "80 BPM" (beats per minute).
        speed = _('{bpm} BPM').format(bpm=low)
    else:
        # Translators: e.g. "70–90 BPM" (beats per minute).
        speed = _('{low}–{high} BPM').format(low=low, high=high)
    return f'{names} · {speed}'


# Generating rhythms --------------------------------------------------------------


def rhythm_length(rhythm: Iterable[RhythmEvent]) -> Fraction:
    """Length in whole notes."""
    return sum((d.length for d, _r in rhythm), Fraction(0))


def cell_pulses(cell: Rhythm, meter: Meter) -> int | None:
    """Beats a cell fills in ``meter``, or ``None`` if it does not fill whole beats."""
    count = rhythm_length(cell) / meter.pulse
    return int(count) if count.denominator == 1 else None


def can_start(pulses: int, index: int, per_bar: int) -> bool:
    """Whether a cell of ``pulses`` beats may start on beat ``index`` (0-based) of a
    bar of ``per_bar`` beats, keeping the middle of an even bar visible."""
    if index + pulses > per_bar:
        return False
    if pulses == 1:
        return True
    if pulses == 2:
        return per_bar % 2 == 1 or index % 2 == 0
    return index == 0


def _cell_table(meter: Meter) -> dict[Vocabulary, tuple[tuple[Rhythm, ...], tuple[Rhythm, ...]]]:
    return COMPOUND_CELLS if meter.is_compound else SIMPLE_CELLS


def generate_rhythm(vocabulary: Vocabulary, meter: Meter, bars: int, rng: random.Random) -> Rhythm:
    """``bars`` full bars of ``meter`` that use at least one cell of ``vocabulary``.

    Every bar has a note, and no cell hides the middle of an even bar.
    """
    if len(set(meter.groups)) != 1:
        raise ValueError(f'irregular meters are not supported: {meter}')
    per_bar = pulses_per_bar(meter)
    focal, fillers = _cell_table(meter)[vocabulary]

    def sized(cells: Iterable[Rhythm]) -> list[tuple[Rhythm, int]]:
        result = []
        for cell in cells:
            pulses = cell_pulses(cell, meter)
            if pulses is not None and pulses <= per_bar:
                result.append((cell, pulses))
        return result

    focal_cells, pool = sized(focal), sized((*focal, *fillers))
    places = [
        (cell, pulses, bar, index)
        for cell, pulses in focal_cells
        for bar in range(bars)
        for index in range(per_bar)
        if can_start(pulses, index, per_bar)
    ]
    if not places:
        raise ValueError(f'{vocabulary.value} has no cell that fits {meter}')
    rhythm: Rhythm = ()
    for _attempt in range(MAX_TRIES):
        cell, pulses, focal_bar, focal_index = rng.choice(places)
        rhythm = ()
        for bar in range(bars):
            slots: list[Rhythm | None] = [None] * per_bar
            if bar == focal_bar:
                slots[focal_index] = cell
                for i in range(focal_index + 1, focal_index + pulses):
                    slots[i] = ()
            index = 0
            while index < per_bar:
                placed = slots[index]
                if placed is not None:
                    rhythm += placed
                    index += 1
                    continue
                free = 0
                while index + free < per_bar and slots[index + free] is None:
                    free += 1
                options = [(c, p) for c, p in pool if p <= free and can_start(p, index, per_bar)]
                chosen, size = rng.choice(options)
                rhythm += chosen
                index += size
        if _acceptable(rhythm, meter):
            return rhythm
    return rhythm


def split_bars(rhythm: Rhythm, meter: Meter) -> list[Rhythm]:
    """The rhythm bar by bar; an unfinished last bar is returned as it is."""
    bars: list[Rhythm] = []
    current: Rhythm = ()
    filled = Fraction(0)
    for event in rhythm:
        current += (event,)
        filled += event[0].length
        if filled >= meter.bar_length:
            bars.append(current)
            current, filled = (), Fraction(0)
    if current:
        bars.append(current)
    return bars


def _acceptable(rhythm: Rhythm, meter: Meter) -> bool:
    bars = split_bars(rhythm, meter)
    return all(any(not is_rest for _d, is_rest in bar) for bar in bars)


def onsets(rhythm: Rhythm) -> tuple[Fraction, ...]:
    """Start of every note (not rest), in quarter-note beats."""
    result = []
    position = Fraction(0)
    for duration, is_rest in rhythm:
        if not is_rest:
            result.append(position)
        position += duration.quarter_length
    return tuple(result)


# Engraving and describing ---------------------------------------------------------


def duration_name(duration: Duration, is_rest: bool = False) -> str:
    """E.g. "dotted quarter note" or "eighth rest"."""
    dotted = duration.dots > 0
    value = duration.value
    if is_rest:
        names = {
            NoteValue.WHOLE: (_('whole rest'), _('dotted whole rest')),
            NoteValue.HALF: (_('half rest'), _('dotted half rest')),
            NoteValue.QUARTER: (_('quarter rest'), _('dotted quarter rest')),
            NoteValue.EIGHTH: (_('eighth rest'), _('dotted eighth rest')),
            NoteValue.SIXTEENTH: (_('sixteenth rest'), _('dotted sixteenth rest')),
        }
    else:
        names = {
            NoteValue.WHOLE: (_('whole note'), _('dotted whole note')),
            NoteValue.HALF: (_('half note'), _('dotted half note')),
            NoteValue.QUARTER: (_('quarter note'), _('dotted quarter note')),
            NoteValue.EIGHTH: (_('eighth note'), _('dotted eighth note')),
            NoteValue.SIXTEENTH: (_('sixteenth note'), _('dotted sixteenth note')),
        }
    pair = names.get(value)
    if pair is None:
        return str(duration.length)
    return pair[1] if dotted else pair[0]


def sentence_case(text: str) -> str:
    return text[:1].upper() + text[1:]


def rhythm_words(rhythm: Rhythm, meter: Meter | None = None) -> str:
    """E.g. "quarter note, quarter note, half note, bar line, whole note"."""
    bars = split_bars(rhythm, meter) if meter is not None else [rhythm]
    parts = [', '.join(duration_name(d, r) for d, r in bar) for bar in bars]
    # Translators: separates the bars of a rhythm read out in words.
    return _(', bar line, ').join(parts)


def _event(duration: Duration, is_rest: bool, ink: Ink, pitch: Pitch = LINE_PITCH) -> Event:
    if is_rest:
        return Rest(duration, ink)
    return Chord((Head(pitch, ink=ink),), duration, ink=ink)


def rhythm_events(
    rhythm: Rhythm, meter: Meter, inks: Sequence[Ink] | None = None, *, final: bool = True
) -> tuple[Event, ...]:
    """Notes and rests with a bar line after every full bar (the last one final)."""
    events: list[Event] = []
    filled = Fraction(0)
    total = rhythm_length(rhythm)
    position = Fraction(0)
    for index, (duration, is_rest) in enumerate(rhythm):
        ink = inks[index] if inks is not None and index < len(inks) else Ink.FOREGROUND
        events.append(_event(duration, is_rest, ink))
        filled += duration.length
        position += duration.length
        if filled >= meter.bar_length:
            filled = Fraction(0)
            last = position >= total
            events.append(Barline(BarStyle.FINAL if last and final else BarStyle.SINGLE))
    return tuple(events)


def rhythm_figure(
    rhythm: Rhythm,
    meter: Meter,
    *,
    inks: Sequence[Ink] | None = None,
    show_meter: bool = True,
    description: str | None = None,
) -> StaffSpec:
    """The rhythm on a one-line percussion staff."""
    if description is None:
        description = describe_rhythm(rhythm, meter, show_meter=show_meter)
    return StaffSpec(
        clef=Clef.PERCUSSION,
        lines=1,
        meter=meter if show_meter else None,
        events=rhythm_events(rhythm, meter, inks),
        description=description,
    )


def describe_rhythm(rhythm: Rhythm, meter: Meter, *, show_meter: bool = True) -> str:
    """Accessible description: the durations in words, bar by bar."""
    words = rhythm_words(rhythm, meter)
    if show_meter:
        # Translators: e.g. "Rhythm in 4/4 time: quarter note, half note, …".
        return _('Rhythm in {meter} time: {words}.').format(meter=meter, words=words)
    # Translators: a rhythm shown without its time signature.
    return _('Rhythm without a time signature: {words}.').format(words=words)


def rhythm_from_figure(figure: object) -> Rhythm:
    """The notes and rests of a figure built by :func:`rhythm_figure`."""
    if not isinstance(figure, StaffSpec):
        return ()
    result: list[RhythmEvent] = []
    for event in figure.events:
        if isinstance(event, Rest):
            result.append(rest(event.duration))
        elif isinstance(event, Chord) and event.duration is not None:
            result.append(note(event.duration))
    return tuple(result)


def as_rhythm(value: object) -> Rhythm:
    """A rhythm answer value, or ``()`` when ``value`` is not one."""
    if not isinstance(value, tuple | list):
        return ()
    result: list[RhythmEvent] = []
    for entry in value:
        if (
            isinstance(entry, tuple | list)
            and len(entry) == 2
            and isinstance(entry[0], Duration)
            and isinstance(entry[1], bool)
        ):
            result.append((entry[0], entry[1]))
        else:
            return ()
    return tuple(result)


def as_taps(value: object) -> tuple[float, ...]:
    if not isinstance(value, tuple | list):
        return ()
    taps = []
    for entry in value:
        if isinstance(entry, int | float) and not isinstance(entry, bool):
            taps.append(float(entry))
    return tuple(taps)


def serialize_rhythm(rhythm: Rhythm) -> str:
    """Compact form for the attempt log: ``4 8 8 r4 2.`` (denominator, dots, r = rest)."""
    tokens = []
    for duration, is_rest in rhythm:
        denominator = duration.value.value.denominator
        token = f'{denominator}{"." * duration.dots}'
        tokens.append(f'r{token}' if is_rest else token)
    return ' '.join(tokens)


def _percussion_playback(
    rhythm: Rhythm, meter: Meter, tempo: float, *, count_in: bool = True, key: int = WOODBLOCK
) -> PlaybackSpec:
    notes = tuple(
        PlaybackNote(key, start, Fraction(1, 4), 100, percussion=True) for start in onsets(rhythm)
    )
    return PlaybackSpec(
        notes,
        tempo,
        count_in=pulses_per_bar(meter) if count_in else 0,
        meter=meter,
        duration=rhythm_length(rhythm) * 4,
    )


def _melodic_playback(rhythm: Rhythm, meter: Meter, tempo: float, midi: int) -> PlaybackSpec:
    """The rhythm on one pitch; notes are slightly detached so repeated notes are heard."""
    notes = []
    position = Fraction(0)
    for duration, is_rest in rhythm:
        length = duration.quarter_length
        if not is_rest:
            held = max(length - min(Fraction(1, 8), length / 4), Fraction(1, 16))
            notes.append(PlaybackNote(midi, position, held, 90))
        position += length
    return PlaybackSpec(
        tuple(notes),
        tempo,
        count_in=pulses_per_bar(meter),
        meter=meter,
        duration=position,
    )


def _ms_to_beats(ms: float, tempo: float) -> Fraction:
    return Fraction(ms * tempo / 60_000.0).limit_denominator(960)


def _vocab_item(item: str, prefix: str) -> Vocabulary:
    if not item.startswith(prefix):
        raise ValueError(f'not an item of this exercise: {item!r}')
    return Vocabulary(item.removeprefix(prefix))


def _join_numbers(numbers: Sequence[int]) -> str:
    # Translators: separator in a list of note numbers, "3, 5, 6".
    return _(', ').join(str(n) for n in numbers)


# Rhythm Reading — Tap ----------------------------------------------------------------

TAP_VOCABULARY = tuple(Vocabulary)
TAP_DEFAULT = tuple(v.value for v in Vocabulary if v is not Vocabulary.SYNCOPATION)


class RhythmTap(ExerciseDefinition):
    """Read a one- or two-bar rhythm and tap it on Space after a count-in.

    The visual metronome counts in and keeps the beat even without sound,
    so the task works for learners who cannot hear the click.
    """

    id = 'rhythm-tap'
    item_prefix = 'rhythm.tap.'
    family = Family.RHYTHM
    modality = Modality.TAP
    level = 1
    icon_name = 'rhythm-symbolic'
    glyph = '♩'
    settings = (
        MultiChoiceSetting(
            'vocabulary', _('Rhythms'), _vocabulary_options(TAP_VOCABULARY), TAP_DEFAULT
        ),
        MultiChoiceSetting('meters', _('Time signatures'), _meter_options(), ('2/4', '3/4', '4/4')),
        IntSetting('bars', _('Bars'), 2, 1, 2),
        *_tempo_settings(70, 90),
        BoolSetting(
            'click',
            _('Metronome while tapping'),
            True,
            subtitle=_('Keep the click going after the count-in'),
        ),
    )

    @property
    def title(self) -> str:
        return _('Rhythm Reading — Tap')

    @property
    def description(self) -> str:
        return _('Read a rhythm and tap it in time with the metronome.')

    @property
    def play_label(self) -> str:
        return _('Play rhythm')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        return _describe_meters_and_tempo(
            _meters(settings, ('2/4', '3/4', '4/4')), _tempo_range(settings, 70, 90)
        )

    def item_label(self, item_id: ItemId) -> str:
        vocabulary = _vocab_item(item_id, self.item_prefix)
        # Translators: an item in "Weakest items", e.g. "Eighth notes — tapping".
        return _('{rhythm} — tapping').format(rhythm=vocabulary_name(vocabulary))

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        chosen = set(_selected(settings, 'vocabulary', TAP_DEFAULT))
        return [ItemId(f'{self.item_prefix}{v.value}') for v in TAP_VOCABULARY if v.value in chosen]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        vocabulary = _vocab_item(item_id, self.item_prefix)
        meter = rng.choice(_meters(settings, ('2/4', '3/4', '4/4')))
        low, high = _tempo_range(settings, 70, 90)
        bpm = rng.randint(low, high)
        tempo = quarter_tempo(meter, bpm)
        bars = _bars(settings, 2)
        rhythm = generate_rhythm(vocabulary, meter, bars, rng)
        playback = _percussion_playback(rhythm, meter, tempo)
        expected = tuple(playback.beats_to_ms(start) for start in onsets(rhythm))
        click = bool(settings.get('click', True))
        beat = '♩.' if meter.is_compound else '♩'
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Tap this rhythm after the count-in'),
            answer=TapAnswer(meter, tempo, pulses_per_bar(meter), bars=bars, click=click),
            expected=expected,
            figure=rhythm_figure(rhythm, meter),
            playback=playback,
            # Translators: the tempo of a rhythm, e.g. "4/4 · ♩ = 80".
            context=_('{meter} · {beat} = {bpm}').format(meter=meter, beat=beat, bpm=bpm),
            hint=_vocabulary_hint(vocabulary),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        answer = cast(TapAnswer, question.answer)
        expected = cast(tuple[float, ...], question.expected)
        result = grade_taps(expected, as_taps(given), tempo=answer.tempo)
        score = result.score
        correct = score >= PARTIAL_CREDIT_PASS
        total = len(result.matches)
        good = result.good
        if result.perfect:
            title = _('Correct — every note on time')
        elif correct:
            title = ngettext(
                'Correct — {good} of {total} note on time',
                'Correct — {good} of {total} notes on time',
                total,
            ).format(good=good, total=total)
        else:
            title = ngettext(
                'Not quite — {good} of {total} note on time',
                'Not quite — {good} of {total} notes on time',
                total,
            ).format(good=good, total=total)
        rhythm = rhythm_from_figure(question.figure)
        inks = self._inks(rhythm, result)
        figure = question.figure
        if isinstance(figure, StaffSpec) and rhythm:
            figure = rhythm_figure(rhythm, answer.meter, inks=inks)
        return Feedback(
            correct=correct,
            title=title,
            detail=tap_explanation(result),
            expected_label=self.answer_label(question, question.expected),
            score=score,
            figure=figure,
            play_expected=question.playback,
            play_given=self._taps_playback(question, as_taps(given)),
        )

    def answer_label(self, question: Question, value: object) -> str:
        if value == question.expected:
            rhythm = rhythm_from_figure(question.figure)
            if rhythm:
                return sentence_case(rhythm_words(rhythm))
        count = len(as_taps(value))
        return ngettext('{count} tap', '{count} taps', count).format(count=count)

    def serialize(self, value: object) -> str:
        return ' '.join(f'{t:.0f}' for t in as_taps(value))

    @staticmethod
    def _inks(rhythm: Rhythm, result: TapResult) -> list[Ink]:
        grades = iter(result.matches)
        inks = []
        for _duration, is_rest in rhythm:
            if is_rest:
                inks.append(Ink.FOREGROUND)
                continue
            match = next(grades, None)
            if match is None or match.grade is TapGrade.OK:
                inks.append(Ink.FOREGROUND)
            elif match.grade is TapGrade.GOOD:
                inks.append(Ink.SUCCESS)
            else:
                inks.append(Ink.ERROR)
        return inks

    @staticmethod
    def _taps_playback(question: Question, taps: tuple[float, ...]) -> PlaybackSpec | None:
        playback = question.playback
        if playback is None or not taps:
            return None
        notes = tuple(
            PlaybackNote(
                WOODBLOCK,
                max(Fraction(0), _ms_to_beats(t, playback.tempo)),
                Fraction(1, 4),
                100,
                percussion=True,
            )
            for t in taps
        )
        return PlaybackSpec(
            notes,
            playback.tempo,
            count_in=playback.count_in,
            meter=playback.meter,
            duration=playback.duration,
        )


def tap_explanation(result: TapResult) -> str:
    """Which notes were early, late or missed, the learner's tendency and the windows."""
    early = [i + 1 for i, m in enumerate(result.matches) if _off(m.error_ms, result) < 0]
    late = [i + 1 for i, m in enumerate(result.matches) if _off(m.error_ms, result) > 0]
    missed = [i + 1 for i, m in enumerate(result.matches) if m.grade is TapGrade.MISSED]
    sentences = []
    if early:
        sentences.append(
            ngettext(
                'A little early: note {notes}.', 'A little early: notes {notes}.', len(early)
            ).format(notes=_join_numbers(early))
        )
    if late:
        sentences.append(
            ngettext(
                'A little late: note {notes}.', 'A little late: notes {notes}.', len(late)
            ).format(notes=_join_numbers(late))
        )
    if missed:
        sentences.append(
            ngettext('No tap near note {notes}.', 'No tap near notes {notes}.', len(missed)).format(
                notes=_join_numbers(missed)
            )
        )
    if result.extra:
        sentences.append(
            ngettext(
                '{count} tap matched no note.', '{count} taps matched no note.', result.extra
            ).format(count=result.extra)
        )
    mean = result.mean_error_ms
    if mean is not None and abs(mean) >= 25:
        if mean > 0:
            sentences.append(
                _(
                    'On average you tapped {ms} ms late: listen for the click and tap with it.'
                ).format(ms=round(mean))
            )
        else:
            sentences.append(
                _('On average you tapped {ms} ms early: wait for each beat.').format(
                    ms=round(-mean)
                )
            )
    sentences.append(
        _(
            'Taps within {good} ms of a note are on time; within {ok} ms, a little early or late.'
        ).format(good=round(result.good_ms), ok=round(result.ok_ms))
    )
    return ' '.join(sentences)


def _off(error: float | None, result: TapResult) -> int:
    """-1 for a tap a little early, 1 for a little late, 0 otherwise."""
    if error is None or abs(error) <= result.good_ms:
        return 0
    return 1 if error > 0 else -1


# Rhythm Dictation -----------------------------------------------------------------------

DICTATION_VOCABULARY = tuple(v for v in Vocabulary if v is not Vocabulary.QUARTERS)
DICTATION_DEFAULT = ('halves', 'eighths', 'rests', 'dotted-quarter')
DICTATION_PITCHES = (67, 69, 72, 74)
"""G4, A4, C5, D5: the pitch varies, the rhythm is the question."""


def palette_for(vocabularies: Iterable[Vocabulary], meter: Meter) -> tuple[Duration, ...]:
    """The durations the dictation answer offers: those of the vocabularies' cells
    plus half, quarter and eighth notes, longest first, none longer than a bar."""
    table = _cell_table(meter)
    durations = {Q, E} | ({H} if not meter.is_compound else {QD})
    for vocabulary in vocabularies:
        focal, fillers = table[vocabulary]
        for cell in (*focal, *fillers):
            durations.update(d for d, _r in cell)
    fitting = [d for d in durations if d.length <= meter.bar_length]
    return tuple(sorted(fitting, key=lambda d: d.length, reverse=True))


def sound_grid(rhythm: Rhythm, cells: int) -> list[str]:
    """``cells`` sixteenths of the rhythm: ``A`` attack, ``S`` sustain, ``R`` rest,
    ``-`` nothing written (an unfinished answer)."""
    grid: list[str] = []
    for duration, is_rest in rhythm:
        count = duration.length / GRID
        steps = int(count) if count.denominator == 1 else max(1, round(float(count)))
        if is_rest:
            grid.extend('R' * steps)
        else:
            grid.append('A')
            grid.extend('S' * (steps - 1))
    grid = grid[:cells]
    grid.extend('-' * (cells - len(grid)))
    return grid


def beat_matches(expected: Rhythm, given: Rhythm, meter: Meter, bars: int) -> list[bool]:
    """For every felt beat: whether the given rhythm sounds the same there."""
    per_beat = int(meter.pulse / GRID)
    beats = pulses_per_bar(meter) * bars
    cells = per_beat * beats
    a, b = sound_grid(expected, cells), sound_grid(given, cells)
    too_long = rhythm_length(given) > meter.bar_length * bars
    matches = [
        a[i * per_beat : (i + 1) * per_beat] == b[i * per_beat : (i + 1) * per_beat]
        for i in range(beats)
    ]
    if too_long and matches:
        matches[-1] = False
    return matches


def _beat_events(rhythm: Rhythm, meter: Meter, beat: int) -> Rhythm:
    """Events that start within felt beat ``beat`` (0-based)."""
    start, end = meter.pulse * beat, meter.pulse * (beat + 1)
    position = Fraction(0)
    result = []
    for event in rhythm:
        if start <= position < end:
            result.append(event)
        position += event[0].length
    return tuple(result)


class RhythmDictation(ExerciseDefinition):
    """Hear a one- or two-bar rhythm after a count-in and write it down."""

    id = 'rhythm-dictation'
    item_prefix = 'rhythm.dictation.'
    family = Family.RHYTHM
    modality = Modality.EAR
    level = 1
    icon_name = 'rhythm-symbolic'
    glyph = '♫'
    settings = (
        MultiChoiceSetting(
            'vocabulary',
            _('Rhythms'),
            _vocabulary_options(DICTATION_VOCABULARY),
            DICTATION_DEFAULT,
        ),
        MultiChoiceSetting('meters', _('Time signatures'), _meter_options(), ('2/4', '3/4', '4/4')),
        IntSetting('bars', _('Bars'), 1, 1, 2),
        *_tempo_settings(70, 80),
    )

    @property
    def title(self) -> str:
        return _('Rhythm Dictation')

    @property
    def description(self) -> str:
        return _('Hear a rhythm and write it down.')

    @property
    def play_label(self) -> str:
        return _('Play rhythm')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        return _describe_meters_and_tempo(
            _meters(settings, ('2/4', '3/4', '4/4')), _tempo_range(settings, 70, 80)
        )

    def item_label(self, item_id: ItemId) -> str:
        vocabulary = _vocab_item(item_id, self.item_prefix)
        # Translators: an item in "Weakest items", e.g. "Eighth notes — dictation".
        return _('{rhythm} — dictation').format(rhythm=vocabulary_name(vocabulary))

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        chosen = set(_selected(settings, 'vocabulary', DICTATION_DEFAULT))
        return [
            ItemId(f'{self.item_prefix}{v.value}')
            for v in DICTATION_VOCABULARY
            if v.value in chosen
        ]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        vocabulary = _vocab_item(item_id, self.item_prefix)
        meter = rng.choice(_meters(settings, ('2/4', '3/4', '4/4')))
        low, high = _tempo_range(settings, 70, 80)
        tempo = quarter_tempo(meter, rng.randint(low, high))
        bars = _bars(settings, 1)
        rhythm = generate_rhythm(vocabulary, meter, bars, rng)
        chosen = {
            Vocabulary(v)
            for v in _selected(settings, 'vocabulary', DICTATION_DEFAULT)
            if v in {x.value for x in Vocabulary}
        }
        palette = palette_for(chosen | {vocabulary}, meter)
        midi = rng.choice(DICTATION_PITCHES)
        bar_text = ngettext('{count} bar', '{count} bars', bars).format(count=bars)
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Write the rhythm you hear'),
            answer=RhythmInputAnswer(meter, bars, palette),
            expected=rhythm,
            playback=_melodic_playback(rhythm, meter, tempo, midi),
            playback_is_question=True,
            # The contract asks every ear question for a written alternative. For
            # dictation it is the answer itself: learners who turn it on (or have no
            # sound) practise copying notation instead of hearing.
            written_alternative=rhythm_figure(rhythm, meter),
            playback_style_choice=False,
            context=f'{meter} · {bar_text}',
            hint=_vocabulary_hint(vocabulary),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        answer = cast(RhythmInputAnswer, question.answer)
        expected = cast(Rhythm, question.expected)
        written = as_rhythm(given)
        matches = beat_matches(expected, written, answer.meter, answer.bars)
        right = sum(matches)
        total = len(matches)
        score = right / total if total else 0.0
        correct = score >= PARTIAL_CREDIT_PASS
        if right == total:
            title = _('Correct — every beat right')
        elif correct:
            title = ngettext(
                'Nearly — {right} of {total} beat right',
                'Nearly — {right} of {total} beats right',
                total,
            ).format(right=right, total=total)
        else:
            title = ngettext(
                'Not quite — {right} of {total} beat right',
                'Not quite — {right} of {total} beats right',
                total,
            ).format(right=right, total=total)
        inks = []
        position = Fraction(0)
        for duration, _is_rest in expected:
            beat = int(position / answer.meter.pulse)
            ok = beat < total and matches[beat]
            inks.append(Ink.SUCCESS if ok else Ink.ERROR)
            position += duration.length
        playback = question.playback
        play_given = None
        if playback is not None and written:
            midi = playback.notes[0].midi if playback.notes else DICTATION_PITCHES[0]
            play_given = _melodic_playback(written, answer.meter, playback.tempo, midi)
        return Feedback(
            correct=correct,
            title=title,
            detail=self._explanation(expected, written, answer.meter, matches),
            expected_label=sentence_case(rhythm_words(expected, answer.meter)),
            score=score,
            figure=rhythm_figure(expected, answer.meter, inks=inks),
            play_expected=playback,
            play_given=play_given,
        )

    def answer_label(self, question: Question, value: object) -> str:
        rhythm = as_rhythm(value)
        if not rhythm:
            return _('Nothing written')
        return sentence_case(rhythm_words(rhythm, cast(RhythmInputAnswer, question.answer).meter))

    def serialize(self, value: object) -> str:
        return serialize_rhythm(as_rhythm(value))

    @staticmethod
    def _explanation(
        expected: Rhythm, written: Rhythm, meter: Meter, matches: Sequence[bool]
    ) -> str:
        wrong = [i for i, ok in enumerate(matches) if not ok]
        if not wrong:
            return _('Each beat starts and holds its sounds exactly as played.')
        sentences = []
        for beat in wrong[:3]:
            heard = _beat_events(expected, meter, beat)
            wrote = _beat_events(written, meter, beat)
            held = _('the value before it, held on')
            heard_text = ', '.join(duration_name(d, r) for d, r in heard) or held
            if rhythm_length(written) <= meter.pulse * beat:
                wrote_text = _('nothing')
            else:
                wrote_text = ', '.join(duration_name(d, r) for d, r in wrote) or held
            sentences.append(
                # Translators: e.g. "Beat 3: you heard eighth note, eighth note; you wrote
                # quarter note."
                _('Beat {beat}: you heard {heard}; you wrote {wrote}.').format(
                    beat=beat + 1, heard=heard_text, wrote=wrote_text
                )
            )
        sentences.append(
            _('Count the beats of the count-in and listen for where each sound starts.')
        )
        return ' '.join(sentences)


# Note Values ------------------------------------------------------------------------

VALUE_KEYS: dict[str, Duration] = {
    'whole': W,
    'half': H,
    'quarter': Q,
    'eighth': E,
    'sixteenth': S,
    'dotted-half': HD,
    'dotted-quarter': QD,
    'dotted-eighth': ED,
}
REST_KEYS = ('whole', 'half', 'quarter', 'eighth', 'sixteenth')
BEAT_OPTIONS = ('1/4', '1/2', '3/4', '1', '3/2', '2', '3', '4')
NOTE_PITCHES = ('D4', 'E4', 'F4', 'G4', 'A4', 'B4', 'C5', 'D5', 'E5', 'F5', 'G5')


def beats_label(key: str) -> str:
    labels = {
        '1/4': _('¼ beat'),
        '1/2': _('½ beat'),
        '3/4': _('¾ beat'),
        '1': _('1 beat'),
        '3/2': _('1½ beats'),
        '2': _('2 beats'),
        '3': _('3 beats'),
        '4': _('4 beats'),
    }
    return labels[key]


def _value_explanation(key: str, is_rest: bool) -> str:
    duration = VALUE_KEYS[key]
    beats = beats_label(str(duration.quarter_length))
    if is_rest:
        texts = {
            'whole': _('A whole rest hangs below a line and fills a whole bar of 4/4.'),
            'half': _('A half rest sits on top of a line and lasts two beats in 4/4.'),
            'quarter': _('A quarter rest is a zigzag and lasts one beat in 4/4.'),
            'eighth': _('An eighth rest has one flag-like hook and lasts half a beat in 4/4.'),
            'sixteenth': _('A sixteenth rest has two hooks and lasts a quarter of a beat in 4/4.'),
        }
        return texts[key]
    texts = {
        'whole': _('A whole note is an open head without a stem: four beats in 4/4.'),
        'half': _('A half note is an open head with a stem: two beats in 4/4.'),
        'quarter': _('A quarter note is a filled head with a stem: one beat in 4/4.'),
        'eighth': _('An eighth note has one flag: half a beat in 4/4.'),
        'sixteenth': _('A sixteenth note has two flags: a quarter of a beat in 4/4.'),
    }
    if key in texts:
        return texts[key]
    # Translators: e.g. "The dot adds half the value of the half note: 3 beats in 4/4."
    return _('The dot adds half the value of the {note}: {beats} in 4/4.').format(
        note=duration_name(Duration(duration.value)), beats=beats
    )


class NoteValues(ExerciseDefinition):
    """Name a note or rest symbol, or say how many beats it lasts in 4/4."""

    id = 'note-values'
    item_prefix = 'notevalue.'
    family = Family.RHYTHM
    modality = Modality.EYE
    level = 1
    icon_name = 'rhythm-symbolic'
    glyph = '𝅗𝅥'
    settings = (
        MultiChoiceSetting(
            'kinds',
            _('Questions'),
            (
                Option('notes', _('Name the note')),
                Option('rests', _('Name the rest')),
                Option('beats', _('Count the beats')),
            ),
            ('notes', 'rests', 'beats'),
        ),
        BoolSetting('dotted', _('Dotted notes'), True),
        BoolSetting('sixteenths', _('Sixteenth notes and rests'), True),
    )

    @property
    def title(self) -> str:
        return _('Note Values')

    @property
    def description(self) -> str:
        return _('Name note and rest values and count their beats.')

    @property
    def play_label(self) -> str:
        return _('Play value')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        names = {
            'notes': _('notes'),
            'rests': _('rests'),
            'beats': _('beats'),
        }
        kinds = [names[k] for k in _selected(settings, 'kinds', ()) if k in names]
        return sentence_case(', '.join(kinds))

    def _keys(self, settings: Mapping[str, object], kind: str) -> list[str]:
        sixteenths = bool(settings.get('sixteenths', True))
        dotted = bool(settings.get('dotted', True))
        keys = list(REST_KEYS) if kind == 'rest' else list(VALUE_KEYS)
        if not sixteenths:
            keys.remove('sixteenth')
        if not dotted or kind == 'rest':
            keys = [k for k in keys if not k.startswith('dotted')]
        return keys

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        kinds = _selected(settings, 'kinds', ('notes', 'rests', 'beats'))
        result: list[ItemId] = []
        if 'notes' in kinds:
            result += [ItemId(f'notevalue.note.{k}') for k in self._keys(settings, 'note')]
        if 'rests' in kinds:
            result += [ItemId(f'notevalue.rest.{k}') for k in self._keys(settings, 'rest')]
        if 'beats' in kinds:
            result += [ItemId(f'notevalue.beats.{k}') for k in self._keys(settings, 'note')]
        return result

    @staticmethod
    def _parse(item: str) -> tuple[str, str]:
        parts = item.split('.')
        if len(parts) != 3 or parts[0] != 'notevalue' or parts[1] not in ('note', 'rest', 'beats'):
            raise ValueError(f'not a note value item: {item!r}')
        if parts[2] not in VALUE_KEYS or (parts[1] == 'rest' and parts[2] not in REST_KEYS):
            raise ValueError(f'not a note value item: {item!r}')
        return parts[1], parts[2]

    def item_label(self, item_id: ItemId) -> str:
        kind, key = self._parse(item_id)
        name = duration_name(VALUE_KEYS[key], kind == 'rest')
        if kind == 'beats':
            # Translators: an item in "Weakest items", e.g. "Beats of a dotted half note".
            return _('Beats of a {value}').format(value=name)
        return sentence_case(name)

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        kind, key = self._parse(item_id)
        pairs = {
            'whole': 'half',
            'half': 'whole',
            'eighth': 'sixteenth',
            'sixteenth': 'eighth',
            'dotted-quarter': 'dotted-half',
            'dotted-half': 'dotted-quarter',
        }
        other = pairs.get(key)
        return (ItemId(f'notevalue.{kind}.{other}'),) if other else ()

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        kind, key = self._parse(item_id)
        duration = VALUE_KEYS[key]
        is_rest = kind == 'rest'
        pitch = Pitch.parse(rng.choice(NOTE_PITCHES))
        event = _event(duration, is_rest, Ink.FOREGROUND, pitch)
        if kind == 'beats':
            options = tuple(
                Option(k, beats_label(k), accel=str(i + 1)) for i, k in enumerate(BEAT_OPTIONS)
            )
            expected = str(duration.quarter_length)
            figure = StaffSpec(
                meter=Meter(4, 4),
                events=(event,),
                description=_('Treble staff in 4/4 time with one note symbol.'),
            )
            prompt = _('How many beats does this note last in 4/4?')
        else:
            keys = self._keys(settings, kind)
            if key not in keys:
                keys.append(key)
            options = tuple(
                Option(k, sentence_case(duration_name(VALUE_KEYS[k], is_rest)), accel=str(i + 1))
                for i, k in enumerate(keys)
            )
            expected = key
            if is_rest:
                description = _('Treble staff with one rest symbol.')
                prompt = _('What is this rest called?')
            else:
                description = _('Treble staff with one note symbol.')
                prompt = _('What is this note called?')
            figure = StaffSpec(events=(event,), description=description)
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=prompt,
            answer=ChoiceAnswer(options),
            expected=expected,
            figure=figure,
            playback=self._playback(duration, is_rest, pitch),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        kind, key = self._parse(question.item_id)
        label = self.answer_label(question, question.expected)
        correct = str(given) == question.expected
        if correct:
            title = _('Correct — {answer}').format(answer=label)
        else:
            title = _('Not quite — the answer is {answer}').format(answer=label)
        return Feedback(
            correct=correct,
            title=title,
            detail=_value_explanation(key, kind == 'rest'),
            expected_label=label,
            play_expected=question.playback,
        )

    @staticmethod
    def _playback(duration: Duration, is_rest: bool, pitch: Pitch) -> PlaybackSpec:
        """A bar of 4/4 counted in, then the value held (or silent) with the click on,
        so the learner hears how long it lasts."""
        meter = Meter(4, 4)
        length = duration.quarter_length
        notes = () if is_rest else (PlaybackNote(pitch.midi, Fraction(0), length, 90),)
        return PlaybackSpec(
            notes, 80.0, count_in=4, click=True, meter=meter, duration=max(length, Fraction(1))
        )


# Meter by Ear ---------------------------------------------------------------------------

METER_KINDS: dict[str, Meter] = {
    'duple': Meter(2, 4),
    'triple': Meter(3, 4),
    'quadruple': Meter(4, 4),
    'compound-duple': Meter(6, 8),
    'compound-triple': Meter(9, 8),
    'compound-quadruple': Meter(12, 8),
}
BASS_DRUM = 36
SIDE_STICK = 37


def meter_kind_label(key: str, *, compound_choice: bool) -> str:
    if not compound_choice:
        labels = {
            'duple': _('Duple — 2 beats'),
            'triple': _('Triple — 3 beats'),
            'quadruple': _('Quadruple — 4 beats'),
        }
    else:
        labels = {
            'duple': _('Simple duple'),
            'triple': _('Simple triple'),
            'quadruple': _('Simple quadruple'),
            'compound-duple': _('Compound duple'),
            'compound-triple': _('Compound triple'),
            'compound-quadruple': _('Compound quadruple'),
        }
    return labels[key]


class MeterByEar(ExerciseDefinition):
    """Hear a few bars with stressed downbeats and say how many beats a bar has."""

    id = 'meter-ear'
    item_prefix = 'meter.ear.'
    family = Family.RHYTHM
    modality = Modality.EAR
    level = 1
    icon_name = 'rhythm-symbolic'
    glyph = '𝄴'
    settings = (
        BoolSetting(
            'compound',
            _('Simple and compound time'),
            False,
            subtitle=_('Also tell whether beats divide in two or in three'),
        ),
        IntSetting('bars', _('Bars'), 4, 2, 6),
        *_tempo_settings(80, 110),
    )

    @property
    def title(self) -> str:
        return _('Meter by Ear')

    @property
    def description(self) -> str:
        return _('Hear the strong beats and tell duple, triple or quadruple time.')

    @property
    def play_label(self) -> str:
        return _('Play rhythm')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        if settings.get('compound', False):
            return _('Simple and compound time')
        return _('Simple time')

    def _kinds(self, settings: Mapping[str, object]) -> list[str]:
        kinds = ['duple', 'triple', 'quadruple']
        if settings.get('compound', False):
            kinds += ['compound-duple', 'compound-triple', 'compound-quadruple']
        return kinds

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        return [ItemId(f'{self.item_prefix}{k}') for k in self._kinds(settings)]

    def _parse(self, item: str) -> str:
        kind = item.removeprefix(self.item_prefix)
        if not item.startswith(self.item_prefix) or kind not in METER_KINDS:
            raise ValueError(f'not a meter item: {item!r}')
        return kind

    def item_label(self, item_id: ItemId) -> str:
        kind = self._parse(item_id)
        # Translators: an item in "Weakest items", e.g. "Triple — 3 beats (by ear)".
        return _('{meter} (by ear)').format(meter=meter_kind_label(kind, compound_choice=True))

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        kind = self._parse(item_id)
        pairs = {
            'duple': 'quadruple',
            'quadruple': 'duple',
            'compound-duple': 'triple',
            'triple': 'compound-duple',
        }
        other = pairs.get(kind)
        return (ItemId(f'{self.item_prefix}{other}'),) if other else ()

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        kind = self._parse(item_id)
        meter = METER_KINDS[kind]
        compound_choice = bool(settings.get('compound', False)) or kind.startswith('compound')
        kinds = list(METER_KINDS) if compound_choice else ['duple', 'triple', 'quadruple']
        low, high = _tempo_range(settings, 80, 110)
        tempo = quarter_tempo(meter, rng.randint(low, high))
        bars = max(2, min(6, _int(settings, 'bars', 4)))
        rhythm: Rhythm = ()
        for _bar in range(bars):
            vocabulary = rng.choice((Vocabulary.QUARTERS, Vocabulary.HALVES, Vocabulary.EIGHTHS))
            rhythm += generate_rhythm(vocabulary, meter, 1, rng)
        options = tuple(
            Option(
                k,
                meter_kind_label(k, compound_choice=compound_choice),
                accel=str(i + 1) if compound_choice else str(i + 2),
            )
            for i, k in enumerate(kinds)
        )
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=(
                _('Which meter do you hear?')
                if compound_choice
                else _('How many beats are in each bar?')
            ),
            answer=ChoiceAnswer(options),
            expected=kind,
            playback=self._playback(rhythm, meter, tempo),
            playback_is_question=True,
            written_alternative=rhythm_figure(rhythm, meter, show_meter=False),
            playback_style_choice=False,
            hint=_('Listen for the low drum: it marks the first beat of every bar.'),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        kind = cast(str, question.expected)
        meter = METER_KINDS[kind]
        label = self.answer_label(question, kind)
        correct = str(given) == kind
        if correct:
            title = _('Correct — {answer}').format(answer=label)
        else:
            title = _('Not quite — the answer is {answer}').format(answer=label)
        playback = question.playback
        rhythm = rhythm_from_figure(question.written_alternative)
        return Feedback(
            correct=correct,
            title=title,
            detail=self._explanation(meter),
            expected_label=label,
            figure=rhythm_figure(rhythm, meter) if rhythm else None,
            play_expected=playback,
        )

    @staticmethod
    def _explanation(meter: Meter) -> str:
        beats = pulses_per_bar(meter)
        counting = ' '.join([_('ONE')] + [str(n) for n in range(2, beats + 1)])
        if meter.is_compound:
            # Translators: e.g. "The strong beat came every 2 beats (ONE 2), and each beat
            # divided into three eighths: compound time, like 6/8."
            return _(
                'The strong beat came every {beats} beats ({counting}), and each beat '
                'divided into three eighths: compound time, like {meter}.'
            ).format(beats=beats, counting=counting, meter=meter)
        return _(
            'The strong beat came every {beats} beats ({counting}), and each beat divided '
            'into two: simple time, like {meter}.'
        ).format(beats=beats, counting=counting, meter=meter)

    @staticmethod
    def _playback(rhythm: Rhythm, meter: Meter, tempo: float) -> PlaybackSpec:
        """Side stick for the rhythm, stressed on the beats and most on the downbeat, and a
        bass drum on every downbeat. No count-in: it would give the meter away."""
        bar = meter.bar_length * 4
        pulse = meter.pulse * 4
        per_bar = pulses_per_bar(meter)
        notes: list[PlaybackNote] = []
        for start in onsets(rhythm):
            within = start % bar
            if within == 0:
                velocity = 112
                notes.append(PlaybackNote(BASS_DRUM, start, Fraction(1, 2), 110, percussion=True))
            elif per_bar == 4 and within == 2 * pulse:
                velocity = 88
            elif within % pulse == 0:
                velocity = 76
            else:
                velocity = 56
            notes.append(PlaybackNote(SIDE_STICK, start, Fraction(1, 4), velocity, percussion=True))
        return PlaybackSpec(tuple(notes), tempo, meter=meter, duration=rhythm_length(rhythm) * 4)


EXERCISES: tuple[ExerciseDefinition, ...] = (
    NoteValues(),
    RhythmTap(),
    RhythmDictation(),
    MeterByEar(),
)
