# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Symbols: read the signs of notation that are not notes.

Four groups, each a setting: dynamics (pp to ff and the crescendo and
diminuendo hairpins), articulations (staccato, accent, tenuto, fermata),
clefs, and barlines with repeat signs. Items are one symbol each,
``symbol.dynamic.mf``, ``symbol.articulation.staccato``, ``symbol.clef.alto`` or
``symbol.bar.repeat-end``; the options are the other symbols of the group,
which are exactly the ones learners mix up.

Dynamics are answered by meaning ("moderately loud"), the other groups by
name with the meaning underneath. Dynamics and articulations are drawn as
:class:`~etude.notation.spec.GlyphFigure` (articulations on a note on a
staff, above or below it); clefs and barlines are ordinary staves. Every
figure has its own description, which never names the symbol.

Feedback explains the symbol, adds the glossary's gloss when the glossary
has an entry for it, and plays what the symbol does to a few notes
(louder, shorter, held …) where sound can show it.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from gettext import gettext as _
from typing import ClassVar, cast

from ...audio.spec import PlaybackNote, PlaybackSpec
from ...content.library import ContentLibrary, default_library
from ...core import Pitch
from ...learning.model import ItemId
from ...notation.spec import (
    Barline,
    BarStyle,
    Chord,
    Clef,
    Event,
    Figure,
    GlyphFigure,
    Head,
    StaffSpec,
)
from ..base import (
    ChoiceAnswer,
    ExerciseDefinition,
    Family,
    Feedback,
    Modality,
    MultiChoiceSetting,
    Option,
    Question,
    Setting,
)

GROUPS = ('dynamic', 'articulation', 'clef', 'bar')


@dataclass(frozen=True, slots=True)
class Symbol:
    group: str
    key: str
    glossary: str
    """Id of the glossary entry that explains the symbol, if the glossary has one."""
    velocity: int = 80


SYMBOLS: tuple[Symbol, ...] = (
    Symbol('dynamic', 'pp', 'pianissimo', 30),
    Symbol('dynamic', 'p', 'piano', 45),
    Symbol('dynamic', 'mp', 'mezzo-piano', 60),
    Symbol('dynamic', 'mf', 'mezzo-forte', 75),
    Symbol('dynamic', 'f', 'forte', 95),
    Symbol('dynamic', 'ff', 'fortissimo', 115),
    Symbol('dynamic', 'cresc', 'crescendo'),
    Symbol('dynamic', 'dim', 'diminuendo'),
    Symbol('articulation', 'staccato', 'staccato'),
    Symbol('articulation', 'accent', 'accent'),
    Symbol('articulation', 'tenuto', 'tenuto'),
    Symbol('articulation', 'fermata', 'fermata'),
    Symbol('clef', 'treble', 'treble-clef'),
    Symbol('clef', 'bass', 'bass-clef'),
    Symbol('clef', 'alto', 'alto-clef'),
    Symbol('clef', 'tenor', 'tenor-clef'),
    Symbol('bar', 'repeat-start', 'repeat-sign'),
    Symbol('bar', 'repeat-end', 'repeat-sign'),
    Symbol('bar', 'double', 'double-barline'),
    Symbol('bar', 'final', 'final-barline'),
)
_BY_ID = {f'symbol.{s.group}.{s.key}': s for s in SYMBOLS}

_DYNAMIC_GLYPHS = {
    'pp': 'dynamicPP',
    'p': 'dynamicPiano',
    'mp': 'dynamicMP',
    'mf': 'dynamicMF',
    'f': 'dynamicForte',
    'ff': 'dynamicFF',
    'cresc': 'dynamicCrescendoHairpin',
    'dim': 'dynamicDiminuendoHairpin',
}
_ARTICULATION_GLYPHS = {
    'staccato': 'articStaccato',
    'accent': 'articAccent',
    'tenuto': 'articTenuto',
    'fermata': 'fermata',
}
_CLEFS = {'treble': Clef.TREBLE, 'bass': Clef.BASS, 'alto': Clef.ALTO, 'tenor': Clef.TENOR}
_BARS = {
    'repeat-start': BarStyle.REPEAT_START,
    'repeat-end': BarStyle.REPEAT_END,
    'double': BarStyle.DOUBLE,
    'final': BarStyle.FINAL,
}
_PHRASE = tuple(Pitch.parse(p) for p in ('C4', 'E4', 'G4', 'C5', 'G4', 'E4', 'C4'))


def item_id(symbol: Symbol) -> ItemId:
    return ItemId(f'symbol.{symbol.group}.{symbol.key}')


def parse_item(item: str) -> Symbol:
    """The symbol of an item id; raises :class:`ValueError` for other ids."""
    try:
        return _BY_ID[item]
    except KeyError:
        raise ValueError(f'not a symbol item: {item!r}') from None


# Words -------------------------------------------------------------------------------


def _labels() -> dict[str, str]:
    return {
        # Translators: answer options for dynamics: what the marking means.
        'pp': _('Very soft'),
        'p': _('Soft'),
        'mp': _('Moderately soft'),
        'mf': _('Moderately loud'),
        'f': _('Loud'),
        'ff': _('Very loud'),
        'cresc': _('Gradually louder'),
        'dim': _('Gradually softer'),
        'staccato': _('Staccato'),
        'accent': _('Accent'),
        'tenuto': _('Tenuto'),
        'fermata': _('Fermata'),
        'treble': _('Treble clef'),
        'bass': _('Bass clef'),
        'alto': _('Alto clef'),
        'tenor': _('Tenor clef'),
        'repeat-start': _('Start repeat'),
        'repeat-end': _('End repeat'),
        'double': _('Double barline'),
        'final': _('Final barline'),
    }


def _captions() -> dict[str, str]:
    """Second lines of the options that are names."""
    return {
        'staccato': _('Short, detached'),
        'accent': _('Stressed'),
        'tenuto': _('Held its full length'),
        'fermata': _('Pause: hold longer'),
        'treble': _('G clef'),
        'bass': _('F clef'),
        'alto': _('C clef'),
        'tenor': _('C clef'),
        'repeat-start': _('Repeat from here'),
        'repeat-end': _('Go back and repeat'),
        'double': _('End of a section'),
        'final': _('End of the piece'),
    }


def _facts() -> dict[str, str]:
    return {
        'pp': _('pp stands for pianissimo, Italian for “very soft”.'),
        'p': _('p stands for piano, Italian for “soft”.'),
        'mp': _('mp stands for mezzo piano, “moderately soft”: mezzo means “half”.'),
        'mf': _('mf stands for mezzo forte, “moderately loud”: mezzo means “half”.'),
        'f': _('f stands for forte, Italian for “loud”.'),
        'ff': _('ff stands for fortissimo, Italian for “very loud”.'),
        'cresc': _(
            'A hairpin opening to the right is a crescendo: get gradually louder. It can '
            'also be written cresc.'
        ),
        'dim': _(
            'A hairpin closing to the right is a diminuendo (or decrescendo): get gradually '
            'softer. It can also be written dim.'
        ),
        'staccato': _(
            'A dot above or below the notehead is staccato: play the note short and detached.'
        ),
        'accent': _('A wedge > above or below the notehead is an accent: stress the note.'),
        'tenuto': _(
            'A short line above or below the notehead is tenuto: hold the note its full '
            'length, perhaps with slight weight.'
        ),
        'fermata': _(
            'An arc with a dot is a fermata: hold the note longer than written, as long as '
            'feels right.'
        ),
        'treble': _(
            'The treble clef, or G clef, curls around the second line from the bottom: that '
            'line is G4.'
        ),
        'bass': _(
            'The bass clef, or F clef, has two dots around the fourth line from the bottom: '
            'that line is F3.'
        ),
        'alto': _(
            'A C clef centred on the middle line is the alto clef: the middle line is middle '
            'C. Violas read it.'
        ),
        'tenor': _(
            'A C clef centred on the fourth line from the bottom is the tenor clef: that line '
            'is middle C. Cellos, bassoons and trombones use it for high passages.'
        ),
        'repeat-start': _(
            'A thick and a thin line with two dots after them start a repeat: the passage from '
            'here to the end repeat is played twice.'
        ),
        'repeat-end': _(
            'Two dots before a thin and a thick line end a repeat: go back to the start repeat '
            '(or to the beginning) and play the passage again.'
        ),
        'double': _('Two thin lines are a double barline: the end of a section.'),
        'final': _('A thin and a thick line are the final barline: the end of the piece.'),
    }


def _group_names() -> dict[str, str]:
    return {
        'dynamic': _('Dynamics'),
        'articulation': _('Articulations'),
        'clef': _('Clefs'),
        'bar': _('Barlines and repeats'),
    }


# Figures and sound -------------------------------------------------------------------


def figure_for(symbol: Symbol, rng: random.Random) -> Figure:
    """The symbol as the learner meets it, with a description that does not name it."""
    if symbol.group == 'dynamic':
        description = (
            _('A hairpin marking.')
            if symbol.key in ('cresc', 'dim')
            else _('A dynamic marking in bold italic letters.')
        )
        return GlyphFigure((_DYNAMIC_GLYPHS[symbol.key],), description)
    if symbol.group == 'articulation':
        base = _ARTICULATION_GLYPHS[symbol.key]
        below = symbol.key != 'fermata' and rng.random() < 0.5
        glyphs = ('noteQuarterUp', f'{base}Below') if below else ('noteQuarterDown', f'{base}Above')
        return GlyphFigure(glyphs, _('A note on a staff with a mark at its notehead.'), staff=True)
    if symbol.group == 'clef':
        return StaffSpec(clef=_CLEFS[symbol.key], description=_('A staff with a clef.'))
    pitches = rng.sample(('C5', 'D5', 'E5', 'F5', 'G5', 'A4', 'B4'), 4)
    notes = tuple(Chord((Head(Pitch.parse(p)),)) for p in pitches)
    bar = Barline(_BARS[symbol.key])
    events: tuple[Event, ...] = (
        (bar, *notes, Barline()) if symbol.key == 'repeat-start' else (*notes, bar)
    )
    return StaffSpec(events=events, description=_('A short passage of notes ending with a bar.'))


def _phrase(velocities: Sequence[int], lengths: Sequence[Fraction]) -> PlaybackSpec:
    notes = tuple(
        PlaybackNote(p.midi, Fraction(i), length, velocity)
        for i, (p, velocity, length) in enumerate(zip(_PHRASE, velocities, lengths, strict=True))
    )
    return PlaybackSpec(notes, tempo=100.0)


def demonstration(symbol: Symbol) -> PlaybackSpec | None:
    """A few notes that do what the symbol says, or ``None`` for clefs and barlines."""
    count = len(_PHRASE)
    full = [Fraction(1)] * count
    match symbol.group, symbol.key:
        case 'dynamic', 'cresc':
            return _phrase([30 + 14 * i for i in range(count)], full)
        case 'dynamic', 'dim':
            return _phrase([115 - 14 * i for i in range(count)], full)
        case 'dynamic', _:
            return _phrase([symbol.velocity] * count, full)
        case 'articulation', 'staccato':
            return _phrase([80] * count, [Fraction(1, 4)] * count)
        case 'articulation', 'accent':
            return _phrase([115 if i % 2 == 0 else 60 for i in range(count)], full)
        case 'articulation', 'tenuto':
            return _phrase([85] * count, full)
        case 'articulation', 'fermata':
            return _phrase([80] * count, [*full[:-1], Fraction(4)])
    return None


# The exercise ------------------------------------------------------------------------


def _safe_library(provider: Callable[[], ContentLibrary]) -> ContentLibrary | None:
    try:
        return provider()
    except (OSError, ValueError):
        return None


class Symbols(ExerciseDefinition):
    id = 'symbols'
    item_prefix = 'symbol.'
    family = Family.NOTATION
    modality = Modality.EYE
    level = 1
    icon_name = 'symbols-symbolic'
    glyph = 'ƒ'
    settings: ClassVar[tuple[Setting, ...]] = (
        MultiChoiceSetting(
            'groups',
            _('Symbols'),
            tuple(Option(key, label) for key, label in _group_names().items()),
            GROUPS,
        ),
    )

    def __init__(self, library: Callable[[], ContentLibrary] = default_library) -> None:
        self._library = library

    @property
    def title(self) -> str:
        return _('Symbols')

    @property
    def description(self) -> str:
        return _('Dynamics, articulations, clefs and repeat signs.')

    @property
    def play_label(self) -> str:
        return _('Play example')

    def _groups(self, settings: Mapping[str, object]) -> list[str]:
        chosen = settings.get('groups', GROUPS)
        keys = set(cast(Sequence[str], chosen)) if isinstance(chosen, list | tuple) else set()
        return [g for g in GROUPS if g in keys] or list(GROUPS)

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        groups = self._groups(settings)
        if len(groups) == len(GROUPS):
            return _('All symbols')
        names = _group_names()
        # Translators: separator between the groups of symbols in a subtitle.
        return _(', ').join(names[g] for g in groups)

    def item_label(self, item_id: ItemId) -> str:
        symbol = parse_item(item_id)
        if symbol.group == 'dynamic':
            # Translators: an item in "Weakest items", e.g. "mf — moderately loud". {symbol}
            # is the dynamic marking itself, {meaning} its meaning.
            return _('{symbol} — {meaning}').format(
                symbol=symbol.key if symbol.key not in ('cresc', 'dim') else symbol.key + '.',
                meaning=_labels()[symbol.key].lower(),
            )
        return _labels()[symbol.key]

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        groups = self._groups(settings)
        return [item_id(s) for g in groups for s in SYMBOLS if s.group == g]

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        partners = {
            'pp': ('p',),
            'p': ('pp', 'mp'),
            'mp': ('mf', 'p'),
            'mf': ('mp', 'f'),
            'f': ('ff', 'mf'),
            'ff': ('f',),
            'cresc': ('dim',),
            'dim': ('cresc',),
            'staccato': ('tenuto',),
            'tenuto': ('staccato', 'accent'),
            'accent': ('tenuto',),
            'alto': ('tenor',),
            'tenor': ('alto',),
            'repeat-start': ('repeat-end',),
            'repeat-end': ('repeat-start', 'final'),
            'double': ('final',),
            'final': ('double', 'repeat-end'),
        }
        symbol = parse_item(item_id)
        return [ItemId(f'symbol.{symbol.group}.{k}') for k in partners.get(symbol.key, ())]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        symbol = parse_item(item_id)
        labels, captions = _labels(), _captions()
        group = [s for s in SYMBOLS if s.group == symbol.group]
        options = tuple(
            Option(s.key, labels[s.key], accel=str(i + 1), description=captions.get(s.key))
            for i, s in enumerate(group)
        )
        prompts = {
            'dynamic': _('What does this marking mean?'),
            'articulation': _('What is the mark at the notehead called?'),
            'clef': _('Which clef is this?'),
            'bar': _('What is the barline at the end of the bar?'),
        }
        if symbol.key == 'repeat-start':
            prompts['bar'] = _('What is the barline at the start?')
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=prompts[symbol.group],
            answer=ChoiceAnswer(options),
            expected=symbol.key,
            figure=figure_for(symbol, rng),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        symbol = parse_item(question.item_id)
        expected = str(question.expected)
        correct = str(given) == expected
        label = self.answer_label(question, expected)
        if correct:
            # Translators: e.g. "Correct — moderately loud".
            title = _('Correct — {answer}').format(answer=label)
        else:
            # Translators: e.g. "Not quite — the answer is staccato".
            title = _('Not quite — the answer is {answer}').format(answer=label)
        sentences = [_facts()[symbol.key]]
        library = _safe_library(self._library)
        entry = library.glossary.get(symbol.glossary) if library is not None else None
        if entry is not None:
            # Translators: the glossary's short definition, e.g. "Glossary: crescendo —
            # gradually louder."
            sentences.append(
                _('Glossary: {term} — {gloss}.').format(term=entry.headword, gloss=entry.gloss)
            )
        if not correct and str(given) in _labels() and str(given) != expected:
            # Translators: what the learner's answer would have looked like.
            sentences.append(_('For comparison: {text}').format(text=_facts()[str(given)]))
        given_symbol = _BY_ID.get(f'symbol.{symbol.group}.{given}')
        return Feedback(
            correct=correct,
            title=title,
            detail=' '.join(sentences),
            expected_label=label,
            play_expected=demonstration(symbol),
            play_given=(
                demonstration(given_symbol) if given_symbol is not None and not correct else None
            ),
        )

    def answer_label(self, question: Question, value: object) -> str:
        label = _labels().get(str(value))
        if label is None:
            return super().answer_label(question, value)
        if parse_item(question.item_id).group in ('dynamic', 'articulation'):
            return label[:1].lower() + label[1:]
        return label

    def serialize(self, value: object) -> str:
        return str(value)


EXERCISES: tuple[ExerciseDefinition, ...] = (Symbols(),)
