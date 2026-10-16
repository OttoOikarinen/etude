# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The shipped content loads, is consistent, and the loaders reject bad files."""

from __future__ import annotations

import itertools
import shutil
import subprocess
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from etude.content.library import ContentLibrary, content_dir
from etude.content.loaders import parse_curriculum, parse_glossary, parse_lesson
from etude.content.model import Check, Example, NoteRef, WorkedExample
from etude.content.xml import ContentError
from etude.notation.spec import Clef, StaffSpec, SystemSpec

CONTENT = content_dir()


@pytest.fixture(scope='module')
def library() -> ContentLibrary:
    return ContentLibrary.load(CONTENT)


def test_shipped_content_loads(library: ContentLibrary) -> None:
    levels = library.curriculum.levels
    assert levels[0].number == 1
    assert levels[0].units[0].id == 'l1.staff'
    assert 'l1.staff' in library.lessons
    assert 'treble-clef' in library.glossary


def test_units_require_the_previous_unit_by_default(library: ContentLibrary) -> None:
    units = library.curriculum.levels[0].units
    assert units[0].requires == ()
    for previous, unit in itertools.pairwise(units):
        assert unit.requires == (previous.id,)


def test_reference_lesson_structure(library: ContentLibrary) -> None:
    lesson = library.lessons['l1.staff']
    blocks = [b for s in lesson.sections for b in s.blocks]
    assert any(isinstance(b, WorkedExample) for b in blocks)
    checks = lesson.checks
    assert [c.id for c in checks] == ['middle-line', 'bass-top-line', 'middle-c']
    assert checks[0].answer == 'b'
    middle_c = next(
        b for b in blocks if isinstance(b, Example) and isinstance(b.figure, SystemSpec)
    )
    assert [s.clef for s in middle_c.figure.staves] == [Clef.TREBLE, Clef.BASS]
    assert middle_c.playback is not None
    assert {n.midi for n in middle_c.playback.notes} == {60}


def test_check_figures_do_not_name_their_answer(library: ContentLibrary) -> None:
    """Screen readers read figure descriptions: a check's figure must describe the
    staff without the note it asks about (set <description>)."""
    for lesson in library.lessons.values():
        for check in lesson.checks:
            if check.example is None:
                continue
            assert isinstance(check.example.figure, StaffSpec | SystemSpec)
            assert check.example.figure.description, f'{lesson.id}/{check.id} needs <description>'


def test_vocabulary_of_a_unit(library: ContentLibrary) -> None:
    unit = library.curriculum.unit('l1.staff')
    ids = {e.id for e in library.vocabulary(unit)}
    assert {'staff', 'clef', 'treble-clef', 'bass-clef', 'ledger-line'} <= ids
    assert 'crescendo' not in ids


def test_foreign_terms(library: ContentLibrary) -> None:
    entry = library.glossary['crescendo']
    assert entry.foreign == 'crescendo'
    assert entry.foreign_language == 'it'
    assert entry.abbreviation == 'cresc.'
    assert entry.headword == 'crescendo'
    assert library.glossary['staff'].headword == 'staff'


def test_glossary_notes_are_note_refs(library: ContentLibrary) -> None:
    definition = library.glossary['treble-clef'].definition
    assert any(isinstance(i, NoteRef) for i in definition)


def test_schemas_validate_the_shipped_content() -> None:
    xmllint = shutil.which('xmllint')
    if xmllint is None:
        pytest.skip('xmllint is not installed')
    schemas = {'lessons': 'lesson', 'glossary': 'glossary'}
    files = [
        CONTENT / 'curriculum.xml',
        *CONTENT.glob('lessons/*/*.xml'),
        *CONTENT.glob('glossary/*.xml'),
    ]
    for path in files:
        kind = (
            'curriculum'
            if path.name == 'curriculum.xml'
            else schemas[path.relative_to(CONTENT).parts[0]]
        )
        result = subprocess.run(
            [xmllint, '--noout', '--relaxng', str(CONTENT / 'schema' / f'{kind}.rng'), str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


# Broken content ------------------------------------------------------------------------


def lesson(body: str) -> ET.Element:
    return ET.fromstring(f'<lesson id="l1.x"><title>T</title>{body}</lesson>')


@pytest.mark.parametrize(
    ('body', 'message'),
    [
        ('', 'at least one <section>'),
        ('<section><title>S</title><table/></section>', 'not a lesson block'),
        ('<section><title>S</title><figure/></section>', 'at least one <staff>'),
        (
            '<section><title>S</title><figure><staff clef="soprano">C4</staff></figure></section>',
            'unknown clef',
        ),
        ('<section><title>S</title><figure><staff>C4/z</staff></figure></section>', 'C4/z'),
        (
            '<section><title>S</title><figure play="loud"><staff>C4</staff></figure></section>',
            'play must be',
        ),
        (
            '<section><title>S</title><check id="c"><prompt>Q</prompt>'
            '<option key="a">x</option><option key="b">y</option></check></section>',
            'one correct',
        ),
        (
            '<section><title>S</title><check id="c"><prompt>Q</prompt>'
            '<option key="a" correct="true">x</option><option key="a">y</option></check></section>',
            'repeats an option key',
        ),
        ('<section><title>S</title><worked><title>W</title></worked></section>', '<step>'),
        ('<section><p>No title</p></section>', '<title>'),
    ],
)
def test_bad_lessons(body: str, message: str) -> None:
    with pytest.raises(ContentError, match=message):
        parse_lesson(lesson(body), 'bad.xml')


def test_bad_glossary_entries() -> None:
    with pytest.raises(ContentError, match='level'):
        parse_glossary(
            ET.fromstring(
                '<glossary><entry id="x" level="one"><term>x</term><gloss>g</gloss>'
                '<def>d</def></entry></glossary>'
            ),
            'g.xml',
        )
    with pytest.raises(ContentError, match='<gloss>'):
        parse_glossary(
            ET.fromstring(
                '<glossary><entry id="x" level="1"><term>x</term><def>d</def></entry></glossary>'
            ),
            'g.xml',
        )


def write_tree(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text).strip())


CURRICULUM = """
    <curriculum><level id="level1" number="1"><title>L</title>
      <unit id="l1.a" lesson="l1.a"><title>A</title></unit>
      <unit id="l1.b"><title>B</title><requires unit="{required}"/></unit>
    </level></curriculum>
"""
LESSON = """
    <lesson id="l1.a"><title>A</title>
      <section><title>S</title><p>See <term ref="{term}">it</term>.</p></section>
    </lesson>
"""
GLOSSARY = """
    <glossary><entry id="staff" level="1"><term>staff</term><gloss>g</gloss><def>d</def>
      <see ref="{see}"/></entry></glossary>
"""


@pytest.mark.parametrize(
    ('required', 'term', 'see', 'lesson_file', 'message'),
    [
        ('l1.zz', 'staff', 'staff', True, 'requires unknown unit'),
        ('l1.a', 'nothing', 'staff', True, 'unknown glossary term'),
        ('l1.a', 'staff', 'nothing', True, 'unknown term'),
        ('l1.a', 'staff', 'staff', False, 'missing lesson'),
    ],
)
def test_broken_references(
    tmp_path: Path, required: str, term: str, see: str, lesson_file: bool, message: str
) -> None:
    files = {
        'curriculum.xml': CURRICULUM.format(required=required),
        'glossary/a.xml': GLOSSARY.format(see=see),
    }
    if lesson_file:
        files['lessons/level1/a.xml'] = LESSON.format(term=term)
    write_tree(tmp_path, files)
    with pytest.raises(ContentError, match=message):
        ContentLibrary.load(tmp_path)


def test_duplicate_ids(tmp_path: Path) -> None:
    write_tree(
        tmp_path,
        {
            'curriculum.xml': CURRICULUM.format(required='l1.a'),
            'lessons/level1/a.xml': LESSON.format(term='staff'),
            'lessons/level1/b.xml': LESSON.format(term='staff'),
            'glossary/a.xml': GLOSSARY.format(see='staff'),
        },
    )
    with pytest.raises(ContentError, match='defined twice'):
        ContentLibrary.load(tmp_path)


def test_curriculum_settings_are_kept_as_text() -> None:
    root = ET.fromstring(
        '<curriculum><level id="l" number="1"><title>L</title><unit id="l1.a"><title>A</title>'
        '<practice exercise="keysig"><setting key="mode" value="minor"/></practice>'
        '<vocabulary tags="a b"/><vocabulary tags="c"/></unit><exam size="12"/>'
        '</level></curriculum>'
    )
    curriculum = parse_curriculum(root, 'c.xml')
    unit = curriculum.unit('l1.a')
    assert unit.practices[0].exercise_id == 'keysig'
    assert dict(unit.practices[0].settings) == {'mode': 'minor'}
    assert unit.vocabulary_tags == ('a', 'b', 'c')
    assert curriculum.levels[0].exam_size == 12
    assert curriculum.level_of('l1.a').id == 'l'
    with pytest.raises(KeyError):
        curriculum.unit('nope')


def test_checks_are_retrieval_questions(library: ContentLibrary) -> None:
    for lesson in library.lessons.values():
        for check in lesson.checks:
            assert isinstance(check, Check)
            assert check.explanation, f'{lesson.id}/{check.id}: explain the answer'
