# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Intervals: name them on the staff (design 1d) and by ear (design 1e).

Items are intervals. On the staff they are spelled intervals,
``interval.staff.M6`` or ``interval.staff.A4``, and the clef, root,
direction and melodic or harmonic form are surface variations chosen per
question. By default the tritone is one item, ``interval.staff.TT``, written
as an augmented fourth or a diminished fifth; with "Augmented and
diminished" turned on it is replaced by ``A4`` and ``d5`` (and other
augmented and diminished intervals join the pool), because the learner
must then tell the spellings apart.

By ear only the size counts, but listeners hear an interval differently
going up, going down and sounding together, so these are separate items:
``interval.ear.melodic.asc.m6``, ``interval.ear.melodic.desc.m6`` and
``interval.ear.harmonic.TT``.

Options are the intervals of the learner's pool in order of size. A pool
of more than eight shows a window of eight neighbouring intervals that
contains the answer, at a random offset so its position gives nothing
away; neighbours by size are exactly the confusable ones (minor and major
sixth, tritone and perfect fifth). Every option keeps a number key 1–8.

Explanations count letter names for the number and semitones for the
quality: "G4 to E5 spans six letter names and nine semitones."

The staff figure's accessible description names both notes. That is the
information a sighted learner reads from the staff; naming the interval
from it still takes the counting this exercise trains, so it gives nothing
away.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from gettext import gettext as _
from gettext import ngettext, pgettext
from typing import ClassVar, cast

from ...audio.spec import PlaybackSpec
from ...core import Interval, Letter, Pitch, PitchName
from ...core.naming import interval_name, pitch_name
from ...learning.model import ItemId
from ...notation.spec import Bracket, Chord, Clef, Figure, Head, StaffSpec
from ..base import (
    BoolSetting,
    ChoiceAnswer,
    ChoiceSetting,
    ExerciseDefinition,
    Family,
    Feedback,
    Modality,
    MultiChoiceSetting,
    Option,
    Question,
    Setting,
)

TRITONE = 'TT'
"""Key of the tritone, the six-semitone interval without a spelling."""

SIMPLE = ('m2', 'M2', 'm3', 'M3', 'P4', 'TT', 'P5', 'm6', 'M6', 'm7', 'M7', 'P8')
"""The intervals within an octave, in order of size (the pool setting)."""

TEACHING_ORDER = ('P5', 'P8', 'M3', 'm3', 'P4', 'M2', 'm2', 'M6', 'm6', 'm7', 'M7', 'TT')
"""Stable, easily sung intervals first, then sixths, sevenths and the tritone."""

COMPOUND = ('M10', 'm10', 'P12', 'P11', 'M9', 'm9', 'M13', 'm13')
"""Compound intervals in teaching order: tenths and twelfths are heard most often."""

ALTERED = ('A4', 'd5', 'A2', 'd7', 'A5', 'd4', 'A6', 'd3')
"""Augmented and diminished intervals in teaching order: the tritone's two
spellings, then those of harmonic minor (A2, d7), the augmented triad (A5,
d4) and augmented sixth chords (A6, d3)."""

_TRITONE_SPELLINGS = ('A4', 'd5')

# Pairs that learners confuse, by ear or by spelling.
_CONFUSABLE: dict[str, tuple[str, ...]] = {
    'm2': ('M2',),
    'M2': ('m2', 'm3'),
    'm3': ('M3', 'M2'),
    'M3': ('m3', 'P4'),
    'P4': ('P5', 'TT', 'M3'),
    'TT': ('P5', 'P4'),
    'P5': ('TT', 'P4', 'm6'),
    'm6': ('M6', 'P5'),
    'M6': ('m6', 'm7'),
    'm7': ('M7', 'M6'),
    'M7': ('m7', 'P8'),
    'P8': ('M7',),
    'm9': ('M9', 'm2'),
    'M9': ('m9', 'M2'),
    'm10': ('M10', 'm3'),
    'M10': ('m10', 'M3'),
    'P11': ('P12', 'P4'),
    'P12': ('P11', 'P5'),
    'm13': ('M13', 'm6'),
    'M13': ('m13', 'M6'),
    'A4': ('d5', 'P4'),
    'd5': ('A4', 'P5'),
    'A2': ('m3', 'M2'),
    'd3': ('M2', 'm3'),
    'd4': ('M3', 'P4'),
    'A5': ('m6', 'P5'),
    'A6': ('m7', 'M6'),
    'd7': ('M6', 'm7'),
}

MAX_OPTIONS = 8
"""The design's grid: two rows of four, numbered 1–8."""
MIN_OPTIONS = 4
"""A pool smaller than this is padded with its neighbours, so a question never
offers only the answer."""

_CLEFS = {
    'treble': Clef.TREBLE,
    'bass': Clef.BASS,
    'alto': Clef.ALTO,
    'tenor': Clef.TENOR,
}
# Staff positions used for notes (0 = bottom line, 8 = top line): one ledger
# line for simple intervals, two for compound ones.
_SIMPLE_RANGE = (-2, 10)
_COMPOUND_RANGE = (-4, 12)
_STAFF_TOP = 8

# Roots heard in ear training: naturals and the common black-key spellings.
_EAR_ROOTS = tuple(
    PitchName.parse(text)
    for text in ('C', 'C#', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B')
)
# MIDI range of the lower note and highest upper note heard.
_EAR_SIMPLE_RANGE = (48, 67, 81)
_EAR_COMPOUND_RANGE = (41, 60, 84)


# Interval keys ------------------------------------------------------------------------


def interval_for(key: str) -> Interval:
    """The interval of an option or item key; the tritone is spelled as an augmented fourth."""
    return Interval.parse('A4' if key == TRITONE else key)


def semitones(key: str) -> int:
    return interval_for(key).semitones


def _staff_order(key: str) -> tuple[float, int]:
    """Written order: by number, then size; the tritone sits between fourths and fifths."""
    if key == TRITONE:
        return (4.5, 6)
    interval = Interval.parse(key)
    return (float(interval.number), interval.semitones)


def _ear_order(key: str) -> tuple[float, int]:
    return (float(semitones(key)), 0)


_NAME_CACHE: dict[str, dict[str, str]] = {}


def _name(interval: Interval) -> str:
    """:func:`~etude.core.naming.interval_name`, memoised per translation.

    ``interval_name`` translates its whole table of about eighty names on every
    call, which made generating and grading noticeably slow; the cache is keyed
    by a translated probe string so it follows the language.
    """
    probe = _('Tritone')
    names = _NAME_CACHE.get(probe)
    if names is None:
        _NAME_CACHE.clear()
        names = _NAME_CACHE.setdefault(probe, {})
    key = str(interval)
    name = names.get(key)
    if name is None:
        name = names[key] = interval_name(interval)
    return name


def interval_label(key: str) -> str:
    """Option label, e.g. "Major sixth" or "Tritone"."""
    if key == TRITONE:
        # Translators: answer option for the six-semitone interval.
        return _('Tritone')
    name = _name(Interval.parse(key))
    return name[:1].upper() + name[1:]


def interval_phrase(key: str) -> str:
    """Name inside a sentence, e.g. "major sixth" or "tritone"."""
    if key == TRITONE:
        # Translators: the six-semitone interval inside a sentence, e.g. "Correct — tritone".
        return _('tritone')
    return _name(Interval.parse(key))


def _takes_an(key: str) -> bool:
    """English needs "an" before "augmented"; other interval names take "a"."""
    return key.startswith('A')


# Number words for explanations; looked up one at a time because every gettext call
# costs a catalogue lookup.
_NUMBER_WORDS: tuple[Callable[[], str], ...] = (
    lambda: pgettext('counting word', 'zero'),
    lambda: pgettext('counting word', 'one'),
    lambda: pgettext('counting word', 'two'),
    lambda: pgettext('counting word', 'three'),
    lambda: pgettext('counting word', 'four'),
    lambda: pgettext('counting word', 'five'),
    lambda: pgettext('counting word', 'six'),
    lambda: pgettext('counting word', 'seven'),
    lambda: pgettext('counting word', 'eight'),
    lambda: pgettext('counting word', 'nine'),
    lambda: pgettext('counting word', 'ten'),
    lambda: pgettext('counting word', 'eleven'),
    lambda: pgettext('counting word', 'twelve'),
    lambda: pgettext('counting word', 'thirteen'),
    lambda: pgettext('counting word', 'fourteen'),
    lambda: pgettext('counting word', 'fifteen'),
    lambda: pgettext('counting word', 'sixteen'),
    lambda: pgettext('counting word', 'seventeen'),
    lambda: pgettext('counting word', 'eighteen'),
    lambda: pgettext('counting word', 'nineteen'),
    lambda: pgettext('counting word', 'twenty'),
    lambda: pgettext('counting word', 'twenty-one'),
    lambda: pgettext('counting word', 'twenty-two'),
    lambda: pgettext('counting word', 'twenty-three'),
    lambda: pgettext('counting word', 'twenty-four'),
)


def _number_word(count: int) -> str:
    """The word for ``count``, e.g. "nine"; digits beyond twenty-four."""
    return _NUMBER_WORDS[count]() if 0 <= count < len(_NUMBER_WORDS) else str(count)


def _letters(count: int) -> str:
    # Translators: part of "G4 to E5 spans six letter names and nine semitones."
    # {count} is a number word.
    return ngettext('{count} letter name', '{count} letter names', count).format(
        count=_number_word(count)
    )


def _semitones(count: int) -> str:
    # Translators: part of "G4 to E5 spans six letter names and nine semitones."
    # {count} is a number word.
    return ngettext('{count} semitone', '{count} semitones', count).format(
        count=_number_word(count)
    )


def note_label(pitch: Pitch) -> str:
    """A note with its octave in the learner's naming convention, e.g. "G4"."""
    return pitch_name(pitch.name) + str(pitch.octave)


# Settings ------------------------------------------------------------------------------


def _pool_setting() -> MultiChoiceSetting:
    return MultiChoiceSetting(
        'intervals',
        _('Intervals'),
        tuple(Option(key, interval_label(key)) for key in SIMPLE),
        SIMPLE,
    )


def _compound_setting() -> BoolSetting:
    return BoolSetting(
        'compound',
        _('Compound intervals'),
        False,
        subtitle=_('Ninths to thirteenths'),
    )


def _form_setting(default: str, *, written: bool) -> ChoiceSetting:
    return ChoiceSetting(
        'form',
        _('Written as') if written else _('Played as'),
        (
            Option('melodic', _('Melodic')),
            Option('harmonic', _('Harmonic')),
            Option('both', _('Melodic and harmonic')),
        ),
        default,
        subtitle=(
            _('Notes side by side, or stacked')
            if written
            else _('One note after the other, or both together')
        ),
    )


def _direction_setting(default: str) -> ChoiceSetting:
    return ChoiceSetting(
        'direction',
        _('Direction'),
        (
            Option('asc', _('Ascending')),
            Option('desc', _('Descending')),
            Option('both', _('Both directions')),
        ),
        default,
        subtitle=_('For melodic intervals'),
    )


def _choice(settings: Mapping[str, object], key: str, allowed: Sequence[str], default: str) -> str:
    value = str(settings.get(key, default))
    return value if value in allowed else default


def _selected(settings: Mapping[str, object]) -> list[str]:
    chosen = settings.get('intervals', SIMPLE)
    keys = set(cast(Sequence[str], chosen)) if isinstance(chosen, list | tuple) else set(SIMPLE)
    return [key for key in TEACHING_ORDER if key in keys] or list(TEACHING_ORDER)


def _forms(settings: Mapping[str, object], default: str) -> tuple[str, ...]:
    choice = _choice(settings, 'form', ('melodic', 'harmonic', 'both'), default)
    return ('melodic', 'harmonic') if choice == 'both' else (choice,)


def _directions(settings: Mapping[str, object], default: str) -> tuple[str, ...]:
    choice = _choice(settings, 'direction', ('asc', 'desc', 'both'), default)
    return ('asc', 'desc') if choice == 'both' else (choice,)


# Options -------------------------------------------------------------------------------


def _without_conflicts(keys: Sequence[str], expected: str) -> list[str]:
    """The tritone and its spellings never appear together: one of them would be
    a second right answer."""
    if expected == TRITONE:
        return [k for k in keys if k not in _TRITONE_SPELLINGS]
    if expected in _TRITONE_SPELLINGS or set(keys) & set(_TRITONE_SPELLINGS):
        return [k for k in keys if k != TRITONE]
    return list(keys)


def choose_options(
    pool: Sequence[str],
    expected: str,
    rng: random.Random,
    *,
    spare: Sequence[str],
    written: bool,
) -> tuple[Option, ...]:
    """Up to eight numbered options in order of size, always including ``expected``
    and the interval it is most often confused with.

    ``spare`` pads a pool smaller than :data:`MIN_OPTIONS` with the intervals
    nearest in size. ``written`` sorts by number before size (thirds together)
    for questions read from the staff.
    """
    order = _staff_order if written else _ear_order
    keys = _without_conflicts(list(dict.fromkeys([*pool, expected])), expected)
    if len(keys) < MIN_OPTIONS:
        extra = [k for k in _without_conflicts(spare, expected) if k not in keys]
        extra.sort(key=lambda k: (abs(semitones(k) - semitones(expected)), order(k)))
        keys.extend(extra[: MIN_OPTIONS - len(keys)])
    keys.sort(key=order)
    if len(keys) > MAX_OPTIONS:
        # The window always holds the answer and its closest confusable partner.
        partner = next((k for k in _CONFUSABLE.get(expected, ()) if k in keys), expected)
        required = (keys.index(expected), keys.index(partner))
        low = max(0, max(required) - MAX_OPTIONS + 1)
        high = min(min(required), len(keys) - MAX_OPTIONS)
        start = rng.randint(low, high)
        keys = keys[start : start + MAX_OPTIONS]
    return tuple(
        Option(key, interval_label(key), accel=str(number))
        for number, key in enumerate(keys, start=1)
    )


# Figures -------------------------------------------------------------------------------


def _staff_name(clef: Clef) -> str:
    names = {
        Clef.TREBLE: _('Treble staff'),
        Clef.BASS: _('Bass staff'),
        Clef.ALTO: _('Alto staff'),
        Clef.TENOR: _('Tenor staff'),
    }
    return names.get(clef, _('Treble staff'))


def interval_figure(clef: Clef, first: Pitch, second: Pitch, *, harmonic: bool) -> StaffSpec:
    """Two stemless notes side by side, or stacked when ``harmonic``, with the
    design's "?" bracket."""
    staff = _staff_name(clef)
    if harmonic:
        low, high = sorted((first, second), key=lambda p: p.diatonic_index)
        # Translators: accessible description of a harmonic interval, e.g.
        # "Treble staff with two notes sounding together, G4 and E5."
        description = _('{staff} with two notes sounding together, {low} and {high}.').format(
            staff=staff, low=note_label(low), high=note_label(high)
        )
        return StaffSpec(
            clef=clef,
            events=(Chord((Head(low), Head(high))),),
            brackets=(Bracket(0, 0, '?'),),
            description=description,
        )
    # Translators: accessible description of a melodic interval, e.g.
    # "Treble staff with two notes, G4 then E5."
    description = _('{staff} with two notes, {first} then {second}.').format(
        staff=staff, first=note_label(first), second=note_label(second)
    )
    return StaffSpec(
        clef=clef,
        events=(Chord((Head(first),)), Chord((Head(second),))),
        brackets=(Bracket(0, 1, '?'),),
        description=description,
    )


@dataclass(frozen=True, slots=True)
class Notes:
    """The two notes of an interval figure, as the learner meets them."""

    first: Pitch
    second: Pitch
    harmonic: bool

    @property
    def low(self) -> Pitch:
        return min(self.first, self.second, key=lambda p: p.diatonic_index)

    @property
    def high(self) -> Pitch:
        return max(self.first, self.second, key=lambda p: p.diatonic_index)

    @property
    def descending(self) -> bool:
        return not self.harmonic and self.first.diatonic_index > self.second.diatonic_index

    @property
    def interval(self) -> Interval:
        return Interval.between(self.low, self.high)

    @classmethod
    def of(cls, figure: Figure | None) -> Notes:
        """Read the notes back from a figure made by :func:`interval_figure`."""
        if not isinstance(figure, StaffSpec):
            raise ValueError('not an interval figure')
        chords = [e for e in figure.events if isinstance(e, Chord)]
        if len(chords) == 1 and len(chords[0].heads) == 2:
            low, high = chords[0].heads
            return cls(low.pitch, high.pitch, harmonic=True)
        if len(chords) == 2 and all(len(c.heads) == 1 for c in chords):
            return cls(chords[0].heads[0].pitch, chords[1].heads[0].pitch, harmonic=False)
        raise ValueError('not an interval figure')

    def playback(self) -> PlaybackSpec:
        if self.harmonic:
            return PlaybackSpec.harmonic([self.low, self.high])
        return PlaybackSpec.melodic([self.first, self.second])

    def playback_of(self, key: str) -> PlaybackSpec:
        """The interval ``key`` from the same first note, in the same direction and form."""
        size = semitones(key)
        if self.harmonic:
            return PlaybackSpec.harmonic([self.low, Pitch.from_midi(self.low.midi + size)])
        step = -size if self.descending else size
        return PlaybackSpec.melodic([self.first, Pitch.from_midi(self.first.midi + step)])


# Shared behaviour ----------------------------------------------------------------------


class _IntervalExercise(ExerciseDefinition):
    """Grading and explanations shared by the staff and ear exercises."""

    written: ClassVar[bool]
    """Options and explanations follow spelling (staff) or only size (ear)."""

    @property
    def play_label(self) -> str:
        return _('Play interval')

    def _figure(self, question: Question) -> Figure | None:
        return question.figure

    def grade(self, question: Question, given: object) -> Feedback:
        expected = str(question.expected)
        given_key = str(given)
        notes = Notes.of(self._figure(question))
        correct = given_key == expected
        phrase = interval_phrase(expected)
        if correct:
            # Translators: e.g. "Correct — major sixth".
            title = _('Correct — {interval}').format(interval=phrase)
        elif _takes_an(expected):
            # Translators: e.g. "Not quite — the answer is an augmented fourth". This form is
            # used where English needs "an"; translate it like the "a" form if your language
            # makes no such distinction.
            title = _('Not quite — the answer is an {interval}').format(interval=phrase)
        else:
            # Translators: e.g. "Not quite — the answer is a major sixth".
            title = _('Not quite — the answer is a {interval}').format(interval=phrase)
        offered = isinstance(question.answer, ChoiceAnswer) and any(
            o.key == given_key for o in question.answer.options
        )
        return Feedback(
            correct=correct,
            title=title,
            detail=self._explanation(
                notes, expected, None if correct or not offered else given_key
            ),
            expected_label=self.answer_label(question, expected),
            play_expected=question.playback,
            play_given=notes.playback_of(given_key) if offered and not correct else None,
        )

    def answer_label(self, question: Question, value: object) -> str:
        key = str(value)
        try:
            return interval_phrase(key)
        except ValueError:
            return key

    def serialize(self, value: object) -> str:
        return str(value)

    def item_key(self, item_id: ItemId) -> str:
        """The interval key at the end of an item id."""
        return item_id.rsplit('.', 1)[-1]

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        """Items that learners confuse with ``item_id`` (same direction and form),
        for placing them next to each other in a session (interleaving)."""
        stem, key = item_id.rsplit('.', 1)
        return [ItemId(f'{stem}.{partner}') for partner in _CONFUSABLE.get(key, ())]

    # Explanations

    def _explanation(self, notes: Notes, expected: str, given: str | None) -> str:
        written = notes.interval
        letters = _letters(written.number)
        size = _semitones(written.semitones)
        low, high = note_label(notes.low), note_label(notes.high)
        if notes.descending:
            # Translators: e.g. "E5 down to G4 spans six letter names and nine semitones."
            span = _('{high} down to {low} spans {letters} and {semitones}.')
        else:
            # Translators: e.g. "G4 to E5 spans six letter names and nine semitones."
            span = _('{low} to {high} spans {letters} and {semitones}.')
        sentences = [span.format(low=low, high=high, letters=letters, semitones=size)]
        if expected == TRITONE:
            if self.written and written.number == 4:
                sentences.append(
                    _('Written across four letter names, this tritone is an augmented fourth.')
                )
            elif self.written:
                sentences.append(
                    _('Written across five letter names, this tritone is a diminished fifth.')
                )
            else:
                sentences.append(_('A tritone splits the octave exactly in half: six semitones.'))
        elif written.is_compound:
            # Translators: e.g. "A major tenth is a major third plus an octave."
            sentences.append(
                _('A {compound} is a {simple} plus an octave.').format(
                    compound=_name(written), simple=_name(written.simple())
                )
            )
        if given is not None:
            sentences.append(self._comparison(expected, given))
        return ' '.join(sentences)

    def _comparison(self, expected: str, given: str) -> str:
        """What the learner's answer would have looked or sounded like."""
        phrase = interval_phrase(given)
        by_letters = (
            self.written
            and TRITONE not in (expected, given)
            and Interval.parse(expected).number != Interval.parse(given).number
        )
        if by_letters:
            count = _letters(Interval.parse(given).number)
            if _takes_an(given):
                # Translators: e.g. "An augmented fifth spans five letter names." Used where
                # English needs "an".
                template = _('An {interval} spans {count}.')
            else:
                # Translators: e.g. "A perfect fifth spans five letter names."
                template = _('A {interval} spans {count}.')
        else:
            count = _semitones(semitones(given))
            if _takes_an(given):
                # Translators: e.g. "An augmented fourth spans six semitones." Used where
                # English needs "an".
                template = _('An {interval} has {count}.')
            else:
                # Translators: e.g. "A minor sixth has eight semitones."
                template = _('A {interval} has {count}.')
        return template.format(interval=phrase, count=count)


# Intervals on the staff ----------------------------------------------------------------


def staff_item(key: str) -> ItemId:
    return ItemId(f'interval.staff.{key}')


_STAFF_KEYS = frozenset((*SIMPLE, *COMPOUND, *ALTERED))


def parse_staff_item(item: str) -> str:
    """The interval key of ``interval.staff.<key>``; raises :class:`ValueError` otherwise."""
    prefix, _sep, key = item.rpartition('.')
    if prefix != 'interval.staff' or key not in _STAFF_KEYS:
        raise ValueError(f'not a staff interval item: {item!r}')
    return key


def _max_alter(settings: Mapping[str, object]) -> int:
    choice = _choice(settings, 'accidentals', ('none', 'single', 'double'), 'single')
    return {'none': 0, 'single': 1, 'double': 2}[choice]


_UNUSUAL_ROOTS = frozenset(
    (
        PitchName(Letter.E, 1),
        PitchName(Letter.B, 1),
        PitchName(Letter.F, -1),
        PitchName(Letter.C, -1),
    )
)


def place_interval(
    interval: Interval, clef: Clef, max_alter: int, rng: random.Random
) -> tuple[Pitch, Pitch]:
    """A lower and upper note for ``interval`` on ``clef`` with at most ``max_alter``
    sharps or flats each. Spellings with fewer accidentals are more likely, and
    E♯, B♯, F♭ and C♭ are not used as the lower note unless double accidentals
    are allowed. Intervals that cannot be written without accidentals (an
    augmented second) get single ones."""
    bottom, top = _COMPOUND_RANGE if interval.is_compound else _SIMPLE_RANGE
    span = interval.number - 1
    candidates: list[tuple[Pitch, Pitch]] = []
    weights: list[int] = []
    for limit in dict.fromkeys((max_alter, max(max_alter, 1))):
        for position in range(bottom, top - span + 1):
            for alter in range(-limit, limit + 1):
                low = clef.pitch_at(position, alter)
                if limit < 2 and low.name in _UNUSUAL_ROOTS:
                    continue
                try:
                    high = low.transpose(interval)
                except ValueError:
                    continue
                if abs(high.alter) > limit:
                    continue
                candidates.append((low, high))
                # Each sharp or flat halves the weight: 8, 4, 2, then 1.
                weights.append(8 >> min(3, abs(low.alter) + abs(high.alter)))
        if candidates:
            break
    return rng.choices(candidates, weights)[0]


class IntervalsStaff(_IntervalExercise):
    id = 'interval-staff'
    item_prefix = 'interval.staff.'
    family = Family.NOTATION
    modality = Modality.EYE
    level = 1
    icon_name = 'interval-staff-symbolic'
    glyph = '♫'
    written = True
    settings: ClassVar[tuple[Setting, ...]] = (
        MultiChoiceSetting(
            'clefs',
            _('Clefs'),
            (
                Option('treble', _('Treble')),
                Option('bass', _('Bass')),
                Option('alto', _('Alto')),
                Option('tenor', _('Tenor')),
            ),
            ('treble', 'bass'),
        ),
        _pool_setting(),
        _form_setting('both', written=True),
        _direction_setting('both'),
        ChoiceSetting(
            'accidentals',
            _('Accidentals'),
            (
                Option('none', _('None')),
                Option('single', _('Sharps and flats')),
                Option('double', _('Double sharps and flats too')),
            ),
            'single',
        ),
        BoolSetting(
            'altered',
            _('Augmented and diminished'),
            False,
            subtitle=_('Tell augmented fourths from diminished fifths, and more'),
        ),
        _compound_setting(),
    )

    @property
    def title(self) -> str:
        return _('Intervals — Staff')

    @property
    def description(self) -> str:
        return _('Identify intervals written on the staff.')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        clefs = [c for c in cast(Sequence[str], settings.get('clefs', ())) if c in _CLEFS]
        names = {
            'treble': _('Treble clef'),
            'bass': _('Bass clef'),
            'alto': _('Alto clef'),
            'tenor': _('Tenor clef'),
        }
        parts = [names[clefs[0]] if len(clefs) == 1 else _('Mixed clefs')]
        form = _choice(settings, 'form', ('melodic', 'harmonic', 'both'), 'both')
        if form == 'melodic':
            parts.append(_('melodic'))
        elif form == 'harmonic':
            parts.append(_('harmonic'))
        if settings.get('altered'):
            parts.append(_('augmented and diminished'))
        if settings.get('compound'):
            parts.append(_('compound'))
        # Translators: separator between the parts of an exercise subtitle.
        return _(' · ').join(parts)

    def item_label(self, item_id: ItemId) -> str:
        # Translators: an item in "Weakest items", e.g. "Major sixth (staff)".
        return _('{interval} (staff)').format(interval=interval_label(parse_staff_item(item_id)))

    def _pool(self, settings: Mapping[str, object]) -> list[str]:
        keys = _selected(settings)
        if settings.get('altered'):
            keys = [k for k in keys if k != TRITONE] + list(ALTERED)
        if settings.get('compound'):
            keys += list(COMPOUND)
        return keys

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        return [staff_item(key) for key in self._pool(settings)]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        key = parse_staff_item(item_id)
        interval = (
            Interval.parse(rng.choice(_TRITONE_SPELLINGS))
            if key == TRITONE
            else (Interval.parse(key))
        )
        clefs = [c for c in cast(Sequence[str], settings.get('clefs', ())) if c in _CLEFS]
        clef = _CLEFS[rng.choice(clefs or ['treble'])]
        harmonic = rng.choice(_forms(settings, 'both')) == 'harmonic'
        descending = not harmonic and rng.choice(_directions(settings, 'both')) == 'desc'
        low, high = place_interval(interval, clef, _max_alter(settings), rng)
        first, second = (high, low) if descending else (low, high)
        notes = Notes(first, second, harmonic)
        spare = [*SIMPLE, *COMPOUND, *(ALTERED if settings.get('altered') else ())]
        options = choose_options(self._pool(settings), key, rng, spare=spare, written=True)
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Name the interval'),
            answer=ChoiceAnswer(options),
            expected=key,
            figure=interval_figure(clef, first, second, harmonic=harmonic),
            playback=notes.playback(),
            hint=_(
                'Count the letter names from the lower note to the upper one, both included, '
                'for the number; count semitones for the quality.'
            ),
        )


# Intervals by ear ----------------------------------------------------------------------

_EAR_KEYS = frozenset((*SIMPLE, *COMPOUND))
_VARIANTS = ('melodic.asc', 'melodic.desc', 'harmonic')


def ear_item(variant: str, key: str) -> ItemId:
    """``interval.ear.melodic.asc.m6``, ``interval.ear.harmonic.TT`` …"""
    return ItemId(f'interval.ear.{variant}.{key}')


def parse_ear_item(item: str) -> tuple[str, str]:
    """``(variant, key)`` of an ear item, e.g. ``('melodic.desc', 'm6')``."""
    prefix = 'interval.ear.'
    rest = item.removeprefix(prefix) if item.startswith(prefix) else ''
    variant, _sep, key = rest.rpartition('.')
    if variant not in _VARIANTS or key not in _EAR_KEYS:
        raise ValueError(f'not an ear interval item: {item!r}')
    return variant, key


def hear_interval(key: str, rng: random.Random) -> tuple[Pitch, Pitch]:
    """A lower and upper note for the interval ``key`` in a comfortable register,
    spelled with at most one sharp or flat each (the tritone either way)."""
    lowest, highest, top = _EAR_COMPOUND_RANGE if key in COMPOUND else _EAR_SIMPLE_RANGE
    spellings = _TRITONE_SPELLINGS if key == TRITONE else (key,)
    candidates: list[tuple[Pitch, Pitch]] = []
    for octave in range(2, 6):
        for name in _EAR_ROOTS:
            low = name.at(octave)
            if not lowest <= low.midi <= highest:
                continue
            for spelling in spellings:
                high = low.transpose(Interval.parse(spelling))
                if abs(high.alter) <= 1 and high.midi <= top:
                    candidates.append((low, high))
    return rng.choice(candidates)


def _written_clef(low: Pitch, high: Pitch) -> Clef:
    """Treble or bass, whichever needs fewer ledger lines."""

    def ledgers(clef: Clef) -> int:
        bottom, top = clef.staff_position(low), clef.staff_position(high)
        return max(0, -bottom) + max(0, top - _STAFF_TOP)

    return Clef.BASS if ledgers(Clef.BASS) < ledgers(Clef.TREBLE) else Clef.TREBLE


class IntervalsEar(_IntervalExercise):
    id = 'interval-ear'
    item_prefix = 'interval.ear.'
    family = Family.EAR
    modality = Modality.EAR
    level = 1
    icon_name = 'interval-ear-symbolic'
    glyph = '♪'
    written = False
    settings: ClassVar[tuple[Setting, ...]] = (
        _pool_setting(),
        _form_setting('melodic', written=False),
        _direction_setting('asc'),
        _compound_setting(),
    )

    @property
    def title(self) -> str:
        return _('Intervals — Ear')

    @property
    def description(self) -> str:
        return _('Recognise intervals by ear, melodic or harmonic.')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        forms = _forms(settings, 'melodic')
        directions = _directions(settings, 'asc')
        if forms == ('harmonic',):
            parts = [_('Harmonic')]
        else:
            parts = [_('Melodic') if forms == ('melodic',) else _('Melodic and harmonic')]
            if directions == ('asc',):
                parts.append(_('ascending'))
            elif directions == ('desc',):
                parts.append(_('descending'))
            else:
                parts.append(_('ascending and descending'))
        if settings.get('compound'):
            parts.append(_('compound'))
        return _(' · ').join(parts)

    def item_label(self, item_id: ItemId) -> str:
        variant, key = parse_ear_item(item_id)
        label = interval_label(key)
        if variant == 'melodic.asc':
            # Translators: an item in "Weakest items", e.g. "Minor sixth (ear, ascending)".
            return _('{interval} (ear, ascending)').format(interval=label)
        if variant == 'melodic.desc':
            # Translators: an item in "Weakest items", e.g. "Minor sixth (ear, descending)".
            return _('{interval} (ear, descending)').format(interval=label)
        # Translators: an item in "Weakest items", e.g. "Tritone (ear, harmonic)".
        return _('{interval} (ear, harmonic)').format(interval=label)

    def _pool(self, settings: Mapping[str, object]) -> list[str]:
        keys = _selected(settings)
        if settings.get('compound'):
            keys += list(COMPOUND)
        return keys

    def _variants(self, settings: Mapping[str, object]) -> list[str]:
        """Ascending first, then descending, then harmonic: the usual order of difficulty."""
        variants: list[str] = []
        forms = _forms(settings, 'melodic')
        if 'melodic' in forms:
            variants += [f'melodic.{d}' for d in _directions(settings, 'asc')]
        if 'harmonic' in forms:
            variants.append('harmonic')
        return variants

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        pool = self._pool(settings)
        return [ear_item(variant, key) for variant in self._variants(settings) for key in pool]

    def _figure(self, question: Question) -> Figure | None:
        return question.written_alternative

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        variant, key = parse_ear_item(item_id)
        low, high = hear_interval(key, rng)
        harmonic = variant == 'harmonic'
        descending = variant == 'melodic.desc'
        first, second = (high, low) if descending else (low, high)
        notes = Notes(first, second, harmonic)
        options = choose_options(
            self._pool(settings), key, rng, spare=(*SIMPLE, *COMPOUND), written=False
        )
        if descending:
            # Translators: shown with a descending interval by ear, e.g. "First note: E4".
            context = _('First note: {note}').format(note=note_label(first))
        else:
            # Translators: shown with an interval by ear, e.g. "Root: C4" (the lower note).
            context = _('Root: {note}').format(note=note_label(low))
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Which interval do you hear?'),
            answer=ChoiceAnswer(options),
            expected=key,
            playback=notes.playback(),
            playback_is_question=True,
            written_alternative=interval_figure(
                _written_clef(low, high), first, second, harmonic=harmonic
            ),
            context=context,
        )


EXERCISES: tuple[ExerciseDefinition, ...] = (IntervalsStaff(), IntervalsEar())
