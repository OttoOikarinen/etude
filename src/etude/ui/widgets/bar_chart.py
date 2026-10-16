# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""A small vertical bar chart drawn with ``Gtk.Snapshot`` (design 1h)."""

from __future__ import annotations

from collections.abc import Sequence
from gettext import gettext as _

from gi.repository import Adw, Graphene, Gsk, Gtk, Pango


class BarChart(Gtk.Widget):
    """Bars with a value above and a label below each; the last bar is highlighted.

    Colours come from the accent colour and the widget's foreground colour, so
    the chart follows the accent colour and dark style. Screen readers get the
    numbers as text (the widget is an image with a full description).
    """

    __gtype_name__ = 'EtudeBarChart'

    def __init__(self, title: str = '', **kwargs: object) -> None:
        super().__init__(accessible_role=Gtk.AccessibleRole.IMG, hexpand=True, **kwargs)
        self.add_css_class('bar-chart')
        self._title = title
        self._data: list[tuple[str, int]] = []
        style = Adw.StyleManager.get_default()
        style.connect('notify::accent-color-rgba', lambda *_a: self.queue_draw())
        style.connect('notify::dark', lambda *_a: self.queue_draw())

    def set_data(self, data: Sequence[tuple[str, int]]) -> None:
        self._data = list(data)
        parts = [
            # Translators: one bar of a chart for screen readers, e.g. "Mon: 32".
            _('{label}: {value}').format(label=label, value=value)
            for label, value in self._data
        ]
        description = f'{self._title}. ' + ', '.join(parts) if self._title else ', '.join(parts)
        self.update_property([Gtk.AccessibleProperty.LABEL], [description])
        self.queue_draw()

    def do_measure(self, orientation: Gtk.Orientation, for_size: int) -> tuple[int, int, int, int]:
        if orientation == Gtk.Orientation.HORIZONTAL:
            return max(1, len(self._data)) * 28, max(1, len(self._data)) * 56, -1, -1
        return 140, 180, -1, -1

    def _layout(self, text: str, small: bool = True) -> Pango.Layout:
        layout = self.create_pango_layout(text)
        if small:
            attrs = Pango.AttrList()
            attrs.insert(Pango.attr_scale_new(0.85))
            layout.set_attributes(attrs)
        return layout

    def _text(self, snapshot: Gtk.Snapshot, text: str, cx: float, y: float, color) -> None:
        layout = self._layout(text)
        width, _height = layout.get_pixel_size()
        snapshot.save()
        snapshot.translate(Graphene.Point().init(cx - width / 2, y))
        snapshot.append_layout(layout, color)
        snapshot.restore()

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        if not self._data:
            return
        width, height = self.get_width(), self.get_height()
        foreground = self.get_color()
        dim = foreground.copy()
        dim.alpha *= 0.7
        accent = Adw.StyleManager.get_default().get_accent_color_rgba()
        muted = accent.copy()
        muted.alpha = 0.45
        _w, text_height = self._layout('0').get_pixel_size()
        top, bottom = text_height + 4, height - text_height - 6
        slot = width / len(self._data)
        bar_width = min(36.0, slot * 0.6)
        peak = max(value for _label, value in self._data) or 1
        for index, (label, value) in enumerate(self._data):
            cx = slot * index + slot / 2
            bar_height = max(2.0, (bottom - top) * value / peak)
            rect = Graphene.Rect().init(
                cx - bar_width / 2, bottom - bar_height, bar_width, bar_height
            )
            rounded = Gsk.RoundedRect()
            radius = Graphene.Size().init(4, 4)
            zero = Graphene.Size().init(0, 0)
            rounded.init(rect, radius, radius, zero, zero)
            snapshot.push_rounded_clip(rounded)
            last = index == len(self._data) - 1
            snapshot.append_color(accent if last else muted, rect)
            snapshot.pop()
            self._text(snapshot, str(value), cx, bottom - bar_height - text_height - 2, dim)
            self._text(snapshot, label, cx, bottom + 4, foreground if last else dim)
