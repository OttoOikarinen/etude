# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Helpers of the harmony ear exercises (cadences and progressions by ear).

Voicings come from :func:`etude.checkers.realize.realize`, the project's only
four-part voicer, and figures and keys from :mod:`.harmony`. What is left
here is specific to hearing a phrase: how it is played (instrument, tempo,
chords slightly detached), the settings that choose them, the note values of a
phrase, and the soprano constraints of a cadence.

A question keeps its key and numerals in :attr:`Question.details` (``key``,
``numerals``), so grading reads them back instead of analysing the voicing.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import replace
from fractions import Fraction
from functools import lru_cache
from gettext import gettext as _

from ...audio.spec import Instrument, PlaybackSpec
from ...checkers.realize import RealisationError, Voicing, realize
from ...core import Duration, NoteValue, PitchName
from ...core.roman import RomanNumeral
from ...core.scale import Key, Mode
from ...notation.spec import SystemSpec
from ..base import ChoiceSetting, IntSetting, Option, Setting
from .harmony import keys_within, limit_setting, modes_setting, roman_label, satb_figure
from .harmony import progression_playback as block_chords

_INSTRUMENTS = {
    'piano': Instrument.PIANO,
    'organ': Instrument.ORGAN,
    'strings': Instrument.STRINGS,
    'choir': Instrument.CHOIR,
}
_ATTEMPTS = 8


# Numerals --------------------------------------------------------------------------------


def parse_numerals(text: str) -> tuple[RomanNumeral, ...]:
    """``'I-IV-V7-I'`` → numerals (the ASCII form :class:`RomanNumeral` prints)."""
    return tuple(RomanNumeral.parse(t) for t in text.split('-'))


def numerals_text(numerals: Sequence[RomanNumeral]) -> str:
    """Inverse of :func:`parse_numerals`."""
    return '-'.join(str(n) for n in numerals)


def progression_label(numerals: Sequence[RomanNumeral]) -> str:
    """``'I–IV–V7–I'``, ``'i–ii°6–V–i'``, with :func:`.harmony.roman_label`."""
    return '–'.join(roman_label(n) for n in numerals)


# Voicing -----------------------------------------------------------------------------------


VARIANTS = 6
"""Different correct voicings a key and progression are played in. A question draws
one; the realisations are cached, so generating many questions stays fast."""


def voice(
    key: Key,
    numerals: Sequence[RomanNumeral],
    rng: random.Random,
    *,
    soprano_last: Sequence[PitchName] = (),
    falling_bass: bool = False,
) -> tuple[Voicing, ...]:
    """A correct SATB realisation, one of :data:`VARIANTS`.

    With ``soprano_last`` the soprano ends on one of those notes. With
    ``falling_bass`` the bass of the last two chords falls by a semitone (the
    Phrygian cadence; :func:`realize` does not promise it, so the phrase is voiced
    again until it does). Raises :class:`RealisationError`.
    """
    variant = rng.randrange(VARIANTS)
    return _voiced(key, numerals_text(numerals), variant, tuple(soprano_last), falling_bass)


def falls_by_semitone(voicings: Sequence[Voicing]) -> bool:
    """The bass of the last two chords falls by a semitone (♭6 to 5)."""
    return voicings[-2][3].midi - voicings[-1][3].midi == 1


@lru_cache(maxsize=4096)
def _voiced(
    key: Key,
    text: str,
    variant: int,
    soprano_last: tuple[PitchName, ...],
    falling_bass: bool,
) -> tuple[Voicing, ...]:
    numerals = list(parse_numerals(text))
    rng = random.Random(variant)
    tops: list[PitchName | None] = list(soprano_last) or [None]
    rng.shuffle(tops)
    voicings: tuple[Voicing, ...] = ()
    for _attempt in range(_ATTEMPTS):
        failure: RealisationError | None = None
        for top in tops:
            soprano = None if top is None else [*([None] * (len(numerals) - 1)), top]
            try:
                voicings = realize(numerals, key, rng, soprano=soprano)
                break
            except RealisationError as error:
                failure = error
        else:
            assert failure is not None
            raise failure
        if not falling_bass or falls_by_semitone(voicings):
            break
    return voicings


# Rhythm, figures and sound -------------------------------------------------------------------


def lengths(count: int) -> tuple[Fraction, ...]:
    """Every chord one beat, the last two."""
    return (*(Fraction(1),) * (count - 1), Fraction(2))


def durations(count: int) -> tuple[Duration, ...]:
    return (*(Duration(NoteValue.QUARTER),) * (count - 1), Duration(NoteValue.HALF))


def phrase_figure(
    key: Key,
    voicings: Sequence[Voicing],
    *,
    labels: Sequence[str | None] = (),
    highlight: Sequence[int] = (),
) -> SystemSpec:
    """The phrase as a chorale on a grand staff, with an optional Roman numeral under
    each chord."""
    return satb_figure(
        voicings,
        key.signature,
        durations=durations(len(voicings)),
        labels=labels,
        highlight=highlight,
        final_bar=True,
    )


def phrase_playback(
    voicings: Sequence[Voicing], *, tempo: float, instrument: Instrument
) -> PlaybackSpec:
    """The chords as block chords, one beat each and the last two."""
    playback = block_chords(voicings, lengths(len(voicings)), tempo)
    return replace(playback, instrument=instrument)


# Settings ---------------------------------------------------------------------------------


def mode_setting(default: str = 'major') -> ChoiceSetting:
    """``mode``: major, minor or both, read with :func:`.harmony.modes_setting`."""
    return ChoiceSetting(
        'mode',
        _('Keys'),
        (
            Option('major', _('Major')),
            Option('minor', _('Minor')),
            Option('both', _('Major and minor')),
        ),
        default,
    )


def harmony_settings(*, tempo: int = 80) -> tuple[Setting, ...]:
    """``max-accidentals``, ``tempo`` and ``instrument`` of a played progression."""
    return (
        IntSetting(
            'max-accidentals',
            _('Key signatures'),
            4,
            0,
            6,
            subtitle=_('Keys with up to this many sharps or flats'),
        ),
        IntSetting('tempo', _('Tempo'), tempo, 50, 120, subtitle=_('Chords per minute')),
        ChoiceSetting(
            'instrument',
            _('Instrument'),
            (
                Option('piano', _('Piano')),
                Option('organ', _('Organ')),
                Option('strings', _('Strings')),
                Option('choir', _('Choir')),
                Option('varied', _('Varied')),
            ),
            'piano',
            subtitle=_('Varied timbres help you hear the harmony, not the instrument'),
        ),
    )


def modes(settings: Mapping[str, object]) -> tuple[Mode, ...]:
    return modes_setting(settings)


def pick_key(mode: Mode, settings: Mapping[str, object], rng: random.Random) -> Key:
    return rng.choice(keys_within(min(6, limit_setting(settings, 4)), (mode,)))


def pick_instrument(settings: Mapping[str, object], rng: random.Random) -> Instrument:
    choice = str(settings.get('instrument', 'piano'))
    if choice == 'varied':
        return rng.choice(tuple(_INSTRUMENTS.values()))
    return _INSTRUMENTS.get(choice, Instrument.PIANO)


def tempo_of(settings: Mapping[str, object], default: int = 80) -> float:
    value = settings.get('tempo', default)
    return float(max(50, min(120, value if isinstance(value, int) else default)))


def describe_keys(settings: Mapping[str, object]) -> str:
    chosen = modes(settings)
    if len(chosen) == 2:
        return _('Major and minor keys')
    return _('Minor keys') if chosen[0] is Mode.MINOR else _('Major keys')
