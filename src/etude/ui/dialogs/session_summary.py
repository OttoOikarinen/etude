# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The "Session complete" dialog (design 1i), built from a ``SessionSummary``."""

from __future__ import annotations

from gettext import gettext as _
from gettext import ngettext

from gi.repository import Adw, Gtk

from ...learning.model import SessionSummary
from ..common import format_duration, format_percent

RESPONSE_AGAIN = 'again'
RESPONSE_REVIEW = 'review'
RESPONSE_BACK = 'back'


def _big_number(value: str, caption: str) -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
    number = Gtk.Label(label=value)
    number.add_css_class('title-1')
    number.add_css_class('numeric')
    box.append(number)
    label = Gtk.Label(label=caption)
    label.add_css_class('dim-label')
    label.add_css_class('caption')
    box.append(label)
    return box


def create_session_summary_dialog(
    summary: SessionSummary, subtitle: str, *, mixed: bool = False
) -> Adw.AlertDialog:
    """``subtitle`` describes the session, e.g. "Key Signatures · 20 questions · treble clef";
    ``mixed`` sessions (daily review, drills) practise several exercises.

    Responses: :data:`RESPONSE_AGAIN` (suggested), :data:`RESPONSE_REVIEW` (only when
    there were mistakes) and :data:`RESPONSE_BACK`.
    """
    dialog = Adw.AlertDialog(heading=_('Session Complete'), body=subtitle)
    dialog.add_css_class('session-summary')
    accuracy = summary.correct / summary.total if summary.total else 0.0
    numbers = Gtk.Box(homogeneous=True, spacing=12)
    numbers.add_css_class('summary-numbers')
    numbers.append(_big_number(str(summary.correct), _('Correct')))
    numbers.append(_big_number(format_percent(accuracy), _('Accuracy')))
    numbers.append(_big_number(format_duration(summary.duration_ms), _('Time')))
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    content.append(numbers)
    # Translators: e.g. "Best streak 11".
    streak = _('Best streak {n}').format(n=summary.best_streak)
    if summary.personal_best:
        best = _('New personal best') if mixed else _('New personal best for this exercise')
        streak = f'{streak} · {best}'
    streak_box = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
    if summary.personal_best:
        icon = Gtk.Image(
            icon_name='starred-symbolic', accessible_role=Gtk.AccessibleRole.PRESENTATION
        )
        icon.add_css_class('accent')
        streak_box.append(icon)
    streak_label = Gtk.Label(label=streak, wrap=True, justify=Gtk.Justification.CENTER)
    streak_box.append(streak_label)
    content.append(streak_box)
    dialog.set_extra_child(content)

    dialog.add_response(RESPONSE_BACK, _('_Back to Exercises'))
    mistakes = len(summary.mistakes)
    if mistakes:
        dialog.add_response(
            RESPONSE_REVIEW,
            ngettext('_Review {n} Mistake', '_Review {n} Mistakes', mistakes).format(n=mistakes),
        )
    dialog.add_response(RESPONSE_AGAIN, _('_Practise Again'))
    dialog.set_response_appearance(RESPONSE_AGAIN, Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response(RESPONSE_AGAIN)
    dialog.set_close_response(RESPONSE_BACK)
    dialog.set_prefer_wide_layout(True)
    return dialog
