# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""All content of the application, loaded once and cross-checked.

Layout of the content directory (``data/content/`` in the source tree,
``<pkgdatadir>/content/`` when installed)::

    curriculum.xml
    lessons/<level>/<unit>.xml
    glossary/<topic>.xml
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from .. import paths
from .loaders import parse_curriculum, parse_glossary, parse_lesson, read
from .model import (
    Callout,
    Check,
    Curriculum,
    Example,
    GlossaryEntry,
    Lesson,
    ListBlock,
    Paragraph,
    ParagraphBlock,
    TermRef,
    Unit,
    WorkedExample,
)
from .xml import ContentError, languages


@dataclass(frozen=True)
class ContentLibrary:
    curriculum: Curriculum
    lessons: dict[str, Lesson] = field(default_factory=dict)
    glossary: dict[str, GlossaryEntry] = field(default_factory=dict)

    @classmethod
    def load(cls, directory: Path, preferred: Sequence[str] = ()) -> ContentLibrary:
        where = directory / 'curriculum.xml'
        curriculum = parse_curriculum(read(where, preferred), where.name)
        lessons: dict[str, Lesson] = {}
        for path in sorted((directory / 'lessons').glob('*/*.xml')):
            lesson = parse_lesson(read(path, preferred), str(path.relative_to(directory)))
            if lesson.id in lessons:
                raise ContentError(f'{path.name}: lesson {lesson.id!r} is defined twice')
            lessons[lesson.id] = lesson
        glossary: dict[str, GlossaryEntry] = {}
        for path in sorted((directory / 'glossary').glob('*.xml')):
            for entry in parse_glossary(read(path, preferred), path.name):
                if entry.id in glossary:
                    raise ContentError(f'{path.name}: glossary entry {entry.id!r} is defined twice')
                glossary[entry.id] = entry
        library = cls(curriculum, lessons, glossary)
        library.check()
        return library

    # Queries

    def lesson_for(self, unit: Unit) -> Lesson | None:
        return self.lessons.get(unit.lesson_id) if unit.lesson_id else None

    def vocabulary(self, unit: Unit) -> list[GlossaryEntry]:
        """Glossary entries a unit teaches: its tags at its level."""
        level = self.curriculum.level_of(unit.id).number
        tags = set(unit.vocabulary_tags)
        return [e for e in self.glossary.values() if e.level == level and tags & set(e.tags)]

    def entries(self, *, level: int | None = None) -> list[GlossaryEntry]:
        """Glossary entries sorted by headword, optionally up to a level."""
        chosen = [e for e in self.glossary.values() if level is None or e.level <= level]
        return sorted(chosen, key=lambda e: e.headword.casefold())

    # Consistency

    def check(self) -> None:
        """Raise :class:`ContentError` for broken references between files."""
        unit_ids: set[str] = set()
        for level in self.curriculum.levels:
            for unit in level.units:
                if unit.id in unit_ids:
                    raise ContentError(f'curriculum: unit {unit.id!r} is defined twice')
                unit_ids.add(unit.id)
        for level in self.curriculum.levels:
            for unit in level.units:
                if unit.lesson_id is not None and unit.lesson_id not in self.lessons:
                    raise ContentError(f'curriculum: unit {unit.id!r} names a missing lesson')
                for required in unit.requires:
                    if required not in unit_ids:
                        raise ContentError(
                            f'curriculum: unit {unit.id!r} requires unknown unit {required!r}'
                        )
        for lesson in self.lessons.values():
            for ref in _term_refs_in_lesson(lesson):
                if ref not in self.glossary:
                    raise ContentError(f'lesson {lesson.id!r}: unknown glossary term {ref!r}')
            check_ids = [c.id for c in lesson.checks]
            if len(check_ids) != len(set(check_ids)):
                raise ContentError(f'lesson {lesson.id!r}: check ids must be unique')
        for entry in self.glossary.values():
            for ref in (*entry.see_also, *_refs(entry.definition)):
                if ref not in self.glossary:
                    raise ContentError(f'glossary {entry.id!r}: unknown term {ref!r}')


def _refs(paragraph: Paragraph) -> Iterable[str]:
    return (i.entry_id for i in paragraph if isinstance(i, TermRef))


def _example_refs(example: Example | None) -> Iterable[str]:
    return _refs(example.caption) if example is not None else ()


def _term_refs_in_lesson(lesson: Lesson) -> Iterable[str]:
    for section in lesson.sections:
        for block in section.blocks:
            if isinstance(block, ParagraphBlock):
                yield from _refs(block.content)
            elif isinstance(block, ListBlock):
                for item in block.items:
                    yield from _refs(item)
            elif isinstance(block, Callout):
                for paragraph in block.content:
                    yield from _refs(paragraph)
            elif isinstance(block, Example):
                yield from _example_refs(block)
            elif isinstance(block, WorkedExample):
                for step in block.steps:
                    for paragraph in step.content:
                        yield from _refs(paragraph)
                    yield from _example_refs(step.example)
            elif isinstance(block, Check):
                yield from _refs(block.prompt)
                yield from _refs(block.explanation)
                for option in block.options:
                    yield from _refs(option.content)
                yield from _example_refs(block.example)


def content_dir() -> Path:
    return paths.data_file('content')


@cache
def default_library() -> ContentLibrary:
    """The application's content in the learner's language."""
    return ContentLibrary.load(content_dir(), languages())
