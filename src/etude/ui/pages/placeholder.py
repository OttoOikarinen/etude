# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Status pages for sections that later waves build (Today, Path, Theory, Glossary)."""

from __future__ import annotations

from gi.repository import Adw


def create_placeholder_page(tag: str, title: str, icon_name: str, description: str):
    """An ``AdwNavigationPage`` with a header bar and an ``AdwStatusPage``."""
    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())
    toolbar.set_content(Adw.StatusPage(title=title, icon_name=icon_name, description=description))
    return Adw.NavigationPage(title=title, tag=tag, child=toolbar)
