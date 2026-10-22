# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The counterpoint realizer: its solutions pass the checker in every species and mode."""

from __future__ import annotations

import random
import time
from fractions import Fraction

import pytest

from etude.checkers.cantus import FUX, fux_mode, generate, modal_keys
from etude.checkers.counterpoint import (
    MODES,
    Context,
    Species,
    check,
    errors,
    species_rhythm,
)
from etude.checkers.species import (
    CounterpointError,
    florid_rhythm,
    fourth_rhythm,
    pitch_range,
    realize,
    solve,
)
from etude.core import NoteValue, Pitch, ScaleType

P = Pitch.parse


@pytest.mark.parametrize('species', list(Species))
@pytest.mark.parametrize('above', [True, False])
def test_solutions_pass_the_checker(species: Species, above: bool) -> None:
    solved = 0
    for mode_type in MODES:
        for mode in modal_keys(mode_type, 2)[::2]:
            for seed in range(3):
                rng = random.Random(seed)
                final = mode.tonic.at(3 if above else 4)
                cantus = generate(mode, final, rng)
                try:
                    rhythm, line = solve(cantus, Context(mode, species, above), rng)
                except CounterpointError:
                    continue  # the exercise then draws another cantus firmus
                context = Context(mode, species, above, rhythm)
                violations = check(cantus, line, context)
                assert not errors(violations), [v.message for v in errors(violations)]
                low, high = pitch_range(cantus, above)
                assert all(low.midi <= p.midi <= high.midi for p in line)
                solved += 1
    assert solved >= 0.9 * len(MODES) * 2 * 3


@pytest.mark.parametrize('mode_type', MODES)
def test_fux_cantus_firmi_are_realised(mode_type: ScaleType) -> None:
    mode = fux_mode(mode_type)
    cantus = FUX[mode_type]
    for species in (Species.FIRST, Species.SECOND, Species.THIRD):
        line = realize(cantus, Context(mode, species, True), random.Random(1))
        assert not errors(check(cantus, line, Context(mode, species, True)))


def test_seeds_vary_the_answer_and_repeat_it() -> None:
    mode = fux_mode(MODES[0])
    cantus = FUX[MODES[0]]
    context = Context(mode, Species.FIRST)
    answers = {realize(cantus, context, random.Random(seed)) for seed in range(8)}
    assert len(answers) > 3
    assert realize(cantus, context, random.Random(5)) == realize(cantus, context, random.Random(5))


def test_realize_is_fast() -> None:
    mode = fux_mode(MODES[0])
    started = time.perf_counter()
    for seed in range(10):
        rng = random.Random(100 + seed)
        cantus = generate(mode, P('D3'), rng)
        solve(cantus, Context(mode, Species.THIRD, True), rng)
    assert time.perf_counter() - started < 5.0


def test_florid_rhythm() -> None:
    for seed in range(40):
        bars = 8 + seed % 7
        rhythm = florid_rhythm(bars, random.Random(seed))
        assert rhythm.length == bars
        assert rhythm.rest is not None
        assert rhythm.rest.value is NoteValue.HALF
        onsets = rhythm.onsets
        tied = rhythm.tied()
        assert tied[0], 'the first note is tied over'
        assert rhythm.notes[-1].value is NoteValue.WHOLE
        assert onsets[-1] == bars - 1
        # The cadence: a tied note into the penultimate bar, then a half note.
        assert tied[-3]
        assert not tied[-2]
        assert onsets[-2] == bars - Fraction(3, 2)
        for index, duration in enumerate(rhythm.notes):
            if duration.value is NoteValue.EIGHTH:
                position = onsets[index] % 1
                assert position in (Fraction(1, 4), Fraction(3, 8)), 'eighths on beat 2'
            if tied[index]:
                assert onsets[index] % 1 == Fraction(1, 2), 'ties from the third beat'
    with pytest.raises(ValueError, match='three bars'):
        florid_rhythm(2, random.Random(0))


def test_fourth_rhythm() -> None:
    assert fourth_rhythm(6) == species_rhythm(Species.FOURTH, 6)
    broken = fourth_rhythm(6, frozenset({2}))
    assert broken.length == 6
    assert broken.tied() == (True, False, False, True, True, False, False)
    with pytest.raises(ValueError, match='broken'):
        fourth_rhythm(6, frozenset({4}))


def test_fifth_species_needs_a_rhythm() -> None:
    mode = fux_mode(MODES[0])
    with pytest.raises(ValueError, match='needs a rhythm'):
        realize(FUX[MODES[0]], Context(mode, Species.FIFTH), random.Random(0))
