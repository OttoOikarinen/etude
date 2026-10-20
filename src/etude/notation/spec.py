# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""What to engrave: an immutable, toolkit-free description of a staff.

Exercises build a :class:`StaffSpec` (or a :class:`SystemSpec` for grand
staves and SATB), :func:`etude.notation.layout.layout` turns it into a
:class:`~etude.notation.displaylist.DisplayList`, and the GTK
``StaffView`` widget draws that list. Nothing in this module knows about
pixels, fonts or GTK.

Staff positions count diatonic steps from the bottom line: 0 is the
bottom line, 1 the first space, 8 the top line, -2 the first ledger line
below, and so on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..core import Duration, KeySignature, Meter, Pitch
from ..core.pitch import Letter


class Clef(Enum):
    """Clefs, defined by the pitch written on the bottom staff line."""

    TREBLE = 'treble'
    BASS = 'bass'
    ALTO = 'alto'
    TENOR = 'tenor'
    TREBLE_8VB = 'treble_8vb'
    """Treble clef sounding an octave lower (tenor voice in SATB)."""
    PERCUSSION = 'percussion'
    """Neutral clef for rhythm-only staves; positions behave like treble."""

    @property
    def bottom_line(self) -> Pitch:
        return _BOTTOM_LINES[self]

    def staff_position(self, pitch: Pitch) -> int:
        """Diatonic steps of ``pitch`` above the bottom line (accidentals ignored)."""
        return pitch.diatonic_index - self.bottom_line.diatonic_index

    def pitch_at(self, position: int, alter: int = 0) -> Pitch:
        """Inverse of :meth:`staff_position` for a given alteration."""
        octave, step = divmod(self.bottom_line.diatonic_index + position, 7)
        return Pitch(Letter(step), alter, octave)


_BOTTOM_LINES = {
    Clef.TREBLE: Pitch(Letter.E, 0, 4),
    Clef.BASS: Pitch(Letter.G, 0, 2),
    Clef.ALTO: Pitch(Letter.F, 0, 3),
    Clef.TENOR: Pitch(Letter.D, 0, 3),
    Clef.TREBLE_8VB: Pitch(Letter.E, 0, 3),
    Clef.PERCUSSION: Pitch(Letter.E, 0, 4),
}


class Ink(Enum):
    """Semantic colour of a mark. The widget maps these to libadwaita colours,
    so notation follows the accent colour and dark style automatically."""

    FOREGROUND = 'foreground'
    DIM = 'dim'
    ACCENT = 'accent'
    SUCCESS = 'success'
    ERROR = 'error'


class AccidentalDisplay(Enum):
    AUTO = 'auto'
    """Show an accidental only when the key signature and earlier notes in the
    bar do not already imply it."""
    ALWAYS = 'always'
    """Always show it (courtesy accidental, or a natural)."""
    NEVER = 'never'


class BarStyle(Enum):
    SINGLE = 'single'
    DOUBLE = 'double'
    FINAL = 'final'
    REPEAT_START = 'repeat_start'
    REPEAT_END = 'repeat_end'


@dataclass(frozen=True, slots=True)
class Head:
    """One notehead of a chord."""

    pitch: Pitch
    ink: Ink = Ink.FOREGROUND
    accidental: AccidentalDisplay = AccidentalDisplay.AUTO
    halo: bool = False
    """Draw a translucent highlight circle behind the head (design 1g)."""


@dataclass(frozen=True, slots=True)
class Chord:
    """A note or chord. A single note is a chord with one head.

    With ``duration=None`` the heads are drawn as stemless black noteheads,
    which is how the theory exercises show pitches whose rhythm does not
    matter.
    """

    heads: tuple[Head, ...]
    duration: Duration | None = None
    label: str | None = None
    """Text centred below the staff, e.g. a scale degree or Roman numeral. Lines
    separated by ``'\\n'`` are stacked downwards, as figured-bass figures are."""
    ink: Ink = Ink.FOREGROUND
    """Colour of the stem, flag and label."""
    tie_to_next: bool = False


@dataclass(frozen=True, slots=True)
class Rest:
    duration: Duration
    ink: Ink = Ink.FOREGROUND


@dataclass(frozen=True, slots=True)
class Barline:
    style: BarStyle = BarStyle.SINGLE


Event = Chord | Rest | Barline


@dataclass(frozen=True, slots=True)
class Bracket:
    """A labelled bracket spanning events ``first``–``last`` (design 1d: the ``?``
    between two notes of an interval)."""

    first: int
    last: int
    label: str
    ink: Ink = Ink.ACCENT


@dataclass(frozen=True, slots=True)
class StaffSpec:
    clef: Clef = Clef.TREBLE
    key_signature: KeySignature | None = None
    meter: Meter | None = None
    events: tuple[Event, ...] = ()
    brackets: tuple[Bracket, ...] = ()
    lines: int = 5
    """Number of staff lines; rhythm exercises may use a single line."""
    description: str | None = None
    """Accessible description. When ``None`` one is generated from the content."""
    voices: tuple[tuple[Event, ...], ...] = ()
    """Further voices on the same staff, aligned with ``events`` by onset (alto under
    soprano on a grand staff). When set, ``events`` is the upper voice with stems up
    and every further voice has stems down. Hit regions and ``event_x`` number the
    events of further voices after those of ``events``: the first event of
    ``voices[0]`` has index ``len(events)``."""

    @classmethod
    def notes(cls, *pitches: Pitch | str, clef: Clef = Clef.TREBLE, **kwargs: object) -> StaffSpec:
        """Convenience for exercises: a staff of stemless single notes."""
        events = tuple(
            Chord((Head(p if isinstance(p, Pitch) else Pitch.parse(p)),)) for p in pitches
        )
        return cls(clef=clef, events=events, **kwargs)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class SystemSpec:
    """Several staves sharing one time line: a grand staff, SATB, score excerpts.

    Events on different staves are aligned by onset. Events without a
    duration (stemless notes) each take one slot, so two staves with the
    same number of stemless events line up one to one.
    """

    staves: tuple[StaffSpec, ...]
    brace: bool = True
    description: str | None = None
    labels: tuple[str, ...] = field(default=())
    """Optional staff names shown at the left (``'S'``, ``'A'`` …)."""


@dataclass(frozen=True, slots=True)
class GlyphFigure:
    """Symbols shown on their own: dynamics, hairpins, articulations (design: Symbols).

    ``glyphs`` are SMuFL glyph names drawn side by side on a common baseline
    and centred in the figure. A glyph whose name ends in ``Above`` or
    ``Below`` (``articStaccatoAbove``, ``fermataAbove``) is not placed beside
    the glyph before it but centred above or below it, so a precomposed note
    followed by an articulation reads as one marked note. With ``staff`` the
    glyphs stand on the middle line of a five-line staff without a clef.

    There is no automatic description: ``description`` is what screen readers
    hear, and must not name the symbol when the question asks for it.
    """

    glyphs: tuple[str, ...]
    description: str
    staff: bool = False
    ink: Ink = Ink.FOREGROUND


Figure = StaffSpec | SystemSpec | GlyphFigure
