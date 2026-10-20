# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Four-part (SATB) voicings of Roman numeral progressions for ear training.

The cadence and progression exercises play chorale-style progressions, so
the chords must move the way a harmony textbook teaches. This module finds,
for a key and a list of numerals, the four-part realisation with the
smoothest voice leading that breaks none of the common-practice rules
(Kostka & Payne, *Tonal Harmony*, ch. 5–7; Aldwell & Schachter, *Harmony and
Voice Leading*, ch. 4–6):

* **Ranges**: soprano C4–G5, alto G3–D5, tenor C3–G4, bass E2–C4; voices
  never cross or overlap the previous note of a neighbouring voice; at most
  an octave between soprano and alto and between alto and tenor.
* **Doubling**: complete chords, root doubled by preference; never the
  leading tone or a chord seventh; the bass of a six-four chord and the third
  of a diminished triad are doubled. A root-position tonic may omit its fifth
  with a tripled root (after a dominant seventh), and a root-position
  seventh chord may omit its fifth with a doubled root.
* **Motion**: no parallel or contrary fifths, octaves or unisons between
  any two voices; no direct fifths or octaves between the outer voices with
  a leap in the soprano; no augmented or diminished melodic intervals; upper
  voices leap at most a fifth, the bass at most an octave.
* **Tendency tones**: the leading tone rises to the tonic when the next
  chord has one; a chord seventh falls by step.

Among the realisations that obey the rules, a dynamic programme picks the one
with the least total motion of the upper voices (a common tone is kept when it
can be), preferring the preferred doublings and a soprano near the middle of
its range. Results are cached per key and progression, so generating many
questions stays fast.
"""

from __future__ import annotations

import itertools
import random
from collections.abc import Mapping, Sequence
from fractions import Fraction
from functools import cache
from gettext import gettext as _

from ...audio.spec import Instrument, PlaybackNote, PlaybackSpec
from ...core import Chord, ChordKind, ChordQuality, Duration, Interval, Pitch, PitchName
from ...core import Quality as IntervalQuality
from ...core.roman import RomanNumeral
from ...core.scale import Key, Mode
from ...notation.spec import Barline, BarStyle, Clef, Head, Ink, StaffSpec, SystemSpec
from ...notation.spec import Chord as StaffChord
from ..base import ChoiceSetting, IntSetting, Option, Setting
from .scale_degrees import key_for

Voicing = tuple[Pitch, Pitch, Pitch, Pitch]
"""Soprano, alto, tenor, bass."""

RANGES = ((60, 79), (55, 74), (48, 67), (40, 60))
"""MIDI ranges of soprano (C4–G5), alto (G3–D5), tenor (C3–G4) and bass (E2–C4)."""
_UPPER_SPACING = 12
_TENOR_BASS_SPACING = 19
_UPPER_LEAP = 7
_BASS_LEAP = 12
_SOPRANO_CENTRE = 70


class NoVoicingError(ValueError):
    """No realisation of a progression obeys the rules (never raised for the
    progressions the exercises use; the tests check every key)."""


# Single chords -----------------------------------------------------------------


def _doubling_cost(chord: Chord, key: Key, names: Sequence[PitchName]) -> float | None:
    """Cost of the doubling in a four-note voicing, or ``None`` when it breaks a rule."""
    tones = chord.names()
    counts = [names.count(t) for t in tones]
    if any(n not in tones for n in names):
        return None
    root, third = counts[0], counts[1]
    if root == 0 or third == 0:
        return None
    seventh_chord = chord.quality.kind is ChordKind.SEVENTH
    if seventh_chord and counts[3] != 1:
        return None
    if key.leading_tone in tones and counts[tones.index(key.leading_tone)] > 1:
        return None
    if counts[2] == 0:
        # An incomplete chord: root position only, with the root doubled (sevenths) or
        # tripled (a tonic after a dominant seventh).
        if chord.inversion != 0:
            return None
        if seventh_chord:
            return 1.0 if root == 2 else None
        if chord.quality not in (ChordQuality.MAJOR, ChordQuality.MINOR) or root != 3:
            return None
        return 3.0
    if seventh_chord:
        return 0.0
    doubled = next(i for i, c in enumerate(counts) if c == 2)
    if chord.inversion == 2:
        return 0.0 if doubled == 2 else None
    if chord.quality is ChordQuality.DIMINISHED:
        return 0.0 if doubled == 1 else None
    if chord.inversion == 1:
        return (0.0, 1.5, 0.5)[doubled]
    return (0.0, 3.0, 1.5)[doubled]


def _pitches_in(name: PitchName, low: int, high: int) -> list[Pitch]:
    return [p for p in (name.at(o) for o in range(1, 7)) if low <= p.midi <= high]


@cache
def candidates(chord: Chord, key: Key) -> tuple[tuple[Voicing, float], ...]:
    """Every rule-abiding four-part voicing of ``chord`` with its cost."""
    tones = chord.names()
    pools = [
        [p for name in tones for p in _pitches_in(name, low, high)] for low, high in RANGES[:3]
    ]
    basses = _pitches_in(chord.bass, *RANGES[3])
    result: list[tuple[Voicing, float]] = []
    for bass in basses:
        for soprano, alto, tenor in itertools.product(*pools):
            if not soprano.midi > alto.midi > tenor.midi > bass.midi:
                continue
            if soprano.midi - alto.midi > _UPPER_SPACING or alto.midi - tenor.midi > _UPPER_SPACING:
                continue
            if tenor.midi - bass.midi > _TENOR_BASS_SPACING:
                continue
            voicing = (soprano, alto, tenor, bass)
            cost = _doubling_cost(chord, key, [p.name for p in voicing])
            if cost is None:
                continue
            cost += abs(soprano.midi - _SOPRANO_CENTRE) * 0.15
            result.append((voicing, cost))
    return tuple(result)


# Motion ------------------------------------------------------------------------


@cache
def bad_melodic_interval(a: Pitch, b: Pitch) -> bool:
    """Augmented and diminished melodic intervals (an augmented second, a chromatic
    semitone) are not sung in chorale style."""
    if a == b:
        return False
    low, high = (a, b) if (a.diatonic_index, a.midi) <= (b.diatonic_index, b.midi) else (b, a)
    try:
        interval = Interval.between(low, high)
    except ValueError:
        return True
    return interval.quality in (
        IntervalQuality.AUGMENTED,
        IntervalQuality.DIMINISHED,
        IntervalQuality.DOUBLY_AUGMENTED,
        IntervalQuality.DOUBLY_DIMINISHED,
    )


def parallel_perfects(prev: Voicing, cur: Voicing) -> list[tuple[int, int]]:
    """Voice pairs (upper, lower index) moving in parallel or contrary fifths,
    octaves or unisons from ``prev`` to ``cur``."""
    found = []
    for i, j in itertools.combinations(range(4), 2):
        if prev[i] == cur[i] or prev[j] == cur[j]:
            continue
        before = (prev[i].midi - prev[j].midi) % 12
        after = (cur[i].midi - cur[j].midi) % 12
        if before == after and after in (0, 7):
            found.append((i, j))
    return found


def _transition_cost(
    prev: Voicing, cur: Voicing, prev_chord: Chord, cur_chord: Chord, key: Key
) -> float | None:
    moves = [c.midi - p.midi for p, c in zip(prev, cur, strict=True)]
    for voice, move in enumerate(moves):
        if abs(move) > (_BASS_LEAP if voice == 3 else _UPPER_LEAP):
            return None
        if bad_melodic_interval(prev[voice], cur[voice]):
            return None
    for upper in range(3):
        if cur[upper].midi <= prev[upper + 1].midi or cur[upper + 1].midi >= prev[upper].midi:
            return None  # overlap
    if parallel_perfects(prev, cur):
        return None
    soprano, bass = moves[0], moves[3]
    if soprano * bass > 0 and (cur[0].midi - cur[3].midi) % 12 in (0, 7) and abs(soprano) > 2:
        return None  # direct fifth or octave in the outer voices
    tonic = key.tonic
    resolve_leading_tone = (
        key.leading_tone in prev_chord.names()
        and tonic in cur_chord.names()
        and key.leading_tone not in cur_chord.names()
    )
    seventh = prev_chord.names()[3] if prev_chord.quality.kind is ChordKind.SEVENTH else None
    for voice in range(4):
        before, after = prev[voice], cur[voice]
        if (
            resolve_leading_tone
            and before.name == key.leading_tone
            and (after.name != tonic or after.midi != before.midi + 1)
        ):
            return None
        if (
            seventh is not None
            and before.name == seventh
            and not 1 <= before.midi - after.midi <= 2
        ):
            return None
    cost = sum(abs(m) for m in moves[:3]) + 0.3 * abs(bass)
    if all(m > 0 for m in moves) or all(m < 0 for m in moves):
        cost += 2.0
    return cost


# Progressions -------------------------------------------------------------------


@cache
def voice_progression(
    key: Key,
    numerals: tuple[RomanNumeral, ...],
    soprano_first: frozenset[PitchName] | None = None,
    soprano_last: frozenset[PitchName] | None = None,
) -> tuple[Voicing, ...]:
    """The smoothest rule-abiding SATB realisation of ``numerals`` in ``key``.

    ``soprano_first`` and ``soprano_last`` restrict the soprano's first and last
    notes (a perfect authentic cadence ends with the tonic on top). Raises
    :class:`NoVoicingError` when nothing fits.
    """
    chords = [n.realize(key) for n in numerals]
    layers = [list(candidates(c, key)) for c in chords]
    if soprano_first is not None:
        layers[0] = [(v, c) for v, c in layers[0] if v[0].name in soprano_first]
    if soprano_last is not None:
        layers[-1] = [(v, c) for v, c in layers[-1] if v[0].name in soprano_last]
    best: list[list[tuple[float, int]]] = [[(cost, -1) for _v, cost in layers[0]]]
    for step in range(1, len(layers)):
        row: list[tuple[float, int]] = []
        previous = layers[step - 1]
        for voicing, own in layers[step]:
            choice = (float('inf'), -1)
            for index, (before, _c) in enumerate(previous):
                total = best[-1][index][0]
                if total >= choice[0]:
                    continue
                motion = _transition_cost(before, voicing, chords[step - 1], chords[step], key)
                if motion is not None and total + motion < choice[0]:
                    choice = (total + motion, index)
            row.append((choice[0] + own, choice[1]))
        best.append(row)
    last = best[-1]
    if not last or min(last)[0] == float('inf'):
        raise NoVoicingError(f'no voicing of {" ".join(map(str, numerals))} in {key}')
    index = min(range(len(last)), key=lambda i: last[i][0])
    path: list[Voicing] = []
    for step in range(len(layers) - 1, -1, -1):
        path.append(layers[step][index][0])
        index = best[step][index][1]
    return tuple(reversed(path))


def parse_numerals(text: str) -> tuple[RomanNumeral, ...]:
    """``'I-IV-V7-I'`` → numerals."""
    return tuple(RomanNumeral.parse(t) for t in text.split('-'))


# Display ------------------------------------------------------------------------

_SUPERSCRIPT = str.maketrans('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹')
_SUBSCRIPT = str.maketrans('0123456789', '₀₁₂₃₄₅₆₇₈₉')


def figure_text(figure: str) -> str:
    """Inversion figures as printed after a numeral: ``'6'`` → ``'⁶'``, ``'65'`` → ``'⁶₅'``."""
    if len(figure) == 2:
        return figure[0].translate(_SUPERSCRIPT) + figure[1].translate(_SUBSCRIPT)
    return figure.translate(_SUPERSCRIPT)


def numeral_label(numeral: RomanNumeral) -> str:
    """Display form with proper symbols: ``'ii°⁶'``, ``'V⁷'``, ``'♭VI'``, ``'V⁶₅/V'``."""
    if numeral.cadential:
        return 'Cad' + figure_text('64')
    primary = RomanNumeral(
        numeral.degree, numeral.quality, numeral.inversion, numeral.alter, None, False
    )
    text = primary.symbol
    figure = primary.figure
    if figure and text.endswith(figure):
        text = text[: -len(figure)] + figure_text(figure)
    if numeral.secondary is not None:
        text += '/' + numeral_label(numeral.secondary)
    return text


def progression_label(numerals: Sequence[RomanNumeral]) -> str:
    """``'I–IV–V⁷–I'``."""
    return '–'.join(numeral_label(n) for n in numerals)


def system_figure(
    key: Key,
    voicings: Sequence[Voicing],
    *,
    durations: Sequence[Duration],
    labels: Sequence[str] | None = None,
    inks: Sequence[Ink] | None = None,
    description: str | None = None,
) -> SystemSpec:
    """A grand staff: soprano and alto on the treble staff, tenor and bass on the bass
    staff, with ``labels`` (Roman numerals) under the system."""
    signature = key.signature

    def chord(pitch: Pitch, index: int, label: str | None = None) -> StaffChord:
        ink = inks[index] if inks is not None else Ink.FOREGROUND
        return StaffChord((Head(pitch, ink=ink),), durations[index], label=label, ink=ink)

    def voice(part: int, *, labelled: bool = False) -> tuple[StaffChord | Barline, ...]:
        events: list[StaffChord | Barline] = [
            chord(v[part], i, labels[i] if labelled and labels is not None else None)
            for i, v in enumerate(voicings)
        ]
        return (*events, Barline(BarStyle.FINAL))

    upper = StaffSpec(
        clef=Clef.TREBLE, key_signature=signature, events=voice(0), voices=(voice(1),)
    )
    lower = StaffSpec(
        clef=Clef.BASS,
        key_signature=signature,
        events=voice(2, labelled=True),
        voices=(voice(3),),
    )
    return SystemSpec((upper, lower), description=description)


def voicings_of(figure: object) -> list[Voicing]:
    """The SATB chords of a figure built by :func:`system_figure`."""
    if not isinstance(figure, SystemSpec) or len(figure.staves) != 2:
        return []
    upper, lower = figure.staves

    def notes(events: Sequence[object]) -> list[Pitch]:
        return [e.heads[0].pitch for e in events if isinstance(e, StaffChord)]

    if not upper.voices or not lower.voices:
        return []
    parts = (
        notes(upper.events),
        notes(upper.voices[0]),
        notes(lower.events),
        notes(lower.voices[0]),
    )
    return [(s, a, t, b) for s, a, t, b in zip(*parts, strict=True)]


def progression_playback(
    voicings: Sequence[Voicing],
    lengths: Sequence[Fraction],
    *,
    tempo: float,
    instrument: Instrument = Instrument.PIANO,
) -> PlaybackSpec:
    """The chords one after another, each held ``lengths[i]`` beats (slightly detached)."""
    notes: list[PlaybackNote] = []
    start = Fraction(0)
    for voicing, length in zip(voicings, lengths, strict=True):
        held = length - Fraction(1, 16)
        for index, pitch in enumerate(voicing):
            velocity = 84 if index in (0, 3) else 72
            notes.append(PlaybackNote(pitch.midi, start, held, velocity))
        start += length
    return PlaybackSpec(tuple(notes), tempo=tempo, instrument=instrument)


# Settings shared by the harmony ear exercises ----------------------------------------

_INSTRUMENTS = {
    'piano': Instrument.PIANO,
    'organ': Instrument.ORGAN,
    'strings': Instrument.STRINGS,
    'choir': Instrument.CHOIR,
}


def mode_setting(default: str = 'major') -> ChoiceSetting:
    return ChoiceSetting(
        'mode',
        _('Keys'),
        (
            Option('major', _('Major')),
            Option('minor', _('Minor')),
            Option('both', _('Major and minor')),
        ),
        default,
    )


def harmony_settings(*, tempo: int = 80) -> tuple[Setting, ...]:
    """Key signatures, tempo and instrument of a progression."""
    return (
        IntSetting(
            'accidentals',
            _('Key signatures'),
            4,
            0,
            6,
            subtitle=_('Keys with up to this many sharps or flats'),
        ),
        IntSetting('tempo', _('Tempo'), tempo, 50, 120, subtitle=_('Chords per minute')),
        ChoiceSetting(
            'instrument',
            _('Instrument'),
            (
                Option('piano', _('Piano')),
                Option('organ', _('Organ')),
                Option('strings', _('Strings')),
                Option('choir', _('Choir')),
                Option('varied', _('Varied')),
            ),
            'piano',
            subtitle=_('Varied timbres help you hear the harmony, not the instrument'),
        ),
    )


def modes(settings: Mapping[str, object]) -> tuple[Mode, ...]:
    choice = settings.get('mode', 'major')
    if choice == 'minor':
        return (Mode.MINOR,)
    if choice == 'both':
        return (Mode.MAJOR, Mode.MINOR)
    return (Mode.MAJOR,)


def _int(settings: Mapping[str, object], key: str, default: int) -> int:
    value = settings.get(key, default)
    return int(value) if isinstance(value, int | float) else default


def pick_key(mode: Mode, settings: Mapping[str, object], rng: random.Random) -> Key:
    limit = max(0, min(6, _int(settings, 'accidentals', 4)))
    return key_for(mode, rng.randint(-limit, limit))


def pick_instrument(settings: Mapping[str, object], rng: random.Random) -> Instrument:
    choice = str(settings.get('instrument', 'piano'))
    if choice == 'varied':
        return rng.choice(tuple(_INSTRUMENTS.values()))
    return _INSTRUMENTS.get(choice, Instrument.PIANO)


def tempo_of(settings: Mapping[str, object], default: int = 80) -> float:
    return float(max(50, min(120, _int(settings, 'tempo', default))))


def describe_keys(settings: Mapping[str, object]) -> str:
    chosen = modes(settings)
    if len(chosen) == 2:
        return _('Major and minor keys')
    return _('Minor keys') if chosen[0] is Mode.MINOR else _('Major keys')


def key_of(figure: object) -> Key | None:
    """The key of a figure built by :func:`system_figure` whose first chord is the
    tonic: the signature gives the tonic, the first chord the mode."""
    voicings = voicings_of(figure)
    if not voicings or not isinstance(figure, SystemSpec):
        return None
    signature = figure.staves[0].key_signature
    if signature is None:
        return None
    names = {p.name for p in voicings[0]}
    minor = key_for(Mode.MINOR, signature.fifths)
    if minor.tonic in names and minor.degree(3) in names:
        return minor
    return key_for(Mode.MAJOR, signature.fifths)
