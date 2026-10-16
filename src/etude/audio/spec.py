# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""What to play: an immutable, backend-free description of a playback.

Times and lengths are in beats (quarter notes) as exact fractions; the
backend converts them to milliseconds with ``tempo``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from enum import Enum
from fractions import Fraction

from ..core import Meter, Pitch


class Instrument(Enum):
    """Timbres offered to the learner; values are General MIDI programs.

    Varying the timbre helps listeners recognise intervals and chords as
    relationships rather than as the sound of one instrument.
    """

    PIANO = 0
    ORGAN = 19
    GUITAR = 24
    STRINGS = 48
    CHOIR = 52
    FLUTE = 73


@dataclass(frozen=True, slots=True)
class PlaybackNote:
    midi: int
    start: Fraction
    """Onset in beats from the start of the playback (after any count-in)."""
    length: Fraction
    velocity: int = 90
    percussion: bool = False
    """Play on the General MIDI percussion channel (channel 10): ``midi`` is
    then a GM drum key (76 is a high wood block) and the instrument is ignored."""

    def __post_init__(self) -> None:
        if not 0 <= self.midi <= 127:
            raise ValueError(f'MIDI note {self.midi} is out of range')
        if not 1 <= self.velocity <= 127:
            raise ValueError(f'velocity {self.velocity} is out of range')
        if self.start < 0 or self.length <= 0:
            raise ValueError('notes need a non-negative start and a positive length')


@dataclass(frozen=True, slots=True)
class PlaybackSpec:
    notes: tuple[PlaybackNote, ...]
    tempo: float = 80.0
    """Quarter notes per minute."""
    instrument: Instrument = Instrument.PIANO
    count_in: int = 0
    """Metronome clicks before the first note (rhythm exercises)."""
    click: bool = False
    """Keep the metronome running during the playback."""
    meter: Meter | None = None
    """How the metronome counts. With a meter, beats are the felt pulses
    (dotted quarters in 6/8, 2+2+3 eighths in 7/8), ``count_in`` counts those
    pulses and the first beat of each bar is accented. Without one, every
    quarter note is a beat."""

    def __post_init__(self) -> None:
        if self.tempo <= 0:
            raise ValueError(f'tempo must be positive, not {self.tempo}')
        if self.count_in < 0:
            raise ValueError('count-in cannot be negative')

    @property
    def length(self) -> Fraction:
        """Total length in beats, excluding the count-in."""
        return max((n.start + n.length for n in self.notes), default=Fraction(0))

    def beats_to_ms(self, beats: Fraction | float) -> float:
        return float(beats) * 60_000.0 / self.tempo

    @classmethod
    def melodic(
        cls,
        pitches: Iterable[Pitch],
        *,
        note_length: Fraction = Fraction(1),
        **kwargs: object,
    ) -> PlaybackSpec:
        """One pitch after another, each ``note_length`` beats long."""
        notes = tuple(
            PlaybackNote(p.midi, i * note_length, note_length) for i, p in enumerate(pitches)
        )
        return cls(notes, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def harmonic(
        cls,
        pitches: Iterable[Pitch],
        *,
        length: Fraction = Fraction(2),
        **kwargs: object,
    ) -> PlaybackSpec:
        """All pitches sounding together."""
        notes = tuple(PlaybackNote(p.midi, Fraction(0), length) for p in pitches)
        return cls(notes, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def sequence(cls, *parts: PlaybackSpec, gap: Fraction = Fraction(1)) -> PlaybackSpec:
        """Concatenate playbacks (e.g. a tonic-establishing cadence, then the question).
        Tempo, instrument, count-in, click and meter come from the first part."""
        if not parts:
            raise ValueError('nothing to sequence')
        notes: list[PlaybackNote] = []
        offset = Fraction(0)
        for part in parts:
            notes.extend(replace(n, start=n.start + offset) for n in part.notes)
            offset += part.length + gap
        first = parts[0]
        return cls(
            tuple(notes), first.tempo, first.instrument, first.count_in, first.click, first.meter
        )
