# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Pitch-class sets.

Pitch classes are integers 0–11 with C = 0 (written ``T`` and ``E`` for
10 and 11 in prime forms). Operations follow Straus, *Introduction to
Post-Tonal Theory*:

* ``Tn`` transposes by ``n``; ``TnI`` inverts around 0 and then
  transposes, mapping ``x`` to ``n - x``.
* **Normal form** is the rotation of the sorted set with the smallest
  span. Ties are broken with **Rahn's algorithm** (as in Straus and most
  current textbooks): compare the interval from the first note to the
  second-to-last, then to the third-to-last, and so on, preferring the
  smaller ("packed to the left"). Remaining ties (symmetrical sets) go to
  the rotation that starts on the smallest pitch class.
* **Prime form** is the normal form of the set or of its inversion,
  transposed to start on 0, whichever is more packed by the same rule.
  Forte's original algorithm (*The Structure of Atonal Music*, 1973)
  compares from the left instead (first to second, first to third…); the
  two disagree for 5-20, 6-Z29, 6-31, 7-Z18, 7-20 and 8-26.
  :meth:`PitchClassSet.prime_form` takes ``forte=True`` for Forte's.
* **Forte names** label the 208 set classes of cardinality 3–9 as in
  Forte's table; a ``Z`` marks the Z-related classes, which share an
  interval vector without being Tn/TnI-equivalent. Complementary classes
  share the ordinal number (4-Z15 and 8-Z15).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from functools import cache

_DIGITS = '0123456789TE'


def _parse_pcs(text: str) -> tuple[int, ...]:
    return tuple(_DIGITS.index(c) for c in text.upper().replace('A', 'T').replace('B', 'E'))


# Forte numbers and Rahn prime forms of cardinalities 3–6. Classes of
# cardinality 7–9 are named after their complements (see _forte_table).
_FORTE_3_TO_6 = """
3-1 012 3-2 013 3-3 014 3-4 015 3-5 016 3-6 024 3-7 025 3-8 026 3-9 027 3-10 036 3-11 037
3-12 048
4-1 0123 4-2 0124 4-3 0134 4-4 0125 4-5 0126 4-6 0127 4-7 0145 4-8 0156 4-9 0167 4-10 0235
4-11 0135 4-12 0236 4-13 0136 4-14 0237 4-Z15 0146 4-16 0157 4-17 0347 4-18 0147 4-19 0148
4-20 0158 4-21 0246 4-22 0247 4-23 0257 4-24 0248 4-25 0268 4-26 0358 4-27 0258 4-28 0369
4-Z29 0137
5-1 01234 5-2 01235 5-3 01245 5-4 01236 5-5 01237 5-6 01256 5-7 01267 5-8 02346 5-9 01246
5-10 01346 5-11 02347 5-Z12 01356 5-13 01248 5-14 01257 5-15 01268 5-16 01347 5-Z17 01348
5-Z18 01457 5-19 01367 5-20 01568 5-21 01458 5-22 01478 5-23 02357 5-24 01357 5-25 02358
5-26 02458 5-27 01358 5-28 02368 5-29 01368 5-30 01468 5-31 01369 5-32 01469 5-33 02468
5-34 02469 5-35 02479 5-Z36 01247 5-Z37 03458 5-Z38 01258
6-1 012345 6-2 012346 6-Z3 012356 6-Z4 012456 6-5 012367 6-Z6 012567 6-7 012678 6-8 023457
6-9 012357 6-Z10 013457 6-Z11 012457 6-Z12 012467 6-Z13 013467 6-14 013458 6-15 012458
6-16 014568 6-Z17 012478 6-18 012578 6-Z19 013478 6-20 014589 6-21 023468 6-22 012468
6-Z23 023568 6-Z24 013468 6-Z25 013568 6-Z26 013578 6-27 013469 6-Z28 013569 6-Z29 023679
6-30 013679 6-31 014579 6-32 024579 6-33 023579 6-34 013579 6-35 02468T 6-Z36 012347
6-Z37 012348 6-Z38 012378 6-Z39 023458 6-Z40 012358 6-Z41 012368 6-Z42 012369 6-Z43 012568
6-Z44 012569 6-Z45 023469 6-Z46 012469 6-Z47 012479 6-Z48 012579 6-Z49 013479 6-Z50 014679
"""


def _packing_key(pcs: tuple[int, ...], *, forte: bool) -> tuple[int, ...]:
    """Sort key for candidate orderings of the same set; the smallest wins."""
    intervals = tuple((pc - pcs[0]) % 12 for pc in pcs)
    if forte:
        return (intervals[-1], *intervals[1:])
    return tuple(reversed(intervals))


def _rotations(pcs: Iterable[int]) -> list[tuple[int, ...]]:
    ordered = sorted(set(pcs))
    return [tuple(ordered[i:] + ordered[:i]) for i in range(len(ordered))]


@dataclass(frozen=True, slots=True)
class PitchClassSet:
    """An unordered set of pitch classes: ``PitchClassSet.of(0, 4, 7)``."""

    pcs: frozenset[int]

    def __post_init__(self) -> None:
        if any(not isinstance(pc, int) or not 0 <= pc < 12 for pc in self.pcs):
            raise ValueError(f'pitch classes must be integers 0–11: {sorted(self.pcs)}')

    @classmethod
    def of(cls, *pcs: int) -> PitchClassSet:
        """Build a set from pitch classes; values are reduced modulo 12."""
        return cls(frozenset(pc % 12 for pc in pcs))

    @classmethod
    def parse(cls, text: str) -> PitchClassSet:
        """Parse ``'014'``, ``'[0,1,4]'``, ``'(0 1 4)'`` or ``'{0, 4, 7, T}'`` (T/A = 10,
        E/B = 11)."""
        cleaned = ''.join(c for c in text if c not in '[](){}<>, ')
        try:
            return cls(frozenset(_parse_pcs(cleaned)))
        except ValueError:
            raise ValueError(f'not a pitch-class set: {text!r}') from None

    @property
    def cardinality(self) -> int:
        return len(self.pcs)

    def __len__(self) -> int:
        return len(self.pcs)

    def __iter__(self) -> Iterator[int]:
        return iter(sorted(self.pcs))

    def __contains__(self, pc: object) -> bool:
        return pc in self.pcs

    def transpose(self, n: int) -> PitchClassSet:
        """``Tn``: add ``n`` to every pitch class."""
        return PitchClassSet(frozenset((pc + n) % 12 for pc in self.pcs))

    def invert(self, n: int = 0) -> PitchClassSet:
        """``TnI``: invert around 0, then transpose by ``n`` (``x`` → ``n - x``)."""
        return PitchClassSet(frozenset((n - pc) % 12 for pc in self.pcs))

    def complement(self) -> PitchClassSet:
        """The pitch classes not in the set (the literal complement)."""
        return PitchClassSet(frozenset(range(12)) - self.pcs)

    def normal_form(self) -> tuple[int, ...]:
        """Normal form (Rahn): ``{11, 2, 7}`` → ``(7, 11, 2)``."""
        if not self.pcs:
            return ()
        return min(_rotations(self.pcs), key=lambda r: (_packing_key(r, forte=False), r[0]))

    def prime_form(self, *, forte: bool = False) -> tuple[int, ...]:
        """Prime form starting on 0: the major and minor triads are both ``(0, 3, 7)``.

        Rahn's algorithm by default; ``forte=True`` uses Forte's (see the
        module docstring).
        """
        if not self.pcs:
            return ()
        candidates = [
            tuple((pc - r[0]) % 12 for pc in r)
            for source in (self.pcs, self.invert().pcs)
            for r in _rotations(source)
        ]
        return min(candidates, key=lambda c: (_packing_key(c, forte=forte), c))

    def interval_vector(self) -> tuple[int, int, int, int, int, int]:
        """Counts of interval classes 1–6 between all pairs: major triad → (0, 0, 1, 1, 1, 0)."""
        counts = [0] * 6
        ordered = sorted(self.pcs)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 :]:
                ic = min((b - a) % 12, (a - b) % 12)
                counts[ic - 1] += 1
        return (counts[0], counts[1], counts[2], counts[3], counts[4], counts[5])

    def set_class(self) -> PitchClassSet:
        """The set in prime form (a canonical member of its Tn/TnI class)."""
        return PitchClassSet(frozenset(self.prime_form()))

    @property
    def forte_name(self) -> str | None:
        """Forte name such as ``'3-11'`` or ``'4-Z15'``; None outside cardinalities 3–9."""
        return _forte_table()[0].get(self.prime_form())

    @classmethod
    def from_forte_name(cls, name: str) -> PitchClassSet:
        """The prime form of a Forte class; ``'4-15'`` and ``'4-Z15'`` both work."""
        names = _forte_table()[1]
        key = name.strip().upper().replace('Z', '')
        if key not in names:
            raise ValueError(f'not a Forte name: {name!r}')
        return cls(frozenset(names[key]))

    @property
    def is_z_related(self) -> bool:
        return self.z_correspondent() is not None

    def z_correspondent(self) -> PitchClassSet | None:
        """The prime form of the Z-related set class, or None if there is none."""
        vector = self.interval_vector()
        own = self.prime_form()
        for prime in _forte_table()[0]:
            if len(prime) == len(own) and prime != own:
                other = PitchClassSet(frozenset(prime))
                if other.interval_vector() == vector:
                    return other
        return None

    def is_tn_equivalent(self, other: PitchClassSet) -> bool:
        return any(self.transpose(n) == other for n in range(12))

    def is_tni_equivalent(self, other: PitchClassSet) -> bool:
        """True when the sets belong to the same Tn/TnI set class."""
        return len(self) == len(other) and self.prime_form() == other.prime_form()

    def __str__(self) -> str:
        """Normal form in brackets with T and E: ``'[7,E,2]'``."""
        return '[' + ','.join(_DIGITS[pc] for pc in self.normal_form()) + ']'


def format_prime_form(prime: tuple[int, ...]) -> str:
    """Write a prime form the usual way: ``(0, 1, 4, 10)`` → ``'(014T)'``."""
    return '(' + ''.join(_DIGITS[pc] for pc in prime) + ')'


@cache
def _forte_table() -> tuple[dict[tuple[int, ...], str], dict[str, tuple[int, ...]]]:
    by_prime: dict[tuple[int, ...], str] = {}
    tokens = _FORTE_3_TO_6.split()
    for name, digits in zip(tokens[::2], tokens[1::2], strict=True):
        prime = _parse_pcs(digits)
        by_prime[prime] = name
        cardinality, number = name.split('-')
        if cardinality != '6':
            complement = PitchClassSet(frozenset(prime)).complement().prime_form()
            by_prime[complement] = f'{12 - int(cardinality)}-{number}'
    by_name = {name.replace('Z', ''): prime for prime, name in by_prime.items()}
    return by_prime, by_name


def all_set_classes() -> list[PitchClassSet]:
    """One prime form for each of the 224 Tn/TnI set classes, ordered by cardinality."""
    primes = {
        PitchClassSet(frozenset(i for i in range(12) if mask >> i & 1)).prime_form()
        for mask in range(4096)
    }
    return [PitchClassSet(frozenset(p)) for p in sorted(primes, key=lambda p: (len(p), p))]
