# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Widgets for teaching content: lesson blocks and glossary entries.

Texts come from :mod:`etude.content.model`. Note names are written in the
learner's convention (``ui.common.note_label``), glossary terms become links
that call ``on_term(entry_id)``, and notated examples use
:func:`~etude.ui.figure.create_figure_widget` with a play button that calls
``on_play(spec)``. Every state is shown with colour, an icon and text.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from gettext import gettext as _

from gi.repository import GLib, GObject, Gtk, Pango

from ..audio.spec import PlaybackSpec
from ..content.model import (
    Callout,
    CalloutKind,
    Check,
    Emphasis,
    Example,
    GlossaryEntry,
    NoteRef,
    Paragraph,
    TermRef,
    Text,
    WorkedExample,
    plain_text,
)
from ..core import Pitch, PitchName
from .common import note_label
from .figure import create_figure_widget, describe_figure, pitch_label

TermHandler = Callable[[str], None]
PlayHandler = Callable[[PlaybackSpec], None]

TERM_SCHEME = 'term:'


def note_text(note: Pitch | PitchName) -> str:
    """A note of a text in the learner's convention: "B♭4", "B4" or "Si♭4"."""
    return pitch_label(note) if isinstance(note, Pitch) else note_label(note)


def plain(paragraph: Paragraph) -> str:
    return plain_text(paragraph, note_text)


def inline_markup(paragraph: Paragraph) -> str:
    """Pango markup: emphasis in italics, glossary terms as ``term:`` links."""
    parts = []
    for inline in paragraph:
        if isinstance(inline, Text):
            parts.append(GLib.markup_escape_text(inline.text))
        elif isinstance(inline, Emphasis):
            parts.append(f'<i>{GLib.markup_escape_text(inline.text)}</i>')
        elif isinstance(inline, TermRef):
            href = GLib.markup_escape_text(TERM_SCHEME + inline.entry_id)
            parts.append(f'<a href="{href}">{GLib.markup_escape_text(inline.text)}</a>')
        elif isinstance(inline, NoteRef):
            parts.append(GLib.markup_escape_text(note_text(inline.note)))
    return ''.join(parts)


def paragraph_label(
    paragraph: Paragraph, on_term: TermHandler | None = None, *, css: Sequence[str] = ()
) -> Gtk.Label:
    """A wrapping label for a paragraph; glossary links call ``on_term``."""
    label = Gtk.Label(
        label=inline_markup(paragraph),
        use_markup=True,
        wrap=True,
        xalign=0,
        hexpand=True,
    )
    label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)  # long words never widen the page
    for name in css:
        label.add_css_class(name)

    def on_link(_label: Gtk.Label, uri: str) -> bool:
        if uri.startswith(TERM_SCHEME):
            if on_term is not None:
                on_term(uri.removeprefix(TERM_SCHEME))
            return True
        return False

    label.connect('activate-link', on_link)
    return label


def heading(text: str, css: str = 'title-2', level: int = 2) -> Gtk.Label:
    label = Gtk.Label(label=text, wrap=True, xalign=0, accessible_role=Gtk.AccessibleRole.HEADING)
    label.update_property([Gtk.AccessibleProperty.LEVEL], [level])
    label.add_css_class(css)
    return label


def caption_heading(text: str) -> Gtk.Label:
    label = Gtk.Label(label=text, xalign=0, wrap=True)
    label.add_css_class('caption-heading')
    label.add_css_class('accent')
    return label


def play_button(spec: PlaybackSpec, on_play: PlayHandler, label: str | None = None) -> Gtk.Button:
    content = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
    content.append(
        Gtk.Image(
            icon_name='media-playback-start-symbolic',
            accessible_role=Gtk.AccessibleRole.PRESENTATION,
        )
    )
    content.append(Gtk.Label(label=label or _('Play')))
    button = Gtk.Button(child=content, halign=Gtk.Align.CENTER)
    button.add_css_class('pill')
    button.add_css_class('play-example')
    button.update_property([Gtk.AccessibleProperty.LABEL], [label or _('Play example')])
    button.connect('clicked', lambda _b: on_play(spec))
    return button


def example_card(
    example: Example, on_play: PlayHandler, on_term: TermHandler | None = None
) -> Gtk.Widget:
    """A notated example: the staff, its caption and a play button."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.add_css_class('figure-card')
    box.add_css_class('lesson-figure')
    figure = create_figure_widget(example.figure)
    # Lesson figures are not answered by clicking noteheads: keep them out of the
    # focus chain (the description still reaches screen readers).
    figure.set_focusable(False)
    figure.update_property([Gtk.AccessibleProperty.DESCRIPTION], [describe_figure(example.figure)])
    box.append(figure)
    if example.caption:
        caption = paragraph_label(example.caption, on_term, css=('caption', 'dim-label'))
        caption.set_xalign(0.5)
        caption.set_justify(Gtk.Justification.CENTER)
        box.append(caption)
    if example.playback is not None:
        box.append(play_button(example.playback, on_play))
    return box


# Callouts ----------------------------------------------------------------------------


def callout_style(kind: CalloutKind) -> tuple[str, str]:
    """Icon name and title of a callout kind."""
    return {
        # Translators: title of a highlighted tip in a lesson.
        CalloutKind.TIP: ('emoji-objects-symbolic', _('Tip')),
        # Translators: title of a box of facts to memorise in a lesson.
        CalloutKind.REMEMBER: ('view-pin-symbolic', _('Remember')),
        # Translators: title of a warning about a common mistake in a lesson.
        CalloutKind.WARNING: ('dialog-warning-symbolic', _('Watch Out')),
    }[kind]


def callout_box(callout: Callout, on_term: TermHandler | None = None) -> Gtk.Widget:
    icon_name, title = callout_style(callout.kind)
    box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=6, accessible_role=Gtk.AccessibleRole.NOTE
    )
    box.add_css_class('callout')
    box.add_css_class(f'callout-{callout.kind.value}')
    header = Gtk.Box(spacing=8)
    header.append(Gtk.Image(icon_name=icon_name, accessible_role=Gtk.AccessibleRole.PRESENTATION))
    title_label = Gtk.Label(label=title, xalign=0)
    title_label.add_css_class('heading')
    title_label.add_css_class('callout-title')
    header.append(title_label)
    box.append(header)
    for paragraph in callout.content:
        box.append(paragraph_label(paragraph, on_term, css=('lesson-text',)))
    box.update_property([Gtk.AccessibleProperty.LABEL], [title])
    return box


# Worked examples (fading guidance) ---------------------------------------------------


class WorkedExampleView(Gtk.Box):
    """A worked example whose steps are revealed one at a time with "Next Step"."""

    __gtype_name__ = 'EtudeWorkedExampleView'

    def __init__(
        self, worked: WorkedExample, on_play: PlayHandler, on_term: TermHandler | None = None
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add_css_class('card')
        self.add_css_class('lesson-card')
        self.add_css_class('worked-example')
        self.append(caption_heading(_('Worked Example')))
        self.append(heading(worked.title, 'heading', level=3))
        self.revealers: list[Gtk.Revealer] = []
        total = len(worked.steps)
        for number, step in enumerate(worked.steps, start=1):
            row = Gtk.Box(spacing=12)
            badge = Gtk.Label(label=str(number), valign=Gtk.Align.START)
            badge.add_css_class('step-number')
            badge.add_css_class('numeric')
            # Translators: read by screen readers before a step, e.g. "Step 2 of 3".
            badge.update_property(
                [Gtk.AccessibleProperty.LABEL],
                [_('Step {number} of {total}').format(number=number, total=total)],
            )
            row.append(badge)
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True)
            for paragraph in step.content:
                content.append(paragraph_label(paragraph, on_term, css=('lesson-text',)))
            if step.example is not None:
                content.append(example_card(step.example, on_play, on_term))
            row.append(content)
            revealer = Gtk.Revealer(
                child=row,
                reveal_child=number == 1,
                transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
            )
            self.revealers.append(revealer)
            self.append(revealer)
        self.next_button = Gtk.Button(halign=Gtk.Align.START, use_underline=True)
        self.next_button.add_css_class('pill')
        self.next_button.connect('clicked', lambda _b: self.reveal_next())
        self.append(self.next_button)
        self._update_button()

    @property
    def shown(self) -> int:
        return sum(r.get_reveal_child() for r in self.revealers)

    def reveal_next(self) -> None:
        hidden = [r for r in self.revealers if not r.get_reveal_child()]
        if hidden:
            hidden[0].set_reveal_child(True)
        self._update_button()

    def _update_button(self) -> None:
        shown, total = self.shown, len(self.revealers)
        done = shown >= total
        self.next_button.set_visible(not done)
        if not done:
            # Translators: reveals the next step of a worked example; "(2 of 3)" counts steps.
            self.next_button.set_label(
                _('_Next Step ({number} of {total})').format(number=shown + 1, total=total)
            )


# Check questions (retrieval practice) ------------------------------------------------


class CheckView(Gtk.Box):
    """A "check your understanding" question with immediate, explained feedback.

    Signal ``answered(correct)`` fires on every answer, including retries.
    """

    __gtype_name__ = 'EtudeCheckView'
    __gsignals__ = {  # noqa: RUF012 (GObject API)
        'answered': (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
    }

    def __init__(
        self, check: Check, on_play: PlayHandler, on_term: TermHandler | None = None
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.check = check
        self.add_css_class('card')
        self.add_css_class('lesson-card')
        self.add_css_class('check-card')
        self.append(caption_heading(_('Check Your Understanding')))
        prompt = paragraph_label(check.prompt, on_term, css=('heading',))
        self.append(prompt)
        if check.example is not None:
            # A check's figure carries a description that does not give the answer away.
            self.append(example_card(check.example, on_play, on_term))
        self.options_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.options_box.update_property([Gtk.AccessibleProperty.LABEL], [plain(check.prompt)])
        self.buttons: dict[str, Gtk.Button] = {}
        for option in check.options:
            label = paragraph_label(option.content, None)
            label.set_xalign(0)
            button = Gtk.Button(child=label)
            button.add_css_class('answer-button')
            button.add_css_class('check-option')
            button.update_property([Gtk.AccessibleProperty.LABEL], [plain(option.content)])
            button.connect('clicked', lambda _b, key=option.key: self.choose(key))
            self.buttons[option.key] = button
            self.options_box.append(button)
        self.append(self.options_box)

        self.feedback = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.feedback.add_css_class('feedback-banner')
        top = Gtk.Box(spacing=8)
        self.feedback_icon = Gtk.Image(accessible_role=Gtk.AccessibleRole.PRESENTATION)
        self.feedback_icon.add_css_class('feedback-icon')
        top.append(self.feedback_icon)
        self.feedback_title = Gtk.Label(xalign=0, wrap=True, hexpand=True)
        self.feedback_title.add_css_class('heading')
        self.feedback_title.add_css_class('feedback-title')
        top.append(self.feedback_title)
        self.feedback.append(top)
        if check.explanation:
            self.feedback.append(paragraph_label(check.explanation, on_term, css=('lesson-text',)))
        self.retry_button = Gtk.Button(
            label=_('_Try Again'), use_underline=True, halign=Gtk.Align.START
        )
        self.retry_button.add_css_class('pill')
        self.retry_button.connect('clicked', lambda _b: self.reset())
        self.feedback.append(self.retry_button)
        self.revealer = Gtk.Revealer(
            child=self.feedback, transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN
        )
        self.append(self.revealer)
        self.chosen: str | None = None

    @property
    def answered_correctly(self) -> bool:
        return self.chosen == self.check.answer

    def choose(self, key: str) -> None:
        if self.chosen is not None:
            return
        self.chosen = key
        correct = key == self.check.answer
        for option_key, button in self.buttons.items():
            if option_key == self.check.answer:
                button.add_css_class('success')
            elif option_key == key:
                button.add_css_class('error')
            button.set_can_target(False)
        self.feedback.remove_css_class('feedback-success')
        self.feedback.remove_css_class('feedback-error')
        if correct:
            self.feedback.add_css_class('feedback-success')
            self.feedback_icon.set_from_icon_name('object-select-symbolic')
            title = _('Correct')
        else:
            self.feedback.add_css_class('feedback-error')
            self.feedback_icon.set_from_icon_name('dialog-error-symbolic')
            answer = next(o for o in self.check.options if o.key == self.check.answer)
            # Translators: feedback on a lesson question, e.g. "Not quite — the answer is B4".
            title = _('Not quite — the answer is {answer}').format(answer=plain(answer.content))
        self.feedback_title.set_label(title)
        self.retry_button.set_visible(not correct)
        self.revealer.set_reveal_child(True)
        self.feedback.announce(
            f'{title}. {plain(self.check.explanation)}', Gtk.AccessibleAnnouncementPriority.MEDIUM
        )
        self.emit('answered', correct)

    def reset(self) -> None:
        """Answer again: retrieval practice works best when retried after feedback."""
        self.chosen = None
        for button in self.buttons.values():
            button.remove_css_class('success')
            button.remove_css_class('error')
            button.set_can_target(True)
        self.revealer.set_reveal_child(False)
        first = next(iter(self.buttons.values()), None)
        if first is not None:
            first.grab_focus()


# Glossary entries --------------------------------------------------------------------


def language_name(code: str) -> str:
    names = {
        # Translators: the language of a musical term, e.g. "crescendo — Italian".
        'it': _('Italian'),
        'de': _('German'),
        'fr': _('French'),
        'la': _('Latin'),
        'es': _('Spanish'),
        'en': _('English'),
    }
    return names.get(code, code)


def headword_text(entry: GlossaryEntry) -> str:
    """ "crescendo — Italian" for foreign terms, the term otherwise."""
    if entry.foreign and entry.foreign_language:
        # Translators: a foreign musical term and its language, e.g. "crescendo — Italian".
        return _('{term} — {language}').format(
            term=entry.foreign, language=language_name(entry.foreign_language)
        )
    return entry.headword


def entry_detail(
    entry: GlossaryEntry,
    on_term: TermHandler,
    on_play: PlayHandler,
    see_also: Sequence[GlossaryEntry] = (),
) -> Gtk.Widget:
    """Everything about one glossary entry; "See also" and links call ``on_term``."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    box.add_css_class('glossary-entry')
    box.append(heading(entry.headword, 'title-1', level=1))
    facts = []
    if entry.foreign and entry.foreign_language:
        facts.append(language_name(entry.foreign_language))
    if entry.foreign and entry.term and entry.term != entry.foreign:
        facts.append(entry.term)
    if entry.abbreviation:
        # Translators: the abbreviation of a term, e.g. "Abbreviation: cresc."
        facts.append(_('Abbreviation: {abbreviation}').format(abbreviation=entry.abbreviation))
    if facts:
        line = Gtk.Label(label=' · '.join(facts), xalign=0, wrap=True)
        line.add_css_class('dim-label')
        box.append(line)
    gloss = Gtk.Label(label=entry.gloss, xalign=0, wrap=True)
    gloss.add_css_class('glossary-gloss')
    box.append(gloss)
    box.append(paragraph_label(entry.definition, on_term, css=('lesson-text',)))
    if entry.example is not None:
        box.append(example_card(entry.example, on_play, on_term))
    if see_also:
        box.append(heading(_('See Also'), 'heading', level=2))
        links = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            column_spacing=6,
            row_spacing=6,
            max_children_per_line=6,
        )
        for other in see_also:
            button = Gtk.Button(label=other.headword)
            button.add_css_class('pill')
            button.add_css_class('see-also')
            button.connect('clicked', lambda _b, entry_id=other.id: on_term(entry_id))
            links.append(button)
        box.append(links)
    return box
