# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import random

import pytest

from etude.content.library import ContentLibrary, content_dir
from etude.exercises.base import ChoiceAnswer
from etude.exercises.families.symbols import (
    GROUPS,
    SYMBOLS,
    Symbols,
    demonstration,
    figure_for,
    item_id,
    parse_item,
)
from etude.notation.a11y import describe
from etude.notation.layout import layout
from etude.notation.smufl import FontMetrics
from etude.notation.spec import Barline, BarStyle, Clef, GlyphFigure, StaffSpec

LIBRARY = ContentLibrary.load(content_dir())
EXERCISE = Symbols(lambda: LIBRARY)
DEFAULTS = EXERCISE.default_settings()
ITEMS = EXERCISE.items(DEFAULTS)


def test_items_cover_every_symbol_once() -> None:
    assert len(ITEMS) == len(SYMBOLS) == len(set(ITEMS))
    assert [parse_item(i) for i in ITEMS] == list(SYMBOLS)
    assert EXERCISE.items({**DEFAULTS, 'groups': ('clef',)}) == [
        'symbol.clef.treble',
        'symbol.clef.bass',
        'symbol.clef.alto',
        'symbol.clef.tenor',
    ]
    with pytest.raises(ValueError, match='not a symbol item'):
        parse_item('symbol.dynamic.fff')


@pytest.mark.parametrize('item', ITEMS)
def test_figures_lay_out_and_never_name_the_symbol(item: str) -> None:
    symbol = parse_item(item)
    names = {symbol.key, symbol.glossary.replace('-', ' ')}
    for seed in range(4):
        figure = figure_for(symbol, random.Random(seed))
        display = layout(figure, FontMetrics.bravura())
        assert display.items
        text = describe(figure).casefold()
        assert not any(name.casefold() in text.split() for name in names), text
        assert 'clef' not in text or symbol.group == 'clef'


def test_figure_kinds() -> None:
    rng = random.Random(0)
    dynamic = figure_for(parse_item('symbol.dynamic.mf'), rng)
    assert dynamic == GlyphFigure(('dynamicMF',), 'A dynamic marking in bold italic letters.')
    fermata = figure_for(parse_item('symbol.articulation.fermata'), rng)
    assert isinstance(fermata, GlyphFigure)
    assert fermata.glyphs == ('noteQuarterDown', 'fermataAbove')
    assert fermata.staff
    clef = figure_for(parse_item('symbol.clef.tenor'), rng)
    assert isinstance(clef, StaffSpec)
    assert clef.clef is Clef.TENOR
    repeat = figure_for(parse_item('symbol.bar.repeat-start'), rng)
    assert isinstance(repeat, StaffSpec)
    assert repeat.events[0] == Barline(BarStyle.REPEAT_START)


def test_options_are_the_group() -> None:
    q = EXERCISE.generate('symbol.dynamic.mp', DEFAULTS, random.Random(0))
    assert isinstance(q.answer, ChoiceAnswer)
    assert [o.label for o in q.answer.options] == [
        'Very soft',
        'Soft',
        'Moderately soft',
        'Moderately loud',
        'Loud',
        'Very loud',
        'Gradually louder',
        'Gradually softer',
    ]
    q = EXERCISE.generate('symbol.articulation.tenuto', DEFAULTS, random.Random(0))
    assert isinstance(q.answer, ChoiceAnswer)
    assert [o.key for o in q.answer.options] == ['staccato', 'accent', 'tenuto', 'fermata']
    assert q.answer.options[2].description == 'Held its full length'


def test_feedback_meaning_glossary_and_sound() -> None:
    q = EXERCISE.generate('symbol.dynamic.cresc', DEFAULTS, random.Random(0))
    feedback = EXERCISE.grade(q, 'dim')
    assert feedback.title == 'Not quite — the answer is gradually louder'
    assert 'hairpin opening to the right is a crescendo' in feedback.detail
    assert 'Glossary: crescendo — gradually louder.' in feedback.detail
    assert 'For comparison: A hairpin closing' in feedback.detail
    assert feedback.play_expected is not None
    assert feedback.play_given is not None
    velocities = [n.velocity for n in feedback.play_expected.notes]
    assert velocities == sorted(velocities)
    q = EXERCISE.generate('symbol.clef.alto', DEFAULTS, random.Random(0))
    feedback = EXERCISE.grade(q, 'alto')
    assert feedback.correct
    assert feedback.title == 'Correct — Alto clef'
    assert feedback.play_expected is None


def test_demonstrations() -> None:
    by_key = {s.key: s for s in SYMBOLS}
    staccato = demonstration(by_key['staccato'])
    tenuto = demonstration(by_key['tenuto'])
    assert staccato is not None
    assert tenuto is not None
    assert max(n.length for n in staccato.notes) < min(n.length for n in tenuto.notes)
    pp, ff = demonstration(by_key['pp']), demonstration(by_key['ff'])
    assert pp is not None
    assert ff is not None
    assert pp.notes[0].velocity < ff.notes[0].velocity


def test_missing_content_is_not_fatal() -> None:
    def broken() -> ContentLibrary:
        raise OSError('no content')

    exercise = Symbols(broken)
    q = exercise.generate(item_id(SYMBOLS[0]), DEFAULTS, random.Random(0))
    assert exercise.grade(q, q.expected).correct
    assert set(GROUPS) == {s.group for s in SYMBOLS}
