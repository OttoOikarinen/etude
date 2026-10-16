# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from etude.core import Duration, KeySignature, NoteValue, Pitch
from etude.notation._accidentals import AccidentalMemory, Box, stack
from etude.notation.displaylist import GlyphItem
from etude.notation.layout import layout
from etude.notation.smufl import FontMetrics
from etude.notation.spec import AccidentalDisplay, Barline, Chord, Head, StaffSpec

Q = Duration(NoteValue.QUARTER)


def head(text: str, display: AccidentalDisplay = AccidentalDisplay.AUTO) -> Head:
    return Head(Pitch.parse(text), accidental=display)


def shown(memory: AccidentalMemory, *pitches: str) -> list[int | None]:
    return [memory.decide([head(p)])[0] for p in pitches]


def test_auto_without_key() -> None:
    memory = AccidentalMemory(None)
    assert shown(memory, 'C4', 'F#4', 'F#4', 'F4', 'Bb4', 'Bb4') == [None, 1, None, 0, -1, None]


def test_key_signature_is_respected() -> None:
    memory = AccidentalMemory(KeySignature(4))  # F♯ C♯ G♯ D♯
    assert shown(memory, 'F#4', 'C#5', 'G4', 'A4', 'D4', 'D#4') == [None, None, 0, None, 0, 1]


def test_memory_is_per_octave_and_resets_at_barlines() -> None:
    memory = AccidentalMemory(None)
    assert shown(memory, 'F#4', 'F#5') == [1, 1]
    memory.reset()
    assert shown(memory, 'F#4', 'F4') == [1, 0]


def test_always_and_never() -> None:
    memory = AccidentalMemory(KeySignature(1))
    assert memory.decide([head('F#4', AccidentalDisplay.ALWAYS)]) == [1]
    assert memory.decide([head('C4', AccidentalDisplay.ALWAYS)]) == [0]  # courtesy natural
    assert memory.decide([head('Bb4', AccidentalDisplay.NEVER)]) == [None]
    # A hidden accidental does not change what the reader assumes.
    assert memory.in_force(head('B4')) == 0


def test_chord_clash_shows_both() -> None:
    memory = AccidentalMemory(None)
    assert memory.decide([head('F4'), head('F#4')]) == [0, 1]


def test_tied_continuation_has_no_accidental() -> None:
    memory = AccidentalMemory(None)
    memory.decide([head('G#4')])
    memory.reset()
    assert memory.decide([head('G#4')], [True]) == [None]
    # The next G♯ in the new bar repeats the accidental.
    assert memory.decide([head('G#4')]) == [1]


def test_stack_single_column_when_far_apart() -> None:
    boxes = [Box(0.0, 2.8, 1.0), Box(3.0, 5.8, 1.0)]
    assert stack(boxes) == [0.0, 0.0]


def test_stack_moves_close_accidentals_left() -> None:
    boxes = [Box(0.0, 2.8, 1.0), Box(1.5, 4.3, 1.0), Box(3.2, 6.0, 1.0)]
    rights = stack(boxes)
    # Zig-zag: the top and bottom accidentals stay closest to the chord.
    assert rights[0] == 0.0
    assert rights[2] == 0.0
    assert rights[1] < -1.0
    # No two placed accidentals overlap.
    placed = sorted((r - b.width, r, b.top, b.bottom) for r, b in zip(rights, boxes, strict=True))
    for a in placed:
        for b in placed:
            if a is b:
                continue
            vertical = min(a[3], b[3]) - max(a[2], b[2])
            horizontal = min(a[1], b[1]) - max(a[0], b[0])
            assert vertical <= 0.3 or horizontal <= 0


def test_a_sixth_shares_a_column(metrics: FontMetrics) -> None:
    sharp = metrics.glyph('accidentalSharp')
    height = sharp.height
    boxes = [Box(0.0, height, sharp.width), Box(2.5, 2.5 + height, sharp.width)]
    assert stack(boxes) == [0.0, 0.0]


def accidentals(spec: StaffSpec, metrics: FontMetrics) -> list[str]:
    display = layout(spec, metrics)
    return [
        item.glyph
        for item in display.items
        if isinstance(item, GlyphItem) and item.glyph.startswith('accidental')
    ]


@pytest.mark.parametrize(
    ('key', 'pitches', 'expected'),
    [
        (None, ['C#4', 'C#4', 'C4'], ['accidentalSharp', 'accidentalNatural']),
        (KeySignature(2), ['F#4', 'C5', 'Fx4'], ['accidentalNatural', 'accidentalDoubleSharp']),
        (KeySignature(-1), ['Bb4', 'Ebb5'], ['accidentalDoubleFlat']),
    ],
)
def test_layout_applies_accidental_logic(
    metrics: FontMetrics, key: KeySignature | None, pitches: list[str], expected: list[str]
) -> None:
    events = tuple(Chord((head(p),), Q) for p in pitches)
    found = accidentals(StaffSpec(key_signature=key, events=events), metrics)
    signature = key.count if key else 0
    assert found[signature:] == expected


def test_layout_resets_memory_at_barlines(metrics: FontMetrics) -> None:
    events = (Chord((head('F#4'),), Q), Barline(), Chord((head('F#4'),), Q))
    assert accidentals(StaffSpec(events=events), metrics) == ['accidentalSharp'] * 2


def test_layout_stacks_chord_accidentals(metrics: FontMetrics) -> None:
    chord = Chord(tuple(head(p) for p in ('C#4', 'E#4', 'G#4')), Q)
    display = layout(StaffSpec(events=(chord,)), metrics)
    xs = [
        item.x
        for item in display.items
        if isinstance(item, GlyphItem) and item.glyph == 'accidentalSharp'
    ]
    assert len(xs) == 3
    assert len(set(xs)) >= 2  # thirds apart cannot share one column
    heads = [i.x for i in display.items if isinstance(i, GlyphItem) and i.glyph == 'noteheadBlack']
    width = metrics.glyph('accidentalSharp').width
    assert max(xs) + width < min(heads)
