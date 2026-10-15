# paths.py
#
# Copyright 2026 Otto Oikarinen
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Locations of read-only application data (fonts, SoundFonts, content).

The installed launcher calls :func:`set_data_dir` with ``pkgdatadir``.
When the package is imported from the source tree (tests, tools), the
repository's ``data/`` directory is used instead, so the same relative
paths work in both cases: ``fonts/``, ``soundfonts/`` and ``content/``.
"""

from pathlib import Path

_SOURCE_DATA_DIR = Path(__file__).resolve().parents[2] / 'data'
_data_dir = _SOURCE_DATA_DIR


def set_data_dir(path: str | Path) -> None:
    """Point data lookups at an installed ``pkgdatadir``."""
    global _data_dir
    _data_dir = Path(path)


def data_dir() -> Path:
    """Return the directory that holds ``fonts/``, ``soundfonts/`` and ``content/``."""
    return _data_dir


def data_file(*parts: str) -> Path:
    """Return the path of a data file, e.g. ``data_file('fonts', 'Bravura.otf')``."""
    return _data_dir.joinpath(*parts)
