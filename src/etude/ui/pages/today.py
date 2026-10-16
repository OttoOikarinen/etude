# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Today page: the daily review of due items, the daily goal and the streak.

Spaced repetition happens here (``docs/PEDAGOGY.md``): one button starts an
interleaved review of everything due across all exercises, plus the few new
items the learner may meet today. When nothing is waiting the page says so
plainly and points to the exercises instead.
"""

from __future__ import annotations

from gettext import gettext as _
from gettext import ngettext

from gi.repository import Adw, GObject, Gtk

from ..common import ui_resource
from ..model import DueExercise, TodayData


def due_text(count: int) -> str:
    # Translators: the Today page's headline, e.g. "24 items due".
    return ngettext('{n} item due', '{n} items due', count).format(n=count)


def new_text(count: int) -> str:
    return ngettext('{n} new item to learn', '{n} new items to learn', count).format(n=count)


def held_back_text() -> str:
    # Translators: 85% is the accuracy target of the learning engine.
    return _('New items return when your recent accuracy reaches 85%')


def review_detail(data: TodayData) -> str:
    """The line under the headline, e.g. "5 new items to learn · 20 questions per session"."""
    parts = []
    if data.due == 0:
        parts.append(_('No reviews are due'))
    elif data.new:
        parts.append(new_text(data.new))
    if data.new_held_back:
        parts.append(held_back_text())
    if data.due:
        parts.append(
            ngettext(
                '{n} question per session', '{n} questions per session', data.session_size
            ).format(n=data.session_size)
        )
    return ' · '.join(parts)


def goal_detail(data: TodayData) -> str:
    if data.goal_met:
        return _('Today’s goal is met')
    left = data.daily_goal - data.answered_today
    # Translators: e.g. "12 more questions to reach today’s goal".
    return ngettext(
        '{n} more question to reach today’s goal',
        '{n} more questions to reach today’s goal',
        left,
    ).format(n=left)


def streak_detail(data: TodayData) -> str:
    if data.goal_met:
        return _('Today counts towards your streak')
    if data.streak:
        # Translators: e.g. "Meet today’s goal to make it 13 days".
        return ngettext(
            'Meet today’s goal to make it {n} day',
            'Meet today’s goal to make it {n} days',
            data.streak + 1,
        ).format(n=data.streak + 1)
    return _('Meet the daily goal to start a streak')


@Gtk.Template(resource_path=ui_resource('pages/today.ui'))
class TodayPage(Adw.NavigationPage):
    """Signals: ``start-review``, ``exercise-activated(exercise_id)`` and ``browse-requested``."""

    __gtype_name__ = 'EtudeTodayPage'
    __gsignals__ = {  # noqa: RUF012 (GObject API)
        'start-review': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'exercise-activated': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        'browse-requested': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    hero_stack: Gtk.Stack = Gtk.Template.Child()
    review_box: Gtk.Box = Gtk.Template.Child()
    review_icon: Gtk.Image = Gtk.Template.Child()
    due_label: Gtk.Label = Gtk.Template.Child()
    review_detail: Gtk.Label = Gtk.Template.Child()
    start_button: Gtk.Button = Gtk.Template.Child()
    caught_up_detail: Gtk.Label = Gtk.Template.Child()
    browse_button: Gtk.Button = Gtk.Template.Child()
    stats_box: Gtk.Box = Gtk.Template.Child()
    goal_number: Gtk.Label = Gtk.Template.Child()
    goal_bar: Gtk.LevelBar = Gtk.Template.Child()
    goal_icon: Gtk.Image = Gtk.Template.Child()
    goal_detail: Gtk.Label = Gtk.Template.Child()
    streak_number: Gtk.Label = Gtk.Template.Child()
    streak_detail: Gtk.Label = Gtk.Template.Child()
    due_group: Adw.PreferencesGroup = Gtk.Template.Child()

    compact = GObject.Property(type=bool, default=False)

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.data: TodayData | None = None
        self._due_rows: list[Adw.ActionRow] = []
        for name in ('low', 'high', 'full'):
            self.goal_bar.remove_offset_value(name)
        self.connect('notify::compact', lambda *_a: self._apply_compact())

    def _apply_compact(self) -> None:
        if self.compact:
            self.add_css_class('compact')
        else:
            self.remove_css_class('compact')
        vertical = Gtk.Orientation.VERTICAL
        self.review_box.set_orientation(vertical if self.compact else Gtk.Orientation.HORIZONTAL)
        self.stats_box.set_orientation(vertical if self.compact else Gtk.Orientation.HORIZONTAL)
        self.stats_box.set_homogeneous(not self.compact)  # equal heights side by side
        self.start_button.set_halign(Gtk.Align.FILL if self.compact else Gtk.Align.CENTER)
        self.review_icon.set_visible(not self.compact)

    # Data ---------------------------------------------------------------------------

    def set_data(self, data: TodayData) -> None:
        self.data = data
        if data.caught_up:
            self.hero_stack.set_visible_child_name('caught-up')
            if data.new_held_back:
                text = _(
                    'Nothing is due for review. New items return when your recent accuracy '
                    'reaches 85% — practising an exercise gets you there.'
                )
            else:
                text = _(
                    'Nothing is due for review. Practise an exercise to keep going, '
                    'or come back tomorrow.'
                )
            self.caught_up_detail.set_label(text)
        else:
            self.hero_stack.set_visible_child_name('review')
            self.due_label.set_label(due_text(data.due) if data.due else new_text(data.new))
            self.review_detail.set_label(review_detail(data))
            self.start_button.set_label(_('_Start Review') if data.due else _('_Learn New Items'))
        self._set_goal(data)
        self._set_due_rows(data.by_exercise)

    def _set_goal(self, data: TodayData) -> None:
        # Translators: progress towards the daily goal, e.g. "18 of 30".
        self.goal_number.set_label(
            _('{answered} of {goal}').format(answered=data.answered_today, goal=data.daily_goal)
        )
        goal = max(1, data.daily_goal)
        self.goal_bar.set_max_value(goal)
        self.goal_bar.set_value(min(data.answered_today, goal))
        if data.goal_met:
            self.goal_bar.add_css_class('goal-met')
        else:
            self.goal_bar.remove_css_class('goal-met')
        self.goal_icon.set_visible(data.goal_met)
        self.goal_detail.set_label(goal_detail(data))
        self.goal_bar.update_property(
            [Gtk.AccessibleProperty.VALUE_TEXT],
            [f'{self.goal_number.get_label()}. {goal_detail(data)}'],
        )
        self.streak_number.set_label(str(data.streak))
        self.streak_detail.set_label(streak_detail(data))

    def _set_due_rows(self, exercises: tuple[DueExercise, ...]) -> None:
        for row in self._due_rows:
            self.due_group.remove(row)
        self._due_rows = []
        for exercise in exercises:
            row = Adw.ActionRow(title=exercise.title, activatable=True)
            tile = Gtk.Label(
                label=exercise.glyph,
                valign=Gtk.Align.CENTER,
                accessible_role=Gtk.AccessibleRole.PRESENTATION,
            )
            tile.add_css_class('icon-tile')
            tile.add_css_class('small')
            row.add_prefix(tile)
            # Translators: number of due items of one exercise, e.g. "6 due".
            count = Gtk.Label(
                label=ngettext('{n} due', '{n} due', exercise.due).format(n=exercise.due)
            )
            count.add_css_class('numeric')
            count.add_css_class('dim-label')
            row.add_suffix(count)
            row.add_suffix(
                Gtk.Image(
                    icon_name='go-next-symbolic', accessible_role=Gtk.AccessibleRole.PRESENTATION
                )
            )
            row.connect('activated', self._on_row_activated, exercise.exercise_id)
            self.due_group.add(row)
            self._due_rows.append(row)
        self.due_group.set_visible(bool(exercises))

    # Signal handlers ----------------------------------------------------------------

    def _on_row_activated(self, _row: Adw.ActionRow, exercise_id: str) -> None:
        self.emit('exercise-activated', exercise_id)

    @Gtk.Template.Callback()
    def _on_start_clicked(self, _button: Gtk.Button) -> None:
        self.emit('start-review')

    @Gtk.Template.Callback()
    def _on_browse_clicked(self, _button: Gtk.Button) -> None:
        self.emit('browse-requested')
