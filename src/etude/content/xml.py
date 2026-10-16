# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Reading content XML: language selection and inline text.

Installed content files are produced by ``itstool`` (``i18n.itstool_join``),
which places each translation right after its English original as a
sibling with the same tag and an ``xml:lang`` attribute. :func:`localize`
keeps the best translation of every such run and drops the rest, so the
loaders never see more than one language. Content read from the source
tree has no translations and passes through unchanged.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence

from ..core import Pitch, PitchName
from .model import Emphasis, Inline, NoteRef, Paragraph, TermRef, Text

XML_LANG = '{http://www.w3.org/XML/1998/namespace}lang'


class ContentError(ValueError):
    """Invalid content; the message names the file and the element."""


def languages(environ: Mapping[str, str] = os.environ) -> tuple[str, ...]:
    """The learner's languages in order of preference, like gettext chooses them:
    ``LANGUAGE`` (a colon-separated list), else ``LC_ALL``, ``LC_MESSAGES`` or ``LANG``.
    ``fi_FI.UTF-8`` gives ``('fi_FI', 'fi')``."""
    names: list[str] = []
    for variable in ('LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG'):
        value = environ.get(variable)
        if value:
            names = value.split(':') if variable == 'LANGUAGE' else [value]
            break
    result: list[str] = []
    for name in names:
        name = name.split('.')[0].split('@')[0]
        if not name or name in ('C', 'POSIX'):
            continue
        for candidate in (name, name.split('_')[0]):
            if candidate not in result:
                result.append(candidate)
    return tuple(result)


def _rank(lang: str, preferred: Sequence[str]) -> int | None:
    normalized = lang.replace('-', '_')
    for index, wanted in enumerate(preferred):
        if normalized == wanted or normalized.split('_')[0] == wanted:
            return index
    return None


def localize(root: ET.Element, preferred: Sequence[str]) -> ET.Element:
    """Keep, in every run of an original and its translations, the best one."""
    for parent in root.iter():
        children = list(parent)
        keep: list[ET.Element] = []
        index = 0
        while index < len(children):
            original = children[index]
            run = [original]
            index += 1
            while (
                index < len(children)
                and children[index].tag == original.tag
                and children[index].get(XML_LANG) is not None
                and original.get(XML_LANG) is None
            ):
                run.append(children[index])
                index += 1
            best = original
            best_rank: int | None = None
            for variant in run[1:]:
                rank = _rank(variant.get(XML_LANG, ''), preferred)
                if rank is not None and (best_rank is None or rank < best_rank):
                    best, best_rank = variant, rank
            keep.append(best)
        if len(keep) != len(children):
            for child in children:
                parent.remove(child)
            parent.extend(keep)
    return root


def text_of(element: ET.Element | None) -> str:
    """All text of an element with whitespace collapsed (for titles and glosses)."""
    if element is None:
        return ''
    return ' '.join(''.join(element.itertext()).split())


def _note(text: str, where: str) -> Pitch | PitchName:
    text = text.strip()
    try:
        return Pitch.parse(text) if text[-1:].isdigit() else PitchName.parse(text)
    except ValueError:
        raise ContentError(f'{where}: <note> must hold a note name, not {text!r}') from None


def paragraph(element: ET.Element, where: str) -> Paragraph:
    """Inline content: text with ``<em>``, ``<term ref="…">`` and ``<note>``."""
    parts: list[Inline] = []

    def add_text(text: str | None) -> None:
        if text:
            parts.append(Text(text))

    add_text(element.text)
    for child in element:
        if child.tag == 'em':
            parts.append(Emphasis(text_of(child)))
        elif child.tag == 'term':
            ref = child.get('ref')
            if not ref:
                raise ContentError(f'{where}: <term> needs a ref attribute')
            parts.append(TermRef(text_of(child), ref))
        elif child.tag == 'note':
            parts.append(NoteRef(_note(text_of(child), where)))
        else:
            raise ContentError(f'{where}: <{child.tag}> is not allowed inside <{element.tag}>')
        add_text(child.tail)
    return _collapse(parts)


def _collapse(parts: list[Inline]) -> Paragraph:
    """Collapse whitespace across inline boundaries and trim the ends."""
    result: list[Inline] = []
    for part in parts:
        if isinstance(part, Text):
            text = ' '.join(part.text.split())
            if part.text[:1].isspace():
                text = ' ' + text
            if part.text[-1:].isspace() and text.strip():
                text += ' '
            if result and isinstance(result[-1], Text):
                result[-1] = Text(result[-1].text + text)
            elif text:
                result.append(Text(text))
        else:
            result.append(part)
    if result and isinstance(result[0], Text):
        result[0] = Text(result[0].text.lstrip())
    if result and isinstance(result[-1], Text):
        result[-1] = Text(result[-1].text.rstrip())
    return tuple(p for p in result if not (isinstance(p, Text) and not p.text))


def required(element: ET.Element, attribute: str, where: str) -> str:
    value = element.get(attribute)
    if value is None or not value.strip():
        raise ContentError(f'{where}: <{element.tag}> needs a {attribute} attribute')
    return value.strip()


def child(element: ET.Element, tag: str, where: str) -> ET.Element:
    found = element.find(tag)
    if found is None:
        raise ContentError(f'{where}: <{element.tag}> needs a <{tag}>')
    return found
