# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random

import pytest

from etude.content.library import ContentLibrary, content_dir
from etude.content.model import GlossaryEntry, Text
from etude.exercises.base import ChoiceAnswer, TextAnswer
from etude.exercises.families.vocabulary import (
    Vocabulary,
    distractors,
    item_id,
    normalize,
    parse_item,
)

LIBRARY = ContentLibrary.load(content_dir())
EXERCISE = Vocabulary(lambda: LIBRARY)
DEFAULTS = EXERCISE.default_settings()
TYPING = {**DEFAULTS, 'answer': 'typing'}


def entry(entry_id: str, gloss: str, *, tags=('t',), level=1, see=(), **kwargs) -> GlossaryEntry:
    return GlossaryEntry(
        id=entry_id,
        term=kwargs.pop('term', entry_id),
        gloss=gloss,
        definition=(Text(f'{gloss}.'),),
        level=level,
        tags=tags,
        see_also=see,
        **kwargs,
    )


SYNTHETIC = {
    e.id: e
    for e in (
        entry('diminuendo', 'gradually softer', see=('crescendo',), foreign='diminuendo'),
        entry('decrescendo', 'Gradually softer'),
        entry('crescendo', 'gradually louder', abbreviation='cresc.', foreign='crescendo'),
        entry('ritardando', 'gradually slower', see=('rallentando',)),
        entry('rallentando', 'gradually slowing down'),
        entry('forte', 'loud'),
        entry('piano', 'soft'),
        entry('presto', 'very fast', tags=('tempo',)),
        entry('largo', 'very slow', tags=('tempo',), level=2),
    )
}
SMALL = ContentLibrary(LIBRARY.curriculum, glossary=SYNTHETIC)


def test_item_ids_are_stable_and_parse() -> None:
    items = EXERCISE.items(DEFAULTS)
    assert len(items) == 2 * len([e for e in LIBRARY.glossary.values() if e.level == 1])
    assert items == EXERCISE.items(dict(DEFAULTS)), 'same settings, same order'
    assert 'vocab.crescendo.meaning' in items
    assert 'vocab.crescendo.term' in items
    assert items.index('vocab.staff.meaning') < items.index('vocab.crescendo.meaning')
    assert parse_item(item_id('middle-c', 'term')) == ('middle-c', 'term')
    with pytest.raises(ValueError, match='not a vocabulary item'):
        parse_item('vocab.crescendo.spelling')


def test_settings_filter() -> None:
    meaning = EXERCISE.items({**DEFAULTS, 'direction': 'meaning'})
    assert all(i.endswith('.meaning') for i in meaning)
    staff = EXERCISE.items({**DEFAULTS, 'topics': ('staff',)})
    assert 'vocab.clef.meaning' in staff
    assert 'vocab.crescendo.meaning' not in staff
    assert EXERCISE.items({**DEFAULTS, 'levels': ('4',)}) == []


def test_a_removed_entry_raises_key_error() -> None:
    with pytest.raises(KeyError):
        EXERCISE.generate('vocab.no-such-entry.meaning', DEFAULTS, random.Random(0))


@pytest.mark.parametrize('seed', range(30))
def test_distractors_skip_links_and_synonyms(seed: int) -> None:
    rng = random.Random(seed)
    for target in SYNTHETIC.values():
        chosen = distractors(target, SYNTHETIC, rng)
        assert len(chosen) == 3
        ids = {e.id for e in chosen}
        assert target.id not in ids
        assert not ids & set(target.see_also)
        assert not any(target.id in e.see_also for e in chosen)
        glosses = [e.gloss.casefold() for e in chosen]
        assert target.gloss.casefold() not in glosses
        assert len(set(glosses)) == len(glosses)
    diminuendo = distractors(SYNTHETIC['diminuendo'], SYNTHETIC, rng)
    assert not {'crescendo', 'decrescendo'} & {e.id for e in diminuendo}


def test_distractors_prefer_shared_tags_and_level() -> None:
    chosen = distractors(SYNTHETIC['presto'], SYNTHETIC, random.Random(0))
    assert all(e.level == 1 for e in chosen)


def test_meaning_card() -> None:
    exercise = Vocabulary(lambda: SMALL)
    q = exercise.generate('vocab.crescendo.meaning', DEFAULTS, random.Random(0))
    assert q.prompt == 'What does “crescendo” mean?'
    assert isinstance(q.answer, ChoiceAnswer)
    assert len(q.answer.options) == 4
    assert q.expected == 'crescendo'
    feedback = exercise.grade(q, next(o.key for o in q.answer.options if o.key != 'crescendo'))
    assert feedback.title == 'Not quite — the answer is gradually louder'
    assert 'Abbreviation: cresc.' in feedback.detail
    assert ' means “' in feedback.detail


def test_term_card_by_choice() -> None:
    q = EXERCISE.generate('vocab.diminuendo.term', DEFAULTS, random.Random(0))
    assert q.prompt == 'Which term means “gradually softer”?'
    assert isinstance(q.answer, ChoiceAnswer)
    assert 'crescendo' not in {o.key for o in q.answer.options}  # linked with <see>
    assert EXERCISE.grade(q, 'diminuendo').correct


@pytest.mark.parametrize(
    ('typed', 'note'),
    [
        ('crescendo', None),
        ('  Crescendo ', 'Spelled: crescendo.'),
        ('CRESC.', 'Spelled: crescendo.'),
        ('cresc', 'Spelled: crescendo.'),
    ],
)
def test_typed_answers_are_lenient(typed: str, note: str | None) -> None:
    exercise = Vocabulary(lambda: SMALL)
    q = exercise.generate('vocab.crescendo.term', TYPING, random.Random(0))
    assert isinstance(q.answer, TextAnswer)
    assert q.expected == 'crescendo'
    feedback = exercise.grade(q, typed)
    assert feedback.correct
    if note:
        assert note in feedback.detail
    assert not exercise.grade(q, 'decrescendo').correct


def test_typed_synonym_with_the_same_gloss_counts() -> None:
    exercise = Vocabulary(lambda: SMALL)
    q = exercise.generate('vocab.diminuendo.term', TYPING, random.Random(0))
    feedback = exercise.grade(q, 'Decrescendo')
    assert feedback.correct
    assert 'decrescendo is right too; this card is for diminuendo.' in feedback.detail


def test_normalize() -> None:
    assert normalize(' Ledger-Line. ') == 'ledger line'
    assert normalize('Crescendó') == 'crescendo'
    assert normalize('“tenuto”') == 'tenuto'


def test_example_figure_and_sound() -> None:
    q = EXERCISE.generate('vocab.octave.meaning', DEFAULTS, random.Random(0))
    assert q.figure is not None
    assert q.playback is not None
    term = EXERCISE.generate('vocab.octave.term', DEFAULTS, random.Random(0))
    assert term.figure is None, 'the picture could give the term away'
    feedback = EXERCISE.grade(term, 'octave')
    assert feedback.figure is not None
    assert feedback.play_expected is not None


def test_missing_glossary_gives_no_items() -> None:
    def broken() -> ContentLibrary:
        raise OSError('no content')

    assert Vocabulary(broken).items(DEFAULTS) == []
