# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import itertools
from fractions import Fraction
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from etude.core import Duration, KeySignature, Letter, Meter, NoteValue, Pitch, Tuplet
from etude.notation.displaylist import (
    BeamItem,
    CircleItem,
    CurveItem,
    DisplayList,
    GlyphItem,
    LineItem,
    TextItem,
)
from etude.notation.layout import ideal_space, item_bounds, layout
from etude.notation.smufl import FontMetrics
from etude.notation.spec import (
    Barline,
    BarStyle,
    Bracket,
    Chord,
    Clef,
    Event,
    Head,
    Ink,
    Rest,
    StaffSpec,
    SystemSpec,
)

W = Duration(NoteValue.WHOLE)
H = Duration(NoteValue.HALF)
Q = Duration(NoteValue.QUARTER)
E = Duration(NoteValue.EIGHTH)
S = Duration(NoteValue.SIXTEENTH)


def note(*pitches: str, d: Duration | None = None, **kwargs: Any) -> Chord:
    return Chord(tuple(Head(Pitch.parse(p)) for p in pitches), d, **kwargs)


def glyphs(display: DisplayList, name: str) -> list[GlyphItem]:
    return [i for i in display.items if isinstance(i, GlyphItem) and i.glyph == name]


def stems(display: DisplayList, metrics: FontMetrics) -> list[LineItem]:
    thickness = metrics.engraving_default('stemThickness')
    return [
        i
        for i in display.items
        if isinstance(i, LineItem) and i.thickness == thickness and i.x1 == i.x2
    ]


def ledger_ys(display: DisplayList, metrics: FontMetrics) -> list[float]:
    thickness = metrics.engraving_default('legerLineThickness')
    return sorted(
        round(i.y1, 6)
        for i in display.items
        if isinstance(i, LineItem) and i.thickness == thickness and i.y1 == i.y2
    )


# --- Basic behaviour --------------------------------------------------------------------


def test_ideal_space_grows_with_duration() -> None:
    lengths = [Fraction(1, 128), Fraction(1, 16), Fraction(1, 8), Fraction(1, 4), Fraction(4)]
    spaces = [ideal_space(length) for length in lengths]
    assert spaces == sorted(spaces)
    assert ideal_space(Fraction(0)) == 0
    assert ideal_space(Fraction(1, 4)) == pytest.approx(3.6)


def test_empty_system(metrics: FontMetrics) -> None:
    display = layout(SystemSpec(staves=()), metrics)
    assert display.items == ()
    assert display.staves == ()


def test_staff_geometry_matches_heads(metrics: FontMetrics) -> None:
    spec = StaffSpec(clef=Clef.BASS, events=(note('C3'), note('C4'), note('E2')))
    display = layout(spec, metrics)
    (geometry,) = display.staves
    heads = glyphs(display, 'noteheadBlack')
    positions = [geometry.position_at(h.y) for h in heads]
    assert positions == [Clef.BASS.staff_position(Pitch.parse(p)) for p in ('C3', 'C4', 'E2')]


@pytest.mark.parametrize(
    ('clef', 'glyph', 'position'),
    [
        (Clef.TREBLE, 'gClef', 2),
        (Clef.TREBLE_8VB, 'gClef8vb', 2),
        (Clef.BASS, 'fClef', 6),
        (Clef.ALTO, 'cClef', 4),
        (Clef.TENOR, 'cClef', 6),
        (Clef.PERCUSSION, 'unpitchedPercussionClef1', 4),
    ],
)
def test_clefs(metrics: FontMetrics, clef: Clef, glyph: str, position: int) -> None:
    display = layout(StaffSpec(clef=clef), metrics)
    (item,) = glyphs(display, glyph)
    assert display.staves[0].position_at(item.y) == position


@pytest.mark.parametrize(
    ('clef', 'fifths', 'positions'),
    [
        (Clef.TREBLE, 4, [8, 5, 9, 6]),
        (Clef.TREBLE, -3, [4, 7, 3]),
        (Clef.BASS, 2, [6, 3]),
        (Clef.ALTO, -2, [3, 6]),
        (Clef.TENOR, 3, [2, 6, 3]),
    ],
)
def test_key_signature_positions(
    metrics: FontMetrics, clef: Clef, fifths: int, positions: list[int]
) -> None:
    display = layout(StaffSpec(clef=clef, key_signature=KeySignature(fifths)), metrics)
    glyph = 'accidentalSharp' if fifths > 0 else 'accidentalFlat'
    items = glyphs(display, glyph)
    assert [display.staves[0].position_at(i.y) for i in items] == positions
    assert [i.x for i in items] == sorted(i.x for i in items)


def test_no_key_signature_on_percussion(metrics: FontMetrics) -> None:
    display = layout(StaffSpec(clef=Clef.PERCUSSION, key_signature=KeySignature(3)), metrics)
    assert not glyphs(display, 'accidentalSharp')


def test_time_signature_digits(metrics: FontMetrics) -> None:
    display = layout(StaffSpec(meter=Meter(12, 8)), metrics)
    assert [g.glyph for g in display.items if isinstance(g, GlyphItem)][1:] == [
        'timeSig1',
        'timeSig2',
        'timeSig8',
    ]


@pytest.mark.parametrize(
    ('duration', 'glyph'),
    [
        (None, 'noteheadBlack'),
        (Q, 'noteheadBlack'),
        (H, 'noteheadHalf'),
        (W, 'noteheadWhole'),
        (Duration(NoteValue.BREVE), 'noteheadDoubleWhole'),
    ],
)
def test_noteheads(metrics: FontMetrics, duration: Duration | None, glyph: str) -> None:
    display = layout(StaffSpec(events=(note('C5', d=duration),)), metrics)
    assert len(glyphs(display, glyph)) == 1
    has_stem = duration is not None and duration.value.value <= NoteValue.HALF.value
    assert len(stems(display, metrics)) == int(has_stem)


@pytest.mark.parametrize(
    ('pitches', 'up'),
    [
        (['A4'], True),
        (['B4'], False),  # middle line: down
        (['C5'], False),
        (['C4', 'C5'], True),  # farthest note decides
        (['G4', 'D5'], False),  # equal distance: down
        (['A3', 'B4', 'F5'], True),
    ],
)
def test_stem_direction(metrics: FontMetrics, pitches: list[str], up: bool) -> None:
    display = layout(StaffSpec(events=(note(*pitches, d=Q),)), metrics)
    (stem,) = stems(display, metrics)
    assert (stem.y2 < stem.y1) == up


def test_stems_reach_the_middle_line(metrics: FontMetrics) -> None:
    display = layout(StaffSpec(events=(note('A3', d=Q), note('E6', d=Q))), metrics)
    middle = display.staves[0].y_of(4)
    low, high = stems(display, metrics)
    assert low.y2 <= middle + 1e-9
    assert high.y2 >= middle - 1e-9


def test_seconds_are_displaced(metrics: FontMetrics) -> None:
    display = layout(StaffSpec(events=(note('C4', 'D4', 'E4', d=Q),)), metrics)
    heads = sorted(glyphs(display, 'noteheadBlack'), key=lambda g: -g.y)  # bottom up
    (stem,) = stems(display, metrics)
    assert heads[0].x == heads[2].x  # C4 and E4 on the normal side (left of the stem)
    assert heads[1].x > stem.x1 - 0.1  # D4 to the right of the stem
    down = layout(StaffSpec(events=(note('B4', 'C5', d=Q),)), metrics)
    b4, c5 = sorted(glyphs(down, 'noteheadBlack'), key=lambda g: -g.y)
    assert b4.x < c5.x  # stem down: the lower note moves left


def test_flags_and_beams(metrics: FontMetrics) -> None:
    single = layout(StaffSpec(events=(note('G4', d=S),)), metrics)
    assert len(glyphs(single, 'flag16thUp')) == 1
    beamed = layout(StaffSpec(meter=Meter(2, 4), events=(note('G4', d=S),) * 4), metrics)
    assert not [g for g in beamed.items if isinstance(g, GlyphItem) and 'flag' in g.glyph]
    assert len([i for i in beamed.items if isinstance(i, BeamItem)]) == 2
    # Stems end on the beam.
    beam = next(i for i in beamed.items if isinstance(i, BeamItem))
    for stem in stems(beamed, metrics):
        assert beam.x1 - 1e-9 <= stem.x1 <= beam.x2 + 1e-9


def test_dotted_rhythm_has_a_stub(metrics: FontMetrics) -> None:
    events = (note('G4', d=Duration(NoteValue.EIGHTH, 1)), note('A4', d=S))
    display = layout(StaffSpec(meter=Meter(2, 4), events=events), metrics)
    beams = [i for i in display.items if isinstance(i, BeamItem)]
    assert len(beams) == 2
    stub = min(beams, key=lambda b: b.x2 - b.x1)
    assert stub.x2 - stub.x1 < beams[0].x2 - beams[0].x1
    assert len(glyphs(display, 'augmentationDot')) == 1


def test_tuplets(metrics: FontMetrics) -> None:
    triplet = Duration(NoteValue.EIGHTH, tuplet=Tuplet(3, 2))
    beamed = layout(StaffSpec(events=(note('C5', d=triplet),) * 3), metrics)
    assert len(glyphs(beamed, 'tuplet3')) == 1
    unbeamed = StaffSpec(
        events=(note('C5', d=Duration(NoteValue.QUARTER, tuplet=Tuplet(3, 2))),) * 3
    )
    display = layout(unbeamed, metrics)
    thickness = metrics.engraving_default('tupletBracketThickness')
    brackets = [i for i in display.items if isinstance(i, LineItem) and i.thickness == thickness]
    assert len(brackets) == 4


def test_ties(metrics: FontMetrics) -> None:
    events = (note('C4', 'E4', d=H, tie_to_next=True), Barline(), note('C4', 'G4', d=H))
    display = layout(StaffSpec(events=events), metrics)
    (tie,) = [i for i in display.items if isinstance(i, CurveItem)]
    assert tie.x2 > tie.x1
    assert tie.bulge > 0  # stems up: ties curve downwards
    # A tie into a rest draws nothing.
    rest = (note('C4', d=Q, tie_to_next=True), Rest(Q))
    items = layout(StaffSpec(events=rest), metrics).items
    assert not [i for i in items if isinstance(i, CurveItem)]


def test_rests(metrics: FontMetrics) -> None:
    events = (Rest(Duration(NoteValue.HALF, 1)), Rest(Q), Barline(), Rest(W), Barline())
    display = layout(StaffSpec(meter=Meter(4, 4), events=events), metrics)
    assert len(glyphs(display, 'restHalf')) == 1
    assert len(glyphs(display, 'restQuarter')) == 1
    assert len(glyphs(display, 'augmentationDot')) == 1
    (whole,) = glyphs(display, 'restWhole')
    bar1, bar2 = (i.x1 for i in display.items if isinstance(i, LineItem) and i.x1 == i.x2)
    centre = whole.x + metrics.glyph('restWhole').width / 2
    assert centre == pytest.approx((bar1 + bar2) / 2, abs=0.2)
    assert display.staves[0].position_at(whole.y) == 6


def test_whole_bar_rest_in_three_four(metrics: FontMetrics) -> None:
    events = (Rest(Duration(NoteValue.HALF, 1)), Barline())
    display = layout(StaffSpec(meter=Meter(3, 4), events=events), metrics)
    assert len(glyphs(display, 'restWhole')) == 1
    assert not glyphs(display, 'augmentationDot')


@pytest.mark.parametrize(
    ('style', 'lines', 'dots'),
    [
        (BarStyle.SINGLE, 1, 0),
        (BarStyle.DOUBLE, 2, 0),
        (BarStyle.FINAL, 2, 0),
        (BarStyle.REPEAT_START, 2, 2),
        (BarStyle.REPEAT_END, 2, 2),
    ],
)
def test_barlines(metrics: FontMetrics, style: BarStyle, lines: int, dots: int) -> None:
    display = layout(StaffSpec(events=(note('C5', d=Q), Barline(style))), metrics)
    vertical = [i for i in display.items if isinstance(i, LineItem) and i.x1 == i.x2]
    assert len(vertical) == lines + 1  # plus the stem
    assert len(glyphs(display, 'repeatDot')) == dots


def test_labels_halo_and_ink(metrics: FontMetrics) -> None:
    events = (
        Chord((Head(Pitch.parse('D4')),), label='1'),
        Chord((Head(Pitch.parse('G4'), ink=Ink.ERROR, halo=True),), label='4', ink=Ink.ACCENT),
    )
    display = layout(StaffSpec(events=events), metrics)
    assert isinstance(display.items[0], CircleItem)  # halos are drawn first
    labels = [i for i in display.items if isinstance(i, TextItem)]
    assert [(t.text, t.ink, t.bold) for t in labels] == [
        ('1', Ink.DIM, False),
        ('4', Ink.ACCENT, True),
    ]
    assert labels[0].y == labels[1].y
    assert labels[0].y > display.staves[0].y_of(0) + 2
    assert labels[1].x == pytest.approx(display.event_x[0][1])
    error_heads = [g for g in glyphs(display, 'noteheadBlack') if g.ink is Ink.ERROR]
    assert len(error_heads) == 1


def test_bracket_with_label(metrics: FontMetrics) -> None:
    spec = StaffSpec(events=(note('G4', d=Q), note('E5', d=Q)), brackets=(Bracket(0, 1, '?'),))
    display = layout(spec, metrics)
    (label,) = [i for i in display.items if isinstance(i, TextItem)]
    assert label.text == '?'
    assert label.ink is Ink.ACCENT
    assert label.x > max(display.event_x[0])
    geometry = display.staves[0]
    accent = [i for i in display.items if isinstance(i, LineItem) and i.ink is Ink.ACCENT]
    vertical = next(i for i in accent if i.x1 == i.x2)
    assert vertical.y1 < geometry.y_of(7)  # above E5
    assert vertical.y2 > geometry.y_of(2)  # below G4


def test_system_aligns_by_onset(metrics: FontMetrics) -> None:
    upper = StaffSpec(events=(note('C5', d=H), note('D5', d=H)))
    lower = StaffSpec(clef=Clef.BASS, events=(note('C3', d=Q),) * 4)
    display = layout(SystemSpec((upper, lower), labels=('R', 'L')), metrics)
    up, low = display.event_x
    assert up[0] == pytest.approx(low[0])
    assert up[1] == pytest.approx(low[2])
    assert len(glyphs(display, 'brace')) == 1
    assert display.staves[1].top > display.staves[0].top + 4
    texts = sorted(i.text for i in display.items if isinstance(i, TextItem))
    assert texts == ['L', 'R']


def test_braced_barlines_connect(metrics: FontMetrics) -> None:
    staff = StaffSpec(events=(note('C5', d=Q), Barline()))
    braced = layout(SystemSpec((staff, staff)), metrics)
    plain = layout(SystemSpec((staff, staff), brace=False), metrics)
    thin = metrics.engraving_default('thinBarlineThickness')

    def barlines(display: DisplayList) -> int:
        return len([i for i in display.items if isinstance(i, LineItem) and i.thickness == thin])

    assert barlines(braced) == barlines(plain) + 1
    assert not glyphs(plain, 'brace')


def test_voices_share_a_staff(metrics: FontMetrics) -> None:
    spec = StaffSpec(events=(note('E5', d=Q),), voices=((note('D5', d=Q), Rest(Q)),))
    display = layout(spec, metrics)
    directions = {stem.y2 < stem.y1 for stem in stems(display, metrics)}
    assert directions == {True, False}
    assert len(display.event_x[0]) == 3
    regions = {(r.event, r.head) for r in display.hit_regions}
    assert {(0, 0), (1, 0), (0, None), (1, None), (2, None)} <= regions
    # The second apart between the voices pushes the lower voice to the right.
    e5, d5 = sorted(glyphs(display, 'noteheadBlack'), key=lambda g: g.y)
    assert d5.x > e5.x


def test_width_stretches_and_compresses(metrics: FontMetrics) -> None:
    spec = StaffSpec(events=tuple(note(p, d=Q) for p in ('C5', 'D5', 'E5', 'F5')))
    natural = layout(spec, metrics)
    wide = layout(spec, metrics, width=natural.width + 20)
    assert wide.width == pytest.approx(natural.width + 20)
    gaps = [b - a for a, b in itertools.pairwise(wide.event_x[0])]
    assert max(gaps) - min(gaps) < 1e-6  # equal durations stay evenly spaced
    narrow = layout(spec, metrics, width=natural.width - 3)
    assert narrow.width == pytest.approx(natural.width - 3)
    tiny = layout(spec, metrics, width=1)
    assert tiny.width < narrow.width
    xs = tiny.event_x[0]
    head = metrics.glyph('noteheadBlack').width
    assert all(b - a > head for a, b in itertools.pairwise(xs))


def test_hit_test_finds_heads(metrics: FontMetrics) -> None:
    display = layout(StaffSpec(events=(note('C4', 'G4', d=Q),)), metrics)
    for item in glyphs(display, 'noteheadBlack'):
        region = display.hit_test(item.x + 0.5, item.y)
        assert region is not None
        assert region.head is not None


# --- Properties -------------------------------------------------------------------------


@st.composite
def pitches(draw: st.DrawFn) -> Pitch:
    return Pitch(Letter(draw(st.integers(0, 6))), draw(st.integers(-2, 2)), draw(st.integers(2, 6)))


durations = st.sampled_from(
    [
        None,
        W,
        H,
        Q,
        E,
        S,
        Duration(NoteValue.THIRTY_SECOND),
        Duration(NoteValue.QUARTER, 1),
        Duration(NoteValue.EIGHTH, tuplet=Tuplet(3, 2)),
    ]
)


@st.composite
def events(draw: st.DrawFn) -> Event:
    kind = draw(st.sampled_from(['chord', 'chord', 'chord', 'rest', 'bar']))
    if kind == 'bar':
        return Barline(draw(st.sampled_from(list(BarStyle))))
    duration = draw(durations)
    if kind == 'rest':
        return Rest(duration or Q)
    heads = draw(st.lists(pitches(), min_size=1, max_size=4))
    return Chord(
        tuple(Head(p, halo=draw(st.booleans())) for p in heads),
        duration,
        label=draw(st.sampled_from([None, '1', 'V7'])),
        tie_to_next=draw(st.booleans()),
    )


@st.composite
def staves(draw: st.DrawFn) -> StaffSpec:
    staff_events = tuple(draw(st.lists(events(), max_size=10)))
    brackets = ()
    if len(staff_events) >= 2 and draw(st.booleans()):
        brackets = (Bracket(0, len(staff_events) - 1, '?'),)
    key = draw(st.none() | st.integers(-7, 7).map(KeySignature))
    meter = draw(st.none() | st.sampled_from([Meter(4, 4), Meter(6, 8), Meter(7, 8), Meter(3, 4)]))
    return StaffSpec(
        clef=draw(st.sampled_from(list(Clef))),
        key_signature=key,
        meter=meter,
        events=staff_events,
        brackets=brackets,
        lines=draw(st.sampled_from([5, 5, 5, 1])),
    )


figures = staves() | st.builds(
    lambda staffs, brace: SystemSpec(tuple(staffs), brace=brace, labels=('A', 'B')),
    st.lists(staves(), min_size=2, max_size=3),
    st.booleans(),
)

PROPERTY_SETTINGS = settings(
    max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)


def all_events(staff: StaffSpec) -> tuple[Event, ...]:
    return (*staff.events, *(e for voice in staff.voices for e in voice))


@PROPERTY_SETTINGS
@given(figures, st.none() | st.floats(5, 80))
def test_every_head_and_event_has_a_hit_region(
    metrics: FontMetrics, figure: StaffSpec | SystemSpec, width: float | None
) -> None:
    display = layout(figure, metrics, width=width)
    regions = {(r.staff, r.event, r.head) for r in display.hit_regions}
    staffs = figure.staves if isinstance(figure, SystemSpec) else (figure,)
    for s, staff in enumerate(staffs):
        assert len(display.event_x[s]) == len(all_events(staff))
        for e, event in enumerate(all_events(staff)):
            if isinstance(event, Chord) and not event.heads:
                continue
            assert (s, e, None) in regions
            if isinstance(event, Chord):
                for h in range(len(event.heads)):
                    assert (s, e, h) in regions


@PROPERTY_SETTINGS
@given(figures, st.none() | st.floats(5, 80))
def test_items_stay_within_bounds(
    metrics: FontMetrics, figure: StaffSpec | SystemSpec, width: float | None
) -> None:
    display = layout(figure, metrics, width=width)
    for item in display.items:
        x0, y0, x1, y1 = item_bounds(item, metrics)
        assert x0 >= -1e-6, item
        assert y0 >= -1e-6, item
        assert x1 <= display.width + 1e-6, item
        assert y1 <= display.height + 1e-6, item
    if width is not None:
        assert display.width >= width - 1e-6


@PROPERTY_SETTINGS
@given(staves())
def test_events_run_left_to_right(metrics: FontMetrics, staff: StaffSpec) -> None:
    display = layout(staff, metrics)
    xs = display.event_x[0]
    assert all(b >= a - 1e-9 for a, b in itertools.pairwise(xs))


# Tuplet brackets share the ledger lines' thickness, so leave tuplets out here.
plain_durations = durations.filter(lambda d: d is None or d.tuplet is None)


@settings(max_examples=150, deadline=None)
@given(st.lists(pitches(), min_size=1, max_size=4), st.sampled_from(list(Clef)), plain_durations)
def test_ledger_lines_exactly_when_needed(
    metrics: FontMetrics, chord_pitches: list[Pitch], clef: Clef, duration: Duration | None
) -> None:
    spec = StaffSpec(clef=clef, events=(Chord(tuple(Head(p) for p in chord_pitches), duration),))
    display = layout(spec, metrics)
    geometry = display.staves[0]
    expected: set[float] = set()
    for pitch in chord_pitches:
        position = clef.staff_position(pitch)
        expected.update(round(geometry.y_of(p), 6) for p in range(-2, position - 1, -2))
        expected.update(round(geometry.y_of(p), 6) for p in range(10, position + 1, 2))
    assert ledger_ys(display, metrics) == sorted(expected)


def test_wide_labels_stack_instead_of_overlapping(metrics) -> None:
    """Labels wider than their columns move down a row; narrow ones stay on the first."""
    events = tuple(
        Chord((Head(Pitch.parse(p)),), label=label)
        for p, label in (('C4', 'spacing ∥8'), ('D4', 'range'), ('E4', 'I'), ('F4', 'IV'))
    )
    display = layout(StaffSpec(events=events), metrics)
    labels = [i for i in display.items if isinstance(i, TextItem)]
    boxes = [item_bounds(i, metrics) for i in labels]
    for i, (x0, y0, x1, y1) in enumerate(boxes):
        for a0, b0, a1, b1 in boxes[i + 1 :]:
            assert x1 <= a0 or a1 <= x0 or y1 <= b0 or b1 <= y0
    baselines = {i.text: i.y for i in labels}
    assert baselines['range'] > baselines['spacing ∥8'], 'moved down a row'
    assert baselines['I'] == baselines['IV'] == baselines['spacing ∥8']
