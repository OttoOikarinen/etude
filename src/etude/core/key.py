# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Key signatures.

A key signature is a position on the line of fifths: ``fifths=4`` is four
sharps (E major / C♯ minor), ``fifths=-3`` is three flats (E♭ major /
C minor). Keys, modes and scales build on this in :mod:`etude.core.scale`.
"""

from __future__ import annotations

from dataclasses import dataclass

from .pitch import Letter, PitchName

SHARP_ORDER = (Letter.F, Letter.C, Letter.G, Letter.D, Letter.A, Letter.E, Letter.B)
FLAT_ORDER = tuple(reversed(SHARP_ORDER))
MAX_FIFTHS = 7


@dataclass(frozen=True, slots=True)
class KeySignature:
    fifths: int

    def __post_init__(self) -> None:
        if not -MAX_FIFTHS <= self.fifths <= MAX_FIFTHS:
            raise ValueError(f'a key signature has at most {MAX_FIFTHS} sharps or flats')

    @classmethod
    def for_major(cls, tonic: PitchName) -> KeySignature:
        """Key signature of the major key on ``tonic``; raises for theoretical keys like G♯ major."""
        return cls(tonic.line_of_fifths)

    @classmethod
    def for_minor(cls, tonic: PitchName) -> KeySignature:
        """Key signature of the natural minor key on ``tonic``."""
        return cls(tonic.line_of_fifths - 3)

    @property
    def count(self) -> int:
        """Number of accidentals in the signature."""
        return abs(self.fifths)

    @property
    def accidentals(self) -> tuple[PitchName, ...]:
        """Accidentals in written order: F♯ C♯ G♯ … or B♭ E♭ A♭ …"""
        if self.fifths >= 0:
            return tuple(PitchName(letter, 1) for letter in SHARP_ORDER[: self.fifths])
        return tuple(PitchName(letter, -1) for letter in FLAT_ORDER[: -self.fifths])

    @property
    def major_tonic(self) -> PitchName:
        return PitchName.from_line_of_fifths(self.fifths)

    @property
    def minor_tonic(self) -> PitchName:
        return PitchName.from_line_of_fifths(self.fifths + 3)

    def alter_for(self, letter: Letter) -> int:
        """Alteration the signature applies to ``letter`` (1, -1 or 0)."""
        if self.fifths > 0 and letter in SHARP_ORDER[: self.fifths]:
            return 1
        if self.fifths < 0 and letter in FLAT_ORDER[: -self.fifths]:
            return -1
        return 0
