# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Turn content XML into the model of :mod:`etude.content.model`.

The formats are described in docs/CONTENT_AUTHORING.md and in the RELAX NG
schemas in ``data/content/schema/``. The loaders check everything the
model relies on and raise :class:`~etude.content.xml.ContentError` with the
file and element otherwise; cross-references between files are checked by
:class:`etude.content.library.ContentLibrary`.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path

from ..core import KeySignature, Meter
from ..notation.spec import Clef, StaffSpec, SystemSpec
from .model import (
    Block,
    Callout,
    CalloutKind,
    Check,
    CheckOption,
    Curriculum,
    Example,
    GlossaryEntry,
    Lesson,
    Level,
    ListBlock,
    Paragraph,
    ParagraphBlock,
    Practice,
    Section,
    Step,
    Unit,
    WorkedExample,
)
from .music_text import MusicTextError, figure_playback, parse_events
from .xml import ContentError, child, localize, paragraph, required, text_of

_CLEFS = {c.value: c for c in Clef}
_PLAY_MODES = ('as-written', 'melodic', 'harmonic')


def read(path: Path, preferred: Sequence[str]) -> ET.Element:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        raise ContentError(f'{path.name}: {error}') from None
    return localize(root, preferred)


# Examples --------------------------------------------------------------------------


def _staff(element: ET.Element, where: str) -> StaffSpec:
    clef_name = element.get('clef', 'treble')
    if clef_name not in _CLEFS:
        raise ContentError(f'{where}: unknown clef {clef_name!r}')
    key = element.get('key')
    time = element.get('time')
    try:
        events = parse_events(element.text or '')
        return StaffSpec(
            clef=_CLEFS[clef_name],
            key_signature=KeySignature(int(key)) if key is not None else None,
            meter=Meter.parse(time) if time is not None else None,
            events=events,
        )
    except (MusicTextError, ValueError) as error:
        raise ContentError(f'{where}: {error}') from None


def example(element: ET.Element, where: str) -> Example:
    """``<figure play="…" tempo="…"><staff …>notes</staff>…<caption>…</caption></figure>``;
    two or more staves make a system (grand staff, SATB)."""
    staves = [_staff(s, where) for s in element.findall('staff')]
    if not staves:
        raise ContentError(f'{where}: <figure> needs at least one <staff>')
    description = element.findtext('description')
    figure: StaffSpec | SystemSpec
    if len(staves) == 1:
        figure = StaffSpec(
            clef=staves[0].clef,
            key_signature=staves[0].key_signature,
            meter=staves[0].meter,
            events=staves[0].events,
            description=' '.join(description.split()) if description else None,
        )
    else:
        figure = SystemSpec(
            tuple(staves), description=' '.join(description.split()) if description else None
        )
    play = element.get('play')
    playback = None
    if play is not None:
        if play not in _PLAY_MODES:
            raise ContentError(f'{where}: play must be one of {", ".join(_PLAY_MODES)}')
        try:
            playback = figure_playback(figure, play, tempo=float(element.get('tempo', '96')))
        except (MusicTextError, ValueError) as error:
            raise ContentError(f'{where}: {error}') from None
    caption = element.find('caption')
    return Example(figure, paragraph(caption, where) if caption is not None else (), playback)


# Lessons ---------------------------------------------------------------------------


def _paragraphs(element: ET.Element, where: str) -> tuple[Paragraph, ...]:
    return tuple(paragraph(p, where) for p in element.findall('p'))


def _block(element: ET.Element, where: str) -> Block:
    tag = element.tag
    if tag == 'p':
        return ParagraphBlock(paragraph(element, where))
    if tag in ('list', 'steps'):
        return ListBlock(
            tuple(paragraph(li, where) for li in element.findall('li')),
            ordered=element.get('ordered') == 'true' or tag == 'steps',
        )
    if tag == 'callout':
        try:
            kind = CalloutKind(element.get('kind', 'tip'))
        except ValueError:
            raise ContentError(f'{where}: unknown callout kind {element.get("kind")!r}') from None
        return Callout(kind, _paragraphs(element, where))
    if tag == 'figure':
        return example(element, where)
    if tag == 'worked':
        steps = []
        for step in element.findall('step'):
            figure = step.find('figure')
            steps.append(
                Step(
                    _paragraphs(step, where),
                    example(figure, where) if figure is not None else None,
                )
            )
        if not steps:
            raise ContentError(f'{where}: <worked> needs at least one <step>')
        return WorkedExample(text_of(child(element, 'title', where)), tuple(steps))
    if tag == 'check':
        check_id = required(element, 'id', where)
        options = tuple(
            CheckOption(required(o, 'key', where), paragraph(o, where), o.get('correct') == 'true')
            for o in element.findall('option')
        )
        if len(options) < 2 or sum(o.correct for o in options) != 1:
            raise ContentError(f'{where}: check {check_id!r} needs options with one correct')
        if len({o.key for o in options}) != len(options):
            raise ContentError(f'{where}: check {check_id!r} repeats an option key')
        figure = element.find('figure')
        explanation = element.find('explanation')
        return Check(
            check_id,
            paragraph(child(element, 'prompt', where), where),
            options,
            paragraph(explanation, where) if explanation is not None else (),
            example(figure, where) if figure is not None else None,
        )
    raise ContentError(f'{where}: <{tag}> is not a lesson block')


def parse_lesson(root: ET.Element, where: str) -> Lesson:
    if root.tag != 'lesson':
        raise ContentError(f'{where}: the root element must be <lesson>')
    lesson_id = required(root, 'id', where)
    sections = []
    for section in root.findall('section'):
        blocks = tuple(_block(b, f'{where} ({lesson_id})') for b in section if b.tag != 'title')
        sections.append(Section(text_of(child(section, 'title', where)), blocks))
    if not sections:
        raise ContentError(f'{where}: a lesson needs at least one <section>')
    return Lesson(
        lesson_id,
        text_of(child(root, 'title', where)),
        tuple(sections),
        text_of(root.find('summary')),
    )


# Glossary --------------------------------------------------------------------------


def parse_glossary(root: ET.Element, where: str) -> list[GlossaryEntry]:
    if root.tag != 'glossary':
        raise ContentError(f'{where}: the root element must be <glossary>')
    topic_tags = tuple(root.get('tags', '').split())
    entries = []
    for entry in root.findall('entry'):
        entry_id = required(entry, 'id', where)
        here = f'{where} ({entry_id})'
        term = child(entry, 'term', here)
        foreign = entry.find('foreign')
        figure = entry.find('figure')
        try:
            level = int(required(entry, 'level', here))
        except ValueError:
            raise ContentError(f'{here}: level must be a number') from None
        entries.append(
            GlossaryEntry(
                id=entry_id,
                term=text_of(term),
                gloss=text_of(child(entry, 'gloss', here)),
                definition=paragraph(child(entry, 'def', here), here),
                level=level,
                tags=topic_tags + tuple(entry.get('tags', '').split()),
                foreign=text_of(foreign) if foreign is not None else None,
                foreign_language=foreign.get('lang') if foreign is not None else None,
                abbreviation=entry.findtext('abbr'),
                example=example(figure, here) if figure is not None else None,
                see_also=tuple(s.get('ref', '') for s in entry.findall('see')),
            )
        )
    return entries


# Curriculum ------------------------------------------------------------------------


def parse_curriculum(root: ET.Element, where: str) -> Curriculum:
    if root.tag != 'curriculum':
        raise ContentError(f'{where}: the root element must be <curriculum>')
    levels = []
    for level in root.findall('level'):
        level_id = required(level, 'id', where)
        units = []
        previous: str | None = None
        for unit in level.findall('unit'):
            unit_id = required(unit, 'id', where)
            here = f'{where} ({unit_id})'
            practices = tuple(
                Practice(
                    required(p, 'exercise', here),
                    {required(s, 'key', here): s.get('value', '') for s in p.findall('setting')},
                )
                for p in unit.findall('practice')
            )
            requires = tuple(required(r, 'unit', here) for r in unit.findall('requires'))
            if not unit.findall('requires') and previous is not None:
                requires = (previous,)
            units.append(
                Unit(
                    id=unit_id,
                    title=text_of(child(unit, 'title', here)),
                    summary=text_of(unit.find('summary')),
                    lesson_id=unit.get('lesson'),
                    practices=practices,
                    vocabulary_tags=tuple(
                        tag for v in unit.findall('vocabulary') for tag in v.get('tags', '').split()
                    ),
                    requires=requires,
                )
            )
            previous = unit_id
        exam = level.find('exam')
        levels.append(
            Level(
                id=level_id,
                number=int(required(level, 'number', where)),
                title=text_of(child(level, 'title', where)),
                description=text_of(level.find('description')),
                units=tuple(units),
                exam_size=int(exam.get('size', '30')) if exam is not None else 30,
            )
        )
    return Curriculum(tuple(levels))
