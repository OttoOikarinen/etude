# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import xml.etree.ElementTree as ET

import pytest

from etude.content.model import Emphasis, NoteRef, TermRef, Text, plain_text
from etude.content.xml import ContentError, languages, localize, paragraph, text_of
from etude.core import Pitch, PitchName


@pytest.mark.parametrize(
    ('environ', 'expected'),
    [
        ({'LANGUAGE': 'fi:en_GB', 'LANG': 'de_DE.UTF-8'}, ('fi', 'en_GB', 'en')),
        ({'LANG': 'fi_FI.UTF-8'}, ('fi_FI', 'fi')),
        ({'LC_MESSAGES': 'pt_BR.utf8@euro', 'LANG': 'en_US'}, ('pt_BR', 'pt')),
        ({'LC_ALL': 'C'}, ()),
        ({}, ()),
    ],
)
def test_languages(environ: dict[str, str], expected: tuple[str, ...]) -> None:
    assert languages(environ) == expected


JOINED = """<lesson>
  <title>Intervals</title>
  <title xml:lang="de">Intervalle</title>
  <title xml:lang="fi">Intervallit</title>
  <p>One</p>
  <p xml:lang="fi">Yksi</p>
  <p>Untranslated</p>
  <p>Two</p>
  <p xml:lang="sv">Två</p>
</lesson>"""


def texts(root: ET.Element, tag: str) -> list[str]:
    return [text_of(e) for e in root.findall(tag)]


def test_localize_picks_the_best_translation_of_each_run() -> None:
    root = localize(ET.fromstring(JOINED), ('fi_FI', 'fi'))
    assert texts(root, 'title') == ['Intervallit']
    assert texts(root, 'p') == ['Yksi', 'Untranslated', 'Two']


def test_localize_keeps_the_original_without_a_match() -> None:
    root = localize(ET.fromstring(JOINED), ())
    assert texts(root, 'title') == ['Intervals']
    assert texts(root, 'p') == ['One', 'Untranslated', 'Two']


def test_localize_respects_preference_order() -> None:
    root = localize(ET.fromstring(JOINED), ('de', 'fi'))
    assert texts(root, 'title') == ['Intervalle']


def test_paragraph_inlines_and_whitespace() -> None:
    element = ET.fromstring(
        '<p>  A <em>major</em>\n   third above <note>Bb3</note> is\n'
        '<note>D4</note>, see <term ref="interval">interval</term>.  </p>'
    )
    content = paragraph(element, 'test')
    assert content == (
        Text('A '),
        Emphasis('major'),
        Text(' third above '),
        NoteRef(Pitch.parse('Bb3')),
        Text(' is '),
        NoteRef(Pitch.parse('D4')),
        Text(', see '),
        TermRef('interval', 'interval'),
        Text('.'),
    )
    assert plain_text(content) == 'A major third above B♭3 is D4, see interval.'
    named = plain_text(content, lambda note: 'X')
    assert named == 'A major third above X is X, see interval.'


def test_note_without_octave_is_a_pitch_name() -> None:
    (note,) = paragraph(ET.fromstring('<p><note>F#</note></p>'), 'test')
    assert note == NoteRef(PitchName.parse('F#'))


@pytest.mark.parametrize(
    'markup',
    ['<p><note>H</note></p>', '<p><term>x</term></p>', '<p><b>bold</b></p>'],
)
def test_bad_inline_content(markup: str) -> None:
    with pytest.raises(ContentError, match='test'):
        paragraph(ET.fromstring(markup), 'test')
