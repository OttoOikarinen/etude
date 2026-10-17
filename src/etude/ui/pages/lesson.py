# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""A theory lesson (``etude.content.model.Lesson``), pushed over the main page.

The page follows docs/PEDAGOGY.md: notation and sound appear together
(examples with a play button), worked examples reveal one step at a time
(fading guidance), and sections end with check questions instead of a
summary to re-read (retrieval practice). Checks are not scheduled: the
lesson counts as completed once every check has been answered, and the
"Practise This Unit" button at the end hands over to spaced practice.
"""

from __future__ import annotations

from gettext import gettext as _

from gi.repository import Adw, GObject, Gtk

from ...audio.spec import PlaybackSpec
from ...content.model import (
    Block,
    Callout,
    Check,
    Example,
    Lesson,
    ListBlock,
    ParagraphBlock,
    Section,
    WorkedExample,
)
from ..common import ui_resource
from ..content import (
    CheckView,
    WorkedExampleView,
    callout_box,
    example_card,
    heading,
    paragraph_label,
)
from ..model import UnitData


@Gtk.Template(resource_path=ui_resource('pages/lesson.ui'))
class LessonPage(Adw.NavigationPage):
    """Signals: ``term-activated(entry_id)``, ``play-requested(spec)``,
    ``practise-requested(unit_id)`` and ``completed(lesson_id)`` (every check answered)."""

    __gtype_name__ = 'EtudeLessonPage'
    __gsignals__ = {  # noqa: RUF012 (GObject API)
        'term-activated': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        'play-requested': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        'practise-requested': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        'completed': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    window_title: Adw.WindowTitle = Gtk.Template.Child()
    scroller: Gtk.ScrolledWindow = Gtk.Template.Child()
    kicker_label: Gtk.Label = Gtk.Template.Child()
    title_label: Gtk.Label = Gtk.Template.Child()
    summary_label: Gtk.Label = Gtk.Template.Child()
    sections_box: Gtk.Box = Gtk.Template.Child()
    end_box: Gtk.Box = Gtk.Template.Child()
    end_icon: Gtk.Image = Gtk.Template.Child()
    end_title: Gtk.Label = Gtk.Template.Child()
    end_detail: Gtk.Label = Gtk.Template.Child()
    practise_button: Gtk.Button = Gtk.Template.Child()

    compact = GObject.Property(type=bool, default=False)

    def __init__(
        self, lesson: Lesson, unit: UnitData | None = None, *, done: bool = False, **kwargs: object
    ) -> None:
        super().__init__(**kwargs)
        self.lesson = lesson
        self.unit = unit
        self.done = done
        self.set_title(lesson.title)
        self.set_tag(f'lesson-{lesson.id}')
        self.window_title.set_title(lesson.title)
        self.title_label.set_label(lesson.title)
        self.title_label.update_property([Gtk.AccessibleProperty.LEVEL], [1])
        self.summary_label.set_label(lesson.summary)
        self.summary_label.set_visible(bool(lesson.summary))
        # Translators: above a lesson's title.
        self.kicker_label.set_label(_('Theory Lesson'))
        self.checks: list[CheckView] = []
        self.worked: list[WorkedExampleView] = []
        self._answered: set[str] = set()
        for section in lesson.sections:
            self.sections_box.append(self._section(section))
        self._update_end()
        self.connect('notify::compact', lambda *_a: self._apply_compact())

    def _apply_compact(self) -> None:
        if self.compact:
            self.add_css_class('compact')
        else:
            self.remove_css_class('compact')
        self.practise_button.set_halign(Gtk.Align.FILL if self.compact else Gtk.Align.CENTER)

    # Rendering -------------------------------------------------------------------------

    def _on_term(self, entry_id: str) -> None:
        self.emit('term-activated', entry_id)

    def _on_play(self, spec: PlaybackSpec) -> None:
        self.emit('play-requested', spec)

    def _section(self, section: Section) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.add_css_class('lesson-section')
        box.append(heading(section.title))
        for block in section.blocks:
            box.append(self._block(block))
        return box

    def _block(self, block: Block) -> Gtk.Widget:
        if isinstance(block, ParagraphBlock):
            return paragraph_label(block.content, self._on_term, css=('lesson-text',))
        if isinstance(block, ListBlock):
            return self._list(block)
        if isinstance(block, Callout):
            return callout_box(block, self._on_term)
        if isinstance(block, Example):
            return example_card(block, self._on_play, self._on_term)
        if isinstance(block, WorkedExample):
            worked = WorkedExampleView(block, self._on_play, self._on_term)
            self.worked.append(worked)
            return worked
        if isinstance(block, Check):
            check = CheckView(block, self._on_play, self._on_term)
            check.connect('answered', self._on_check_answered)
            self.checks.append(check)
            return check
        raise TypeError(f'unknown lesson block {block!r}')

    def _list(self, block: ListBlock) -> Gtk.Widget:
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=6, accessible_role=Gtk.AccessibleRole.LIST
        )
        box.add_css_class('lesson-list')
        for number, item in enumerate(block.items, start=1):
            row = Gtk.Box(spacing=10, accessible_role=Gtk.AccessibleRole.LIST_ITEM)
            marker = Gtk.Label(
                label=f'{number}.' if block.ordered else '•',
                valign=Gtk.Align.START,
                accessible_role=Gtk.AccessibleRole.PRESENTATION,
            )
            marker.add_css_class('lesson-text')
            marker.add_css_class('list-marker')
            if block.ordered:
                marker.add_css_class('numeric')
            row.append(marker)
            row.append(paragraph_label(item, self._on_term, css=('lesson-text',)))
            box.append(row)
        return box

    # Completion ---------------------------------------------------------------------

    @property
    def answered(self) -> int:
        """Check questions answered at least once."""
        return len(self._answered)

    def _on_check_answered(self, check: CheckView, _correct: bool) -> None:
        self._answered.add(check.check.id)
        if not self.done and self.answered == len(self.checks):
            self.done = True
            self.emit('completed', self.lesson.id)
        self._update_end()

    def _update_end(self) -> None:
        practisable = self.unit is not None and self.unit.practisable
        self.practise_button.set_visible(practisable)
        if self.done:
            self.end_icon.add_css_class('success')
        else:
            self.end_icon.remove_css_class('success')
        self.end_icon.set_from_icon_name(
            'object-select-symbolic' if self.done else 'x-office-document-symbolic'
        )
        if practisable and self.unit is not None:
            self.end_title.set_label(_('Ready to Practise'))
            # Translators: at the end of a lesson; the unit's title is in quotes.
            detail = _(
                'Spaced practice of “{unit}” turns what you read into lasting knowledge.'
            ).format(unit=self.unit.title)
        else:
            self.end_title.set_label(_('End of the Lesson'))
            detail = _('Practice for this unit arrives in a later version.')
        if self.checks and not self.done:
            detail = '{} {}'.format(
                _('Answer the check questions above to complete the lesson.'), detail
            )
        self.end_detail.set_label(detail)

    # Signal handlers ----------------------------------------------------------------

    @Gtk.Template.Callback()
    def _on_practise_clicked(self, _button: Gtk.Button) -> None:
        if self.unit is not None:
            self.emit('practise-requested', self.unit.id)
