# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

from fractions import Fraction

import pytest

from etude.audio.null import NullBackend
from etude.audio.spec import Instrument, PlaybackNote, PlaybackSpec
from etude.core import Pitch

C4, E4, G4 = (Pitch.parse(t) for t in ('C4', 'E4', 'G4'))


def test_melodic() -> None:
    spec = PlaybackSpec.melodic([C4, G4], note_length=Fraction(1, 2), tempo=120)
    assert [(n.midi, n.start, n.length) for n in spec.notes] == [
        (60, 0, Fraction(1, 2)),
        (67, Fraction(1, 2), Fraction(1, 2)),
    ]
    assert spec.length == 1
    assert spec.beats_to_ms(spec.length) == 500


def test_harmonic() -> None:
    spec = PlaybackSpec.harmonic([C4, E4, G4], instrument=Instrument.STRINGS)
    assert {n.start for n in spec.notes} == {0}
    assert spec.instrument is Instrument.STRINGS
    assert spec.length == 2


def test_sequence_offsets_parts() -> None:
    cadence = PlaybackSpec.harmonic([C4, E4, G4], length=Fraction(1), tempo=90)
    question = PlaybackSpec.melodic([E4])
    spec = PlaybackSpec.sequence(cadence, question, gap=Fraction(1, 2))
    assert spec.tempo == 90
    assert spec.notes[-1].start == Fraction(3, 2)


def test_sequence_needs_parts() -> None:
    with pytest.raises(ValueError, match='nothing'):
        PlaybackSpec.sequence()


def test_note_validation() -> None:
    with pytest.raises(ValueError, match='out of range'):
        PlaybackNote(128, Fraction(0), Fraction(1))
    with pytest.raises(ValueError, match='velocity'):
        PlaybackNote(60, Fraction(0), Fraction(1), velocity=0)


def test_note_and_spec_ranges() -> None:
    with pytest.raises(ValueError, match='positive length'):
        PlaybackNote(60, Fraction(0), Fraction(0))
    with pytest.raises(ValueError, match='non-negative start'):
        PlaybackNote(60, Fraction(-1), Fraction(1))
    with pytest.raises(ValueError, match='tempo'):
        PlaybackSpec((), tempo=0)
    with pytest.raises(ValueError, match='count-in'):
        PlaybackSpec((), count_in=-1)


def test_null_backend_finishes_asynchronously() -> None:
    backend = NullBackend()
    events: list[object] = []
    spec = PlaybackSpec.melodic([C4, E4], count_in=2)
    handle = backend.play(spec, on_finished=lambda: events.append('done'), on_beat=events.append)
    assert not backend.available
    assert backend.played == [spec]
    assert events == []
    backend.complete()
    assert events == [-2, -1, 0, 1, 'done']
    assert handle.finished


def test_null_backend_stop_cancels_callbacks() -> None:
    backend = NullBackend()
    events: list[str] = []
    first = backend.play(PlaybackSpec.melodic([C4]), on_finished=lambda: events.append('first'))
    backend.play(PlaybackSpec.melodic([E4]), on_finished=lambda: events.append('second'))
    assert first.stopped
    backend.complete()
    assert events == ['second']
