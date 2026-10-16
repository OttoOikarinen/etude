# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The content model: curriculum, theory lessons and glossary.

These types are what the loaders in this package produce from the XML in
``data/content/`` and what the UI renders. Texts are already in the
learner's language (the loaders pick the translation); note names inside
texts stay as :class:`NoteRef` so the UI writes them in the learner's
naming convention (C–B, H/B or do).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

from ..audio.spec import PlaybackSpec
from ..core import Pitch, PitchName
from ..notation.spec import Figure

# Inline text ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Text:
    text: str


@dataclass(frozen=True, slots=True)
class Emphasis:
    text: str


@dataclass(frozen=True, slots=True)
class TermRef:
    """A glossary term mentioned in a text; the UI links it to the glossary."""

    text: str
    entry_id: str


@dataclass(frozen=True, slots=True)
class NoteRef:
    """A note name in a text (``<note>Bb</note>``), shown in the learner's convention."""

    note: Pitch | PitchName


Inline = Text | Emphasis | TermRef | NoteRef
Paragraph = tuple[Inline, ...]


def _symbol(note: Pitch | PitchName) -> str:
    if isinstance(note, Pitch):
        return f'{note.name.symbol}{note.octave}'
    return note.symbol


def plain_text(paragraph: Paragraph, name_note: object = None) -> str:
    """The paragraph as plain text; ``name_note(note) -> str`` names notes."""
    parts = []
    for inline in paragraph:
        if isinstance(inline, NoteRef):
            parts.append(name_note(inline.note) if callable(name_note) else _symbol(inline.note))
        else:
            parts.append(inline.text)
    return ''.join(parts)


# Lesson blocks ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Example:
    """A notated example with optional sound."""

    figure: Figure
    caption: Paragraph = ()
    playback: PlaybackSpec | None = None


@dataclass(frozen=True, slots=True)
class ParagraphBlock:
    content: Paragraph


@dataclass(frozen=True, slots=True)
class ListBlock:
    items: tuple[Paragraph, ...]
    ordered: bool = False


class CalloutKind(Enum):
    TIP = 'tip'
    REMEMBER = 'remember'
    WARNING = 'warning'


@dataclass(frozen=True, slots=True)
class Callout:
    kind: CalloutKind
    content: tuple[Paragraph, ...]


@dataclass(frozen=True, slots=True)
class Step:
    """One step of a worked example: text, optionally with notation."""

    content: tuple[Paragraph, ...]
    example: Example | None = None


@dataclass(frozen=True, slots=True)
class WorkedExample:
    """A problem solved step by step (worked examples, docs/PEDAGOGY.md)."""

    title: str
    steps: tuple[Step, ...]


@dataclass(frozen=True, slots=True)
class CheckOption:
    key: str
    content: Paragraph
    correct: bool = False


@dataclass(frozen=True, slots=True)
class Check:
    """A "check your understanding" question inside a lesson (retrieval practice).

    Exactly one option is correct; ``explanation`` is shown after answering.
    """

    id: str
    prompt: Paragraph
    options: tuple[CheckOption, ...]
    explanation: Paragraph = ()
    example: Example | None = None

    @property
    def answer(self) -> str:
        return next(o.key for o in self.options if o.correct)


Block = ParagraphBlock | ListBlock | Callout | Example | WorkedExample | Check


@dataclass(frozen=True, slots=True)
class Section:
    title: str
    blocks: tuple[Block, ...]


@dataclass(frozen=True, slots=True)
class Lesson:
    id: str
    title: str
    sections: tuple[Section, ...]
    summary: str = ''

    @property
    def checks(self) -> tuple[Check, ...]:
        return tuple(b for s in self.sections for b in s.blocks if isinstance(b, Check))


# Glossary ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GlossaryEntry:
    """A term with a short gloss and a definition.

    ``term`` is in the learner's language (``"half note"`` → ``"puolinuotti"``);
    ``foreign`` keeps an original-language term untranslated (``crescendo``,
    language ``"it"``), and is then what flashcards ask for.
    """

    id: str
    term: str
    gloss: str
    definition: Paragraph
    level: int
    tags: tuple[str, ...] = ()
    foreign: str | None = None
    foreign_language: str | None = None
    abbreviation: str | None = None
    example: Example | None = None
    see_also: tuple[str, ...] = ()

    @property
    def headword(self) -> str:
        """What the glossary lists and flashcards ask: the foreign term if any."""
        return self.foreign or self.term


# Curriculum -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Practice:
    """An exercise with the settings that narrow it to what the unit teaches.

    Settings are raw strings from the XML; ``etude.exercises.settings.coerce``
    turns them into the exercise's setting types.
    """

    exercise_id: str
    settings: Mapping[str, str] = field(default_factory=dict, hash=False)


@dataclass(frozen=True, slots=True)
class Unit:
    id: str
    title: str
    summary: str
    lesson_id: str | None
    practices: tuple[Practice, ...]
    vocabulary_tags: tuple[str, ...] = ()
    """Glossary entries of the unit: those with any of these tags at this level."""
    requires: tuple[str, ...] = ()
    """Units that must be mastered first; by default the previous unit of the level."""


@dataclass(frozen=True, slots=True)
class Level:
    id: str
    number: int
    title: str
    description: str
    units: tuple[Unit, ...]
    exam_size: int = 30


@dataclass(frozen=True, slots=True)
class Curriculum:
    levels: tuple[Level, ...]

    def unit(self, unit_id: str) -> Unit:
        for level in self.levels:
            for unit in level.units:
                if unit.id == unit_id:
                    return unit
        raise KeyError(unit_id)

    def level_of(self, unit_id: str) -> Level:
        for level in self.levels:
            if any(u.id == unit_id for u in level.units):
                return level
        raise KeyError(unit_id)
