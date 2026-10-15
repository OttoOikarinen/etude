# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""SQLite persistence for cards, attempts and sessions.

Implements the protocols of :mod:`etude.learning.ports`. The database lives
in ``GLib.get_user_data_dir()/etude/etude.db``; the schema is versioned with
``PRAGMA user_version`` and upgraded by numbered migrations."""
