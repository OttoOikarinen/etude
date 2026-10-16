# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Neo-Riemannian transformations of major and minor triads.

Each basic transformation keeps two common tones and moves the third
voice by step (Cohn, "Introduction to Neo-Riemannian Theory", 1998):

* **P** (parallel): C major ↔ C minor.
* **L** (leading-tone exchange): C major ↔ E minor.
* **R** (relative): C major ↔ A minor.

The compounds **N** (*Nebenverwandt*, RLP: C major ↔ F minor), **S**
(slide, LPR: C major ↔ C♯ minor) and **H** (hexatonic pole, LPL: C major
↔ G♯ minor) are also understood.

Transformation strings are read **left to right**, the order in which
the operations are applied: ``'PL'`` applied to C major is P (C minor),
then L (A♭ major). Results keep exact spellings (L of C minor is A♭
major, not G♯ major); spelling drift in long chains is respelled to the
simplest root if a spelling runs past triple sharps or flats.
"""

from __future__ import annotations

from collections import deque

from .chord import Chord, ChordQuality
from .interval import Interval
from .pitch import PitchName

_BASIC = 'PLR'
_COMPOUNDS = {'N': 'RLP', 'S': 'LPR', 'H': 'LPL'}
# (root motion for a major triad, for a minor triad); the minor motion is the inverse.
_ROOT_MOTION = {
    'P': (None, None),
    'L': ((Interval.parse('M3'), False), (Interval.parse('M3'), True)),
    'R': ((Interval.parse('m3'), True), (Interval.parse('m3'), False)),
}


def _check(chord: Chord) -> None:
    if chord.quality not in (ChordQuality.MAJOR, ChordQuality.MINOR):
        raise ValueError('neo-Riemannian transformations apply to major and minor triads')


def _move(root: PitchName, interval: Interval, down: bool) -> PitchName:
    try:
        return root.transpose(interval, down=down)
    except ValueError:
        return root.simplest().transpose(interval, down=down)


def transform(chord: Chord, operation: str) -> Chord:
    """Apply a single P, L or R to a major or minor triad (returned in root position)."""
    _check(chord)
    if operation not in _BASIC:
        raise ValueError(f'unknown transformation: {operation!r}')
    major = chord.quality is ChordQuality.MAJOR
    other = ChordQuality.MINOR if major else ChordQuality.MAJOR
    motion = _ROOT_MOTION[operation][0 if major else 1]
    root = chord.root if motion is None else _move(chord.root, *motion)
    try:
        return Chord(root, other)
    except ValueError:
        return Chord(root.simplest(), other)


def expand(transformations: str) -> str:
    """Expand compounds into P, L and R: ``'NS'`` → ``'RLPLPR'``. Spaces and dots are ignored."""
    result = []
    for symbol in transformations.upper():
        if symbol in ' .·':
            continue
        if symbol in _BASIC:
            result.append(symbol)
        elif symbol in _COMPOUNDS:
            result.append(_COMPOUNDS[symbol])
        else:
            raise ValueError(f'unknown transformation {symbol!r} in {transformations!r}')
    return ''.join(result)


def apply(chord: Chord, transformations: str) -> Chord:
    """Apply a sequence such as ``'PLR'`` from left to right."""
    _check(chord)
    result = Chord(chord.root, chord.quality)
    for symbol in expand(transformations):
        result = transform(result, symbol)
    return result


def _key(chord: Chord) -> tuple[int, ChordQuality]:
    return (chord.root.pitch_class, chord.quality)


def shortest_path(start: Chord, end: Chord) -> str:
    """The shortest string of P, L and R taking ``start`` to ``end`` (compared by pitch class).

    Among paths of equal length the first in alphabetical order (L < P < R)
    is returned, so the answer is deterministic. ``''`` when the triads
    are the same.
    """
    _check(start)
    _check(end)
    target = _key(end)
    seen = {_key(start)}
    queue: deque[tuple[Chord, str]] = deque([(Chord(start.root, start.quality), '')])
    while queue:
        chord, path = queue.popleft()
        if _key(chord) == target:
            return path
        for symbol in sorted(_BASIC):
            following = transform(chord, symbol)
            if _key(following) not in seen:
                seen.add(_key(following))
                queue.append((following, path + symbol))
    raise AssertionError('the PLR graph is connected')  # pragma: no cover
