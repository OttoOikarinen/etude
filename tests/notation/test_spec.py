# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from etude.core import Pitch
from etude.notation.displaylist import DisplayList, HitRegion, StaffGeometry
from etude.notation.spec import Chord, Clef, StaffSpec


@pytest.mark.parametrize(
    ('clef', 'pitch', 'position'),
    [
        (Clef.TREBLE, 'E4', 0),
        (Clef.TREBLE, 'F4', 1),  # design 1c: first space
        (Clef.TREBLE, 'F5', 8),
        (Clef.TREBLE, 'C4', -2),  # first ledger line below
        (Clef.TREBLE, 'F#4', 1),
        (Clef.BASS, 'G2', 0),
        (Clef.BASS, 'A3', 8),
        (Clef.ALTO, 'C4', 4),  # middle line
        (Clef.TENOR, 'C4', 6),  # fourth line
        (Clef.TREBLE_8VB, 'C4', 5),
    ],
)
def test_staff_position(clef: Clef, pitch: str, position: int) -> None:
    assert clef.staff_position(Pitch.parse(pitch)) == position
    assert clef.pitch_at(position, Pitch.parse(pitch).alter) == Pitch.parse(pitch)


def test_notes_convenience() -> None:
    spec = StaffSpec.notes('G4', Pitch.parse('E5'), clef=Clef.TREBLE)
    assert len(spec.events) == 2
    second = spec.events[1]
    assert isinstance(second, Chord)
    assert second.heads[0].pitch == Pitch.parse('E5')
    assert second.duration is None


def test_staff_geometry_round_trip() -> None:
    geometry = StaffGeometry(Clef.TREBLE, top=2.0)
    for position in range(-4, 13):
        assert geometry.position_at(geometry.y_of(position)) == position
    assert geometry.y_of(8) == 2.0  # top line
    assert geometry.y_of(0) == 6.0  # bottom line


def test_hit_test_prefers_heads() -> None:
    event = HitRegion(staff=0, event=1, head=None, x=0, y=0, width=4, height=8)
    head = HitRegion(staff=0, event=1, head=0, x=1, y=3, width=1.2, height=1)
    display = DisplayList(
        items=(), width=10, height=8, staves=(), hit_regions=(head, event)
    )
    assert display.hit_test(1.5, 3.5) == head
    assert display.hit_test(3.5, 7) == event
    assert display.hit_test(9, 1) is None
