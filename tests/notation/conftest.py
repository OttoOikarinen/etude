# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared fixtures for the notation tests."""

from __future__ import annotations

import pytest

from etude.notation.smufl import FontMetrics


@pytest.fixture(scope='session')
def metrics() -> FontMetrics:
    return FontMetrics.bravura()
