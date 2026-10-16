# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Music theory domain model.

Pure Python with no GObject imports, so everything here can be tested
without a display. Higher layers (notation, audio, exercises) build on
these immutable value types.
"""

from .chord import Chord, ChordKind, ChordQuality
from .chord_symbol import ChordSymbol
from .figured_bass import Figure, FigureAccidental, FiguredBass
from .interval import Interval, Quality
from .key import KeySignature
from .pcset import PitchClassSet
from .pitch import Letter, Pitch, PitchName
from .rhythm import Duration, Meter, NoteValue, Tuplet
from .roman import RomanNumeral
from .scale import DegreeFunction, Key, Mode, Scale, ScaleType
from .tone_row import RowForm, RowLabelling, ToneRow

__all__ = [
    'Chord',
    'ChordKind',
    'ChordQuality',
    'ChordSymbol',
    'DegreeFunction',
    'Duration',
    'Figure',
    'FigureAccidental',
    'FiguredBass',
    'Interval',
    'Key',
    'KeySignature',
    'Letter',
    'Meter',
    'Mode',
    'NoteValue',
    'Pitch',
    'PitchClassSet',
    'PitchName',
    'Quality',
    'RomanNumeral',
    'RowForm',
    'RowLabelling',
    'Scale',
    'ScaleType',
    'ToneRow',
    'Tuplet',
]
