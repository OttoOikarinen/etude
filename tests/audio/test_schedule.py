# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

from fractions import Fraction

from hypothesis import given
from hypothesis import strategies as st

from etude.audio.metronome import ACCENT_KEY, CLICK_KEY
from etude.audio.schedule import (
    CLICK_MS,
    MELODIC_CHANNEL,
    PERCUSSION_CHANNEL,
    RELEASE_MS,
    EventKind,
    Schedule,
    ScheduledEvent,
    build_schedule,
    to_ticks,
)
from etude.audio.spec import PlaybackNote, PlaybackSpec
from etude.core import Meter

F = Fraction


def kinds(schedule: Schedule, kind: EventKind) -> list[ScheduledEvent]:
    return [e for e in schedule.events if e.kind is kind]


def test_beats_to_ms_at_tempo() -> None:
    spec = PlaybackSpec((), tempo=120)
    assert spec.beats_to_ms(F(1)) == 500
    assert spec.beats_to_ms(F(1, 3)) == 500 / 3


def test_melody_events() -> None:
    spec = PlaybackSpec(
        (PlaybackNote(60, F(0), F(1)), PlaybackNote(62, F(1), F(1, 2), velocity=70)), tempo=60
    )
    schedule = build_schedule(spec)
    assert [(e.time_ms, e.kind, e.key) for e in schedule.events if e.kind < EventKind.FINISHED] == [
        (0.0, EventKind.BEAT, 0),
        (0.0, EventKind.NOTE_ON, 60),
        (1000.0, EventKind.NOTE_OFF, 60),
        (1000.0, EventKind.BEAT, 0),
        (1000.0, EventKind.NOTE_ON, 62),
        (1500.0, EventKind.NOTE_OFF, 62),
    ]
    assert kinds(schedule, EventKind.NOTE_ON)[1].velocity == 70
    assert all(e.channel == MELODIC_CHANNEL for e in schedule.events)
    assert [e.beat for e in kinds(schedule, EventKind.BEAT)] == [0, 1]
    assert schedule.start_ms == 0
    assert schedule.end_ms == 1500 + RELEASE_MS
    assert schedule.events[-1].kind is EventKind.FINISHED


def test_repeated_note_releases_before_it_restrikes() -> None:
    spec = PlaybackSpec((PlaybackNote(60, F(0), F(1)), PlaybackNote(60, F(1), F(1))), tempo=60)
    at_one_second = [e.kind for e in build_schedule(spec).events if e.time_ms == 1000]
    assert at_one_second == [EventKind.NOTE_OFF, EventKind.BEAT, EventKind.NOTE_ON]


def test_count_in_clicks_are_negative_and_accented() -> None:
    spec = PlaybackSpec((PlaybackNote(64, F(0), F(1)),), tempo=120, count_in=4, meter=Meter(4, 4))
    schedule = build_schedule(spec)
    clicks = [e for e in kinds(schedule, EventKind.NOTE_ON) if e.channel == PERCUSSION_CHANNEL]
    assert [(e.time_ms, e.key) for e in clicks] == [
        (-2000.0, ACCENT_KEY),
        (-1500.0, CLICK_KEY),
        (-1000.0, CLICK_KEY),
        (-500.0, CLICK_KEY),
    ]
    note_offs = [e for e in kinds(schedule, EventKind.NOTE_OFF) if e.channel == PERCUSSION_CHANNEL]
    assert [e.time_ms for e in note_offs] == [t + CLICK_MS for t in (-2000, -1500, -1000, -500)]
    assert [e.beat for e in kinds(schedule, EventKind.BEAT)] == [-4, -3, -2, -1, 0]
    assert schedule.start_ms == -2000


def test_click_runs_through_the_playback() -> None:
    spec = PlaybackSpec((PlaybackNote(64, F(0), F(3)),), tempo=60, click=True, meter=Meter(6, 8))
    clicks = [
        (e.time_ms, e.key)
        for e in build_schedule(spec).events
        if e.kind is EventKind.NOTE_ON and e.channel == PERCUSSION_CHANNEL
    ]
    assert clicks == [(0.0, ACCENT_KEY), (1500.0, CLICK_KEY)]


def test_percussion_notes_use_channel_ten() -> None:
    spec = PlaybackSpec((PlaybackNote(76, F(0), F(1), percussion=True),))
    assert {e.channel for e in kinds(build_schedule(spec), EventKind.NOTE_ON)} == {
        PERCUSSION_CHANNEL
    }


def test_empty_spec_only_finishes() -> None:
    schedule = build_schedule(PlaybackSpec(()), release_ms=10)
    assert schedule.events == (ScheduledEvent(10, EventKind.FINISHED),)
    assert Schedule(()).start_ms == Schedule(()).end_ms == 0


def test_count_in_only_finishes_after_the_last_click() -> None:
    spec = PlaybackSpec((), tempo=60, count_in=2)
    schedule = build_schedule(spec, release_ms=0)
    assert schedule.end_ms == 0.0


def test_duration_keeps_counting_beats_after_the_notes() -> None:
    """A tap phase: a count-in, then two bars of beats with nothing written in them."""
    spec = PlaybackSpec((), tempo=60, count_in=2, meter=Meter(2, 4), duration=F(4))
    schedule = build_schedule(spec, release_ms=100)
    assert [e.beat for e in kinds(schedule, EventKind.BEAT)] == [-2, -1, 0, 1, 2, 3]
    assert schedule.end_ms == 4100
    # Without the click only the count-in sounds.
    assert len(kinds(schedule, EventKind.NOTE_ON)) == 2


def test_duration_shorter_than_the_notes_changes_nothing() -> None:
    note = PlaybackNote(60, F(0), F(2))
    assert PlaybackSpec((note,), duration=F(1)).length == 2
    assert PlaybackSpec((note,), duration=F(3)).length == 3


def test_to_ticks_rounds_each_event() -> None:
    assert to_ticks(0, 500) == 500
    assert to_ticks(-1000, 1500) == 500
    assert to_ticks(1000 / 3, 0) == 333
    assert to_ticks(2000 / 3, 0) == 667
    assert to_ticks(10, 0, ticks_per_second=48_000) == 480


@given(
    st.lists(
        st.tuples(
            st.integers(21, 108),
            st.fractions(min_value=0, max_value=16, max_denominator=12),
            st.fractions(min_value=F(1, 12), max_value=4, max_denominator=12),
        ),
        max_size=12,
    ),
    st.floats(min_value=30, max_value=240),
    st.integers(0, 8),
    st.booleans(),
)
def test_schedule_properties(
    raw: list[tuple[int, Fraction, Fraction]], tempo: float, count_in: int, click: bool
) -> None:
    spec = PlaybackSpec(
        tuple(PlaybackNote(m, s, n) for m, s, n in raw), tempo=tempo, count_in=count_in, click=click
    )
    schedule = build_schedule(spec)
    assert list(schedule.events) == sorted(schedule.events)
    note_ons = kinds(schedule, EventKind.NOTE_ON)
    note_offs = kinds(schedule, EventKind.NOTE_OFF)
    assert len(note_ons) == len(note_offs)
    melodic_ons = sorted(e.time_ms for e in note_ons if e.channel == MELODIC_CHANNEL)
    assert melodic_ons == sorted(spec.beats_to_ms(n.start) for n in spec.notes)
    assert schedule.start_ms == (-spec.beats_to_ms(count_in) if count_in else 0)
    assert kinds(schedule, EventKind.FINISHED) == [schedule.events[-1]]
    assert all(e.time_ms < schedule.end_ms for e in schedule.events[:-1])
