# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Scales, modes and keys.

Scales are spelled from their tonic by intervals, so every heptatonic
scale uses each letter exactly once (F♯ major has E♯, not F). Scales with
more or fewer than seven notes follow these spellings:

* Pentatonic: major 1 2 3 5 6, minor 1 ♭3 4 5 ♭7.
* Blues: 1 ♭3 4 ♭5 5 ♭7 (the "blue note" spelled as a diminished fifth,
  as in Levine, *The Jazz Theory Book*).
* Whole-tone: 1 2 3 ♯4 ♯5 ♯6 (C D E F♯ G♯ A♯).
* Octatonic: half-whole 1 ♭2 ♭3 ♮3 ♯4 5 6 ♭7 (C D♭ E♭ E F♯ G A B♭),
  whole-half 1 2 ♭3 4 ♭5 ♭6 ♮6 7 (C D E♭ F G♭ A♭ A B).
* Chromatic: sharps ascending and flats descending, the usual spelling
  for melodic chromatic scales.

Melodic minor and chromatic scales have separate ascending and
descending forms; :meth:`Scale.names` and :meth:`Scale.pitches` take a
``descending`` flag.

A :class:`Key` is a tonic and a major or minor :class:`Mode`. Its diatonic
chords follow Kostka & Payne (*Tonal Harmony*): the minor mode uses the
natural minor scale except that chords on the dominant and the leading
tone take the raised seventh degree (V, V7, vii°, vii°7).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .chord import Chord
from .interval import Interval
from .key import KeySignature
from .pitch import Pitch, PitchName


def _intervals(text: str) -> tuple[Interval, ...]:
    return tuple(Interval.parse(token) for token in text.split())


class ScaleType(Enum):
    MAJOR = 'major'
    NATURAL_MINOR = 'natural-minor'
    HARMONIC_MINOR = 'harmonic-minor'
    MELODIC_MINOR = 'melodic-minor'
    IONIAN = 'ionian'
    DORIAN = 'dorian'
    PHRYGIAN = 'phrygian'
    LYDIAN = 'lydian'
    MIXOLYDIAN = 'mixolydian'
    AEOLIAN = 'aeolian'
    LOCRIAN = 'locrian'
    MAJOR_PENTATONIC = 'major-pentatonic'
    MINOR_PENTATONIC = 'minor-pentatonic'
    BLUES = 'blues'
    WHOLE_TONE = 'whole-tone'
    CHROMATIC = 'chromatic'
    OCTATONIC_HALF_WHOLE = 'octatonic-half-whole'
    OCTATONIC_WHOLE_HALF = 'octatonic-whole-half'

    @property
    def intervals(self) -> tuple[Interval, ...]:
        """Intervals above the tonic of the ascending form, starting with P1."""
        return _ASCENDING[self]

    @property
    def descending_intervals(self) -> tuple[Interval, ...]:
        """Intervals above the tonic used when descending, in ascending order."""
        return _DESCENDING.get(self, _ASCENDING[self])

    @property
    def size(self) -> int:
        """Number of different notes in the octave."""
        return len(self.intervals)

    @property
    def is_mode(self) -> bool:
        """True for the seven diatonic (church) modes."""
        return self in _MODES

    @property
    def is_diatonic(self) -> bool:
        """True for scales with the interval pattern of the white keys (major, natural minor,
        modes)."""
        return self in _MODES or self in (ScaleType.MAJOR, ScaleType.NATURAL_MINOR)


_MODES = (
    ScaleType.IONIAN,
    ScaleType.DORIAN,
    ScaleType.PHRYGIAN,
    ScaleType.LYDIAN,
    ScaleType.MIXOLYDIAN,
    ScaleType.AEOLIAN,
    ScaleType.LOCRIAN,
)

_ASCENDING: dict[ScaleType, tuple[Interval, ...]] = {
    ScaleType.MAJOR: _intervals('P1 M2 M3 P4 P5 M6 M7'),
    ScaleType.NATURAL_MINOR: _intervals('P1 M2 m3 P4 P5 m6 m7'),
    ScaleType.HARMONIC_MINOR: _intervals('P1 M2 m3 P4 P5 m6 M7'),
    ScaleType.MELODIC_MINOR: _intervals('P1 M2 m3 P4 P5 M6 M7'),
    ScaleType.IONIAN: _intervals('P1 M2 M3 P4 P5 M6 M7'),
    ScaleType.DORIAN: _intervals('P1 M2 m3 P4 P5 M6 m7'),
    ScaleType.PHRYGIAN: _intervals('P1 m2 m3 P4 P5 m6 m7'),
    ScaleType.LYDIAN: _intervals('P1 M2 M3 A4 P5 M6 M7'),
    ScaleType.MIXOLYDIAN: _intervals('P1 M2 M3 P4 P5 M6 m7'),
    ScaleType.AEOLIAN: _intervals('P1 M2 m3 P4 P5 m6 m7'),
    ScaleType.LOCRIAN: _intervals('P1 m2 m3 P4 d5 m6 m7'),
    ScaleType.MAJOR_PENTATONIC: _intervals('P1 M2 M3 P5 M6'),
    ScaleType.MINOR_PENTATONIC: _intervals('P1 m3 P4 P5 m7'),
    ScaleType.BLUES: _intervals('P1 m3 P4 d5 P5 m7'),
    ScaleType.WHOLE_TONE: _intervals('P1 M2 M3 A4 A5 A6'),
    ScaleType.CHROMATIC: _intervals('P1 A1 M2 A2 M3 P4 A4 P5 A5 M6 A6 M7'),
    ScaleType.OCTATONIC_HALF_WHOLE: _intervals('P1 m2 m3 M3 A4 P5 M6 m7'),
    ScaleType.OCTATONIC_WHOLE_HALF: _intervals('P1 M2 m3 P4 d5 m6 M6 M7'),
}
_DESCENDING: dict[ScaleType, tuple[Interval, ...]] = {
    ScaleType.MELODIC_MINOR: _ASCENDING[ScaleType.NATURAL_MINOR],
    ScaleType.CHROMATIC: _intervals('P1 m2 M2 m3 M3 P4 d5 P5 m6 M6 m7 M7'),
}


@dataclass(frozen=True, slots=True)
class Scale:
    """A scale on a spelled tonic: ``Scale(PitchName.parse('D'), ScaleType.DORIAN)``."""

    tonic: PitchName
    type: ScaleType

    def __post_init__(self) -> None:
        self.names()
        self.names(descending=True)

    def names(self, *, descending: bool = False) -> tuple[PitchName, ...]:
        """Scale degrees in ascending order from the tonic.

        With ``descending=True`` the descending form is used (natural minor
        for melodic minor, flats for chromatic), still listed from the tonic
        upwards; :meth:`pitches` lists notes in the direction of travel.
        """
        intervals = self.type.descending_intervals if descending else self.type.intervals
        return tuple(self.tonic.transpose(i) for i in intervals)

    def pitches(self, octave: int = 4, *, descending: bool = False) -> tuple[Pitch, ...]:
        """One octave of the scale including both tonics.

        Ascending from the tonic in ``octave``; descending from the tonic an
        octave above it down to the tonic in ``octave``.
        """
        intervals = self.type.descending_intervals if descending else self.type.intervals
        start = self.tonic.at(octave)
        up = [start.transpose(i) for i in intervals]
        up.append(start.transpose(Interval.parse('P8')))
        return tuple(reversed(up)) if descending else tuple(up)

    def degree(self, number: int, *, descending: bool = False) -> PitchName:
        """Scale degree ``number`` (1 = tonic); numbers past the octave wrap around."""
        if number < 1:
            raise ValueError(f'scale degrees start at 1, not {number}')
        names = self.names(descending=descending)
        return names[(number - 1) % len(names)]

    def degree_of(self, name: PitchName, *, descending: bool = False) -> int | None:
        """Degree number of a spelled name, or None if the scale does not contain it."""
        names = self.names(descending=descending)
        return names.index(name) + 1 if name in names else None

    def __contains__(self, name: object) -> bool:
        return name in self.names() or name in self.names(descending=True)

    def transpose(self, interval: Interval, *, down: bool = False) -> Scale:
        return Scale(self.tonic.transpose(interval, down=down), self.type)

    def __str__(self) -> str:
        return f'{self.tonic} {self.type.value}'


class Mode(Enum):
    MAJOR = 'major'
    MINOR = 'minor'


class DegreeFunction(Enum):
    """Traditional names of the scale degrees.

    In minor the seventh degree is the *subtonic* when it lies a whole step
    below the tonic (natural minor) and the *leading tone* when raised.
    """

    TONIC = 1
    SUPERTONIC = 2
    MEDIANT = 3
    SUBDOMINANT = 4
    DOMINANT = 5
    SUBMEDIANT = 6
    LEADING_TONE = 7
    SUBTONIC = 8

    @property
    def degree(self) -> int:
        return min(self.value, 7)


_KEY_RE = re.compile(
    r'^([A-Ga-g](?:#{1,2}|x|b{1,2}|♯|♭|𝄪|𝄫)?)\s*(major|minor|maj|min|M|m)?$',
    re.IGNORECASE,
)
_RAISED = Interval.parse('A1')


@dataclass(frozen=True, slots=True)
class Key:
    """A major or minor key, e.g. ``Key(PitchName.parse('C#'), Mode.MINOR)``.

    Keys with more than seven sharps or flats (G♯ major) can be built,
    because tonicizations reach them, but have no :attr:`signature`.
    """

    tonic: PitchName
    mode: Mode = Mode.MAJOR

    @classmethod
    def parse(cls, text: str) -> Key:
        """Parse ``'E major'``, ``'c# minor'``, ``'Bbm'``, ``'F'`` or ``'f'``.

        Without a mode word an upper-case letter means major and a
        lower-case letter minor, as in Roman numeral analysis.
        """
        match = _KEY_RE.match(text.strip())
        if not match:
            raise ValueError(f'not a key: {text!r}')
        tonic_text, mode_text = match.group(1), match.group(2)
        tonic = PitchName.parse(tonic_text)
        if mode_text is None:
            mode = Mode.MAJOR if tonic_text[0].isupper() else Mode.MINOR
        elif mode_text == 'M':
            mode = Mode.MAJOR
        elif mode_text == 'm':
            mode = Mode.MINOR
        else:
            lowered = mode_text.lower()
            mode = Mode.MAJOR if lowered in ('major', 'maj') else Mode.MINOR
        return cls(tonic, mode)

    @property
    def signature(self) -> KeySignature:
        """Key signature (natural minor for minor keys). Raises ValueError for theoretical
        keys."""
        if self.mode is Mode.MAJOR:
            return KeySignature.for_major(self.tonic)
        return KeySignature.for_minor(self.tonic)

    @property
    def is_theoretical(self) -> bool:
        """True for keys that need more than seven sharps or flats."""
        fifths = self.tonic.line_of_fifths - (3 if self.mode is Mode.MINOR else 0)
        return abs(fifths) > 7

    @property
    def relative(self) -> Key:
        """The relative key: C major ↔ A minor."""
        third = Interval.parse('m3')
        if self.mode is Mode.MAJOR:
            return Key(self.tonic.transpose(third, down=True), Mode.MINOR)
        return Key(self.tonic.transpose(third), Mode.MAJOR)

    @property
    def parallel(self) -> Key:
        """The parallel key: C major ↔ C minor."""
        return Key(self.tonic, Mode.MINOR if self.mode is Mode.MAJOR else Mode.MAJOR)

    @property
    def scale(self) -> Scale:
        """The major or natural minor scale of the key."""
        kind = ScaleType.MAJOR if self.mode is Mode.MAJOR else ScaleType.NATURAL_MINOR
        return Scale(self.tonic, kind)

    @property
    def leading_tone(self) -> PitchName:
        """The note a semitone below the tonic (raised seventh degree in minor)."""
        return self.tonic.transpose(Interval.parse('M7'))

    def degree(self, number: int) -> PitchName:
        """Scale degree of the major or natural minor scale."""
        return self.scale.degree(number)

    def _chord_names(self, degree: int, size: int) -> tuple[PitchName, ...]:
        if not 1 <= degree <= 7:
            raise ValueError(f'scale degree must be 1–7, not {degree}')
        names = list(self.scale.names())
        if self.mode is Mode.MINOR and degree in (5, 7):
            names[6] = self.leading_tone
        return tuple(names[(degree - 1 + 2 * k) % 7] for k in range(size))

    def _build(self, degree: int, size: int) -> Chord:
        names = self._chord_names(degree, size)
        for chord in Chord.identify(names):
            if chord.root == names[0]:
                return chord
        raise AssertionError('diatonic chords are always tertian')  # pragma: no cover

    def triad(self, degree: int) -> Chord:
        """Diatonic triad in root position on a scale degree (1–7).

        Major: I ii iii IV V vi vii°. Minor: i ii° III iv V VI vii°.
        """
        return self._build(degree, 3)

    def seventh(self, degree: int) -> Chord:
        """Diatonic seventh chord in root position on a scale degree (1–7).

        Major: IM7 ii7 iii7 IVM7 V7 vi7 viiø7.
        Minor: i7 iiø7 IIIM7 iv7 V7 VIM7 vii°7.
        """
        return self._build(degree, 4)

    def degree_function(self, degree: int) -> DegreeFunction:
        """Name of a scale degree of the key's scale (1–7)."""
        if not 1 <= degree <= 7:
            raise ValueError(f'scale degree must be 1–7, not {degree}')
        if degree == 7 and self.mode is Mode.MINOR:
            return DegreeFunction.SUBTONIC
        return DegreeFunction(degree)

    def function_of(self, name: PitchName) -> DegreeFunction | None:
        """Name of the degree a spelled note occupies in this key, or None if chromatic.

        In minor the raised sixth and seventh degrees of the melodic minor
        are accepted: B♮ in C minor is the leading tone and A♮ the
        (raised) submediant.
        """
        degree = self.scale.degree_of(name)
        if degree is not None:
            return self.degree_function(degree)
        if self.mode is Mode.MINOR:
            if name == self.leading_tone:
                return DegreeFunction.LEADING_TONE
            if name == self.tonic.transpose(Interval.parse('M6')):
                return DegreeFunction.SUBMEDIANT
        return None

    def raised(self, degree: int) -> PitchName:
        """A scale degree raised by a chromatic semitone (♯4 in major is F♯ in C)."""
        return self.degree(degree).transpose(_RAISED)

    def __str__(self) -> str:
        if self.mode is Mode.MAJOR:
            return f'{self.tonic} major'
        return f'{str(self.tonic).lower()} minor'
