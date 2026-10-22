# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The species counterpoint checker on textbook examples: Fux's own solutions pass,
and the classic mistakes fail with the right rule."""

from __future__ import annotations

from fractions import Fraction

import pytest

from etude.checkers.counterpoint import (
    CANTUS,
    COUNTERPOINT,
    Context,
    Rhythm,
    Rule,
    Severity,
    Species,
    Violation,
    cadence_ficta,
    check,
    check_cantus,
    errors,
    is_consonant,
    mode_ficta,
    rule_mark,
    rule_name,
    rule_reason,
    scan,
    species_name,
    species_rhythm,
    voice_name,
    voice_title,
)
from etude.core import Duration, NoteValue, Pitch, PitchName, Scale, ScaleType

from .fux_examples import EXAMPLES, Example

P = Pitch.parse
DORIAN = Scale(PitchName.parse('D'), ScaleType.DORIAN)
PHRYGIAN = Scale(PitchName.parse('E'), ScaleType.PHRYGIAN)
FUX_DORIAN = tuple(P(n) for n in ('D4', 'F4', 'E4', 'D4', 'G4', 'F4', 'A4', 'G4', 'F4', 'E4', 'D4'))
"""Fux's Dorian cantus firmus."""
FIG_5 = 'A4 A4 G4 A4 B4 C5 C5 B4 D5 C#5 D5'
"""Fux's first first-species solution, above it."""

_MODES = {
    'D': ScaleType.DORIAN,
    'E': ScaleType.PHRYGIAN,
    'F': ScaleType.LYDIAN,
    'G': ScaleType.MIXOLYDIAN,
    'A': ScaleType.AEOLIAN,
    'C': ScaleType.IONIAN,
}
_VALUES = {
    'w': Fraction(1),
    'h': Fraction(1, 2),
    'q': Fraction(1, 4),
    'e': Fraction(1, 8),
}


def duration(length: Fraction) -> Duration:
    for value in NoteValue:
        for dots in (0, 1):
            if Duration(value, dots).length == length:
                return Duration(value, dots)
    raise ValueError(length)


def parse_line(text: str) -> tuple[tuple[Pitch, ...], Rhythm]:
    """Tokens ``pitch/value`` (``~`` ties to the next) → pitches and rhythm."""
    rest: Duration | None = None
    pitches: list[Pitch] = []
    lengths: list[Fraction] = []
    held = False
    for token in text.split():
        name, value = token.split('/')
        tie = value.endswith('~')
        length = _VALUES[value.rstrip('~')]
        if name == 'r':
            rest = duration(length)
        elif held:
            lengths[-1] += length
        else:
            pitches.append(P(name))
            lengths.append(length)
        held = tie
    return tuple(pitches), Rhythm(tuple(duration(n) for n in lengths), rest)


def notes(text: str) -> tuple[Pitch, ...]:
    return tuple(P(n) for n in text.split())


def fux_case(example: Example) -> tuple[tuple[Pitch, ...], tuple[Pitch, ...], Context]:
    cantus = notes(example.cantus)
    line, rhythm = parse_line(example.counterpoint)
    mode = Scale(PitchName.parse(example.final), _MODES[example.final])
    return cantus, line, Context(mode, Species(example.species), example.above, rhythm)


def found(violations: list[Violation]) -> set[tuple[Rule, int]]:
    return {(v.rule, v.slot) for v in errors(violations)}


def first(text: str = FIG_5, **context: object) -> list[Violation]:
    return check(FUX_DORIAN, notes(text), Context(DORIAN, **context))  # type: ignore[arg-type]


# Fux's own solutions --------------------------------------------------------------------


@pytest.mark.parametrize('example', EXAMPLES, ids=lambda e: f'fig{e.figure}')
def test_fux_solutions_have_no_error(example: Example) -> None:
    cantus, line, context = fux_case(example)
    violations = check(cantus, line, context)
    assert not errors(violations), [v.message for v in errors(violations)]
    assert all(v.message for v in violations)
    assert scan(cantus, line, context) == [
        Violation(v.rule, v.severity, v.slot, v.voices, '', v.notes, v.cantus) for v in violations
    ]


def test_fux_examples_cover_every_species_and_both_positions() -> None:
    covered = {(e.species, e.above) for e in EXAMPLES}
    assert covered == {(s, a) for s in range(1, 6) for a in (True, False)}
    assert {e.final for e in EXAMPLES} == set(_MODES)


@pytest.mark.parametrize('example', EXAMPLES[:10], ids=lambda e: f'fig{e.figure}')
def test_fux_cantus_firmi_are_valid(example: Example) -> None:
    cantus, _line, context = fux_case(example)
    assert not errors(check_cantus(cantus, context.mode))


# Consonance -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('low', 'high', 'consonant'),
    [
        ('C4', 'C4', True),
        ('C4', 'E4', True),
        ('C4', 'Eb4', True),
        ('C4', 'F4', False),  # the fourth is a dissonance in two voices
        ('C4', 'F#4', False),
        ('C4', 'G4', True),
        ('C4', 'Ab4', True),
        ('C4', 'A4', True),
        ('C4', 'Bb4', False),
        ('C4', 'C5', True),
        ('C4', 'D5', False),
        ('C4', 'E5', True),  # a tenth
        ('B3', 'F4', False),  # the diminished fifth
        ('C4', 'G#4', False),  # the augmented fifth
    ],
)
def test_consonances(low: str, high: str, consonant: bool) -> None:
    assert is_consonant(P(low), P(high)) is consonant
    assert is_consonant(P(high), P(low)) is consonant


# First species ---------------------------------------------------------------------------


def test_parallel_fifths() -> None:
    # Bar 5 D5 over G4: A4/D4 to D5/G4 and on to C5/F4 move in fifths.
    violations = first('A4 A4 G4 A4 D5 C5 C5 B4 D5 C#5 D5')
    assert {(Rule.PARALLEL_FIFTHS, 4), (Rule.PARALLEL_FIFTHS, 5)} <= found(violations)
    fifths = next(v for v in violations if v.rule is Rule.PARALLEL_FIFTHS)
    assert fifths.notes == (3, 4)
    assert fifths.cantus == (3, 4)
    assert fifths.voices == (COUNTERPOINT, CANTUS)
    assert 'bars 4–5' in fifths.message


def test_parallel_octaves_and_unisons() -> None:
    # F5 E5 over F4 E4 (bars 9–10) are octaves, D4 over D4 a unison on a downbeat.
    violations = first('A4 A4 G4 A4 B4 C5 C5 B4 F5 E5 D5')
    assert (Rule.PARALLEL_OCTAVES, 9) in found(violations)
    unison = first('A4 A4 G4 D4 B4 C5 C5 B4 D5 C#5 D5')
    assert (Rule.UNISON, 3) in found(unison)


def test_octaves_by_contrary_motion_are_a_warning() -> None:
    violations = check(notes('D4 A4 D4'), notes('D5 A3 D5'), Context(DORIAN))
    contrary = [v for v in violations if v.rule is Rule.PARALLEL_OCTAVES]
    assert [v.severity for v in contrary] == [Severity.WARNING, Severity.WARNING]
    assert 'contrary motion' in contrary[0].message


def test_direct_octaves_with_a_leap_above() -> None:
    # A4 over D4 (a fifth) to G5 over G4: both rise into an octave, the upper voice leaps.
    violations = first('A4 A4 G4 A4 G5 F5 E5 D5 D5 C#5 D5')
    assert (Rule.DIRECT_OCTAVES, 4) in found(violations)


def test_direct_fifth_with_a_step_above_is_a_warning() -> None:
    # B4 over D4 (a sixth) to C5 over F4 (a fifth): similar motion, the upper voice steps.
    violations = check(notes('D4 F4 E4 D4'), notes('B4 C5 C#5 D5'), Context(DORIAN))
    direct = [v for v in violations if v.rule is Rule.DIRECT_FIFTHS]
    assert [(v.slot, v.severity) for v in direct] == [(1, Severity.WARNING)]


def test_dissonance_in_first_species() -> None:
    violations = first('A4 A4 G4 A4 C5 C5 C5 B4 D5 C#5 D5')  # C5 over G4: a fourth
    assert (Rule.DISSONANCE, 4) in found(violations)
    message = next(v for v in violations if v.rule is Rule.DISSONANCE).message
    assert message == 'Dissonance (perfect fourth) on the downbeat of bar 5'


def test_beginning() -> None:
    assert (Rule.BEGINNING, 0) in found(first('F4 A4 G4 A4 B4 C5 C5 B4 D5 C#5 D5'))
    assert (Rule.BEGINNING, 0) not in found(first('D5 A4 G4 A4 B4 C5 C5 B4 D5 C#5 D5'))
    # Below the cantus a fifth is wrong: it would put the line in G.
    below = check(
        FUX_DORIAN, notes('G3 D3 A3 F3 E3 D3 F3 C4 D4 C#4 D4'), Context(DORIAN, above=False)
    )
    assert (Rule.BEGINNING, 0) in found(below)


def test_ending_and_cadence() -> None:
    assert (Rule.ENDING, 10) in found(first('A4 A4 G4 A4 B4 C5 C5 B4 D5 C#5 A4'))
    # The leading tone is missing: C5 over E4 is a minor sixth.
    missing = first('A4 A4 G4 A4 B4 C5 C5 B4 D5 C5 D5')
    assert (Rule.LEADING_TONE, 9) in found(missing)
    message = next(v for v in missing if v.rule is Rule.LEADING_TONE).message
    assert message == 'The cadence needs the raised leading tone: C♯5, not C5'
    # The final reached by leap is no clausula vera.
    assert (Rule.CADENCE, 10) in found(first('A4 A4 G4 A4 B4 C5 C5 B4 D5 A4 D5'))


def test_phrygian_cadence_rises_a_whole_step() -> None:
    cantus = notes('E4 C4 D4 C4 A3 A4 G4 E4 F4 E4')
    good = notes('B4 C5 F4 G4 A4 C5 B4 E5 D5 E5')  # Fux, fig. 11
    context = Context(PHRYGIAN)
    assert not errors(check(cantus, good, context))
    raised = notes('B4 C5 F4 G4 A4 C5 B4 E5 D#5 E5')
    assert (Rule.LEADING_TONE, 8) in found(check(cantus, raised, context))


def test_ficta() -> None:
    assert mode_ficta(DORIAN) == {PitchName.parse('Bb')}
    assert cadence_ficta(DORIAN) == (PitchName.parse('C#'), None)
    aeolian = Scale(PitchName.parse('A'), ScaleType.AEOLIAN)
    assert cadence_ficta(aeolian) == (PitchName.parse('G#'), PitchName.parse('F#'))
    assert cadence_ficta(PHRYGIAN) == (None, None)
    # A raised seventh inside the line that does not lead to the final, and a G♯.
    assert (Rule.FOREIGN_NOTE, 5) in found(first('A4 A4 G4 A4 B4 C#5 A4 B4 D5 C#5 D5'))
    assert (Rule.FOREIGN_NOTE, 3) in found(first('A4 A4 G4 G#4 B4 C5 C5 B4 D5 C#5 D5'))
    # B♭ is Dorian's ficta anywhere.
    assert not found(first('A4 A4 G4 A4 Bb4 C5 C5 B4 D5 C#5 D5')) - {(Rule.MELODIC_INTERVAL, 7)}


def test_melodic_rules() -> None:
    # F5 down to B4 is a diminished fifth; G4 up to A5 more than an octave.
    tritone = first('A4 A4 G4 F5 B4 C5 C5 B4 D5 C#5 D5')
    assert (Rule.MELODIC_INTERVAL, 4) in found(tritone)
    assert (Rule.LARGE_LEAP, 5) in found(first('A4 A4 G4 A4 G4 A5 C5 B4 D5 C#5 D5'))
    # C5 up to A5 is a major sixth.
    assert (Rule.LARGE_LEAP, 6) in found(first('A4 A4 G4 A4 B4 C5 A5 B4 D5 C#5 D5'))
    # A falling minor sixth is only a warning (Fux uses it, fig. 75).
    fall = first('A4 A4 G4 A4 B4 F5 A4 B4 D5 C#5 D5')
    leap = [v for v in fall if v.rule is Rule.LARGE_LEAP]
    assert [v.severity for v in leap] == [Severity.WARNING]


def test_repeated_notes_by_species() -> None:
    repeated = [v for v in first() if v.rule is Rule.REPEATED_NOTE]
    assert len(repeated) == 2
    assert all(v.severity is Severity.WARNING for v in repeated)
    assert repeated[0].message == 'The counterpoint repeats A4 (bars 1–2)'
    # In second species a repeated note is an error.
    line = notes('A4 D5 A4 A4 C5 G4 A4 D5 B4 C5 D5 A4 C5 D5 E5 B4 D5 A4 B4 C#5 D5')
    context = Context(DORIAN, Species.SECOND, rhythm=FIG_33_RHYTHM)
    assert (Rule.REPEATED_NOTE, 3) in found(check(FUX_DORIAN, line, context))


# Second species --------------------------------------------------------------------------

FIG_33 = 'A4 D5 A4 B4 C5 G4 A4 D5 B4 C5 D5 A4 C5 D5 E5 B4 D5 A4 B4 C#5 D5'
"""Fux's second-species solution above the Dorian cantus (fig. 33, begun without a rest)."""
FIG_33_RHYTHM = Rhythm((Duration(NoteValue.HALF),) * 20 + (Duration(NoteValue.WHOLE),))


def second(line: str) -> list[Violation]:
    return check(FUX_DORIAN, notes(line), Context(DORIAN, Species.SECOND, rhythm=FIG_33_RHYTHM))


def test_passing_tone_and_a_dissonance_left_by_leap() -> None:
    assert not errors(second(FIG_33))
    # B4 over F4 passes from A4 to C5; left for G4 instead, it is left by leap.
    bad = second('A4 D5 A4 B4 G4 G4 A4 D5 B4 C5 D5 A4 C5 D5 E5 B4 D5 A4 B4 C#5 D5')
    assert (Rule.DISSONANCE_TREATMENT, 3) in found(bad)
    treatment = next(v for v in bad if v.rule is Rule.DISSONANCE_TREATMENT)
    assert treatment.notes == (2, 3, 4)
    assert 'not a passing tone' in treatment.message


def test_downbeat_dissonance_in_second_species() -> None:
    bad = second('A4 D5 G4 B4 C5 G4 A4 D5 B4 C5 D5 A4 C5 D5 E5 B4 D5 A4 B4 C#5 D5')
    assert (Rule.DISSONANCE, 2) in found(bad)


def test_downbeat_fifths_in_second_species() -> None:
    # C5 over F4 (bar 3) and B4 over E4 (bar 4), with D5 a step between them.
    cantus = notes('D4 G4 F4 E4 D4')
    line = notes('A4 D5 E5 C5 D5 B4 C#5 D5')
    violations = check(cantus, line, Context(DORIAN, Species.SECOND))
    downbeats = [v for v in violations if v.message == 'Fifths on the downbeats of bars 3 and 4']
    assert [(v.rule, v.severity, v.notes) for v in downbeats] == [
        (Rule.PARALLEL_FIFTHS, Severity.ERROR, (3, 5))
    ]


# Third species ---------------------------------------------------------------------------


def third(line: str, cantus: str = 'D4 E4 D4') -> list[Violation]:
    return check(notes(cantus), notes(line), Context(DORIAN, Species.THIRD))


def test_neighbor_and_double_neighbor() -> None:
    # G4 over D4 is a lower neighbor (A4 G4 A4); B4 C5 A4 B4 a double neighbor.
    assert not errors(third('A4 G4 A4 B4 C5 A4 B4 C#5 D5'))


def test_cambiata() -> None:
    # C5, a seventh over D4, steps down from D5, leaps a third down and turns up.
    assert not errors(third('D5 C5 A4 B4 G4 A4 B4 C#5 D5'))
    # Without the turn the dissonance is only left by leap.
    bad = third('D5 C5 A4 G4 G4 A4 B4 C#5 D5')
    assert (Rule.DISSONANCE_TREATMENT, 1) in found(bad)


def test_fifth_species_eighths_move_by_step() -> None:
    cantus = notes('D4 F4 E4 D4')
    eighth = Duration(NoteValue.EIGHTH)
    quarter = Duration(NoteValue.QUARTER)
    half = Duration(NoteValue.HALF)
    whole = Duration(NoteValue.WHOLE)
    rhythm = Rhythm((whole, quarter, eighth, eighth, half, half, whole), rest=half)
    context = Context(DORIAN, Species.FIFTH, rhythm=rhythm)
    good = check(cantus, notes('A4 A4 G4 F4 G4 C#5 D5'), context)
    assert not any(v.rule is Rule.EIGHTH_NOTES for v in good)
    bad = check(cantus, notes('A4 A4 C5 F4 G4 C#5 D5'), context)
    assert any(v.rule is Rule.EIGHTH_NOTES for v in errors(bad))


# Fourth species ---------------------------------------------------------------------------


def fourth(line: str, cantus: str = 'D4 F4 E4 D4', above: bool = True) -> list[Violation]:
    return check(notes(cantus), notes(line), Context(DORIAN, Species.FOURTH, above))


def test_seven_six_and_two_three_suspensions() -> None:
    # Above: A4 | A4 (a third over F4) D5 | D5 (a seventh over E4) C♯5 | D5.
    assert not errors(fourth('A4 D5 C#5 D5'))
    # Below: D3 | D3 D4 | D4 (a second under E4) C♯4 | D4.
    assert not errors(fourth('D3 D4 C#4 D4', above=False))


def test_suspension_resolving_up() -> None:
    violations = fourth('A4 D5 E5 D5')
    suspension = [v for v in errors(violations) if v.rule is Rule.SUSPENSION]
    assert suspension
    assert suspension[0].slot == 1
    assert (
        suspension[0].message
        == 'The suspension (D5) in bar 3 resolves up; it resolves down by step'
    )


def test_unprepared_suspension() -> None:
    # D4 struck under G4 is a fourth: the suspension is not prepared.
    violations = fourth('D3 D4 C#4 D4', 'D4 G4 E4 D4', above=False)
    assert (Rule.SUSPENSION, 1) in found(violations)


def test_suspensions_the_style_avoids() -> None:
    # Above, E4 struck over C4 becomes a second over D4: a 2–1 resolving into a unison.
    above = fourth('A4 E4 D4 C#5 D5', 'D4 C4 D4 E4 D4')
    assert (Rule.SUSPENSION, 1) in found(above)
    # Below, F3 struck under F4 becomes a seventh under E4: a 7–8.
    below = fourth('D3 F3 C#4 D4', 'D4 F4 E4 D4', above=False)
    seven = [v for v in errors(below) if v.rule is Rule.SUSPENSION]
    assert seven
    assert seven[0].slot == 1
    assert '7–8' in seven[0].message
    # Below, a 4–5 is only a warning (Fux, fig. 76).
    cantus = notes('E4 C4 D4 C4 A3 A4 G4 E4 F4 E4')
    line, rhythm = parse_line(next(e for e in EXAMPLES if e.figure == '76').counterpoint)
    context = Context(PHRYGIAN, Species.FOURTH, above=False, rhythm=rhythm)
    four_five = [v for v in check(cantus, line, context) if v.rule is Rule.SUSPENSION]
    assert four_five
    assert all(v.severity is Severity.WARNING for v in four_five)
    assert '4–5' in four_five[0].message


# Names ----------------------------------------------------------------------------------


def test_every_rule_has_a_name_mark_and_reason() -> None:
    for rule in Rule:
        assert rule_name(rule)
        assert 0 < len(rule_mark(rule)) <= 3
        assert rule_reason(rule).endswith('.')
    assert voice_name(COUNTERPOINT) == 'counterpoint'
    assert voice_title(CANTUS) == 'Cantus firmus'
    assert species_name(Species.FOURTH) == 'Fourth species'


def test_species_rhythms() -> None:
    assert species_rhythm(Species.FIRST, 4).length == 4
    second_species = species_rhythm(Species.SECOND, 4)
    assert second_species.rest == Duration(NoteValue.HALF)
    assert len(second_species.notes) == 6
    assert species_rhythm(Species.THIRD, 4).length == 4
    fourth_species = species_rhythm(Species.FOURTH, 5)
    assert fourth_species.tied() == (True, True, True, False, False)
    with pytest.raises(ValueError, match='fifth species'):
        species_rhythm(Species.FIFTH, 4)


def test_mismatched_lengths_raise() -> None:
    with pytest.raises(ValueError, match='the rhythm'):
        check(FUX_DORIAN, notes('A4 A4'), Context(DORIAN))
