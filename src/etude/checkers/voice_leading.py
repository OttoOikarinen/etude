# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Four-part (SATB) voice-leading rules of common-practice harmony.

The checker reports every rule a progression of four-voice chords breaks,
with the chords and voices involved and a translated explanation, so the
exercise page can mark the problem on the staff and say why it matters.
The rules and their defaults follow the conventions of Kostka–Payne and
Aldwell–Schachter; where textbooks differ the stricter common reading is
used and documented on the rule.

Voices are numbered from the top: 0 soprano, 1 alto, 2 tenor, 3 bass. A
progression is a sequence of chords, one per slot, each a tuple of four
pitches in that order.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

from ..core import Pitch
from ..core.chord import Chord
from ..core.scale import Key

SOPRANO, ALTO, TENOR, BASS = 0, 1, 2, 3
VOICES = (SOPRANO, ALTO, TENOR, BASS)


class Severity(Enum):
    ERROR = 'error'
    """Breaks the style: the answer is wrong."""
    WARNING = 'warning'
    """Allowed but weak, or allowed only in particular contexts: mentioned, not penalised."""


class Rule(Enum):
    """Every rule the checker knows. The value is a stable id for settings and tests."""

    WRONG_CHORD = 'wrong-chord'
    """The pitches do not form the chord asked for (``harmony``)."""
    INCOMPLETE_CHORD = 'incomplete-chord'
    """A chord tone is missing (the omitted fifth of a root-position chord is a warning)."""
    WRONG_DOUBLING = 'wrong-doubling'
    """A tendency tone (leading tone, chordal seventh) is doubled."""
    RANGE = 'range'
    """A voice leaves its range (:class:`Ranges`)."""
    SPACING = 'spacing'
    """More than an octave between adjacent upper voices (S–A, A–T)."""
    CROSSING = 'crossing'
    """A lower voice sounds above a higher one."""
    OVERLAP = 'overlap'
    """A voice moves past the previous note of an adjacent voice."""
    PARALLEL_FIFTHS = 'parallel-fifths'
    PARALLEL_OCTAVES = 'parallel-octaves'
    """Includes parallel unisons and compound octaves."""
    DIRECT_FIFTHS = 'direct-fifths'
    """Hidden fifths between the outer voices with a leap in the soprano."""
    DIRECT_OCTAVES = 'direct-octaves'
    """Hidden octaves between the outer voices with a leap in the soprano."""
    LEADING_TONE = 'leading-tone'
    """The leading tone in an outer voice of V–I does not rise to the tonic."""
    CHORDAL_SEVENTH = 'chordal-seventh'
    """A chordal seventh does not resolve down by step."""
    AUGMENTED_SECOND = 'augmented-second'
    """A voice moves by an augmented second (or another augmented interval)."""
    LARGE_LEAP = 'large-leap'
    """An inner voice leaps more than a fourth, or any voice more than an octave."""


@dataclass(frozen=True, slots=True)
class Ranges:
    """Lowest and highest pitch of each voice, soprano first (Kostka–Payne)."""

    soprano: tuple[Pitch, Pitch] = (Pitch.parse('C4'), Pitch.parse('G5'))
    alto: tuple[Pitch, Pitch] = (Pitch.parse('G3'), Pitch.parse('C5'))
    tenor: tuple[Pitch, Pitch] = (Pitch.parse('C3'), Pitch.parse('G4'))
    bass: tuple[Pitch, Pitch] = (Pitch.parse('E2'), Pitch.parse('C4'))

    def of(self, voice: int) -> tuple[Pitch, Pitch]:
        return (self.soprano, self.alto, self.tenor, self.bass)[voice]


@dataclass(frozen=True, slots=True)
class Violation:
    rule: Rule
    severity: Severity
    slot: int
    """The chord where the problem is heard (the second chord of a motion)."""
    voices: tuple[int, ...]
    """Voices involved, e.g. ``(SOPRANO, BASS)`` for parallel octaves."""
    message: str
    """Translated explanation, e.g. "Parallel fifths between alto and bass (chords 2–3)"."""


@dataclass(frozen=True, slots=True)
class Context:
    """What the checker needs to know besides the notes."""

    key: Key | None = None
    """Needed for leading-tone and seventh resolution rules."""
    harmony: Sequence[Chord | None] = field(default=())
    """The chord each slot should be (from a Roman numeral or figured bass); ``None``
    or a shorter sequence skips chord-membership checks for those slots."""
    ranges: Ranges = field(default_factory=Ranges)
    rules: frozenset[Rule] = frozenset(Rule)
    """Rules to apply; exercises switch some off for earlier stages."""


def check(chords: Sequence[tuple[Pitch, ...]], context: Context | None = None) -> list[Violation]:
    """Every violation in ``chords`` (four pitches each, soprano first), sorted by slot.

    W4 implements this; until then it raises :class:`NotImplementedError`.
    """
    raise NotImplementedError
