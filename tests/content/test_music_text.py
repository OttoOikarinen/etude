# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

from fractions import Fraction

import pytest

from etude.content.music_text import MusicTextError, figure_playback, parse_events
from etude.core import Duration, NoteValue, Pitch
from etude.core.rhythm import Tuplet
from etude.notation.spec import Barline, BarStyle, Chord, Ink, Rest, StaffSpec, SystemSpec


def test_stemless_notes_and_chords() -> None:
    events = parse_events('C4 E4  [C4 E4 G4]')
    assert len(events) == 3
    assert all(isinstance(e, Chord) and e.duration is None for e in events)
    chord = events[2]
    assert isinstance(chord, Chord)
    assert [h.pitch for h in chord.heads] == [Pitch.parse(p) for p in ('C4', 'E4', 'G4')]


def test_durations_dots_tuplets_and_rests() -> None:
    events = parse_events('F#4/q Bb3/h. G4/e3 r/q r/w..')
    assert events[0] == Chord((events[0].heads[0],), Duration(NoteValue.QUARTER))  # type: ignore[union-attr]
    assert events[1].duration == Duration(NoteValue.HALF, 1)  # type: ignore[union-attr]
    assert events[2].duration == Duration(NoteValue.EIGHTH, 0, Tuplet(3, 2))  # type: ignore[union-attr]
    assert isinstance(events[3], Rest)
    assert events[3].duration == Duration(NoteValue.QUARTER)
    assert events[4] == Rest(Duration(NoteValue.WHOLE, 2))


def test_highlight_label_tie_and_bars() -> None:
    events = parse_events('*E4/q{3} D4/h~ | D4/q || :| |: |.')
    first = events[0]
    assert isinstance(first, Chord)
    assert first.ink is Ink.ACCENT
    assert first.heads[0].halo
    assert first.label == '3'
    assert isinstance(events[1], Chord)
    assert events[1].tie_to_next
    bars = [e.style for e in events if isinstance(e, Barline)]
    assert bars == [
        BarStyle.SINGLE,
        BarStyle.DOUBLE,
        BarStyle.REPEAT_END,
        BarStyle.REPEAT_START,
        BarStyle.FINAL,
    ]


def test_highlighted_chord() -> None:
    (chord,) = parse_events('*[C4 E4]/h')
    assert isinstance(chord, Chord)
    assert all(h.halo for h in chord.heads)


@pytest.mark.parametrize(
    'text',
    ['H4', 'C4/z', 'r', 'C4.', '[]/q', 'C4/q7', 'C4/w....', 'C4/{x'],
)
def test_errors_name_the_token(text: str) -> None:
    with pytest.raises(MusicTextError, match=r"'"):
        parse_events(text)


def test_as_written_playback_follows_rhythm() -> None:
    figure = StaffSpec(events=parse_events('C4/q E4/e r/e G4/h'))
    spec = figure_playback(figure, tempo=120)
    assert [(n.midi, n.start, n.length) for n in spec.notes] == [
        (60, Fraction(0), Fraction(1)),
        (64, Fraction(1), Fraction(1, 2)),
        (67, Fraction(2), Fraction(2)),
    ]
    assert spec.tempo == 120


def test_stemless_notes_play_one_beat_each_and_systems_together() -> None:
    system = SystemSpec(
        (StaffSpec(events=parse_events('E4 G4')), StaffSpec(events=parse_events('C3')))
    )
    spec = figure_playback(system)
    assert sorted((n.midi, n.start) for n in spec.notes) == [
        (48, Fraction(0)),
        (64, Fraction(0)),
        (67, Fraction(1)),
    ]


def test_melodic_and_harmonic_playback() -> None:
    figure = StaffSpec(events=parse_events('[E4 C4 G4]/w'))
    melodic = figure_playback(figure, 'melodic')
    assert [(n.midi, n.start) for n in melodic.notes] == [(60, 0), (64, 1), (67, 2)]
    harmonic = figure_playback(StaffSpec(events=parse_events('C4 E4 C4')), 'harmonic')
    assert sorted(n.midi for n in harmonic.notes) == [60, 64]
    assert {n.start for n in harmonic.notes} == {0}


def test_playback_errors() -> None:
    with pytest.raises(MusicTextError):
        figure_playback(StaffSpec(events=parse_events('r/q')))
    with pytest.raises(MusicTextError):
        figure_playback(StaffSpec(events=parse_events('C4')), 'backwards')


def test_tied_notes_sustain_instead_of_sounding_again() -> None:
    figure = StaffSpec(events=parse_events('C4/h~ | C4/q E4/q~ E4/e r/e E4/q'))
    spec = figure_playback(figure)
    assert [(n.midi, n.start, n.length) for n in spec.notes] == [
        (60, Fraction(0), Fraction(3)),
        (64, Fraction(3), Fraction(3, 2)),
        (64, Fraction(5), Fraction(1)),
    ]
    melodic = figure_playback(figure, 'melodic')
    assert [n.midi for n in melodic.notes] == [60, 64, 64]


def test_a_tied_chord_holds_only_the_common_pitches() -> None:
    spec = figure_playback(StaffSpec(events=parse_events('[C4 G4]/q~ [C4 A4]/q')))
    assert sorted((n.midi, n.start, n.length) for n in spec.notes) == [
        (60, Fraction(0), Fraction(2)),
        (67, Fraction(0), Fraction(1)),
        (69, Fraction(1), Fraction(1)),
    ]
