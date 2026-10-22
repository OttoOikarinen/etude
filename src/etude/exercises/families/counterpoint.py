# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Two-voice species counterpoint: write a counterpoint, and find the mistake in one.

*Counterpoint Writing* prints a cantus firmus on one staff of a pair and asks
for a counterpoint above or below it in one of the five species, in one of the
six modes of Fux and transposed within a number of accidentals. The learner
writes into the species' rhythm (fifth species: a rhythm chosen per
question; fourth species: tied notes written once). Any correct counterpoint
is right: the answer is graded by :mod:`etude.checkers.counterpoint`; warnings
are shown but not penalised, and the score is the share of notes without an
error. Mistakes are marked on the learner's staff in error ink with short
labels, the first three explained, and a model answer from
:mod:`etude.checkers.species` can be played and compared. Items are a species
and a position (``counterpoint.write.2.above``).

*Counterpoint Errors* shows a correct counterpoint with exactly one mistake
put in (verified with the checker) and asks which one it is. Items are
mistakes (``counterpoint.error.parallel-fifths`` …).

Cantus firmi are Fux's own (transposed) or new ones from
:func:`etude.checkers.cantus.generate`, so questions do not repeat.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from gettext import gettext as _
from gettext import ngettext
from typing import ClassVar, cast

from ...audio.spec import PlaybackNote, PlaybackSpec
from ...checkers.cantus import FUX, fux_cantus, generate, modal_keys, signature
from ...checkers.counterpoint import (
    CANTUS,
    COUNTERPOINT,
    MODES,
    Context,
    Rhythm,
    Rule,
    Severity,
    Species,
    Violation,
    cadence_ficta,
    check,
    is_consonant,
    mode_ficta,
    rule_mark,
    rule_name,
    rule_reason,
    scan,
    species_name,
    voice_title,
)
from ...checkers.species import CounterpointError, solve
from ...core import Duration, Interval, Meter, NoteValue, Pitch, PitchName, Scale, ScaleType
from ...core.naming import pitch_name, scale_name, scale_type_name
from ...learning.model import ItemId
from ...notation.parts import durations_of, rhythm_line, voices_figure
from ...notation.spec import Chord as StaffChord
from ...notation.spec import Clef, Head, Ink, SystemSpec
from ..base import (
    ChoiceAnswer,
    ChoiceSetting,
    ExerciseDefinition,
    Family,
    Feedback,
    IntSetting,
    Modality,
    MultiChoiceSetting,
    Option,
    Question,
    Setting,
    StaffInputAnswer,
)

STAVES = (Clef.TREBLE, Clef.BASS)
METER = Meter(2, 2)
WHOLE = Duration(NoteValue.WHOLE)
MAX_LISTED = 3
"""Mistakes spelled out in feedback; the staff marks all of them."""
MAX_ACCIDENTALS = 4
TEMPO = 132.0
"""Quarter notes per minute: a whole note lasts under two seconds."""
_ATTEMPTS = 12
_FUX_SHARE = 0.25
"""How often a writing question uses Fux's own cantus firmus."""

_LENGTHS = {
    Species.FIRST: (8, 11),
    Species.SECOND: (8, 10),
    Species.THIRD: (7, 8),
    Species.FOURTH: (8, 11),
    Species.FIFTH: (7, 9),
}
"""Cantus firmus lengths per species: the quick species get shorter ones, so a line
still fits a phone without scrolling far."""


# Settings -----------------------------------------------------------------------------


def _species_setting() -> MultiChoiceSetting:
    return MultiChoiceSetting(
        'species',
        _('Species'),
        tuple(Option(str(s.value), species_name(s)) for s in Species),
        tuple(str(s.value) for s in Species),
    )


def _position_setting() -> ChoiceSetting:
    return ChoiceSetting(
        'position',
        _('Counterpoint'),
        (
            Option('above', _('Above the cantus firmus')),
            Option('below', _('Below the cantus firmus')),
            Option('both', _('Above and below')),
        ),
        'both',
    )


def _modes_setting() -> MultiChoiceSetting:
    return MultiChoiceSetting(
        'modes',
        _('Modes'),
        tuple(Option(m.value, scale_type_name(m)) for m in MODES),
        tuple(m.value for m in MODES),
    )


def _accidentals_setting() -> IntSetting:
    return IntSetting(
        'max-accidentals',
        _('Most accidentals'),
        1,
        0,
        MAX_ACCIDENTALS,
        subtitle=_('Largest number of sharps or flats in the transposed mode'),
    )


def _chosen(settings: Mapping[str, object], key: str, every: Sequence[str]) -> list[str]:
    value = settings.get(key, tuple(every))
    chosen = set(cast(Sequence[str], value)) if isinstance(value, list | tuple) else set()
    return [k for k in every if k in chosen] or list(every)


def _modes(settings: Mapping[str, object]) -> list[ScaleType]:
    return [ScaleType(m) for m in _chosen(settings, 'modes', [m.value for m in MODES])]


def _limit(settings: Mapping[str, object]) -> int:
    value = settings.get('max-accidentals', 1)
    return max(0, min(MAX_ACCIDENTALS, value if isinstance(value, int) else 1))


def _positions(settings: Mapping[str, object]) -> list[bool]:
    position = settings.get('position', 'both')
    if position == 'above':
        return [True]
    if position == 'below':
        return [False]
    return [True, False]


def _describe(settings: Mapping[str, object]) -> list[str]:
    parts = []
    modes = _modes(settings)
    if len(modes) < len(MODES):
        # Translators: separator between mode names in an exercise subtitle.
        parts.append(_(', ').join(scale_type_name(m) for m in modes))
    limit = _limit(settings)
    parts.append(ngettext('up to {n} accidental', 'up to {n} accidentals', limit).format(n=limit))
    return parts


# Passages -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Passage:
    """A cantus firmus and a counterpoint to it."""

    mode: Scale
    species: Species
    above: bool
    cantus: tuple[Pitch, ...]
    rhythm: Rhythm
    line: tuple[Pitch, ...]

    @property
    def context(self) -> Context:
        return Context(self.mode, self.species, self.above, self.rhythm)

    def details(self) -> dict[str, str]:
        """What :func:`passage_of` reads back (kept in :attr:`Question.details`)."""
        return {
            'mode': f'{self.mode.tonic} {self.mode.type.value}',
            'species': str(self.species.value),
            'position': 'above' if self.above else 'below',
            'cantus': ' '.join(str(p) for p in self.cantus),
            'rhythm': ' '.join(str(d.length) for d in self.rhythm.notes),
            'rest': str(self.rhythm.rest.length) if self.rhythm.rest is not None else '',
            'line': ' '.join(str(p) for p in self.line),
        }


def passage_of(details: Mapping[str, str], line: Sequence[Pitch] | None = None) -> Passage:
    """The passage of a question's details, with ``line`` in place of its own."""
    tonic, mode_type = details['mode'].split()
    rest = details.get('rest', '')
    rhythm = Rhythm(
        tuple(durations_of(Fraction(t))[0] for t in details['rhythm'].split()),
        durations_of(Fraction(rest))[0] if rest else None,
    )
    return Passage(
        Scale(PitchName.parse(tonic), ScaleType(mode_type)),
        Species(int(details['species'])),
        details['position'] == 'above',
        tuple(Pitch.parse(n) for n in details['cantus'].split()),
        rhythm,
        tuple(line) if line is not None else tuple(Pitch.parse(n) for n in details['line'].split()),
    )


def _register(above: bool, cantus: Sequence[Pitch]) -> tuple[Pitch, ...]:
    """The cantus moved by octaves to its staff: around the bass staff's top when the
    counterpoint is above (C3–B3 final), on the treble staff when it is below."""
    target = 54 if above else 66
    centre = sum(p.midi for p in cantus) / len(cantus)
    octaves = round((target - centre) / 12)
    interval = Interval.parse('P8')
    moved = tuple(cantus)
    for _step in range(abs(octaves)):
        moved = tuple(p.transpose(interval, down=octaves < 0) for p in moved)
    return moved


def counterpoint_range(cantus: Sequence[Pitch], above: bool) -> tuple[Pitch, Pitch]:
    """Where the counterpoint may go: on the treble staff above the cantus (from a fourth
    below its top, at least G3, a twelfth up), on the bass staff below it."""
    fourth, twelfth, step = Interval.parse('P4'), Interval.parse('P12'), Interval.parse('M2')
    if above:
        low = max(cantus, key=lambda p: p.midi).transpose(fourth, down=True)
        low = max(low, Pitch.parse('G3'), key=lambda p: p.midi)
        return low, low.transpose(twelfth)
    high = min(cantus, key=lambda p: p.midi).transpose(fourth)
    high = min(high, Pitch.parse('E4'), key=lambda p: p.midi)
    return high.transpose(twelfth, down=True).transpose(step, down=True), high


def make_passage(
    species: Species,
    above: bool,
    modes: Sequence[ScaleType],
    limit: int,
    rng: random.Random,
    *,
    lengths: tuple[int, int] | None = None,
    fux: bool = True,
) -> Passage:
    """A cantus firmus in one of ``modes`` (transposed within ``limit`` accidentals) and a
    correct counterpoint to it, drawing another cantus when none is found.

    Passages are cached by a seed drawn from ``rng``, so generating the same question
    again (or the same draw under other settings) is free."""
    return _passage(
        species,
        above,
        tuple(modes),
        limit,
        rng.randrange(2**32),
        lengths or _LENGTHS[species],
        fux,
    )


@lru_cache(maxsize=2048)
def _passage(
    species: Species,
    above: bool,
    modes: tuple[ScaleType, ...],
    limit: int,
    seed: int,
    lengths: tuple[int, int],
    fux: bool,
) -> Passage:
    rng = random.Random(seed)
    low_length, high_length = lengths
    for _attempt in range(_ATTEMPTS):
        mode_type = rng.choice(modes)
        mode = rng.choice(modal_keys(mode_type, limit))
        original = FUX[mode_type]
        if fux and len(original) <= high_length and rng.random() < _FUX_SHARE:
            cantus = fux_cantus(mode)
        else:
            cantus = generate(
                mode, mode.tonic.at(4), rng, length=rng.randint(low_length, high_length)
            )
        cantus = _register(above, cantus)
        low, high = counterpoint_range(cantus, above)
        try:
            rhythm, line = solve(cantus, Context(mode, species, above), rng, low=low, high=high)
        except CounterpointError:
            continue
        return Passage(mode, species, above, cantus, rhythm, line)
    raise CounterpointError(f'no {species.name.lower()}-species passage')  # pragma: no cover


# Figures and sound ----------------------------------------------------------------------


def voices_of(passage: Passage) -> tuple[tuple[Pitch, ...], tuple[Pitch, ...]]:
    """The two lines top first."""
    if passage.above:
        return passage.line, passage.cantus
    return passage.cantus, passage.line


def notes_text(pitches: Sequence[Pitch]) -> str:
    return ' '.join(pitch_name(p.name) + str(p.octave) for p in pitches)


def _names(pitches: Sequence[Pitch]) -> str:
    # Translators: separator between note names in a list such as "D4, F4, E4".
    return _(', ').join(pitch_name(p.name) + str(p.octave) for p in pitches)


def counterpoint_figure(
    passage: Passage,
    *,
    inks: Mapping[int, Ink] | None = None,
    marks: Mapping[int, str] | None = None,
    description: str | None = None,
) -> SystemSpec:
    """The two voices on a treble and a bass staff in 2/2, the counterpoint in its
    rhythm (tied over the barlines where it is syncopated).

    ``inks`` colours counterpoint notes by index; ``marks`` writes a short text under
    a counterpoint note (the rule a mistake breaks), in error ink.
    """
    inks = inks or {}
    marks = marks or {}
    line = []
    for index, pitch in enumerate(passage.line):
        ink = inks.get(index, Ink.FOREGROUND)
        label = marks.get(index)
        stem = Ink.ERROR if label is not None else ink
        line.append(StaffChord((Head(pitch, ink=ink),), label=label, ink=stem))
    cantus = [StaffChord((Head(p),)) for p in passage.cantus]
    counterpoint_events = rhythm_line(
        line, passage.rhythm.notes, rest=passage.rhythm.rest, bar=Fraction(1), final_bar=True
    ).events
    cantus_events = rhythm_line(
        cantus, (WHOLE,) * len(cantus), bar=Fraction(1), final_bar=True
    ).events
    upper, lower = (
        (counterpoint_events, cantus_events)
        if passage.above
        else (cantus_events, counterpoint_events)
    )
    figure = voices_figure(
        STAVES,
        (0, 1),
        (upper, lower),
        key_signature=signature(passage.mode),
        meter=METER,
        description=description,
    )
    assert isinstance(figure, SystemSpec)
    return figure


def describe(passage: Passage, violations: Sequence[Violation] = ()) -> str:
    """What the figure shows, for screen readers: the mode, both lines and the mistakes."""
    position = (
        _('Counterpoint above the cantus firmus')
        if passage.above
        else _('Counterpoint below the cantus firmus')
    )
    parts = [
        # Translators: e.g. "Treble and bass staves, D Dorian, second species".
        _('Treble and bass staves, {mode}, {species}').format(
            mode=scale_name(passage.mode), species=species_name(passage.species).lower()
        ),
        position,
        f'{voice_title(COUNTERPOINT)}: {_names(passage.line)}',
        f'{voice_title(CANTUS)}: {_names(passage.cantus)}',
        *(v.message for v in violations),
    ]
    return _('. ').join(parts) + '.'


def playback(passage: Passage) -> PlaybackSpec:
    """Both voices together."""
    notes: list[PlaybackNote] = []
    for bar, pitch in enumerate(passage.cantus):
        notes.append(PlaybackNote(pitch.midi, Fraction(bar * 4), Fraction(4)))
    for start, duration, pitch in zip(
        passage.rhythm.onsets, passage.rhythm.notes, passage.line, strict=True
    ):
        notes.append(PlaybackNote(pitch.midi, start * 4, duration.quarter_length))
    return PlaybackSpec(tuple(sorted(notes, key=lambda n: n.start)), tempo=TEMPO, meter=METER)


def cantus_playback(cantus: Sequence[Pitch]) -> PlaybackSpec:
    notes = tuple(
        PlaybackNote(p.midi, Fraction(4 * bar), Fraction(4)) for bar, p in enumerate(cantus)
    )
    return PlaybackSpec(notes, tempo=TEMPO, meter=METER)


def marked(
    violations: Sequence[Violation], count: int, *, correct_ink: bool = False
) -> tuple[dict[int, Ink], dict[int, str]]:
    """Inks and marks: the counterpoint notes of every error in error ink, and a short
    mark under the note where each of the first :data:`MAX_LISTED` errors is heard,
    merged into one label per note."""
    inks = dict.fromkeys(range(count), Ink.SUCCESS) if correct_ink else {}
    errors = [v for v in violations if v.severity is Severity.ERROR]
    for violation in errors:
        for note in violation.slots:
            if 0 <= note < count:
                inks[note] = Ink.ERROR
    labels: dict[int, list[str]] = {}
    for violation in errors[:MAX_LISTED]:
        mark = rule_mark(violation.rule)
        if mark not in labels.setdefault(violation.slot, []):
            labels[violation.slot].append(mark)
    return inks, {slot: ' '.join(m) for slot, m in labels.items()}


# Counterpoint writing -----------------------------------------------------------------


def _hint(species: Species) -> str:
    hints: dict[Species, Callable[[], str]] = {
        Species.FIRST: lambda: _(
            'Begin and end on a perfect consonance, use mostly thirds and sixths in between, '
            'approach fifths and octaves in contrary motion, and end with a major sixth to '
            'an octave (or minor third to a unison).'
        ),
        Species.SECOND: lambda: _(
            'Every downbeat is consonant; a half note on the weak beat may be a dissonance '
            'only as a passing tone, between two steps in one direction.'
        ),
        Species.THIRD: lambda: _(
            'The first quarter of each bar is consonant; the others may pass or neighbor by '
            'step, and the cambiata leaps down a third from a dissonance and turns up.'
        ),
        Species.FOURTH: lambda: _(
            'Strike each note as a consonance on the weak beat and tie it over; if it is '
            'dissonant on the downbeat, resolve it down by step (7–6, 4–3 above; 2–3 below).'
        ),
        Species.FIFTH: lambda: _(
            'Combine the species in the given rhythm: consonant downbeats, passing and '
            'neighboring quarters, eighth notes by step, and suspensions that resolve down.'
        ),
    }
    return hints[species]()


class CounterpointWriting(ExerciseDefinition):
    id = 'counterpoint-writing'
    item_prefix = 'counterpoint.write.'
    family = Family.HARMONY
    modality = Modality.EYE
    level = 3
    icon_name = 'counterpoint-writing-symbolic'
    glyph = '𝅝'
    settings: ClassVar[tuple[Setting, ...]] = (
        _species_setting(),
        _position_setting(),
        _modes_setting(),
        _accidentals_setting(),
    )

    @property
    def title(self) -> str:
        return _('Counterpoint Writing')

    @property
    def description(self) -> str:
        return _('Write a species counterpoint above or below a cantus firmus.')

    @property
    def play_label(self) -> str:
        return _('Play cantus firmus')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        parts = _describe(settings)
        position = settings.get('position', 'both')
        if position == 'above':
            parts.append(_('above'))
        elif position == 'below':
            parts.append(_('below'))
        # Translators: separator between the parts of an exercise subtitle.
        return _(' · ').join(parts)

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        species = _chosen(settings, 'species', [str(s.value) for s in Species])
        positions = _positions(settings)
        return [
            ItemId(f'counterpoint.write.{s}.{"above" if above else "below"}')
            for s in species
            for above in positions
        ]

    def item_label(self, item_id: ItemId) -> str:
        species, above = _parse_write(item_id)
        if above:
            # Translators: an item in "Weakest items", e.g. "Second species above".
            return _('{species} above').format(species=species_name(species))
        return _('{species} below').format(species=species_name(species))

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        species, above = _parse_write(item_id)
        return [ItemId(f'counterpoint.write.{species.value}.{"below" if above else "above"}')]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        species, above = _parse_write(item_id)
        passage = make_passage(species, above, _modes(settings), _limit(settings), rng)
        n = len(passage.cantus)
        cp, cf = (0, 1) if above else (1, 0)
        names = (
            (voice_title(COUNTERPOINT), voice_title(CANTUS))
            if above
            else (voice_title(CANTUS), voice_title(COUNTERPOINT))
        )
        rests = {cp: passage.rhythm.rest} if passage.rhythm.rest is not None else {}
        if above:
            prompt = _('Write a counterpoint above the cantus firmus')
        else:
            prompt = _('Write a counterpoint below the cantus firmus')
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=prompt,
            answer=StaffInputAnswer(
                clef=Clef.TREBLE,
                key_signature=signature(passage.mode),
                voices=2,
                staves=STAVES,
                voice_staves=(0, 1),
                given_voices={cf: passage.cantus},
                voice_rhythms={cp: passage.rhythm.notes, cf: (WHOLE,) * n},
                voice_rests=rests,
                meter=METER,
                voice_names=names,
            ),
            expected=voices_of(passage),
            playback=cantus_playback(passage.cantus),
            # Translators: e.g. "Second species · D Dorian".
            context=_('{species} · {mode}').format(
                species=species_name(species), mode=scale_name(passage.mode)
            ),
            details=passage.details(),
            hint=_hint(species),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        model = passage_of(question.details)
        lines = _lines(given)
        play_expected = playback(model)
        expected_label = _model_label(model)
        if lines is None or len(lines[0 if model.above else 1]) != len(model.line):
            return Feedback(
                correct=False,
                title=_('Not quite — write every note of the counterpoint'),
                detail=_('Each note of the rhythm needs a pitch.'),
                expected_label=expected_label,
                score=0.0,
                play_expected=play_expected,
            )
        written = lines[0] if model.above else lines[1]
        cantus = lines[1] if model.above else lines[0]
        if cantus != model.cantus:
            return Feedback(
                correct=False,
                title=_('Not quite — the cantus firmus must stay as it is'),
                detail=_('Write only the counterpoint.'),
                expected_label=expected_label,
                score=0.0,
                play_expected=play_expected,
            )
        answer = passage_of(question.details, written)
        violations = check(answer.cantus, answer.line, answer.context)
        errors = [v for v in violations if v.severity is Severity.ERROR]
        warnings = [v for v in violations if v.severity is Severity.WARNING]
        score = 1.0 - len({v.slot for v in errors}) / len(written)
        correct = not errors
        if correct:
            title = _('Correct — no counterpoint errors')
        else:
            title = ngettext(
                'Not quite — {n} counterpoint error',
                'Not quite — {n} counterpoint errors',
                len(errors),
            ).format(n=len(errors))
        sentences = [f'{v.message}.' for v in errors[:MAX_LISTED]]
        if len(errors) > MAX_LISTED:
            more = len(errors) - MAX_LISTED
            # Translators: after the first few counterpoint mistakes, e.g. "And 3 more."
            sentences.append(ngettext('And {n} more.', 'And {n} more.', more).format(n=more))
        sentences += list(dict.fromkeys(rule_reason(v.rule) for v in errors))[:2]
        if warnings:
            # Translators: introduces weaknesses that are not counted as mistakes, e.g.
            # "Worth noticing: The counterpoint repeats A4 (bars 1–2)."
            sentences.append(
                _('Worth noticing: {items}').format(
                    items=' '.join(f'{w.message}.' for w in warnings[:MAX_LISTED])
                )
            )
        if correct and not warnings:
            sentences.append(_('Every rule of the species is kept.'))
        inks, marks = marked(violations, len(written), correct_ink=correct)
        figure = counterpoint_figure(
            answer, inks=inks, marks=marks, description=describe(answer, errors)
        )
        return Feedback(
            correct=correct,
            title=title,
            detail=' '.join(sentences),
            expected_label=expected_label,
            score=score,
            figure=figure,
            play_expected=play_expected,
            play_given=playback(answer),
        )

    def answer_label(self, question: Question, value: object) -> str:
        lines = _lines(value)
        if lines is None:
            return str(value)
        line = lines[0] if question.details.get('position') == 'above' else lines[-1]
        return notes_text(line)

    def serialize(self, value: object) -> str:
        lines = _lines(value)
        if lines is None:
            return str(value)
        return ' | '.join(' '.join(str(p) for p in line) for line in lines)


def _model_label(model: Passage) -> str:
    # Translators: the model answer in feedback, e.g. "A model answer: A4 A4 G4 …".
    return _('A model answer: {notes}').format(notes=notes_text(model.line))


def _lines(value: object) -> tuple[tuple[Pitch, ...], tuple[Pitch, ...]] | None:
    if not isinstance(value, tuple) or len(value) != 2:
        return None
    for line in value:
        if not isinstance(line, tuple) or not all(isinstance(p, Pitch) for p in line):
            return None
    return (value[0], value[1])


def _parse_write(item_id: str) -> tuple[Species, bool]:
    prefix = 'counterpoint.write.'
    parts = item_id[len(prefix) :].split('.') if item_id.startswith(prefix) else []
    if len(parts) != 2 or parts[0] not in '12345' or parts[1] not in ('above', 'below'):
        raise ValueError(f'not a counterpoint writing item: {item_id!r}')
    return Species(int(parts[0])), parts[1] == 'above'


# Counterpoint errors ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Mistake:
    key: str
    rule: Rule
    species: tuple[Species, ...]
    """Species a passage with this mistake is written in."""
    modes: tuple[ScaleType, ...] = MODES
    """Modes the mistake can be made in alone (a missing leading tone needs ficta)."""
    positions: tuple[bool, ...] = (True, False)
    """Counterpoint above, below: direct octaves are an error only when the upper voice
    leaps, which a single changed note of a counterpoint below cannot do."""


_S1, _S2, _S3, _S4 = Species.FIRST, Species.SECOND, Species.THIRD, Species.FOURTH
MISTAKES = (
    Mistake('parallel-fifths', Rule.PARALLEL_FIFTHS, (_S1, _S2)),
    Mistake('parallel-octaves', Rule.PARALLEL_OCTAVES, (_S1, _S2)),
    Mistake('direct-octaves', Rule.DIRECT_OCTAVES, (_S1,), positions=(True,)),
    Mistake('dissonance', Rule.DISSONANCE, (_S1, _S2)),
    Mistake('dissonance-treatment', Rule.DISSONANCE_TREATMENT, (_S2, _S3)),
    Mistake('unison', Rule.UNISON, (_S1,)),
    Mistake('suspension', Rule.SUSPENSION, (_S4,)),
    Mistake(
        'leading-tone',
        Rule.LEADING_TONE,
        (_S1, _S2),
        (ScaleType.DORIAN, ScaleType.MIXOLYDIAN, ScaleType.AEOLIAN),
    ),
    Mistake('melodic-interval', Rule.MELODIC_INTERVAL, (_S1, _S2)),
)
_MISTAKES = {m.key: m for m in MISTAKES}
_CONFUSABLE = {
    'parallel-fifths': ('parallel-octaves', 'direct-octaves'),
    'parallel-octaves': ('parallel-fifths', 'unison'),
    'direct-octaves': ('parallel-octaves',),
    'dissonance': ('dissonance-treatment',),
    'dissonance-treatment': ('dissonance',),
    'unison': ('parallel-octaves',),
    'suspension': ('dissonance',),
    'leading-tone': ('melodic-interval',),
    'melodic-interval': ('leading-tone',),
}
_ERROR_LENGTHS = (7, 9)
_MUTATION_TRIES = 60
"""Changed notes tried after one with the mistake but a new warning was found."""


def _mistake_label(key: str) -> str:
    return rule_name(_MISTAKES[key].rule)


def _candidates(passage: Passage, index: int) -> list[Pitch]:
    """Other notes of the mode (and its ficta) near note ``index``."""
    mode = passage.mode
    seventh, sixth = cadence_ficta(mode)
    names: set[PitchName] = {*mode.names(), *mode_ficta(mode)}
    names |= {n for n in (seventh, sixth) if n is not None}
    original = passage.line[index]
    return [
        name.at(octave)
        for name in names
        for octave in (original.octave - 1, original.octave, original.octave + 1)
        if 0 < abs(name.at(octave).midi - original.midi) <= 9
    ]


def _aims(mistake: Mistake, passage: Passage, index: int, pitch: Pitch) -> bool:
    """Whether changing note ``index`` to ``pitch`` could make ``mistake`` (a quick filter
    before the checker decides)."""
    rhythm = passage.rhythm
    start = rhythm.onsets[index]
    bar = int(start)
    strong = start == bar
    cantus = passage.cantus[bar]
    steps = abs(pitch.diatonic_index - cantus.diatonic_index)
    perfect = steps % 7 in (0, 4)
    match mistake.key:
        case 'parallel-fifths' | 'parallel-octaves' | 'direct-octaves':
            return strong and perfect
        case 'unison':
            return strong and pitch == cantus
        case 'dissonance':
            return strong and not is_consonant(pitch, cantus)
        case 'dissonance-treatment':
            return not strong and not is_consonant(pitch, cantus)
        case 'suspension':
            return rhythm.tied()[index] or (index > 0 and rhythm.tied()[index - 1])
        case 'leading-tone':
            return index == len(passage.line) - 2
    return True


def make_mistake(mistake: Mistake, passage: Passage, rng: random.Random) -> Passage | None:
    """``passage`` with one note changed so that the checker finds exactly one error, of
    ``mistake``'s rule (preferably without a new warning); ``None`` if no change does
    it."""
    before = {(v.rule, v.slot) for v in scan(passage.cantus, passage.line, passage.context)}
    indexes = list(range(len(passage.line)))
    rng.shuffle(indexes)
    fallback: tuple[Pitch, ...] | None = None
    tries = 0
    for index in indexes:
        options = [p for p in _candidates(passage, index) if _aims(mistake, passage, index, p)]
        rng.shuffle(options)
        for pitch in options:
            tries += 1
            if fallback is not None and tries > _MUTATION_TRIES:
                break  # settle for a new warning rather than search on
            line = (*passage.line[:index], pitch, *passage.line[index + 1 :])
            found = scan(passage.cantus, line, passage.context)
            errors = [v for v in found if v.severity is Severity.ERROR]
            if len(errors) != 1 or errors[0].rule is not mistake.rule:
                continue
            if all(v.severity is Severity.ERROR or (v.rule, v.slot) in before for v in found):
                fallback = line
                tries = _MUTATION_TRIES + 1
                break
            fallback = fallback or line
        if fallback is not None and tries > _MUTATION_TRIES:
            break
    if fallback is None:
        return None
    return Passage(
        passage.mode, passage.species, passage.above, passage.cantus, passage.rhythm, fallback
    )


@lru_cache(maxsize=1024)
def _mistaken(
    mistake: Mistake,
    positions: tuple[bool, ...],
    modes: tuple[ScaleType, ...],
    limit: int,
    seed: int,
) -> Passage:
    """A short correct passage with ``mistake`` put in (cached by seed)."""
    rng = random.Random(seed)
    for _attempt in range(_ATTEMPTS):
        correct = make_passage(
            rng.choice(mistake.species),
            rng.choice(positions),
            modes,
            limit,
            rng,
            lengths=_ERROR_LENGTHS,
            fux=False,
        )
        passage = make_mistake(mistake, correct, rng)
        if passage is not None:
            return passage
    raise CounterpointError(f'no example of {mistake.key}')  # pragma: no cover


class CounterpointErrors(ExerciseDefinition):
    id = 'counterpoint-errors'
    item_prefix = 'counterpoint.error.'
    family = Family.HARMONY
    modality = Modality.EYE
    level = 3
    icon_name = 'counterpoint-errors-symbolic'
    glyph = '∦'
    settings: ClassVar[tuple[Setting, ...]] = (
        MultiChoiceSetting(
            'mistakes',
            _('Mistakes'),
            tuple(Option(m.key, _mistake_label(m.key)) for m in MISTAKES),
            tuple(m.key for m in MISTAKES),
            minimum=2,
        ),
        _position_setting(),
        _modes_setting(),
        _accidentals_setting(),
    )

    @property
    def title(self) -> str:
        return _('Counterpoint Errors')

    @property
    def description(self) -> str:
        return _('Find the mistake in a two-voice species counterpoint.')

    @property
    def play_label(self) -> str:
        return _('Play passage')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        return _(' · ').join(_describe(settings))

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        keys = _chosen(settings, 'mistakes', [m.key for m in MISTAKES])
        return [ItemId(f'counterpoint.error.{key}') for key in keys]

    def item_label(self, item_id: ItemId) -> str:
        # Translators: an item in "Weakest items", e.g. "Parallel fifths (counterpoint)".
        return _('{mistake} (counterpoint)').format(
            mistake=_mistake_label(_parse_error(item_id).key)
        )

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        key = _parse_error(item_id).key
        return [ItemId(f'counterpoint.error.{k}') for k in _CONFUSABLE.get(key, ())]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        mistake = _parse_error(item_id)
        modes = [m for m in _modes(settings) if m in mistake.modes] or list(mistake.modes)
        positions = [p for p in _positions(settings) if p in mistake.positions]
        passage = _mistaken(
            mistake,
            tuple(positions or mistake.positions),
            tuple(modes),
            _limit(settings),
            rng.randrange(2**32),
        )
        options = tuple(
            Option(m.key, _mistake_label(m.key), accel=str(index + 1))
            for index, m in enumerate(MISTAKES)
        )
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Which mistake is in this counterpoint?'),
            answer=ChoiceAnswer(options),
            expected=mistake.key,
            figure=counterpoint_figure(passage, description=describe(passage)),
            playback=playback(passage),
            # Translators: e.g. "First species · D Dorian".
            context=_('{species} · {mode}').format(
                species=species_name(passage.species), mode=scale_name(passage.mode)
            ),
            details=passage.details(),
            hint=_(
                'Compare the voices from note to note (consonances, parallels, the cadence), '
                'then follow the counterpoint on its own (leaps, dissonances, accidentals).'
            ),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        passage, violation, figure = _marked_passage(tuple(sorted(question.details.items())))
        expected = str(question.expected)
        correct = given == expected
        label = _mistake_label(expected)
        if correct:
            # Translators: e.g. "Correct — parallel fifths".
            title = _('Correct — {mistake}').format(mistake=label)
        else:
            # Translators: e.g. "Not quite — the mistake is: Parallel fifths".
            title = _('Not quite — the mistake is: {mistake}').format(mistake=label)
        return Feedback(
            correct=correct,
            title=title,
            detail=f'{violation.message}. {rule_reason(violation.rule)}',
            expected_label=label,
            figure=figure,
            play_expected=playback(passage),
        )


@lru_cache(maxsize=64)
def _marked_passage(
    details: tuple[tuple[str, str], ...],
) -> tuple[Passage, Violation, SystemSpec]:
    """A question's passage, its mistake and the figure that marks it (the same for every
    answer to the question)."""
    passage = passage_of(dict(details))
    violation = next(
        v
        for v in check(passage.cantus, passage.line, passage.context)
        if v.severity is Severity.ERROR
    )
    inks, marks = marked([violation], len(passage.line))
    figure = counterpoint_figure(
        passage, inks=inks, marks=marks, description=describe(passage, [violation])
    )
    return passage, violation, figure


def _parse_error(item_id: str) -> Mistake:
    prefix = 'counterpoint.error.'
    if not item_id.startswith(prefix) or item_id[len(prefix) :] not in _MISTAKES:
        raise ValueError(f'not a counterpoint error item: {item_id!r}')
    return _MISTAKES[item_id[len(prefix) :]]


EXERCISES: tuple[ExerciseDefinition, ...] = (CounterpointWriting(), CounterpointErrors())
