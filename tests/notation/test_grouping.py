# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

from fractions import Fraction

from etude.core import Duration, Meter, NoteValue, Pitch, Tuplet
from etude.notation._grouping import beam_groups, flag_count, onsets, tuplet_groups
from etude.notation.spec import Barline, Chord, Event, Head, Rest

Q = Duration(NoteValue.QUARTER)
E = Duration(NoteValue.EIGHTH)
S = Duration(NoteValue.SIXTEENTH)
C4 = Head(Pitch.parse('C4'))


def notes(*durations: Duration | None) -> tuple[Event, ...]:
    return tuple(Chord((C4,), d) for d in durations)


def test_onsets() -> None:
    events = (*notes(Q, E, None), Barline(), Rest(Q))
    assert onsets(events) == [
        Fraction(0),
        Fraction(1, 4),
        Fraction(3, 8),
        Fraction(5, 8),
        Fraction(5, 8),
    ]


def test_flag_count() -> None:
    assert flag_count(None) == 0
    assert flag_count(Q) == 0
    assert flag_count(E) == 1
    assert flag_count(Duration(NoteValue.SIXTY_FOURTH)) == 4


def test_beams_follow_beats_in_four_four() -> None:
    events = notes(E, E, E, E, Q, S, S, S, S)
    assert beam_groups(events, Meter(4, 4)) == [[0, 1], [2, 3], [5, 6, 7, 8]]


def test_beams_in_compound_and_irregular_meters() -> None:
    six = notes(E, E, E, E, E, E)
    assert beam_groups(six, Meter(6, 8)) == [[0, 1, 2], [3, 4, 5]]
    seven = notes(E, E, E, E, E, E, E)
    assert beam_groups(seven, Meter(7, 8)) == [[0, 1], [2, 3], [4, 5, 6]]
    assert beam_groups(seven, Meter(7, 8, (3, 2, 2))) == [[0, 1, 2], [3, 4], [5, 6]]


def test_rests_barlines_and_long_notes_break_beams() -> None:
    events = (*notes(E), Rest(E), *notes(E, E), Barline(), *notes(E, Q, E))
    assert beam_groups(events, Meter(2, 4)) == [[2, 3]]


def test_beams_without_meter_use_quarter_beats() -> None:
    assert beam_groups(notes(E, E, E, E), None) == [[0, 1], [2, 3]]
    assert beam_groups(notes(None, None), None) == []


def test_dotted_rhythm_is_one_group() -> None:
    events = notes(Duration(NoteValue.EIGHTH, 1), S)
    assert beam_groups(events, Meter(2, 4)) == [[0, 1]]


def test_tuplet_groups() -> None:
    triplet = Duration(NoteValue.EIGHTH, tuplet=Tuplet(3, 2))
    quarter_triplet = Duration(NoteValue.QUARTER, tuplet=Tuplet(3, 2))
    events = notes(triplet, triplet, triplet, triplet, triplet, triplet, Q)
    assert tuplet_groups(events) == [(Tuplet(3, 2), [0, 1, 2]), (Tuplet(3, 2), [3, 4, 5])]
    mixed = notes(quarter_triplet, triplet)
    assert tuplet_groups(mixed) == [(Tuplet(3, 2), [0, 1])]


def test_sextuplet_is_one_group() -> None:
    six = Duration(NoteValue.SIXTEENTH, tuplet=Tuplet(6, 4))
    assert tuplet_groups(notes(*[six] * 6)) == [(Tuplet(6, 4), [0, 1, 2, 3, 4, 5])]


def test_unfinished_tuplets_still_group() -> None:
    triplet = Duration(NoteValue.EIGHTH, tuplet=Tuplet(3, 2))
    five = Duration(NoteValue.SIXTEENTH, tuplet=Tuplet(5, 4))
    assert tuplet_groups(notes(triplet, triplet, Q)) == [(Tuplet(3, 2), [0, 1])]
    assert tuplet_groups(notes(triplet, five)) == [(Tuplet(3, 2), [0]), (Tuplet(5, 4), [1])]
    assert tuplet_groups(notes(Q, triplet)) == [(Tuplet(3, 2), [1])]
    rests = (Rest(triplet), *notes(triplet, triplet))
    assert tuplet_groups(rests) == [(Tuplet(3, 2), [0, 1, 2])]
