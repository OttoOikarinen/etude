# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from etude.core import (
    Chord,
    ChordQuality,
    DegreeFunction,
    Interval,
    Key,
    NamingConvention,
    PitchName,
    Quality,
    Scale,
    ScaleType,
    naming,
)
from etude.core.naming import (
    chord_name,
    chord_quality_name,
    convention_for_locale,
    degree_name,
    degree_short_name,
    interval_name,
    key_name,
    pitch_name,
    scale_name,
    scale_type_name,
)

EN, DE, DO = NamingConvention.ENGLISH, NamingConvention.GERMAN_NORDIC, NamingConvention.FIXED_DO


@pytest.mark.parametrize(
    ('name', 'english', 'german', 'solfege'),
    [
        ('C', 'C', 'C', 'Do'),
        ('C#', 'C♯', 'Cis', 'Do♯'),
        ('Db', 'D♭', 'Des', 'Re♭'),
        ('Eb', 'E♭', 'Es', 'Mi♭'),
        ('Ab', 'A♭', 'As', 'La♭'),
        ('F#', 'F♯', 'Fis', 'Fa♯'),
        ('B', 'B', 'H', 'Si'),
        ('Bb', 'B♭', 'B', 'Si♭'),
        ('Bbb', 'B𝄫', 'Heses', 'Si𝄫'),
        ('Fx', 'F𝄪', 'Fisis', 'Fa𝄪'),
        ('Abb', 'A𝄫', 'Asas', 'La𝄫'),
        ('G', 'G', 'G', 'Sol'),
        ('C###', 'C♯𝄪', 'C♯𝄪', 'Do♯𝄪'),
    ],
)
def test_pitch_names(name: str, english: str, german: str, solfege: str) -> None:
    spelled = PitchName.parse(name)
    assert pitch_name(spelled) == english
    assert pitch_name(spelled, DE) == german
    assert pitch_name(spelled, DO) == solfege


def test_every_double_alteration_has_a_german_name() -> None:
    from etude.core import Letter

    names = {
        pitch_name(PitchName(letter, alter), DE) for letter in Letter for alter in range(-2, 3)
    }
    assert len(names) == 35
    assert not any('♯' in n or '♭' in n for n in names)


@pytest.mark.parametrize(
    ('key', 'convention', 'expected'),
    [
        ('E', EN, 'E major'),
        ('c#', EN, 'C♯ minor'),
        ('c#', DE, 'Cis minor'),
        ('Bb', DE, 'B major'),
        ('f#', DO, 'Fa♯ minor'),
    ],
)
def test_key_names(key: str, convention: NamingConvention, expected: str) -> None:
    assert key_name(Key.parse(key), convention) == expected


def test_key_name_can_lowercase_the_minor_tonic(monkeypatch: pytest.MonkeyPatch) -> None:
    finnish = {
        ('key name, German/Nordic notes', '{tonic} minor'): '{tonic_lower}-molli',
        ('key name, German/Nordic notes', '{tonic} major'): '{tonic}-duuri',
    }
    monkeypatch.setattr(naming, 'pgettext', lambda ctx, msg: finnish.get((ctx, msg), msg))
    assert key_name(Key.parse('c#'), DE) == 'cis-molli'
    assert key_name(Key.parse('Eb'), DE) == 'Es-duuri'


@pytest.mark.parametrize(
    ('interval', 'expected'),
    [
        ('P1', 'perfect unison'),
        ('A1', 'augmented unison'),
        ('m2', 'minor second'),
        ('A4', 'augmented fourth'),
        ('d5', 'diminished fifth'),
        ('m6', 'minor sixth'),
        ('d7', 'diminished seventh'),
        ('P8', 'perfect octave'),
        ('M9', 'major ninth'),
        ('M10', 'major tenth'),
        ('P11', 'perfect eleventh'),
        ('P12', 'perfect twelfth'),
        ('m13', 'minor thirteenth'),
        ('M14', 'major fourteenth'),
        ('P15', 'perfect fifteenth'),
        ('AA5', 'doubly augmented fifth'),
        ('dd3', 'doubly diminished third'),
    ],
)
def test_interval_names(interval: str, expected: str) -> None:
    assert interval_name(Interval.parse(interval)) == expected


def test_every_interval_up_to_fifteen_is_named() -> None:
    count = 0
    for number in range(1, 16):
        for quality in Quality:
            try:
                interval = Interval(quality, number)
            except ValueError:
                continue
            assert interval_name(interval)
            count += 1
    assert count == 81
    with pytest.raises(ValueError, match='fifteenth'):
        interval_name(Interval.parse('M16'))


def test_every_chord_quality_is_named() -> None:
    names = {chord_quality_name(q) for q in ChordQuality}
    assert len(names) == len(ChordQuality)
    assert chord_quality_name(ChordQuality.HALF_DIMINISHED_SEVENTH) == 'half-diminished seventh'
    c_sharp = Chord(PitchName.parse('C#'), ChordQuality.MINOR)
    assert chord_name(c_sharp) == 'C♯ minor triad'
    assert chord_name(c_sharp, DE) == 'Cis minor triad'


def test_every_scale_type_is_named() -> None:
    assert len({scale_type_name(t) for t in ScaleType}) == len(ScaleType)
    dorian = Scale(PitchName.parse('D'), ScaleType.DORIAN)
    assert scale_name(dorian) == 'D Dorian'
    assert scale_name(Scale(PitchName.parse('Bb'), ScaleType.MAJOR), DE) == 'B major'


def test_degree_names() -> None:
    assert [degree_name(f) for f in DegreeFunction] == [
        'Tonic',
        'Supertonic',
        'Mediant',
        'Subdominant',
        'Dominant',
        'Submediant',
        'Leading tone',
        'Subtonic',
    ]
    assert [degree_short_name(f) for f in DegreeFunction] == [
        'Tonic',
        'Supert.',
        'Mediant',
        'Subdom.',
        'Dominant',
        'Submed.',
        'Leading',
        'Subtonic',
    ]


@pytest.mark.parametrize(
    ('locale', 'expected'),
    [
        ('fi', DE),
        ('fi_FI.UTF-8', DE),
        ('de_DE@euro', DE),
        ('sv-SE', DE),
        ('nb_NO', DE),
        ('da', DE),
        ('nl_NL', DE),
        ('fr_FR.UTF-8', DO),
        ('it', DO),
        ('es_MX', DO),
        ('pt-BR', DO),
        ('ro', DO),
        ('en_US.UTF-8', EN),
        ('ja_JP', EN),
        ('C', EN),
        ('POSIX', EN),
        ('', EN),
        (None, EN),
    ],
)
def test_convention_for_locale(locale: str | None, expected: NamingConvention) -> None:
    assert convention_for_locale(locale) is expected
