# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Engraving: turn a :data:`~etude.notation.spec.Figure` into a display list.

The engraver works in four passes:

1. **Analysis.** Every staff is split into *tracks* (its events plus any
   further voices). Onsets, beam groups, stem directions and tuplets are
   worked out per track.
2. **Columns.** Events of all staves that start together share a *slot*.
   For each staff and slot the engraver builds a column: noteheads (with
   seconds displaced), accidentals (stacked), stems, flags, dots, rests or
   a barline, all relative to the slot's x position. Each column knows how
   far it reaches to the left and right of that position.
3. **Spacing.** Slots are placed left to right with springs whose natural
   length follows the duration until the next onset (Gould's proportional
   spacing) and rods that keep neighbouring columns from colliding.
   ``width`` stretches or compresses the springs.
4. **Drawing.** Items are emitted per staff (beams, ties, tuplets,
   brackets and labels need the final x positions), then the staves are
   stacked vertically and the system's brace, labels and connecting
   barlines are added.

Everything is measured in staff spaces with y growing downwards. Staff
positions count diatonic steps up from the bottom line, as in
:mod:`etude.notation.spec`.
"""

from __future__ import annotations

import dataclasses
import itertools
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from fractions import Fraction

from ..core import Meter, NoteValue, Pitch
from . import _accidentals, _grouping
from .displaylist import (
    Align,
    BeamItem,
    CircleItem,
    CurveItem,
    DisplayList,
    GlyphItem,
    HitRegion,
    Item,
    LineItem,
    StaffGeometry,
    TextItem,
)
from .smufl import FontMetrics
from .spec import (
    Barline,
    BarStyle,
    Bracket,
    Chord,
    Clef,
    Event,
    Figure,
    GlyphFigure,
    Ink,
    Rest,
    StaffSpec,
    SystemSpec,
)

# --- Engraving rules, in staff spaces ---------------------------------------------------

STEM_LENGTH = 3.5
"""Normal stem length, from the centre of the notehead (one octave)."""
EXTRA_FLAG_STEM = 0.75
"""Added stem length for every flag or beam beyond the second."""
CLEF_INDENT = 0.8
"""From the start of the staff to the clef."""
PREAMBLE_GAP = 1.0
"""Between clef, key signature and time signature."""
KEY_ACCIDENTAL_GAP = 0.08
"""Between the accidentals of a key signature."""
FIRST_NOTE_GAP = 1.8
"""From the end of the preamble to the first column."""
COLUMN_PAD = 0.5
"""Smallest clear space between neighbouring columns."""
BEFORE_BARLINE = 1.0
AFTER_BARLINE = 1.2
EMPTY_STAFF_TAIL = 3.0
"""Staff length after the preamble when a staff has no events."""
END_PAD = 1.2
"""Smallest space between the last column and the end of the staff."""
STEMLESS_SPACE = 4.0
"""Natural distance between stemless notes."""
ACCIDENTAL_GAP = 0.22
"""Between an accidental and its notehead."""
LEDGER_ACCIDENTAL_EXTENSION = 0.2
"""Ledger line extension on the side of an accidental (shortened to make room)."""
DOT_GAP = 0.35
DOT_ADVANCE = 0.55
HALO_RADIUS = 1.2
LABEL_SIZE = 1.35
LABEL_CLEARANCE = 0.6
"""Smallest space between the staff's lowest mark and the labels below."""
LABEL_MIN_BASELINE = 3.4
"""Smallest distance from the bottom line to the label baseline."""
BRACKET_GAP = 0.6
BRACKET_HOOK = 0.5
BRACKET_PAD = 0.55
"""How far a label bracket reaches beyond the outermost noteheads."""
BRACKET_LABEL_SIZE = 2.1
BRACKET_LABEL_GAP = 0.35
TUPLET_CLEARANCE = 1.0
TUPLET_HOOK = 0.6
TUPLET_GAP = 0.25
"""Space between a tuplet number and the bracket lines on either side."""
TIE_GAP = 0.12
TIE_OFFSET = 0.32
STAFF_DISTANCE = 6.5
"""Smallest distance between the bottom line of a staff and the top line of the next."""
STAFF_CLEARANCE = 1.0
MIN_ABOVE = 2.5
"""Room kept above the top line so that figures do not jump between questions."""
MIN_BELOW = 2.5
MARGIN = 0.5
BRACE_GAP = 0.3
SYSTEM_LABEL_SIZE = 1.4
SYSTEM_LABEL_GAP = 0.6
TEXT_WIDTH = 0.6
"""Estimated advance of a UI-font character, in ems (used for collision checks only)."""
TEXT_ASCENT = 0.75
TEXT_DESCENT = 0.25
GLYPH_GAP = 1.0
"""Between the symbols of a :class:`~etude.notation.spec.GlyphFigure`."""
ATTACH_GAP = 0.6
"""Between a glyph and an articulation centred above or below it."""
GLYPH_STAFF_PAD = 1.2
"""Staff lines reach this far beyond the first and last symbol."""

_SPACING = ((-6, 1.7), (-5, 1.9), (-4, 2.2), (-3, 2.8), (-2, 3.6), (-1, 5.0), (0, 6.6), (1, 8.4))
"""Natural space after a note as a function of log₂ of its length in whole notes,
approximately the proportions in Gould's *Behind Bars*."""

_CLEFS = {
    Clef.TREBLE: ('gClef', 2),
    Clef.BASS: ('fClef', 6),
    Clef.ALTO: ('cClef', 4),
    Clef.TENOR: ('cClef', 6),
    Clef.TREBLE_8VB: ('gClef8vb', 2),
    Clef.PERCUSSION: ('unpitchedPercussionClef1', None),
}
"""Clef glyph and the staff position of its origin (``None``: the middle line)."""

_TREBLE_SHARPS = (8, 5, 9, 6, 3, 7, 4)
_TREBLE_FLATS = (4, 7, 3, 6, 2, 5, 1)
_KEY_POSITIONS: dict[Clef, tuple[tuple[int, ...], tuple[int, ...]]] = {
    Clef.TREBLE: (_TREBLE_SHARPS, _TREBLE_FLATS),
    Clef.TREBLE_8VB: (_TREBLE_SHARPS, _TREBLE_FLATS),
    Clef.PERCUSSION: (_TREBLE_SHARPS, _TREBLE_FLATS),
    Clef.BASS: (tuple(p - 2 for p in _TREBLE_SHARPS), tuple(p - 2 for p in _TREBLE_FLATS)),
    Clef.ALTO: (tuple(p - 1 for p in _TREBLE_SHARPS), tuple(p - 1 for p in _TREBLE_FLATS)),
    # Tenor clef sharps start low to stay inside the staff.
    Clef.TENOR: ((2, 6, 3, 7, 4, 8, 5), tuple(p + 1 for p in _TREBLE_FLATS)),
}
"""Staff positions of key signature sharps and flats, in written order."""

_NOTEHEADS = {
    NoteValue.BREVE: 'noteheadDoubleWhole',
    NoteValue.WHOLE: 'noteheadWhole',
    NoteValue.HALF: 'noteheadHalf',
}
_RESTS = {
    NoteValue.BREVE: 'restDoubleWhole',
    NoteValue.WHOLE: 'restWhole',
    NoteValue.HALF: 'restHalf',
    NoteValue.QUARTER: 'restQuarter',
    NoteValue.EIGHTH: 'rest8th',
    NoteValue.SIXTEENTH: 'rest16th',
    NoteValue.THIRTY_SECOND: 'rest32nd',
    NoteValue.SIXTY_FOURTH: 'rest64th',
}
_FLAG_NAMES = {1: '8th', 2: '16th', 3: '32nd', 4: '64th'}

UP = -1
DOWN = 1


def ideal_space(length: Fraction) -> float:
    """Natural horizontal space after a note of ``length`` whole notes."""
    if length <= 0:
        return 0.0
    exponent = math.log2(length)
    points = _SPACING
    if exponent <= points[0][0]:
        (x0, y0), (x1, y1) = points[0], points[1]
    elif exponent >= points[-1][0]:
        (x0, y0), (x1, y1) = points[-2], points[-1]
    else:
        index = next(i for i in range(1, len(points)) if points[i][0] >= exponent)
        (x0, y0), (x1, y1) = points[index - 1], points[index]
    return y0 + (y1 - y0) * (exponent - x0) / (x1 - x0)


# --- Working structures -----------------------------------------------------------------


@dataclass
class _Track:
    staff: int
    voice: int
    events: tuple[Event, ...]
    base: int
    """Index of the first event in the staff's combined numbering."""
    forced_stem: int
    times: list[Fraction] = field(default_factory=list)
    keys: list[tuple[Fraction, int, int]] = field(default_factory=list)
    """Slot key of every event: (onset, 0 for barlines and 1 otherwise, ordinal)."""
    beams: list[list[int]] = field(default_factory=list)
    stems: dict[int, int] = field(default_factory=dict)


@dataclass
class _HeadGeom:
    index: int
    pos: int
    y: float
    glyph: str
    x: float
    """Left edge of the notehead, relative to the slot until placed."""
    width: float
    origin_dx: float
    ink: Ink
    halo: bool
    accidental: str | None = None
    acc_x: float = 0.0


@dataclass
class _ChordGeom:
    track: _Track
    index: int
    chord: Chord
    heads: list[_HeadGeom]
    """Sorted from the lowest staff position to the highest."""
    stem: int
    """``UP``, ``DOWN`` or 0 for no stem."""
    flags: int
    beamed: bool
    stem_x: float = 0.0
    stem_head_y: float = 0.0
    stem_end_y: float = 0.0
    dot_x: float = 0.0
    dot_ys: list[float] = field(default_factory=list)


@dataclass
class _RestGeom:
    track: _Track
    index: int
    rest: Rest
    glyph: str
    x: float
    y: float
    bar_rest: bool
    dot_x: float = 0.0
    dot_y: float = 0.0


@dataclass
class _BarGeom:
    track: _Track
    index: int
    style: BarStyle
    lines: list[tuple[float, float]]
    """(centre x, thickness) of each vertical line."""
    dots: list[float]
    """x of each pair of repeat dots (glyph origin)."""
    width: float


@dataclass
class _Column:
    chords: list[_ChordGeom] = field(default_factory=list)
    rests: list[_RestGeom] = field(default_factory=list)
    bar: _BarGeom | None = None
    left: float = 0.0
    right: float = 0.0
    content_right: float = 0.0
    """Right extent without brackets."""

    @property
    def empty(self) -> bool:
        return not (self.chords or self.rests or self.bar)


@dataclass
class _Box:
    x0: float
    y0: float
    x1: float
    y1: float

    def union(self, other: _Box) -> _Box:
        return _Box(
            min(self.x0, other.x0),
            min(self.y0, other.y0),
            max(self.x1, other.x1),
            max(self.y1, other.y1),
        )


@dataclass
class _StaffOut:
    """A staff drawn in local coordinates (top line at y = 0)."""

    items: list[Item] = field(default_factory=list)
    halos: list[Item] = field(default_factory=list)
    regions: list[HitRegion] = field(default_factory=list)
    event_x: list[float] = field(default_factory=list)


# --- Public entry point -----------------------------------------------------------------


def layout(figure: Figure, metrics: FontMetrics, *, width: float | None = None) -> DisplayList:
    """Lay out a staff or system.

    ``width`` (in staff spaces) stretches the events to fill the given
    width; when ``None`` the natural width is used. The result is
    deterministic so it can be golden-tested.
    """
    if isinstance(figure, GlyphFigure):
        return _layout_glyphs(figure, metrics)
    if isinstance(figure, SystemSpec):
        staves = figure.staves
        system: SystemSpec | None = figure
    else:
        staves = (figure,)
        system = None
    if not staves:
        return DisplayList(items=(), width=2 * MARGIN, height=2 * MARGIN, staves=())
    engraver = _Engraver(metrics, staves, system)
    display = engraver.run(width)
    # A brace grows with the system, which is only known after stacking. If the
    # estimate used for the left margin was too small, engrave again with the real span.
    first, last = display.staves[0], display.staves[-1]
    span = last.top + last.lines - 1 - first.top
    if span > engraver.span + 1e-9:
        display = _Engraver(metrics, staves, system).run(width, span)
    return display


def _attached(name: str) -> int:
    """``-1`` for a glyph drawn above the one before it, ``1`` below, ``0`` beside it."""
    if name.endswith('Above'):
        return -1
    if name.endswith('Below'):
        return 1
    return 0


def _layout_glyphs(figure: GlyphFigure, metrics: FontMetrics) -> DisplayList:
    """Symbols side by side on one baseline (y = 0), articulations stacked on the glyph
    before them, optionally on the middle line of a staff; then moved inside the margins."""
    items: list[Item] = []
    cursor = 0.0
    # Extent of the current group (a glyph and what is attached to it): x0, x1, top, bottom.
    group: list[float] | None = None
    staff_top = -2.0  # the baseline is the middle line
    for name in figure.glyphs:
        info = metrics.glyph(name)
        side = _attached(name)
        if side and group is not None:
            x = (group[0] + group[1]) / 2 - (info.bbox_sw[0] + info.bbox_ne[0]) / 2
            if side < 0:
                bottom = group[2] - ATTACH_GAP
                if figure.staff and name.startswith('fermata'):
                    bottom = min(bottom, staff_top - ATTACH_GAP)
                y = bottom + info.bbox_sw[1]
                group[2] = y - info.bbox_ne[1]
            else:
                top = group[3] + ATTACH_GAP
                if figure.staff and name.startswith('fermata'):
                    top = max(top, staff_top + 4 + ATTACH_GAP)
                y = top + info.bbox_ne[1]
                group[3] = y - info.bbox_sw[1]
            items.append(GlyphItem(name, x, y, figure.ink))
            continue
        if group is not None:
            cursor = group[1] + GLYPH_GAP
        x = cursor - info.bbox_sw[0]
        items.append(GlyphItem(name, x, 0.0, figure.ink))
        group = [cursor, cursor + info.width, -info.bbox_ne[1], -info.bbox_sw[1]]
    if not items:
        return DisplayList(items=(), width=2 * MARGIN, height=2 * MARGIN, staves=())
    box = _items_box(items, metrics)
    staves: tuple[StaffGeometry, ...] = ()
    if figure.staff:
        thickness = metrics.engraving_default('staffLineThickness')
        x0, x1 = box.x0 - GLYPH_STAFF_PAD, box.x1 + GLYPH_STAFF_PAD
        lines = [
            LineItem(x0, staff_top + n, x1, staff_top + n, thickness, figure.ink) for n in range(5)
        ]
        items = [*lines, *items]
        box = box.union(_Box(x0, staff_top - MIN_ABOVE, x1, staff_top + 4 + MIN_BELOW))
    dx, dy = MARGIN - box.x0, MARGIN - box.y0
    shifted = tuple(_shift(item, dx, dy) for item in items)
    if figure.staff:
        staves = (StaffGeometry(Clef.PERCUSSION, staff_top + dy),)
    return DisplayList(
        items=shifted,
        width=box.x1 - box.x0 + 2 * MARGIN,
        height=box.y1 - box.y0 + 2 * MARGIN,
        staves=staves,
    )


class _Engraver:
    def __init__(
        self, metrics: FontMetrics, staves: Sequence[StaffSpec], system: SystemSpec | None
    ) -> None:
        self.m = metrics
        self.staves = tuple(staves)
        self.system = system
        self.staff_line = metrics.engraving_default('staffLineThickness')
        self.stem_t = metrics.engraving_default('stemThickness')
        self.ledger_t = metrics.engraving_default('legerLineThickness')
        self.ledger_ext = metrics.engraving_default('legerLineExtension')
        self.beam_t = metrics.engraving_default('beamThickness')
        self.beam_gap = metrics.engraving_default('beamSpacing')
        self.thin = metrics.engraving_default('thinBarlineThickness')
        self.thick = metrics.engraving_default('thickBarlineThickness')
        self.bar_sep = metrics.engraving_default('barlineSeparation')
        self.thin_thick = metrics.engraving_default('thinThickBarlineSeparation')
        self.dot_sep = metrics.engraving_default('repeatBarlineDotSeparation')
        self.tuplet_t = metrics.engraving_default('tupletBracketThickness')
        self.bracket_t = metrics.engraving_default('subBracketThickness')
        self.tie_mid = metrics.engraving_default('tieMidpointThickness')
        self.tie_end = metrics.engraving_default('tieEndpointThickness')

    # -- orchestration --

    def run(self, width: float | None, span: float | None = None) -> DisplayList:
        """Engrave once; ``span`` is the height of the system used to size the brace."""
        self.span = self._estimate_span() if span is None else span
        self._analyse()
        self._build_columns()
        left = self._left_margin()
        target = None if width is None else width - left
        outs, slot_x, staff_end = self._draw_staves(target)
        return self._assemble(outs, slot_x, staff_end, left, width)

    # -- pass 1: analysis --

    def _analyse(self) -> None:
        self.tracks: list[list[_Track]] = []
        for staff_index, staff in enumerate(self.staves):
            voices = (staff.events, *staff.voices)
            tracks: list[_Track] = []
            base = 0
            for voice_index, events in enumerate(voices):
                forced = 0 if len(voices) == 1 else (UP if voice_index == 0 else DOWN)
                track = _Track(staff_index, voice_index, tuple(events), base, forced)
                track.times = _grouping.onsets(track.events)
                track.beams = _grouping.beam_groups(track.events, staff.meter)
                track.stems = self._stem_directions(staff, track)
                tracks.append(track)
                base += len(events)
            self.tracks.append(tracks)

        # Barlines sort before the notes that start at the same time; several
        # barlines in a row (a final barline and a repeat sign) get one slot each.
        keys: set[tuple[Fraction, int, int]] = set()
        for tracks in self.tracks:
            for track in tracks:
                ordinal = 0
                for index, (event, time) in enumerate(zip(track.events, track.times, strict=True)):
                    if isinstance(event, Barline):
                        previous = track.keys[-1] if index else None
                        same = previous is not None and previous[:2] == (time, 0)
                        ordinal = ordinal + 1 if same else 0
                        key = (time, 0, ordinal)
                    else:
                        key = (time, 1, 0)
                    track.keys.append(key)
                    keys.add(key)
        self.slots = sorted(keys)
        self.slot_index = {key: i for i, key in enumerate(self.slots)}

    def _stem_directions(self, staff: StaffSpec, track: _Track) -> dict[int, int]:
        middle = staff.lines - 1
        stems: dict[int, int] = {}

        def positions(index: int) -> list[int]:
            event = track.events[index]
            assert isinstance(event, Chord)
            return [staff.clef.staff_position(head.pitch) for head in event.heads]

        def direction(indices: Iterable[int]) -> int:
            if track.forced_stem:
                return track.forced_stem
            if staff.lines == 1:
                return UP  # rhythm on a single line
            all_positions = [p for i in indices for p in positions(i)]
            above = max(p - middle for p in all_positions)
            below = max(middle - p for p in all_positions)
            return UP if below > above else DOWN

        beamed: set[int] = set()
        for group in track.beams:
            group_direction = direction(group)
            for index in group:
                stems[index] = group_direction
                beamed.add(index)
        for index, event in enumerate(track.events):
            if index in beamed or not isinstance(event, Chord) or not event.heads:
                continue
            if _has_stem(event):
                stems[index] = direction([index])
            else:
                # Stemless heads are still arranged as if the stem pointed this way.
                stems[index] = track.forced_stem or UP
        return stems

    # -- pass 2: columns --

    def _build_columns(self) -> None:
        self.columns: list[list[_Column]] = []
        self.bar_rests: set[tuple[int, int, int]] = set()
        for staff_index, staff in enumerate(self.staves):
            memory = _accidentals.AccidentalMemory(staff.key_signature)
            self.ties_in: dict[int, set[Pitch]] = {}
            columns = [_Column() for _ in self.slots]
            at_slot: dict[int, list[tuple[_Track, int]]] = {}
            for track in self.tracks[staff_index]:
                self._find_bar_rests(staff, track)
                for index, key in enumerate(track.keys):
                    at_slot.setdefault(self.slot_index[key], []).append((track, index))
            for slot, entries in sorted(at_slot.items()):
                self._build_column(staff, columns[slot], entries, memory)
            self._add_bracket_room(staff_index, staff, columns)
            self.columns.append(columns)

    def _find_bar_rests(self, staff: StaffSpec, track: _Track) -> None:
        if staff.meter is None:
            return
        events = track.events
        for index, event in enumerate(events):
            if not isinstance(event, Rest) or event.duration.length != staff.meter.bar_length:
                continue
            before = index == 0 or isinstance(events[index - 1], Barline)
            after = index == len(events) - 1 or isinstance(events[index + 1], Barline)
            if before and after:
                self.bar_rests.add((track.staff, track.voice, index))

    def _build_column(
        self,
        staff: StaffSpec,
        column: _Column,
        entries: list[tuple[_Track, int]],
        memory: _accidentals.AccidentalMemory,
    ) -> None:
        chords: list[tuple[_Track, int, Chord]] = []
        for track, index in entries:
            event = track.events[index]
            if isinstance(event, Barline):
                column.bar = self._barline(track, index, event.style)
            elif isinstance(event, Rest):
                column.rests.append(self._rest(staff, track, index, event))
            elif event.heads:
                chords.append((track, index, event))
        if column.bar is not None:
            memory.reset()

        all_heads = [head for _, _, chord in chords for head in chord.heads]
        tied = [
            head.pitch in self.ties_in.get(track.voice, set())
            for track, _, chord in chords
            for head in chord.heads
        ]
        for track, _, chord in chords:
            pitches = {head.pitch for head in chord.heads} if chord.tie_to_next else set()
            self.ties_in[track.voice] = pitches
        for rest in column.rests:
            self.ties_in[rest.track.voice] = set()
        shown = iter(memory.decide(all_heads, tied))
        for track, index, chord in chords:
            alters = [next(shown) for _ in chord.heads]
            column.chords.append(self._chord(staff, track, index, chord, alters))
        self._resolve_voice_collisions(column.chords)
        for geom in column.chords:
            self._finish_chord(staff, geom)
        self._place_accidentals(staff, column.chords)
        self._measure_column(column)

    def _measure_column(self, column: _Column) -> None:
        left, right = 0.0, 0.0
        for geom in column.chords:
            for head in geom.heads:
                left = min(left, head.x)
                right = max(right, head.x + head.width)
                if head.accidental is not None:
                    info = self.m.glyph(head.accidental)
                    left = min(left, head.acc_x + info.bbox_sw[0])
            if geom.stem:
                right = max(right, geom.stem_x + self.stem_t / 2)
            if geom.flags and not geom.beamed and geom.stem == UP:
                flag = self.m.glyph(self._flag_glyph(geom))
                right = max(right, geom.stem_x - self.stem_t / 2 + flag.bbox_ne[0])
            if geom.dot_ys:
                right = max(right, geom.dot_x + self._dots_width(geom.chord))
        for rest in column.rests:
            info = self.m.glyph(rest.glyph)
            right = max(right, rest.x + info.bbox_ne[0])
            if rest.rest.duration.dots and not rest.bar_rest:
                right = max(right, rest.dot_x + self._dots_width(rest.rest))
        if column.bar is not None:
            right = max(right, column.bar.width)
        column.left = -left
        column.right = right
        column.content_right = right

    def _dots_width(self, event: Chord | Rest) -> float:
        dots = event.duration.dots if event.duration else 0
        if not dots:
            return 0.0
        return (dots - 1) * DOT_ADVANCE + self.m.glyph('augmentationDot').bbox_ne[0]

    def _chord(
        self,
        staff: StaffSpec,
        track: _Track,
        index: int,
        chord: Chord,
        alters: list[int | None],
    ) -> _ChordGeom:
        duration = chord.duration
        glyph = 'noteheadBlack' if duration is None else _NOTEHEADS.get(duration.value)
        glyph = glyph or 'noteheadBlack'
        info = self.m.glyph(glyph)
        origin_dx = -info.anchors['noteheadOrigin'][0] if 'noteheadOrigin' in info.anchors else 0.0
        width = info.bbox_ne[0] - info.bbox_sw[0]
        heads = []
        for head_index, head in enumerate(chord.heads):
            pos = staff.clef.staff_position(head.pitch)
            alter = alters[head_index]
            heads.append(
                _HeadGeom(
                    index=head_index,
                    pos=pos,
                    y=_y(staff, pos),
                    glyph=glyph,
                    x=0.0,
                    width=width,
                    origin_dx=origin_dx,
                    ink=head.ink,
                    halo=head.halo,
                    accidental=None if alter is None else _accidentals.GLYPHS[alter],
                )
            )
        heads.sort(key=lambda h: (h.pos, h.index))
        direction = track.stems.get(index, UP)
        stemmed = _has_stem(chord)
        beamed = any(index in group for group in track.beams)
        geom = _ChordGeom(
            track=track,
            index=index,
            chord=chord,
            heads=heads,
            stem=direction if stemmed else 0,
            flags=_grouping.flag_count(duration),
            beamed=beamed,
        )
        self._displace_seconds(geom, direction, stemmed)
        return geom

    def _displace_seconds(self, geom: _ChordGeom, direction: int, stemmed: bool) -> None:
        """Put the upper (stem up) or lower (stem down) note of a second on the other side."""
        heads = geom.heads if direction == UP else list(reversed(geom.heads))
        width = heads[0].width
        shift = width - self.stem_t if stemmed else width
        previous: _HeadGeom | None = None
        previous_displaced = False
        for head in heads:
            close = previous is not None and abs(head.pos - previous.pos) <= 1
            displaced = close and not previous_displaced
            head.x = (shift if direction == UP else -shift) if displaced else 0.0
            previous, previous_displaced = head, displaced

    def _resolve_voice_collisions(self, chords: list[_ChordGeom]) -> None:
        """Move a lower voice to the right when it would collide with the upper one."""
        if len(chords) < 2:
            return
        chords.sort(key=lambda c: c.track.voice)
        upper = chords[0]
        for lower in chords[1:]:
            low_of_upper = min(h.pos for h in upper.heads)
            high_of_lower = max(h.pos for h in lower.heads)
            if low_of_upper - high_of_lower >= 2:
                continue
            same = (
                len(upper.heads) == 1
                and len(lower.heads) == 1
                and upper.heads[0].pos == lower.heads[0].pos
                and upper.heads[0].glyph == lower.heads[0].glyph
                and upper.heads[0].glyph != 'noteheadWhole'
                and upper.chord.heads[0].pitch == lower.chord.heads[0].pitch
                and (upper.chord.duration and upper.chord.duration.dots)
                == (lower.chord.duration and lower.chord.duration.dots)
            )
            if same:
                continue  # a shared unison notehead
            shift = max(h.x + h.width for h in upper.heads) + 0.1 - min(h.x for h in lower.heads)
            for head in lower.heads:
                head.x += shift

    def _finish_chord(self, staff: StaffSpec, geom: _ChordGeom) -> None:
        """Stem, flag and dots, relative to the slot."""
        heads = geom.heads
        if geom.stem:
            info = self.m.glyph(heads[0].glyph)
            normal = [h for h in heads if _is_normal(h, geom)]
            base_x = min(h.x for h in normal) if geom.stem == DOWN else max(h.x for h in normal)
            middle_y = _y(staff, staff.lines - 1)
            extra = max(0, geom.flags - 2) * EXTRA_FLAG_STEM
            if geom.stem == UP:
                anchor = info.anchors.get('stemUpSE', (info.bbox_ne[0], 0.0))
                geom.stem_x = base_x + anchor[0] - self.stem_t / 2
                geom.stem_head_y = heads[0].y - anchor[1]
                geom.stem_end_y = min(heads[-1].y - STEM_LENGTH - extra, middle_y)
            else:
                anchor = info.anchors.get('stemDownNW', (0.0, 0.0))
                geom.stem_x = base_x + anchor[0] + self.stem_t / 2
                geom.stem_head_y = heads[-1].y - anchor[1]
                geom.stem_end_y = max(heads[0].y + STEM_LENGTH + extra, middle_y)
        dots = geom.chord.duration.dots if geom.chord.duration else 0
        if dots:
            right = max(h.x + h.width for h in heads)
            dot_x = right + DOT_GAP
            if geom.stem == UP and geom.flags and not geom.beamed:
                flag = self.m.glyph(self._flag_glyph(geom))
                dot_x = max(dot_x, geom.stem_x - self.stem_t / 2 + flag.bbox_ne[0] + 0.15)
            geom.dot_x = dot_x
            used: set[int] = set()
            lower_voice = geom.track.voice > 0
            for head in sorted(heads, key=lambda h: -h.pos):
                pos = head.pos
                if pos % 2 == 0:
                    pos += -1 if lower_voice else 1
                while pos in used:
                    pos -= 2
                used.add(pos)
                geom.dot_ys.append(_y(staff, pos))

    def _flag_glyph(self, geom: _ChordGeom) -> str:
        return f'flag{_FLAG_NAMES[min(geom.flags, 4)]}{"Up" if geom.stem == UP else "Down"}'

    def _place_accidentals(self, staff: StaffSpec, chords: list[_ChordGeom]) -> None:
        heads = [head for geom in chords for head in geom.heads if head.accidental]
        if not heads:
            return
        all_heads = [head for geom in chords for head in geom.heads]
        heads_left = min(h.x for h in all_heads)
        boxes = []
        for head in heads:
            assert head.accidental is not None
            info = self.m.glyph(head.accidental)
            boxes.append(
                _accidentals.Box(
                    top=head.y - info.bbox_ne[1],
                    bottom=head.y - info.bbox_sw[1],
                    width=info.bbox_ne[0] - info.bbox_sw[0],
                )
            )
        rights = _accidentals.stack(boxes)
        for head, right, box in zip(heads, rights, boxes, strict=True):
            assert head.accidental is not None
            info = self.m.glyph(head.accidental)
            head.acc_x = heads_left - ACCIDENTAL_GAP + right - box.width - info.bbox_sw[0]

    def _rest(self, staff: StaffSpec, track: _Track, index: int, rest: Rest) -> _RestGeom:
        middle = staff.lines - 1
        bar_rest = (track.staff, track.voice, index) in self.bar_rests
        value = NoteValue.WHOLE if bar_rest else rest.duration.value
        glyph = _RESTS[value]
        # Whole rests hang from the line above the middle; the others centre on it.
        pos = middle + 2 if value is NoteValue.WHOLE and staff.lines > 1 else middle
        if track.forced_stem == UP:
            pos += 4
        elif track.forced_stem == DOWN:
            pos -= 4
        geom = _RestGeom(track, index, rest, glyph, 0.0, _y(staff, pos), bar_rest)
        if rest.duration.dots and not bar_rest:
            info = self.m.glyph(glyph)
            geom.dot_x = info.bbox_ne[0] + DOT_GAP
            geom.dot_y = _y(staff, middle + 1 + (pos - middle))
        return geom

    def _barline(self, track: _Track, index: int, style: BarStyle) -> _BarGeom:
        dot_w = self.m.glyph('repeatDot').bbox_ne[0]
        parts: list[tuple[str, float]] = []
        match style:
            case BarStyle.SINGLE:
                parts = [('thin', 0)]
            case BarStyle.DOUBLE:
                parts = [('thin', 0), ('thin', self.bar_sep)]
            case BarStyle.FINAL:
                parts = [('thin', 0), ('thick', self.thin_thick)]
            case BarStyle.REPEAT_START:
                parts = [('thick', 0), ('thin', self.thin_thick), ('dots', self.dot_sep)]
            case BarStyle.REPEAT_END:
                parts = [('dots', 0), ('thin', self.dot_sep), ('thick', self.thin_thick)]
        x = 0.0
        lines: list[tuple[float, float]] = []
        dots: list[float] = []
        for kind, gap in parts:
            x += gap
            if kind == 'dots':
                dots.append(x)
                x += dot_w
            else:
                thickness = self.thin if kind == 'thin' else self.thick
                lines.append((x + thickness / 2, thickness))
                x += thickness
        return _BarGeom(track, index, style, lines, dots, x)

    def _add_bracket_room(self, staff_index: int, staff: StaffSpec, columns: list[_Column]) -> None:
        for bracket in staff.brackets:
            located = self._locate(staff_index, bracket.last)
            if located is None:
                continue
            column = columns[located]
            room = (
                BRACKET_GAP
                + self.bracket_t
                + BRACKET_LABEL_GAP
                + _text_width(bracket.label, BRACKET_LABEL_SIZE)
            )
            column.right = max(column.right, column.content_right + room)

    def _locate(self, staff_index: int, event: int) -> int | None:
        """Slot of an event given by its combined index in a staff."""
        for track in self.tracks[staff_index]:
            if track.base <= event < track.base + len(track.events):
                return self.slot_index[track.keys[event - track.base]]
        return None

    # -- pass 3: spacing --

    def _preamble(self) -> tuple[float, float, float, float]:
        """x of the clef, key signature and time signature, and the end of the preamble."""
        clef_x = CLEF_INDENT
        clef_w = max(self._clef_width(staff) for staff in self.staves)
        key_w = max(self._key_width(staff) for staff in self.staves)
        time_w = max(self._time_width(staff) for staff in self.staves)
        x = clef_x + clef_w
        key_x = x + PREAMBLE_GAP
        if key_w:
            x = key_x + key_w
        time_x = x + PREAMBLE_GAP
        if time_w:
            x = time_x + time_w
        return clef_x, key_x, time_x, x

    def _clef_width(self, staff: StaffSpec) -> float:
        info = self.m.glyph(_CLEFS[staff.clef][0])
        return info.bbox_ne[0]

    def _key_width(self, staff: StaffSpec) -> float:
        key = staff.key_signature
        if key is None or key.fifths == 0 or staff.clef is Clef.PERCUSSION:
            return 0.0
        info = self.m.glyph('accidentalSharp' if key.fifths > 0 else 'accidentalFlat')
        width = info.bbox_ne[0]
        return key.count * width + (key.count - 1) * KEY_ACCIDENTAL_GAP

    def _time_width(self, staff: StaffSpec) -> float:
        if staff.meter is None:
            return 0.0
        top, bottom = _time_digits(staff.meter)
        return max(self._digits_width(top), self._digits_width(bottom))

    def _digits_width(self, glyphs: Sequence[str]) -> float:
        return sum(self.m.glyph(g).advance for g in glyphs)

    def _space(self, target: float | None) -> tuple[list[float], float, float]:
        """x of every slot, the end of the staves and the end of the preamble."""
        *_, preamble_end = self._preamble()
        n = len(self.slots)
        if n == 0:
            natural = EMPTY_STAFF_TAIL
            end = preamble_end + max(natural, (target or 0) - preamble_end)
            return [], end, preamble_end

        def lefts(i: int) -> list[float]:
            return [cols[i].left for cols in self.columns if not cols[i].empty]

        def is_bar(i: int) -> bool:
            return self.slots[i][1] == 0

        first_gap = FIRST_NOTE_GAP if not is_bar(0) else AFTER_BARLINE / 2
        lead = first_gap + max(lefts(0), default=0.0)
        x0 = preamble_end + lead

        # Natural spring lengths; they double as weights when the staff is stretched,
        # so extra space is shared in proportion to duration. The space after a
        # barline stays fixed.
        ideals: list[float] = []
        weights: list[float] = []
        for i in range(n - 1):
            if is_bar(i):
                ideals.append(0.0)
                weights.append(0.0)
                continue
            delta = self.slots[i + 1][0] - self.slots[i][0]
            ideal = STEMLESS_SPACE if self._all_stemless(i) else ideal_space(delta)
            if is_bar(i + 1):
                ideal -= AFTER_BARLINE
            ideals.append(ideal)
            weights.append(max(ideal, 0.0))

        def place(use_ideal: bool) -> list[float]:
            xs = [x0]
            last_right: list[float | None] = [None] * len(self.staves)
            for k, cols in enumerate(self.columns):
                if not cols[0].empty:
                    last_right[k] = x0 + cols[0].right
            for j in range(1, n):
                x = xs[-1] + (ideals[j - 1] if use_ideal else 0.0)
                for k, cols in enumerate(self.columns):
                    column = cols[j]
                    if column.empty or last_right[k] is None:
                        continue
                    pad = COLUMN_PAD
                    if is_bar(j):
                        pad = BEFORE_BARLINE
                    elif is_bar(j - 1):
                        pad = AFTER_BARLINE
                    previous = last_right[k]
                    assert previous is not None
                    x = max(x, previous + pad + column.left)
                xs.append(x)
                for k, cols in enumerate(self.columns):
                    if not cols[j].empty:
                        last_right[k] = x + cols[j].right
            return xs

        natural_xs = place(True)
        minimal_xs = place(False)
        springs = [b - a for a, b in itertools.pairwise(natural_xs)]
        minimum = [b - a for a, b in itertools.pairwise(minimal_xs)]

        # The space after the last column.
        last = n - 1
        last_right = max(cols[last].right for cols in self.columns if not cols[last].empty)
        if is_bar(last):
            tail_min = tail = last_right
            weights.append(0.0)
        else:
            tail_min = last_right + END_PAD
            lengths = [
                _grouping.event_length(track.events[i])
                for tracks in self.tracks
                for track in tracks
                for i, key in enumerate(track.keys)
                if key == self.slots[last]
            ]
            length = max(lengths, default=_grouping.STEMLESS_LENGTH)
            tail = STEMLESS_SPACE if self._all_stemless(last) else ideal_space(length)
            weights.append(tail)
            tail = max(tail, tail_min)
        springs.append(tail)
        minimum.append(tail_min)
        # Later springs must also respect the rods of non-adjacent columns.
        springs = [max(s, m) for s, m in zip(springs, minimum, strict=True)]

        if target is not None:
            # The gap before the first note takes a share too, so that a few notes
            # on a wide staff spread out evenly instead of huddling by the clef.
            stretchy = [w for w in weights if w > 0]
            lead_weight = 0.5 * sum(stretchy) / len(stretchy) if stretchy else 0.0
            fitted = _fit(
                [lead, *springs],
                [lead, *minimum],
                [lead_weight, *weights],
                target - preamble_end,
            )
            x0 = preamble_end + fitted[0]
            springs = fitted[1:]
        xs = [x0]
        for spring in springs[:-1]:
            xs.append(xs[-1] + spring)
        return xs, xs[-1] + springs[-1], preamble_end

    def _all_stemless(self, slot: int) -> bool:
        found = False
        for cols in self.columns:
            column = cols[slot]
            if column.rests:
                return False
            for geom in column.chords:
                if geom.chord.duration is not None:
                    return False
                found = True
        return found

    # -- pass 4: drawing --

    def _left_margin(self) -> float:
        if self.system is None:
            return 0.0
        left = 0.0
        if len(self.staves) > 1 and self.system.brace:
            left += BRACE_GAP + self.m.glyph('brace').bbox_ne[0] * self.span / 4
        if self.system.labels:
            widest = max(_text_width(label, SYSTEM_LABEL_SIZE) for label in self.system.labels)
            left += widest + SYSTEM_LABEL_GAP + MARGIN
        return left

    def _estimate_span(self) -> float:
        # The smallest possible span; layout() engraves again if the real one is larger.
        return sum(s.lines - 1 for s in self.staves) + STAFF_DISTANCE * (len(self.staves) - 1)

    def _draw_staves(self, target: float | None) -> tuple[list[_StaffOut], list[float], float]:
        slot_x, staff_end, preamble_end = self._space(target)
        clef_x, key_x, time_x, _ = self._preamble()
        outs = []
        for staff_index, staff in enumerate(self.staves):
            out = _StaffOut()
            out.event_x = [0.0] * sum(len(t.events) for t in self.tracks[staff_index])
            self._draw_staff_lines(out, staff, staff_end)
            self._draw_clef(out, staff, clef_x)
            self._draw_key(out, staff, key_x)
            self._draw_time(out, staff, time_x)
            columns = self.columns[staff_index]
            for slot, column in enumerate(columns):
                self._place_column(column, slot_x[slot])
            self._center_bar_rests(staff_index, slot_x, staff_end, preamble_end)
            for track in self.tracks[staff_index]:
                self._draw_beams(out, staff, track)
            for column in columns:
                self._draw_column(out, staff, column)
            for track in self.tracks[staff_index]:
                self._draw_tuplets(out, staff, track)
                self._draw_ties(out, staff, track)
            for bracket in staff.brackets:
                self._draw_bracket(out, staff_index, staff, bracket)
            self._draw_labels(out, staff, columns)
            outs.append(out)
        return outs, slot_x, staff_end

    def _draw_staff_lines(self, out: _StaffOut, staff: StaffSpec, end: float) -> None:
        for line in range(staff.lines):
            out.items.append(LineItem(0.0, float(line), end, float(line), self.staff_line))

    def _draw_clef(self, out: _StaffOut, staff: StaffSpec, x: float) -> None:
        glyph, pos = _CLEFS[staff.clef]
        position = staff.lines - 1 if pos is None else pos
        out.items.append(GlyphItem(glyph, x, _y(staff, position)))

    def _draw_key(self, out: _StaffOut, staff: StaffSpec, x: float) -> None:
        key = staff.key_signature
        if key is None or key.fifths == 0 or staff.clef is Clef.PERCUSSION:
            return
        sharps, flats = _KEY_POSITIONS[staff.clef]
        positions = sharps if key.fifths > 0 else flats
        glyph = 'accidentalSharp' if key.fifths > 0 else 'accidentalFlat'
        width = self.m.glyph(glyph).bbox_ne[0]
        for i in range(key.count):
            out.items.append(GlyphItem(glyph, x, _y(staff, positions[i])))
            x += width + KEY_ACCIDENTAL_GAP

    def _draw_time(self, out: _StaffOut, staff: StaffSpec, x: float) -> None:
        if staff.meter is None:
            return
        top, bottom = _time_digits(staff.meter)
        width = self._time_width(staff)
        middle = _y(staff, staff.lines - 1)
        for glyphs, y in ((top, middle - 1), (bottom, middle + 1)):
            gx = x + (width - self._digits_width(glyphs)) / 2
            for glyph in glyphs:
                out.items.append(GlyphItem(glyph, gx, y))
                gx += self.m.glyph(glyph).advance

    def _place_column(self, column: _Column, x: float) -> None:
        """Turn the column's relative x coordinates into absolute ones."""
        for geom in column.chords:
            for head in geom.heads:
                head.x += x
                head.acc_x += x
            geom.stem_x += x
            geom.dot_x += x
        for rest in column.rests:
            rest.x += x
            rest.dot_x += x
        if column.bar is not None:
            bar = column.bar
            bar.lines = [(cx + x, t) for cx, t in bar.lines]
            bar.dots = [dx + x for dx in bar.dots]

    def _center_bar_rests(
        self, staff_index: int, slot_x: list[float], staff_end: float, preamble_end: float
    ) -> None:
        columns = self.columns[staff_index]
        for slot, column in enumerate(columns):
            for rest in column.rests:
                if not rest.bar_rest:
                    continue
                start = preamble_end
                for previous in range(slot - 1, -1, -1):
                    bar = columns[previous].bar
                    if bar is not None:
                        start = slot_x[previous] + bar.width
                        break
                end = staff_end
                for following in range(slot + 1, len(columns)):
                    if columns[following].bar is not None:
                        end = slot_x[following]
                        break
                info = self.m.glyph(rest.glyph)
                rest.x = (start + end) / 2 - info.bbox_ne[0] / 2

    def _draw_column(self, out: _StaffOut, staff: StaffSpec, column: _Column) -> None:
        bottom = float(staff.lines - 1)
        for geom in column.chords:
            self._draw_chord(out, staff, geom)
        for rest in column.rests:
            ink = rest.rest.ink
            out.items.append(GlyphItem(rest.glyph, rest.x, rest.y, ink))
            info = self.m.glyph(rest.glyph)
            if rest.rest.duration.dots and not rest.bar_rest:
                for d in range(rest.rest.duration.dots):
                    x = rest.dot_x + d * DOT_ADVANCE
                    out.items.append(GlyphItem('augmentationDot', x, rest.dot_y, ink))
            x0, x1 = rest.x + info.bbox_sw[0], rest.x + info.bbox_ne[0]
            index = rest.track.base + rest.index
            out.event_x[index] = (x0 + x1) / 2
            y0 = min(-1.0, rest.y - info.bbox_ne[1])
            y1 = max(bottom + 1, rest.y - info.bbox_sw[1])
            out.regions.append(
                HitRegion(rest.track.staff, index, None, x0 - 0.2, y0, x1 - x0 + 0.4, y1 - y0)
            )
        if column.bar is not None:
            bar = column.bar
            top, end = (-1.0, 1.0) if staff.lines == 1 else (0.0, bottom)
            for cx, thickness in bar.lines:
                out.items.append(LineItem(cx, top, cx, end, thickness))
            middle = staff.lines - 1
            for dx in bar.dots:
                for pos in (middle - 1, middle + 1):
                    out.items.append(GlyphItem('repeatDot', dx, _y(staff, pos)))
            index = bar.track.base + bar.index
            x0 = bar.lines[0][0] - bar.lines[0][1] / 2 if bar.lines else bar.dots[0]
            out.event_x[index] = x0 + bar.width / 2
            out.regions.append(
                HitRegion(bar.track.staff, index, None, x0 - 0.3, top - 1, bar.width + 0.6, 6)
            )

    def _draw_chord(self, out: _StaffOut, staff: StaffSpec, geom: _ChordGeom) -> None:
        chord = geom.chord
        staff_index = geom.track.staff
        event = geom.track.base + geom.index
        top_pos = 2 * (staff.lines - 1)
        # Ledger lines, one per staff position, as wide as the heads that need them.
        ledgers: dict[int, tuple[float, float, bool]] = {}
        for head in geom.heads:
            needed = list(range(-2, head.pos - 1, -2)) + list(range(top_pos + 2, head.pos + 1, 2))
            for pos in needed:
                x0, x1, acc = ledgers.get(pos, (math.inf, -math.inf, False))
                ledgers[pos] = (
                    min(x0, head.x),
                    max(x1, head.x + head.width),
                    acc or head.accidental is not None,
                )
        for pos, (x0, x1, acc) in sorted(ledgers.items()):
            left_ext = LEDGER_ACCIDENTAL_EXTENSION if acc else self.ledger_ext
            y = _y(staff, pos)
            out.items.append(LineItem(x0 - left_ext, y, x1 + self.ledger_ext, y, self.ledger_t))

        for head in geom.heads:
            if head.halo:
                out.halos.append(CircleItem(head.x + head.width / 2, head.y, HALO_RADIUS))
            out.items.append(GlyphItem(head.glyph, head.x + head.origin_dx, head.y, head.ink))
            if head.accidental is not None:
                out.items.append(GlyphItem(head.accidental, head.acc_x, head.y, head.ink))
            out.regions.append(
                HitRegion(
                    staff_index,
                    event,
                    head.index,
                    head.x - 0.1,
                    head.y - 0.6,
                    head.width + 0.2,
                    1.2,
                )
            )

        if geom.stem:
            out.items.append(
                LineItem(
                    geom.stem_x,
                    geom.stem_head_y,
                    geom.stem_x,
                    geom.stem_end_y,
                    self.stem_t,
                    chord.ink,
                )
            )
            if geom.flags and not geom.beamed:
                glyph = self._flag_glyph(geom)
                info = self.m.glyph(glyph)
                left = geom.stem_x - self.stem_t / 2
                if geom.stem == UP:
                    ax, ay = info.anchors.get('stemUpNW', (0.0, 0.0))
                else:
                    ax, ay = info.anchors.get('stemDownSW', (0.0, 0.0))
                out.items.append(GlyphItem(glyph, left - ax, geom.stem_end_y + ay, chord.ink))
        dots = chord.duration.dots if chord.duration else 0
        for y in geom.dot_ys:
            for d in range(dots):
                x = geom.dot_x + d * DOT_ADVANCE
                out.items.append(GlyphItem('augmentationDot', x, y, chord.ink))

        box = self._chord_box(geom)
        out.event_x[event] = (
            min(h.x for h in geom.heads if _is_normal(h, geom)) + geom.heads[0].width / 2
        )
        y0 = min(box.y0, -1.0)
        y1 = max(box.y1, staff.lines)
        out.regions.append(
            HitRegion(staff_index, event, None, box.x0 - 0.2, y0, box.x1 - box.x0 + 0.4, y1 - y0)
        )

    def _chord_box(self, geom: _ChordGeom) -> _Box:
        box = _Box(math.inf, math.inf, -math.inf, -math.inf)
        for head in geom.heads:
            box = box.union(_Box(head.x, head.y - 0.5, head.x + head.width, head.y + 0.5))
            if head.accidental is not None:
                info = self.m.glyph(head.accidental)
                box = box.union(_Box(head.acc_x + info.bbox_sw[0], head.y, head.acc_x, head.y))
        if geom.stem:
            y0, y1 = sorted((geom.stem_head_y, geom.stem_end_y))
            box = box.union(_Box(geom.stem_x, y0, geom.stem_x, y1))
        return box

    def _draw_beams(self, out: _StaffOut, staff: StaffSpec, track: _Track) -> None:
        columns = self.columns[track.staff]
        by_index = {
            (geom.track.voice, geom.index): geom for column in columns for geom in column.chords
        }
        middle_y = _y(staff, staff.lines - 1)
        for group in track.beams:
            geoms = [by_index[(track.voice, i)] for i in group]
            direction = geoms[0].stem
            near = [g.heads[-1].y if direction == UP else g.heads[0].y for g in geoms]
            xs = [g.stem_x for g in geoms]
            beams = [g.flags for g in geoms]
            inner = near[1:-1]
            if direction == UP:
                concave = any(y < min(near[0], near[-1]) for y in inner)
            else:
                concave = any(y > max(near[0], near[-1]) for y in inner)
            rise = 0.0 if concave else max(-1.0, min(1.0, (near[-1] - near[0]) / 2))
            span = xs[-1] - xs[0]
            slope = rise / span if span > 0 else 0.0
            length = STEM_LENGTH + max(0, max(beams) - 2) * EXTRA_FLAG_STEM
            offsets = [slope * (x - xs[0]) for x in xs]
            if direction == UP:
                start = min(y - length - o for y, o in zip(near, offsets, strict=True))
                start = min([start] + [middle_y - o for o in offsets])
            else:
                start = max(y + length - o for y, o in zip(near, offsets, strict=True))
                start = max([start] + [middle_y - o for o in offsets])
            for geom, offset in zip(geoms, offsets, strict=True):
                geom.stem_end_y = start + offset
            inward = -direction  # from the stem end towards the noteheads
            half = self.stem_t / 2
            ink = geoms[0].chord.ink

            step = self.beam_t + self.beam_gap
            origin = xs[0]

            for level in range(max(beams)):
                i = 0
                while i < len(geoms):
                    if beams[i] <= level:
                        i += 1
                        continue
                    j = i
                    while j + 1 < len(geoms) and beams[j + 1] > level:
                        j += 1
                    if j > i:
                        x1, x2 = xs[i] - half, xs[j] + half
                    else:
                        stub = min(1.1, span / 2 / max(1, len(geoms) - 1))
                        if i == len(geoms) - 1 and i > 0:
                            x1, x2 = xs[i] - stub, xs[i] + half
                        else:
                            x1, x2 = xs[i] - half, xs[i] + stub
                    depth = inward * (self.beam_t / 2 + level * step)
                    y1 = start + slope * (x1 - origin) + depth
                    y2 = start + slope * (x2 - origin) + depth
                    out.items.append(BeamItem(x1, y1, x2, y2, self.beam_t, ink))
                    i = j + 1

    def _draw_tuplets(self, out: _StaffOut, staff: StaffSpec, track: _Track) -> None:
        geoms = self._track_geoms(track)
        beam_sets = [set(group) for group in track.beams]
        for tuplet, group in _grouping.tuplet_groups(track.events):
            members = [geoms[i] for i in group if i in geoms]
            if not members:
                continue
            stems = [g.stem for g in members if isinstance(g, _ChordGeom) and g.stem]
            above = not stems or sum(stems) <= 0
            if track.forced_stem:
                above = track.forced_stem == UP
            boxes = [self._geom_box(g) for g in members]
            x0, x1 = boxes[0].x0, boxes[-1].x1
            if above:
                y = min(min(b.y0 for b in boxes) - TUPLET_CLEARANCE, -TUPLET_CLEARANCE)
            else:
                bottom = staff.lines - 1
                y = max(max(b.y1 for b in boxes) + TUPLET_CLEARANCE, bottom + TUPLET_CLEARANCE)
            digits = [f'tuplet{d}' for d in str(tuplet.actual)]
            width = self._digits_width(digits)
            center = (x0 + x1) / 2
            gx = center - width / 2
            for digit in digits:
                info = self.m.glyph(digit)
                out.items.append(GlyphItem(digit, gx, y + info.bbox_ne[1] / 2))
                gx += info.advance
            if set(group) in beam_sets:
                continue
            hook = TUPLET_HOOK if above else -TUPLET_HOOK
            t = self.tuplet_t
            left_end = center - width / 2 - TUPLET_GAP
            right_start = center + width / 2 + TUPLET_GAP
            out.items.append(LineItem(x0, y, left_end, y, t))
            out.items.append(LineItem(right_start, y, x1, y, t))
            out.items.append(LineItem(x0 + t / 2, y - t / 2, x0 + t / 2, y + hook, t))
            out.items.append(LineItem(x1 - t / 2, y - t / 2, x1 - t / 2, y + hook, t))

    def _track_geoms(self, track: _Track) -> dict[int, _ChordGeom | _RestGeom]:
        result: dict[int, _ChordGeom | _RestGeom] = {}
        for column in self.columns[track.staff]:
            for geom in column.chords:
                if geom.track is track:
                    result[geom.index] = geom
            for rest in column.rests:
                if rest.track is track:
                    result[rest.index] = rest
        return result

    def _geom_box(self, geom: _ChordGeom | _RestGeom) -> _Box:
        if isinstance(geom, _ChordGeom):
            box = self._chord_box(geom)
            if geom.stem:
                box = box.union(
                    _Box(
                        geom.stem_x + self.stem_t / 2, box.y0, geom.stem_x + self.stem_t / 2, box.y1
                    )
                )
            return box
        info = self.m.glyph(geom.glyph)
        return _Box(
            geom.x + info.bbox_sw[0],
            geom.y - info.bbox_ne[1],
            geom.x + info.bbox_ne[0],
            geom.y - info.bbox_sw[1],
        )

    def _draw_ties(self, out: _StaffOut, staff: StaffSpec, track: _Track) -> None:
        geoms = self._track_geoms(track)
        middle = staff.lines - 1
        for index, event in enumerate(track.events):
            if not isinstance(event, Chord) or not event.tie_to_next or index not in geoms:
                continue
            target = None
            for following in range(index + 1, len(track.events)):
                candidate = track.events[following]
                if isinstance(candidate, Barline):
                    continue
                if isinstance(candidate, Chord) and following in geoms:
                    target = geoms[following]
                break
            start = geoms[index]
            if not isinstance(target, _ChordGeom) or not isinstance(start, _ChordGeom):
                continue
            heads = start.heads
            for order, head in enumerate(heads):
                pitch = event.heads[head.index].pitch
                match = [h for h in target.heads if target.chord.heads[h.index].pitch == pitch]
                if not match:
                    continue
                other = match[0]
                if track.forced_stem:
                    up = track.forced_stem == UP
                elif len(heads) == 1:
                    stem = start.stem or (UP if head.pos < middle else DOWN)
                    up = stem == DOWN
                elif len(heads) % 2 and order == len(heads) // 2:
                    up = head.pos >= middle
                else:
                    up = order >= len(heads) / 2
                sign = -1 if up else 1
                x1 = head.x + head.width + TIE_GAP
                x2 = other.x - TIE_GAP
                if x2 <= x1:
                    continue
                bulge = sign * min(0.45 + 0.04 * (x2 - x1), 0.8)
                y1 = head.y + sign * TIE_OFFSET
                y2 = other.y + sign * TIE_OFFSET
                out.items.append(
                    CurveItem(x1, y1, x2, y2, bulge, self.tie_mid, self.tie_end, event.ink)
                )

    def _draw_bracket(
        self, out: _StaffOut, staff_index: int, staff: StaffSpec, bracket: Bracket
    ) -> None:
        ys: list[float] = []
        right = -math.inf
        for track in self.tracks[staff_index]:
            geoms = self._track_geoms(track)
            for local, geom in geoms.items():
                if not bracket.first <= track.base + local <= bracket.last:
                    continue
                box = self._geom_box(geom)
                if isinstance(geom, _ChordGeom):
                    ys.extend(h.y for h in geom.heads)
                    right = max(right, max(h.x + h.width for h in geom.heads))
                else:
                    ys.append(geom.y)
                    right = max(right, box.x1)
        if not ys:
            return
        top, bottom = min(ys) - BRACKET_PAD, max(ys) + BRACKET_PAD
        x = right + BRACKET_GAP + self.bracket_t / 2
        t = self.bracket_t
        out.items.append(LineItem(x, top, x, bottom, t, bracket.ink))
        out.items.append(
            LineItem(x - BRACKET_HOOK, top + t / 2, x + t / 2, top + t / 2, t, bracket.ink)
        )
        out.items.append(
            LineItem(x - BRACKET_HOOK, bottom - t / 2, x + t / 2, bottom - t / 2, t, bracket.ink)
        )
        size = BRACKET_LABEL_SIZE
        baseline = (top + bottom) / 2 + size * (TEXT_ASCENT - TEXT_DESCENT) / 2
        out.items.append(
            TextItem(
                bracket.label,
                x + t / 2 + BRACKET_LABEL_GAP,
                baseline,
                size,
                Align.START,
                True,
                bracket.ink,
            )
        )

    def _draw_labels(self, out: _StaffOut, staff: StaffSpec, columns: list[_Column]) -> None:
        labelled = [g for column in columns for g in column.chords if g.chord.label]
        if not labelled:
            return
        lowest = max(_item_box(item, self.m).y1 for item in out.items)
        bottom = staff.lines - 1
        baseline = max(bottom + LABEL_MIN_BASELINE, lowest + LABEL_CLEARANCE + LABEL_SIZE * 0.75)
        for geom in labelled:
            chord = geom.chord
            assert chord.label is not None
            index = geom.track.base + geom.index
            highlighted = chord.ink is not Ink.FOREGROUND
            ink = chord.ink if highlighted else Ink.DIM
            out.items.append(
                TextItem(
                    chord.label,
                    out.event_x[index],
                    baseline,
                    LABEL_SIZE,
                    Align.CENTER,
                    highlighted,
                    ink,
                )
            )

    # -- stacking and assembly --

    def _assemble(
        self,
        outs: list[_StaffOut],
        slot_x: list[float],
        staff_end: float,
        left: float,
        width: float | None,
    ) -> DisplayList:
        # Vertical stacking.
        tops: list[float] = []
        y = MARGIN
        previous_below = 0.0
        for index, (staff, out) in enumerate(zip(self.staves, outs, strict=True)):
            box = _items_box(out.items + out.halos, self.m)
            bottom = staff.lines - 1
            above = max(-box.y0, 0.0)
            below = max(box.y1 - bottom, 0.0)
            if index == 0:
                top = y + max(above, MIN_ABOVE)
            else:
                previous = self.staves[index - 1]
                gap = max(STAFF_DISTANCE, previous_below + above + STAFF_CLEARANCE)
                top = tops[-1] + previous.lines - 1 + gap
            tops.append(top)
            previous_below = below
        last = self.staves[-1]
        bottom_y = tops[-1] + last.lines - 1
        height = bottom_y + max(previous_below, MIN_BELOW) + MARGIN

        halos: list[Item] = []
        items: list[Item] = []
        regions: list[HitRegion] = []
        event_x: list[tuple[float, ...]] = []
        for top, out in zip(tops, outs, strict=True):
            halos.extend(_shift(item, left, top) for item in out.halos)
            items.extend(_shift(item, left, top) for item in out.items)
            regions.extend(dataclasses.replace(r, x=r.x + left, y=r.y + top) for r in out.regions)
            event_x.append(tuple(x + left for x in out.event_x))
        # Halos go first so that they are drawn behind everything else.
        items = halos + items

        if self.system is not None and len(self.staves) > 1:
            items.extend(self._system_items(tops, slot_x, left))
        elif self.system is not None and self.system.labels:
            items.extend(self._system_labels(tops, left))

        content_right = max(_item_box(item, self.m).x1 for item in items) if items else 0.0
        total_width = max(left + staff_end, content_right + 0.0)
        if width is not None:
            total_width = max(total_width, width)
        # Keep everything inside the box vertically, too (very low labels, ledger lines).
        box = _items_box(items, self.m) if items else _Box(0, 0, 0, 0)
        height = max(height, box.y1 + MARGIN)
        staves = tuple(
            StaffGeometry(staff.clef, top, staff.lines)
            for staff, top in zip(self.staves, tops, strict=True)
        )
        return DisplayList(
            items=tuple(items),
            width=total_width,
            height=height,
            staves=staves,
            hit_regions=tuple(regions),
            event_x=tuple(event_x),
        )

    def _system_items(self, tops: list[float], slot_x: list[float], left: float) -> list[Item]:
        assert self.system is not None
        items: list[Item] = []
        first_top = tops[0]
        last_bottom = tops[-1] + self.staves[-1].lines - 1
        items.append(
            LineItem(left + self.thin / 2, first_top, left + self.thin / 2, last_bottom, self.thin)
        )
        if self.system.brace:
            span = last_bottom - first_top
            scale = span / 4
            info = self.m.glyph('brace')
            x = left - BRACE_GAP - info.bbox_ne[0] * scale
            items.append(GlyphItem('brace', x, last_bottom, Ink.FOREGROUND, scale))
            # Barlines run through the gaps between braced staves.
            for slot, (_, kind, _) in enumerate(self.slots):
                if kind != 0:
                    continue
                for k in range(len(self.staves) - 1):
                    upper = self.columns[k][slot].bar
                    lower = self.columns[k + 1][slot].bar
                    if upper is None or lower is None:
                        continue
                    y0 = tops[k] + self.staves[k].lines - 1
                    y1 = tops[k + 1]
                    for cx, thickness in upper.lines:
                        items.append(LineItem(cx + left, y0, cx + left, y1, thickness))
        items.extend(self._system_labels(tops, left))
        return items

    def _system_labels(self, tops: list[float], left: float) -> list[Item]:
        assert self.system is not None
        items: list[Item] = []
        x = left - SYSTEM_LABEL_GAP
        if len(self.staves) > 1 and self.system.brace:
            span = tops[-1] + self.staves[-1].lines - 1 - tops[0]
            x -= BRACE_GAP + self.m.glyph('brace').bbox_ne[0] * span / 4
        for label, staff, top in zip(self.system.labels, self.staves, tops, strict=False):
            middle = top + (staff.lines - 1) / 2
            size = SYSTEM_LABEL_SIZE
            baseline = middle + size * (TEXT_ASCENT - TEXT_DESCENT) / 2
            items.append(TextItem(label, x, baseline, size, Align.END, False, Ink.FOREGROUND))
        return items


# --- Helpers ----------------------------------------------------------------------------


def _y(staff: StaffSpec, position: int) -> float:
    """y of a staff position in staff-local coordinates (top line at 0)."""
    return (staff.lines - 1) - position / 2


def _has_stem(chord: Chord) -> bool:
    duration = chord.duration
    return duration is not None and duration.value.value <= NoteValue.HALF.value


def _is_normal(head: _HeadGeom, geom: _ChordGeom) -> bool:
    """Whether a head sits on the normal side of the stem (not displaced by a second)."""
    reference = min(h.x for h in geom.heads) if geom.stem != DOWN else max(h.x for h in geom.heads)
    return head.x == reference


def _time_digits(meter: Meter) -> tuple[list[str], list[str]]:
    return (
        [f'timeSig{d}' for d in str(meter.beats)],
        [f'timeSig{d}' for d in str(meter.beat_unit)],
    )


def _text_width(text: str, size: float) -> float:
    return len(text) * TEXT_WIDTH * size


def _fit(
    springs: list[float], minimum: list[float], weights: list[float], target: float
) -> list[float]:
    """Stretch or compress springs so that they add up to ``target`` where possible.

    Stretching shares the extra space in proportion to ``weights``;
    compressing moves every spring towards its minimum by the same fraction.
    """
    natural = sum(springs)
    if target >= natural:
        total = sum(weights)
        if total <= 0:
            return springs
        extra = target - natural
        return [s + extra * w / total for s, w in zip(springs, weights, strict=True)]
    least = sum(minimum)
    if target <= least or natural <= least:
        return list(minimum)
    fraction = (target - least) / (natural - least)
    return [m + (s - m) * fraction for s, m in zip(springs, minimum, strict=True)]


def _item_box(item: Item, metrics: FontMetrics) -> _Box:
    """Bounding box of a display item, used for collision checks and the figure size."""
    match item:
        case GlyphItem():
            info = metrics.glyph(item.glyph)
            s = item.scale
            return _Box(
                item.x + info.bbox_sw[0] * s,
                item.y - info.bbox_ne[1] * s,
                item.x + info.bbox_ne[0] * s,
                item.y - info.bbox_sw[1] * s,
            )
        case LineItem():
            dx, dy = item.x2 - item.x1, item.y2 - item.y1
            length = math.hypot(dx, dy) or 1.0
            px, py = abs(dy / length) * item.thickness / 2, abs(dx / length) * item.thickness / 2
            return _Box(
                min(item.x1, item.x2) - px,
                min(item.y1, item.y2) - py,
                max(item.x1, item.x2) + px,
                max(item.y1, item.y2) + py,
            )
        case BeamItem():
            half = item.thickness / 2
            return _Box(
                min(item.x1, item.x2),
                min(item.y1, item.y2) - half,
                max(item.x1, item.x2),
                max(item.y1, item.y2) + half,
            )
        case CircleItem():
            r = item.radius
            return _Box(item.cx - r, item.cy - r, item.cx + r, item.cy + r)
        case CurveItem():
            mid = (item.y1 + item.y2) / 2 + item.bulge
            ys = (item.y1, item.y2, mid + math.copysign(item.thickness / 2, item.bulge))
            return _Box(min(item.x1, item.x2), min(ys), max(item.x1, item.x2), max(ys))
        case TextItem():
            width = _text_width(item.text, item.size)
            if item.align is Align.START:
                x0 = item.x
            elif item.align is Align.END:
                x0 = item.x - width
            else:
                x0 = item.x - width / 2
            return _Box(
                x0, item.y - TEXT_ASCENT * item.size, x0 + width, item.y + TEXT_DESCENT * item.size
            )


def _items_box(items: Iterable[Item], metrics: FontMetrics) -> _Box:
    box = _Box(math.inf, math.inf, -math.inf, -math.inf)
    for item in items:
        box = box.union(_item_box(item, metrics))
    return box


def item_bounds(item: Item, metrics: FontMetrics) -> tuple[float, float, float, float]:
    """(x0, y0, x1, y1) of an item as the engraver sees it; useful for tests and tools."""
    box = _item_box(item, metrics)
    return box.x0, box.y0, box.x1, box.y1


def _shift(item: Item, dx: float, dy: float) -> Item:
    match item:
        case GlyphItem() | TextItem():
            return dataclasses.replace(item, x=item.x + dx, y=item.y + dy)
        case LineItem() | BeamItem() | CurveItem():
            return dataclasses.replace(
                item, x1=item.x1 + dx, y1=item.y1 + dy, x2=item.x2 + dx, y2=item.y2 + dy
            )
        case CircleItem():
            return dataclasses.replace(item, cx=item.cx + dx, cy=item.cy + dy)
