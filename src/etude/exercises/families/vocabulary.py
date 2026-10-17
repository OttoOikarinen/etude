# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Vocabulary: flashcards made from the glossary.

Every glossary entry (``data/content/glossary/``) gives two items:

* ``vocab.<entry>.meaning``: the headword is shown ("crescendo") and the
  learner picks its gloss among four;
* ``vocab.<entry>.term``: the gloss is shown ("gradually louder") and the
  learner picks the headword, or types it.

Items are generated from the glossary at runtime, so the deck grows as
entries are added; ids use the entry ids, which the content format keeps
stable. An entry that disappears in an update makes :meth:`generate` raise
:class:`KeyError`, and the session runner skips the item.

Distractors come from entries of the same level that share a tag, then
from the same level, then from any level. Entries linked to the answer with
``<see>`` (in either direction) and entries with the same gloss are never
distractors: they are often synonyms (diminuendo and decrescendo).

Typed answers are graded leniently: case, spaces, hyphens, diacritics and a
final full stop do not matter, and the abbreviation ("cresc.") or a synonym
with the same gloss counts; feedback then shows the usual spelling.
"""

from __future__ import annotations

import random
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from gettext import gettext as _
from typing import ClassVar, cast

from ...content.library import ContentLibrary, default_library
from ...content.model import GlossaryEntry, plain_text
from ...core import Pitch, PitchName
from ...core.naming import pitch_name
from ...learning.model import ItemId
from ..base import (
    ChoiceAnswer,
    ChoiceSetting,
    ExerciseDefinition,
    Family,
    Feedback,
    Modality,
    MultiChoiceSetting,
    Option,
    Question,
    Setting,
    TextAnswer,
)

TOPICS = (
    'staff',
    'rhythm',
    'meter',
    'accidentals',
    'scales',
    'keys',
    'minor',
    'intervals',
    'degrees',
    'chords',
    'tempo',
    'dynamics',
    'articulation',
    'directions',
)
"""The vocabulary tags of the curriculum's units. With every topic selected, entries
with other tags are included too."""
LEVELS = ('1', '2', '3', '4')
MEANING = 'meaning'
TERM = 'term'
OPTIONS = 4

Library = Callable[[], ContentLibrary]


def item_id(entry_id: str, kind: str) -> ItemId:
    """``vocab.crescendo.meaning`` or ``vocab.crescendo.term``."""
    return ItemId(f'vocab.{entry_id}.{kind}')


def parse_item(item: str) -> tuple[str, str]:
    """``(entry id, kind)``; raises :class:`ValueError` for other ids."""
    rest = item.removeprefix('vocab.') if item.startswith('vocab.') else ''
    entry_id, _sep, kind = rest.rpartition('.')
    if not entry_id or kind not in (MEANING, TERM):
        raise ValueError(f'not a vocabulary item: {item!r}')
    return entry_id, kind


def normalize(text: str) -> str:
    """Comparison form of a typed term: no case, diacritics, hyphens, extra spaces or
    final full stop."""
    decomposed = unicodedata.normalize('NFKD', text)
    stripped = ''.join(c for c in decomposed if not unicodedata.combining(c))
    words = stripped.casefold().replace('-', ' ').replace('’', "'").split()
    return ' '.join(words).strip('.\'"“”‘ ')


def _capitalized(text: str) -> str:
    """``text`` at the start of a sentence."""
    return text[:1].upper() + text[1:]


def _linked(a: GlossaryEntry, b: GlossaryEntry) -> bool:
    return a.id in b.see_also or b.id in a.see_also


def _same_gloss(a: GlossaryEntry, b: GlossaryEntry) -> bool:
    return a.gloss.casefold().strip() == b.gloss.casefold().strip()


def distractors(
    entry: GlossaryEntry,
    glossary: Mapping[str, GlossaryEntry],
    rng: random.Random,
    count: int = OPTIONS - 1,
    *,
    by_term: bool = False,
) -> list[GlossaryEntry]:
    """Up to ``count`` other entries to offer with ``entry``: same level and a shared tag
    first, then the same level, then any. Never linked entries or ones with the same gloss
    (or, ``by_term``, the same headword)."""

    def label(e: GlossaryEntry) -> str:
        return (e.headword if by_term else e.gloss).casefold().strip()

    usable = [
        e
        for e in sorted(glossary.values(), key=lambda e: e.id)
        if e.id != entry.id and not _linked(entry, e) and not _same_gloss(entry, e)
    ]
    tiers = [
        [e for e in usable if e.level == entry.level and set(e.tags) & set(entry.tags)],
        [e for e in usable if e.level == entry.level],
        usable,
    ]
    chosen: list[GlossaryEntry] = []
    seen = {label(entry)}
    for tier in tiers:
        tier = list(tier)
        rng.shuffle(tier)
        for candidate in tier:
            if len(chosen) == count:
                return chosen
            if candidate in chosen or label(candidate) in seen:
                continue
            if any(_linked(candidate, c) for c in chosen):
                continue
            chosen.append(candidate)
            seen.add(label(candidate))
    return chosen


def _definition(entry: GlossaryEntry) -> str:
    return plain_text(entry.definition, _note_name)


def _note_name(note: object) -> str:
    if isinstance(note, Pitch):
        return pitch_name(note.name) + str(note.octave)
    if isinstance(note, PitchName):
        return pitch_name(note)
    return str(note)


class Vocabulary(ExerciseDefinition):
    id = 'vocabulary'
    item_prefix = 'vocab.'
    family = Family.VOCABULARY
    modality = Modality.EYE
    level = 1
    icon_name = 'vocabulary-symbolic'
    glyph = 'Aa'
    settings: ClassVar[tuple[Setting, ...]] = (
        MultiChoiceSetting(
            'levels',
            _('Levels'),
            tuple(
                # Translators: a curriculum level in the vocabulary settings, e.g. "Level 1".
                Option(level, _('Level {number}').format(number=level))
                for level in LEVELS
            ),
            ('1',),
        ),
        MultiChoiceSetting(
            'topics',
            _('Topics'),
            (
                Option('staff', _('Staff and clefs')),
                Option('rhythm', _('Rhythm')),
                Option('meter', _('Meter')),
                Option('accidentals', _('Accidentals')),
                Option('scales', _('Scales')),
                Option('keys', _('Keys')),
                Option('minor', _('Minor')),
                Option('intervals', _('Intervals')),
                Option('degrees', _('Scale degrees')),
                Option('chords', _('Chords')),
                Option('tempo', _('Tempo')),
                Option('dynamics', _('Dynamics')),
                Option('articulation', _('Articulation')),
                Option('directions', _('Performance directions')),
            ),
            TOPICS,
        ),
        ChoiceSetting(
            'direction',
            _('Cards'),
            (
                Option(MEANING, _('Term → meaning')),
                Option(TERM, _('Meaning → term')),
                Option('both', _('Both ways')),
            ),
            'both',
        ),
        ChoiceSetting(
            'answer',
            _('Answer terms by'),
            (
                Option('choice', _('Choosing')),
                Option('typing', _('Typing')),
            ),
            'choice',
            subtitle=_('For cards that show the meaning'),
        ),
    )

    def __init__(self, library: Library = default_library) -> None:
        self._library = library

    @property
    def title(self) -> str:
        return _('Vocabulary')

    @property
    def description(self) -> str:
        return _('Flashcards of musical terms from the glossary.')

    @property
    def play_label(self) -> str:
        return _('Play example')

    def glossary(self) -> Mapping[str, GlossaryEntry]:
        try:
            return self._library().glossary
        except (OSError, ValueError):
            return {}

    # Settings

    def _levels(self, settings: Mapping[str, object]) -> set[int]:
        chosen = settings.get('levels', ('1',))
        keys = cast(Sequence[str], chosen) if isinstance(chosen, list | tuple) else ('1',)
        return {int(k) for k in keys if k in LEVELS} or {1}

    def _topics(self, settings: Mapping[str, object]) -> set[str] | None:
        """Chosen topics, or ``None`` for everything."""
        chosen = settings.get('topics', TOPICS)
        keys = set(cast(Sequence[str], chosen)) if isinstance(chosen, list | tuple) else set()
        keys &= set(TOPICS)
        return None if not keys or keys == set(TOPICS) else keys

    def _kinds(self, settings: Mapping[str, object]) -> tuple[str, ...]:
        direction = str(settings.get('direction', 'both'))
        if direction == MEANING:
            return (MEANING,)
        if direction == TERM:
            return (TERM,)
        return (MEANING, TERM)

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        levels = sorted(self._levels(settings))
        parts = [
            ', '.join(_('Level {number}').format(number=n) for n in levels),
        ]
        kinds = self._kinds(settings)
        if kinds == (MEANING,):
            parts.append(_('term → meaning'))
        elif kinds == (TERM,):
            parts.append(_('meaning → term'))
        if TERM in kinds and settings.get('answer') == 'typing':
            parts.append(_('typing'))
        return _(' · ').join(parts)

    def item_label(self, item_id: ItemId) -> str:
        entry_id, kind = parse_item(item_id)
        entry = self.glossary().get(entry_id)
        term = entry.headword if entry is not None else entry_id
        if kind == MEANING:
            # Translators: an item in "Weakest items", e.g. "crescendo — meaning".
            return _('{term} — meaning').format(term=term)
        # Translators: an item in "Weakest items", e.g. "crescendo — term".
        return _('{term} — term').format(term=term)

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        """Level by level, topic by topic in curriculum order, then by id."""
        levels, topics = self._levels(settings), self._topics(settings)

        def topic_rank(entry: GlossaryEntry) -> int:
            ranks = [TOPICS.index(t) for t in entry.tags if t in TOPICS]
            return min(ranks, default=len(TOPICS))

        entries = [
            e
            for e in self.glossary().values()
            if e.level in levels and (topics is None or topics & set(e.tags))
        ]
        entries.sort(key=lambda e: (e.level, topic_rank(e), e.id))
        return [item_id(e.id, kind) for e in entries for kind in self._kinds(settings)]

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        """Entries the glossary links with ``<see>``, same kind of card."""
        entry_id, kind = parse_item(item_id)
        glossary = self.glossary()
        entry = glossary.get(entry_id)
        if entry is None:
            return ()
        return [ItemId(f'vocab.{other}.{kind}') for other in entry.see_also if other in glossary]

    # Questions

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        entry_id, kind = parse_item(item_id)
        glossary = self.glossary()
        entry = glossary[entry_id]  # KeyError: the entry is gone; the runner skips it
        example = entry.example
        if kind == MEANING:
            others = distractors(entry, glossary, rng)
            choices = [entry, *others]
            rng.shuffle(choices)
            options = tuple(Option(e.id, e.gloss, accel=str(i + 1)) for i, e in enumerate(choices))
            return Question(
                exercise_id=self.id,
                item_id=item_id,
                # Translators: a vocabulary card, e.g. "What does “crescendo” mean?"
                prompt=_('What does “{term}” mean?').format(term=entry.headword),
                answer=ChoiceAnswer(options),
                expected=entry.id,
                figure=example.figure if example is not None else None,
                playback=example.playback if example is not None else None,
            )
        # Translators: a vocabulary card, e.g. "Which term means “gradually louder”?"
        prompt = _('Which term means “{gloss}”?').format(gloss=entry.gloss)
        if settings.get('answer') == 'typing':
            return Question(
                exercise_id=self.id,
                item_id=item_id,
                prompt=prompt,
                answer=TextAnswer(placeholder=_('Type the term')),
                expected=entry.headword,
                hint=_('It starts with “{start}”.').format(start=entry.headword[:1]),
            )
        others = distractors(entry, glossary, rng, by_term=True)
        choices = [entry, *others]
        rng.shuffle(choices)
        options = tuple(Option(e.id, e.headword, accel=str(i + 1)) for i, e in enumerate(choices))
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=prompt,
            answer=ChoiceAnswer(options),
            expected=entry.id,
        )

    # Grading

    def accepted(self, entry: GlossaryEntry) -> dict[str, str]:
        """Normalised typed answers that count → the spelling they stand for."""
        glossary = self.glossary()
        accepted: dict[str, str] = {}
        for other in (entry, *(e for e in glossary.values() if e is not entry)):
            if other is not entry and not _same_gloss(entry, other):
                continue
            for text in (other.headword, other.term, other.foreign, other.abbreviation):
                if text:
                    accepted.setdefault(normalize(text), other.headword)
        return accepted

    def grade(self, question: Question, given: object) -> Feedback:
        entry_id, kind = parse_item(question.item_id)
        glossary = self.glossary()
        entry = glossary.get(entry_id)
        if entry is None:
            return Feedback(correct=str(given) == str(question.expected), title=_('Not quite'))
        typed = isinstance(question.answer, TextAnswer)
        sentences: list[str] = []
        if typed:
            match = self.accepted(entry).get(normalize(str(given)))
            correct = match is not None
            if match is not None and match != entry.headword:
                # Translators: a typed synonym was accepted, e.g. "Decrescendo is right too;
                # this card is for diminuendo."
                sentences.append(
                    _('{given} is right too; this card is for {term}.').format(
                        given=_capitalized(match), term=entry.headword
                    )
                )
            elif correct and str(given).strip() != entry.headword:
                # Translators: the usual spelling after a leniently accepted typed answer.
                sentences.append(_('Spelled: {term}.').format(term=entry.headword))
        else:
            correct = str(given) == entry.id
        label = entry.gloss if kind == MEANING else entry.headword
        if correct:
            # Translators: e.g. "Correct — gradually louder".
            title = _('Correct — {answer}').format(answer=label)
        else:
            # Translators: e.g. "Not quite — the answer is crescendo".
            title = _('Not quite — the answer is {answer}').format(answer=label)
        # Translators: a glossary definition in feedback, e.g. "Crescendo: Getting gradually
        # louder."
        sentences.append(
            _('{term}: {definition}').format(
                term=_capitalized(entry.headword), definition=_definition(entry)
            )
        )
        if entry.abbreviation:
            sentences.append(
                _('Abbreviation: {abbreviation}.').format(abbreviation=entry.abbreviation)
            )
        other = glossary.get(str(given)) if not typed and not correct else None
        if other is not None:
            # Translators: what the learner's choice means, e.g. "Diminuendo means “gradually
            # softer”."
            sentences.append(
                _('{term} means “{gloss}”.').format(
                    term=_capitalized(other.headword), gloss=other.gloss
                )
            )
        example = entry.example
        return Feedback(
            correct=correct,
            title=title,
            detail=' '.join(sentences),
            expected_label=label,
            figure=example.figure if example is not None else None,
            play_expected=example.playback if example is not None else None,
        )

    def answer_label(self, question: Question, value: object) -> str:
        if isinstance(question.answer, TextAnswer):
            return str(value)
        return super().answer_label(question, value)

    def serialize(self, value: object) -> str:
        return str(value)


EXERCISES: tuple[ExerciseDefinition, ...] = (Vocabulary(),)
