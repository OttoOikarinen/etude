# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Theory page: the units' lessons by level. Reading is never locked."""

from __future__ import annotations

from gettext import gettext as _

from gi.repository import Adw, GObject, Gtk

from ..common import ui_resource
from ..model import PathData


@Gtk.Template(resource_path=ui_resource('pages/lessons.ui'))
class LessonsPage(Adw.NavigationPage):
    """Signal: ``lesson-requested(unit_id)``."""

    __gtype_name__ = 'EtudeLessonsPage'
    __gsignals__ = {  # noqa: RUF012 (GObject API)
        'lesson-requested': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    stack: Gtk.Stack = Gtk.Template.Child()
    groups_box: Gtk.Box = Gtk.Template.Child()
    coming_label: Gtk.Label = Gtk.Template.Child()

    compact = GObject.Property(type=bool, default=False)

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.rows: dict[str, Adw.ActionRow] = {}
        self._groups: list[Adw.PreferencesGroup] = []
        self.connect('notify::compact', lambda *_a: self._apply_compact())

    def _apply_compact(self) -> None:
        if self.compact:
            self.add_css_class('compact')
        else:
            self.remove_css_class('compact')

    def set_data(self, data: PathData) -> None:
        for group in self._groups:
            self.groups_box.remove(group)
        self._groups = []
        self.rows = {}
        without = 0
        for level in data.levels:
            # Translators: a group of lessons, e.g. "Level 1 · Fundamentals".
            group = Adw.PreferencesGroup(
                title=_('Level {number} · {title}').format(number=level.number, title=level.title)
            )
            for number, unit in enumerate(level.units, start=1):
                if not unit.lesson_id:
                    without += 1
                    continue
                row = Adw.ActionRow(
                    title=unit.lesson_title or unit.title,
                    subtitle=unit.lesson_summary or unit.summary,
                    activatable=True,
                    use_markup=False,
                )
                tile = Gtk.Label(
                    label=str(number),
                    valign=Gtk.Align.CENTER,
                    accessible_role=Gtk.AccessibleRole.PRESENTATION,
                )
                tile.add_css_class('icon-tile')
                tile.add_css_class('small')
                tile.add_css_class('numeric')
                row.add_prefix(tile)
                if unit.lesson_done:
                    done = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
                    icon = Gtk.Image(
                        icon_name='object-select-symbolic',
                        accessible_role=Gtk.AccessibleRole.PRESENTATION,
                    )
                    icon.add_css_class('success')
                    done.append(icon)
                    label = Gtk.Label(label=_('Completed'))
                    label.add_css_class('dim-label')
                    label.add_css_class('caption')
                    done.append(label)
                    row.add_suffix(done)
                row.add_suffix(
                    Gtk.Image(
                        icon_name='go-next-symbolic',
                        accessible_role=Gtk.AccessibleRole.PRESENTATION,
                    )
                )
                row.connect('activated', lambda _r, u=unit.id: self.emit('lesson-requested', u))
                self.rows[unit.id] = row
                group.add(row)
            if any(u.lesson_id for u in level.units):
                self.groups_box.insert_child_after(
                    group, self._groups[-1] if self._groups else None
                )
                self._groups.append(group)
        self.coming_label.set_visible(bool(self.rows) and without > 0)
        self.stack.set_visible_child_name('lessons' if self.rows else 'empty')
