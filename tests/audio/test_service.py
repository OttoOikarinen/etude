# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import ctypes.util
import logging
from pathlib import Path

import pytest

from etude import paths
from etude.audio import service
from etude.audio.fluidsynth import Library, LibraryNotFoundError, find_library
from etude.audio.null import NullBackend


def test_soundfont_path_defaults_to_bundled_file() -> None:
    assert service.soundfont_path({}) == paths.data_file('soundfonts', 'GeneralUser-GS.sf2')
    assert service.soundfont_path({'ETUDE_SOUNDFONT': '/x/y.sf2'}) == Path('/x/y.sf2')


def test_falls_back_to_null_backend_without_library(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    environ = {
        'ETUDE_FLUIDSYNTH_LIB': str(tmp_path / 'libmissing.so'),
        'ETUDE_SOUNDFONT': str(tmp_path / 'missing.sf2'),
    }
    with caplog.at_level(logging.WARNING, logger='etude.audio.service'):
        backend = service.create_backend(environ)
    assert isinstance(backend, NullBackend)
    assert not backend.available
    assert 'cannot load FluidSynth' in caplog.text


def test_unexpected_errors_also_fall_back(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(*_args: object, **_kwargs: object) -> None:
        raise ZeroDivisionError

    monkeypatch.setattr(service, 'FluidSynthBackend', broken)
    with caplog.at_level(logging.ERROR, logger='etude.audio.service'):
        assert isinstance(service.create_backend({}), NullBackend)
    assert 'failed to start' in caplog.text


def test_library_errors(tmp_path: Path) -> None:
    assert find_library(tmp_path / 'lib.so') == str(tmp_path / 'lib.so')
    assert 'fluidsynth' in find_library()
    with pytest.raises(LibraryNotFoundError, match='cannot load'):
        Library(tmp_path / 'lib.so')
    # A real shared library that is not FluidSynth.
    libc = ctypes.util.find_library('c')
    if libc is not None:
        with pytest.raises(LibraryNotFoundError, match='lacks'):
            Library(libc)
