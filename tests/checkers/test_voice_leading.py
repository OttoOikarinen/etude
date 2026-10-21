# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The voice-leading rules, each with a correct and a broken textbook example.

References: Kostka & Payne, *Tonal Harmony* (K–P), ch. 5–6 (voice leading in
four parts), 13 (V7); Aldwell & Schachter, *Harmony and Voice Leading* (A–S),
ch. 4–5. Chords are written soprano, alto, tenor, bass; C major unless noted.
"""

from __future__ import annotations

import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from etude.checkers.realize import chords_of, realize
from etude.checkers.voice_leading import (
    ALTO,
    BASS,
    MOTION_RULES,
    SOPRANO,
    TENOR,
    Context,
    Ranges,
    Rule,
    Severity,
    Violation,
    check,
    errors,
    rule_mark,
    rule_name,
    rule_reason,
    scan,
    voice_name,
)
from etude.core import Interval, Key, Pitch

C = Key.parse('C')
P = Pitch.parse
WIDE = Ranges(*(((P('C1'), P('C8')),) * 4))
"""Ranges no example leaves: for rules other than RANGE in transposed passages."""


def chords(*texts: str) -> tuple[tuple[Pitch, ...], ...]:
    return tuple(tuple(P(n) for n in text.split()) for text in texts)


def run(
    numerals: str | None,
    *texts: str,
    key: Key = C,
    rules: frozenset[Rule] | None = None,
) -> list[Violation]:
    harmony = chords_of(numerals.split(), key) if numerals else ()
    context = Context(key, harmony, rules=rules if rules is not None else frozenset(Rule))
    return check(chords(*texts), context)


def kinds(violations: list[Violation]) -> set[tuple[Rule, Severity]]:
    return {(v.rule, v.severity) for v in violations}


def only(violations: list[Violation]) -> Violation:
    assert len(violations) == 1, [v.message for v in violations]
    return violations[0]


# Correct writing ---------------------------------------------------------------------


def test_a_correct_cadence_has_no_violation() -> None:
    # K–P ex. 5-?: I–IV–V–I with common tones held and the other voices by step.
    found = run('I IV V I', 'C5 G4 E4 C3', 'C5 A4 F4 F3', 'B4 G4 D4 G3', 'C5 G4 E4 C3')
    assert found == []


def test_tenor_and_bass_may_be_more_than_an_octave_apart() -> None:
    # K–P: spacing applies to soprano–alto and alto–tenor only.
    assert run('I', 'E5 C5 G4 C3') == []


def test_incomplete_v7_resolves_to_complete_i_and_complete_v7_to_incomplete_i() -> None:
    # K–P ch. 13: the two standard resolutions of V7 in four parts.
    assert run('V7 I', 'B4 G4 F4 G3', 'C5 G4 E4 C3') == []
    assert run('V7 I', 'D5 B4 F4 G3', 'C5 C5 E4 C3') == []


# Parallels ---------------------------------------------------------------------------


def test_parallel_fifths() -> None:
    # A–S ch. 4: consecutive perfect fifths between alto and tenor (I–ii6); the rest of
    # the passage is correct.
    found = only(run('I ii6', 'E5 G4 C4 C3', 'D5 A4 D4 F2'))
    assert (found.rule, found.severity, found.slot) == (Rule.PARALLEL_FIFTHS, Severity.ERROR, 1)
    assert found.voices == (ALTO, TENOR)
    assert found.slots == (0, 1)
    assert found.message == 'Parallel fifths between alto and tenor (chords 1–2)'
    # A compound fifth (a twelfth) counts too: soprano and bass, I–IV.
    found = only(run('I IV', 'G4 E4 G3 C3', 'C5 F4 A3 F3'))
    assert (found.rule, found.voices) == (Rule.PARALLEL_FIFTHS, (SOPRANO, BASS))


def test_fifths_by_contrary_motion_are_errors() -> None:
    # K–P ch. 6: consecutive fifths by contrary motion are avoided in exercises.
    found = only(run('I IV', 'G5 G4 E4 C3', 'C5 A4 F4 F3'))
    assert (found.rule, found.severity) == (Rule.PARALLEL_FIFTHS, Severity.ERROR)
    assert 'contrary motion' in found.message


def test_unequal_fifths() -> None:
    # K–P ch. 6: P5 → d5 is acceptable in the upper voices (I–vii°6, alto and tenor).
    assert run('I viio6', 'E5 G4 C4 C3', 'D5 F4 B3 D3') == []
    # d5 → P5 in the upper voices is weak (vii°6–I6, soprano and alto): a warning.
    found = only(run('viio6 I6', 'F5 B4 D4 D3', 'G5 C5 C4 E3'))
    assert (found.rule, found.severity) == (Rule.PARALLEL_FIFTHS, Severity.WARNING)
    # Involving the bass, d5 → P5 is an error.
    found = only(run(None, 'D5 F4 D4 B2', 'E5 G4 E4 C3', rules=frozenset({Rule.PARALLEL_FIFTHS})))
    assert (found.severity, found.voices) == (Severity.ERROR, (ALTO, BASS))


def test_parallel_octaves() -> None:
    # K–P ch. 6: the classic V7–I mistake, the tenor doubling the bass in octaves.
    found = only(run('V7 I', 'B4 F4 G3 G2', 'C5 E4 C4 C3'))
    assert (found.rule, found.severity) == (Rule.PARALLEL_OCTAVES, Severity.ERROR)
    assert found.voices == (TENOR, BASS)
    found = only(run('ii6 V', 'D5 F4 A3 F3', 'D5 G4 B3 G3'))
    assert (found.rule, found.voices) == (Rule.PARALLEL_OCTAVES, (ALTO, BASS))


def test_parallel_unisons() -> None:
    found = run(None, 'C5 E4 E4 C3', 'B4 D4 D4 G2', rules=frozenset({Rule.PARALLEL_OCTAVES}))
    assert only(found).message == 'Parallel unisons between alto and tenor (chords 1–2)'


def test_octave_leaps_of_the_same_two_notes_are_not_parallels() -> None:
    # Soprano and tenor keep G and C, both an octave lower: no new interval is heard.
    rules = frozenset({Rule.PARALLEL_FIFTHS, Rule.PARALLEL_OCTAVES})
    assert run(None, 'G5 E5 C4 C3', 'G4 E4 C3 C3', rules=rules) == []


def test_held_notes_are_not_parallels() -> None:
    # Oblique motion into the same interval is fine (a common tone held).
    assert run(None, 'G4 C4 E3 C3', 'G4 C4 E3 C3', rules=frozenset(MOTION_RULES)) == []


# Direct fifths and octaves -----------------------------------------------------------


def test_direct_octaves_in_the_outer_voices() -> None:
    # K–P ch. 6: similar motion into an octave with a leap in the soprano.
    found = only(run('ii6 V', 'D5 A4 D4 F3', 'G5 B4 D4 G3'))
    assert (found.rule, found.severity) == (Rule.DIRECT_OCTAVES, Severity.ERROR)
    assert found.voices == (SOPRANO, BASS)


def test_direct_octaves_are_fine_when_the_soprano_steps() -> None:
    # The same arrival with the soprano moving by step (V–I, 7̂–1̂ over 5̂–1̂).
    assert run('V I', 'B4 G4 D4 G3', 'C5 G4 E4 C3') == []


def test_direct_fifths_are_a_warning() -> None:
    # A–S ch. 4 treat direct fifths as less objectionable than direct octaves.
    found = only(run('IV V', 'A4 F4 C4 F3', 'D5 D4 B3 G3'))
    assert (found.rule, found.severity) == (Rule.DIRECT_FIFTHS, Severity.WARNING)


# One chord ---------------------------------------------------------------------------


def test_spacing() -> None:
    # K–P ch. 5: no more than an octave between soprano and alto.
    found = only(run('I V', 'G5 E4 G3 C3', 'B4 D4 G3 G2'))
    assert (found.rule, found.slot, found.voices) == (Rule.SPACING, 0, (SOPRANO, ALTO))
    found = only(run('I', 'C5 G4 E3 C3'))
    assert (found.rule, found.voices) == (Rule.SPACING, (ALTO, TENOR))


def test_crossing() -> None:
    # K–P ch. 5: the tenor above the alto in V7.
    found = only(run('ii65 V7', 'C5 A4 D4 F3', 'B4 F4 G4 G3'))
    assert (found.rule, found.severity, found.slot) == (Rule.CROSSING, Severity.ERROR, 1)
    assert found.voices == (ALTO, TENOR)


def test_overlap_is_a_warning() -> None:
    # A–S ch. 4: the tenor moves above the note the alto just left.
    found = run(None, 'C5 E4 C4 C3', 'B4 D4 G4 G2', rules=frozenset({Rule.OVERLAP}))
    assert (only(found).severity, only(found).voices) == (Severity.WARNING, (ALTO, TENOR))
    assert run(None, 'C5 G4 E4 C3', 'B4 G4 D4 G3', rules=frozenset({Rule.OVERLAP})) == []


def test_range() -> None:
    found = only(run('IV', 'A5 C5 F4 F3'))
    assert (found.rule, found.voices) == (Rule.RANGE, (SOPRANO,))
    assert found.message == "The soprano's A5 is above its range (highest G5) in chord 1"
    found = only(run('ii', 'F5 A4 D4 D2'))
    assert (found.rule, found.voices) == (Rule.RANGE, (BASS,))


# Doubling and completeness -----------------------------------------------------------


def test_doubled_leading_tone() -> None:
    # K–P ch. 5: never double the leading tone.
    found = only(run('IV V', 'C5 A4 F4 F3', 'B4 B4 D4 G3'))
    assert (found.rule, found.severity, found.slot) == (Rule.WRONG_DOUBLING, Severity.ERROR, 1)
    assert found.voices == (SOPRANO, ALTO)


def test_doubled_seventh() -> None:
    found = only(run('V7', 'F5 B4 F4 G3'))
    assert (found.rule, found.severity) == (Rule.WRONG_DOUBLING, Severity.ERROR)
    assert 'seventh' in found.message


def test_doubled_third_of_a_major_triad_is_a_warning() -> None:
    # A–S ch. 5: in root-position major triads double the root, not the third.
    found = only(run('I', 'E5 G4 E4 C3'))
    assert (found.rule, found.severity) == (Rule.WRONG_DOUBLING, Severity.WARNING)


def test_doubled_third_is_right_in_the_deceptive_cadence() -> None:
    # K–P ch. 6: in V–VI in minor the third of VI (the tonic) is doubled.
    c_minor = Key.parse('c')
    assert run('V VI', 'B4 G4 D4 G3', 'C5 Eb4 C4 Ab3', key=c_minor) == []


def test_missing_third_is_an_error() -> None:
    found = only(run('I', 'C5 G4 C4 C3'))
    assert (found.rule, found.severity) == (Rule.INCOMPLETE_CHORD, Severity.ERROR)
    assert found.message == 'Chord 1 has no third (E)'


def test_missing_root_is_an_error() -> None:
    found = only(run('I6', 'E5 G4 G3 E3'))
    assert (found.rule, found.severity) == (Rule.INCOMPLETE_CHORD, Severity.ERROR)


def test_omitted_fifth() -> None:
    # K–P: a root-position triad may omit its fifth (a weakness out of context) …
    found = only(run('I', 'C5 E4 C4 C3'))
    assert (found.rule, found.severity) == (Rule.INCOMPLETE_CHORD, Severity.WARNING)
    # … a root-position seventh chord often does (ch. 13) …
    assert run('V7', 'B4 G4 F4 G3') == []
    # … but an inverted seventh chord is complete.
    found = only(run('V65', 'G4 F4 G3 B2'))
    assert (found.rule, found.severity) == (Rule.INCOMPLETE_CHORD, Severity.ERROR)


def test_wrong_chord() -> None:
    found = only(run('I', 'E5 A4 G4 C3'))
    assert (found.rule, found.voices) == (Rule.WRONG_CHORD, (ALTO,))
    found = only(run('I6', 'C5 G4 E4 C3'))
    assert (found.rule, found.voices) == (Rule.WRONG_CHORD, (BASS,))
    assert found.message == 'The bass of chord 1 should be E for this inversion'


def test_without_harmony_the_chord_is_identified() -> None:
    # No numerals: the doubled leading tone is still found in an identified V.
    assert kinds(run(None, 'B4 B4 D4 G3')) == {(Rule.WRONG_DOUBLING, Severity.ERROR)}
    with pytest.raises(ValueError, match='four pitches'):
        check(chords('C5 G4 C3'))


# Tendency tones ----------------------------------------------------------------------


def test_leading_tone_in_the_soprano_rises() -> None:
    # K–P ch. 6: 7̂ in an outer voice goes to 1̂ in V–I.
    found = only(run('V I', 'B4 D4 G3 G2', 'G4 E4 G3 C3'))
    assert (found.rule, found.severity, found.voices) == (
        Rule.LEADING_TONE,
        Severity.ERROR,
        (SOPRANO,),
    )


def test_frustrated_leading_tone_in_an_inner_voice() -> None:
    # K–P ch. 6: in an inner voice 7̂ may drop to 5̂ to complete the tonic triad.
    assert run('V I', 'D5 B4 G4 G3', 'C5 G4 E4 C3') == []


def test_leading_tone_rises_in_the_deceptive_cadence() -> None:
    found = only(run('V vi', 'D5 B4 G4 G3', 'C5 A4 E4 A3'))
    assert (found.rule, found.severity, found.voices) == (
        Rule.LEADING_TONE,
        Severity.ERROR,
        (ALTO,),
    )


def test_chordal_seventh_resolves_down() -> None:
    # K–P ch. 13: the seventh of V7 falls by step to 3̂.
    found = only(run('V7 I', 'D5 B4 F4 G3', 'E5 C5 G4 C3'))
    assert (found.rule, found.severity, found.voices) == (
        Rule.CHORDAL_SEVENTH,
        Severity.ERROR,
        (TENOR,),
    )


def test_seventh_may_rise_in_v43_i6() -> None:
    # K–P ch. 13: in V4/3–I6 the seventh may rise, in parallel tenths with the bass
    # (the unequal fifths it makes with the leading tone are mentioned, too).
    found = run('V43 I6', 'F5 B4 G4 D3', 'G5 C5 G4 E3')
    assert kinds(found) == {
        (Rule.CHORDAL_SEVENTH, Severity.WARNING),
        (Rule.PARALLEL_FIFTHS, Severity.WARNING),
    }


def test_seventh_may_wait_while_the_harmony_continues() -> None:
    assert run('V7 V65', 'B4 G4 F4 G3', 'D5 G4 F4 B2', rules=frozenset(MOTION_RULES)) == []


# Melodic intervals -------------------------------------------------------------------


def test_augmented_second() -> None:
    # K–P ch. 6: in minor, ♭6̂–7̂ is an augmented second (A♭–B in C minor).
    rules = frozenset({Rule.AUGMENTED_SECOND})
    found = only(run(None, 'C5 Ab4 F4 F3', 'B4 B4 D4 G3', key=Key.parse('c'), rules=rules))
    assert found.voices == (ALTO,)
    assert found.message == 'The alto moves by an augmented second, A♭4 to B4 (chords 1–2)'
    # A chromatic semitone is not an augmented interval.
    assert run(None, 'C5 G4 E4 C3', 'C#5 G4 E4 A2', rules=rules) == []


def test_large_leaps() -> None:
    rules = frozenset({Rule.LARGE_LEAP})
    found = only(run(None, 'C5 G4 E4 C3', 'C5 G4 A3 C3', rules=rules))
    assert (found.severity, found.voices) == (Severity.WARNING, (TENOR,))
    found = only(run(None, 'C5 G4 E4 C3', 'E5 G4 E4 G4', rules=rules))
    assert (found.severity, found.voices) == (Severity.ERROR, (BASS,))
    # The soprano and bass may leap up to an octave.
    assert run(None, 'C5 G4 E4 C3', 'C4 G4 E4 C2', rules=rules) == []


# The API -----------------------------------------------------------------------------


def test_rules_can_be_switched_off() -> None:
    passage = ('G4 E4 G3 C3', 'C5 F4 A3 F3')
    assert run('I IV', *passage)
    assert run('I IV', *passage, rules=frozenset(Rule) - {Rule.PARALLEL_FIFTHS}) == []


def test_scan_finds_the_same_violations_without_messages() -> None:
    passage = chords('C5 A4 F4 F3', 'B4 B4 D4 G3', 'G4 E4 G3 C3')
    context = Context(C, chords_of(['IV', 'V', 'I'], C))
    full = check(passage, context)
    fast = scan(passage, context)
    assert [(v.rule, v.severity, v.slot, v.voices) for v in fast] == [
        (v.rule, v.severity, v.slot, v.voices) for v in full
    ]
    assert all(v.message for v in full)
    assert not any(v.message for v in fast)
    assert errors(full) == [v for v in full if v.severity is Severity.ERROR]


def test_every_rule_has_a_name_a_mark_and_a_reason() -> None:
    for rule in Rule:
        assert rule_name(rule).strip()
        assert rule_mark(rule).strip()
        assert rule_reason(rule).strip()
    assert [voice_name(v) for v in range(4)] == ['soprano', 'alto', 'tenor', 'bass']


# Properties --------------------------------------------------------------------------

PROGRESSIONS = (
    'I IV V I',
    'I vi IV V I',
    'I ii6 V7 I',
    'I IV Cad64 V I',
    'I V65 I',
    'I V42 I6',
    'I V43 I6',
    'I viio6 I6',
    'I IV V vi',
    'I ii65 V7 I',
)
TONICS = ('C', 'G', 'D', 'A', 'E', 'F', 'Bb', 'Eb', 'Ab', 'Db')


def _minor(numerals: str) -> str:
    table = {
        'I': 'i',
        'I6': 'i6',
        'IV': 'iv',
        'vi': 'VI',
        'ii6': 'iio6',
        'ii65': 'iiø65',
    }
    return ' '.join(table.get(n, n) for n in numerals.split())


def _transpose(passage: tuple[tuple[Pitch, ...], ...], interval: Interval):
    return tuple(tuple(p.transpose(interval) for p in chord) for chord in passage)


@settings(max_examples=40, deadline=None)
@given(
    progression=st.sampled_from(PROGRESSIONS),
    minor=st.booleans(),
    seed=st.integers(0, 10_000),
    interval=st.sampled_from(('M2', 'm3', 'P4', 'P5', 'M6', 'm7')),
)
def test_transposing_a_passage_keeps_its_violations(
    progression: str, minor: bool, seed: int, interval: str
) -> None:
    """Breaking a correct realisation somewhere and transposing it finds the same
    violations in the same places (spelled transposition keeps every interval)."""
    rng = random.Random(seed)
    key = Key.parse('c' if minor else 'C')
    numerals = (_minor(progression) if minor else progression).split()
    passage = realize(numerals, key, rng)
    slot, voice = rng.randrange(len(passage)), rng.randrange(3)
    broken = list(map(list, passage))
    broken[slot][voice] = broken[slot][voice].transpose(Interval.parse('M2'))
    original = tuple(map(tuple, broken))
    step = Interval.parse(interval)
    moved_key = Key(key.tonic.transpose(step), key.mode)

    def signature(found: list[Violation]) -> list[tuple[Rule, Severity, int, tuple[int, ...]]]:
        return [(v.rule, v.severity, v.slot, v.voices) for v in found]

    before = check(original, Context(key, chords_of(numerals, key), WIDE))
    after = check(
        _transpose(original, step), Context(moved_key, chords_of(numerals, moved_key), WIDE)
    )
    assert signature(before) == signature(after)


@settings(max_examples=40, deadline=None)
@given(progression=st.sampled_from(PROGRESSIONS), seed=st.integers(0, 10_000))
def test_voice_order_matters(progression: str, seed: int) -> None:
    """Reversing the voices of a correct passage turns every chord upside down: the
    checker reports crossings, so it does not treat the voices as a set."""
    passage = realize(progression.split(), C, random.Random(seed))
    assert errors(check(passage, Context(C, chords_of(progression.split(), C)))) == []
    flipped = tuple(tuple(reversed(chord)) for chord in passage)
    found = check(flipped, Context(C, (), WIDE))
    assert any(v.rule is Rule.CROSSING for v in found)


@settings(max_examples=60, deadline=None)
@given(
    progression=st.sampled_from(PROGRESSIONS),
    minor=st.booleans(),
    tonic=st.sampled_from(TONICS),
    seed=st.integers(0, 10_000),
)
def test_violations_are_sorted_and_in_range(
    progression: str, minor: bool, tonic: str, seed: int
) -> None:
    key = Key.parse(tonic.lower() if minor else tonic)
    numerals = (_minor(progression) if minor else progression).split()
    rng = random.Random(seed)
    passage = [list(c) for c in realize(numerals, key, rng)]
    # Scramble a few notes to provoke violations.
    for _ in range(3):
        slot, voice = rng.randrange(len(passage)), rng.randrange(4)
        passage[slot][voice] = passage[slot][voice].transpose(
            Interval.parse(rng.choice(('m2', 'M3', 'P5'))), down=rng.random() < 0.5
        )
    found = check(tuple(map(tuple, passage)), Context(key, chords_of(numerals, key)))
    assert [v.slot for v in found] == sorted(v.slot for v in found)
    for violation in found:
        assert 0 <= violation.slot < len(passage)
        assert all(0 <= v < 4 for v in violation.voices)
        assert all(0 <= s < len(passage) for s in violation.slots)
        assert violation.message


def test_scan_from_a_slot_checks_only_the_new_chord() -> None:
    # The first chord breaks a rule (no third); from slot 1 only the motion into the
    # second chord and the second chord itself are looked at.
    passage = chords('C5 G4 C4 C3', 'B4 G4 D4 G3')
    context = Context(C, chords_of(['I', 'V'], C))
    assert {v.slot for v in scan(passage, context)} == {0}
    assert scan(passage, context, first=1) == []
    broken = chords('C5 G4 E4 C3', 'B4 B4 D4 G3')
    assert [v.rule for v in scan(broken, context, first=1)] == [Rule.WRONG_DOUBLING]
