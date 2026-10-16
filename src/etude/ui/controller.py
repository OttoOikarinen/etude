# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Drives an :class:`ExercisePage` with a running session.

The page renders questions and reports answers; the session (a
:class:`~etude.exercises.runner.SessionRunner`, or the design preview's
stub) grades and records them; the model plays sound. This class connects
the three and shows the summary dialog at the end (design 1i).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from gettext import gettext as _
from gettext import ngettext

from gi.repository import Adw

from ..audio.spec import PlaybackSpec
from ..exercises.runner import EmptySessionError
from ..learning.model import SessionSummary
from .dialogs.session_summary import (
    RESPONSE_AGAIN,
    RESPONSE_REVIEW,
    create_session_summary_dialog,
)
from .model import AppModel, SessionSource
from .pages.exercise import ExercisePage

log = logging.getLogger(__name__)


def questions_text(count: int) -> str:
    return ngettext('{n} question', '{n} questions', count).format(n=count)


class ExerciseController:
    def __init__(
        self,
        page: ExercisePage,
        session: SessionSource,
        model: AppModel,
        on_finished: Callable[[str], None],
    ) -> None:
        """``on_finished(response)`` is called with the summary dialog's response."""
        self.page = page
        self.session = session
        self.model = model
        self.on_finished = on_finished
        self.summary: SessionSummary | None = None
        self._hinted = False
        page.audio_available = model.audio_available
        page.connect('answered', self._on_answered)
        page.connect('next-requested', lambda _p: self.next())
        page.connect('skip-requested', lambda _p: self._on_skip())
        page.connect('hint-requested', lambda _p: self._on_hint())
        page.connect('play-requested', self._on_play_requested)
        page.connect('close-requested', lambda _p: self.model.stop_audio())
        self.show_current()

    def show_current(self) -> None:
        shown = self.session.current
        self._hinted = False
        self.model.new_question()
        self.page.show_question(
            shown.question,
            number=self.session.number,
            total=self.session.total,
            settings_text=shown.settings_text,
            play_label=shown.play_label,
        )
        self._update_stats()

    def _update_stats(self, streak_reset: bool = False) -> None:
        self.page.set_stats(
            self.session.streak,
            self.session.best_today,
            self.session.accuracy,
            streak_reset=streak_reset,
        )

    # Page signals

    def _on_answered(self, page: ExercisePage, value: object) -> None:
        feedback = self.session.answer(value, response_ms=page.response_ms, hinted=self._hinted)
        page.show_feedback(feedback, value, play_label=self.session.current.play_label)
        self._update_stats(streak_reset=not feedback.correct)

    def _on_skip(self) -> None:
        if self.page.feedback is not None:
            self.next()
            return
        self.page.stop_clock()
        feedback = self.session.skip(response_ms=self.page.response_ms)
        self.page.show_feedback(feedback, None, play_label=self.session.current.play_label)
        self._update_stats(streak_reset=True)

    def _on_hint(self) -> None:
        self._hinted = True

    def _on_play_requested(self, _page: ExercisePage, spec: PlaybackSpec) -> None:
        self.model.play(spec)

    # Flow

    def next(self) -> None:
        self.model.stop_audio()
        if self.session.advance():
            self.show_current()
        else:
            self.finish()

    def finish(self) -> Adw.AlertDialog:
        self.summary = summary = self.session.finish()
        dialog = create_session_summary_dialog(
            summary, summary_subtitle(self.session, summary), mixed=self.is_mixed
        )
        dialog.connect('response', self._on_response)
        dialog.present(self.page)
        return dialog

    @property
    def is_mixed(self) -> bool:
        """Whether the session mixes exercises (daily review, weakest items, mistakes)."""
        return self.session.title != self.session.current.exercise_title

    def _on_response(self, _dialog: Adw.AlertDialog, response: str) -> None:
        try:
            if response == RESPONSE_AGAIN:
                self._restart(self.session.again())
            elif response == RESPONSE_REVIEW and self.summary is not None:
                self._restart(self.session.review_mistakes(self.summary))
        except EmptySessionError:
            log.info('nothing to practise after %s', response)
            response = 'back'
        self.on_finished(response)

    def _restart(self, session: SessionSource) -> None:
        self.session = session
        self.summary = None
        self.page.set_title(session.title)
        self.page.window_title.set_title(session.title)
        self.page.set_elapsed(0)
        self.show_current()


def summary_subtitle(session: SessionSource, summary: SessionSummary) -> str:
    """E.g. "Key Signatures · 20 questions · Treble clef" or "Daily Review · 20 questions"."""
    shown = session.current
    parts = [session.title, questions_text(summary.total)]
    # A one-exercise session describes its settings; in mixed sessions the
    # settings text is just the exercise's title.
    if shown.settings_text and shown.settings_text != shown.exercise_title:
        parts.append(shown.settings_text)
    return ' · '.join(p for p in parts if p)


def empty_session_message() -> str:
    return _('Nothing to practise right now — come back later or pick an exercise')
