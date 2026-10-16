# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""UI smoke tests: every page, dialog and answer widget with the W1 stub data.

Skipped when PyGObject with GTK 4 and libadwaita 1.10, or a display, is not
available. The checks live in ``smoke.py`` so that ``meson test`` can run them
without pytest.
"""

import importlib.util
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('etude_ui_smoke', HERE / 'smoke.py')
assert _spec is not None
assert _spec.loader is not None
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)

pytestmark = pytest.mark.gtk


@pytest.fixture(scope='module', autouse=True)
def gtk_environment(tmp_path_factory: pytest.TempPathFactory) -> None:
    reason = smoke.unavailable_reason()
    if reason:
        pytest.skip(reason)
    smoke.prepare(smoke.ROOT, tmp_path_factory.mktemp('ui'))


@pytest.mark.parametrize('check', smoke.CHECKS, ids=lambda c: c.__name__.removeprefix('check_'))
def test_ui(check) -> None:
    check()
