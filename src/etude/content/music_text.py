# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""A compact text notation for the musical examples in lessons and the glossary.

Tokens are separated by spaces::

    C4            a stemless note (pitch only; rhythm does not matter)
    F#4/q         a quarter note; durations: w h q e s t (32nd), dots follow: h. q..
    Bb3/e3        an eighth-note triplet member (the digit is the tuplet: 3 in 2)
    [C4 E4 G4]/h  a chord
    r/q           a rest (rests need a duration)
    *E4/q         highlighted: accent colour with a halo
    G4/q{5}       with a label under the staff, e.g. a scale degree
    D4/h~         tied to the next note
    |  ||  |.  |:  :|   barlines: single, double, final, repeat start, repeat end

Writing ``C4 E4 G4`` gives three stemless notes; ``[C4 E4 G4]`` one chord.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from fractions import Fraction

from ..audio.spec import PlaybackNote, PlaybackSpec
from ..core import Duration, NoteValue, Pitch
from ..core.rhythm import Tuplet
from ..notation.spec import Barline, BarStyle, Chord, Event, Figure, Head, Ink, Rest, StaffSpec

_DURATIONS = {
    'w': NoteValue.WHOLE,
    'h': NoteValue.HALF,
    'q': NoteValue.QUARTER,
    'e': NoteValue.EIGHTH,
    's': NoteValue.SIXTEENTH,
    't': NoteValue.THIRTY_SECOND,
}
_TUPLETS = {'3': Tuplet(3, 2), '5': Tuplet(5, 4), '6': Tuplet(6, 4), '2': Tuplet(2, 3)}
_BARS = {
    '|': BarStyle.SINGLE,
    '||': BarStyle.DOUBLE,
    '|.': BarStyle.FINAL,
    '|:': BarStyle.REPEAT_START,
    ':|': BarStyle.REPEAT_END,
}
_TOKEN = re.compile(r'\*?\[[^\]]*\]\S*|\S+')
_NOTE = re.compile(
    r'^(?P<mark>\*)?(?P<body>\[[^\]]*\]|[^/{~\s]+)'
    r'(?:/(?P<value>[whqest])(?P<dots>\.*)(?P<tuplet>\d)?)?'
    r'(?:\{(?P<label>[^}]*)\})?(?P<tie>~)?$'
)


class MusicTextError(ValueError):
    """The text is not valid example notation; the message names the token."""


def _duration(value: str | None, dots: str, tuplet: str | None, token: str) -> Duration | None:
    if value is None:
        if dots or tuplet:
            raise MusicTextError(f'dots or a tuplet without a duration in {token!r}')
        return None
    if tuplet is not None and tuplet not in _TUPLETS:
        raise MusicTextError(f'unsupported tuplet {tuplet!r} in {token!r}')
    try:
        return Duration(
            _DURATIONS[value], len(dots), _TUPLETS[tuplet] if tuplet is not None else None
        )
    except ValueError as error:
        raise MusicTextError(f'{error} in {token!r}') from None


def _pitches(body: str, token: str) -> tuple[Pitch, ...]:
    names = body[1:-1].split() if body.startswith('[') else [body]
    if not names:
        raise MusicTextError(f'empty chord in {token!r}')
    try:
        return tuple(Pitch.parse(name) for name in names)
    except ValueError:
        raise MusicTextError(f'not a pitch in {token!r}') from None


def parse_events(text: str) -> tuple[Event, ...]:
    """Parse example notation into staff events."""
    return tuple(_events(text))


def _events(text: str) -> Iterator[Event]:
    for token in _TOKEN.findall(text):
        if token in _BARS:
            yield Barline(_BARS[token])
            continue
        match = _NOTE.match(token)
        if match is None:
            raise MusicTextError(f'cannot read {token!r}')
        duration = _duration(match['value'], match['dots'], match['tuplet'], token)
        highlight = match['mark'] is not None
        ink = Ink.ACCENT if highlight else Ink.FOREGROUND
        if match['body'] == 'r':
            if duration is None:
                raise MusicTextError(f'a rest needs a duration: {token!r}')
            yield Rest(duration, ink=ink)
            continue
        heads = tuple(
            Head(pitch, ink=ink, halo=highlight) for pitch in _pitches(match['body'], token)
        )
        yield Chord(
            heads,
            duration,
            label=match['label'],
            ink=ink,
            tie_to_next=match['tie'] is not None,
        )


# Playback ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Timed:
    midis: tuple[int, ...]
    beats: Fraction
    rest: bool


def _timeline(events: tuple[Event, ...]) -> list[_Timed]:
    timed: list[_Timed] = []
    for event in events:
        if isinstance(event, Barline):
            continue
        if isinstance(event, Rest):
            timed.append(_Timed((), event.duration.quarter_length, True))
            continue
        beats = event.duration.quarter_length if event.duration is not None else Fraction(1)
        timed.append(_Timed(tuple(h.pitch.midi for h in event.heads), beats, False))
    return timed


def figure_playback(
    figure: Figure,
    mode: str = 'as-written',
    *,
    tempo: float = 96.0,
) -> PlaybackSpec:
    """Sound for an example figure.

    ``mode`` is ``'as-written'`` (rhythm as notated; stemless notes one beat each;
    staves of a system together), ``'melodic'`` (every pitch one after another,
    low to high within a chord) or ``'harmonic'`` (all pitches together).
    """
    staves = figure.staves if not isinstance(figure, StaffSpec) else (figure,)
    notes: list[PlaybackNote] = []
    if mode == 'harmonic':
        midis = sorted(
            {
                h.pitch.midi
                for s in staves
                for e in s.events
                if isinstance(e, Chord)
                for h in e.heads
            }
        )
        notes = [PlaybackNote(m, Fraction(0), Fraction(2)) for m in midis]
    elif mode == 'melodic':
        start = Fraction(0)
        for staff in staves:
            for item in _timeline(staff.events):
                for midi in sorted(item.midis):
                    notes.append(PlaybackNote(midi, start, Fraction(1)))
                    start += 1
    elif mode == 'as-written':
        for staff in staves:
            start = Fraction(0)
            for item in _timeline(staff.events):
                notes.extend(PlaybackNote(m, start, item.beats) for m in item.midis)
                start += item.beats
    else:
        raise MusicTextError(f'unknown playback mode {mode!r}')
    if not notes:
        raise MusicTextError('the figure has no notes to play')
    return PlaybackSpec(tuple(notes), tempo=tempo)
