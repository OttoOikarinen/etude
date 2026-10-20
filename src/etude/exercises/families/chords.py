# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Chords: name triads and seventh chords on the staff (design 1f) and by ear.

*Chords — Staff* shows a chord and asks for its root, quality and
inversion with three chip groups. Items are quality × inversion,
``chord.staff.minor.root`` or ``chord.staff.dom7.second``; the root, clef,
register, spacing and key signature vary per question, so the learner
learns to stack thirds rather than to recognise one picture.

*Chord Quality — Ear* plays a chord and asks for its quality. Items are
qualities, ``chord.ear.major`` or ``chord.ear.dim7``; root, register,
inversion and instrument vary.

Chord tones are always spelled from the root (B♭ diminished is B♭ D♭ F♭),
so the root chips offer natural letters with a ♯ / ♭ chip, and roots whose
chords would need triple sharps or flats are never asked.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from gettext import gettext as _
from gettext import pgettext
from typing import cast

from ...audio.spec import Instrument, PlaybackSpec
from ...core import Chord, ChordQuality, KeySignature, Letter, Pitch, PitchName
from ...core.naming import chord_name, chord_quality_name, pitch_name
from ...learning.model import ItemId
from ...notation.spec import Chord as StaffChord
from ...notation.spec import Clef, Figure, Head, Ink, StaffSpec
from ..base import (
    BoolSetting,
    ChipGroup,
    ChipsAnswer,
    ChoiceAnswer,
    ChoiceSetting,
    ExerciseDefinition,
    Family,
    Feedback,
    Modality,
    MultiChoiceSetting,
    Option,
    Question,
)

# Qualities ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Quality:
    key: str
    """Item segment and chip value, e.g. ``'minor'`` or ``'dom7'``."""
    quality: ChordQuality

    def label(self) -> str:
        """Short chip or button label ("Minor", "Dominant 7th")."""
        return _short_labels()[self.key]

    def structure(self) -> str:
        """The intervals above the root, as a sentence with ``{notes}`` and ``{root}``."""
        return _structures()[self.key]

    def character(self) -> str:
        """How the chord is built and sounds, for ear-training feedback."""
        return _characters()[self.key]

    def indefinite(self) -> str:
        """The quality name with an indefinite article, "an augmented triad"."""
        return _indefinite_names()[self.key]


def _short_labels() -> dict[str, str]:
    ctx = 'chord quality, short'
    return {
        'major': pgettext(ctx, 'Major'),
        'minor': pgettext(ctx, 'Minor'),
        'dim': pgettext(ctx, 'Diminished'),
        'aug': pgettext(ctx, 'Augmented'),
        'dom7': pgettext(ctx, 'Dominant 7th'),
        'maj7': pgettext(ctx, 'Major 7th'),
        'min7': pgettext(ctx, 'Minor 7th'),
        'hdim7': pgettext(ctx, 'Half-diminished'),
        'dim7': pgettext(ctx, 'Diminished 7th'),
    }


def _structures() -> dict[str, str]:
    return {
        # Translators: these sentences explain a chord, e.g. "E–G–B: a minor third and a
        # perfect fifth above E." {notes} lists the chord tones from the root; {root} is the root.
        'major': _('{notes}: a major third and a perfect fifth above {root}.'),
        'minor': _('{notes}: a minor third and a perfect fifth above {root}.'),
        'dim': _('{notes}: a minor third and a diminished fifth above {root}.'),
        'aug': _('{notes}: a major third and an augmented fifth above {root}.'),
        'dom7': _('{notes}: a major third, a perfect fifth and a minor seventh above {root}.'),
        'maj7': _('{notes}: a major third, a perfect fifth and a major seventh above {root}.'),
        'min7': _('{notes}: a minor third, a perfect fifth and a minor seventh above {root}.'),
        'hdim7': _('{notes}: a minor third, a diminished fifth and a minor seventh above {root}.'),
        'dim7': _(
            '{notes}: a minor third, a diminished fifth and a diminished seventh above {root}.'
        ),
    }


def _characters() -> dict[str, str]:
    return {
        'major': _('A major triad stacks a major and a minor third; it sounds bright and stable.'),
        'minor': _('A minor triad stacks a minor and a major third; it sounds darker but stable.'),
        'dim': _('A diminished triad stacks two minor thirds; its diminished fifth sounds tense.'),
        'aug': _('An augmented triad stacks two major thirds; it sounds bright but unsettled.'),
        'dom7': _('A dominant seventh is a major triad with a minor seventh; it wants to resolve.'),
        'maj7': _(
            'A major seventh chord is a major triad with a major seventh, a semitone below '
            'the octave; it sounds soft.'
        ),
        'min7': _('A minor seventh chord is a minor triad with a minor seventh; it sounds mellow.'),
        'hdim7': _(
            'A half-diminished seventh is a diminished triad with a minor seventh; it sounds '
            'darker than a minor seventh chord.'
        ),
        'dim7': _(
            'A diminished seventh stacks three minor thirds; it sounds tense and symmetrical.'
        ),
    }


def _indefinite_names() -> dict[str, str]:
    # Translators: chord qualities as in "the answer is a minor triad". Languages
    # without articles use the bare name.
    ctx = 'chord quality with article'
    return {
        'major': pgettext(ctx, 'a major triad'),
        'minor': pgettext(ctx, 'a minor triad'),
        'dim': pgettext(ctx, 'a diminished triad'),
        'aug': pgettext(ctx, 'an augmented triad'),
        'dom7': pgettext(ctx, 'a dominant seventh'),
        'maj7': pgettext(ctx, 'a major seventh'),
        'min7': pgettext(ctx, 'a minor seventh'),
        'hdim7': pgettext(ctx, 'a half-diminished seventh'),
        'dim7': pgettext(ctx, 'a diminished seventh'),
    }


_TRIADS = (
    _Quality('major', ChordQuality.MAJOR),
    _Quality('minor', ChordQuality.MINOR),
    _Quality('dim', ChordQuality.DIMINISHED),
    _Quality('aug', ChordQuality.AUGMENTED),
)
_SEVENTHS = (
    _Quality('dom7', ChordQuality.DOMINANT_SEVENTH),
    _Quality('maj7', ChordQuality.MAJOR_SEVENTH),
    _Quality('min7', ChordQuality.MINOR_SEVENTH),
    _Quality('hdim7', ChordQuality.HALF_DIMINISHED_SEVENTH),
    _Quality('dim7', ChordQuality.DIMINISHED_SEVENTH),
)
_QUALITIES = {q.key: q for q in (*_TRIADS, *_SEVENTHS)}
_BY_QUALITY = {q.quality: q for q in _QUALITIES.values()}
_TRIAD_KEYS = tuple(q.key for q in _TRIADS)
_SEVENTH_KEYS = tuple(q.key for q in _SEVENTHS)

INVERSIONS = ('root', 'first', 'second', 'third')
"""Item segment and chip value of each inversion, indexed by the inversion number."""


def _inversion_chip(index: int) -> str:
    return (
        _('Root position'),
        # Translators: chip label for "first inversion" (design 1f).
        pgettext('inversion', 'First'),
        # Translators: chip label for "second inversion" (design 1f).
        pgettext('inversion', 'Second'),
        # Translators: chip label for "third inversion".
        pgettext('inversion', 'Third'),
    )[index]


def _inversion_name(index: int) -> str:
    return (
        pgettext('inversion', 'root position'),
        pgettext('inversion', 'first inversion'),
        pgettext('inversion', 'second inversion'),
        pgettext('inversion', 'third inversion'),
    )[index]


def _bass_sentence(index: int) -> str:
    # Translators: {bass} is a note name, e.g. "The third, G, is in the bass: first inversion."
    return (
        _('The root, {bass}, is in the bass: root position.'),
        _('The third, {bass}, is in the bass: first inversion.'),
        _('The fifth, {bass}, is in the bass: second inversion.'),
        _('The seventh, {bass}, is in the bass: third inversion.'),
    )[index]


def _capitalized(text: str) -> str:
    return text[:1].upper() + text[1:]


# Roots, spelling and register -------------------------------------------------------

_SUFFIX = {-1: 'b', 0: '', 1: '#'}
_UNCOMMON_ROOTS = frozenset(PitchName.parse(n) for n in ('E#', 'B#', 'Fb', 'Cb'))
_ALL_ROOTS = tuple(PitchName(letter, alter) for alter in (0, -1, 1) for letter in Letter)


def root_value(name: PitchName) -> str:
    """A root as the chips widget reports it: ``'E'``, ``'F#'`` or ``'Bb'``."""
    return name.letter.name + _SUFFIX[name.alter]


def _roots(choice: object) -> tuple[PitchName, ...]:
    if choice == 'natural':
        return _ALL_ROOTS[:7]
    if choice == 'all':
        return _ALL_ROOTS
    return tuple(n for n in _ALL_ROOTS if n not in _UNCOMMON_ROOTS)


def _spellable(root: PitchName, quality: ChordQuality) -> bool:
    """Chord tones need at most double sharps or flats."""
    return all(abs(n.alter) <= 2 for n in Chord(root, quality).names())


def voicing(chord: Chord, bass_octave: int, *, open_position: bool = False) -> tuple[Pitch, ...]:
    """The chord with its bass in ``bass_octave``, lowest pitch first.

    Close position stacks the tones as tightly as possible. Open position
    raises the tone just above the bass by an octave (C3 G3 E4 for C major,
    C3 G3 B3 E4 for C major seventh), so the chord spans at most an eleventh.
    """
    close = chord.pitches(bass_octave)
    if not open_position:
        return close
    raised = close[1]
    raised = Pitch(raised.letter, raised.alter, raised.octave + 1)
    return (close[0], *close[2:], raised)


_STAFF_LOW = -3
"""Lowest staff position that needs no second ledger line (just below the first)."""
_STAFF_HIGH = 11


def _overflow(clef: Clef, pitches: Sequence[Pitch]) -> int:
    positions = [clef.staff_position(p) for p in pitches]
    return max(0, _STAFF_LOW - min(positions)) + max(0, max(positions) - _STAFF_HIGH)


def _place(chord: Chord, clef: Clef, open_position: bool, rng: random.Random) -> tuple[Pitch, ...]:
    """A voicing in a register that sits on the staff with at most one ledger line.

    An open chord that cannot fit (a wide one whose octaves both overflow) is
    written in close position instead, which always fits.
    """
    for spread in (True, False) if open_position else (False,):
        candidates = [voicing(chord, octave, open_position=spread) for octave in range(1, 7)]
        fitting = [c for c in candidates if _overflow(clef, c) == 0]
        if fitting:
            return rng.choice(fitting)
    return min(candidates, key=lambda c: _overflow(clef, c))


def _signature_for(chord: Chord, rng: random.Random) -> KeySignature:
    """A key signature that supplies as many of the chord's accidentals as possible."""
    names = chord.names()

    def misses(fifths: int) -> int:
        signature = KeySignature(fifths)
        return sum(n.alter != signature.alter_for(n.letter) for n in names)

    options = range(-6, 7)
    best = min(misses(f) for f in options)
    return KeySignature(rng.choice([f for f in options if misses(f) == best]))


def _figure_pitches(figure: Figure | None) -> tuple[Pitch, ...]:
    if not isinstance(figure, StaffSpec):
        return ()
    return tuple(
        head.pitch
        for event in figure.events
        if isinstance(event, StaffChord)
        for head in event.heads
    )


def _note_list(names: Sequence[PitchName]) -> str:
    # Translators: separator between the notes of a chord, "E–G–B".
    return _('–').join(pitch_name(n) for n in names)


def _structure(chord: Chord) -> str:
    return (
        _BY_QUALITY[chord.quality]
        .structure()
        .format(notes=_note_list(chord.names()), root=pitch_name(chord.root))
    )


_PLAY_TEMPO = 96.0


def chord_playback(
    pitches: Sequence[Pitch], *, style: str = 'both', instrument: Instrument = Instrument.PIANO
) -> PlaybackSpec:
    """``'broken'`` (lowest note first), ``'block'`` or ``'both'`` (broken, then block)."""
    broken = PlaybackSpec.melodic(
        pitches, note_length=Fraction(1, 2), tempo=_PLAY_TEMPO, instrument=instrument
    )
    block = PlaybackSpec.harmonic(
        pitches, length=Fraction(2), tempo=_PLAY_TEMPO, instrument=instrument
    )
    if style == 'broken':
        return broken
    if style == 'block':
        return block
    return PlaybackSpec.sequence(broken, block, gap=Fraction(1, 2))


def _playback_style(playback: PlaybackSpec | None, size: int) -> str:
    if playback is None or len(playback.notes) > size:
        return 'both'
    return 'block' if all(n.start == 0 for n in playback.notes) else 'broken'


# Settings helpers -----------------------------------------------------------------


def _quality_pool(settings: Mapping[str, object]) -> tuple[str, ...]:
    chosen = cast(Sequence[str], settings.get('qualities', _TRIAD_KEYS))
    triads = tuple(k for k in _TRIAD_KEYS if k in chosen)
    sevenths = _SEVENTH_KEYS if settings.get('sevenths', False) else ()
    return (*triads, *sevenths)


def _clefs(settings: Mapping[str, object]) -> list[Clef]:
    chosen = cast(Sequence[str], settings.get('clefs', ()))
    return [c for c in (Clef.TREBLE, Clef.BASS, Clef.ALTO, Clef.TENOR) if c.value in chosen]


def _chord_types_text(settings: Mapping[str, object]) -> str:
    if settings.get('sevenths', False):
        return _('triads and sevenths')
    return _('triads')


_DIGITS = '1234567890'
_SPARE_KEYS = 'qwtyuiop'
"""Accelerators once the digits run out: letters that are not note names (a–g select
the root) and not R (replay)."""


def _numbered(options: Sequence[tuple[str, str]], start: int = 0) -> tuple[Option, ...]:
    keys = _DIGITS + _SPARE_KEYS
    return tuple(
        Option(key, label, keys[start + i] if start + i < len(keys) else None)
        for i, (key, label) in enumerate(options)
    )


_CLEF_NAMES: dict[Clef, Callable[[], str]] = {
    Clef.TREBLE: lambda: _('Treble clef'),
    Clef.BASS: lambda: _('Bass clef'),
    Clef.ALTO: lambda: _('Alto clef'),
    Clef.TENOR: lambda: _('Tenor clef'),
}

_QUALITY_SETTING = MultiChoiceSetting(
    'qualities',
    _('Triads'),
    tuple(Option(q.key, q.label()) for q in _TRIADS),
    _TRIAD_KEYS,
)
_SEVENTHS_SETTING = BoolSetting(
    'sevenths',
    _('Seventh chords'),
    False,
    subtitle=_('Dominant, major, minor, half-diminished and diminished sevenths'),
)


# Chords — Staff ---------------------------------------------------------------------


def staff_item(quality: str, inversion: int) -> ItemId:
    """``chord.staff.minor.root`` or ``chord.staff.dom7.second``."""
    return ItemId(f'chord.staff.{quality}.{INVERSIONS[inversion]}')


def parse_staff_item(item: str) -> tuple[str, int]:
    """Inverse of :func:`staff_item`; raises :class:`ValueError` for other ids."""
    parts = item.split('.')
    if (
        len(parts) != 4
        or parts[:2] != ['chord', 'staff']
        or parts[2] not in _QUALITIES
        or parts[3] not in INVERSIONS
    ):
        raise ValueError(f'not a chord item: {item!r}')
    quality, inversion = parts[2], INVERSIONS.index(parts[3])
    if inversion >= _QUALITIES[quality].quality.size:
        raise ValueError(f'not a chord item: {item!r}')
    return quality, inversion


class ChordsStaff(ExerciseDefinition):
    id = 'chord-staff'
    item_prefix = 'chord.staff.'
    family = Family.HARMONY
    modality = Modality.EYE
    level = 1
    icon_name = 'chord-symbolic'
    glyph = '♮'
    settings = (
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
        _QUALITY_SETTING,
        _SEVENTHS_SETTING,
        BoolSetting(
            'inversions',
            _('Inversions'),
            True,
            subtitle=_('Ask for the inversion as well as the root and quality'),
        ),
        BoolSetting(
            'open',
            _('Open position'),
            False,
            subtitle=_('Spread some chords over more than an octave'),
        ),
        BoolSetting(
            'key-signature',
            _('Key signatures'),
            False,
            subtitle=_('Write chords in a key, with accidentals from its signature'),
        ),
        ChoiceSetting(
            'roots',
            _('Roots'),
            (
                Option('natural', _('Natural notes only')),
                Option('common', _('Common sharps and flats')),
                Option('all', _('All sharps and flats')),
            ),
            'common',
            subtitle=_('“All” adds E♯, B♯, F♭ and C♭'),
        ),
    )

    @property
    def title(self) -> str:
        return _('Chords — Staff')

    @property
    def description(self) -> str:
        return _('Name triads and sevenths with their inversion.')

    @property
    def play_label(self) -> str:
        return _('Play chord')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        clefs = _clefs(settings)
        clef_text = _CLEF_NAMES[clefs[0]]() if len(clefs) == 1 else _('Mixed clefs')
        return f'{clef_text} · {_chord_types_text(settings)}'

    def item_label(self, item_id: ItemId) -> str:
        quality, inversion = parse_staff_item(item_id)
        # Translators: an item in "Weakest items", e.g. "Minor triad, first inversion (staff)".
        text = _('{quality}, {inversion} (staff)').format(
            quality=chord_quality_name(_QUALITIES[quality].quality),
            inversion=_inversion_name(inversion),
        )
        return _capitalized(text)

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        """Major and minor in root position, then their inversions, then diminished
        and augmented triads, then seventh chords."""
        pool = _quality_pool(settings)
        inversions = range(4) if settings.get('inversions', True) else range(1)
        stages = (
            [q for q in ('major', 'minor') if q in pool],
            [q for q in ('dim', 'aug') if q in pool],
            [q for q in _SEVENTH_KEYS if q in pool],
        )
        return [
            staff_item(quality, inversion)
            for stage in stages
            for inversion in inversions
            for quality in stage
            if inversion < _QUALITIES[quality].quality.size
        ]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        quality_key, inversion = parse_staff_item(item_id)
        quality = _QUALITIES[quality_key].quality
        roots = [r for r in _roots(settings.get('roots')) if _spellable(r, quality)]
        chord = Chord(rng.choice(roots), quality, inversion)
        clef = rng.choice(_clefs(settings) or [Clef.TREBLE])
        open_position = bool(settings.get('open', False)) and rng.random() < 0.5
        signature = _signature_for(chord, rng) if settings.get('key-signature', False) else None
        pitches = _place(chord, clef, open_position, rng)

        # Items outside the current settings (an older review) keep their own options.
        pool = set(_quality_pool(settings)) | {quality_key}
        sevenths = any(k in pool for k in _SEVENTH_KEYS)
        ask_inversion = bool(settings.get('inversions', True)) or inversion > 0
        qualities = _numbered(
            [(q.key, q.label()) for q in _QUALITIES.values() if q.key in pool], start=0
        )
        groups = [
            ChipGroup(
                'root',
                _('Root'),
                tuple(
                    Option(
                        letter.name,
                        pitch_name(PitchName(letter)),
                        letter.name.lower(),
                        fixed_accel=True,
                    )
                    for letter in Letter
                ),
                accidentals=True,
            ),
            ChipGroup('quality', _('Quality'), qualities),
        ]
        expected = {'root': root_value(chord.root), 'quality': quality_key}
        if ask_inversion:
            count = 4 if sevenths else 3
            inversions = _numbered(
                [(INVERSIONS[i], _inversion_chip(i)) for i in range(count)], start=len(qualities)
            )
            groups.append(ChipGroup('inversion', _('Inversion'), inversions))
            expected['inversion'] = INVERSIONS[inversion]

        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Name the chord'),
            answer=ChipsAnswer(tuple(groups)),
            expected=expected,
            figure=StaffSpec(
                clef=clef,
                key_signature=signature,
                events=(StaffChord(tuple(Head(p) for p in pitches)),),
            ),
            playback=chord_playback(pitches),
            hint=_('Stack the notes in thirds: the lowest note of the stack is the root.'),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        expected = cast(Mapping[str, str], question.expected)
        quality_key, inversion = parse_staff_item(question.item_id)
        chord = Chord(PitchName.parse(expected['root']), _QUALITIES[quality_key].quality, inversion)
        given_map = given if isinstance(given, Mapping) else {}
        right = [str(given_map.get(key, '')) == value for key, value in expected.items()]
        correct = all(right)
        label = self.answer_label(question, expected)
        if correct:
            # Translators: e.g. "Correct — E minor triad, root position".
            title = _('Correct — {answer}').format(answer=label)
        else:
            # Translators: e.g. "Not quite — the answer is E minor triad, root position".
            title = _('Not quite — the answer is {answer}').format(answer=label)
        return Feedback(
            correct=correct,
            title=title,
            detail=self._explanation(chord, question.figure),
            expected_label=label,
            score=sum(right) / len(right),
            figure=self._annotated(question.figure, chord),
            play_expected=question.playback,
        )

    def answer_label(self, question: Question, value: object) -> str:
        """``'E minor triad, root position'`` or ``'B♭ dominant seventh'``."""
        if not isinstance(value, Mapping):
            return super().answer_label(question, value)
        try:
            root = PitchName.parse(str(value.get('root', '')))
            info = _QUALITIES[str(value.get('quality', ''))]
            name = chord_name(Chord(root, info.quality))
        except (KeyError, ValueError):
            return super().answer_label(question, value)
        inversion = value.get('inversion')
        if inversion not in INVERSIONS:
            return name
        # Translators: a chord and its inversion, e.g. "E minor triad, first inversion".
        return pgettext('chord and inversion', '{chord}, {inversion}').format(
            chord=name, inversion=_inversion_name(INVERSIONS.index(str(inversion)))
        )

    def serialize(self, value: object) -> str:
        if isinstance(value, Mapping):
            return ','.join(f'{k}={v}' for k, v in value.items())
        return str(value)

    @staticmethod
    def _explanation(chord: Chord, figure: Figure | None) -> str:
        parts = [
            _structure(chord),
            _bass_sentence(chord.inversion).format(bass=pitch_name(chord.bass)),
        ]
        signature = figure.key_signature if isinstance(figure, StaffSpec) else None
        if signature is not None:
            supplied = [
                n
                for n in chord.names()
                if n.alter != 0 and signature.alter_for(n.letter) == n.alter
            ]
            if supplied:
                # Translators: e.g. "The key signature supplies F♯ and C♯." The list is
                # joined with the separator for multi-part answers.
                parts.append(
                    _('The key signature supplies {notes}.').format(
                        notes=_(', ').join(pitch_name(n) for n in supplied)
                    )
                )
        return ' '.join(parts)

    @staticmethod
    def _annotated(figure: Figure | None, chord: Chord) -> Figure | None:
        """The question's chord with its root drawn in the accent colour."""
        if not isinstance(figure, StaffSpec):
            return figure
        events = tuple(
            StaffChord(
                tuple(
                    Head(h.pitch, ink=Ink.ACCENT) if h.pitch.name == chord.root else h
                    for h in event.heads
                ),
                event.duration,
            )
            if isinstance(event, StaffChord)
            else event
            for event in figure.events
        )
        return replace(figure, events=events)


# Chord Quality — Ear ----------------------------------------------------------------

_INSTRUMENTS = (Instrument.PIANO, Instrument.ORGAN, Instrument.GUITAR, Instrument.STRINGS)
_EAR_ROOTS = _roots('common')
_LOWEST_BASS = 48  # C3
_HIGHEST_BASS = 60  # C4


def ear_item(quality: str) -> ItemId:
    """``chord.ear.major`` or ``chord.ear.dim7``."""
    return ItemId(f'chord.ear.{quality}')


def parse_ear_item(item: str) -> str:
    parts = item.split('.')
    if len(parts) != 3 or parts[:2] != ['chord', 'ear'] or parts[2] not in _QUALITIES:
        raise ValueError(f'not a chord item: {item!r}')
    return parts[2]


class ChordQualityEar(ExerciseDefinition):
    id = 'chord-ear'
    item_prefix = 'chord.ear.'
    family = Family.EAR
    modality = Modality.EAR
    level = 1
    icon_name = 'chord-ear-symbolic'
    glyph = '♬'
    settings = (
        _QUALITY_SETTING,
        _SEVENTHS_SETTING,
        BoolSetting(
            'inversions',
            _('Inversions'),
            False,
            subtitle=_('Play some chords with the third, fifth or seventh in the bass'),
        ),
        ChoiceSetting(
            'style',
            _('Playback'),
            (
                Option('block', _('Block chord')),
                Option('both', _('Broken, then block')),
                Option('broken', _('Broken chord')),
            ),
            'both',
        ),
        ChoiceSetting(
            'instrument',
            _('Instrument'),
            (
                Option('piano', _('Piano')),
                Option('varied', _('Varied')),
            ),
            'piano',
            subtitle=_('Varied timbres help you hear the chord, not the instrument'),
        ),
    )

    @property
    def title(self) -> str:
        return _('Chord Quality — Ear')

    @property
    def description(self) -> str:
        return _('Recognise major, minor, diminished and augmented chords by ear.')

    @property
    def play_label(self) -> str:
        return _('Play chord')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        styles = {
            'block': _('block'),
            'broken': _('broken'),
            'both': _('broken, then block'),
        }
        style = styles.get(str(settings.get('style', 'both')), styles['both'])
        return f'{_capitalized(_chord_types_text(settings))} · {style}'

    def item_label(self, item_id: ItemId) -> str:
        quality = _QUALITIES[parse_ear_item(item_id)].quality
        # Translators: an item in "Weakest items", e.g. "Diminished triad (ear)".
        return _capitalized(_('{quality} (ear)').format(quality=chord_quality_name(quality)))

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        """Major and minor first, then diminished, augmented and the sevenths."""
        return [ear_item(q) for q in _quality_pool(settings)]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        quality_key = parse_ear_item(item_id)
        quality = _QUALITIES[quality_key].quality
        root = rng.choice([r for r in _EAR_ROOTS if _spellable(r, quality)])
        inversion = rng.randrange(quality.size) if settings.get('inversions', False) else 0
        chord = Chord(root, quality, inversion)
        octaves = [o for o in range(1, 6) if _LOWEST_BASS <= chord.bass.at(o).midi <= _HIGHEST_BASS]
        pitches = chord.pitches(rng.choice(octaves))
        instrument = (
            rng.choice(_INSTRUMENTS) if settings.get('instrument') == 'varied' else Instrument.PIANO
        )
        style = str(settings.get('style', 'both'))
        clef = min((Clef.TREBLE, Clef.BASS), key=lambda c: _overflow(c, pitches))
        figure = StaffSpec(clef=clef, events=(StaffChord(tuple(Head(p) for p in pitches)),))

        pool = set(_quality_pool(settings)) | {quality_key}
        options = _numbered([(q.key, q.label()) for q in _QUALITIES.values() if q.key in pool])
        lowest = pitch_name(pitches[0].name) + str(pitches[0].octave)
        if inversion == 0:
            # Translators: context of an ear-training question, e.g. "Root: C4".
            context = _('Root: {note}').format(note=lowest)
        else:
            # Translators: context of an ear-training question, e.g. "Lowest note: E3".
            context = _('Lowest note: {note}').format(note=lowest)
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Which chord do you hear?'),
            answer=ChoiceAnswer(options),
            expected=quality_key,
            figure=figure,
            playback=chord_playback(pitches, style=style, instrument=instrument),
            playback_is_question=True,
            playback_style_choice=False,
            written_alternative=figure,
            context=context,
            hint=_('Listen for the third first: major sounds bright, minor darker.'),
        )

    def grade(self, question: Question, given: object) -> Feedback:
        expected = str(question.expected)
        info = _QUALITIES[expected]
        chord = self._chord(question)
        label = self.answer_label(question, expected)
        correct = str(given) == expected
        if correct:
            # Translators: e.g. "Correct — minor triad".
            title = _('Correct — {answer}').format(answer=label)
        else:
            # Translators: e.g. "Not quite — the answer is a minor triad"; {answer}
            # already has its article.
            title = _('Not quite — the answer is {answer}').format(answer=info.indefinite())
        detail = [_structure(chord), info.character()]
        play_given = None
        given_info = _QUALITIES.get(str(given))
        if not correct and given_info is not None:
            # Translators: contrasts the learner's answer with the right one, e.g.
            # "For comparison: A major triad stacks a major and a minor third; …".
            detail.append(_('For comparison: {text}').format(text=given_info.character()))
            play_given = self._playback_for(question, chord, given_info.quality)
        return Feedback(
            correct=correct,
            title=title,
            detail=' '.join(detail),
            expected_label=label,
            figure=question.figure,
            play_expected=question.playback,
            play_given=play_given,
        )

    def answer_label(self, question: Question, value: object) -> str:
        """The full quality name, ``'minor triad'`` or ``'dominant seventh'``."""
        info = _QUALITIES.get(str(value))
        if info is None:
            return super().answer_label(question, value)
        return chord_quality_name(info.quality)

    @staticmethod
    def _chord(question: Question) -> Chord:
        """The spelled chord of a question, read back from its written alternative."""
        quality = _QUALITIES[str(question.expected)].quality
        pitches = _figure_pitches(question.written_alternative)
        return next(c for c in Chord.identify(pitches) if c.quality is quality)

    @staticmethod
    def _playback_for(question: Question, chord: Chord, quality: ChordQuality) -> PlaybackSpec:
        """The learner's answer on the same root, inversion (if it has one) and register."""
        other = Chord(chord.root, quality, min(chord.inversion, quality.size - 1))
        lowest = min(_figure_pitches(question.written_alternative))
        octave = lowest.octave
        if other.bass.at(octave).midi < lowest.midi - 6:
            octave += 1
        elif other.bass.at(octave).midi > lowest.midi + 6:
            octave -= 1
        playback = question.playback
        return chord_playback(
            other.pitches(octave),
            style=_playback_style(playback, chord.quality.size),
            instrument=playback.instrument if playback is not None else Instrument.PIANO,
        )


EXERCISES: tuple[ExerciseDefinition, ...] = (ChordsStaff(), ChordQualityEar())
