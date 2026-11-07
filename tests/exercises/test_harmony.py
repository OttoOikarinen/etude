# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from etude.core import Chord, ChordQuality, Duration, NoteValue, Pitch, PitchName
from etude.core.roman import RomanNumeral
from etude.core.scale import Mode
from etude.exercises.families.harmony import (
    chord_of,
    figure_text,
    keys_within,
    roman_label,
    satb_durations,
    satb_figure,
    satb_voices,
)


def test_figure_text_writes_figures_with_slashes() -> None:
    assert figure_text('53') == ''
    assert figure_text('6') == '6'
    assert figure_text('64') == '6/4'
    assert figure_text('65') == '6/5'
    assert figure_text('43') == '4/3'
    assert figure_text('42') == '4/2'


@pytest.mark.parametrize(
    ('text', 'label'),
    [
        ('V65', 'V6/5'),
        ('viio7', 'vii°7'),
        ('viiø43', 'viiø4/3'),
        ('IV', 'IV'),
        ('I64', 'I6/4'),
        ('IM7', 'IM7'),
        ('V7/V', 'V7/V'),
        ('V65/V', 'V6/5/V'),
        ('viio42/ii', 'vii°4/2/ii'),
        ('bII6', 'N6'),
        ('N6', 'N6'),
        ('bII', 'N'),
        ('bVI', '♭VI'),
        ('Ger+6', 'Ger+6'),
        ('Ger+6(#2)', 'Ger+6'),
        ('It+6/V', 'It+6/V'),
        ('viiø7/V', 'viiø7/V'),
    ],
)
def test_roman_label(text: str, label: str) -> None:
    assert roman_label(RomanNumeral.parse(text)) == label


def test_keys_within_counts_signatures() -> None:
    assert [str(k) for k in keys_within(0, (Mode.MAJOR, Mode.MINOR))] == ['C major', 'a minor']
    keys = keys_within(2, (Mode.MAJOR,))
    assert {str(k.tonic) for k in keys} == {'Bb', 'F', 'C', 'G', 'D'}
    assert len(keys_within(7, (Mode.MAJOR, Mode.MINOR))) == 30


def test_chord_of_reads_complete_and_incomplete_chords() -> None:
    def pitches(text: str) -> list[Pitch]:
        return [Pitch.parse(p) for p in text.split()]

    assert chord_of(pitches('E3 G3 C4')) == Chord(PitchName.parse('C'), ChordQuality.MAJOR, 1)
    # V7 without its fifth, and a tonic with a tripled root and no fifth.
    assert chord_of(pitches('G2 G3 B3 F4')) == Chord(
        PitchName.parse('G'), ChordQuality.DOMINANT_SEVENTH
    )
    assert chord_of(pitches('C3 C4 E4 C5')) == Chord(PitchName.parse('C'), ChordQuality.MAJOR)


def test_satb_figure_round_trips() -> None:
    voices = ((Pitch.parse('C5'), Pitch.parse('G4'), Pitch.parse('E4'), Pitch.parse('C3')),)
    for durations in ((), (Duration(NoteValue.HALF),)):
        figure = satb_figure(voices, None, durations=durations, labels=('I',), highlight=(0,))
        assert satb_voices(figure) == list(voices)
        assert satb_durations(figure) == durations
