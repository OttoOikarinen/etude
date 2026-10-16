# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Drives an :class:`ExercisePage` with the W1 stub session.

STUB FOR W1: W2 replaces :class:`PreviewExerciseController` with a controller
that builds sessions with the learning engine, grades with the exercise
definitions, plays audio and records outcomes. The page API stays the same.
"""

from __future__ import annotations

from collections.abc import Callable
from gettext import ngettext

from gi.repository import Adw

from .dialogs.session_summary import (
    RESPONSE_AGAIN,
    RESPONSE_REVIEW,
    create_session_summary_dialog,
)
from .pages.exercise import ExercisePage
from .preview import PreviewSession


class PreviewExerciseController:
    def __init__(
        self,
        page: ExercisePage,
        session: PreviewSession,
        on_finished: Callable[[str], None],
    ) -> None:
        """``on_finished(response)`` is called with the summary dialog's response."""
        self.page = page
        self.session = session
        self.on_finished = on_finished
        self.played: list[object] = []
        """Playbacks requested so far (W1 has no audio)."""
        page.connect('answered', self._on_answered)
        page.connect('next-requested', lambda _p: self.next())
        page.connect('skip-requested', lambda _p: self.next())
        page.connect('play-requested', lambda _p, spec: self.played.append(spec))
        self.show_current()

    def show_current(self) -> None:
        item = self.session.current
        self.page.show_question(
            item.question,
            number=self.session.number,
            total=self.session.total,
            settings_text=item.settings_text,
            play_label=item.play_label,
        )
        self.page.set_stats(self.session.streak, self.session.best_today, self.session.accuracy)

    def _on_answered(self, page: ExercisePage, value: object) -> None:
        feedback = self.session.answer(value)
        page.show_feedback(feedback, value, play_label=self.session.current.play_label)
        page.set_stats(
            self.session.streak,
            self.session.best_today,
            self.session.accuracy,
            streak_reset=not feedback.correct,
        )

    def next(self) -> None:
        if self.session.advance():
            self.show_current()
        else:
            self.finish()

    def finish(self) -> Adw.AlertDialog:
        item = self.session.current
        total = self.session.total
        questions = ngettext('{n} question', '{n} questions', total).format(n=total)
        subtitle = ' · '.join(p for p in (item.exercise_title, questions, item.settings_text) if p)
        dialog = create_session_summary_dialog(self.session.summary(), subtitle)
        dialog.connect('response', self._on_response)
        dialog.present(self.page)
        return dialog

    def _on_response(self, _dialog: Adw.AlertDialog, response: str) -> None:
        if response in (RESPONSE_AGAIN, RESPONSE_REVIEW):
            self.session = PreviewSession(self.session.keys, start=1, total=self.session.total)
            self.show_current()
        self.on_finished(response)
