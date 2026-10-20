# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Inversions by ear: hear a triad or seventh chord and say which tone is in the bass.

The chord's quality is given in the context line ("Minor triad"), so the
question is only the inversion: root position, first, second or (sevenths)
third inversion. Items are quality × inversion, ``inversion.ear.minor.first``
or ``inversion.ear.dom7.third``; the root, register and instrument vary.

Augmented triads and diminished seventh chords are left out: they divide the
octave equally, so their inversions sound like root positions of other chords
of the same kind and cannot be told apart by ear.

Two voicings (setting ``voicing``): *close*, the chord stacked as tightly as
possible above the bass, where the intervals above the bass (5/3, 6/3, 6/4 …)
give the inversion away; and *keyboard*, a bass note in the left hand under
the full chord in any position in the right hand, as a pianist plays it,
where only the bass tells (Kostka & Payne, *Tonal Harmony*, ch. 3).
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from gettext import gettext as _
from gettext import pgettext
from typing import ClassVar, cast

from ...audio.spec import Instrument, PlaybackSpec
from ...core import Chord, ChordQuality, Pitch, PitchName
from ...core.naming import chord_quality_name, pitch_name
from ...learning.model import ItemId
from ...notation.spec import Chord as StaffChord
from ...notation.spec import Clef, Figure, Head, Ink, StaffSpec, SystemSpec
from ..base import (
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
from .chords import INVERSIONS, chord_playback

TRIADS = {
    'major': ChordQuality.MAJOR,
    'minor': ChordQuality.MINOR,
    'dim': ChordQuality.DIMINISHED,
}
SEVENTHS = {
    'dom7': ChordQuality.DOMINANT_SEVENTH,
    'maj7': ChordQuality.MAJOR_SEVENTH,
    'min7': ChordQuality.MINOR_SEVENTH,
    'hdim7': ChordQuality.HALF_DIMINISHED_SEVENTH,
}
QUALITIES = {**TRIADS, **SEVENTHS}
_ROOTS = tuple(
    PitchName.parse(n)
    for n in ('C', 'D', 'E', 'F', 'G', 'A', 'B', 'Bb', 'Eb', 'Ab', 'Db', 'F#', 'C#', 'Gb')
)
_CLOSE_BASS = (45, 57)
"""MIDI range of the bass of a close chord: A2 to A3."""
_LEFT_HAND = (38, 52)
"""MIDI range of the left-hand bass of a keyboard voicing: D2 to E3."""
_RIGHT_HAND_LOW = (55, 66)
"""MIDI range of the lowest right-hand note: G3 to F♯4 (every pitch class once)."""
_INSTRUMENTS = (Instrument.PIANO, Instrument.ORGAN, Instrument.GUITAR, Instrument.STRINGS)

_CONFUSABLE = {
    'root': ('second', 'first'),
    'first': ('second', 'root'),
    'second': ('first', 'root'),
    'third': ('second', 'first'),
}


def inversion_label(index: int) -> str:
    return (
        pgettext('inversion', 'Root position'),
        pgettext('inversion', 'First inversion'),
        pgettext('inversion', 'Second inversion'),
        pgettext('inversion', 'Third inversion'),
    )[index]


def _inversion_name(index: int) -> str:
    return (
        pgettext('inversion', 'root position'),
        pgettext('inversion', 'first inversion'),
        pgettext('inversion', 'second inversion'),
        pgettext('inversion', 'third inversion'),
    )[index]


def _figures(quality: ChordQuality, index: int) -> str | None:
    """The option's second line: the figured-bass symbol (none for a triad's third
    inversion, offered when sevenths are asked too)."""
    figures = ('5/3', '6/3', '6/4') if quality.size == 3 else ('7', '6/5', '4/3', '4/2')
    return figures[index] if index < len(figures) else None


def above_bass(quality: ChordQuality, index: int) -> str:
    """The intervals above the bass in close position."""
    if quality.size == 3:
        return (
            _('Above the bass you hear a third and a fifth (5/3).'),
            _('Above the bass you hear a third and a sixth (6/3).'),
            _('Above the bass you hear a fourth and a sixth (6/4).'),
        )[index]
    return (
        _('Above the bass you hear a third, a fifth and a seventh (7).'),
        _('Above the bass you hear a third, a fifth and a sixth (6/5).'),
        _('Above the bass you hear a third, a fourth and a sixth (4/3).'),
        _('Above the bass you hear a second, a fourth and a sixth (4/2).'),
    )[index]


def _bass_sentence(index: int) -> str:
    # Translators: {bass} is a note name, e.g. "The third, G, is in the bass."
    return (
        _('The root, {bass}, is in the bass.'),
        _('The third, {bass}, is in the bass.'),
        _('The fifth, {bass}, is in the bass.'),
        _('The seventh, {bass}, is in the bass.'),
    )[index]


def item_id(quality: str, inversion: int) -> ItemId:
    """``inversion.ear.minor.first``."""
    return ItemId(f'inversion.ear.{quality}.{INVERSIONS[inversion]}')


def parse_item(item: str) -> tuple[str, int]:
    parts = item.split('.')
    if (
        len(parts) != 4
        or parts[:2] != ['inversion', 'ear']
        or parts[2] not in QUALITIES
        or parts[3] not in INVERSIONS
        or INVERSIONS.index(parts[3]) >= QUALITIES[parts[2]].size
    ):
        raise ValueError(f'not an inversion item: {item!r}')
    return parts[2], INVERSIONS.index(parts[3])


def _pool(settings: Mapping[str, object]) -> list[str]:
    chosen = cast(Sequence[str], settings.get('qualities', ('major', 'minor')))
    triads = [q for q in TRIADS if q in chosen]
    sevenths = str(settings.get('sevenths', 'none'))
    if sevenths == 'dominant':
        return [*triads, 'dom7']
    if sevenths == 'all':
        return [*triads, *SEVENTHS]
    return triads


def _spellable(root: PitchName, quality: ChordQuality) -> bool:
    return all(abs(n.alter) <= 1 for n in Chord(root, quality).names())


def _nearest(name: PitchName, low: int, high: int, rng: random.Random) -> Pitch:
    return rng.choice([p for p in (name.at(o) for o in range(1, 7)) if low <= p.midi <= high])


def keyboard_voicing(chord: Chord, rng: random.Random) -> tuple[Pitch, ...]:
    """A left-hand bass under the whole chord, close, in any position, in the right hand."""
    bass = _nearest(chord.bass, *_LEFT_HAND, rng)
    position = rng.randrange(chord.quality.size)
    upper = chord.with_inversion(position)
    lowest = _nearest(upper.bass, *_RIGHT_HAND_LOW, rng)
    return (bass, *upper.pitches(lowest.octave))


def _staff_overflow(clef: Clef, pitches: Sequence[Pitch]) -> int:
    positions = [clef.staff_position(p) for p in pitches]
    return max(0, -3 - min(positions)) + max(0, max(positions) - 11)


def written(pitches: Sequence[Pitch], keyboard: bool) -> Figure:
    """A close chord on the staff that fits it best; a keyboard voicing on a grand staff."""
    if keyboard:
        return SystemSpec(
            (
                StaffSpec(
                    clef=Clef.TREBLE, events=(StaffChord(tuple(Head(p) for p in pitches[1:])),)
                ),
                StaffSpec(clef=Clef.BASS, events=(StaffChord((Head(pitches[0]),)),)),
            )
        )
    clef = min((Clef.BASS, Clef.TREBLE), key=lambda c: _staff_overflow(c, pitches))
    return StaffSpec(clef=clef, events=(StaffChord(tuple(Head(p) for p in pitches)),))


def pitches_of(figure: Figure | None) -> list[Pitch]:
    staves = figure.staves if isinstance(figure, SystemSpec) else (figure,)
    return sorted(
        head.pitch
        for staff in staves
        if isinstance(staff, StaffSpec)
        for event in staff.events
        if isinstance(event, StaffChord)
        for head in event.heads
    )


class InversionEar(ExerciseDefinition):
    id = 'inversion-ear'
    item_prefix = 'inversion.ear.'
    family = Family.EAR
    modality = Modality.EAR
    level = 2
    icon_name = 'inversion-ear-symbolic'
    glyph = '⁶₄'
    settings: ClassVar[tuple[Setting, ...]] = (
        MultiChoiceSetting(
            'qualities',
            _('Triads'),
            (
                Option('major', pgettext('chord quality, short', 'Major')),
                Option('minor', pgettext('chord quality, short', 'Minor')),
                Option('dim', pgettext('chord quality, short', 'Diminished')),
            ),
            ('major', 'minor'),
        ),
        ChoiceSetting(
            'sevenths',
            _('Seventh chords'),
            (
                Option('none', _('None')),
                Option('dominant', _('Dominant sevenths')),
                Option('all', _('Dominant, major, minor and half-diminished')),
            ),
            'none',
        ),
        ChoiceSetting(
            'voicing',
            _('Voicing'),
            (
                Option('close', _('Close position')),
                Option('keyboard', _('Bass under a right-hand chord')),
            ),
            'close',
            subtitle=_('With a right-hand chord on top, only the bass tells the inversion'),
        ),
        ChoiceSetting(
            'style',
            _('Playback'),
            (
                Option('block', _('Block chord')),
                Option('both', _('Broken, then block')),
            ),
            'block',
        ),
        ChoiceSetting(
            'instrument',
            _('Instrument'),
            (Option('piano', _('Piano')), Option('varied', _('Varied'))),
            'piano',
        ),
    )

    @property
    def title(self) -> str:
        return _('Inversions — Ear')

    @property
    def description(self) -> str:
        return _('Hear which chord tone is in the bass.')

    @property
    def play_label(self) -> str:
        return _('Play chord')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        sevenths = str(settings.get('sevenths', 'none')) != 'none'
        kinds = _('Triads and sevenths') if sevenths else _('Triads')
        voicing = (
            _('keyboard voicing') if settings.get('voicing') == 'keyboard' else _('close position')
        )
        return _(' · ').join((kinds, voicing))

    def item_label(self, item_id: ItemId) -> str:
        quality, inversion = parse_item(item_id)
        # Translators: an item in "Weakest items", e.g. "Minor triad, first inversion (ear)".
        text = _('{quality}, {inversion} (ear)').format(
            quality=chord_quality_name(QUALITIES[quality]), inversion=_inversion_name(inversion)
        )
        return text[:1].upper() + text[1:]

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        """Major and minor triads first, root position before the inversions, then
        diminished triads, then sevenths."""
        pool = _pool(settings)
        stages = (
            [q for q in ('major', 'minor') if q in pool],
            [q for q in ('dim',) if q in pool],
            [q for q in SEVENTHS if q in pool],
        )
        return [
            item_id(q, i)
            for stage in stages
            for i in range(4)
            for q in stage
            if i < QUALITIES[q].size
        ]

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        quality, inversion = parse_item(item_id)
        size = QUALITIES[quality].size
        return [
            ItemId(f'inversion.ear.{quality}.{other}')
            for other in _CONFUSABLE[INVERSIONS[inversion]]
            if INVERSIONS.index(other) < size
        ]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        quality_key, inversion = parse_item(item_id)
        quality = QUALITIES[quality_key]
        root = rng.choice([r for r in _ROOTS if _spellable(r, quality)])
        chord = Chord(root, quality, inversion)
        keyboard = settings.get('voicing') == 'keyboard'
        if keyboard:
            pitches = keyboard_voicing(chord, rng)
        else:
            bass = _nearest(chord.bass, *_CLOSE_BASS, rng)
            pitches = chord.pitches(bass.octave)
        instrument = (
            rng.choice(_INSTRUMENTS) if settings.get('instrument') == 'varied' else Instrument.PIANO
        )
        style = 'both' if settings.get('style') == 'both' else 'block'
        figure = written(pitches, keyboard)
        sevenths = quality.size == 4 or any(QUALITIES[q].size == 4 for q in _pool(settings))
        options = tuple(
            Option(INVERSIONS[i], inversion_label(i), str(i + 1), _figures(quality, i))
            for i in range(4 if sevenths else 3)
        )
        name = chord_quality_name(quality)
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Which inversion do you hear?'),
            answer=ChoiceAnswer(options),
            expected=INVERSIONS[inversion],
            figure=figure,
            playback=chord_playback(pitches, style=style, instrument=instrument),
            playback_is_question=True,
            playback_style_choice=False,
            written_alternative=figure,
            context=name[:1].upper() + name[1:],
            hint=_(
                'Sing the lowest note, then find it in the chord: root, third, fifth or seventh?'
            ),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        quality_key, inversion = parse_item(question.item_id)
        quality = QUALITIES[quality_key]
        pitches = pitches_of(question.written_alternative)
        chord = next(c for c in Chord.identify(pitches) if c.quality is quality)
        expected = str(question.expected)
        correct = str(given) == expected
        label = self.answer_label(question, expected)
        if correct:
            # Translators: e.g. "Correct — first inversion".
            title = _('Correct — {answer}').format(answer=label)
        else:
            # Translators: e.g. "Not quite — the answer is first inversion".
            title = _('Not quite — the answer is {answer}').format(answer=label)
        sentences = [
            _bass_sentence(inversion).format(bass=pitch_name(chord.bass)),
            above_bass(quality, inversion),
        ]
        play_given = None
        if not correct and str(given) in INVERSIONS:
            other = INVERSIONS.index(str(given))
            if other < quality.size:
                play_given = self._playback_for(question, chord, pitches, other)
                sentences.append(
                    # Translators: e.g. "In second inversion the fifth, D, would be in the bass."
                    _('In {inversion} {bass} would be in the bass.').format(
                        inversion=_inversion_name(other),
                        bass=pitch_name(chord.with_inversion(other).bass),
                    )
                )
        return Feedback(
            correct=correct,
            title=title,
            detail=' '.join(sentences),
            expected_label=label,
            figure=self._annotated(question.written_alternative),
            play_expected=question.playback,
            play_given=play_given,
        )

    def answer_label(self, question: Question, value: object) -> str:
        text = str(value)
        if text not in INVERSIONS:
            return super().answer_label(question, value)
        return _inversion_name(INVERSIONS.index(text))

    @staticmethod
    def _annotated(figure: Figure | None) -> Figure | None:
        """The written chord with its bass in the accent colour."""
        pitches = pitches_of(figure)
        if not pitches:
            return figure
        lowest = pitches[0]

        def mark(staff: StaffSpec) -> StaffSpec:
            events = tuple(
                StaffChord(
                    tuple(
                        Head(h.pitch, ink=Ink.ACCENT) if h.pitch == lowest else h for h in e.heads
                    ),
                    e.duration,
                )
                if isinstance(e, StaffChord)
                else e
                for e in staff.events
            )
            return StaffSpec(clef=staff.clef, key_signature=staff.key_signature, events=events)

        if isinstance(figure, SystemSpec):
            return SystemSpec(tuple(mark(s) for s in figure.staves))
        if isinstance(figure, StaffSpec):
            return mark(figure)
        return figure

    @staticmethod
    def _playback_for(
        question: Question, chord: Chord, pitches: Sequence[Pitch], inversion: int
    ) -> PlaybackSpec:
        """The same chord with another tone in the bass, in the same register."""
        other = chord.with_inversion(inversion)
        bass = min(
            (other.bass.at(o) for o in range(1, 7)), key=lambda p: abs(p.midi - pitches[0].midi)
        )
        if isinstance(question.written_alternative, SystemSpec):
            heard = (bass, *pitches[1:])
        else:
            heard = other.pitches(bass.octave)
        playback = question.playback
        assert playback is not None
        style = 'block' if all(n.start == 0 for n in playback.notes) else 'both'
        return chord_playback(heard, style=style, instrument=playback.instrument)


EXERCISES: tuple[ExerciseDefinition, ...] = (InversionEar(),)
