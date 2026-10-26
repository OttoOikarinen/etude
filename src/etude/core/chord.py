# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Spelled chords.

A :class:`Chord` is a root, a :class:`ChordQuality` (the spelled intervals
above the root) and an inversion (which chord tone is in the bass). Chord
tones are always spelled from the root, so C–E–G♯ is an augmented triad
and C–E–A♭ is not a chord this module recognises at all (it is an A♭
augmented triad in first inversion).

Conventions:

* Ninth, eleventh and thirteenth chords list every chord tone the symbol
  implies. Following jazz usage (Levine, *The Jazz Theory Book*), the
  dominant, major and minor thirteenth chords omit the eleventh, which is
  an avoid note over a major third and optional over a minor one. The
  eleventh chords keep their third; in practice it is often omitted.
* The augmented sixth chords (Italian, French, German) are spelled from
  the lowered sixth degree, which is treated as their "root" so that the
  usual position (♭6 in the bass) is inversion 0: A♭–C–F♯, A♭–C–D–F♯ and
  A♭–C–E♭–F♯ in C. Their spelling separates them from enharmonic chords:
  A♭–C–E♭–G♭ is a dominant seventh. In major keys the German sixth is also
  spelled with ♯2̂ instead of ♭3̂, A♭–C–D♯–F♯ in C (Kostka–Payne; Aldwell–Schachter
  call it the chord of the doubly augmented fourth), when it moves to a
  cadential six-four whose third is E♮: :attr:`ChordQuality.DOUBLY_AUGMENTED_FOURTH`.
* Inversion figures follow common-practice figured bass: 5/3, 6, 6/4 for
  triads and 7, 6/5, 4/3, 4/2 for seventh chords.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from .interval import Interval
from .pitch import Pitch, PitchName


class ChordKind(Enum):
    TRIAD = 'triad'
    SEVENTH = 'seventh'
    ADDED = 'added'
    """Added-tone chords: sixth, six-nine and add-nine chords."""
    EXTENDED = 'extended'
    """Ninth, eleventh and thirteenth chords and altered dominants."""
    AUGMENTED_SIXTH = 'augmented-sixth'


class ChordQuality(Enum):
    """The interval structure of a chord above its root.

    The value is a stable identifier, not a display string: use
    :mod:`etude.core.naming` for names and :mod:`etude.core.chord_symbol`
    for lead-sheet symbols.
    """

    # Triads
    MAJOR = 'major'
    MINOR = 'minor'
    DIMINISHED = 'diminished'
    AUGMENTED = 'augmented'
    SUS2 = 'sus2'
    SUS4 = 'sus4'
    # Seventh chords
    DOMINANT_SEVENTH = 'dominant-seventh'
    MAJOR_SEVENTH = 'major-seventh'
    MINOR_SEVENTH = 'minor-seventh'
    HALF_DIMINISHED_SEVENTH = 'half-diminished-seventh'
    DIMINISHED_SEVENTH = 'diminished-seventh'
    MINOR_MAJOR_SEVENTH = 'minor-major-seventh'
    AUGMENTED_MAJOR_SEVENTH = 'augmented-major-seventh'
    AUGMENTED_SEVENTH = 'augmented-seventh'
    # Added-tone chords
    MAJOR_SIXTH = 'major-sixth'
    MINOR_SIXTH = 'minor-sixth'
    SIX_NINE = 'six-nine'
    MINOR_SIX_NINE = 'minor-six-nine'
    ADD_NINE = 'add-nine'
    MINOR_ADD_NINE = 'minor-add-nine'
    # Altered and suspended sevenths
    DOMINANT_SEVENTH_FLAT_FIVE = 'dominant-seventh-flat-five'
    DOMINANT_SEVENTH_SUS4 = 'dominant-seventh-sus4'
    # Ninth chords
    DOMINANT_NINTH = 'dominant-ninth'
    MAJOR_NINTH = 'major-ninth'
    MINOR_NINTH = 'minor-ninth'
    MINOR_MAJOR_NINTH = 'minor-major-ninth'
    DOMINANT_NINTH_SUS4 = 'dominant-ninth-sus4'
    DOMINANT_FLAT_NINTH = 'dominant-flat-ninth'
    DOMINANT_SHARP_NINTH = 'dominant-sharp-ninth'
    DOMINANT_FLAT_FIVE_FLAT_NINTH = 'dominant-flat-five-flat-ninth'
    DOMINANT_FLAT_FIVE_SHARP_NINTH = 'dominant-flat-five-sharp-ninth'
    DOMINANT_SHARP_FIVE_FLAT_NINTH = 'dominant-sharp-five-flat-ninth'
    DOMINANT_SHARP_FIVE_SHARP_NINTH = 'dominant-sharp-five-sharp-ninth'
    # Eleventh chords
    DOMINANT_ELEVENTH = 'dominant-eleventh'
    MINOR_ELEVENTH = 'minor-eleventh'
    DOMINANT_SHARP_ELEVENTH = 'dominant-sharp-eleventh'
    DOMINANT_NINTH_SHARP_ELEVENTH = 'dominant-ninth-sharp-eleventh'
    MAJOR_SEVENTH_SHARP_ELEVENTH = 'major-seventh-sharp-eleventh'
    MAJOR_NINTH_SHARP_ELEVENTH = 'major-ninth-sharp-eleventh'
    # Thirteenth chords
    DOMINANT_THIRTEENTH = 'dominant-thirteenth'
    MAJOR_THIRTEENTH = 'major-thirteenth'
    MINOR_THIRTEENTH = 'minor-thirteenth'
    DOMINANT_THIRTEENTH_FLAT_NINTH = 'dominant-thirteenth-flat-ninth'
    DOMINANT_THIRTEENTH_SHARP_ELEVENTH = 'dominant-thirteenth-sharp-eleventh'
    DOMINANT_FLAT_THIRTEENTH = 'dominant-flat-thirteenth'
    ALTERED = 'altered'
    # Augmented sixth chords
    ITALIAN_SIXTH = 'italian-sixth'
    FRENCH_SIXTH = 'french-sixth'
    GERMAN_SIXTH = 'german-sixth'
    DOUBLY_AUGMENTED_FOURTH = 'doubly-augmented-fourth'
    """The German sixth spelled with a doubly augmented fourth above the bass (♯2̂ for
    ♭3̂ in major): A♭–C–D♯–F♯."""

    @property
    def intervals(self) -> tuple[Interval, ...]:
        """Intervals of the chord tones above the root, in chord-tone order."""
        return _STRUCTURE[self][1]

    @property
    def kind(self) -> ChordKind:
        return _STRUCTURE[self][0]

    @property
    def size(self) -> int:
        """Number of chord tones, root included."""
        return len(self.intervals) + 1

    @property
    def is_tertian(self) -> bool:
        """True for the four triads and eight seventh chords of common-practice harmony."""
        return self.kind in (ChordKind.TRIAD, ChordKind.SEVENTH) and self not in (
            ChordQuality.SUS2,
            ChordQuality.SUS4,
        )

    @property
    def pitch_classes(self) -> frozenset[int]:
        """Pitch classes of the chord on C."""
        return frozenset({0, *(i.semitones % 12 for i in self.intervals)})


def _parse(text: str) -> tuple[Interval, ...]:
    return tuple(Interval.parse(token) for token in text.split())


_Q = ChordQuality
_K = ChordKind
_STRUCTURE: dict[ChordQuality, tuple[ChordKind, tuple[Interval, ...]]] = {
    q: (k, _parse(s))
    for q, k, s in [
        (_Q.MAJOR, _K.TRIAD, 'M3 P5'),
        (_Q.MINOR, _K.TRIAD, 'm3 P5'),
        (_Q.DIMINISHED, _K.TRIAD, 'm3 d5'),
        (_Q.AUGMENTED, _K.TRIAD, 'M3 A5'),
        (_Q.SUS2, _K.TRIAD, 'M2 P5'),
        (_Q.SUS4, _K.TRIAD, 'P4 P5'),
        (_Q.DOMINANT_SEVENTH, _K.SEVENTH, 'M3 P5 m7'),
        (_Q.MAJOR_SEVENTH, _K.SEVENTH, 'M3 P5 M7'),
        (_Q.MINOR_SEVENTH, _K.SEVENTH, 'm3 P5 m7'),
        (_Q.HALF_DIMINISHED_SEVENTH, _K.SEVENTH, 'm3 d5 m7'),
        (_Q.DIMINISHED_SEVENTH, _K.SEVENTH, 'm3 d5 d7'),
        (_Q.MINOR_MAJOR_SEVENTH, _K.SEVENTH, 'm3 P5 M7'),
        (_Q.AUGMENTED_MAJOR_SEVENTH, _K.SEVENTH, 'M3 A5 M7'),
        (_Q.AUGMENTED_SEVENTH, _K.SEVENTH, 'M3 A5 m7'),
        (_Q.MAJOR_SIXTH, _K.ADDED, 'M3 P5 M6'),
        (_Q.MINOR_SIXTH, _K.ADDED, 'm3 P5 M6'),
        (_Q.SIX_NINE, _K.ADDED, 'M3 P5 M6 M9'),
        (_Q.MINOR_SIX_NINE, _K.ADDED, 'm3 P5 M6 M9'),
        (_Q.ADD_NINE, _K.ADDED, 'M3 P5 M9'),
        (_Q.MINOR_ADD_NINE, _K.ADDED, 'm3 P5 M9'),
        (_Q.DOMINANT_SEVENTH_FLAT_FIVE, _K.EXTENDED, 'M3 d5 m7'),
        (_Q.DOMINANT_SEVENTH_SUS4, _K.EXTENDED, 'P4 P5 m7'),
        (_Q.DOMINANT_NINTH, _K.EXTENDED, 'M3 P5 m7 M9'),
        (_Q.MAJOR_NINTH, _K.EXTENDED, 'M3 P5 M7 M9'),
        (_Q.MINOR_NINTH, _K.EXTENDED, 'm3 P5 m7 M9'),
        (_Q.MINOR_MAJOR_NINTH, _K.EXTENDED, 'm3 P5 M7 M9'),
        (_Q.DOMINANT_NINTH_SUS4, _K.EXTENDED, 'P4 P5 m7 M9'),
        (_Q.DOMINANT_FLAT_NINTH, _K.EXTENDED, 'M3 P5 m7 m9'),
        (_Q.DOMINANT_SHARP_NINTH, _K.EXTENDED, 'M3 P5 m7 A9'),
        (_Q.DOMINANT_FLAT_FIVE_FLAT_NINTH, _K.EXTENDED, 'M3 d5 m7 m9'),
        (_Q.DOMINANT_FLAT_FIVE_SHARP_NINTH, _K.EXTENDED, 'M3 d5 m7 A9'),
        (_Q.DOMINANT_SHARP_FIVE_FLAT_NINTH, _K.EXTENDED, 'M3 A5 m7 m9'),
        (_Q.DOMINANT_SHARP_FIVE_SHARP_NINTH, _K.EXTENDED, 'M3 A5 m7 A9'),
        (_Q.DOMINANT_ELEVENTH, _K.EXTENDED, 'M3 P5 m7 M9 P11'),
        (_Q.MINOR_ELEVENTH, _K.EXTENDED, 'm3 P5 m7 M9 P11'),
        (_Q.DOMINANT_SHARP_ELEVENTH, _K.EXTENDED, 'M3 P5 m7 A11'),
        (_Q.DOMINANT_NINTH_SHARP_ELEVENTH, _K.EXTENDED, 'M3 P5 m7 M9 A11'),
        (_Q.MAJOR_SEVENTH_SHARP_ELEVENTH, _K.EXTENDED, 'M3 P5 M7 A11'),
        (_Q.MAJOR_NINTH_SHARP_ELEVENTH, _K.EXTENDED, 'M3 P5 M7 M9 A11'),
        (_Q.DOMINANT_THIRTEENTH, _K.EXTENDED, 'M3 P5 m7 M9 M13'),
        (_Q.MAJOR_THIRTEENTH, _K.EXTENDED, 'M3 P5 M7 M9 M13'),
        (_Q.MINOR_THIRTEENTH, _K.EXTENDED, 'm3 P5 m7 M9 M13'),
        (_Q.DOMINANT_THIRTEENTH_FLAT_NINTH, _K.EXTENDED, 'M3 P5 m7 m9 M13'),
        (_Q.DOMINANT_THIRTEENTH_SHARP_ELEVENTH, _K.EXTENDED, 'M3 P5 m7 M9 A11 M13'),
        (_Q.DOMINANT_FLAT_THIRTEENTH, _K.EXTENDED, 'M3 P5 m7 m13'),
        # 1 3 ♭7 ♭9 ♯9 ♯11(=♭5) ♭13(=♯5)
        (_Q.ALTERED, _K.EXTENDED, 'M3 m7 m9 A9 A11 m13'),
        (_Q.ITALIAN_SIXTH, _K.AUGMENTED_SIXTH, 'M3 A6'),
        (_Q.FRENCH_SIXTH, _K.AUGMENTED_SIXTH, 'M3 A4 A6'),
        (_Q.GERMAN_SIXTH, _K.AUGMENTED_SIXTH, 'M3 P5 A6'),
        (_Q.DOUBLY_AUGMENTED_FOURTH, _K.AUGMENTED_SIXTH, 'M3 AA4 A6'),
    ]
}

_TRIAD_FIGURES = ('5/3', '6', '6/4')
_SEVENTH_FIGURES = ('7', '6/5', '4/3', '4/2')


@dataclass(frozen=True, slots=True)
class Chord:
    """A spelled chord: ``Chord(PitchName.parse('E'), ChordQuality.MINOR, 1)`` is E minor/G."""

    root: PitchName
    quality: ChordQuality
    inversion: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.inversion < self.quality.size:
            raise ValueError(
                f'a {self.quality.value} chord has no inversion {self.inversion}',
            )
        self.names()  # reject roots whose chord tones cannot be spelled

    def names(self) -> tuple[PitchName, ...]:
        """Chord tones in chord-tone order from the root (root, third, fifth, …).

        The order does not depend on the inversion; see :attr:`bass`.
        """
        return (self.root, *(self.root.transpose(i) for i in self.quality.intervals))

    def names_from_bass(self) -> tuple[PitchName, ...]:
        """Chord tones in chord-tone order, rotated to start from the bass."""
        names = self.names()
        return names[self.inversion :] + names[: self.inversion]

    @property
    def bass(self) -> PitchName:
        return self.names()[self.inversion]

    def pitches(self, bass_octave: int = 3) -> tuple[Pitch, ...]:
        """The chord in close position with the bass in ``bass_octave``.

        Each following chord tone (in chord-tone order from the bass) is
        placed as low as possible above the previous one, so C major in
        first inversion with ``bass_octave=4`` is E4 G4 C5 and C9 is C E G
        B♭ D.
        """
        names = self.names_from_bass()
        result = [names[0].at(bass_octave)]
        for name in names[1:]:
            previous = result[-1]
            octave = previous.octave - 1
            while True:
                candidate = name.at(octave)
                if (
                    candidate.midi > previous.midi
                    and candidate.diatonic_index >= previous.diatonic_index
                ):
                    break
                octave += 1
            result.append(candidate)
        return tuple(result)

    @property
    def figures(self) -> str | None:
        """Figured-bass inversion symbol (``'5/3'``, ``'6'``, ``'6/4'``, ``'7'``,
        ``'6/5'``, ``'4/3'``, ``'4/2'``), or None for chords outside
        common-practice triads and seventh chords."""
        if not self.quality.is_tertian:
            return None
        if self.quality.kind is ChordKind.TRIAD:
            return _TRIAD_FIGURES[self.inversion]
        return _SEVENTH_FIGURES[self.inversion]

    def transpose(self, interval: Interval, *, down: bool = False) -> Chord:
        return Chord(self.root.transpose(interval, down=down), self.quality, self.inversion)

    def with_inversion(self, inversion: int) -> Chord:
        return Chord(self.root, self.quality, inversion)

    def __contains__(self, name: object) -> bool:
        return name in self.names()

    def is_enharmonic(self, other: Chord) -> bool:
        """True when both chords contain the same pitch classes over the same bass pitch class."""
        return self.bass.pitch_class == other.bass.pitch_class and {
            n.pitch_class for n in self.names()
        } == {n.pitch_class for n in other.names()}

    @classmethod
    def identify(cls, pitches: Iterable[Pitch] | Iterable[PitchName]) -> list[Chord]:
        """All spelled chords whose tones are exactly the given ones.

        Given :class:`Pitch` objects the lowest one is the bass; given
        :class:`PitchName` objects the first one is. Doublings are ignored.
        Interpretations are ordered with root position first, then by the
        order of :class:`ChordQuality` (triads, sevenths, added-tone and
        extended chords): C–E–G–A gives C6 before Am7/C.

        Spelling matters: C–E–G♯ is C augmented, C–E–A♭ is A♭ augmented in
        first inversion, and C–E♭–G♭–B𝄫 is only C diminished seventh.
        """
        items = list(pitches)
        if not items:
            return []
        names: list[PitchName] = []
        if isinstance(items[0], Pitch):
            spelled = [p for p in items if isinstance(p, Pitch)]
            bass = min(spelled).name
            names = [p.name for p in spelled]
        else:
            names = [n for n in items if isinstance(n, PitchName)]
            bass = names[0]
        wanted = frozenset(names)
        found: list[Chord] = []
        for root in sorted(wanted, key=lambda n: (n.letter, n.alter)):
            for quality in ChordQuality:
                if quality.size != len(wanted):
                    continue
                try:
                    tones = Chord(root, quality).names()
                except ValueError:
                    continue
                if frozenset(tones) == wanted:
                    found.append(Chord(root, quality, tones.index(bass)))
        order = list(ChordQuality)
        found.sort(key=lambda c: (c.inversion != 0, order.index(c.quality)))
        return found

    def __str__(self) -> str:
        text = f'{self.root}:{self.quality.value}'
        return f'{text}/{self.bass}' if self.inversion else text
