# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Golden tests: display lists compared with JSON files in ``golden/``.

After an intentional change to the engraving, regenerate the files with::

    ETUDE_UPDATE_GOLDEN=1 pytest tests/notation/test_golden.py

and review the diff (and the gallery, ``tools/notation_gallery.py``)
before committing.
"""

from __future__ import annotations

import dataclasses
import json
import os
from enum import Enum
from pathlib import Path
from typing import Any

import pytest

from etude.core import Duration, KeySignature, Meter, NoteValue, Pitch, Tuplet
from etude.notation.displaylist import DisplayList
from etude.notation.layout import layout
from etude.notation.smufl import FontMetrics
from etude.notation.spec import (
    AccidentalDisplay,
    Barline,
    BarStyle,
    Bracket,
    Chord,
    Clef,
    Event,
    Figure,
    GlyphFigure,
    Head,
    Ink,
    Rest,
    StaffSpec,
    SystemSpec,
)

GOLDEN = Path(__file__).parent / 'golden'
UPDATE = os.environ.get('ETUDE_UPDATE_GOLDEN') == '1'

W = Duration(NoteValue.WHOLE)
H = Duration(NoteValue.HALF)
Q = Duration(NoteValue.QUARTER)
E = Duration(NoteValue.EIGHTH)
S = Duration(NoteValue.SIXTEENTH)
DESIGN_WIDTH = 500 / (40 / 3.5)
"""The design's 500 px staves, in staff spaces (stems are 40 px)."""


def note(*pitches: str, d: Duration | None = None, **kwargs: Any) -> Chord:
    return Chord(tuple(Head(Pitch.parse(p)) for p in pitches), d, **kwargs)


def run(pitches: str, d: Duration | None = None) -> tuple[Event, ...]:
    return tuple(note(p, d=d) for p in pitches.split())


def _scale() -> StaffSpec:
    events = tuple(
        Chord(
            (Head(Pitch.parse(p), halo=i == 3),),
            label=str(i + 1),
            ink=Ink.ACCENT if i == 3 else Ink.FOREGROUND,
        )
        for i, p in enumerate(['D4', 'E4', 'F#4', 'G4', 'A4', 'B4', 'C#5', 'D5'])
    )
    return StaffSpec(events=events)


FIGURES: dict[str, tuple[Figure, float | None]] = {
    'fig-key-sig': (StaffSpec(key_signature=KeySignature(4)), DESIGN_WIDTH),
    'fig-note': (StaffSpec(events=(note('F4', d=Q),)), DESIGN_WIDTH),
    'fig-interval': (
        StaffSpec(events=(note('G4', d=Q), note('E5', d=Q)), brackets=(Bracket(0, 1, '?'),)),
        DESIGN_WIDTH,
    ),
    'fig-chord': (StaffSpec(events=(note('E4', 'G4', 'B4'),)), DESIGN_WIDTH),
    'fig-scale': (_scale(), DESIGN_WIDTH),
    'beams-4-4': (
        StaffSpec(
            meter=Meter(4, 4),
            events=(
                *run('C4 E4 G4 C5', E),
                note('G4', d=Duration(NoteValue.EIGHTH, 1)),
                note('A4', d=S),
                *run('B4 C5 D5 E5', S),
                Barline(BarStyle.FINAL),
            ),
        ),
        None,
    ),
    'beams-6-8': (
        StaffSpec(
            meter=Meter(6, 8),
            key_signature=KeySignature(-2),
            events=(*run('B4 C5 D5 E5 F5 G5', E), Barline(), note('F5', d=Q), note('D5', d=E)),
        ),
        None,
    ),
    'tuplets': (
        StaffSpec(
            meter=Meter(2, 4),
            events=(
                *run('C5 D5 E5', Duration(NoteValue.EIGHTH, tuplet=Tuplet(3, 2))),
                *run('G4 A4 B4', Duration(NoteValue.QUARTER, tuplet=Tuplet(3, 2))),
            ),
        ),
        None,
    ),
    'chords': (
        StaffSpec(
            events=(
                note('C4', 'D4', d=Q),
                note('B4', 'C5', 'E5', d=Q),
                note('F4', 'G4', d=W),
                note('C#4', 'E4', 'G#4', 'B4', d=H),
                note('C4', 'E4', d=Duration(NoteValue.HALF, 1), tie_to_next=True),
                note('C4', 'E4', d=Q),
            ),
        ),
        None,
    ),
    'rests': (
        StaffSpec(
            meter=Meter(4, 4),
            events=(
                Rest(W),
                Barline(BarStyle.REPEAT_START),
                Rest(H),
                Rest(Duration(NoteValue.QUARTER, 1)),
                Rest(E),
                Barline(BarStyle.REPEAT_END),
                Rest(W),
                Barline(BarStyle.DOUBLE),
            ),
        ),
        30.0,
    ),
    'clefs': (
        SystemSpec(
            staves=tuple(
                StaffSpec(clef=clef, key_signature=KeySignature(-3), events=(note('C4', d=Q),))
                for clef in Clef
            ),
            brace=False,
            labels=tuple(clef.value for clef in Clef),
        ),
        None,
    ),
    'single-line': (
        StaffSpec(
            clef=Clef.PERCUSSION,
            lines=1,
            meter=Meter(2, 4),
            events=(*run('E4 E4', E), note('E4', d=Q), Barline(), Rest(H)),
        ),
        None,
    ),
    'grand-staff-satb': (
        SystemSpec(
            staves=(
                StaffSpec(
                    key_signature=KeySignature(1),
                    meter=Meter(2, 4),
                    events=(note('B4', d=Q), note('A4', d=Q), Barline(BarStyle.FINAL)),
                    voices=(
                        (
                            note('G4', d=Q),
                            Chord(
                                (Head(Pitch.parse('F#4'), accidental=AccidentalDisplay.ALWAYS),),
                                Q,
                            ),
                            Barline(BarStyle.FINAL),
                        ),
                    ),
                ),
                StaffSpec(
                    clef=Clef.BASS,
                    key_signature=KeySignature(1),
                    meter=Meter(2, 4),
                    events=(note('D4', d=Q), note('D4', d=Q), Barline(BarStyle.FINAL)),
                    voices=((note('G3', d=Q), note('D3', d=Q), Barline(BarStyle.FINAL)),),
                ),
            ),
            labels=('S A', 'T B'),
        ),
        None,
    ),
    'glyphs-dynamics': (
        GlyphFigure(('dynamicMF', 'dynamicCrescendoHairpin', 'dynamicFF'), 'Dynamics.'),
        None,
    ),
    'glyphs-articulations': (
        GlyphFigure(
            ('noteQuarterDown', 'articStaccatoAbove', 'noteQuarterUp', 'fermataBelow'),
            'Articulations.',
            staff=True,
        ),
        None,
    ),
}


def _number(value: float) -> float:
    rounded = round(value, 3)
    return 0.0 if rounded == 0 else rounded


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float):
        return _number(value)
    if isinstance(value, tuple | list):
        return [_plain(v) for v in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields = {f.name: _plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
        return {'type': type(value).__name__, **fields}
    return value


def serialise(display: DisplayList) -> dict[str, Any]:
    """A stable, diff-friendly form of a display list (floats rounded to 0.001)."""
    result = _plain(display)
    assert isinstance(result, dict)
    return result


@pytest.mark.parametrize('name', sorted(FIGURES))
def test_golden(name: str, metrics: FontMetrics) -> None:
    figure, width = FIGURES[name]
    actual = serialise(layout(figure, metrics, width=width))
    path = GOLDEN / f'{name}.json'
    if UPDATE:
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(json.dumps(actual, indent=1, ensure_ascii=False) + '\n')
    assert path.exists(), f'missing {path.name}; run with ETUDE_UPDATE_GOLDEN=1'
    expected = json.loads(path.read_text())
    assert actual == expected, f'{name} changed; run with ETUDE_UPDATE_GOLDEN=1 and review'


def test_layout_is_deterministic(metrics: FontMetrics) -> None:
    for figure, width in FIGURES.values():
        assert layout(figure, metrics, width=width) == layout(figure, metrics, width=width)
