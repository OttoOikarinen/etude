# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Cantus firmi: Fux's own, transpositions, and generated ones."""

from __future__ import annotations

import itertools
import random

import pytest

from etude.checkers.cantus import (
    FUX,
    MAX_LENGTH,
    MIN_LENGTH,
    fux_cantus,
    fux_mode,
    generate,
    modal_keys,
    signature,
)
from etude.checkers.counterpoint import MODES, Rule, check_cantus, errors
from etude.core import KeySignature, Pitch, PitchName, Scale, ScaleType

P = Pitch.parse


def notes(text: str) -> tuple[Pitch, ...]:
    return tuple(P(n) for n in text.split())


@pytest.mark.parametrize('mode_type', MODES)
def test_fux_cantus_firmi_pass(mode_type: ScaleType) -> None:
    mode = fux_mode(mode_type)
    cantus = FUX[mode_type]
    assert cantus[0].name == cantus[-1].name == mode.tonic
    assert not errors(check_cantus(cantus, mode))


def test_fux_finals_and_signatures() -> None:
    finals = [str(fux_mode(m).tonic) for m in MODES]
    assert finals == ['D', 'E', 'F', 'G', 'A', 'C']
    assert all(signature(fux_mode(m)) == KeySignature(0) for m in MODES)
    g_dorian = Scale(PitchName.parse('G'), ScaleType.DORIAN)
    assert signature(g_dorian) == KeySignature(-1)
    assert signature(Scale(PitchName.parse('B'), ScaleType.PHRYGIAN)) == KeySignature(1)


def test_modal_keys() -> None:
    keys = modal_keys(ScaleType.DORIAN, 1)
    assert [str(k.tonic) for k in keys] == ['G', 'D', 'A']
    assert all(abs(signature(k).fifths) <= 1 for k in keys)
    assert len(modal_keys(ScaleType.IONIAN, 7)) == 15
    with pytest.raises(ValueError, match='six modes'):
        modal_keys(ScaleType.LOCRIAN, 2)


def test_fux_cantus_transposed() -> None:
    g_dorian = Scale(PitchName.parse('G'), ScaleType.DORIAN)
    moved = fux_cantus(g_dorian, P('G3'))
    assert moved == notes('G3 Bb3 A3 G3 C4 Bb3 D4 C4 Bb3 A3 G3')
    assert not errors(check_cantus(moved, g_dorian))
    assert fux_cantus(fux_mode(ScaleType.DORIAN)) == FUX[ScaleType.DORIAN]
    with pytest.raises(ValueError, match='not the final'):
        fux_cantus(g_dorian, P('A3'))


def test_check_cantus_finds_faults() -> None:
    dorian = fux_mode(ScaleType.DORIAN)
    faults = check_cantus(notes('D4 F4 E4 G4 F4 E4 C4 D4'), dorian)
    assert {v.rule for v in errors(faults)} >= {Rule.CADENCE}
    leap = check_cantus(notes('D4 F4 B4 A4 G4 F4 E4 D4'), dorian)
    assert Rule.MELODIC_INTERVAL in {v.rule for v in errors(leap)}  # F4 to B4
    sharp = check_cantus(notes('D4 F#4 G4 A4 G4 F4 E4 D4'), dorian)
    assert Rule.FOREIGN_NOTE in {v.rule for v in errors(sharp)}


@pytest.mark.parametrize('mode_type', MODES)
def test_generated_cantus_firmi(mode_type: ScaleType) -> None:
    seen = set()
    for mode in modal_keys(mode_type, 3):
        for seed in range(12):
            final = mode.tonic.at(3 + seed % 2)
            cantus = generate(mode, final, random.Random(seed))
            assert check_cantus(cantus, mode) == [], cantus
            assert MIN_LENGTH <= len(cantus) <= MAX_LENGTH
            assert cantus[0] == final
            assert cantus[-1] == final
            assert cantus[-2].name == mode.degree(2)
            highest = max(p.midi for p in cantus)
            assert sum(1 for p in cantus if p.midi == highest) == 1, 'a single climax'
            assert max(p.midi for p in cantus) - min(p.midi for p in cantus) <= 12
            steps = sum(
                1
                for a, b in itertools.pairwise(cantus)
                if abs(b.diatonic_index - a.diatonic_index) == 1
            )
            assert steps >= len(cantus) // 2, 'mostly stepwise'
            seen.add(cantus)
    assert len(seen) > 40, 'exercises do not repeat'


def test_generate_is_deterministic_and_checks_the_final() -> None:
    dorian = fux_mode(ScaleType.DORIAN)
    assert generate(dorian, P('D4'), random.Random(3)) == generate(
        dorian, P('D4'), random.Random(3)
    )
    assert len(generate(dorian, P('D4'), random.Random(3), length=9)) == 9
    with pytest.raises(ValueError, match='not the final'):
        generate(dorian, P('E4'), random.Random(0))
