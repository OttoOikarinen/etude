# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest
from hypothesis import given
from hypothesis import strategies as st

from etude.core import Chord, ChordQuality, Key, Mode, PitchName, RomanNumeral

Q = ChordQuality


def realized(numeral: str, key: str) -> str:
    chord = RomanNumeral.parse(numeral).realize(Key.parse(key))
    return ' '.join(str(n) for n in chord.names_from_bass())


@pytest.mark.parametrize(
    ('numeral', 'key', 'expected'),
    [
        ('I', 'C', 'C E G'),
        ('ii6', 'C', 'F A D'),
        ('V65', 'C', 'B D F G'),
        ('viio7', 'C', 'B D F Ab'),
        ('viiø43', 'C', 'F A B D'),
        ('V7/V', 'C', 'D F# A C'),
        ('bII6', 'C', 'F Ab Db'),
        ('N6', 'c', 'F Ab Db'),
        ('It+6', 'C', 'Ab C F#'),
        ('Fr+6', 'c', 'Ab C D F#'),
        ('Ger+6', 'E', 'C E G A#'),
        ('Ger65', 'C', 'Ab C Eb F#'),
        ('Ger+6(#2)', 'C', 'Ab C D# F#'),
        ('Ger+6(♯2)/V', 'C', 'Eb G A# C#'),
        ('Fr43', 'C', 'Ab C D F#'),
        ('Cad64', 'C', 'G C E'),
        ('Cad64', 'f#', 'C# F# A'),
        ('bVI', 'C', 'Ab C Eb'),
        ('bVII', 'C', 'Bb D F'),
        ('iv', 'C', 'F Ab C'),
        ('VI', 'c', 'Ab C Eb'),
        ('VII', 'c', 'Bb D F'),
        ('viio7', 'c', 'B D F Ab'),
        ('V', 'c', 'G B D'),
        ('i', 'c', 'C Eb G'),
        ('IV', 'c', 'F A C'),
        ('V/ii', 'C', 'A C# E'),
        ('V/V/V', 'C', 'A C# E'),
        ('viio7/V', 'C', 'F# A C Eb'),
        ('V7/III', 'c', 'Bb D F Ab'),
        ('V42/IV', 'C', 'Bb C E G'),
        ('Ger+6/V', 'C', 'Eb G Bb C#'),
        ('IM7', 'F', 'F A C E'),
        ('IM65', 'F', 'A C E F'),
        ('III+', 'c', 'Eb G B'),
        ('iM7', 'c', 'C Eb G B'),
        ('V+7', 'C', 'G B D# F'),
        ('III+M7', 'c', 'Eb G B D'),
        ('#ivo7', 'C', 'F# A C Eb'),
        ('V2', 'C', 'F G B D'),
        ('V6/5', 'C', 'B D F G'),
        ('V6/4', 'C', 'D G B'),
        ('vii°7', 'C', 'B D F Ab'),
        ('vii/o7', 'C', 'B D F A'),
        ('viiø', 'C', 'B D F A'),
        ('♭VI', 'C', 'Ab C Eb'),
        ('V53', 'C', 'G B D'),
    ],
)
def test_realize(numeral: str, key: str, expected: str) -> None:
    assert realized(numeral, key) == expected


@pytest.mark.parametrize(
    ('text', 'canonical', 'symbol'),
    [
        ('V6/5', 'V65', 'V65'),
        ('vii°7', 'viio7', 'vii°7'),
        ('vii/o43', 'viiø43', 'viiø43'),
        ('N6', 'bII6', '♭II6'),
        ('It6', 'It+6', 'It+6'),
        ('Ger65/V', 'Ger+6/V', 'Ger+6/V'),
        ('Ger+6(#2)', 'Ger+6(#2)', 'Ger+6'),
        ('Cad6/4', 'Cad64', 'Cad64'),
        ('V2', 'V42', 'V42'),
        ('#iv°7/V', '#ivo7/V', '♯iv°7/V'),
        ('bbVII', 'bbVII', '♭♭VII'),
    ],
)
def test_format(text: str, canonical: str, symbol: str) -> None:
    numeral = RomanNumeral.parse(text)
    assert str(numeral) == canonical
    assert numeral.symbol == symbol
    assert RomanNumeral.parse(canonical) == numeral


@pytest.mark.parametrize(
    'text', ['', 'VIII', 'Vo', 'iiM', 'V9', 'IIø7', 'v+', 'V/I', 'V/viio', 'X7', 'V/V6', 'IM']
)
def test_parse_rejects(text: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 - several messages are valid here
        RomanNumeral.parse(text)


def test_validation() -> None:
    with pytest.raises(ValueError, match='1–7'):
        RomanNumeral(8, Q.MAJOR)
    with pytest.raises(ValueError, match='cannot show'):
        RomanNumeral(5, Q.DOMINANT_NINTH)
    with pytest.raises(ValueError, match='♭6'):
        RomanNumeral(6, Q.GERMAN_SIXTH)
    with pytest.raises(ValueError, match='only the German'):
        RomanNumeral.parse('It+6(#2)')
    with pytest.raises(ValueError, match='no inversion'):
        RomanNumeral(5, Q.MAJOR, 3)
    with pytest.raises(ValueError, match='I64'):
        RomanNumeral(5, Q.MAJOR, 2, cadential=True)


@pytest.mark.parametrize(
    ('key', 'root', 'quality', 'inversion', 'expected'),
    [
        ('C', 'D', Q.MAJOR, 0, 'V/V'),
        ('C', 'D', Q.DOMINANT_SEVENTH, 1, 'V65/V'),
        ('C', 'E', Q.MAJOR, 0, 'V/vi'),
        ('C', 'C', Q.DOMINANT_SEVENTH, 0, 'V7/IV'),
        ('C', 'C#', Q.DIMINISHED_SEVENTH, 0, 'viio7/ii'),
        ('C', 'F#', Q.HALF_DIMINISHED_SEVENTH, 2, 'viiø43/V'),
        ('C', 'Ab', Q.MAJOR, 0, 'bVI'),
        ('C', 'Bb', Q.MAJOR, 0, 'bVII'),
        ('C', 'Eb', Q.MAJOR, 0, 'bIII'),
        ('C', 'F', Q.MINOR, 0, 'iv'),
        ('C', 'D', Q.HALF_DIMINISHED_SEVENTH, 1, 'iiø65'),
        ('C', 'B', Q.DIMINISHED_SEVENTH, 0, 'viio7'),
        ('C', 'Db', Q.MAJOR, 1, 'bII6'),
        ('c', 'Db', Q.MAJOR, 1, 'bII6'),
        ('C', 'Ab', Q.ITALIAN_SIXTH, 0, 'It+6'),
        ('c', 'Ab', Q.GERMAN_SIXTH, 0, 'Ger+6'),
        ('C', 'Eb', Q.GERMAN_SIXTH, 0, 'Ger+6/V'),
        ('C', 'Ab', Q.DOUBLY_AUGMENTED_FOURTH, 0, 'Ger+6(#2)'),
        ('c', 'C', Q.MAJOR, 0, 'I'),
        ('c', 'F', Q.MAJOR, 0, 'IV'),
        ('c', 'Bb', Q.DOMINANT_SEVENTH, 0, 'VII7'),
        ('c', 'Eb', Q.DOMINANT_SEVENTH, 0, 'V7/VI'),
        ('c', 'D', Q.MAJOR, 0, 'V/V'),
        ('c', 'E', Q.MAJOR, 0, '#III'),
        ('C', 'Gb', Q.MAJOR, 0, 'bV'),
    ],
)
def test_analyze(key: str, root: str, quality: ChordQuality, inversion: int, expected: str) -> None:
    subject = Chord(PitchName.parse(root), quality, inversion)
    result = RomanNumeral.analyze(subject, Key.parse(key))
    assert str(result) == expected


def test_analyze_gives_up() -> None:
    key = Key.parse('C')
    assert RomanNumeral.analyze(Chord(PitchName.parse('C'), Q.DOMINANT_NINTH), key) is None
    assert RomanNumeral.analyze(Chord(PitchName.parse('Ab'), Q.GERMAN_SIXTH, 1), key) is None
    assert RomanNumeral.analyze(Chord(PitchName.parse('A##'), Q.MAJOR), key) is None
    assert str(RomanNumeral.analyze(Chord(PitchName.parse('A#'), Q.AUGMENTED), key)) == '#VI+'
    # The German sixth with ♯2̂ is a major-key spelling: in C minor E♭ is diatonic.
    sharp_two = Chord(PitchName.parse('Ab'), Q.DOUBLY_AUGMENTED_FOURTH)
    assert RomanNumeral.analyze(sharp_two, Key.parse('c')) is None


def test_tonicized_key() -> None:
    key = Key.parse('C')
    assert RomanNumeral.parse('V/ii').tonicized_key(key) == Key.parse('d')
    assert RomanNumeral.parse('V').tonicized_key(key) == key
    assert RomanNumeral.parse('V/V').figure == ''
    assert RomanNumeral.parse('V43').figure == '43'


def _diatonic_numerals() -> list[tuple[Mode, RomanNumeral]]:
    major = [
        'I',
        'ii',
        'iii',
        'IV',
        'V',
        'vi',
        'viio',
        'IM7',
        'ii7',
        'iii7',
        'IVM7',
        'V7',
        'vi7',
        'viiø7',
    ]
    minor = [
        'i',
        'iio',
        'III',
        'iv',
        'V',
        'VI',
        'VII',
        'viio',
        'i7',
        'iiø7',
        'IIIM7',
        'iv7',
        'V7',
        'VIM7',
        'VII7',
        'viio7',
    ]
    found = []
    for mode, labels in ((Mode.MAJOR, major), (Mode.MINOR, minor)):
        for label in labels:
            base = RomanNumeral.parse(label)
            for inversion in range(base.quality.size):
                found.append((mode, RomanNumeral(base.degree, base.quality, inversion)))
    return found


@given(st.sampled_from(_diatonic_numerals()), st.integers(-6, 6))
def test_analyze_inverts_realize_for_diatonic_chords(
    case: tuple[Mode, RomanNumeral], fifths: int
) -> None:
    mode, numeral = case
    tonic = PitchName.from_line_of_fifths(fifths + (3 if mode is Mode.MINOR else 0))
    key = Key(tonic, mode)
    assert RomanNumeral.analyze(numeral.realize(key), key) == numeral


@given(st.integers(-6, 6), st.sampled_from(list(Mode)), st.integers(1, 7))
def test_key_chords_are_their_numerals(fifths: int, mode: Mode, degree: int) -> None:
    key = Key(PitchName.from_line_of_fifths(fifths), mode)
    for chord in (key.triad(degree), key.seventh(degree)):
        numeral = RomanNumeral.analyze(chord, key)
        assert numeral is not None
        assert numeral.degree == degree
        assert numeral.alter == 0
        assert numeral.realize(key) == chord


_CHROMATIC = [
    'V/V',
    'V7/V',
    'viio7/V',
    'V/ii',
    'V7/IV',
    'viiø7/V',
    'bII6',
    'It+6',
    'Fr+6',
    'Ger+6',
    'bVI',
    'bIII',
    'iv',
]


@given(st.sampled_from(_CHROMATIC), st.integers(-5, 5))
def test_chromatic_round_trip_in_major(label: str, fifths: int) -> None:
    key = Key(PitchName.from_line_of_fifths(fifths), Mode.MAJOR)
    numeral = RomanNumeral.parse(label)
    assert RomanNumeral.analyze(numeral.realize(key), key) == numeral
