# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Path page: the curriculum map of levels and units (mastery learning).

Each unit shows how much of it is mastered and whether it is unlocked;
reading a lesson is never locked, and practising a locked unit only asks
for confirmation (the window does that). Each level ends with its exam. A
new learner is offered the placement test to skip what they already know.
"""

from __future__ import annotations

from gettext import gettext as _
from gettext import ngettext

from gi.repository import Adw, GObject, Gtk

from ..common import format_percent, ui_resource
from ..model import LevelData, PathData, UnitData


def missing_text(unit: UnitData) -> str:
    """Why a unit is locked, e.g. "Master “Staff, Clefs and Note Names” to unlock"."""
    if not unit.missing:
        return _('Locked')
    if len(unit.missing) == 1:
        # Translators: why a unit is locked; the other unit's title is in quotes.
        return _('Master “{unit}” to unlock').format(unit=unit.missing[0])
    others = len(unit.missing) - 1
    # Translators: why a unit is locked, e.g. "Master “Intervals” and 2 more units to unlock".
    return ngettext(
        'Master “{unit}” and {n} more unit to unlock',
        'Master “{unit}” and {n} more units to unlock',
        others,
    ).format(unit=unit.missing[0], n=others)


def unit_status(unit: UnitData) -> tuple[str, str]:
    """Icon name and text of a unit's state (colour is never the only signal)."""
    if unit.placed:
        return 'object-select-symbolic', _('Placed out')
    if unit.complete and unit.practisable:
        return 'object-select-symbolic', _('Mastered')
    if not unit.unlocked:
        return 'changes-prevent-symbolic', missing_text(unit)
    if not unit.practisable:
        return 'x-office-document-symbolic', _('Lesson only — practice arrives in a later version')
    fraction = unit.fraction or 0.0
    # Translators: a unit's progress, e.g. "45% mastered · 12 of 27 items".
    return '', _('{percent} mastered · {mastered} of {items} items').format(
        percent=format_percent(fraction), mastered=unit.mastered, items=unit.items
    )


def _label(text: str, *css: str, wrap: bool = True) -> Gtk.Label:
    label = Gtk.Label(label=text, xalign=0, wrap=wrap)
    for name in css:
        label.add_css_class(name)
    return label


class UnitCard(Gtk.Box):
    """One unit: number or state tile, title, summary, progress and actions."""

    __gtype_name__ = 'EtudeUnitCard'

    def __init__(self, unit: UnitData, number: int, *, current: bool) -> None:
        super().__init__(spacing=16, accessible_role=Gtk.AccessibleRole.GROUP)
        self.unit = unit
        self.add_css_class('card')
        self.add_css_class('unit-card')
        if current:
            self.add_css_class('current-unit')
        if not unit.unlocked:
            self.add_css_class('locked')
        self.update_property([Gtk.AccessibleProperty.LABEL], [unit.title])

        if unit.complete and (unit.practisable or unit.placed):
            tile: Gtk.Widget = Gtk.Image(
                icon_name='object-select-symbolic', accessible_role=Gtk.AccessibleRole.PRESENTATION
            )
            tile.add_css_class('success')
        elif not unit.unlocked:
            tile = Gtk.Image(
                icon_name='changes-prevent-symbolic',
                accessible_role=Gtk.AccessibleRole.PRESENTATION,
            )
        else:
            tile = Gtk.Label(label=str(number), accessible_role=Gtk.AccessibleRole.PRESENTATION)
            tile.add_css_class('numeric')
        tile.set_valign(Gtk.Align.START)
        tile.add_css_class('unit-tile')
        self.append(tile)

        self.main = Gtk.Box(spacing=12, hexpand=True)
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        info.append(_label(unit.title, 'heading'))
        if unit.summary:
            info.append(_label(unit.summary, 'dim-label'))
        status_row = Gtk.Box(spacing=8, margin_top=4)
        icon_name, text = unit_status(unit)
        if icon_name:
            icon = Gtk.Image(icon_name=icon_name, accessible_role=Gtk.AccessibleRole.PRESENTATION)
            if unit.complete and (unit.practisable or unit.placed):
                icon.add_css_class('success')
            else:
                icon.add_css_class('dim-label')
            status_row.append(icon)
        elif unit.practisable:
            self.bar = Gtk.LevelBar(
                min_value=0, max_value=1, value=unit.fraction or 0.0, valign=Gtk.Align.CENTER
            )
            for name in ('low', 'high', 'full'):
                self.bar.remove_offset_value(name)
            self.bar.add_css_class('mastery-bar')
            self.bar.set_size_request(72, -1)
            self.bar.update_property([Gtk.AccessibleProperty.LABEL], [_('Mastery')])
            self.bar.update_property([Gtk.AccessibleProperty.VALUE_TEXT], [text])
            status_row.append(self.bar)
        self.status_label = _label(text, 'caption')
        if not unit.complete:
            self.status_label.add_css_class('dim-label')
        self.status_label.set_hexpand(True)
        status_row.append(self.status_label)
        info.append(status_row)
        self.main.append(info)

        self.actions = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        self.lesson_button: Gtk.Button | None = None
        self.practise_button: Gtk.Button | None = None
        if unit.lesson_id:
            # Translators: opens a unit's theory lesson.
            self.lesson_button = Gtk.Button(label=_('Read Lesson'), use_underline=True)
            self.lesson_button.add_css_class('pill')
            if unit.lesson_done:
                self.lesson_button.set_tooltip_text(_('Lesson completed'))
            self.actions.append(self.lesson_button)
        if unit.practisable:
            self.practise_button = Gtk.Button(label=_('Practise'), use_underline=True)
            self.practise_button.add_css_class('pill')
            if current:
                self.practise_button.add_css_class('suggested-action')
            self.practise_button.update_property([Gtk.AccessibleProperty.DESCRIPTION], [unit.title])
            self.actions.append(self.practise_button)
        if self.lesson_button is not None:
            self.lesson_button.update_property([Gtk.AccessibleProperty.DESCRIPTION], [unit.title])
        self.actions.set_visible(self.lesson_button is not None or self.practise_button is not None)
        self.main.append(self.actions)
        self.append(self.main)

    def set_compact(self, compact: bool) -> None:
        self.main.set_orientation(
            Gtk.Orientation.VERTICAL if compact else Gtk.Orientation.HORIZONTAL
        )
        self.actions.set_homogeneous(compact)
        self.actions.set_halign(Gtk.Align.FILL if compact else Gtk.Align.END)


class ExamCard(Gtk.Box):
    """The exam at the end of a level."""

    __gtype_name__ = 'EtudeExamCard'

    def __init__(self, level: LevelData) -> None:
        super().__init__(spacing=16, accessible_role=Gtk.AccessibleRole.GROUP)
        self.level = level
        self.add_css_class('card')
        self.add_css_class('unit-card')
        self.add_css_class('exam-card')
        if level.passed:
            self.add_css_class('passed')
        # Translators: e.g. "Level 1 Exam".
        title = _('Level {number} Exam').format(number=level.number)
        self.update_property([Gtk.AccessibleProperty.LABEL], [title])
        tile = Gtk.Image(
            icon_name='object-select-symbolic' if level.passed else 'document-edit-symbolic',
            valign=Gtk.Align.START,
            accessible_role=Gtk.AccessibleRole.PRESENTATION,
        )
        tile.add_css_class('unit-tile')
        if level.passed:
            tile.add_css_class('success')
        self.append(tile)
        self.main = Gtk.Box(spacing=12, hexpand=True)
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        info.append(_label(title, 'heading'))
        if level.exam_questions:
            # Translators: e.g. "30 questions from every unit · 24 correct answers pass".
            detail = ngettext(
                '{n} question from every unit · {needed} correct answers pass',
                '{n} questions from every unit · {needed} correct answers pass',
                level.exam_questions,
            ).format(n=level.exam_questions, needed=level.exam_needed)
        else:
            detail = _('The exam opens when this level has practice')
        info.append(_label(detail, 'dim-label'))
        status = Gtk.Box(spacing=8, margin_top=4)
        if level.passed:
            icon = Gtk.Image(
                icon_name='object-select-symbolic', accessible_role=Gtk.AccessibleRole.PRESENTATION
            )
            icon.add_css_class('success')
            status.append(icon)
            status.append(_label(_('Passed — every unit of the level is open'), 'caption'))
        elif not level.exam_ready:
            icon = Gtk.Image(
                icon_name='changes-prevent-symbolic',
                accessible_role=Gtk.AccessibleRole.PRESENTATION,
            )
            icon.add_css_class('dim-label')
            status.append(icon)
            status.append(
                _label(_('Recommended once every unit is unlocked'), 'caption', 'dim-label')
            )
        status.set_visible(level.passed or not level.exam_ready)
        info.append(status)
        self.main.append(info)
        self.button = Gtk.Button(
            label=_('Retake Exam') if level.passed else _('Take Exam'),
            valign=Gtk.Align.CENTER,
            sensitive=level.exam_questions > 0,
        )
        self.button.add_css_class('pill')
        if level.exam_ready and not level.passed:
            self.button.add_css_class('suggested-action')
        self.main.append(self.button)
        self.append(self.main)

    def set_compact(self, compact: bool) -> None:
        self.main.set_orientation(
            Gtk.Orientation.VERTICAL if compact else Gtk.Orientation.HORIZONTAL
        )
        self.button.set_halign(Gtk.Align.FILL if compact else Gtk.Align.END)


@Gtk.Template(resource_path=ui_resource('pages/path.ui'))
class PathPage(Adw.NavigationPage):
    """Signals: ``lesson-requested(unit_id)``, ``practise-requested(unit_id)``,
    ``exam-requested(level_id)`` and ``placement-requested``."""

    __gtype_name__ = 'EtudePathPage'
    __gsignals__ = {  # noqa: RUF012 (GObject API)
        'lesson-requested': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        'practise-requested': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        'exam-requested': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        'placement-requested': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    placement_box: Gtk.Box = Gtk.Template.Child()
    placement_icon: Gtk.Image = Gtk.Template.Child()
    placement_button: Gtk.Button = Gtk.Template.Child()
    levels_box: Gtk.Box = Gtk.Template.Child()

    compact = GObject.Property(type=bool, default=False)

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.data: PathData | None = None
        self.unit_cards: dict[str, UnitCard] = {}
        self.exam_cards: dict[str, ExamCard] = {}
        self._levels: list[Gtk.Widget] = []
        self.connect('notify::compact', lambda *_a: self._apply_compact())

    def _apply_compact(self) -> None:
        if self.compact:
            self.add_css_class('compact')
        else:
            self.remove_css_class('compact')
        vertical = Gtk.Orientation.VERTICAL
        self.placement_box.set_orientation(vertical if self.compact else Gtk.Orientation.HORIZONTAL)
        self.placement_icon.set_visible(not self.compact)
        self.placement_button.set_halign(Gtk.Align.FILL if self.compact else Gtk.Align.CENTER)
        for card in (*self.unit_cards.values(), *self.exam_cards.values()):
            card.set_compact(self.compact)

    def set_data(self, data: PathData) -> None:
        self.data = data
        self.placement_box.set_visible(data.placement_available)
        for widget in self._levels:
            self.levels_box.remove(widget)
        self._levels = []
        self.unit_cards = {}
        self.exam_cards = {}
        current = data.current_unit
        for level in data.levels:
            box = self._level(level, current)
            self.levels_box.append(box)
            self._levels.append(box)
        self._apply_compact()

    def _level(self, level: LevelData, current: str | None) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        header.add_css_class('level-header')
        # Translators: above a level's title on the Path page, e.g. "Level 1".
        header.append(
            _label(_('Level {number}').format(number=level.number), 'caption-heading', 'accent')
        )
        title = Gtk.Label(
            label=level.title, xalign=0, wrap=True, accessible_role=Gtk.AccessibleRole.HEADING
        )
        title.update_property([Gtk.AccessibleProperty.LEVEL], [2])
        title.add_css_class('title-2')
        header.append(title)
        if level.description:
            header.append(_label(level.description, 'dim-label'))
        progress = Gtk.Box(spacing=8, margin_top=4)
        if level.passed:
            icon = Gtk.Image(
                icon_name='object-select-symbolic', accessible_role=Gtk.AccessibleRole.PRESENTATION
            )
            icon.add_css_class('success')
            progress.append(icon)
        total = len(level.units)
        # Translators: a level's progress, e.g. "3 of 10 units complete".
        text = ngettext(
            '{done} of {n} unit complete', '{done} of {n} units complete', total
        ).format(done=level.completed, n=total)
        if level.passed:
            text = '{} · {}'.format(text, _('Level passed'))
        progress.append(_label(text, 'caption'))
        header.append(progress)
        box.append(header)
        for number, unit in enumerate(level.units, start=1):
            card = UnitCard(unit, number, current=unit.id == current)
            if card.lesson_button is not None:
                card.lesson_button.connect(
                    'clicked', lambda _b, u=unit.id: self.emit('lesson-requested', u)
                )
            if card.practise_button is not None:
                card.practise_button.connect(
                    'clicked', lambda _b, u=unit.id: self.emit('practise-requested', u)
                )
            self.unit_cards[unit.id] = card
            box.append(card)
        exam = ExamCard(level)
        exam.button.connect('clicked', lambda _b, lv=level.id: self.emit('exam-requested', lv))
        self.exam_cards[level.id] = exam
        box.append(exam)
        return box

    @Gtk.Template.Callback()
    def _on_placement_clicked(self, _button: Gtk.Button) -> None:
        self.emit('placement-requested')
