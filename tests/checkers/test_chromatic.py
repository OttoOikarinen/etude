# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Chromatic harmony in the checker and the voicer, with textbook examples.

References: Kostka & Payne, *Tonal Harmony* (K–P), ch. 16–17 (secondary functions),
21 (mode mixture), 22 (the Neapolitan), 23 (augmented sixths); Aldwell & Schachter,
*Harmony and Voice Leading* (A–S), ch. 16, 22, 29–31. Chords are written soprano,
alto, tenor, bass.
"""

from __future__ import annotations

import random

import pytest

from etude.checkers.realize import chords_of, function_keys, realize
from etude.checkers.voice_leading import (
    ALTO,
    BASS,
    SOPRANO,
    TENOR,
    Context,
    Rule,
    Severity,
    Violation,
    alteration,
    check,
    errors,
)
from etude.core import Key, Pitch, PitchName, RomanNumeral

C = Key.parse('C')
c = Key.parse('c')
P = Pitch.parse
N = PitchName.parse


def chords(*texts: str) -> tuple[tuple[Pitch, ...], ...]:
    return tuple(tuple(P(n) for n in text.split()) for text in texts)


def run(numerals: str, *texts: str, key: Key = C, local: bool = True) -> list[Violation]:
    """Check ``texts`` against ``numerals``; with ``local`` each chord is read in its
    tonicized key, as the exercises do."""
    names = numerals.split()
    keys = function_keys(names, key) if local else ()
    return check(chords(*texts), Context(key, chords_of(names, key), keys=keys))


def kinds(violations: list[Violation]) -> set[tuple[Rule, Severity]]:
    return {(v.rule, v.severity) for v in violations}


def spelled(numeral: str, key: str) -> str:
    chord = RomanNumeral.parse(numeral).realize(Key.parse(key))
    return ' '.join(str(n) for n in chord.names_from_bass())


# Spelling ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('numeral', 'key', 'expected'),
    [
        # Secondary dominants and leading-tone chords (K–P ch. 16–17).
        ('V7/V', 'C', 'D F# A C'),
        ('V65/V', 'G', 'C# E G A'),
        ('V7/V', 'c', 'D F# A C'),
        ('viio7/V', 'C', 'F# A C Eb'),
        ('viio7/V', 'e', 'A# C# E G'),
        ('viiø7/V', 'F', 'B D F A'),
        ('V/ii', 'D', 'B D# F#'),
        ('V7/vi', 'Bb', 'D F# A C'),
        ('viio7/vi', 'A', 'E# G# B D'),
        ('V7/IV', 'Eb', 'Eb G Bb Db'),
        ('V7/iv', 'a', 'A C# E G'),
        ('viio7/iv', 'g', 'B D F Ab'),
        ('V7/VI', 'c', 'Eb G Bb Db'),
        ('V42/V', 'A', 'A B D# F#'),
        # Mode mixture in major (K–P ch. 21).
        ('iv', 'G', 'C Eb G'),
        ('iio6', 'C', 'F Ab D'),
        ('iiø65', 'E', 'A C E F#'),
        ('bIII', 'D', 'F A C'),
        ('bVI', 'A', 'F A C'),
        ('bVII', 'Eb', 'Db F Ab'),
        ('viio7', 'F', 'E G Bb Db'),
        # The Neapolitan sixth (K–P ch. 22): the major triad on ♭2̂, third in the bass.
        ('N6', 'c', 'F Ab Db'),
        ('N6', 'C', 'F Ab Db'),
        ('N6', 'e', 'A C F'),
        ('N6', 'f#', 'B D G'),
        ('N6', 'Bb', 'Eb Gb Cb'),
        # Augmented sixths (K–P ch. 23): ♭6̂ in the bass, ♯4̂ above.
        ('It+6', 'c', 'Ab C F#'),
        ('Fr+6', 'c', 'Ab C D F#'),
        ('Ger+6', 'c', 'Ab C Eb F#'),
        ('Ger+6', 'C', 'Ab C Eb F#'),
        ('Ger+6(#2)', 'C', 'Ab C D# F#'),
        ('It+6', 'a', 'F A D#'),
        ('Fr+6', 'G', 'Eb G A C#'),
        ('Ger+6', 'e', 'C E G A#'),
        ('Ger+6(#2)', 'D', 'Bb D E# G#'),
        ('Ger+6/V', 'C', 'Eb G Bb C#'),
    ],
)
def test_chromatic_chords_are_spelled_as_the_books_do(
    numeral: str, key: str, expected: str
) -> None:
    assert spelled(numeral, key) == expected


def test_alteration_is_measured_against_the_key() -> None:
    assert alteration(N('F#'), C) == 1
    assert alteration(N('Ab'), C) == -1
    assert alteration(N('Db'), C) == -1
    assert alteration(N('B'), c) == 0  # the leading tone of minor
    assert alteration(N('A'), c) == 0  # the raised sixth of minor
    assert alteration(N('Db'), c) == -1  # ♭2̂, the Neapolitan
    assert alteration(N('F#'), c) == 1  # ♯4̂ of vii°7/V and the augmented sixths
    assert alteration(N('E'), c) == 1  # the third of V/iv


# Secondary functions ----------------------------------------------------------------------


def test_a_secondary_leading_tone_is_not_doubled() -> None:
    # V/V in C with F♯ in soprano and alto. Read in G (its tonicized key) F♯ is the
    # leading tone; read in C it is a raised note: an error either way (K–P ch. 16).
    doubled = ('F#5 F#4 A3 D3',)
    local = errors(run('V/V', *doubled))
    assert [v.rule for v in local] == [Rule.WRONG_DOUBLING]
    assert 'leading tone' in local[0].message
    plain = errors(run('V/V', *doubled, local=False))
    assert [v.rule for v in plain] == [Rule.WRONG_DOUBLING]
    assert 'raised' in plain[0].message


def test_a_secondary_leading_tone_rises_to_its_tonic() -> None:
    good = ('F#5 A4 D4 D3', 'G5 B4 D4 G2')
    assert errors(run('V/V V', *good)) == []
    bad = ('F#5 A4 D4 D3', 'D5 B4 D4 G2')  # F♯ in the soprano falls to D
    found = errors(run('V/V V', *bad))
    assert [(v.rule, v.voices) for v in found] == [(Rule.LEADING_TONE, (SOPRANO,))]
    # Without the tonicized key the generic rule for raised notes finds the same.
    plain = errors(run('V/V V', *bad, local=False))
    assert [(v.rule, v.voices) for v in plain] == [(Rule.CHROMATIC_TONE, (SOPRANO,))]


def test_a_leading_tone_may_fall_chromatically_to_the_next_seventh() -> None:
    # V7/ii–V7/V: C♯ becomes C, the seventh of D7 (K–P ch. 17: a chain of dominants).
    chain = ('C#5 G4 E4 A2', 'C5 F#4 D4 D3')
    found = run('V7/ii V7/V', *chain)
    assert errors(found) == [], [v.message for v in found]


def test_the_seventh_of_v7_of_v_may_wait_in_the_cadential_six_four() -> None:
    held = ('C5 A4 F#4 D3', 'C5 G4 E4 G3')
    assert errors(run('V7/V Cad64', *held)) == []


# Mode mixture ------------------------------------------------------------------------------


def test_doubling_a_borrowed_lowered_tone_is_a_warning() -> None:
    found = run('iv', 'Ab4 C4 Ab3 F3')
    assert kinds(found) == {(Rule.WRONG_DOUBLING, Severity.WARNING)}
    # The root of ♭VI is doubled as any root-position root is.
    assert run('bVI', 'Ab4 Eb4 C4 Ab2') == []


def test_a_lowered_tone_that_rises_is_a_warning() -> None:
    # ♭VI–IV: A♭ rises to A♮ and E♭ to F instead of falling (A–S ch. 22).
    found = run('bVI IV', 'C5 Ab4 Eb4 Ab2', 'C5 A4 F4 F2')
    assert errors(found) == []
    rising = [v for v in found if v.rule is Rule.CHROMATIC_TONE]
    assert {v.voices for v in rising} == {(ALTO,), (TENOR,)}
    assert all(v.severity is Severity.WARNING for v in rising)


# The Neapolitan ---------------------------------------------------------------------------


def test_the_neapolitan_root_falls() -> None:
    good = ('Db5 Ab4 F4 F3', 'B4 G4 D4 G3')
    found = run('N6 V', *good, key=c)
    assert errors(found) == []
    # The D♮ of V in the tenor against the D♭ of the soprano: a cross relation.
    assert kinds(found) == {(Rule.CROSS_RELATION, Severity.WARNING)}
    rising = ('Db5 Ab4 F4 F3', 'D5 G4 B3 G3')  # ♭2̂ rises to ♮2̂
    found = errors(run('N6 V', *rising, key=c))
    assert [(v.rule, v.voices) for v in found] == [(Rule.CHROMATIC_TONE, (SOPRANO,))]


def test_doubling_the_neapolitan_root_is_a_warning() -> None:
    found = run('N6', 'Db5 Ab4 Db4 F3', key=c)
    assert kinds(found) == {(Rule.WRONG_DOUBLING, Severity.WARNING)}


# Augmented sixths -------------------------------------------------------------------------


def test_the_augmented_sixth_expands_to_the_octave() -> None:
    good = ('C5 F#4 C4 Ab2', 'B4 G4 D4 G2')
    assert errors(run('It+6 V', *good, key=c)) == []
    bad = ('C5 F#4 C4 Ab2', 'B4 D4 G3 G2')  # F♯ falls to D
    found = errors(run('It+6 V', *bad, key=c))
    assert [(v.rule, v.voices) for v in found] == [(Rule.AUGMENTED_SIXTH, (ALTO,))]


def test_the_notes_of_the_augmented_sixth_are_not_doubled() -> None:
    found = errors(run('It+6', 'C5 Ab4 F#4 Ab2', key=c))
    assert [(v.rule, v.voices) for v in found] == [(Rule.WRONG_DOUBLING, (ALTO, BASS))]
    # The Italian sixth doubles the tonic.
    assert errors(run('It+6', 'C5 F#4 C4 Ab2', key=c)) == []


def test_augmented_sixth_chords_are_complete() -> None:
    found = errors(run('Fr+6', 'C5 F#4 C4 Ab2', key=c))  # no D: an Italian sixth
    assert [v.rule for v in found] == [Rule.INCOMPLETE_CHORD]


def test_german_sixth_to_dominant_gives_parallel_fifths() -> None:
    # K–P ch. 23: A♭–E♭ to G–D; the cure is Ger+6–Cad6/4–V.
    fifths = ('C5 F#4 Eb4 Ab2', 'B4 G4 D4 G2')
    found = errors(run('Ger+6 V', *fifths, key=c))
    assert [(v.rule, v.voices) for v in found] == [(Rule.PARALLEL_FIFTHS, (TENOR, BASS))]
    six_four = ('C5 F#4 Eb4 Ab2', 'C5 G4 Eb4 G2')
    assert errors(run('Ger+6 Cad64', *six_four, key=c)) == []


def test_german_sixth_in_major_rises_to_the_third_of_the_six_four() -> None:
    # Spelled with ♭3̂ or with ♯2̂, the inner note rises to E♮ (K–P ch. 23).
    assert errors(run('Ger+6 Cad64', 'C5 F#4 Eb4 Ab2', 'C5 G4 E4 G2')) == []
    assert errors(run('Ger+6(#2) Cad64', 'C5 F#4 D#4 Ab2', 'C5 G4 E4 G2')) == []
    # D♯ in the tenor falls to C instead of rising to E: in an inner voice a warning
    # (besides the augmented second it makes).
    found = run('Ger+6(#2) Cad64', 'C5 F#4 D#4 Ab2', 'E5 G4 C4 G2')
    assert (Rule.CHROMATIC_TONE, Severity.WARNING) in kinds(found)
    assert [v.rule for v in errors(found)] == [Rule.AUGMENTED_SECOND]


def test_an_augmented_sixth_respelled_as_v7_is_not_held_to_the_octave() -> None:
    # C: Ger+6 = D♭: V7, resolving to D♭ (an enharmonic modulation).
    db = Key.parse('Db')
    found = check(
        chords('Eb5 Gb4 C4 Ab2', 'Db5 F4 Db4 Db3'),
        Context(C, chords_of(['V7', 'I'], db), keys=(db, db)),
    )
    assert errors(found) == []


# Cross relations and sequences ------------------------------------------------------------


def test_a_cross_relation_is_a_warning_unless_one_voice_makes_the_step() -> None:
    # ii–V/V6: F in the soprano, then F♯ in the bass (K–P ch. 16).
    found = run('ii V6/V', 'F5 A4 D4 D3', 'D5 A4 D4 F#3')
    assert kinds(found) == {(Rule.CROSS_RELATION, Severity.WARNING)}
    assert found[0].voices == (SOPRANO, BASS)
    # IV–V6/5/V: the bass itself moves from F to F♯.
    assert run('IV V65/V', 'C5 A4 F4 F3', 'C5 A4 D4 F#3') == []


def test_the_bass_may_fall_from_the_leading_tone_in_a_descending_five_six() -> None:
    found = run('V6 vi', 'D5 G4 D4 B2', 'C5 A4 E4 A2')
    assert kinds(found) == {(Rule.LEADING_TONE, Severity.WARNING)}


# The voicer -------------------------------------------------------------------------------

TONICS = ('C', 'G', 'F', 'Bb', 'D', 'Eb', 'a', 'e', 'd', 'g', 'c', 'b')


@pytest.mark.parametrize('tonic', TONICS)
def test_the_neapolitan_sixth_doubles_its_bass(tonic: str) -> None:
    key = Key.parse(tonic)
    tonic_numeral = 'I' if tonic[0].isupper() else 'i'
    harmony = [tonic_numeral, 'N6', 'V', tonic_numeral]
    for seed in range(3):
        voicing = realize(harmony, key, random.Random(seed))[1]
        names = [p.name for p in voicing]
        assert names.count(voicing[BASS].name) == 2, voicing


@pytest.mark.parametrize('tonic', TONICS)
def test_augmented_sixths_are_complete_and_the_italian_doubles_the_tonic(tonic: str) -> None:
    key = Key.parse(tonic)
    tonic_numeral = 'I' if tonic[0].isupper() else 'i'
    for kind in ('It+6', 'Fr+6', 'Ger+6'):
        follow = ['Cad64', 'V'] if kind == 'Ger+6' else ['V']
        harmony = [tonic_numeral, kind, *follow, tonic_numeral]
        chord = chords_of([kind], key)[0]
        for seed in range(2):
            voicing = realize(harmony, key, random.Random(seed))[1]
            names = [p.name for p in voicing]
            assert set(names) == set(chord.names())
            if kind == 'It+6':
                assert names.count(key.tonic) == 2


@pytest.mark.parametrize('tonic', TONICS)
def test_the_voicer_does_not_double_chromatic_tones(tonic: str) -> None:
    key = Key.parse(tonic)
    major = tonic[0].isupper()
    i = 'I' if major else 'i'
    progressions = [[i, 'V65/V', 'V', i], [i, 'viio7/V', 'V', i], [i, 'V/V', 'V', i]]
    if major:
        progressions += [[i, 'iv6', 'V', i], [i, 'iiø65', 'V', i]]
    for harmony in progressions:
        for seed in range(2):
            result = realize(harmony, key, random.Random(seed))
            for voicing, chord in zip(result, chords_of(harmony, key), strict=True):
                names = [p.name for p in voicing]
                for name in chord.names():
                    if alteration(name, key) != 0:
                        assert names.count(name) == 1, (harmony, voicing)
