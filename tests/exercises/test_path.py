# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The learning path: unit items, unlocking, exams and the placement walk."""

from __future__ import annotations

import random
from datetime import timedelta

import pytest
from tests.learning.fakes import (
    FakeAttemptLog,
    FakeCardStore,
    FakeClock,
    FakeSessionLog,
    outcome,
)

from etude.content.library import ContentLibrary, content_dir
from etude.content.model import Curriculum, GlossaryEntry, Level, Practice, Unit
from etude.exercises.families.key_signatures import KeySignatures
from etude.exercises.families.note_naming import NoteNaming
from etude.exercises.path import (
    ExamRunner,
    LearningPath,
    PathRecord,
    PlacementRunner,
    merged_settings,
)
from etude.exercises.registry import ExerciseRegistry, default_registry
from etude.learning.engine import LearningEngine
from etude.learning.mastery import Mastery
from etude.learning.model import Card, CardState, ItemId, SessionMode, SessionRequest
from etude.learning.scheduler import FsrsScheduler


def keysig(max_accidentals: int, mode: str = 'major') -> Practice:
    return Practice('keysig', {'max-accidentals': str(max_accidentals), 'mode': mode})


def unit(unit_id: str, *practices: Practice, requires: tuple[str, ...] = (), **kw) -> Unit:
    return Unit(unit_id, unit_id.upper(), '', None, practices, requires=requires, **kw)


def curriculum() -> Curriculum:
    """Two levels: a → b → c (c is lesson-only) and d → e in level 2."""
    level1 = Level(
        'level1',
        1,
        'One',
        '',
        (
            unit('l1.a', keysig(1)),
            unit('l1.b', keysig(2), requires=('l1.a',)),
            unit('l1.c', requires=('l1.b',)),
        ),
        exam_size=4,
    )
    level2 = Level(
        'level2',
        2,
        'Two',
        '',
        (unit('l2.d', keysig(1, 'minor')), unit('l2.e', keysig(3), requires=('l2.d',))),
    )
    return Curriculum((level1, level2))


class World:
    def __init__(self, library: ContentLibrary | None = None, registry=None) -> None:
        self.clock = FakeClock()
        self.registry = registry or ExerciseRegistry([KeySignatures(), NoteNaming()])
        self.cards = FakeCardStore()
        self.attempts = FakeAttemptLog()
        self.sessions = FakeSessionLog()
        self.mastery = Mastery(self.cards, self.attempts)
        self.library = library or ContentLibrary(curriculum())
        self.path = LearningPath(self.library, self.registry, self.mastery)
        rng = random.Random(5)
        self.engine = LearningEngine.create(
            self.registry,
            self.cards,
            self.attempts,
            self.sessions,
            scheduler=FsrsScheduler(rng=rng, fuzz=False),
            rng=rng,
            clock=self.clock,
        )

    def master(self, *items: str) -> None:
        now = self.clock()
        for item in items:
            self.cards.put(
                Card(ItemId(item), now + timedelta(days=30), CardState.REVIEW, None, 30.0, 5.0)
            )
            for n in range(3):
                self.attempts.add(
                    outcome(item, now - timedelta(minutes=n), exercise='keysig'), None
                )

    def status(self, record: PathRecord | None = None) -> dict[str, object]:
        levels = self.path.status(record or PathRecord())
        return {u.unit.id: u for level in levels for u in level.units}


# Items


def test_unit_items_follow_the_practice_settings() -> None:
    world = World()
    units = {u.id: u for level in world.library.curriculum.levels for u in level.units}
    assert world.path.unit_items(units['l1.a']) == (
        'keysig.major.0',
        'keysig.major.1s',
        'keysig.major.1b',
    )
    assert len(world.path.unit_items(units['l1.b'])) == 5
    assert world.path.unit_items(units['l1.c']) == ()


def test_unit_items_skip_unknown_exercises_and_bad_settings() -> None:
    world = World()
    odd = unit(
        'l9.x',
        Practice('no-such-exercise'),
        Practice('keysig', {'colour': 'red'}),
        keysig(0),
    )
    assert world.path.unit_items(odd) == ('keysig.major.0',)


def test_the_real_curriculum_resolves() -> None:
    library = ContentLibrary.load(content_dir())
    path = LearningPath(library, default_registry(), Mastery(FakeCardStore(), FakeAttemptLog()))

    def exercise_items(unit_id: str) -> list[str]:
        return [
            i
            for i in path.unit_items(library.curriculum.unit(unit_id))
            if not i.startswith('vocab.')
        ]

    all_staff = path.unit_items(library.curriculum.unit('l1.staff'))
    assert any(i.startswith('vocab.') for i in all_staff), 'unit vocabulary is included'
    items = exercise_items('l1.staff')
    assert items
    assert all(i.startswith(('note.', 'place.')) for i in items)
    assert not any('#' in i or 'b' in i.split('.')[-1][1:] for i in items), 'no accidentals'
    accidentals = exercise_items('l1.accidentals')
    assert set(items) < set(accidentals)
    intervals = exercise_items('l1.intervals')
    assert {i.split('.')[1] for i in intervals} == {'staff', 'ear', 'write'}


class FakeVocabulary(KeySignatures):
    id = 'vocabulary'
    item_prefix = 'vocab.'

    def items(self, settings):
        return [
            ItemId('vocab.staff.meaning'),
            ItemId('vocab.staff.term'),
            ItemId('vocab.forte.meaning'),
            ItemId('vocab.odd'),
        ]


def test_vocabulary_items_belong_to_the_units_glossary_entries() -> None:
    entries = {
        'staff': GlossaryEntry('staff', 'staff', 'g', (), 1, ('staff',)),
        'forte': GlossaryEntry('forte', 'forte', 'g', (), 1, ('dynamics',)),
    }
    level = Level('level1', 1, 'One', '', (unit('l1.a', vocabulary_tags=('staff',)),))
    library = ContentLibrary(Curriculum((level,)), glossary=entries)
    world = World(library, ExerciseRegistry([FakeVocabulary()]))
    assert world.path.unit_items(level.units[0]) == ('vocab.staff.meaning', 'vocab.staff.term')
    # Without the vocabulary exercise a unit's vocabulary adds nothing.
    assert World(library).path.unit_items(level.units[0]) == ()


def test_settings_for_takes_the_last_unit_practising_an_exercise() -> None:
    world = World()
    level = world.library.curriculum.levels[0]
    assert world.path.settings_for(level.units) == {
        'keysig': {'max-accidentals': 2, 'mode': 'major'}
    }
    provider = merged_settings(
        lambda _e: {'max-accidentals': 5, 'clefs': ('bass',)},
        world.path.settings_for(level.units),
    )
    assert provider('keysig') == {'max-accidentals': 2, 'mode': 'major', 'clefs': ('bass',)}


# Unlocking


def test_a_new_learner_has_only_the_first_unit_unlocked() -> None:
    status = World().status()
    assert status['l1.a'].unlocked
    assert not status['l1.b'].unlocked
    assert [u.id for u in status['l1.b'].missing] == ['l1.a']
    assert not status['l2.d'].unlocked
    assert [u.id for u in status['l2.d'].missing] == ['l1.a', 'l1.b'], 'c is lesson-only'
    assert not status['l1.c'].complete, 'a locked unit without items is not complete'
    assert [u.id for u in status['l1.c'].missing] == ['l1.b']
    assert status['l1.c'].fraction is None
    assert status['l1.a'].fraction == 0.0


def test_mastering_most_of_a_unit_unlocks_the_next() -> None:
    world = World()
    world.master('keysig.major.0', 'keysig.major.1s')
    status = world.status()
    assert status['l1.a'].mastered == 2
    assert not status['l1.a'].complete, '2 of 3 is below 80 %'
    world.master('keysig.major.1b')
    status = world.status()
    assert status['l1.a'].complete
    assert status['l1.a'].fraction == 1.0
    assert status['l1.b'].unlocked
    assert not status['l1.c'].unlocked, 'b is not mastered yet'
    world.master('keysig.major.2s', 'keysig.major.2b')
    status = world.status()
    assert status['l1.c'].unlocked
    assert status['l2.d'].unlocked, 'every unit of level 1 is complete'
    assert not status['l2.e'].unlocked


def test_units_without_items_pass_on_the_state_of_the_units_before_them() -> None:
    level = Level(
        'level1',
        1,
        'One',
        '',
        (
            unit('l1.a', keysig(1)),
            unit('l1.lesson1', requires=('l1.a',)),
            unit('l1.lesson2', requires=('l1.lesson1',)),
            unit('l1.b', keysig(2), requires=('l1.lesson2',)),
        ),
    )
    world = World(ContentLibrary(Curriculum((level,))))
    status = world.status()
    assert not status['l1.lesson2'].unlocked
    assert not status['l1.b'].unlocked, 'lesson-only units do not open the way past them'
    assert [u.id for u in status['l1.b'].missing] == ['l1.a'], 'the unit to master is named'
    world.master('keysig.major.0', 'keysig.major.1s', 'keysig.major.1b')
    status = world.status()
    assert status['l1.lesson1'].complete
    assert status['l1.lesson2'].complete
    assert status['l1.b'].unlocked


def test_placement_and_passed_levels_unlock() -> None:
    world = World()
    status = world.status(PathRecord(placed_units=frozenset({'l1.a', 'l1.b'})))
    assert status['l1.a'].placed
    assert status['l1.a'].complete
    assert status['l1.b'].unlocked
    assert status['l1.c'].unlocked
    assert status['l2.d'].unlocked
    status = world.status(PathRecord(passed_levels=frozenset({'level1'})))
    assert all(status[u].unlocked and status[u].complete for u in ('l1.a', 'l1.b', 'l1.c'))
    assert status['l2.d'].unlocked
    assert not status['l2.d'].complete


def test_exam_ready_when_every_unit_of_the_level_is_unlocked() -> None:
    world = World()
    level = world.path.status(PathRecord())[0]
    assert not level.exam_ready
    assert level.completed == 0
    world.master('keysig.major.0', 'keysig.major.1s', 'keysig.major.1b')
    world.master('keysig.major.2s', 'keysig.major.2b')
    level = world.path.status(PathRecord())[0]
    assert level.exam_ready
    assert len(level.items) == 5


# Exams


def test_exam_items_are_balanced_over_units() -> None:
    world = World()
    level = world.library.curriculum.levels[0]
    items = world.path.exam_items(level, random.Random(1))
    assert len(items) == 4
    assert len(set(items)) == 4
    # Unit a has three items, unit b adds two more of its own.
    assert sum(i in world.path.unit_items(level.units[0]) for i in items) == 2


def exam_runner(world: World, passed: list[str]) -> ExamRunner:
    level = world.library.curriculum.levels[0]
    items = world.path.exam_items(level, random.Random(1))
    request = SessionRequest(
        SessionMode.LEVEL_EXAM, now=world.clock(), size=len(items), item_ids=items
    )
    return ExamRunner(
        world.engine,
        world.registry,
        request,
        level=level,
        on_passed=passed.append,
        rng=random.Random(2),
        clock=world.clock,
    )


def answer_all(runner, *, wrong: set[int] = frozenset()) -> None:
    number = 0
    while True:
        question = runner.current.question
        if number in wrong:
            runner.answer(
                next(o.key for o in question.answer.options if o.key != question.expected),
                response_ms=2000,
            )
        else:
            runner.answer(question.expected, response_ms=2000)
        number += 1
        if not runner.advance():
            break


def test_an_exam_with_80_percent_passes_the_level() -> None:
    world = World()
    passed: list[str] = []
    runner = exam_runner(world, passed)
    assert runner.title == 'Level 1 Exam'
    assert runner.total == 4
    answer_all(runner)
    runner.finish()
    assert runner.result is not None
    assert runner.result.passed
    assert runner.result.complete
    assert passed == ['level1']
    assert len(world.attempts.entries) == 4, 'exam answers are recorded'


def test_an_exam_below_80_percent_or_left_early_does_not_pass() -> None:
    world = World()
    passed: list[str] = []
    runner = exam_runner(world, passed)
    answer_all(runner, wrong={0})  # 3 of 4 = 75 %
    runner.finish()
    assert runner.result is not None
    assert not runner.result.passed
    assert runner.result.needed == 4
    runner = runner.again()
    runner.answer(runner.current.question.expected, response_ms=1000)
    runner.finish()
    assert runner.result is not None
    assert not runner.result.complete
    assert not runner.result.passed
    assert passed == []


# Placement


def test_placement_plan_samples_what_each_unit_adds() -> None:
    world = World()
    plan = world.path.placement_plan(PathRecord(), random.Random(1), per_unit=5)
    samples = dict(plan.samples)
    assert list(samples) == ['l1.a', 'l1.b', 'l2.d', 'l2.e']
    assert set(samples['l1.b']) == {'keysig.major.2s', 'keysig.major.2b'}
    assert set(samples['l2.e']) == {'keysig.major.3s', 'keysig.major.3b'}
    assert len(plan.items) == len(set(plan.items))
    skipped = world.path.placement_plan(
        PathRecord(passed_levels=frozenset({'level1'})), random.Random(1)
    )
    assert [u for u, _i in skipped.samples] == ['l2.d', 'l2.e']


def test_placement_plan_places_units_without_new_items_with_the_unit_before() -> None:
    level = Level(
        'level1', 1, 'One', '', (unit('l1.a', keysig(1)), unit('l1.b', keysig(1, 'major')))
    )
    world = World(ContentLibrary(Curriculum((level,))))
    plan = world.path.placement_plan(PathRecord(), random.Random(1))
    assert [u for u, _i in plan.samples] == ['l1.a']
    assert plan.followers == {'l1.a': ('l1.b',)}


def placement_runner(world: World, placed: list[str]) -> PlacementRunner:
    plan = world.path.placement_plan(PathRecord(), random.Random(1), per_unit=5)
    request = SessionRequest(
        SessionMode.PLACEMENT, now=world.clock(), size=len(plan.items), item_ids=plan.items
    )
    return PlacementRunner(
        world.engine,
        world.registry,
        request,
        plan=plan,
        on_placed=placed.append,
        rng=random.Random(2),
        clock=world.clock,
    )


def test_placement_walks_until_the_first_unit_not_known() -> None:
    world = World()
    placed: list[str] = []
    runner = placement_runner(world, placed)
    assert runner.title == 'Placement Test'
    assert runner.total == 3 + 2 + 3 + 2
    # Unit a: all three right. Unit b has two items, so both must be right:
    # one mistake ends the test.
    for _ in range(3):
        runner.answer(runner.current.question.expected, response_ms=2000)
        assert runner.advance()
    assert placed == ['l1.a']
    question = runner.current.question
    assert question.item_id in dict(runner.plan.samples)['l1.b']
    wrong = next(o.key for o in question.answer.options if o.key != question.expected)
    runner.answer(wrong, response_ms=2000)
    assert not runner.advance(), 'the test ends at the first unit failed'
    summary = runner.finish()
    assert summary.total == 4
    assert runner.result.placed == ('l1.a',)
    assert runner.result.failed == 'l1.b'
    status = world.status(PathRecord(placed_units=frozenset(placed)))
    assert status['l1.b'].unlocked
    assert not status['l1.c'].unlocked


def test_placement_skips_the_rest_of_a_unit_once_it_is_placed_out() -> None:
    level = Level('level1', 1, 'One', '', (unit('l1.a', keysig(3)), unit('l1.b', keysig(5))))
    world = World(ContentLibrary(Curriculum((level,))))
    placed: list[str] = []
    runner = placement_runner(world, placed)
    assert runner.total == 9  # five of unit a's seven items, and b's four new ones
    for _ in range(4):
        runner.answer(runner.current.question.expected, response_ms=2000)
        runner.advance()
    assert placed == ['l1.a']
    assert runner.total == 8, 'the fifth question of unit a is no longer needed'
    assert runner.current.question.item_id in dict(runner.plan.samples)['l1.b']
    skipped = runner.skip(response_ms=1000)
    assert not skipped.correct
    again = runner.again()
    assert again.result.placed == ()


@pytest.mark.parametrize('seed', range(3))
def test_placement_answers_feed_the_scheduler(seed: int) -> None:
    world = World()
    runner = placement_runner(world, [])
    runner.answer(runner.current.question.expected, response_ms=1500)
    item = ItemId(runner.current.question.item_id)
    assert world.cards.get(item) is not None
