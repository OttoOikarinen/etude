# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared helpers of the harmony exercises. This module defines no exercise.

* Roman numerals and figures for display: :func:`roman_label`,
  :func:`numeral_base`, :func:`figure_text`, :data:`TRIAD_FIGURES`,
  :data:`SEVENTH_FIGURES`.
* Keys and the common settings: :func:`keys_within`, :func:`modes_setting`
  (``mode``: major, minor or both), :func:`limit_setting`
  (``max-accidentals``), :func:`key_from_signature`.
* Four-part figures and sound: :func:`satb_figure`, :func:`satb_voices`,
  :func:`satb_durations`, :func:`progression_playback`,
  :func:`playback_lengths`, and :func:`chord_of` to name the chord of a
  voicing.

Four-part voicings themselves come from :func:`etude.checkers.realize.realize`,
the project's only voicer.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from fractions import Fraction

from ...audio.spec import PlaybackNote, PlaybackSpec
from ...checkers.realize import Voicing
from ...core import Chord, ChordKind, ChordQuality, Duration, KeySignature, Pitch
from ...core.roman import RomanNumeral
from ...core.scale import Key, Mode
from ...notation.spec import Barline, BarStyle, Clef, Event, Head, Ink, StaffSpec, SystemSpec
from ...notation.spec import Chord as StaffChord
from ..base import ExerciseDefinition

MAX_ACCIDENTALS = 7

# Roman numerals -------------------------------------------------------------------------

_PRETTY_FIGURES = {'': '', '6': '6', '64': '6/4', '7': '7', '65': '6/5', '43': '4/3', '42': '4/2'}
TRIAD_FIGURES = ('53', '6', '64')
"""Item segments of triad inversions (``53`` is root position)."""
SEVENTH_FIGURES = ('7', '65', '43', '42')
"""Item segments of seventh-chord inversions."""


def figure_text(figure: str) -> str:
    """A figure as written after a numeral: ``'65'`` → ``'6/5'``, ``'53'`` → ``''``."""
    return _PRETTY_FIGURES.get('' if figure == '53' else figure, figure)


def roman_label(numeral: RomanNumeral) -> str:
    """Display form with slashed figures and quality signs, as Kostka–Payne print
    them: ``'V6/5'``, ``'vii°7'``, ``'iiø4/3'``, ``'IV'``, ``'V6/5/V'``, ``'♭II6'``,
    ``'Cad6/4'``."""
    if numeral.secondary is not None:
        primary = RomanNumeral(numeral.degree, numeral.quality, numeral.inversion, numeral.alter)
        return f'{roman_label(primary)}/{roman_label(numeral.secondary)}'
    if numeral.cadential:
        return 'Cad' + figure_text('64')
    symbol = numeral.symbol
    figure = numeral.figure
    if not figure or numeral.quality.kind is ChordKind.AUGMENTED_SIXTH:
        return symbol
    return symbol[: len(symbol) - len(figure)] + figure_text(figure)


def numeral_base(numeral: RomanNumeral) -> str:
    """The numeral without inversion figures, but with ``7`` for seventh chords:
    ``'V7'`` for V6/5, ``'vii°'`` for vii°6."""
    root = RomanNumeral(numeral.degree, numeral.quality, 0, numeral.alter)
    return root.symbol


# Keys ------------------------------------------------------------------------------------


def keys_within(limit: int, modes: Sequence[Mode]) -> list[Key]:
    """Keys with at most ``limit`` sharps or flats, per mode, in line-of-fifths order."""
    keys = []
    for mode in modes:
        for fifths in range(-MAX_ACCIDENTALS, MAX_ACCIDENTALS + 1):
            if abs(fifths) > limit:
                continue
            signature = KeySignature(fifths)
            tonic = signature.major_tonic if mode is Mode.MAJOR else signature.minor_tonic
            keys.append(Key(tonic, mode))
    return keys


def modes_setting(settings: Mapping[str, object], default: str = 'major') -> tuple[Mode, ...]:
    """The ``mode`` choice setting: ``'major'``, ``'minor'`` or ``'both'``."""
    choice = settings.get('mode', default)
    if choice == 'minor':
        return (Mode.MINOR,)
    if choice == 'both':
        return (Mode.MAJOR, Mode.MINOR)
    return (Mode.MAJOR,)


def limit_setting(settings: Mapping[str, object], default: int = 4) -> int:
    """The ``max-accidentals`` integer setting, clamped to 0–7."""
    value = settings.get('max-accidentals', default)
    return max(0, min(MAX_ACCIDENTALS, value if isinstance(value, int) else default))


def key_from_signature(signature: KeySignature | None, mode: Mode) -> Key:
    """The major or minor key of a signature (``None`` is C major or A minor), e.g. to
    read a question's key back from its figure."""
    signature = signature or KeySignature(0)
    tonic = signature.major_tonic if mode is Mode.MAJOR else signature.minor_tonic
    return Key(tonic, mode)


# Figures and playback ------------------------------------------------------------------


def satb_figure(
    voices: Sequence[Voicing],
    signature: KeySignature | None = None,
    *,
    durations: Sequence[Duration] = (),
    labels: Sequence[str | None] = (),
    highlight: Collection[int] = (),
    final_bar: bool = False,
    description: str | None = None,
    inks: Mapping[tuple[int, int], Ink] | None = None,
    marks: Mapping[int, str] | None = None,
) -> SystemSpec:
    """Four voices on a grand staff: soprano and alto on the treble staff, tenor
    and bass on the bass staff.

    * ``durations`` (one per chord) draws each staff as two voices with stems up
      and down, as in a chorale; without them each staff shows one stemless
      two-note chord per slot.
    * ``labels`` (one per chord, ``None`` for none) are written under the bass
      staff: Roman numerals, or figured-bass figures with lines separated by
      ``'\\n'``.
    * Chords whose index is in ``highlight`` are drawn in the accent colour, with
      their labels (the cadence of a phrase, the chord a question asked about).

    * ``inks`` colours single notes by ``(voice, chord)`` (voice-leading mistakes in
      error ink, a correct answer in success ink), and ``marks`` writes a short text
      under the treble staff at a chord, in error ink (the rule a mistake breaks).

    :func:`satb_voices` reads the voicings back.
    """
    inks = inks or {}
    marks = marks or {}

    def chord(i: int, voice: int, *, labelled: bool = False) -> StaffChord:
        ink = Ink.ACCENT if i in highlight else Ink.FOREGROUND
        parts = (voice,) if durations else (voice + 1, voice)
        heads = tuple(Head(voices[i][v], ink=inks.get((v, i), ink)) for v in parts)
        label = (labels[i] if i < len(labels) else None) if labelled else None
        stem = ink
        if voice == 0 and i in marks:
            label, stem = marks[i], Ink.ERROR
        elif len({h.ink for h in heads}) == 1 and heads[0].ink is not ink and not labelled:
            stem = heads[0].ink
        return StaffChord(heads, durations[i] if durations else None, label=label, ink=stem)

    count = range(len(voices))
    if durations:
        ending: tuple[Event, ...] = (Barline(BarStyle.FINAL),) if final_bar else ()
        treble = StaffSpec(
            clef=Clef.TREBLE,
            key_signature=signature,
            events=(*(chord(i, 0) for i in count), *ending),
            voices=((*(chord(i, 1) for i in count), *ending),),
        )
        low = StaffSpec(
            clef=Clef.BASS,
            key_signature=signature,
            events=(*(chord(i, 2) for i in count), *ending),
            voices=((*(chord(i, 3, labelled=True) for i in count), *ending),),
        )
    else:
        ending = (Barline(BarStyle.FINAL),) if final_bar else ()
        treble = StaffSpec(
            clef=Clef.TREBLE,
            key_signature=signature,
            events=(*(chord(i, 0) for i in count), *ending),
        )
        low = StaffSpec(
            clef=Clef.BASS,
            key_signature=signature,
            events=(*(chord(i, 2, labelled=True) for i in count), *ending),
        )
    return SystemSpec(staves=(treble, low), description=description)


def satb_durations(figure: object) -> tuple[Duration, ...]:
    """The note values of a figure made by :func:`satb_figure` (empty if stemless)."""
    if not isinstance(figure, SystemSpec) or not figure.staves:
        return ()
    events = [e for e in figure.staves[0].events if isinstance(e, StaffChord)]
    found = tuple(e.duration for e in events if e.duration is not None)
    return found if len(found) == len(events) else ()


def satb_voices(figure: object) -> list[Voicing]:
    """The voicings of a figure made by :func:`satb_figure`, soprano first; empty for
    any other figure."""
    if not isinstance(figure, SystemSpec) or len(figure.staves) != 2:
        return []
    treble, low = figure.staves

    def notes(staff: StaffSpec) -> list[list[Pitch]]:
        lines = [staff.events, *staff.voices]
        columns = [[e for e in line if isinstance(e, StaffChord)] for line in lines]
        if staff.voices:
            # One voice per line, upper voice first: keep the order even when the
            # voices cross (a passage with a mistake).
            return [
                [chord.heads[0].pitch for chord in column] for column in zip(*columns, strict=True)
            ]
        return [
            sorted((h.pitch for chord in column for h in chord.heads), reverse=True)
            for column in zip(*columns, strict=True)
        ]

    result = []
    for top, bottom in zip(notes(treble), notes(low), strict=True):
        s, a = top
        t, b = bottom
        result.append((s, a, t, b))
    return result


def progression_playback(
    voices: Sequence[Sequence[Pitch]], lengths: Sequence[Fraction] = (), tempo: float = 76.0
) -> PlaybackSpec:
    """Block chords one after another, ``lengths`` in beats (one beat each by default).

    Works for any number of voices per chord; :func:`playback_lengths`
    turns note values into lengths.
    """
    notes: list[PlaybackNote] = []
    start = Fraction(0)
    for i, voicing in enumerate(voices):
        length = lengths[i] if i < len(lengths) else Fraction(1)
        notes.extend(PlaybackNote(p.midi, start, length) for p in voicing)
        start += length
    return PlaybackSpec(tuple(notes), tempo=tempo)


def playback_lengths(durations: Sequence[Duration]) -> list[Fraction]:
    """Note values as playback lengths in beats (quarter notes)."""
    return [d.quarter_length for d in durations]


def chord_of(pitches: Sequence[Pitch], quality: ChordQuality | None = None) -> Chord:
    """The tertian chord spelled by ``pitches`` (lowest pitch = bass).

    A chord without its fifth (an incomplete V7 or a final tonic with a tripled
    root, both in root position) is read as the complete chord on its bass.
    """
    found = [c for c in Chord.identify(pitches) if c.quality.is_tertian]
    if quality is not None:
        found = [c for c in found if c.quality is quality] or found
    if found:
        return found[0]
    names = {p.name for p in pitches}
    bass = min(pitches).name
    for candidate in ChordQuality:
        if not candidate.is_tertian or (quality is not None and candidate is not quality):
            continue
        try:
            tones = Chord(bass, candidate).names()
        except ValueError:
            continue
        if names <= set(tones) and set(tones) - names == {tones[2]}:
            return Chord(bass, candidate)
    raise ValueError(f'no tertian chord in {pitches}')


EXERCISES: tuple[ExerciseDefinition, ...] = ()
