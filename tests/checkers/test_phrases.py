# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Chromatic phrases, modulations and sequences: correct, and what they claim to be."""

from __future__ import annotations

import random
from itertools import pairwise

import pytest

from etude.checkers.phrases import (
    CHROMATIC_CHORDS,
    CLOSELY_RELATED,
    COMMON_TONE,
    SEQUENCES,
    ChromaticChord,
    ChromaticFamily,
    Phrase,
    SequenceKind,
    Technique,
    bass_moves,
    chromatic_chord,
    chromatic_phrase,
    enharmonic_keys,
    key_relation,
    modulation,
    modulation_targets,
    neapolitan_key,
    pivot_is_marked,
    pivots,
    related_key,
    sequence,
)
from etude.checkers.voice_leading import check, errors
from etude.core import ChordKind, Interval, Key, Mode, PitchName, RomanNumeral

MAJOR = ('C', 'G', 'F', 'Bb', 'A', 'Eb')
MINOR = ('a', 'e', 'd', 'c', 'b', 'g')
P5 = Interval.parse('P5')


def assert_correct(phrase: Phrase) -> None:
    found = errors(check(phrase.voicings, phrase.context()))
    assert found == [], [v.message for v in found]
    for voicing, chord in zip(phrase.voicings, phrase.chords, strict=True):
        assert {p.name for p in voicing} <= set(chord.names())
        assert voicing[3].name == chord.bass


def _id(chord: ChromaticChord) -> str:
    return f'{chord.mode.value}-{chord.id}'


# Keys ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('home', 'other', 'relation'),
    [
        ('C', 'G', 'V'),
        ('C', 'F', 'IV'),
        ('C', 'a', 'vi'),
        ('C', 'd', 'ii'),
        ('C', 'e', 'iii'),
        ('c', 'Eb', 'III'),
        ('c', 'g', 'v'),
        ('c', 'f', 'iv'),
        ('c', 'Ab', 'VI'),
        ('c', 'Bb', 'VII'),
        ('C', 'Ab', 'bVI'),
        ('C', 'E', 'III'),
        ('C', 'Eb', 'bIII'),
        ('C', 'Db', 'bII'),
        ('c', 'f#', '#iv'),
        ('Eb', 'f#', '#ii'),
    ],
)
def test_key_relations(home: str, other: str, relation: str) -> None:
    assert key_relation(Key.parse(home), Key.parse(other)) == relation
    assert related_key(Key.parse(home), relation) == Key.parse(other)


def test_closely_related_keys_are_one_accidental_away() -> None:
    for mode, tonic in ((Mode.MAJOR, 'C'), (Mode.MINOR, 'A')):
        home = Key(PitchName.parse(tonic), mode)
        for relation in CLOSELY_RELATED[mode]:
            new = related_key(home, relation)
            assert abs(new.signature.fifths - home.signature.fifths) <= 1


def test_enharmonic_keys_of_the_diminished_seventh() -> None:
    # B–D–F–A♭ is also D–F–A♭–C♭ (e♭), E♯–G♯–B–D (f♯) and G♯–B–D–F (a).
    assert enharmonic_keys(Key.parse('C')) == tuple(Key.parse(k) for k in ('eb', 'f#', 'a'))
    for home in ('C', 'g', 'E', 'bb'):
        key = Key.parse(home)
        ours = RomanNumeral.parse('viio7').realize(key)
        for other in enharmonic_keys(key):
            theirs = RomanNumeral.parse('viio7').realize(other)
            assert {n.pitch_class for n in theirs.names()} == {n.pitch_class for n in ours.names()}


def test_the_german_sixth_sounds_like_v7_of_the_neapolitan_key() -> None:
    for home in ('C', 'c', 'A', 'f'):
        key = Key.parse(home)
        german = RomanNumeral.parse('Ger+6').realize(key)
        dominant = RomanNumeral.parse('V7').realize(neapolitan_key(key))
        assert german.is_enharmonic(dominant)


def test_pivot_chords_are_diatonic_in_both_keys() -> None:
    assert ('vi', 'ii') in pivots(Key.parse('C'), Key.parse('G'))
    assert ('I', 'IV') in pivots(Key.parse('C'), Key.parse('G'))
    assert ('ii', 'iv') in pivots(Key.parse('C'), Key.parse('a'))
    assert ('iv', 'ii') in pivots(Key.parse('c'), Key.parse('Eb'))
    # The relative major has no note its minor key lacks.
    assert not pivot_is_marked(Key.parse('c'), Key.parse('Eb'))
    assert pivot_is_marked(Key.parse('C'), Key.parse('F'))


def test_bass_moves_without_augmented_leaps() -> None:
    def chord(text: str, key: str) -> object:
        return RomanNumeral.parse(text).realize(Key.parse(key))

    assert bass_moves(chord('I', 'C'), chord('V', 'C'))  # type: ignore[arg-type]
    assert bass_moves(chord('It+6', 'c'), chord('V', 'c'))  # type: ignore[arg-type]
    # C to D♯: an augmented second, or a diminished seventh the other way.
    assert not bass_moves(chord('VI', 'e'), chord('viio7', 'e'))  # type: ignore[arg-type]


# Chromatic chords ----------------------------------------------------------------------


@pytest.mark.parametrize('chord', CHROMATIC_CHORDS, ids=_id)
def test_every_chromatic_chord_stands_in_a_correct_phrase(chord: ChromaticChord) -> None:
    tonics = MAJOR if chord.mode is Mode.MAJOR else MINOR
    for tonic in tonics:
        key = Key.parse(tonic)
        for seed in range(3):
            phrase = chromatic_phrase(chord, key, random.Random(seed))
            assert_correct(phrase)
            focus = phrase.focus
            assert focus is not None
            numeral = phrase.readings[focus][0].numeral
            assert numeral.degree == chord.numeral.degree
            assert numeral.secondary == chord.numeral.secondary
            assert numeral.inversion in chord.inversions
            following = phrase.chords[focus + 1]
            if chord.family is ChromaticFamily.SECONDARY:
                target = chord.numeral.secondary
                assert target is not None
                # The chord it tonicizes follows, or the cadential six-four before V.
                expected = target.realize(key).root
                assert following.root == expected or (
                    str(target) == 'V' and following.inversion == 2
                )
            elif chord.family is ChromaticFamily.AUGMENTED_SIXTH:
                assert key.degree(5) in following.names()
            elif chord.family is ChromaticFamily.NEAPOLITAN:
                # To V, to the cadential six-four, or through vii°7/V (K–P ch. 22).
                assert numeral.inversion == 1
                assert key.degree(5) in following.names() or following == (
                    RomanNumeral.parse('viio7/V').realize(key)
                )


def test_the_german_sixth_goes_through_the_cadential_six_four() -> None:
    for tonic in ('C', 'c', 'E', 'f#'):
        for seed in range(4):
            phrase = chromatic_phrase('Ger+6', Key.parse(tonic), random.Random(seed))
            assert phrase.focus is not None
            following = phrase.readings[phrase.focus + 1][0].numeral
            assert following.cadential


def test_in_major_the_german_sixth_is_spelled_both_ways() -> None:
    spellings = set()
    for tonic in MAJOR:
        for seed in range(8):
            phrase = chromatic_phrase('Ger+6', Key.parse(tonic), random.Random(seed))
            assert phrase.focus is not None
            spellings.add(phrase.readings[phrase.focus][0].numeral.quality.value)
    assert spellings == {'german-sixth', 'doubly-augmented-fourth'}


def test_chromatic_phrases_are_deterministic() -> None:
    chord = chromatic_chord('viio7/V', Mode.MAJOR)
    first = chromatic_phrase(chord, Key.parse('D'), random.Random(5))
    assert chromatic_phrase(chord, Key.parse('D'), random.Random(5)) == first
    with pytest.raises(ValueError, match='major'):
        chromatic_phrase(chord, Key.parse('d'), random.Random(0))


# Modulations ----------------------------------------------------------------------------


def _targets(home: Key, technique: Technique) -> tuple[str, ...]:
    return modulation_targets(home, technique)


@pytest.mark.parametrize('technique', list(Technique), ids=lambda t: t.value)
def test_every_modulation_is_correct_and_ends_in_its_key(technique: Technique) -> None:
    for tonic in (*MAJOR[:4], *MINOR[:4]):
        home = Key.parse(tonic)
        for relation in _targets(home, technique):
            for seed in range(2):
                phrase = modulation(home, technique, relation, random.Random(seed))
                assert_correct(phrase)
                new = phrase.new_key
                assert new is not None
                assert key_relation(home, new) == relation
                last = phrase.readings[-1][-1]
                assert last.key == new
                assert last.chord.root == new.tonic
                # An authentic cadence confirms the new key: V(7)–I in root position.
                dominant = phrase.readings[-2][-1]
                assert dominant.key == new
                assert (dominant.numeral.degree, dominant.numeral.inversion) == (5, 0)
                assert last.numeral.inversion == 0
                assert phrase.readings[0][0].key == home
                assert phrase.readings[0][0].chord.root == home.tonic
                if technique is Technique.DIRECT:
                    assert len(phrase.breaks) == 1
                if technique is Technique.COMMON_TONE:
                    junction = phrase.breaks[0]
                    held = phrase.voicings[junction][0]
                    assert phrase.voicings[junction + 1][0] == held
                    assert held.name in phrase.chords[junction + 1].names()


def test_a_pivot_chord_is_read_in_both_keys_and_followed_by_the_new_key() -> None:
    for tonic in ('C', 'G', 'Bb', 'a', 'e', 'c'):
        home = Key.parse(tonic)
        for relation in CLOSELY_RELATED[home.mode]:
            for seed in range(3):
                phrase = modulation(home, Technique.PIVOT, relation, random.Random(seed))
                pivot = phrase.pivot
                assert pivot is not None
                old, new = phrase.readings[pivot]
                assert old.key == home
                assert new.key == phrase.new_key
                assert old.chord == new.chord
                if pivot_is_marked(home, new.key):
                    # The first chord with a note the home key lacks comes right after.
                    following = phrase.chords[pivot + 1]
                    pool = set(home.scale.names()) | {home.leading_tone}
                    assert not set(following.names()) <= pool
                    assert all(set(c.names()) <= pool for c in phrase.chords[:pivot])


def test_enharmonic_pivots_are_respelled() -> None:
    for tonic in ('C', 'c', 'G', 'f'):
        home = Key.parse(tonic)
        for technique in (Technique.ENHARMONIC_DIMINISHED, Technique.ENHARMONIC_GERMAN):
            for relation in _targets(home, technique):
                phrase = modulation(home, technique, relation, random.Random(1))
                assert phrase.pivot is not None
                old, new = phrase.readings[phrase.pivot]
                assert old.chord.is_enharmonic(new.chord)
                assert old.chord != new.chord
                if technique is Technique.ENHARMONIC_GERMAN:
                    assert old.numeral.quality.kind is ChordKind.AUGMENTED_SIXTH
                    assert str(new.numeral) == 'V7'


def test_common_tone_modulations_reach_the_chromatic_mediants() -> None:
    home = Key.parse('C')
    assert {str(related_key(home, r)) for r in COMMON_TONE} == {
        'Ab major',
        'A major',
        'Eb major',
        'E major',
    }
    with pytest.raises(ValueError, match='common-tone'):
        modulation(Key.parse('c'), Technique.COMMON_TONE, 'VI', random.Random(0))


def test_pivot_and_direct_modulations_need_a_closely_related_key() -> None:
    with pytest.raises(ValueError, match='closely related'):
        modulation(Key.parse('C'), Technique.PIVOT, 'bVI', random.Random(0))


# Sequences -----------------------------------------------------------------------------


@pytest.mark.parametrize('kind', list(SequenceKind), ids=lambda k: k.value)
def test_sequences_are_correct_and_keep_their_pattern(kind: SequenceKind) -> None:
    for mode, texts in SEQUENCES[kind].items():
        tonics = MAJOR if mode is Mode.MAJOR else MINOR
        for tonic in tonics:
            key = Key.parse(tonic)
            phrase = sequence(kind, key, random.Random(0))
            assert_correct(phrase)
            assert [str(r[0].numeral) for r in phrase.readings] == list(texts)
            roots = [c.root for c in phrase.chords]
            bass = [v[3] for v in phrase.voicings]
            if kind in (SequenceKind.DESCENDING_FIFTHS, SequenceKind.SECONDARY_DOMINANTS):
                # Every root a fifth above the next, until the final tonic.
                for before, after in pairwise(roots[1:-1]):
                    assert before.transpose(P5, down=True).letter == after.letter
            if kind is SequenceKind.SECONDARY_DOMINANTS:
                assert all(c.quality.value == 'dominant-seventh' for c in phrase.chords[1:-1])
            if kind is SequenceKind.DESCENDING_FIVE_SIX:
                steps = [b.diatonic_index - a.diatonic_index for a, b in pairwise(bass[:6])]
                assert all(s in (-1, 6) for s in steps), bass  # down a step, by any octave
            if kind is SequenceKind.ASCENDING_FIVE_SIX:
                letters = [p.letter for p in bass[:5]]
                assert letters[0] == letters[1]
                assert letters[2] == letters[3]
                assert (letters[2] - letters[0]) % 7 == 1


def test_sequences_in_minor_exist_only_where_the_books_write_them() -> None:
    with pytest.raises(ValueError, match='minor'):
        sequence(SequenceKind.ASCENDING_FIVE_SIX, Key.parse('a'), random.Random(0))
