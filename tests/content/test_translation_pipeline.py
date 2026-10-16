# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The content translation pipeline end to end: xgettext extracts with the ITS
rules, itstool merges a translation, and the loader picks it."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from etude.content.library import content_dir
from etude.content.loaders import parse_lesson, read
from etude.content.model import NoteRef, ParagraphBlock, TermRef

TOOLS = ('xgettext', 'msgfmt', 'itstool')
CONTENT = content_dir()
LESSON = CONTENT / 'lessons' / 'level1' / 'staff.xml'
PARAGRAPH = (
    'Notes are named with the first seven letters of the alphabet. After <note>G</note> '
    'the letters start again from <note>A</note>; the next note with the same letter is '
    'an <term ref="octave">octave</term> higher.'
)
TRANSLATED = (
    'Sävelet nimetään aakkosten kirjaimilla. Sävelen <note>G</note> jälkeen aloitetaan '
    'alusta sävelestä <note>A</note>; seuraava samanniminen sävel on '
    '<term ref="octave">oktaavin</term> ylempänä.'
)

pytestmark = pytest.mark.skipif(
    any(shutil.which(t) is None for t in TOOLS), reason='gettext and itstool are needed'
)


def run(*args: str, cwd: Path) -> str:
    env = {**os.environ, 'GETTEXTDATADIRS': str(CONTENT)}
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout


def po_string(text: str) -> str:
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def test_extract_merge_and_load(tmp_path: Path) -> None:
    run('xgettext', '--from-code=UTF-8', '-o', 'content.pot', str(LESSON), cwd=tmp_path)
    pot = (tmp_path / 'content.pot').read_text()
    # Whole paragraphs with their inline markup are one message; note names stay.
    assert 'first seven letters' in pot
    assert '<note>G</' in pot
    (tmp_path / 'fi.po').write_text(
        'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
        f'msgid "Staff, Clefs and Note Names"\nmsgstr "Nuottiviivasto ja avaimet"\n\n'
        f'msgid {po_string(PARAGRAPH)}\nmsgstr {po_string(TRANSLATED)}\n'
    )
    run('msgfmt', '-o', 'fi.mo', 'fi.po', cwd=tmp_path)
    its = CONTENT / 'its' / 'etude.its'
    run('itstool', '-i', str(its), '-j', str(LESSON), '-o', 'staff.xml', 'fi.mo', cwd=tmp_path)

    finnish = parse_lesson(read(tmp_path / 'staff.xml', ('fi_FI', 'fi')), 'staff.xml')
    assert finnish.title == 'Nuottiviivasto ja avaimet'
    block = finnish.sections[0].blocks[3]
    assert isinstance(block, ParagraphBlock)
    assert any(isinstance(i, NoteRef) for i in block.content)
    assert TermRef('oktaavin', 'octave') in block.content

    english = parse_lesson(read(tmp_path / 'staff.xml', ()), 'staff.xml')
    assert english.title == 'Staff, Clefs and Note Names'
    assert english == parse_lesson(read(LESSON, ()), 'staff.xml')
