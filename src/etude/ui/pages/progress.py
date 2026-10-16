# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Statistics (design 1h): streak, accuracy, time, per-exercise accuracy,
questions answered per day, and the weakest items."""

from __future__ import annotations

from collections.abc import Callable
from gettext import gettext as _
from gettext import ngettext

from gi.repository import Adw, GObject, Gtk

from ..common import format_percent, ui_resource
from ..model import ProgressData
from ..widgets.bar_chart import BarChart


def _stat_card(title: str, value: str, detail: str) -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box.add_css_class('card')
    box.add_css_class('stat-card')
    caption = Gtk.Label(label=title, xalign=0)
    caption.add_css_class('dim-label')
    box.append(caption)
    number = Gtk.Label(label=value, xalign=0)
    number.add_css_class('title-1')
    number.add_css_class('numeric')
    box.append(number)
    extra = Gtk.Label(label=detail, xalign=0, wrap=True)
    extra.add_css_class('caption')
    extra.add_css_class('dim-label')
    box.append(extra)
    return box


def format_minutes(minutes: int) -> str:
    hours, rest = divmod(minutes, 60)
    if hours:
        # Translators: practice time, e.g. "2 h 48".
        return _('{hours} h {minutes:02d}').format(hours=hours, minutes=rest)
    return _('{minutes} min').format(minutes=rest)


@Gtk.Template(resource_path=ui_resource('pages/progress.ui'))
class ProgressPage(Adw.NavigationPage):
    """Signals: ``drill-requested(item_ids: tuple)``, ``period-changed(period: str)``.

    The page asks for the data of a period through :attr:`data_source`
    (:meth:`etude.ui.model.AppModel.progress`).
    """

    __gtype_name__ = 'EtudeProgressPage'
    __gsignals__ = {  # noqa: RUF012 (GObject API)
        'drill-requested': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    period_group: Adw.ToggleGroup = Gtk.Template.Child()
    stat_cards: Gtk.FlowBox = Gtk.Template.Child()
    charts_box: Gtk.Box = Gtk.Template.Child()
    accuracy_grid: Gtk.Grid = Gtk.Template.Child()
    chart_slot: Adw.Bin = Gtk.Template.Child()
    weakest_group: Adw.PreferencesGroup = Gtk.Template.Child()
    drill_button: Gtk.Button = Gtk.Template.Child()

    compact = GObject.Property(type=bool, default=False)

    def __init__(self, data_source: Callable[[str], ProgressData], **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.data_source = data_source
        self.data: ProgressData | None = None
        self.chart = BarChart(_('Questions answered'))
        self.chart_slot.set_child(self.chart)
        self._weak_rows: list[Gtk.Widget] = []
        self.connect('notify::compact', lambda *_a: self._apply_compact())
        self.set_data(data_source('week'))

    def _apply_compact(self) -> None:
        self.charts_box.set_orientation(
            Gtk.Orientation.VERTICAL if self.compact else Gtk.Orientation.HORIZONTAL
        )

    @property
    def period(self) -> str:
        """``'week'``, ``'month'`` or ``'all'``."""
        return self.period_group.get_active_name() or 'week'

    def set_data(self, data: ProgressData) -> None:
        self.data = data
        self.stat_cards.remove_all()
        week = self.period_group.get_active_name() == 'week'
        cards = (
            _stat_card(
                _('Day streak'),
                str(data.streak),
                ngettext('Longest {n} day', 'Longest {n} days', data.longest_streak).format(
                    n=data.longest_streak
                ),
            ),
            _stat_card(
                _('Accuracy this week') if week else _('Accuracy'),
                format_percent(data.accuracy),
                self._change_text(data.accuracy_change, week),
            ),
            _stat_card(
                _('Time practised'),
                format_minutes(data.minutes),
                ngettext('Across {n} session', 'Across {n} sessions', data.sessions).format(
                    n=data.sessions
                ),
            ),
        )
        for card in cards:
            self.stat_cards.append(card)
            card.get_parent().set_focusable(False)

        child = self.accuracy_grid.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self.accuracy_grid.remove(child)
            child = following
        for row, (title, accuracy) in enumerate(data.by_exercise):
            label = Gtk.Label(label=title, xalign=0, ellipsize=3)
            bar = Gtk.LevelBar(value=accuracy, hexpand=True, valign=Gtk.Align.CENTER)
            bar.remove_offset_value('low')
            bar.remove_offset_value('high')
            bar.remove_offset_value('full')
            bar.add_css_class('accuracy-bar')
            bar.update_property([Gtk.AccessibleProperty.LABEL], [title])
            percent = Gtk.Label(label=format_percent(accuracy), xalign=1, width_chars=4)
            percent.add_css_class('numeric')
            self.accuracy_grid.attach(label, 0, row, 1, 1)
            self.accuracy_grid.attach(bar, 1, row, 1, 1)
            self.accuracy_grid.attach(percent, 2, row, 1, 1)

        self.chart.set_data(data.answered)

        for row in self._weak_rows:
            self.weakest_group.remove(row)
        self._weak_rows = []
        for item in data.weakest:
            row = Adw.ActionRow(title=item.title)
            percent = Gtk.Label(label=format_percent(item.accuracy))
            percent.add_css_class('numeric')
            percent.add_css_class('weak-percent')
            row.add_suffix(percent)
            self.weakest_group.add(row)
            self._weak_rows.append(row)
        self.drill_button.set_label(
            ngettext('Drill this {n} item', 'Drill these {n} items', data.drill_count).format(
                n=data.drill_count
            )
        )

    @staticmethod
    def _change_text(change: int, week: bool) -> str:
        sign = '+' if change >= 0 else '−'
        if week:
            # Translators: e.g. "+4 points vs. last week".
            text = ngettext(
                '{sign}{n} point vs. last week', '{sign}{n} points vs. last week', abs(change)
            )
        else:
            text = ngettext(
                '{sign}{n} point vs. the previous period',
                '{sign}{n} points vs. the previous period',
                abs(change),
            )
        return text.format(sign=sign, n=abs(change))

    @Gtk.Template.Callback()
    def _on_period_changed(self, group: Adw.ToggleGroup, _pspec: GObject.ParamSpec) -> None:
        name = group.get_active_name()
        if name and hasattr(self, 'data_source'):
            self.set_data(self.data_source(name))

    @Gtk.Template.Callback()
    def _on_drill_clicked(self, _button: Gtk.Button) -> None:
        if self.data is not None:
            self.emit('drill-requested', tuple(i.item_id for i in self.data.weakest))
