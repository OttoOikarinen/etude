# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fux's own two-voice solutions in *Gradus ad Parnassum* (1725), figures 5–88.

The music is in the public domain. The notes follow Mark Gotham's encoding
(github.com/MarkGotham/species, CC0), including his corrections of figures 6, 12,
15 and 33. Counterpoint tokens are ``pitch/value``: ``w`` whole, ``h`` half, ``q``
quarter, ``e`` eighth, ``r`` a rest, and ``~`` ties the note to the next one.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Example:
    figure: str
    species: int
    final: str
    above: bool
    """The counterpoint is above the cantus firmus."""
    counterpoint: str
    cantus: str


EXAMPLES = (
    Example(
        '5',
        1,
        'D',
        True,
        ('A4/w A4/w G4/w A4/w B4/w C5/w C5/w B4/w D5/w C#5/w D5/w'),
        'D4 F4 E4 D4 G4 F4 A4 G4 F4 E4 D4',
    ),
    Example(
        '6',
        1,
        'D',
        False,
        ('D3/w D3/w A3/w F3/w E3/w D3/w F3/w C4/w D4/w C#4/w D4/w'),
        'D4 F4 E4 D4 G4 F4 A4 G4 F4 E4 D4',
    ),
    Example(
        '11',
        1,
        'E',
        True,
        ('B4/w C5/w F4/w G4/w A4/w C5/w B4/w E5/w D5/w E5/w'),
        'E4 C4 D4 C4 A3 A4 G4 E4 F4 E4',
    ),
    Example(
        '12',
        1,
        'E',
        False,
        ('E3/w A3/w D3/w E3/w F3/w F3/w C4/w C4/w D4/w E4/w'),
        'E4 C4 D4 C4 A3 A4 G4 E4 F4 E4',
    ),
    Example(
        '13',
        1,
        'F',
        True,
        ('F4/w E4/w C4/w F4/w F4/w G4/w A4/w G4/w C4/w F4/w E4/w F4/w'),
        'F3 G3 A3 F3 D3 E3 F3 C4 A3 F3 G3 F3',
    ),
    Example(
        '14',
        1,
        'F',
        False,
        ('F3/w E3/w F3/w A3/w Bb3/w G3/w A3/w E3/w F3/w D3/w E3/w F3/w'),
        'F3 G3 A3 F3 D3 E3 F3 C4 A3 F3 G3 F3',
    ),
    Example(
        '15',
        1,
        'G',
        True,
        ('G4/w E4/w D4/w G4/w G4/w G4/w A4/w B4/w G4/w C5/w A4/w G4/w F#4/w G4/w'),
        'G3 C4 B3 G3 C4 E4 D4 G4 E4 C4 D4 B3 A3 G3',
    ),
    Example(
        '21',
        1,
        'G',
        False,
        ('G3/w A3/w G3/w E3/w E3/w C3/w G3/w B3/w C4/w A3/w F#3/w G3/w F#3/w G3/w'),
        'G3 C4 B3 G3 C4 E4 D4 G4 E4 C4 D4 B3 A3 G3',
    ),
    Example(
        '22',
        1,
        'A',
        True,
        ('A4/w E4/w G4/w F4/w E4/w C5/w A4/w B4/w B4/w A4/w G#4/w A4/w'),
        'A3 C4 B3 D4 C4 E4 F4 E4 D4 C4 B3 A3',
    ),
    Example(
        '23',
        1,
        'A',
        False,
        ('A3/w A3/w G3/w F3/w E3/w E3/w D3/w C3/w G3/w A3/w G#3/w A3/w'),
        'A3 C4 B3 D4 C4 E4 F4 E4 D4 C4 B3 A3',
    ),
    Example(
        '33',
        2,
        'D',
        True,
        (
            'A4/h D5/h A4/h B4/h C5/h G4/h A4/h D5/h B4/h C5/h D5/h A4/h C5/h D5/h E5/h B4/h '
            'D5/h A4/h B4/h C#5/h D5/w'
        ),
        'D4 F4 E4 D4 G4 F4 A4 G4 F4 E4 D4',
    ),
    Example(
        '35',
        2,
        'D',
        False,
        (
            'r/h D3/h D4/h A3/h C4/h A3/h B3/h A3/h G3/h B3/h D4/h E4/h F4/h C4/h E4/h B3/h '
            'D4/h D3/h A3/h C#4/h D4/w'
        ),
        'D4 F4 E4 D4 G4 F4 A4 G4 F4 E4 D4',
    ),
    Example(
        '36',
        2,
        'E',
        True,
        (
            'r/h B4/h C5/h B4/h A4/h B4/h C5/h G4/h A4/h B4/h C5/h A4/h B4/h D5/h E5/h D5/h '
            'C5/h D5/h E5/w'
        ),
        'E4 C4 D4 C4 A3 A4 G4 E4 F4 E4',
    ),
    Example(
        '37',
        2,
        'E',
        False,
        (
            'r/h E3/h A3/h G3/h F3/h D3/h E3/h C3/h F3/h C4/h F4/h D4/h E4/h D4/h C4/h B3/h '
            'A3/h D4/h E4/w'
        ),
        'E4 C4 D4 C4 A3 A4 G4 E4 F4 E4',
    ),
    Example(
        '38',
        2,
        'F',
        True,
        (
            'r/h F4/h E4/h D4/h C4/h Bb3/h A3/h G3/h F3/h A3/h C4/h Bb3/h A3/h A4/h G4/h E4/h '
            'F4/h G4/h A4/h F4/h D4/h E4/h F4/w'
        ),
        'F3 G3 A3 F3 D3 E3 F3 C4 A3 F3 G3 F3',
    ),
    Example(
        '39',
        2,
        'F',
        False,
        (
            'r/h F3/h E3/h C3/h F3/h E3/h D3/h C3/h Bb2/h Bb3/h G3/h C4/h A3/h F3/h E3/h C3/h '
            'F3/h F2/h A2/h D3/h C3/h E3/h F3/w'
        ),
        'F3 G3 A3 F3 D3 E3 F3 C4 A3 F3 G3 F3',
    ),
    Example(
        '40',
        2,
        'G',
        True,
        (
            'r/h G4/h E4/h F4/h G4/h A4/h B4/h A4/h G4/h C5/h B4/h C5/h D5/h C5/h B4/h A4/h '
            'G4/h F4/h E4/h C5/h B4/h A4/h G4/h D4/h E4/h F#4/h G4/w'
        ),
        'G3 C4 B3 G3 C4 E4 D4 G4 E4 C4 D4 B3 A3 G3',
    ),
    Example(
        '41',
        2,
        'G',
        False,
        (
            'r/h G3/h E3/h F3/h G3/h F3/h E3/h D3/h C3/h E3/h C3/h C4/h B3/h A3/h G3/h B3/h '
            'C4/h B3/h A3/h G3/h F#3/h D3/h G3/h B2/h D3/h F#3/h G3/w'
        ),
        'G3 C4 B3 G3 C4 E4 D4 G4 E4 C4 D4 B3 A3 G3',
    ),
    Example(
        '42',
        2,
        'A',
        True,
        (
            'r/h A4/h E4/h F4/h G4/h D4/h E4/h E5/h C5/h B4/h A4/h F4/h G4/h B4/h D5/h A4/h '
            'C5/h E4/h F#4/h G#4/h A4/w'
        ),
        'A3 C4 B3 C4 E4 F4 E4 D4 C4 B3 A3',
    ),
    Example(
        '43',
        2,
        'A',
        False,
        (
            'r/h A2/h A3/h E3/h G3/h E3/h D3/h F3/h A3/h B3/h C4/h C3/h D3/h A2/h C3/h E3/h '
            'F3/h G3/h A3/h A2/h E3/h G#3/h A3/w'
        ),
        'A3 C4 B3 D4 C4 E4 F4 E4 D4 C4 B3 A3',
    ),
    Example(
        '44',
        2,
        'C',
        True,
        (
            'r/h G4/h C5/h B4/h A4/h D5/h B4/h A4/h G4/h B4/h C5/h D5/h E5/h D5/h C5/h B4/h '
            'A4/h B4/h C5/h G4/h A4/h B4/h C5/w'
        ),
        'C4 E4 F4 G4 E4 A4 G4 E4 F4 E4 D4 C4',
    ),
    Example(
        '45',
        2,
        'C',
        False,
        (
            'r/h C3/h C4/h B3/h A3/h D4/h B3/h G3/h C4/h B3/h A3/h C4/h E4/h D4/h C4/h A3/h '
            'D4/h A3/h C4/h C3/h G3/h B3/h C4/w'
        ),
        'C4 E4 F4 G4 E4 A4 G4 E4 F4 E4 D4 C4',
    ),
    Example(
        '55',
        3,
        'D',
        True,
        (
            'D4/q E4/q F4/q G4/q A4/q B4/q C5/q D5/q E5/q D5/q B4/q C5/q D5/q C5/q Bb4/q A4/q '
            'Bb4/q C5/q D5/q E5/q F5/q F4/q A4/q B4/q C5/q A4/q Bb4/q C5/q Bb4/q A4/q G4/q '
            'Bb4/q A4/q D4/q E4/q F4/q G4/q A4/q B4/q C#5/q D5/w'
        ),
        'D4 F4 E4 D4 G4 F4 A4 G4 F4 E4 D4',
    ),
    Example(
        '56',
        3,
        'D',
        False,
        (
            'D3/q E3/q F3/q G3/q A3/q D3/q A3/q B3/q C4/q B3/q G3/q A3/q B3/q A3/q G3/q F3/q '
            'E3/q E4/q B3/q C4/q D4/q A3/q D3/q E3/q F3/q G3/q A3/q B3/q C4/q D4/q E4/q C4/q '
            'D4/q A3/q D3/q D4/q C#4/q A3/q B3/q C#4/q D4/w'
        ),
        'D4 F4 E4 D4 G4 F4 A4 G4 F4 E4 D4',
    ),
    Example(
        '57',
        3,
        'E',
        True,
        (
            'B4/q G4/q A4/q B4/q C5/q B4/q A4/q G4/q F4/q G4/q A4/q B4/q C5/q E4/q F4/q G4/q '
            'A4/q C5/q E5/q D5/q C5/q B4/q A4/q C5/q B4/q D5/q B4/q A4/q G4/q B4/q C5/q B4/q '
            'A4/q B4/q C5/q D5/q E5/w'
        ),
        'E4 C4 D4 C4 A3 A4 G4 E4 F4 E4',
    ),
    Example(
        '58',
        3,
        'E',
        False,
        (
            'E3/q F3/q G3/q E3/q A3/q G3/q F3/q E3/q D3/q E3/q F3/q G3/q A3/q E3/q A3/q G3/q '
            'F3/q E3/q D3/q E3/q F3/q G3/q A3/q B3/q C4/q D4/q E4/q D4/q C4/q C3/q C4/q B3/q '
            'A3/q D4/q A3/q D4/q E4/w'
        ),
        'E4 C4 D4 C4 A3 A4 G4 E4 F4 E4',
    ),
    Example(
        '59',
        3,
        'F',
        True,
        (
            'F4/q E4/q D4/q C4/q B3/q D4/q G4/q F4/q E4/q D4/q C4/q Bb3/q A3/q C4/q D4/q E4/q '
            'F4/q D4/q E4/q F4/q G4/q E4/q F4/q G4/q A4/q G4/q F4/q A4/q G4/q F4/q E4/q D4/q '
            'C4/q E4/q C4/q E4/q F4/q E4/q D4/q C4/q Bb3/q C4/q D4/q E4/q F4/w'
        ),
        'F3 G3 A3 F3 D3 E3 F3 C4 A3 F3 G3 F3',
    ),
    Example(
        '60',
        3,
        'F',
        False,
        (
            'F2/q F3/q E3/q D3/q E3/q C3/q D3/q E3/q F3/q E3/q D3/q C3/q D3/q C3/q Bb2/q A2/q '
            'Bb2/q F3/q Bb3/q A3/q G3/q C3/q C4/q Bb3/q A3/q G3/q F3/q D3/q E3/q C3/q D3/q '
            'E3/q F3/q E3/q D3/q C3/q D3/q E3/q F3/q D3/q E3/q C3/q D3/q E3/q F3/w'
        ),
        'F3 G3 A3 F3 D3 E3 F3 C4 A3 F3 G3 F3',
    ),
    Example(
        '73',
        4,
        'D',
        True,
        (
            'r/h A4/h~ A4/h D5/h~ D5/h C5/h~ C5/h Bb4/h~ Bb4/h G4/h A4/h C5/h~ C5/h F5/h~ '
            'F5/h E5/h~ E5/h D5/h~ D5/h C#5/h D5/w'
        ),
        'D4 F4 E4 D4 G4 F4 A4 G4 F4 E4 D4',
    ),
    Example(
        '74',
        4,
        'D',
        False,
        (
            'r/h D3/h~ D3/h D4/h~ D4/h C4/h~ C4/h B3/h~ B3/h E4/h~ E4/h D4/h~ D4/h F4/h~ F4/h '
            'E4/h~ E4/h D4/h~ D4/h C#4/h D4/w'
        ),
        'D4 F4 E4 D4 G4 F4 A4 G4 F4 E4 D4',
    ),
    Example(
        '75',
        4,
        'E',
        True,
        (
            'r/h E5/h~ E5/h C5/h~ C5/h B4/h C5/h E4/h~ E4/h F4/h~ F4/h C5/h~ C5/h B4/h~ B4/h '
            'E5/h~ E5/h D5/h E5/w'
        ),
        'E4 C4 D4 C4 A3 A4 G4 E4 F4 E4',
    ),
    Example(
        '76',
        4,
        'E',
        False,
        (
            'r/h E3/h~ E3/h A3/h~ A3/h G3/h~ G3/h F3/h~ F3/h D3/h~ D3/h D4/h~ D4/h C4/h~ C4/h '
            'E4/h~ E4/h D4/h E4/w'
        ),
        'E4 C4 D4 C4 A3 A4 G4 E4 F4 E4',
    ),
    Example(
        '77',
        4,
        'F',
        True,
        (
            'r/h F4/h~ F4/h E4/h~ E4/h C4/h~ C4/h F4/h~ F4/h A4/h~ A4/h G4/h~ G4/h F4/h~ F4/h '
            'E4/h~ E4/h A4/h~ A4/h F4/h~ F4/h E4/h F4/w'
        ),
        'F3 G3 A3 F3 D3 E3 F3 C4 A3 F3 G3 F3',
    ),
    Example(
        '78',
        4,
        'F',
        False,
        (
            'r/h F3/h~ F3/h E3/h~ E3/h D3/h~ D3/h Bb2/h~ Bb2/h G2/h~ G2/h G3/h~ G3/h F3/h~ '
            'F3/h E3/h~ E3/h D3/h~ D3/h F3/h~ F3/h E3/h F3/w'
        ),
        'F3 G3 A3 F3 D3 E3 F3 C4 A3 F3 G3 F3',
    ),
    Example(
        '82',
        5,
        'D',
        True,
        (
            'r/h A4/h~ A4/q D4/q E4/q F4/q G4/q F4/q E4/q G4/q F4/q D4/q D5/h~ D5/q C5/q '
            'Bb4/q G4/q A4/q B4/q C5/h~ C5/h F5/h~ F5/q E5/e D5/e E5/h~ E5/q A4/q D5/h~ D5/h '
            'C#5/h D5/w'
        ),
        'D4 F4 E4 D4 G4 F4 A4 G4 F4 E4 D4',
    ),
    Example(
        '83',
        5,
        'D',
        False,
        (
            'r/h D4/h~ D4/h A3/q B3/q C4/q G3/q C4/h~ C4/q B3/e A3/e B3/q A3/q G3/q A3/q B3/q '
            'C4/q D4/q A3/q D4/h~ D4/q E4/q F4/h~ F4/q E4/e D4/e E4/h~ E4/q A3/q D4/h~ D4/h '
            'C#4/h D4/w'
        ),
        'D4 F4 E4 D4 G4 F4 A4 G4 F4 E4 D4',
    ),
    Example(
        '84a',
        5,
        'E',
        True,
        (
            'r/h E5/h~ E5/q D5/q C5/q B4/q A4/q G4/q F4/q D4/q E4/q G4/q C5/h~ C5/q B4/q A4/q '
            'G4/q F4/h C5/h~ C5/q B4/e A4/e B4/q A4/q G4/q E4/q E5/h~ E5/h D5/h E5/w'
        ),
        'E4 C4 D4 C4 A3 A4 G4 E4 F4 E4',
    ),
    Example(
        '84b',
        5,
        'E',
        False,
        (
            'r/h E3/h A3/q B3/q C4/h~ C4/q B3/e A3/e B3/q G3/q A3/h E3/h F3/q D3/q F3/h~ F3/q '
            'G3/q A3/q B3/q C4/q B3/q C4/h~ C4/q D4/q E4/h~ E4/h D4/h E4/w'
        ),
        'E4 C4 D4 C4 A3 A4 G4 E4 F4 E4',
    ),
    Example(
        '85a',
        5,
        'F',
        True,
        (
            'r/h F4/h~ F4/h E4/q D4/q C4/q A3/q C4/h~ C4/q A3/q D4/h~ D4/q C4/q Bb3/q A3/q '
            'G3/h C4/q Bb3/q A3/h A4/h~ A4/h G4/h A4/q G4/q F4/q E4/q D4/q C4/q F4/h~ F4/h '
            'E4/h F4/w'
        ),
        'F3 G3 A3 F3 D3 E3 F3 C4 A3 F3 G3 F3',
    ),
    Example(
        '85b',
        5,
        'F',
        False,
        (
            'r/h F3/h~ F3/q E3/e D3/e C3/q Bb2/q A2/q G2/q F2/h~ F2/q A2/q Bb2/h~ Bb2/q C3/q '
            'D3/h~ D3/h C3/q Bb2/q A2/h F3/h E3/h F3/h~ F3/q E3/q D3/h~ D3/q E3/q F3/h~ F3/h '
            'E3/h F3/w'
        ),
        'F3 G3 A3 F3 D3 E3 F3 C4 A3 F3 G3 F3',
    ),
    Example(
        '86a',
        5,
        'G',
        True,
        (
            'r/h G4/h~ G4/q F4/q E4/q D4/e C4/e D4/h G4/q A4/q B4/q C5/q D5/q B4/q E5/q D5/q '
            'C5/h~ C5/q B4/q A4/q G4/q A4/q B4/e C5/e D5/q C5/q B4/q G4/q B4/h~ B4/q A4/q '
            'G4/h~ G4/q F4/q E4/q G4/q F#4/q G4/q A4/h~ A4/q G4/q G4/h~ G4/h F#4/h G4/w'
        ),
        'G3 C4 B3 G3 C4 E4 D4 G4 E4 C4 D4 B3 A3 G3',
    ),
    Example(
        '86b',
        5,
        'G',
        False,
        (
            'r/h G3/h E3/h A3/h~ A3/h G3/q F3/q E3/q C3/q E3/h~ E3/h A3/h~ A3/q B3/q C4/h~ '
            'C4/h B3/q A3/q B3/h E4/q D4/q C4/q B3/q A3/h~ A3/q B3/q C4/h~ C4/h B3/q A3/q '
            'G3/q D3/q G3/h~ G3/h F#3/h G3/w'
        ),
        'G3 C4 B3 G3 C4 E4 D4 G4 E4 C4 D4 B3 A3 G3',
    ),
    Example(
        '87a',
        5,
        'A',
        True,
        (
            'r/h A4/h~ A4/h G4/q A4/q B4/q G4/q B4/h~ B4/h A4/q B4/q C5/q G4/q C5/h~ C5/q '
            'B4/e A4/e B4/q C5/q D5/q A4/q D5/h~ D5/q C5/q C5/h~ C5/q B4/e A4/e B4/h~ B4/q '
            'E4/q A4/h~ A4/h G#4/h A4/w'
        ),
        'A3 C4 B3 D4 C4 E4 F4 E4 D4 C4 B3 A3',
    ),
    Example(
        '87b',
        5,
        'A',
        False,
        (
            'r/h A3/h~ A3/q G3/q E3/q F3/q G3/q D3/q G3/h~ G3/q A3/q B3/h~ B3/h A3/h~ A3/q '
            'B3/q C4/q B3/q A3/h D4/h~ D4/q G3/q C4/h~ C4/q B3/e A3/e B3/h~ B3/q E3/q A3/h~ '
            'A3/h G#3/h A3/w'
        ),
        'A3 C4 B3 D4 C4 E4 F4 E4 D4 C4 B3 A3',
    ),
    Example(
        '88a',
        5,
        'C',
        True,
        (
            'r/h C5/h~ C5/h B4/h A4/q B4/q C5/q D5/q E5/h D5/q C5/q B4/q A4/q G4/h A4/h D5/h~ '
            'D5/q G4/q C5/h~ C5/h B4/h C5/w'
        ),
        'C4 D4 F4 E4 G4 F4 E4 D4 C4',
    ),
    Example(
        '88b',
        5,
        'C',
        False,
        (
            'r/h C4/h~ C4/h B3/h A3/h D4/h~ D4/q C4/e B3/e C4/h~ C4/q D4/q E4/h~ E4/q A3/q '
            'D4/h~ D4/q C4/q C4/h~ C4/h B3/h C4/w'
        ),
        'C4 D4 F4 E4 G4 F4 E4 D4 C4',
    ),
)
