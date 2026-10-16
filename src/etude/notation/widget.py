# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""``StaffView``: draws a notation figure with GTK.

The widget lays out its figure with :func:`etude.notation.layout.layout`
and draws the display list in ``do_snapshot``: SMuFL glyphs as Pango
layouts in Bravura (one em = four staff spaces, glyph origin on the
baseline), lines and rectangles with ``append_color`` and everything
else with GSK paths. Inks map to libadwaita colours, so notation follows
dark style and the accent colour.

:class:`Renderer` holds the drawing code without a widget, so tools such
as ``tools/notation_gallery.py`` can render figures offscreen.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Gsk', '4.0')
gi.require_version('Graphene', '1.0')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, GObject, Graphene, Gsk, Gtk, Pango, PangoCairo  # noqa: E402

from ..core import Pitch  # noqa: E402
from ..paths import data_file  # noqa: E402
from .a11y import describe  # noqa: E402
from .displaylist import (  # noqa: E402
    Align,
    BeamItem,
    CircleItem,
    CurveItem,
    DisplayList,
    GlyphItem,
    HitRegion,
    LineItem,
    TextItem,
)
from .layout import layout  # noqa: E402
from .smufl import FontMetrics  # noqa: E402
from .spec import Figure, Ink  # noqa: E402

FONT_FAMILY = 'Bravura'
DEFAULT_STAFF_SPACE = 12.0
MIN_FIT = 0.5
"""Smallest scale a figure shrinks to before the page has to scroll sideways."""

# libadwaita's standalone colours (for marks on the view background), light and dark.
_SUCCESS = ('#1b8553', '#78e9ab')
_ERROR = ('#c01c28', '#ff938c')
_DIM_ALPHA = 0.55

_font_registered: bool | None = None


def register_font() -> bool:
    """Make Bravura available to Pango (once per process)."""
    global _font_registered
    if _font_registered is None:
        fontmap = PangoCairo.FontMap.get_default()
        path = data_file('fonts', 'Bravura.otf')
        try:
            _font_registered = bool(fontmap.add_font_file(str(path)))
        except GObject.GError:
            _font_registered = False
    return _font_registered


def _rgba(spec: str, alpha: float = 1.0) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.parse(spec)
    color.alpha *= alpha
    return color


def _with_alpha(color: Gdk.RGBA, alpha: float) -> Gdk.RGBA:
    result = color.copy()
    result.alpha = color.alpha * alpha
    return result


@dataclass(frozen=True)
class Palette:
    """The colour of every :class:`Ink`, plus the background accent used for halos."""

    foreground: Gdk.RGBA
    dim: Gdk.RGBA
    accent: Gdk.RGBA
    accent_background: Gdk.RGBA
    success: Gdk.RGBA
    error: Gdk.RGBA

    def color(self, ink: Ink) -> Gdk.RGBA:
        match ink:
            case Ink.FOREGROUND:
                return self.foreground
            case Ink.DIM:
                return self.dim
            case Ink.ACCENT:
                return self.accent
            case Ink.SUCCESS:
                return self.success
            case Ink.ERROR:
                return self.error

    @classmethod
    def resolve(cls, foreground: Gdk.RGBA, *, dark: bool | None = None) -> Palette:
        """Build a palette from a foreground colour and libadwaita's style manager."""
        manager = Adw.StyleManager.get_default()
        if dark is None:
            dark = manager.get_dark()
        accent_background = manager.get_accent_color_rgba()
        accent = Adw.AccentColor.to_standalone_rgba(manager.get_accent_color(), dark)
        index = 1 if dark else 0
        return cls(
            foreground=foreground,
            dim=_with_alpha(foreground, _DIM_ALPHA),
            accent=accent,
            accent_background=accent_background,
            success=_rgba(_SUCCESS[index]),
            error=_rgba(_ERROR[index]),
        )

    @classmethod
    def light(cls) -> Palette:
        """libadwaita's light style with the default blue accent (offscreen rendering)."""
        foreground = _rgba('rgba(0, 0, 6, 0.8)')
        return cls(
            foreground=foreground,
            dim=_with_alpha(foreground, _DIM_ALPHA),
            accent=_rgba('#0461be'),
            accent_background=_rgba('#3584e4'),
            success=_rgba(_SUCCESS[0]),
            error=_rgba(_ERROR[0]),
        )

    @classmethod
    def dark(cls) -> Palette:
        """libadwaita's dark style with the default blue accent (offscreen rendering)."""
        foreground = _rgba('#ffffff')
        return cls(
            foreground=foreground,
            dim=_with_alpha(foreground, _DIM_ALPHA),
            accent=_rgba('#81d0ff'),
            accent_background=_rgba('#3584e4'),
            success=_rgba(_SUCCESS[1]),
            error=_rgba(_ERROR[1]),
        )


class Renderer:
    """Draws display lists onto a :class:`Gtk.Snapshot` with a given Pango context."""

    def __init__(self, context: Pango.Context, metrics: FontMetrics | None = None) -> None:
        register_font()
        self.context = context
        self.metrics = metrics or FontMetrics.bravura()
        self._layouts: dict[tuple[str, str, float, bool], tuple[Pango.Layout, float, float]] = {}

    def clear_cache(self) -> None:
        self._layouts.clear()

    def _layout(
        self, text: str, family: str | None, size: float, bold: bool = False
    ) -> tuple[Pango.Layout, float, float]:
        """A cached layout, its baseline and its logical width in pixels."""
        key = (text, family or '', round(size, 3), bold)
        cached = self._layouts.get(key)
        if cached is None:
            pango_layout = Pango.Layout.new(self.context)
            if family is None:
                base = self.context.get_font_description()
                description = base.copy() if base is not None else Pango.FontDescription()
            else:
                description = Pango.FontDescription.from_string(family)
            description.set_absolute_size(size * Pango.SCALE)
            if bold:
                description.set_weight(Pango.Weight.BOLD)
            pango_layout.set_font_description(description)
            pango_layout.set_text(text, -1)
            baseline = pango_layout.get_baseline() / Pango.SCALE
            _ink, logical = pango_layout.get_extents()
            cached = (pango_layout, baseline, logical.width / Pango.SCALE)
            self._layouts[key] = cached
        return cached

    def draw(
        self,
        snapshot: Gtk.Snapshot,
        display: DisplayList,
        staff_space: float,
        palette: Palette,
        *,
        focus: HitRegion | None = None,
    ) -> None:
        """Draw ``display`` with its origin at the snapshot's current origin."""
        px = staff_space
        for item in display.items:
            match item:
                case GlyphItem():
                    self._glyph(snapshot, item, px, palette)
                case LineItem():
                    self._line(snapshot, item, px, palette)
                case BeamItem():
                    self._beam(snapshot, item, px, palette)
                case CircleItem():
                    builder = Gsk.PathBuilder.new()
                    builder.add_circle(
                        Graphene.Point().init(item.cx * px, item.cy * px), item.radius * px
                    )
                    base = (
                        palette.accent_background
                        if item.ink is Ink.ACCENT
                        else palette.color(item.ink)
                    )
                    snapshot.append_fill(
                        builder.to_path(), Gsk.FillRule.WINDING, _with_alpha(base, item.alpha)
                    )
                case CurveItem():
                    self._curve(snapshot, item, px, palette)
                case TextItem():
                    self._text(snapshot, item, px, palette)
        if focus is not None:
            self._focus_ring(snapshot, focus, px, palette)

    def _glyph(self, snapshot: Gtk.Snapshot, item: GlyphItem, px: float, palette: Palette) -> None:
        codepoint = self.metrics.glyph(item.glyph).codepoint
        pango_layout, baseline, _width = self._layout(codepoint, FONT_FAMILY, 4 * px * item.scale)
        snapshot.save()
        snapshot.translate(Graphene.Point().init(item.x * px, item.y * px - baseline))
        snapshot.append_layout(pango_layout, palette.color(item.ink))
        snapshot.restore()

    def _line(self, snapshot: Gtk.Snapshot, item: LineItem, px: float, palette: Palette) -> None:
        color = palette.color(item.ink)
        half = item.thickness / 2
        if item.x1 == item.x2 or item.y1 == item.y2:
            x0, x1 = sorted((item.x1, item.x2))
            y0, y1 = sorted((item.y1, item.y2))
            if item.x1 == item.x2:
                x0, x1 = x0 - half, x1 + half
            else:
                y0, y1 = y0 - half, y1 + half
            rect = Graphene.Rect().init(x0 * px, y0 * px, (x1 - x0) * px, (y1 - y0) * px)
            snapshot.append_color(color, rect)
            return
        dx, dy = item.x2 - item.x1, item.y2 - item.y1
        length = math.hypot(dx, dy)
        nx, ny = -dy / length * half, dx / length * half
        points = [
            (item.x1 + nx, item.y1 + ny),
            (item.x2 + nx, item.y2 + ny),
            (item.x2 - nx, item.y2 - ny),
            (item.x1 - nx, item.y1 - ny),
        ]
        self._polygon(snapshot, points, px, color)

    def _beam(self, snapshot: Gtk.Snapshot, item: BeamItem, px: float, palette: Palette) -> None:
        half = item.thickness / 2
        points = [
            (item.x1, item.y1 - half),
            (item.x2, item.y2 - half),
            (item.x2, item.y2 + half),
            (item.x1, item.y1 + half),
        ]
        self._polygon(snapshot, points, px, palette.color(item.ink))

    def _polygon(
        self,
        snapshot: Gtk.Snapshot,
        points: list[tuple[float, float]],
        px: float,
        color: Gdk.RGBA,
    ) -> None:
        builder = Gsk.PathBuilder.new()
        builder.move_to(points[0][0] * px, points[0][1] * px)
        for x, y in points[1:]:
            builder.line_to(x * px, y * px)
        builder.close()
        snapshot.append_fill(builder.to_path(), Gsk.FillRule.WINDING, color)

    def _curve(self, snapshot: Gtk.Snapshot, item: CurveItem, px: float, palette: Palette) -> None:
        # Outer and inner edges are cubic Béziers through the end points; the middle
        # of the crescent is ``thickness`` wide and the ends ``end_thickness``.
        sign = 1 if item.bulge >= 0 else -1
        e = item.end_thickness / 2 * sign
        dx = item.x2 - item.x1
        c1x, c2x = item.x1 + dx * 0.25, item.x1 + dx * 0.75
        # A cubic with both control points at height h peaks at 0.75 h.
        outer = (item.bulge + item.thickness / 2 * sign) / 0.75
        inner = (item.bulge - item.thickness / 2 * sign) / 0.75
        builder = Gsk.PathBuilder.new()
        builder.move_to(item.x1 * px, (item.y1 + e) * px)
        builder.cubic_to(
            c1x * px,
            (item.y1 + outer) * px,
            c2x * px,
            (item.y2 + outer) * px,
            item.x2 * px,
            (item.y2 + e) * px,
        )
        builder.line_to(item.x2 * px, (item.y2 - e) * px)
        builder.cubic_to(
            c2x * px,
            (item.y2 + inner) * px,
            c1x * px,
            (item.y1 + inner) * px,
            item.x1 * px,
            (item.y1 - e) * px,
        )
        builder.close()
        snapshot.append_fill(builder.to_path(), Gsk.FillRule.WINDING, palette.color(item.ink))

    def _text(self, snapshot: Gtk.Snapshot, item: TextItem, px: float, palette: Palette) -> None:
        pango_layout, baseline, width = self._layout(item.text, None, item.size * px, item.bold)
        x = item.x * px
        if item.align is Align.CENTER:
            x -= width / 2
        elif item.align is Align.END:
            x -= width
        snapshot.save()
        snapshot.translate(Graphene.Point().init(x, item.y * px - baseline))
        snapshot.append_layout(pango_layout, palette.color(item.ink))
        snapshot.restore()

    def _focus_ring(
        self, snapshot: Gtk.Snapshot, region: HitRegion, px: float, palette: Palette
    ) -> None:
        pad = 0.15
        rect = Graphene.Rect().init(
            (region.x - pad) * px,
            (region.y - pad) * px,
            (region.width + 2 * pad) * px,
            (region.height + 2 * pad) * px,
        )
        radius = Graphene.Size().init(0.4 * px, 0.4 * px)
        rounded = Gsk.RoundedRect().init(rect, radius, radius, radius, radius)
        builder = Gsk.PathBuilder.new()
        builder.add_rounded_rect(rounded)
        stroke = Gsk.Stroke.new(max(2.0, 0.16 * px))
        snapshot.append_stroke(
            builder.to_path(), stroke, _with_alpha(palette.accent_background, 0.5)
        )


class StaffView(Gtk.Widget):
    """Shows a :class:`~etude.notation.spec.StaffSpec` or ``SystemSpec``.

    Noteheads can be clicked, or focused with the arrow keys and activated
    with Enter or Space; both emit ``head-activated(staff, event, head)``.
    Bind ``scale`` to the ``large-notation`` setting to enlarge notation.
    """

    __gtype_name__ = 'EtudeStaffView'
    __gsignals__ = {  # noqa: RUF012
        'head-activated': (GObject.SignalFlags.RUN_LAST, None, (int, int, int)),
    }

    def __init__(self, figure: Figure | None = None, **kwargs: object) -> None:
        kwargs.setdefault('accessible_role', Gtk.AccessibleRole.IMG)
        # Our own properties need the attributes below, so set them after GObject init.
        own = {
            name.replace('-', '_'): kwargs.pop(name)
            for name in list(kwargs)
            if name.replace('-', '_') in ('figure', 'staff_space', 'scale', 'fill_width')
        }
        if figure is not None:
            own.setdefault('figure', figure)
        super().__init__(**kwargs)
        self._figure: Figure | None = None
        self._staff_space = DEFAULT_STAFF_SPACE
        self._scale = 1.0
        self._fill_width = False
        self._fit = 1.0
        """Scale factor below 1 when the allocation is narrower than the figure."""
        self._display: DisplayList | None = None
        self._layout_width: float | None = None
        self._focus_index: int | None = None
        self._renderer: Renderer | None = None
        self._name_pitch: Callable[[Pitch], str] = str
        self.set_focusable(True)
        self.set_overflow(Gtk.Overflow.HIDDEN)

        click = Gtk.GestureClick.new()
        click.connect('released', self._on_click)
        self.add_controller(click)
        keys = Gtk.EventControllerKey.new()
        keys.connect('key-pressed', self._on_key)
        self.add_controller(keys)
        focus = Gtk.EventControllerFocus.new()
        focus.connect('enter', lambda *_: self._on_focus_enter())
        focus.connect('leave', lambda *_: self.queue_draw())
        self.add_controller(focus)

        self._style_handlers: list[int] = []
        for name, value in own.items():
            self.set_property(name.replace('_', '-'), value)

    # -- properties --

    @GObject.Property(type=object)
    def figure(self) -> Figure | None:
        """The figure to show, or ``None`` for an empty widget."""
        return self._figure

    @figure.setter  # type: ignore[no-redef]
    def figure(self, value: Figure | None) -> None:
        self._figure = value
        self._focus_index = None
        self._relayout()
        self._update_accessible()

    @GObject.Property(type=float, default=DEFAULT_STAFF_SPACE, minimum=2.0, maximum=96.0)
    def staff_space(self) -> float:
        """Distance between staff lines in pixels, before ``scale``."""
        return self._staff_space

    @staff_space.setter  # type: ignore[no-redef]
    def staff_space(self, value: float) -> None:
        self._staff_space = value
        self._relayout()

    @GObject.Property(type=float, default=1.0, minimum=0.25, maximum=8.0)
    def scale(self) -> float:
        """Extra magnification for "Large notation"."""
        return self._scale

    @scale.setter  # type: ignore[no-redef]
    def scale(self, value: float) -> None:
        self._scale = value
        self._relayout()

    @GObject.Property(type=bool, default=False)
    def fill_width(self) -> bool:
        """Stretch the spacing to the allocated width instead of using the natural width."""
        return self._fill_width

    @fill_width.setter  # type: ignore[no-redef]
    def fill_width(self, value: bool) -> None:
        self._fill_width = value
        self._relayout()

    def set_pitch_namer(self, name_pitch: Callable[[Pitch], str]) -> None:
        """Use the learner's note naming convention in the accessible description."""
        self._name_pitch = name_pitch
        self._update_accessible()

    @property
    def display_list(self) -> DisplayList | None:
        return self._display

    @property
    def pixels_per_space(self) -> float:
        """Pixels per staff space as drawn: the requested size, reduced when the
        widget is narrower than the figure (phones, design 3b)."""
        return self._staff_space * self._scale * self._fit

    @property
    def _requested_px(self) -> float:
        return self._staff_space * self._scale

    # -- layout --

    def _relayout(self, width: float | None = None) -> None:
        self._layout_width = width
        if self._figure is None:
            self._display = None
        else:
            self._display = layout(self._figure, FontMetrics.bravura(), width=width)
        if self._focus_index is not None and self._focus_index >= len(self._head_regions()):
            self._focus_index = None
        self.queue_resize()
        self.queue_draw()

    def _natural(self) -> DisplayList | None:
        if self._figure is None:
            return None
        if self._layout_width is None:
            return self._display
        return layout(self._figure, FontMetrics.bravura())

    def do_get_request_mode(self) -> Gtk.SizeRequestMode:
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self, orientation: Gtk.Orientation, for_size: int) -> tuple[int, int, int, int]:
        display = self._natural()
        if display is None:
            return 0, 0, -1, -1
        px = self._requested_px
        if orientation == Gtk.Orientation.HORIZONTAL:
            natural = math.ceil(display.width * px)
            # Shrink down to MIN_FIT of the requested size rather than overflow.
            return math.ceil(natural * MIN_FIT), natural, -1, -1
        height = display.height
        if self._display is not None:
            height = max(height, self._display.height)
        if self._fill_width:
            pixels = math.ceil(height * px)
            return pixels, pixels, -1, -1
        if for_size < 0:
            # Without a width, the smallest height is the one at the smallest fit.
            return math.ceil(height * px * MIN_FIT), math.ceil(height * px), -1, -1
        fit = max(MIN_FIT, min(1.0, for_size / (display.width * px)))
        pixels = math.ceil(height * px * fit)
        return pixels, pixels, -1, -1

    def do_size_allocate(self, width: int, height: int, baseline: int) -> None:
        if self._fill_width and self._figure is not None:
            self._fit = 1.0
            target = width / self.pixels_per_space
            if self._layout_width is None or abs(target - self._layout_width) > 1e-3:
                self._layout_width = target
                self._display = layout(self._figure, FontMetrics.bravura(), width=target)
        else:
            display = self._display
            natural = display.width * self._requested_px if display is not None else 0
            self._fit = max(MIN_FIT, min(1.0, width / natural)) if natural > 0 else 1.0
        self.queue_draw()

    def _origin(self) -> tuple[float, float]:
        display = self._display
        if display is None:
            return 0.0, 0.0
        px = self.pixels_per_space
        x = max(0.0, (self.get_width() - display.width * px) / 2)
        y = max(0.0, (self.get_height() - display.height * px) / 2)
        return x, y

    # -- drawing --

    def _palette(self) -> Palette:
        return Palette.resolve(self.get_color())

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        display = self._display
        if display is None:
            return
        if self._renderer is None or self._renderer.context is not self.get_pango_context():
            self._renderer = Renderer(self.get_pango_context())
        focus = None
        if self._focus_index is not None and self.has_focus():
            regions = self._head_regions()
            focus = regions[self._focus_index]
        x, y = self._origin()
        snapshot.save()
        snapshot.translate(Graphene.Point().init(x, y))
        self._renderer.draw(snapshot, display, self.pixels_per_space, self._palette(), focus=focus)
        snapshot.restore()

    def do_css_changed(self, change: Gtk.CssStyleChange) -> None:
        Gtk.Widget.do_css_changed(self, change)
        if self._renderer is not None:
            self._renderer.clear_cache()
        self.queue_draw()

    def _on_style_changed(self, *_args: object) -> None:
        self.queue_draw()

    def do_root(self) -> None:
        Gtk.Widget.do_root(self)
        # The style manager outlives every widget: connect only while rooted.
        manager = Adw.StyleManager.get_default()
        self._style_handlers = [
            manager.connect('notify::dark', self._on_style_changed),
            manager.connect('notify::accent-color-rgba', self._on_style_changed),
            manager.connect('notify::high-contrast', self._on_style_changed),
        ]

    def do_unroot(self) -> None:
        manager = Adw.StyleManager.get_default()
        for handler in self._style_handlers:
            manager.disconnect(handler)
        self._style_handlers = []
        Gtk.Widget.do_unroot(self)

    # -- interaction --

    def _head_regions(self) -> list[HitRegion]:
        if self._display is None:
            return []
        heads = [r for r in self._display.hit_regions if r.head is not None]
        return sorted(heads, key=lambda r: (r.x, r.staff, -r.y))

    def _on_click(self, _gesture: Gtk.GestureClick, _n: int, x: float, y: float) -> None:
        if self._display is None:
            return
        ox, oy = self._origin()
        px = self.pixels_per_space
        region = self._display.hit_test((x - ox) / px, (y - oy) / px)
        if region is None or region.head is None:
            return
        regions = self._head_regions()
        self._focus_index = regions.index(region) if region in regions else None
        self.grab_focus()
        self.queue_draw()
        self.emit('head-activated', region.staff, region.event, region.head)

    def _on_focus_enter(self) -> None:
        if self._focus_index is None and self._head_regions():
            self._focus_index = 0
        self.queue_draw()

    def _on_key(
        self, _controller: Gtk.EventControllerKey, keyval: int, _code: int, _state: Gdk.ModifierType
    ) -> bool:
        regions = self._head_regions()
        if not regions:
            return False
        current = self._focus_index if self._focus_index is not None else 0
        region = regions[current]
        target: int | None = None
        if keyval in (Gdk.KEY_Left, Gdk.KEY_KP_Left):
            target = self._neighbour_event(regions, current, -1)
        elif keyval in (Gdk.KEY_Right, Gdk.KEY_KP_Right):
            target = self._neighbour_event(regions, current, 1)
        elif keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up, Gdk.KEY_Down, Gdk.KEY_KP_Down):
            up = keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up)
            target = self._neighbour_head(regions, current, up)
        elif keyval == Gdk.KEY_Home:
            target = 0
        elif keyval == Gdk.KEY_End:
            target = len(regions) - 1
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space, Gdk.KEY_KP_Space):
            self._focus_index = current
            assert region.head is not None
            self.emit('head-activated', region.staff, region.event, region.head)
            return True
        else:
            return False
        if target is not None:
            self._focus_index = target
            self._announce(regions[target])
            self.queue_draw()
        return True

    @staticmethod
    def _neighbour_event(regions: list[HitRegion], current: int, step: int) -> int | None:
        here = regions[current]
        index = current
        while 0 <= index + step < len(regions):
            index += step
            candidate = regions[index]
            if (candidate.staff, candidate.event) != (here.staff, here.event):
                return index
        return None

    @staticmethod
    def _neighbour_head(regions: list[HitRegion], current: int, up: bool) -> int | None:
        here = regions[current]
        same = [
            (r.y, i)
            for i, r in enumerate(regions)
            if (r.staff, r.event) == (here.staff, here.event) and i != current
        ]
        if up:
            above = [item for item in same if item[0] < here.y]
            return max(above)[1] if above else None
        below = [item for item in same if item[0] > here.y]
        return min(below)[1] if below else None

    # -- accessibility --

    def _update_accessible(self) -> None:
        text = '' if self._figure is None else describe(self._figure, self._name_pitch)
        self.update_property([Gtk.AccessibleProperty.LABEL], [text])

    def _announce(self, region: HitRegion) -> None:
        """Describe the focused notehead for screen readers."""
        figure = self._figure
        if figure is None or region.head is None:
            return
        staves = figure.staves if hasattr(figure, 'staves') else (figure,)
        staff = staves[region.staff]
        events = (*staff.events, *(e for voice in staff.voices for e in voice))
        event = events[region.event]
        heads = getattr(event, 'heads', ())
        if region.head < len(heads):
            name = self._name_pitch(heads[region.head].pitch)
            self.update_property([Gtk.AccessibleProperty.DESCRIPTION], [name])
