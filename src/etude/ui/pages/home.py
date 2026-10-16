# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The exercise overview (design 1a, 3a): a Continue banner and exercise cards.

Wide windows show a grid of cards; narrow windows (``compact``) show boxed
lists grouped by family.
"""

from __future__ import annotations

from collections.abc import Sequence
from gettext import gettext as _
from gettext import ngettext

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from ...exercises.base import Family
from ..common import format_percent, ui_resource
from ..preview import ContinueData, ExerciseCardData


def family_title(family: Family) -> str:
    return {
        Family.NOTATION: _('Notation'),
        Family.EAR: _('Ear Training'),
        Family.RHYTHM: _('Rhythm'),
        Family.HARMONY: _('Harmony'),
        Family.VOCABULARY: _('Vocabulary'),
    }[family]


def sessions_text(count: int) -> str:
    return ngettext('{n} session', '{n} sessions', count).format(n=count)


def accuracy_text(card: ExerciseCardData) -> str:
    return format_percent(card.accuracy) if card.accuracy is not None else _('New')


class ExerciseCard(Gtk.Button):
    """One exercise in the grid: icon tile, title, description, accuracy, sessions."""

    __gtype_name__ = 'EtudeExerciseCard'

    def __init__(self, card: ExerciseCardData) -> None:
        super().__init__()
        self.card = card
        self.add_css_class('card')
        self.add_css_class('exercise-card')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        tile = Gtk.Label(
            label=card.glyph,
            halign=Gtk.Align.START,
            accessible_role=Gtk.AccessibleRole.PRESENTATION,
        )
        tile.add_css_class('icon-tile')
        box.append(tile)
        title = Gtk.Label(label=card.title, xalign=0, wrap=True)
        title.add_css_class('heading')
        box.append(title)
        description = Gtk.Label(
            label=card.description,
            xalign=0,
            wrap=True,
            lines=2,
            vexpand=True,
            valign=Gtk.Align.START,
        )
        description.add_css_class('dim-label')
        box.append(description)
        stats = Gtk.Box(spacing=6)
        accuracy = Gtk.Label(label=accuracy_text(card), xalign=0)
        accuracy.add_css_class('heading')
        accuracy.add_css_class('numeric')
        stats.append(accuracy)
        caption = Gtk.Label(label=_('accuracy'), xalign=0, hexpand=True)
        caption.add_css_class('dim-label')
        caption.add_css_class('caption')
        stats.append(caption)
        sessions = Gtk.Label(label=sessions_text(card.sessions))
        sessions.add_css_class('dim-label')
        sessions.add_css_class('caption')
        stats.append(sessions)
        box.append(stats)
        self.set_child(box)
        self.update_property(
            [Gtk.AccessibleProperty.LABEL, Gtk.AccessibleProperty.DESCRIPTION],
            [
                card.title,
                f'{card.description} {accuracy_text(card)} {_("accuracy")}, '
                f'{sessions_text(card.sessions)}',
            ],
        )


@Gtk.Template(resource_path=ui_resource('pages/home.ui'))
class HomePage(Adw.NavigationPage):
    """Signals: ``exercise-activated(exercise_id)`` and ``resume-activated(exercise_id)``."""

    __gtype_name__ = 'EtudeHomePage'
    __gsignals__ = {  # noqa: RUF012 (GObject API)
        'exercise-activated': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        'resume-activated': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    sort_button: Gtk.MenuButton = Gtk.Template.Child()
    continue_revealer: Gtk.Revealer = Gtk.Template.Child()
    continue_glyph: Gtk.Label = Gtk.Template.Child()
    continue_title: Gtk.Label = Gtk.Template.Child()
    continue_detail: Gtk.Label = Gtk.Template.Child()
    resume_button: Gtk.Button = Gtk.Template.Child()
    resume_button_narrow: Gtk.Button = Gtk.Template.Child()
    layout_stack: Gtk.Stack = Gtk.Template.Child()
    card_grid: Gtk.FlowBox = Gtk.Template.Child()
    list_box: Gtk.Box = Gtk.Template.Child()

    compact = GObject.Property(type=bool, default=False)

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._cards: list[ExerciseCardData] = []
        self._family: Family | None = None
        self._continue: ContinueData | None = None
        self._sort = 'recent'
        group = Gio.SimpleActionGroup()
        sort = Gio.SimpleAction.new_stateful(
            'sort', GLib.VariantType.new('s'), GLib.Variant.new_string(self._sort)
        )
        sort.connect('activate', self._on_sort)
        group.add_action(sort)
        self.insert_action_group('home', group)
        self._update_sort_label()
        self.connect('notify::compact', lambda *_a: self._apply_compact())

    # Data ---------------------------------------------------------------------------

    def set_exercises(
        self, cards: Sequence[ExerciseCardData], family: Family | None = None
    ) -> None:
        """Show ``cards``, filtered to ``family`` (``None`` = all exercises)."""
        self._cards = list(cards)
        self._family = family
        self.set_title(family_title(family) if family else _('All Exercises'))
        self._rebuild()

    def set_continue(self, data: ContinueData | None, glyph: str = '♪') -> None:
        self._continue = data
        self.continue_revealer.set_reveal_child(data is not None)
        if data is None:
            return
        self.continue_glyph.set_label(glyph)
        self.continue_title.set_label(data.title)
        # Translators: e.g. "7 of 20 answered · 64% accuracy in this exercise".
        self.continue_detail.set_label(
            _('{answered} of {total} answered · {accuracy} accuracy in this exercise').format(
                answered=data.answered, total=data.total, accuracy=format_percent(data.accuracy)
            )
        )

    def visible_cards(self) -> list[ExerciseCardData]:
        cards = [c for c in self._cards if self._family is None or c.family is self._family]
        if self._sort == 'name':
            cards.sort(key=lambda c: c.title.casefold())
        elif self._sort == 'accuracy':
            cards.sort(key=lambda c: -(c.accuracy or 0))
        else:
            cards.sort(key=lambda c: c.recency)
        return cards

    # Layout -------------------------------------------------------------------------

    def _apply_compact(self) -> None:
        self.resume_button.set_visible(not self.compact)
        self.resume_button_narrow.set_visible(self.compact)
        self.continue_glyph.set_visible(not self.compact)
        self._update_sort_label()
        self._rebuild()

    def _rebuild(self) -> None:
        self.card_grid.remove_all()
        child = self.list_box.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self.list_box.remove(child)
            child = following
        cards = self.visible_cards()
        if not cards:
            self.layout_stack.set_visible_child_name('empty')
            return
        if self.compact:
            self._build_list(cards)
            self.layout_stack.set_visible_child_name('list')
        else:
            for card in cards:
                button = ExerciseCard(card)
                button.connect('clicked', self._on_card_clicked)
                self.card_grid.append(button)
                button.get_parent().set_focusable(False)
            self.layout_stack.set_visible_child_name('grid')

    def _build_list(self, cards: list[ExerciseCardData]) -> None:
        for family in Family:
            members = [c for c in cards if c.family is family]
            if not members:
                continue
            group = Adw.PreferencesGroup(title=family_title(family))
            for card in members:
                row = Adw.ActionRow(
                    title=card.title,
                    # Translators: e.g. "94% · 18 sessions".
                    subtitle=_('{accuracy} · {sessions}').format(
                        accuracy=accuracy_text(card), sessions=sessions_text(card.sessions)
                    ),
                    activatable=True,
                )
                tile = Gtk.Label(
                    label=card.glyph,
                    valign=Gtk.Align.CENTER,
                    accessible_role=Gtk.AccessibleRole.PRESENTATION,
                )
                tile.add_css_class('icon-tile')
                tile.add_css_class('small')
                row.add_prefix(tile)
                row.add_suffix(Gtk.Image(icon_name='go-next-symbolic'))
                row.connect('activated', self._on_row_activated, card.id)
                group.add(row)
            self.list_box.append(group)

    def _update_sort_label(self) -> None:
        names = {'recent': _('Recent'), 'name': _('Name'), 'accuracy': _('Accuracy')}
        # Translators: the sort menu button, e.g. "Sort: Recent".
        text = _('Sort: {order}').format(order=names[self._sort])
        if self.compact:
            self.sort_button.set_icon_name('view-sort-descending-symbolic')
        else:
            self.sort_button.set_label(text)
        self.sort_button.set_tooltip_text(text)

    # Signal handlers ----------------------------------------------------------------

    def _on_sort(self, action: Gio.SimpleAction, value: GLib.Variant) -> None:
        action.set_state(value)
        self._sort = value.get_string()
        self._update_sort_label()
        self._rebuild()

    def _on_card_clicked(self, button: ExerciseCard) -> None:
        self.emit('exercise-activated', button.card.id)

    def _on_row_activated(self, _row: Adw.ActionRow, exercise_id: str) -> None:
        self.emit('exercise-activated', exercise_id)

    @Gtk.Template.Callback()
    def _on_resume_clicked(self, _button: Gtk.Button) -> None:
        if self._continue is not None:
            self.emit('resume-activated', self._continue.exercise_id)

    @Gtk.Template.Callback()
    def _on_dismiss_clicked(self, _button: Gtk.Button) -> None:
        self.continue_revealer.set_reveal_child(False)
