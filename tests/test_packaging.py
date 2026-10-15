# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Keep build files in step with the source tree.

Meson lists sources explicitly, so a new module that is not added to its
directory's meson.build silently disappears from the installed app. These
tests catch that, plus missing GResource and translation entries.
"""

import json
import re
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'src' / 'etude'


def meson_listed_files(directory: Path) -> set[str]:
    build = directory / 'meson.build'
    if not build.exists():
        return set()
    return set(re.findall(r"'([^']+\.py)'", build.read_text()))


def python_files() -> list[Path]:
    return sorted(p for p in PACKAGE.rglob('*.py') if '__pycache__' not in p.parts)


@pytest.mark.parametrize('path', python_files(), ids=lambda p: str(p.relative_to(PACKAGE)))
def test_python_file_is_installed(path: Path) -> None:
    assert path.name in meson_listed_files(path.parent), (
        f'add {path.name!r} to {path.parent.relative_to(ROOT)}/meson.build'
    )


def test_every_package_directory_is_built() -> None:
    for build in PACKAGE.rglob('meson.build'):
        directory = build.parent
        if directory == PACKAGE:
            continue
        parent_build = (directory.parent / 'meson.build').read_text()
        assert f"'{directory.name}'" in parent_build, (
            f'{directory.relative_to(ROOT)} is not reached by subdir() in its parent meson.build'
        )


def test_ui_files_are_in_gresource() -> None:
    tree = ET.parse(PACKAGE / 'etude.gresource.xml')
    listed = {f.text for f in tree.iter('file')}
    for path in [*PACKAGE.rglob('*.ui'), *PACKAGE.rglob('*.css')]:
        relative = str(path.relative_to(PACKAGE))
        assert relative in listed, f'add {relative} to src/etude/etude.gresource.xml'


def test_translatable_files_are_in_potfiles() -> None:
    potfiles = {
        line.strip()
        for line in (ROOT / 'po' / 'POTFILES.in').read_text().splitlines()
        if line.strip() and not line.startswith('#')
    }
    for path in [*PACKAGE.rglob('*.py'), *PACKAGE.rglob('*.ui')]:
        text = path.read_text()
        if re.search(r'\b_\(|\bngettext\(|\bpgettext\(|translatable="yes"', text):
            relative = str(path.relative_to(ROOT))
            assert relative in potfiles, f'add {relative} to po/POTFILES.in'
    for entry in potfiles:
        assert (ROOT / entry).exists(), f'po/POTFILES.in lists missing file {entry}'


def test_fsrs_pin_matches_flatpak_manifest() -> None:
    pyproject = tomllib.loads((ROOT / 'pyproject.toml').read_text())
    pin = next(d for d in pyproject['dependency-groups']['runtime'] if d.startswith('fsrs=='))
    version = pin.removeprefix('fsrs==')
    manifest = json.loads((ROOT / 'fi.oikarinenotto.etude.json').read_text())
    module = next(m for m in manifest['modules'] if m['name'] == 'python3-fsrs')
    urls = [s['url'] for s in module['sources']]
    assert any(url.endswith(f'/fsrs-{version}-py3-none-any.whl') for url in urls)
