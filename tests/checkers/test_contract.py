# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

from etude.checkers.voice_leading import BASS, SOPRANO, Context, Ranges, Rule
from etude.core import Pitch
from etude.exercises.base import StaffInputAnswer
from etude.notation.spec import Clef


def test_default_ranges() -> None:
    ranges = Ranges()
    assert ranges.of(SOPRANO) == (Pitch.parse('C4'), Pitch.parse('G5'))
    assert ranges.of(BASS) == (Pitch.parse('E2'), Pitch.parse('C4'))


def test_context_applies_every_rule_by_default() -> None:
    assert Context().rules == frozenset(Rule)


def test_voices_on_a_grand_staff() -> None:
    satb = StaffInputAnswer(Clef.TREBLE, voices=4, staves=(Clef.TREBLE, Clef.BASS))
    assert [satb.staff_of_voice(v) for v in range(4)] == [0, 0, 1, 1]
    single = StaffInputAnswer(Clef.BASS)
    assert single.staff_of_voice(0) == 0
    custom = StaffInputAnswer(
        Clef.TREBLE, voices=4, staves=(Clef.TREBLE, Clef.BASS), voice_staves=(0, 1, 1, 1)
    )
    assert custom.staff_of_voice(1) == 1


def test_rhythm_template_defaults_to_stemless() -> None:
    assert StaffInputAnswer(Clef.TREBLE).rhythm == ()


def test_check_is_implemented() -> None:
    from etude.checkers.voice_leading import check

    chord = tuple(Pitch.parse(n) for n in ('C5', 'G4', 'E4', 'C3'))
    assert check([chord]) == []
