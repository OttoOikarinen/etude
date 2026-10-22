# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Correct species counterpoint for a cantus firmus: the model answers.

Exercises need a model solution to show after an answer and correct passages
to break on purpose (spot the error). Use :func:`realize`::

    import random
    from etude.checkers.counterpoint import Context, Species
    from etude.checkers.species import CounterpointError, realize

    try:
        line = realize(cantus, Context(mode, Species.THIRD, above=True), random.Random(seed))
    except CounterpointError:
        ...  # no correct counterpoint in the range

The search is depth first, note by note, with the incremental checker of
:mod:`etude.checkers.counterpoint` (each note is checked once, against the
notes before it), trying stepwise motion first and the other notes in an
order shuffled with ``rng``, so different seeds give different correct
answers. A first pass also avoids every warning; when its searches (restarted
in a new order when they run out of budget) fail, a second pass avoids
only errors. Results are cached, so generating
the same question again is free.

:func:`florid_rhythm` writes a fifth-species rhythm in the manner of Fux's
figures 82–88: a half rest and a tied half note, bars of half notes, quarters
and a pair of eighths on the second beat, ties from the third beat into the
next bar, and the cadence suspension.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import replace
from functools import lru_cache

from ..core import Duration, Interval, NoteValue, Pitch, PitchName, Scale
from .counterpoint import (
    Context,
    Rhythm,
    Rule,
    Severity,
    Species,
    Violation,
    cadence_ficta,
    is_consonant,
    mode_ficta,
    species_rhythm,
    stepper,
)

NODE_BUDGET = 1500
"""Notes tried per search before it gives up and starts again in another order."""
RESTARTS = 4
"""Searches per pass (a randomised restart escapes a dead end faster than backtracking)."""

_RANGE = Interval.parse('P12')
_STEP = Interval.parse('M2')


class CounterpointError(ValueError):
    """No correct counterpoint was found for the request."""


# Fifth-species rhythm -------------------------------------------------------------------

_W = Duration(NoteValue.WHOLE)
_H = Duration(NoteValue.HALF)
_Q = Duration(NoteValue.QUARTER)
_E = Duration(NoteValue.EIGHTH)
_DOTTED_HALF = Duration(NoteValue.HALF, 1)

_FIRST_HALVES = ((_H,), (_Q, _Q), (_Q, _E, _E))
"""How a bar's first half is divided when no tie comes into it."""
_TIED_HALVES = ((), (_Q,), (_E, _E))
"""What follows a tied quarter in the first half (``()``: the tie lasts a half)."""
_SECOND_HALVES = ((_H,), (_Q, _Q))
_WEIGHTS_FIRST = (3, 3, 1)
_WEIGHTS_TIED = (3, 3, 1)
_WEIGHTS_SECOND = (2, 3)


def florid_rhythm(bars: int, rng: random.Random) -> Rhythm:
    """A fifth-species rhythm against ``bars`` cantus notes.

    The first bar is a half rest and a half note tied over; the penultimate bar
    is the cadence suspension (the tied half and the leading tone in a half
    note) and the last a whole note. In between each bar is a tied note or a
    half or two quarters (the second of them may be two eighths), then a half
    (often tied over), or two quarters.
    """
    if bars < 3:
        raise ValueError('a fifth-species exercise needs at least three bars')
    lengths: list[Duration] = []
    tied = True  # the half note of the first bar is tied over
    lengths.append(_H)
    for bar in range(1, bars - 1):
        last = bar == bars - 2
        if tied:
            if last:
                first: tuple[Duration, ...] = ()
                tie_value = _H
            elif rng.random() < 0.55:
                first = ()
                tie_value = _H
            else:
                first = rng.choices(_TIED_HALVES[1:], _WEIGHTS_TIED[1:])[0]
                tie_value = _Q
            lengths[-1] = _W if tie_value is _H else _DOTTED_HALF
            lengths.extend(first)
        else:
            lengths.extend(rng.choices(_FIRST_HALVES, _WEIGHTS_FIRST)[0])
        if last:
            lengths.append(_H)  # the leading tone
            tied = False
        elif bar == bars - 3 or rng.random() < 0.45:
            lengths.append(_H)  # tied over: a suspension or a consonant syncopation
            tied = True
        else:
            lengths.extend(rng.choices(_SECOND_HALVES, _WEIGHTS_SECOND)[0])
            tied = False
    lengths.append(_W)
    return Rhythm(tuple(lengths), rest=_H)


def fourth_rhythm(bars: int, broken: frozenset[int] = frozenset()) -> Rhythm:
    """Fourth species with the ligature broken into the bars in ``broken``: there the
    note before the barline is a half note and the downbeat is struck anew, as Fux does
    when the syncopation would lead into a fault (fig. 73). Bar 0 and the last two bars
    cannot be broken (the opening and the cadence suspension)."""
    if any(not 1 <= bar <= bars - 3 for bar in broken):
        raise ValueError('only the bars between the first and the cadence can be broken')
    notes: list[Duration] = []
    for bar in range(bars - 1):
        if bar in broken:
            notes.append(_H)
        tied = bar + 1 <= bars - 2 and bar + 1 not in broken
        notes.append(_W if tied else _H)
    notes.append(_W)
    return Rhythm(tuple(notes), rest=_H)


FOURTH_ATTEMPTS = 8
"""Rhythms with a broken ligature :func:`solve` tries in fourth species."""
FIFTH_ATTEMPTS = 6
"""Florid rhythms :func:`solve` tries in fifth species."""


def solve(
    cantus: Sequence[Pitch],
    context: Context,
    rng: random.Random | None = None,
    *,
    low: Pitch | None = None,
    high: Pitch | None = None,
) -> tuple[Rhythm, tuple[Pitch, ...]]:
    """A rhythm and a correct counterpoint in it: the standard rhythm in species 1–3;
    in the fourth the syncopation throughout, or else with a ligature broken in one or
    two bars; in the fifth a :func:`florid_rhythm`, drawn again until one works.
    ``context.rhythm`` is ignored. Raises :class:`CounterpointError`."""
    rng = rng or random.Random(0)
    bars = len(cantus)
    rhythms: list[Rhythm]
    if context.species is Species.FOURTH:
        middle = list(range(1, bars - 2))
        rng.shuffle(middle)
        rhythms = [fourth_rhythm(bars)]
        rhythms += [fourth_rhythm(bars, frozenset({bar})) for bar in middle]
        pairs = [frozenset({a, b}) for a in middle for b in middle if a < b]
        rhythms += [fourth_rhythm(bars, pair) for pair in pairs]
        rhythms = rhythms[: FOURTH_ATTEMPTS + 1]
    elif context.species is Species.FIFTH:
        rhythms = [florid_rhythm(bars, rng) for _attempt in range(FIFTH_ATTEMPTS)]
    else:
        rhythms = [species_rhythm(context.species, bars)]
    for rhythm in rhythms:
        try:
            line = realize(cantus, replace(context, rhythm=rhythm), rng, low=low, high=high)
        except CounterpointError:
            continue
        return rhythm, line
    raise CounterpointError(f'no {context.species.name.lower()}-species counterpoint found')


# Search ---------------------------------------------------------------------------------


def pitch_range(cantus: Sequence[Pitch], above: bool) -> tuple[Pitch, Pitch]:
    """A default range for the counterpoint: a twelfth up from the cantus's lowest note
    (above), or down from its highest and a step further, for the leading tone under a
    final at the bottom (below)."""
    if above:
        low = min(cantus, key=lambda p: p.midi)
        return low, low.transpose(_RANGE)
    high = max(cantus, key=lambda p: p.midi)
    return high.transpose(_RANGE, down=True).transpose(_STEP, down=True), high


def realize(
    cantus: Sequence[Pitch],
    context: Context,
    rng: random.Random | None = None,
    *,
    low: Pitch | None = None,
    high: Pitch | None = None,
) -> tuple[Pitch, ...]:
    """A counterpoint to ``cantus`` with no error under
    :func:`~etude.checkers.counterpoint.check` in ``context`` (and if possible no
    warning), within ``low``–``high`` (default :func:`pitch_range`).

    ``rng`` varies the answer (seed 0 when omitted). The fifth species needs
    ``context.rhythm`` (see :func:`florid_rhythm`). Raises
    :class:`CounterpointError` when no counterpoint is found.
    """
    if context.rhythm is None and context.species is Species.FIFTH:
        raise ValueError('the fifth species needs a rhythm (florid_rhythm)')
    default_low, default_high = pitch_range(cantus, context.above)
    seed = (rng or random.Random(0)).randrange(2**32)
    return _realize(tuple(cantus), context, seed, low or default_low, high or default_high)


@lru_cache(maxsize=1024)
def _realize(
    cantus: tuple[Pitch, ...], context: Context, seed: int, low: Pitch, high: Pitch
) -> tuple[Pitch, ...]:
    rng = random.Random(seed)
    for strict in (True, False):
        for _restart in range(RESTARTS if not strict else 2):
            found = _Search(cantus, context, rng, low, high, strict).run()
            if found is not None:
                return found
    raise CounterpointError(f'no {context.species.name.lower()}-species counterpoint found')


def _pool(mode: Scale, low: Pitch, high: Pitch) -> list[Pitch]:
    seventh, sixth = cadence_ficta(mode)
    names: set[PitchName] = {*mode.names(), *mode_ficta(mode)}
    names |= {n for n in (seventh, sixth) if n is not None}
    return sorted(
        (
            name.at(octave)
            for name in names
            for octave in range(low.octave - 1, high.octave + 2)
            if low.midi <= name.at(octave).midi <= high.midi
        ),
        key=lambda p: (p.midi, p.diatonic_index),
    )


class _Search:
    def __init__(
        self,
        cantus: tuple[Pitch, ...],
        context: Context,
        rng: random.Random,
        low: Pitch,
        high: Pitch,
        strict: bool,
    ) -> None:
        self.cantus = cantus
        self.context = context
        self.rng = rng
        self.strict = strict
        self.checker = stepper(cantus, context)
        self.notes = self.checker.notes
        self.pool = _pool(context.mode, low, high)
        mode_names = set(context.mode.names())
        self.ficta = {p for p in self.pool if p.name not in mode_names}
        """Accidentals: the cadence's raised notes are kept for the last two bars, the
        others cost a little, so model answers use them sparingly."""
        self.cadence = {p for p in self.ficta if p.name in cadence_ficta(context.mode)}
        self.cadence_bar = len(cantus) - 2
        self.budget = NODE_BUDGET
        final = cantus[-1]
        self.finals = [
            p
            for p in self.pool
            if p.name == final.name
            and (p.midi >= final.midi if context.above else p.midi <= final.midi)
        ]
        self.rng.shuffle(self.finals)
        self.targets = sorted(
            {p.diatonic_index for p in self.pool if any(_leads(p, f) for f in self.finals)}
        )
        """Where the penultimate note may be (diatonic index)."""

    def bad(self, found: Sequence[Violation]) -> bool:
        """Errors, and in the strict pass warnings too (but a repeated climax, which only
        the end shows, and which Fux allows himself)."""
        if self.strict:
            return any(v.rule is not Rule.CLIMAX for v in found)
        return any(v.severity is Severity.ERROR for v in found)

    def candidates(self, i: int) -> list[Pitch]:
        n = len(self.notes)
        if i == n - 1:
            return list(self.finals)
        under = self.cantus[self.notes[i].bar]
        options = self.pool
        note = self.notes[i]
        consonant_only = (
            note.strong
            or note.tied
            or self.context.species in (Species.FIRST, Species.FOURTH)
            or i == 0
        )
        if note.bar < self.cadence_bar:
            options = [p for p in options if p not in self.cadence]
        if consonant_only:
            options = [p for p in options if is_consonant(p, under)]
        if i == n - 2:
            options = [p for p in options if any(_leads(p, f) for f in self.finals)]
        if i == 0:
            return self._shuffled(options, None, i)
        return self._shuffled(options, self.checker.line[-1], i)

    def _shuffled(self, options: list[Pitch], previous: Pitch | None, i: int) -> list[Pitch]:
        rng = self.rng
        # Near the end, head for the notes the cadence needs.
        left = len(self.notes) - 2 - i
        targets = self.targets if 0 < left <= 6 else []

        def cost(pitch: Pitch) -> float:
            noise = rng.random() * 2.0 + (1.5 if pitch in self.ficta else 0.0)
            if targets:
                distance = min(abs(pitch.diatonic_index - t) for t in targets)
                noise += max(0, distance - left) * 1.5
            if previous is None:
                return noise
            steps = abs(pitch.diatonic_index - previous.diatonic_index)
            if steps == 0:
                return 9.0 + noise
            return {1: 0.0, 2: 1.2, 3: 2.2, 4: 2.8}.get(steps, 4.0) + noise

        return sorted(options, key=cost)

    def run(self) -> tuple[Pitch, ...] | None:
        n = len(self.notes)
        checker = self.checker
        stack: list[list[Pitch]] = [self.candidates(0)]
        marks: list[int] = []
        """Violations recorded before each note on the line (to forget its own)."""
        while stack:
            if self.budget <= 0:
                return None
            options = stack[-1]
            if not options:
                stack.pop()
                if marks:
                    checker.pop()
                    del checker.found[marks.pop() :]
                continue
            pitch = options.pop(0)
            self.budget -= 1
            mark = len(checker.found)
            new = checker.step(pitch)
            done = len(checker.line) == n
            if not self.bad(new) and done:
                new = checker.finish()
                if not self.bad(new):
                    return tuple(checker.line)
            if self.bad(new) or done:
                checker.pop()
                del checker.found[mark:]
                continue
            marks.append(mark)
            stack.append(self.candidates(len(checker.line)))
        return None


def _leads(pitch: Pitch, final: Pitch) -> bool:
    """A step to the final (the candidate penultimate notes; the checker decides)."""
    return (
        abs(final.diatonic_index - pitch.diatonic_index) == 1
        and 1 <= abs(final.midi - pitch.midi) <= 2
    )
