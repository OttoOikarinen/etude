# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Scales: tell scale types apart on the staff and by ear.

*Scales — Staff* shows one octave of a scale and asks for its type. Items
are scale types, ``scale.staff.harmonic-minor``; the tonic, clef and
register vary per question. With "Spot the wrong note" a second kind of
item, ``scale.staff.wrong.major``, names the scale and shows it with one
note a semitone off; the learner clicks that note (or picks its name).

*Scales — Ear* plays a scale up (or up and down) and asks for its type.
Items are ``scale.ear.melodic-minor`` and so on. Melodic minor comes down as
natural minor, so "up and down" is what makes it recognisable.

The basic pool is major and the three minors; the church modes (level 2)
and the pentatonic scales (by ear) are behind settings. Explanations give
the pattern of whole and half steps and what sets the type apart from its
neighbours ("harmonic minor raises the seventh degree").

Scales are written with accidentals, not a key signature, and only on
tonics that need no double sharps or flats.
"""

from __future__ import annotations

import itertools
import random
from collections.abc import Callable, Mapping, Sequence
from fractions import Fraction
from gettext import gettext as _
from gettext import pgettext
from typing import ClassVar, cast

from ...audio.spec import PlaybackSpec
from ...core import Pitch, PitchName, Scale, ScaleType
from ...core.naming import pitch_name, scale_name, scale_type_name
from ...learning.model import ItemId
from ...notation.spec import Chord, Clef, Figure, Head, Ink, StaffSpec, SystemSpec
from ..base import (
    BoolSetting,
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
)

BASIC = ('major', 'natural-minor', 'harmonic-minor', 'melodic-minor')
"""Level 1: the major scale and the three forms of minor."""
MODES = ('dorian', 'phrygian', 'lydian', 'mixolydian', 'locrian')
"""Level 2: the church modes other than Ionian (major) and Aeolian (natural minor)."""
PENTATONIC = ('major-pentatonic', 'minor-pentatonic')
_TYPES = {t.value: t for t in ScaleType}
_WRONG = 'wrong'

# Pairs that learners confuse.
_CONFUSABLE: dict[str, tuple[str, ...]] = {
    'major': ('mixolydian', 'lydian', 'major-pentatonic'),
    'natural-minor': ('harmonic-minor', 'dorian', 'phrygian'),
    'harmonic-minor': ('melodic-minor', 'natural-minor'),
    'melodic-minor': ('harmonic-minor', 'dorian'),
    'dorian': ('natural-minor', 'melodic-minor'),
    'phrygian': ('natural-minor', 'locrian'),
    'lydian': ('major',),
    'mixolydian': ('major', 'dorian'),
    'locrian': ('phrygian',),
    'major-pentatonic': ('major', 'minor-pentatonic'),
    'minor-pentatonic': ('major-pentatonic', 'natural-minor'),
}

# Degrees that set a type apart, highlighted in the worked answer.
_CHARACTERISTIC: dict[str, tuple[int, ...]] = {
    'harmonic-minor': (7,),
    'melodic-minor': (6, 7),
    'dorian': (6,),
    'phrygian': (2,),
    'lydian': (4,),
    'mixolydian': (7,),
    'locrian': (2, 5),
}

_TONICS = tuple(
    PitchName.parse(text)
    for text in (
        'C', 'G', 'D', 'A', 'E', 'B', 'F#', 'C#', 'F', 'Bb', 'Eb', 'Ab', 'Db', 'Gb', 'G#', 'D#',
    )
)  # fmt: skip
_CLEFS = {'treble': Clef.TREBLE, 'bass': Clef.BASS}
_WHITE_KEY_ACCIDENTALS = frozenset(PitchName.parse(n) for n in ('E#', 'B#', 'Fb', 'Cb'))
"""A wrong note is a sharp or flat on a black key, so it reads as a plain mistake."""
_STAFF_RANGE = (-2, 10)
"""Staff positions a written scale may use: one ledger line either side."""


# Scale types -------------------------------------------------------------------------


def type_label(key: str) -> str:
    """Option label: "Harmonic minor", "Dorian"."""
    name = scale_type_name(_TYPES[key])
    return name[:1].upper() + name[1:]


def scale_for(tonic: PitchName, key: str) -> Scale:
    return Scale(tonic, _TYPES[key])


def accidental_count(scale: Scale) -> int:
    """Sharps and flats written in the scale, ascending and descending forms together."""
    names = set(scale.names()) | set(scale.names(descending=True))
    return sum(abs(n.alter) for n in names)


def spellable(scale: Scale) -> bool:
    """True when no note of the scale needs a double sharp or flat."""
    names = set(scale.names()) | set(scale.names(descending=True))
    return all(abs(n.alter) <= 1 for n in names)


def tonics_for(key: str, limit: int = 7) -> list[PitchName]:
    """Tonics whose scale of type ``key`` is spellable with at most ``limit`` accidentals;
    the tonics with the fewest accidentals when none is within the limit."""
    scales = [scale_for(t, key) for t in _TONICS]
    usable = [s for s in scales if spellable(s)]
    within = [s.tonic for s in usable if accidental_count(s) <= limit]
    if within:
        return within
    fewest = min(accidental_count(s) for s in usable)
    return [s.tonic for s in usable if accidental_count(s) == fewest]


def _step_names() -> dict[int, str]:
    ctx = 'scale step'
    return {
        1: pgettext(ctx, 'half'),
        2: pgettext(ctx, 'whole'),
        # Translators: a step of three semitones in a scale (an augmented second or a
        # minor third), as in "whole, half, whole, whole, half, step and a half, half".
        3: pgettext(ctx, 'step and a half'),
        4: pgettext(ctx, 'two whole steps'),
    }


def step_pattern(pitches: Sequence[Pitch]) -> str:
    """The steps between neighbouring notes, e.g. "whole, whole, half, …"."""
    names = _step_names()
    steps = [abs(b.midi - a.midi) for a, b in itertools.pairwise(pitches)]
    # Translators: separator between the steps of a scale pattern, "whole, whole, half".
    return _(', ').join(names.get(s, str(s)) for s in steps)


def character(scale: Scale) -> str:
    """What sets this scale type apart, with the notes of this scale."""

    def note(degree: int) -> str:
        return pitch_name(scale.degree(degree))

    templates: dict[str, Callable[[], str]] = {
        'major': lambda: _('The major scale has half steps from 3 to 4 and from 7 to 8.'),
        'natural-minor': lambda: _(
            'Natural minor has half steps from 2 to 3 and from 5 to 6, and a whole step from '
            'the seventh degree up to the tonic.'
        ),
        'harmonic-minor': lambda: _(
            'Harmonic minor raises the seventh degree of natural minor to {seventh}: a leading '
            'tone a half step below the tonic, with a step and a half from {sixth} up to it.'
        ),
        'melodic-minor': lambda: _(
            'Melodic minor raises the sixth and seventh degrees to {sixth} and {seventh} on the '
            'way up, and comes down as natural minor.'
        ),
        'dorian': lambda: _('Dorian is natural minor with a raised sixth degree, {sixth}.'),
        'phrygian': lambda: _('Phrygian is natural minor with a lowered second degree, {second}.'),
        'lydian': lambda: _('Lydian is major with a raised fourth degree, {fourth}.'),
        'mixolydian': lambda: _('Mixolydian is major with a lowered seventh degree, {seventh}.'),
        'locrian': lambda: _(
            'Locrian is natural minor with a lowered second and fifth degree, {second} and {fifth}.'
        ),
        'major-pentatonic': lambda: _(
            'The major pentatonic scale is the major scale without its fourth and seventh '
            'degrees: five notes and no half steps.'
        ),
        'minor-pentatonic': lambda: _(
            'The minor pentatonic scale is natural minor without its second and sixth degrees: '
            'five notes and no half steps.'
        ),
    }
    text = templates[scale.type.value]()
    if scale.type.size != 7:
        return text
    return text.format(
        second=note(2), fourth=note(4), fifth=note(5), sixth=note(6), seventh=note(7)
    )


def explanation(scale: Scale, pitches: Sequence[Pitch]) -> str:
    """E.g. "C harmonic minor: whole, half, … Harmonic minor raises the seventh degree …"."""
    # Translators: e.g. "C major: whole, whole, half, whole, whole, whole, half."
    pattern = _('{scale}: {steps}.').format(scale=scale_name(scale), steps=step_pattern(pitches))
    return f'{pattern} {character(scale)}'


def _pitch_label(pitch: Pitch) -> str:
    return pitch_name(pitch.name) + str(pitch.octave)


def _numbered(keys: Sequence[str]) -> tuple[Option, ...]:
    return tuple(
        Option(key, type_label(key), accel=str(i + 1) if i < 9 else None)
        for i, key in enumerate(keys)
    )


def _choice(settings: Mapping[str, object], key: str, allowed: Sequence[str], default: str) -> str:
    value = str(settings.get(key, default))
    return value if value in allowed else default


def _confusables(prefix: str, key: str) -> list[ItemId]:
    return [ItemId(f'{prefix}{partner}') for partner in _CONFUSABLE.get(key, ())]


# Scales — Staff ----------------------------------------------------------------------


def staff_item(key: str, *, wrong: bool = False) -> ItemId:
    """``scale.staff.major`` (name the type) or ``scale.staff.wrong.major`` (spot the note)."""
    return ItemId(f'scale.staff.{_WRONG}.{key}' if wrong else f'scale.staff.{key}')


def parse_staff_item(item: str) -> tuple[str, bool]:
    """``(type key, wrong)``; raises :class:`ValueError` for other ids."""
    parts = item.split('.')
    wrong = len(parts) == 4 and parts[2] == _WRONG
    if (
        len(parts) not in (3, 4)
        or (len(parts) == 4 and not wrong)
        or parts[:2] != ['scale', 'staff']
        or parts[-1] not in (*BASIC, *MODES)
    ):
        raise ValueError(f'not a staff scale item: {item!r}')
    return parts[-1], wrong


def _place(scale: Scale, clef: Clef, rng: random.Random) -> list[Pitch]:
    """One ascending octave of ``scale`` that fits on ``clef`` (closest fit if none does)."""
    fits: list[tuple[int, list[Pitch]]] = []
    for octave in range(1, 7):
        pitches = list(scale.pitches(octave))
        positions = [clef.staff_position(p) for p in pitches]
        overflow = max(0, _STAFF_RANGE[0] - min(positions)) + max(
            0, max(positions) - _STAFF_RANGE[1]
        )
        fits.append((overflow, pitches))
    best = min(overflow for overflow, _ in fits)
    return rng.choice([p for overflow, p in fits if overflow == best])


def _scale_events(pitches: Sequence[Pitch]) -> tuple[Chord, ...]:
    return tuple(Chord((Head(p),)) for p in pitches)


class ScalesStaff(ExerciseDefinition):
    id = 'scale-staff'
    item_prefix = 'scale.staff.'
    family = Family.NOTATION
    modality = Modality.EYE
    level = 1
    icon_name = 'scale-staff-symbolic'
    glyph = '♮'
    settings: ClassVar[tuple[Setting, ...]] = (
        MultiChoiceSetting(
            'clefs',
            _('Clefs'),
            (Option('treble', _('Treble')), Option('bass', _('Bass'))),
            ('treble', 'bass'),
        ),
        IntSetting(
            'max-accidentals',
            _('Most accidentals'),
            4,
            0,
            7,
            subtitle=_('Largest number of sharps or flats in a scale'),
        ),
        BoolSetting(
            'spot',
            _('Spot the wrong note'),
            True,
            subtitle=_('Also find the note that does not belong to a named scale'),
        ),
        BoolSetting(
            'modes',
            _('Church modes'),
            False,
            subtitle=_('Dorian, Phrygian, Lydian, Mixolydian and Locrian'),
        ),
    )

    @property
    def title(self) -> str:
        return _('Scales — Staff')

    @property
    def description(self) -> str:
        return _('Name major and minor scales written on the staff.')

    @property
    def play_label(self) -> str:
        return _('Play scale')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        parts = [_('Modes') if settings.get('modes') else _('Major and minor')]
        if settings.get('spot', True):
            parts.append(_('spot the wrong note'))
        return _(' · ').join(parts)

    def item_label(self, item_id: ItemId) -> str:
        key, wrong = parse_staff_item(item_id)
        if wrong:
            # Translators: an item in "Weakest items", e.g. "Harmonic minor — wrong note".
            return _('{scale} — wrong note').format(scale=type_label(key))
        # Translators: an item in "Weakest items", e.g. "Harmonic minor (staff)".
        return _('{scale} (staff)').format(scale=type_label(key))

    def _pool(self, settings: Mapping[str, object]) -> list[str]:
        return [*BASIC, *(MODES if settings.get('modes') else ())]

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        """Name the type first, then spot the wrong note, type by type."""
        spot = bool(settings.get('spot', True))
        return [
            staff_item(key, wrong=wrong)
            for key in self._pool(settings)
            for wrong in ((False, True) if spot else (False,))
        ]

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        key, wrong = parse_staff_item(item_id)
        prefix = 'scale.staff.wrong.' if wrong else 'scale.staff.'
        return [i for i in _confusables(prefix, key) if i.rsplit('.', 1)[1] not in PENTATONIC]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        key, wrong = parse_staff_item(item_id)
        limit = int(cast(int, settings.get('max-accidentals', 4)))
        tonic = rng.choice(tonics_for(key, limit))
        scale = scale_for(tonic, key)
        chosen = [c for c in cast(Sequence[str], settings.get('clefs', ())) if c in _CLEFS]
        clef = _CLEFS[rng.choice(chosen or ['treble'])]
        pitches = _place(scale, clef, rng)
        playback = PlaybackSpec.melodic(pitches, note_length=Fraction(1, 2), tempo=100.0)
        if wrong:
            return self._wrong_note(item_id, scale, clef, pitches, rng)
        pool = self._pool(settings)
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Which scale is this?'),
            answer=ChoiceAnswer(_numbered(pool)),
            expected=key,
            figure=StaffSpec(clef=clef, events=_scale_events(pitches)),
            playback=playback,
            hint=_('Find the half steps: between which degrees do they fall?'),
        )

    def _wrong_note(
        self,
        item_id: ItemId,
        scale: Scale,
        clef: Clef,
        pitches: list[Pitch],
        rng: random.Random,
    ) -> Question:
        choices = [
            (degree, alter)
            for degree in range(2, 8)
            for alter in (1, -1)
            if abs(pitches[degree - 1].alter + alter) <= 1
            and PitchName(pitches[degree - 1].letter, pitches[degree - 1].alter + alter)
            not in _WHITE_KEY_ACCIDENTALS
        ]
        degree, alter = rng.choice(choices)
        right = pitches[degree - 1]
        shown = list(pitches)
        shown[degree - 1] = Pitch(right.letter, right.alter + alter, right.octave)
        options = tuple(
            Option(str(d), pitch_name(shown[d - 1].name), accel=shown[d - 1].letter.name.lower())
            for d in range(2, 8)
        )
        targets = {d - 1: str(d) for d in range(2, 8)}
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            # Translators: e.g. "Which note does not belong to C harmonic minor?"
            prompt=_('Which note does not belong to {scale}?').format(scale=scale_name(scale)),
            answer=ChoiceAnswer(options, targets=targets),
            expected=str(degree),
            figure=StaffSpec(clef=clef, events=_scale_events(shown)),
            playback=PlaybackSpec.melodic(shown, note_length=Fraction(1, 2), tempo=100.0),
            hint=_('Click the note on the staff, or pick its name.'),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        key, wrong = parse_staff_item(question.item_id)
        figure = question.figure
        assert isinstance(figure, StaffSpec)
        shown = [e.heads[0].pitch for e in figure.events if isinstance(e, Chord)]
        if wrong:
            return self._grade_wrong(question, key, figure.clef, shown, given)
        scale = scale_for(shown[0].name, key)
        expected = str(question.expected)
        correct = str(given) == expected
        label = self.answer_label(question, expected)
        if correct:
            # Translators: e.g. "Correct — harmonic minor".
            title = _('Correct — {answer}').format(answer=label)
        else:
            # Translators: e.g. "Not quite — the answer is harmonic minor".
            title = _('Not quite — the answer is {answer}').format(answer=label)
        sentences = [explanation(scale, shown)]
        play_given = None
        if not correct and str(given) in _TYPES and str(given) in (*BASIC, *MODES):
            other = scale_for(shown[0].name, str(given))
            # Translators: e.g. "For comparison: Melodic minor raises the sixth …".
            sentences.append(_('For comparison: {text}').format(text=character(other)))
            play_given = PlaybackSpec.melodic(
                other.pitches(shown[0].octave), note_length=Fraction(1, 2), tempo=100.0
            )
        return Feedback(
            correct=correct,
            title=title,
            detail=' '.join(sentences),
            expected_label=label,
            figure=_worked(figure.clef, shown, key, ()),
            play_expected=question.playback,
            play_given=play_given,
        )

    def _grade_wrong(
        self, question: Question, key: str, clef: Clef, shown: list[Pitch], given: object
    ) -> Feedback:
        scale = scale_for(shown[0].name, key)
        right = list(scale.pitches(shown[0].octave))
        degree = int(str(question.expected))
        correct = str(given) == str(question.expected)
        label = pitch_name(shown[degree - 1].name)
        if correct:
            title = _('Correct — {answer}').format(answer=label)
        else:
            title = _('Not quite — the answer is {answer}').format(answer=label)
        # Translators: e.g. "In C harmonic minor the sixth degree is A♭, not A."
        sentences = [
            _('In {scale}, degree {number} is {right}, not {wrong}.').format(
                scale=scale_name(scale),
                number=degree,
                right=pitch_name(right[degree - 1].name),
                wrong=label,
            ),
            explanation(scale, right),
        ]
        return Feedback(
            correct=correct,
            title=title,
            detail=' '.join(sentences),
            expected_label=label,
            figure=_worked(clef, right, key, (degree,)),
            play_expected=PlaybackSpec.melodic(right, note_length=Fraction(1, 2), tempo=100.0),
        )

    def answer_label(self, question: Question, value: object) -> str:
        _key, wrong = parse_staff_item(question.item_id)
        if wrong or str(value) not in _TYPES:
            return super().answer_label(question, value)
        return scale_type_name(_TYPES[str(value)])

    def serialize(self, value: object) -> str:
        return str(value)


def _worked(
    clef: Clef, pitches: Sequence[Pitch], key: str, corrected: tuple[int, ...]
) -> StaffSpec:
    """The scale with degree numbers; its telling degrees accented, corrected ones in
    success ink."""
    events = []
    marked = _CHARACTERISTIC.get(key, ())
    for index, pitch in enumerate(pitches):
        degree = index % 7 + 1
        if degree in corrected and index < 7:
            head = Head(pitch, ink=Ink.SUCCESS, halo=True)
        elif degree in marked:
            head = Head(pitch, ink=Ink.ACCENT, halo=True)
        else:
            head = Head(pitch)
        events.append(Chord((head,), label=str(degree)))
    return StaffSpec(clef=clef, events=tuple(events))


# Scales — Ear ------------------------------------------------------------------------


def ear_item(key: str) -> ItemId:
    return ItemId(f'scale.ear.{key}')


def parse_ear_item(item: str) -> str:
    parts = item.split('.')
    if len(parts) != 3 or parts[:2] != ['scale', 'ear'] or parts[2] not in _CONFUSABLE:
        raise ValueError(f'not an ear scale item: {item!r}')
    return parts[2]


_EAR_TONIC_RANGE = (57, 69)
"""MIDI range of the tonic heard: A3 to A4, so the scale stays in a singing range."""


def ear_pitches(scale: Scale, octave: int, *, both: bool) -> list[Pitch]:
    """The scale up an octave, and down again with its descending form when ``both``."""
    up = list(scale.pitches(octave))
    if not both:
        return up
    return up + list(scale.pitches(octave, descending=True))[1:]


def written_scale(pitches: Sequence[Pitch]) -> Figure:
    """The scale heard: one staff going up, and a second one coming down, so that a
    phone-width screen shows it without shrinking it out of legibility."""
    top = next((i for i in range(1, len(pitches)) if pitches[i] < pitches[i - 1]), len(pitches))
    up = StaffSpec(events=_scale_events(pitches[:top]))
    if top == len(pitches):
        return up
    down = StaffSpec(events=_scale_events(pitches[top - 1 :]))
    return SystemSpec((up, down), brace=False)


def heard_pitches(figure: Figure) -> list[Pitch]:
    """Inverse of :func:`written_scale`."""
    staves = figure.staves if isinstance(figure, SystemSpec) else (figure,)
    pitches: list[Pitch] = []
    for staff in staves:
        assert isinstance(staff, StaffSpec)
        notes = [e.heads[0].pitch for e in staff.events if isinstance(e, Chord)]
        pitches += notes[1:] if pitches else notes
    return pitches


class ScalesEar(ExerciseDefinition):
    id = 'scale-ear'
    item_prefix = 'scale.ear.'
    family = Family.EAR
    modality = Modality.EAR
    level = 1
    icon_name = 'scale-ear-symbolic'
    glyph = '♫'
    settings: ClassVar[tuple[Setting, ...]] = (
        ChoiceSetting(
            'direction',
            _('Played'),
            (
                Option('asc', _('Ascending')),
                Option('both', _('Up and down')),
            ),
            'both',
            subtitle=_('Melodic minor comes down as natural minor'),
        ),
        BoolSetting(
            'modes',
            _('Church modes'),
            False,
            subtitle=_('Dorian, Phrygian, Lydian, Mixolydian and Locrian'),
        ),
        BoolSetting(
            'pentatonic',
            _('Pentatonic scales'),
            False,
            subtitle=_('Major and minor pentatonic'),
        ),
    )

    @property
    def title(self) -> str:
        return _('Scales — Ear')

    @property
    def description(self) -> str:
        return _('Recognise major and minor scales by ear.')

    @property
    def play_label(self) -> str:
        return _('Play scale')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        both = _choice(settings, 'direction', ('asc', 'both'), 'both') == 'both'
        parts = [_('Up and down') if both else _('Ascending')]
        if settings.get('modes'):
            parts.append(_('modes'))
        if settings.get('pentatonic'):
            parts.append(_('pentatonic'))
        return _(' · ').join(parts)

    def item_label(self, item_id: ItemId) -> str:
        # Translators: an item in "Weakest items", e.g. "Harmonic minor (ear)".
        return _('{scale} (ear)').format(scale=type_label(parse_ear_item(item_id)))

    def _pool(self, settings: Mapping[str, object]) -> list[str]:
        return [
            *BASIC,
            *(MODES if settings.get('modes') else ()),
            *(PENTATONIC if settings.get('pentatonic') else ()),
        ]

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        return [ear_item(key) for key in self._pool(settings)]

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        return _confusables('scale.ear.', parse_ear_item(item_id))

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        key = parse_ear_item(item_id)
        both = _choice(settings, 'direction', ('asc', 'both'), 'both') == 'both'
        tonic = rng.choice(tonics_for(key, 5))
        octave = next(
            o for o in range(2, 6) if _EAR_TONIC_RANGE[0] <= tonic.at(o).midi <= _EAR_TONIC_RANGE[1]
        )
        scale = scale_for(tonic, key)
        pitches = ear_pitches(scale, octave, both=both)
        pool = self._pool(settings)
        if key not in pool:
            pool.append(key)
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Which scale do you hear?'),
            answer=ChoiceAnswer(_numbered(pool)),
            expected=key,
            playback=self._playback(pitches),
            playback_is_question=True,
            playback_style_choice=False,
            written_alternative=written_scale(pitches),
            # Translators: context of a scale heard, e.g. "Tonic: C4".
            context=_('Tonic: {note}').format(note=_pitch_label(pitches[0])),
            hint=_('Listen for the half steps, and for the step and a half of harmonic minor.'),
        )

    @staticmethod
    def _playback(pitches: Sequence[Pitch]) -> PlaybackSpec:
        return PlaybackSpec.melodic(pitches, note_length=Fraction(1, 2), tempo=96.0)

    def grade(self, question: Question, given: object) -> Feedback:
        key = str(question.expected)
        figure = question.written_alternative
        assert figure is not None
        heard = heard_pitches(figure)
        tonic = heard[0]
        both = len(heard) > len(_TYPES[key].intervals) + 1
        scale = scale_for(tonic.name, key)
        correct = str(given) == key
        label = self.answer_label(question, key)
        if correct:
            title = _('Correct — {answer}').format(answer=label)
        else:
            title = _('Not quite — the answer is {answer}').format(answer=label)
        sentences = [explanation(scale, scale.pitches(tonic.octave))]
        play_given = None
        if not correct and str(given) in _CONFUSABLE:
            other = scale_for(tonic.name, str(given))
            sentences.append(_('For comparison: {text}').format(text=character(other)))
            play_given = self._playback(ear_pitches(other, tonic.octave, both=both))
        return Feedback(
            correct=correct,
            title=title,
            detail=' '.join(sentences),
            expected_label=label,
            figure=figure,
            play_expected=question.playback,
            play_given=play_given,
        )

    def answer_label(self, question: Question, value: object) -> str:
        if str(value) not in _TYPES:
            return super().answer_label(question, value)
        return scale_type_name(_TYPES[str(value)])

    def serialize(self, value: object) -> str:
        return str(value)


EXERCISES: tuple[ExerciseDefinition, ...] = (ScalesStaff(), ScalesEar())
