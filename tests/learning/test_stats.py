# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from tests.learning.fakes import (
    FakeAttemptLog,
    FakeCardStore,
    FakeSessionLog,
    outcome,
    utc,
)

from etude.learning.model import Card, CardState, ItemId, SessionMode, SessionSummary
from etude.learning.stats import (
    Accuracy,
    AccuracyChange,
    ExerciseActivity,
    Stats,
    StatsConfig,
    longest_correct_run,
    weakest_items,
)

HELSINKI = ZoneInfo('Europe/Helsinki')


def local(*args: int, tz: ZoneInfo = HELSINKI) -> datetime:
    return datetime(*args, tzinfo=tz).astimezone(UTC)  # type: ignore[misc]


def make(goal: int = 3, tz: ZoneInfo = HELSINKI, **config: object):
    attempts = FakeAttemptLog()
    sessions = FakeSessionLog()
    stats = Stats(attempts, sessions, tzinfo=tz, config=StatsConfig(daily_goal=goal, **config))  # type: ignore[arg-type]
    return attempts, sessions, stats


def answer_on(attempts: FakeAttemptLog, moment: datetime, count: int, **kwargs: object) -> None:
    for n in range(count):
        attempts.add(outcome(f'i{n}', moment + timedelta(seconds=n), **kwargs), None)  # type: ignore[arg-type]


# Streaks


def test_no_answers_no_streak() -> None:
    _, _, stats = make()
    streak = stats.streak(utc(2026, 10, 15, 12))
    assert (streak.current, streak.longest, streak.today_met) == (0, 0, False)


def test_streak_counts_consecutive_days_meeting_the_goal() -> None:
    attempts, _, stats = make(goal=3)
    for day in (10, 11, 12, 13, 14):
        answer_on(attempts, local(2026, 10, day, 18), 3)
    answer_on(attempts, local(2026, 10, 8, 18), 3)
    streak = stats.streak(local(2026, 10, 14, 20))
    assert (streak.current, streak.longest, streak.today_met) == (5, 5, True)


def test_days_below_the_goal_break_the_streak() -> None:
    attempts, _, stats = make(goal=3)
    for day in (1, 2, 3, 4):
        answer_on(attempts, local(2026, 10, day, 18), 3)
    answer_on(attempts, local(2026, 10, 5, 18), 2)  # short of the goal
    for day in (6, 7):
        answer_on(attempts, local(2026, 10, day, 18), 5)
    streak = stats.streak(local(2026, 10, 7, 20))
    assert (streak.current, streak.longest) == (2, 4)


def test_streak_survives_until_today_is_over() -> None:
    attempts, _, stats = make(goal=3)
    for day in (12, 13, 14):
        answer_on(attempts, local(2026, 10, day, 18), 3)
    morning = stats.streak(local(2026, 10, 15, 8))
    assert (morning.current, morning.today_met) == (3, False)
    answer_on(attempts, local(2026, 10, 15, 9), 3)
    later = stats.streak(local(2026, 10, 15, 10))
    assert (later.current, later.today_met) == (4, True)
    # A whole missed day ends it.
    assert stats.streak(local(2026, 10, 17, 8)).current == 0
    assert stats.streak(local(2026, 10, 17, 8)).longest == 4


def test_streak_days_are_local_days_across_midnight() -> None:
    attempts, _, stats = make(goal=2)
    # 23:30 and 00:30 local are different days even though they are an hour apart.
    answer_on(attempts, local(2026, 10, 13, 23, 30), 2)
    answer_on(attempts, local(2026, 10, 14, 0, 30), 2)
    assert stats.streak(local(2026, 10, 14, 12)).current == 2
    # In UTC both moments fall on 13 October, so a UTC learner has one day.
    utc_stats = Stats(attempts, FakeSessionLog(), config=StatsConfig(daily_goal=2))
    assert utc_stats.streak(utc(2026, 10, 14, 12)).current == 1


def test_answers_split_across_midnight_do_not_add_up() -> None:
    attempts, _, stats = make(goal=4)
    answer_on(attempts, local(2026, 10, 13, 23, 58), 2)
    answer_on(attempts, local(2026, 10, 14, 0, 1), 2)
    assert stats.streak(local(2026, 10, 14, 1)).current == 0


@pytest.mark.parametrize(
    ('day', 'hours'),
    [(date(2026, 3, 29), 23), (date(2026, 10, 25), 25)],
    ids=['spring-forward', 'fall-back'],
)
def test_streak_across_daylight_saving_changes(day: date, hours: int) -> None:
    attempts, _, stats = make(goal=2)
    start, end = stats.day_range(day)
    assert end - start == timedelta(hours=hours)
    before = day - timedelta(days=1)
    after = day + timedelta(days=1)
    for d in (before, day, after):
        s, e = stats.day_range(d)
        # First and last minute of each local day.
        attempts.add(outcome('a', s), None)
        attempts.add(outcome('b', e - timedelta(minutes=1)), None)
    streak = stats.streak(stats.day_range(after)[0] + timedelta(hours=12))
    assert (streak.current, streak.longest) == (3, 3)
    assert stats.questions_per_day(stats.day_range(after)[0], days=3) == [
        (before, 2),
        (day, 2),
        (after, 2),
    ]


def test_answered_today() -> None:
    attempts, _, stats = make()
    answer_on(attempts, local(2026, 10, 14, 23, 59), 4)
    answer_on(attempts, local(2026, 10, 15, 0, 0), 3)
    answer_on(attempts, local(2026, 10, 15, 21, 0), 2)
    assert stats.answered_today(local(2026, 10, 15, 22)) == 5


def test_questions_per_day_last_seven_days() -> None:
    attempts, _, stats = make()
    answer_on(attempts, local(2026, 10, 8, 12), 9)  # eight days ago: outside
    answer_on(attempts, local(2026, 10, 9, 12), 1)
    answer_on(attempts, local(2026, 10, 12, 12), 4)
    answer_on(attempts, local(2026, 10, 15, 7), 2)
    days = stats.questions_per_day(local(2026, 10, 15, 8))
    assert days == [
        (date(2026, 10, 9), 1),
        (date(2026, 10, 10), 0),
        (date(2026, 10, 11), 0),
        (date(2026, 10, 12), 4),
        (date(2026, 10, 13), 0),
        (date(2026, 10, 14), 0),
        (date(2026, 10, 15), 2),
    ]


# Accuracy


def test_accuracy_for_a_period() -> None:
    attempts, _, stats = make()
    answer_on(attempts, local(2026, 10, 15, 9), 3)
    answer_on(attempts, local(2026, 10, 15, 10), 1, correct=False)
    result = stats.accuracy(*stats.period(local(2026, 10, 15, 12), 1))
    assert result == Accuracy(correct=3, total=4)
    assert result.ratio == 0.75
    assert Accuracy(0, 0).ratio is None


def test_accuracy_change_in_percentage_points() -> None:
    attempts, _, stats = make()
    now = local(2026, 10, 15, 12)
    # Previous week (2–8 October): 6 of 10.
    answer_on(attempts, local(2026, 10, 3, 12), 6)
    answer_on(attempts, local(2026, 10, 8, 23, 50), 4, correct=False)
    # This week (9–15 October): 8 of 10.
    answer_on(attempts, local(2026, 10, 9, 0, 10), 8)
    answer_on(attempts, local(2026, 10, 15, 11), 2, correct=False)
    # Too old to count.
    answer_on(attempts, local(2026, 10, 1, 12), 5, correct=False)
    change = stats.accuracy_change(now, days=7)
    assert change.current == Accuracy(8, 10)
    assert change.previous == Accuracy(6, 10)
    assert change.change_points == pytest.approx(20.0)


def test_accuracy_change_without_data() -> None:
    assert AccuracyChange(Accuracy(3, 4), Accuracy(0, 0)).change_points is None
    assert AccuracyChange(Accuracy(0, 0), Accuracy(3, 4)).change_points is None


def test_accuracy_by_exercise() -> None:
    attempts, _, stats = make()
    answer_on(attempts, local(2026, 10, 15, 9), 2, exercise='notes')
    answer_on(attempts, local(2026, 10, 15, 9), 2, exercise='keys', correct=False)
    answer_on(attempts, local(2026, 10, 15, 10), 1, exercise='keys')
    result = stats.accuracy_by_exercise(*stats.period(local(2026, 10, 15, 12), 7))
    assert result == {'keys': Accuracy(1, 3), 'notes': Accuracy(2, 2)}
    assert list(result) == ['keys', 'notes']


# Sessions


def summary(total: int = 10, best: int = 5, duration_ms: int = 60_000) -> SessionSummary:
    return SessionSummary(
        total=total,
        correct=best,
        duration_ms=duration_ms,
        best_streak=best,
        personal_best=False,
        mistakes=(),
    )


def test_time_practised_and_session_count() -> None:
    _, sessions, stats = make()
    a = sessions.start(SessionMode.EXERCISE, 'keys', local(2026, 10, 15, 9))
    sessions.finish(a, local(2026, 10, 15, 9, 5), summary(duration_ms=300_000))
    b = sessions.start(SessionMode.DAILY_REVIEW, None, local(2026, 10, 15, 18))
    sessions.finish(b, local(2026, 10, 15, 18, 2), summary(duration_ms=120_000))
    sessions.start(SessionMode.EXERCISE, 'keys', local(2026, 10, 15, 19))  # unfinished
    old = sessions.start(SessionMode.EXERCISE, 'keys', local(2026, 10, 1, 9))
    sessions.finish(old, local(2026, 10, 1, 9, 5), summary(duration_ms=999_000))
    period = stats.period(local(2026, 10, 15, 20), 7)
    assert stats.time_practised(*period) == timedelta(minutes=7)
    assert stats.session_count(*period) == 2


def test_sessions_without_answers_do_not_count() -> None:
    _, sessions, stats = make()
    empty = sessions.start(SessionMode.EXERCISE, 'keys', local(2026, 10, 15, 9))
    sessions.finish(empty, local(2026, 10, 15, 9, 1), summary(total=0, best=0))
    real = sessions.start(SessionMode.EXERCISE, 'keys', local(2026, 10, 15, 10))
    sessions.finish(real, local(2026, 10, 15, 10, 2), summary(duration_ms=120_000))
    period = stats.period(local(2026, 10, 15, 20), 7)
    assert stats.session_count(*period) == 1
    assert stats.time_practised(*period) == timedelta(minutes=2)


def test_exercise_activity() -> None:
    attempts, sessions, stats = make(recent_answers=4)
    now = local(2026, 10, 15, 20)
    for n in range(6):
        # Two old mistakes, then four correct answers: only the recent four count.
        attempts.add(
            outcome(f'k{n}', local(2026, 10, 15, 9, n), correct=n >= 2, exercise='keys'), None
        )
    attempts.add(outcome('n0', local(2026, 10, 14, 9), correct=False, exercise='notes'), None)
    for exercise, total in (('keys', 10), ('keys', 0), ('notes', 3), (None, 5)):
        sid = sessions.start(SessionMode.EXERCISE, exercise, local(2026, 10, 15, 8))
        sessions.finish(sid, local(2026, 10, 15, 8, 5), summary(total=total, best=0))
    sessions.start(SessionMode.EXERCISE, 'keys', local(2026, 10, 15, 11))  # unfinished
    result = stats.exercise_activity(['keys', 'notes', 'ivl'], now)
    assert result['keys'] == ExerciseActivity(Accuracy(4, 4), local(2026, 10, 15, 9, 5), 1)
    assert result['notes'] == ExerciseActivity(Accuracy(0, 1), local(2026, 10, 14, 9), 1)
    assert result['ivl'] == ExerciseActivity(Accuracy(0, 0), None, 0)
    assert result['ivl'].recent.ratio is None


def test_set_daily_goal_applies_to_streaks() -> None:
    attempts, _, stats = make(goal=3)
    now = local(2026, 10, 15, 20)
    answer_on(attempts, local(2026, 10, 15, 9), 4)
    assert stats.streak(now).current == 1
    stats.set_daily_goal(5)
    assert stats.config.daily_goal == 5
    assert stats.streak(now).current == 0
    with pytest.raises(ValueError, match='at least 1'):
        stats.set_daily_goal(0)


def test_paused_time_is_not_practice() -> None:
    _, _, stats = make()
    start = utc(2026, 10, 15, 9)
    result = stats.session_summary(
        [outcome('a', start + timedelta(seconds=5))],
        mode=SessionMode.EXERCISE,
        exercise_id='ex',
        started_at=start,
        finished_at=start + timedelta(hours=1),
        paused=timedelta(minutes=59),
    )
    assert result.duration_ms == 60_000


def test_session_summary() -> None:
    _, _, stats = make()
    start = utc(2026, 10, 15, 9)
    outcomes = [
        outcome('a', start + timedelta(seconds=10)),
        outcome('b', start + timedelta(seconds=20), correct=False),
        outcome('c', start + timedelta(seconds=30)),
        outcome('d', start + timedelta(seconds=40)),
        outcome('e', start + timedelta(seconds=50)),
        outcome('b', start + timedelta(seconds=60), correct=False),
        outcome('f', start + timedelta(seconds=70), correct=False),
    ]
    result = stats.session_summary(
        outcomes,
        mode=SessionMode.EXERCISE,
        exercise_id='ex',
        started_at=start,
        finished_at=start + timedelta(seconds=75),
    )
    assert result == SessionSummary(
        total=7,
        correct=4,
        duration_ms=75_000,
        best_streak=3,
        personal_best=False,
        mistakes=(ItemId('b'), ItemId('f')),
    )


def test_personal_best_compares_earlier_sessions_of_the_same_exercise() -> None:
    _, sessions, stats = make()

    def finished(exercise: str, at: datetime, best: int) -> None:
        sid = sessions.start(SessionMode.EXERCISE, exercise, at)
        sessions.finish(sid, at + timedelta(minutes=5), summary(best=best))

    def best(streak: int, at: datetime, exercise: str = 'keys') -> bool:
        outcomes = [outcome(f'i{n}', at) for n in range(streak)]
        return stats.session_summary(
            outcomes,
            mode=SessionMode.EXERCISE,
            exercise_id=exercise,
            started_at=at,
            finished_at=at + timedelta(minutes=5),
        ).personal_best

    now = utc(2026, 10, 15, 12)
    assert not best(10, now), 'a first session has nothing to beat'
    finished('keys', utc(2026, 10, 10, 9), 8)
    finished('notes', utc(2026, 10, 11, 9), 50)
    finished('keys', utc(2026, 10, 16, 9), 30)  # later: does not count
    assert best(9, now)
    assert not best(8, now), 'equalling is not beating'
    assert not best(7, now, exercise='notes')


def test_unfinished_and_negative_durations() -> None:
    _, _, stats = make()
    start = utc(2026, 10, 15, 9)
    result = stats.session_summary(
        [],
        mode=SessionMode.DAILY_REVIEW,
        exercise_id=None,
        started_at=start,
        finished_at=start - timedelta(seconds=1),
    )
    assert (result.total, result.duration_ms, result.best_streak) == (0, 0, 0)


def test_longest_correct_run() -> None:
    t = utc(2026, 10, 15)
    pattern = [True, True, False, True, True, True, False]
    assert longest_correct_run(outcome('a', t, correct=c) for c in pattern) == 3
    assert longest_correct_run([]) == 0


# Items


def test_weakest_items() -> None:
    t = utc(2026, 10, 15, 9)
    outcomes = []
    for item, results in {
        'good': [True] * 5,
        'bad': [False, False, True],
        'meh': [True, False, True, True],
        'meh-long': [True, False] * 4,  # 50 %, more lapses than 'half'
        'half': [True, False],  # too few attempts
        'half4': [True, False, True, False],
    }.items():
        outcomes += [outcome(item, t, correct=c) for c in results]
    result = weakest_items(outcomes, limit=10, min_attempts=3)
    assert [s.item_id for s in result] == ['bad', 'meh-long', 'half4', 'meh']
    assert result[0].accuracy == pytest.approx(1 / 3)
    assert result[1].lapses == 4
    assert [s.item_id for s in weakest_items(outcomes, limit=2, min_attempts=3)] == [
        'bad',
        'meh-long',
    ]


def test_weakest_items_tie_break_on_fsrs_lapses() -> None:
    t = utc(2026, 10, 15, 9)
    outcomes = [outcome(i, t, correct=c) for i in ('x', 'y') for c in (True, False, False, True)]
    cards = {
        ItemId('x'): Card(ItemId('x'), t, CardState.REVIEW, lapses=1),
        ItemId('y'): Card(ItemId('y'), t, CardState.REVIEW, lapses=5),
    }
    assert [s.item_id for s in weakest_items(outcomes, limit=5, min_attempts=3, cards=cards)] == [
        'y',
        'x',
    ]


def test_stats_weakest_items_uses_a_recent_window_and_cards() -> None:
    attempts = FakeAttemptLog()
    now = utc(2026, 10, 15, 9)
    for c in (False, False, False):
        attempts.add(outcome('old', now - timedelta(days=200), correct=c), None)
    for item, ex in (('a', 'keys'), ('b', 'notes')):
        for c in (True, False, False):
            attempts.add(outcome(item, now - timedelta(days=1), correct=c, exercise=ex), None)
    cards = FakeCardStore([Card(ItemId('b'), now, CardState.REVIEW, lapses=3)])
    stats = Stats(attempts, FakeSessionLog(), cards=cards)
    assert [s.item_id for s in stats.weakest_items(now)] == ['b', 'a']
    assert [s.item_id for s in stats.weakest_items(now, exercise_id='keys')] == ['a']
    no_cards = Stats(attempts, FakeSessionLog())
    assert {s.item_id for s in no_cards.weakest_items(now)} == {'a', 'b'}


# Speed


def test_speed_thresholds_default_with_little_data() -> None:
    attempts, _, stats = make(speed_min_samples=20)
    answer_on(attempts, utc(2026, 10, 15, 9), 19, ms=1000)
    speed = stats.speed_thresholds('ex')
    assert (speed.fast_ms, speed.slow_ms, speed.samples) == (2500.0, 8000.0, 0)


def test_speed_thresholds_are_quartiles_of_correct_unhinted_answers() -> None:
    attempts, _, stats = make(speed_min_samples=5)
    t = utc(2026, 10, 15, 9)
    for n, ms in enumerate([1000, 2000, 3000, 4000, 5000]):
        attempts.add(outcome(f'i{n}', t + timedelta(seconds=n), ms=ms), None)
    # Wrong, hinted and other exercises' answers do not count.
    attempts.add(outcome('w', t, ms=99_000, correct=False), None)
    attempts.add(outcome('h', t, ms=99_000, hinted=True), None)
    attempts.add(outcome('o', t, ms=99_000, exercise='other'), None)
    speed = stats.speed_thresholds('ex')
    assert (speed.fast_ms, speed.slow_ms, speed.samples) == (2000.0, 4000.0, 5)


def test_speed_thresholds_use_only_recent_answers() -> None:
    attempts, _, stats = make(speed_min_samples=3, speed_samples=3)
    t = utc(2026, 10, 15, 9)
    for n in range(10):
        attempts.add(outcome('a', t + timedelta(seconds=n), ms=60_000), None)
    for n in range(3):
        attempts.add(outcome('a', t + timedelta(minutes=1, seconds=n), ms=1000), None)
    assert stats.speed_thresholds('ex').slow_ms == 1000.0
