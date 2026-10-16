#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Render notation figures to PNG files for visual review.

Renders the design's figures (figKeySig, figNote, figInterval, figChord,
figScale) at the design's size and a stress sheet that exercises beams,
tuplets, chords, clefs, key signatures, a grand staff and rests. Run it
inside the GNOME SDK, for example::

    flatpak run --filesystem=<parent of the checkout> --socket=wayland \\
        --socket=fallback-x11 --share=ipc --command=python3 org.gnome.Sdk//51 \\
        tools/notation_gallery.py --output /tmp/etude-gallery

with ``PYTHONPATH`` pointing at the checkout's ``src`` directory.
``--check-glyphs`` compares the ink extents Pango draws for every code
point in ``smufl.CODEPOINTS`` with the bounding boxes in the metadata, which
catches wrong code points.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Gsk', '4.0')
gi.require_version('Graphene', '1.0')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')

from gi.repository import Gdk, Graphene, Gsk, Gtk, Pango, PangoCairo  # noqa: E402

from etude.core import Duration, KeySignature, Meter, NoteValue, Pitch, Tuplet  # noqa: E402
from etude.notation.layout import layout  # noqa: E402
from etude.notation.smufl import CODEPOINTS, FontMetrics  # noqa: E402
from etude.notation.spec import (  # noqa: E402
    AccidentalDisplay,
    Barline,
    BarStyle,
    Bracket,
    Chord,
    Clef,
    Event,
    Figure,
    Head,
    Ink,
    Rest,
    StaffSpec,
    SystemSpec,
)
from etude.notation.widget import Palette, Renderer, register_font  # noqa: E402

DESIGN_WIDTH = 500
DESIGN_STEM = 40
DESIGN_SPACE = DESIGN_STEM / 3.5

W = Duration(NoteValue.WHOLE)
H = Duration(NoteValue.HALF)
Q = Duration(NoteValue.QUARTER)
E = Duration(NoteValue.EIGHTH)
S = Duration(NoteValue.SIXTEENTH)
T = Duration(NoteValue.THIRTY_SECOND)


def note(*pitches: str, d: Duration | None = None, **kwargs: object) -> Chord:
    return Chord(tuple(Head(Pitch.parse(p)) for p in pitches), d, **kwargs)  # type: ignore[arg-type]


def run(pitches: str, d: Duration) -> tuple[Event, ...]:
    return tuple(note(p, d=d) for p in pitches.split())


def design_figures() -> dict[str, Figure]:
    scale = [
        Chord(
            (Head(Pitch.parse(p), halo=(i == 3)),),
            label=str(i + 1),
            ink=Ink.ACCENT if i == 3 else Ink.FOREGROUND,
        )
        for i, p in enumerate(['D4', 'E4', 'F#4', 'G4', 'A4', 'B4', 'C#5', 'D5'])
    ]
    return {
        'figKeySig': StaffSpec(key_signature=KeySignature(4)),
        'figNote': StaffSpec(events=(note('F4', d=Q),)),
        'figInterval': StaffSpec(
            events=(note('G4', d=Q), note('E5', d=Q)), brackets=(Bracket(0, 1, '?'),)
        ),
        'figChord': StaffSpec(events=(note('E4', 'G4', 'B4'),)),
        'figScale': StaffSpec(events=tuple(scale)),
    }


def stress_figures() -> dict[str, Figure]:
    bar = Barline()
    dotted_e = Duration(NoteValue.EIGHTH, 1)
    triplet_e = Duration(NoteValue.EIGHTH, tuplet=Tuplet(3, 2))
    triplet_q = Duration(NoteValue.QUARTER, tuplet=Tuplet(3, 2))
    quint_s = Duration(NoteValue.SIXTEENTH, tuplet=Tuplet(5, 4))
    figures: dict[str, Figure] = {
        'beams-4-4': StaffSpec(
            meter=Meter(4, 4),
            events=(
                *run('C4 E4 G4 C5', E),
                *run('A5 F5 D5 B4', E),
                bar,
                note('G4', d=dotted_e),
                note('A4', d=S),
                *run('B4 C5 D5 E5', S),
                *run('F5 E5', E),
                *run('C6 B5 A5 G5 F5 E5 D5 C5', T),
                Barline(BarStyle.FINAL),
            ),
        ),
        'beams-6-8': StaffSpec(
            meter=Meter(6, 8),
            key_signature=KeySignature(-2),
            events=(
                *run('B4 C5 D5', E),
                *run('E5 F5 G5', E),
                bar,
                note('F5', d=Q),
                note('D5', d=E),
                note('B4', d=Duration(NoteValue.QUARTER, 1)),
                bar,
                note('C4', d=E),
                Rest(E),
                note('E4', d=E),
                Rest(Duration(NoteValue.QUARTER, 1)),
                Barline(BarStyle.FINAL),
            ),
        ),
        'beams-7-8': StaffSpec(
            meter=Meter(7, 8),
            events=(
                *run('D5 E5 F5 G5 A5 G5 F5', E),
                bar,
                note('E5', d=Q),
                note('D5', d=Q),
                note('C5', d=Duration(NoteValue.QUARTER, 1)),
                Barline(BarStyle.FINAL),
            ),
        ),
        'tuplets': StaffSpec(
            meter=Meter(4, 4),
            events=(
                *run('C5 D5 E5', triplet_e),
                *run('F5 G5 A5', triplet_e),
                *run('G4 A4 B4', triplet_q),
                bar,
                *run('C5 D5 E5 F5 G5', quint_s),
                note('A5', d=Q),
                note('E4', d=triplet_q),
                Rest(triplet_q),
                note('G4', d=triplet_q),
                Barline(BarStyle.FINAL),
            ),
        ),
        'chords-seconds': StaffSpec(
            events=(
                note('C4', 'D4', d=Q),
                note('E4', 'F4', 'G4', d=Q),
                note('B4', 'C5', 'E5', d=Q),
                note('A5', 'B5', 'C6', d=H),
                note('F4', 'G4', d=W),
                note('G4', 'A4', 'B4', 'C5'),
                note('C#4', 'E4', 'G#4', 'B4', d=Q),
                note('Db4', 'Fb4', 'Ab4', 'Cb5', 'Eb5', d=H),
                note('F#4', 'G#4', 'A#4', d=Q),
                note('C4', 'G4', 'C5', 'E5', d=Duration(NoteValue.HALF, 1)),
            ),
        ),
        'accidentals': StaffSpec(
            meter=Meter(4, 4),
            key_signature=KeySignature(2),
            events=(
                note('F#4', d=Q),
                note('F4', d=Q),
                note('F4', d=Q),
                note('F5', d=Q),
                bar,
                note('F4', d=Q),
                Chord((Head(Pitch.parse('C#5'), accidental=AccidentalDisplay.ALWAYS),), Q),
                note('Bb4', d=Q),
                note('B4', d=Q),
                bar,
                note('Fx4', d=Q),
                note('Ebb5', d=Q),
                note('G#3', d=Q, tie_to_next=True),
                bar,
                note('G#3', d=H),
                note('A5', 'C6', d=H),
                Barline(BarStyle.FINAL),
            ),
        ),
        'ledger-lines': StaffSpec(
            events=(
                note('A3', d=Q),
                note('C4', d=Q),
                note('G3', 'B3', 'D4', d=H),
                note('A5', d=Q),
                note('E6', d=Q),
                note('C6', 'E6', 'G6', d=H),
                note('F3', d=E),
                note('B5', d=E),
            ),
        ),
        'rests': StaffSpec(
            meter=Meter(4, 4),
            events=(
                Rest(W),
                bar,
                Rest(H),
                Rest(Q),
                Rest(E),
                Rest(S),
                Rest(T),
                Rest(Duration(NoteValue.SIXTY_FOURTH)),
                Rest(Duration(NoteValue.SIXTY_FOURTH)),
                bar,
                Rest(Duration(NoteValue.HALF, 1)),
                Rest(Duration(NoteValue.EIGHTH, 1)),
                Rest(S),
                Barline(BarStyle.REPEAT_START),
                note('C5', d=W),
                Barline(BarStyle.REPEAT_END),
                Rest(W),
                Barline(BarStyle.DOUBLE),
            ),
        ),
        'rests-3-4': StaffSpec(
            meter=Meter(3, 4),
            clef=Clef.BASS,
            events=(Rest(Duration(NoteValue.HALF, 1)), bar, *run('C3 E3 G3', Q), bar),
        ),
        'clefs': SystemSpec(
            staves=tuple(
                StaffSpec(clef=clef, events=(note('C4', d=Q), note('G4', 'A4', d=H)))
                for clef in (Clef.TREBLE, Clef.TREBLE_8VB, Clef.ALTO, Clef.TENOR, Clef.BASS)
            ),
            brace=False,
            labels=('Treble', '8vb', 'Alto', 'Tenor', 'Bass'),
        ),
        'percussion': SystemSpec(
            staves=(
                StaffSpec(
                    clef=Clef.PERCUSSION,
                    meter=Meter(2, 4),
                    events=(*run('B4 B4 B4 B4', E), bar, note('B4', d=Q), Rest(Q), bar),
                ),
                StaffSpec(
                    clef=Clef.PERCUSSION,
                    lines=1,
                    meter=Meter(2, 4),
                    events=(*run('E4 E4', E), note('E4', d=Q), bar, Rest(H), bar),
                ),
            ),
            brace=False,
        ),
        'keys-7': SystemSpec(
            staves=(
                StaffSpec(key_signature=KeySignature(7), meter=Meter(3, 4)),
                StaffSpec(clef=Clef.BASS, key_signature=KeySignature(7), meter=Meter(3, 4)),
            ),
        ),
        'keys-7-flats': SystemSpec(
            staves=(
                StaffSpec(key_signature=KeySignature(-7), meter=Meter(12, 8)),
                StaffSpec(clef=Clef.BASS, key_signature=KeySignature(-7), meter=Meter(12, 8)),
            ),
        ),
        'keys-c-clefs': SystemSpec(
            staves=(
                StaffSpec(clef=Clef.ALTO, key_signature=KeySignature(7)),
                StaffSpec(clef=Clef.ALTO, key_signature=KeySignature(-7)),
                StaffSpec(clef=Clef.TENOR, key_signature=KeySignature(7)),
                StaffSpec(clef=Clef.TENOR, key_signature=KeySignature(-7)),
            ),
            brace=False,
        ),
        'satb': SystemSpec(
            staves=(
                StaffSpec(
                    key_signature=KeySignature(1),
                    meter=Meter(4, 4),
                    events=(
                        *run('B4 A4', Q),
                        note('G4', d=H),
                        bar,
                        note('A4', d=Q),
                        note('B4', d=E),
                        note('C5', d=E),
                        note('D5', d=H),
                        Barline(BarStyle.FINAL),
                    ),
                    voices=(
                        (
                            note('G4', d=Q),
                            note('F#4', d=Q),
                            note('D4', d=H),
                            bar,
                            note('E4', d=Q),
                            note('G4', d=Q),
                            note('F#4', d=H),
                            Barline(BarStyle.FINAL),
                        ),
                    ),
                ),
                StaffSpec(
                    clef=Clef.BASS,
                    key_signature=KeySignature(1),
                    meter=Meter(4, 4),
                    events=(
                        *run('D4 D4', Q),
                        note('B3', d=H),
                        bar,
                        note('C4', d=Q),
                        note('D4', d=Q),
                        note('A3', d=H),
                        Barline(BarStyle.FINAL),
                    ),
                    voices=(
                        (
                            note('G3', d=Q),
                            note('D3', d=Q),
                            note('G2', d=H),
                            bar,
                            note('C3', d=Q),
                            note('B2', d=Q),
                            note('D3', d=H),
                            Barline(BarStyle.FINAL),
                        ),
                    ),
                ),
            ),
            labels=('S A', 'T B'),
        ),
        'grand-staff': SystemSpec(
            staves=(
                StaffSpec(
                    meter=Meter(3, 4),
                    events=(
                        note('E5', 'G5', d=H),
                        note('C5', d=Q),
                        bar,
                        note('D5', d=Duration(NoteValue.HALF, 1)),
                        bar,
                    ),
                ),
                StaffSpec(
                    clef=Clef.BASS,
                    meter=Meter(3, 4),
                    events=(
                        *run('C3 G3 E3', Q),
                        bar,
                        note('G2', 'D3', 'B3', d=Duration(NoteValue.HALF, 1)),
                        bar,
                    ),
                ),
            ),
        ),
    }
    return figures


def check_glyphs(context: Pango.Context, metrics: FontMetrics) -> int:
    """Compare drawn ink extents with the metadata bounding boxes (in staff spaces)."""
    size = 400.0  # pixels per em, so 100 px per staff space
    failures = 0
    for name in sorted(CODEPOINTS):
        info = metrics.glyph(name)
        text_layout = Pango.Layout.new(context)
        description = Pango.FontDescription.from_string('Bravura')
        description.set_absolute_size(size * Pango.SCALE)
        text_layout.set_font_description(description)
        text_layout.set_text(info.codepoint, -1)
        ink, _logical = text_layout.get_extents()
        baseline = text_layout.get_baseline()
        space = size / 4 * Pango.SCALE
        drawn = (
            ink.x / space,
            (baseline - ink.y - ink.height) / space,
            (ink.x + ink.width) / space,
            (baseline - ink.y) / space,
        )
        expected = (*info.bbox_sw, *info.bbox_ne)
        error = max(abs(a - b) for a, b in zip(drawn, expected, strict=True))
        if error > 0.05:
            failures += 1
            print(f'MISMATCH {name}: drawn {drawn} expected {expected}', file=sys.stderr)
    print(f'checked {len(CODEPOINTS)} glyphs, {failures} mismatches')
    return failures


def render(
    renderer: Renderer,
    gsk: Gsk.Renderer,
    figure: Figure,
    path: Path,
    staff_space: float,
    palette: Palette,
    background: str,
    width: float | None = None,
) -> None:
    display = layout(figure, renderer.metrics, width=width)
    pixel_width = round(display.width * staff_space)
    pixel_height = round(display.height * staff_space)
    rect = Graphene.Rect().init(0, 0, pixel_width, pixel_height)
    snapshot = Gtk.Snapshot()
    color = Gdk.RGBA()
    color.parse(background)
    snapshot.append_color(color, rect)
    renderer.draw(snapshot, display, staff_space, palette)
    node = snapshot.to_node()
    texture = gsk.render_texture(node, rect)
    texture.save_to_png(str(path))
    print(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--output', type=Path, help='directory for the PNG files (default: temp)')
    parser.add_argument('--staff-space', type=float, default=14.0, help='pixels per staff space')
    parser.add_argument('--check-glyphs', action='store_true', help='verify code points')
    args = parser.parse_args()

    Gtk.init()
    if not register_font():
        print('could not register Bravura', file=sys.stderr)
        return 1
    output = args.output or Path(tempfile.mkdtemp(prefix='etude-gallery-'))
    output.mkdir(parents=True, exist_ok=True)

    context = PangoCairo.FontMap.get_default().create_context()
    settings = Gtk.Settings.get_default()
    font_name = settings.props.gtk_font_name if settings else None
    context.set_font_description(Pango.FontDescription.from_string(font_name or 'Sans 11'))
    metrics = FontMetrics.bravura()
    renderer = Renderer(context, metrics)
    if args.check_glyphs and check_glyphs(context, metrics):
        return 1

    gsk = Gsk.CairoRenderer()
    gsk.realize_for_display(Gdk.Display.get_default())
    light, dark = Palette.light(), Palette.dark()
    for name, figure in design_figures().items():
        width = DESIGN_WIDTH / DESIGN_SPACE
        render(renderer, gsk, figure, output / f'{name}.png', DESIGN_SPACE, light, '#ffffff', width)
        if name == 'figScale':
            render(
                renderer,
                gsk,
                figure,
                output / f'{name}-dark.png',
                DESIGN_SPACE,
                dark,
                '#1e1e1e',
                width,
            )
    for name, figure in stress_figures().items():
        render(
            renderer, gsk, figure, output / f'stress-{name}.png', args.staff_space, light, '#ffffff'
        )
    gsk.unrealize()
    return 0


if __name__ == '__main__':
    sys.exit(main())
