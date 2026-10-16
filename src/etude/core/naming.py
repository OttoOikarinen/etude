# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Localized names for notes, keys, intervals, chords, scales and degrees.

Learners choose a :class:`NamingConvention` for note names:

* ``ENGLISH``: C D E F G A B with ♯ and ♭ (C♯, B♭).
* ``GERMAN_NORDIC``: C D E F G A H, where B is B♭; accidentals are
  suffixes (Cis, Des, Es, As, Fis, Heses), as taught in Germany and the
  Nordic countries. Every name is a translatable string, so a translation
  can adapt it (Swedish ``Ciss``; Dutch, which keeps B for B♮ and writes
  ``Bes``).
* ``FIXED_DO``: Do Re Mi Fa Sol La Si with ♯ and ♭ (Do♯, Si♭). The
  syllables are translatable (French ``Ré``).

Every user-visible phrase is a whole translatable string, never assembled
from words, because word order and agreement differ between languages
("minor sixth" is "pieni seksti" in Finnish and "sixte mineure" in
French). Templates with placeholders let translators reorder: key names
offer ``{tonic}`` and ``{tonic_lower}`` so that, for example, Finnish can
write ``Cis-duuri`` and ``cis-molli``.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from functools import wraps
from gettext import gettext as _
from gettext import pgettext

from .chord import Chord, ChordQuality
from .interval import Interval
from .pitch import Letter, PitchName
from .scale import DegreeFunction, Key, Mode, Scale, ScaleType


class NamingConvention(Enum):
    ENGLISH = 'english'
    GERMAN_NORDIC = 'german-nordic'
    FIXED_DO = 'fixed-do'


_default_convention = NamingConvention.ENGLISH


def _per_language[T](build: Callable[[], T]) -> Callable[[], T]:
    """Cache a table of translated names until the translation changes.

    Building a table translates every entry; caching it keeps generating
    and grading questions fast. The key is one translated probe string, so a
    different language (as in tests that switch catalogues) rebuilds it.
    """
    cache: dict[str, T] = {}

    @wraps(build)
    def wrapper() -> T:
        key = _('perfect unison')
        if key not in cache:
            cache.clear()
            cache[key] = build()
        return cache[key]

    return wrapper


def set_default_convention(convention: NamingConvention) -> None:
    """Set the convention used when a naming function is called without one.

    The application calls this from the ``note-naming`` setting, so exercises
    produce labels in the learner's convention without passing it around.
    """
    global _default_convention
    _default_convention = convention


def default_convention() -> NamingConvention:
    return _default_convention


_SYMBOLS = {-3: '♭𝄫', -2: '𝄫', -1: '♭', 0: '', 1: '♯', 2: '𝄪', 3: '♯𝄪'}


@_per_language
def _german_names() -> dict[tuple[Letter, int], str]:
    ctx = 'German/Nordic note name'
    C, D, E, F, G, A, B = Letter  # noqa: N806 - letter names
    return {
        (C, -2): pgettext(ctx, 'Ceses'),
        (C, -1): pgettext(ctx, 'Ces'),
        (C, 0): pgettext(ctx, 'C'),
        (C, 1): pgettext(ctx, 'Cis'),
        (C, 2): pgettext(ctx, 'Cisis'),
        (D, -2): pgettext(ctx, 'Deses'),
        (D, -1): pgettext(ctx, 'Des'),
        (D, 0): pgettext(ctx, 'D'),
        (D, 1): pgettext(ctx, 'Dis'),
        (D, 2): pgettext(ctx, 'Disis'),
        (E, -2): pgettext(ctx, 'Eses'),
        (E, -1): pgettext(ctx, 'Es'),
        (E, 0): pgettext(ctx, 'E'),
        (E, 1): pgettext(ctx, 'Eis'),
        (E, 2): pgettext(ctx, 'Eisis'),
        (F, -2): pgettext(ctx, 'Feses'),
        (F, -1): pgettext(ctx, 'Fes'),
        (F, 0): pgettext(ctx, 'F'),
        (F, 1): pgettext(ctx, 'Fis'),
        (F, 2): pgettext(ctx, 'Fisis'),
        (G, -2): pgettext(ctx, 'Geses'),
        (G, -1): pgettext(ctx, 'Ges'),
        (G, 0): pgettext(ctx, 'G'),
        (G, 1): pgettext(ctx, 'Gis'),
        (G, 2): pgettext(ctx, 'Gisis'),
        (A, -2): pgettext(ctx, 'Asas'),
        (A, -1): pgettext(ctx, 'As'),
        (A, 0): pgettext(ctx, 'A'),
        (A, 1): pgettext(ctx, 'Ais'),
        (A, 2): pgettext(ctx, 'Aisis'),
        # Translators: B double flat in German note names.
        (B, -2): pgettext(ctx, 'Heses'),
        # Translators: B flat in German note names (Dutch: Bes).
        (B, -1): pgettext(ctx, 'B'),
        # Translators: B natural in German note names (Dutch: B).
        (B, 0): pgettext(ctx, 'H'),
        (B, 1): pgettext(ctx, 'His'),
        (B, 2): pgettext(ctx, 'Hisis'),
    }


@_per_language
def _solfege_syllables() -> dict[Letter, str]:
    ctx = 'fixed-do syllable'
    return {
        Letter.C: pgettext(ctx, 'Do'),
        Letter.D: pgettext(ctx, 'Re'),
        Letter.E: pgettext(ctx, 'Mi'),
        Letter.F: pgettext(ctx, 'Fa'),
        Letter.G: pgettext(ctx, 'Sol'),
        Letter.A: pgettext(ctx, 'La'),
        Letter.B: pgettext(ctx, 'Si'),
    }


def pitch_name(name: PitchName, convention: NamingConvention | None = None) -> str:
    """Display name of a spelled pitch class: ``'C♯'``, ``'Cis'`` or ``'Do♯'``.

    German/Nordic names cover up to double sharps and flats; rarer triple
    alterations fall back to letters with accidental signs.
    """
    convention = convention or _default_convention
    if convention is NamingConvention.GERMAN_NORDIC:
        german = _german_names().get((name.letter, name.alter))
        if german is not None:
            return german
        return name.symbol
    if convention is NamingConvention.FIXED_DO:
        return _solfege_syllables()[name.letter] + _SYMBOLS[name.alter]
    return name.symbol


def key_name(key: Key, convention: NamingConvention | None = None) -> str:
    """Name of a key: ``'E major'``, ``'C♯ minor'``; in Finnish ``'cis-molli'``."""
    convention = convention or _default_convention
    if convention is NamingConvention.GERMAN_NORDIC:
        if key.mode is Mode.MAJOR:
            # Translators: a major key with German/Nordic note names. {tonic} is the
            # note name (Cis) and {tonic_lower} the same in lower case (cis), e.g. "Cis-duuri".
            template = pgettext('key name, German/Nordic notes', '{tonic} major')
        else:
            # Translators: a minor key with German/Nordic note names. {tonic} is the
            # note name (Cis) and {tonic_lower} the same in lower case (cis), e.g. "cis-molli".
            template = pgettext('key name, German/Nordic notes', '{tonic} minor')
    elif convention is NamingConvention.FIXED_DO:
        if key.mode is Mode.MAJOR:
            # Translators: a major key with fixed-do names; {tonic} is e.g. "Re♭".
            template = pgettext('key name, fixed-do notes', '{tonic} major')
        else:
            # Translators: a minor key with fixed-do names; {tonic} is e.g. "Do♯".
            template = pgettext('key name, fixed-do notes', '{tonic} minor')
    elif key.mode is Mode.MAJOR:
        # Translators: a major key with English note names; {tonic} is e.g. "E♭".
        template = pgettext('key name, English notes', '{tonic} major')
    else:
        # Translators: a minor key with English note names; {tonic} is e.g. "C♯".
        template = pgettext('key name, English notes', '{tonic} minor')
    tonic = pitch_name(key.tonic, convention)
    return template.format(tonic=tonic, tonic_lower=tonic.lower())


@_per_language
def _interval_names() -> dict[tuple[str, int], str]:
    return {
        ('P', 1): _('perfect unison'),
        ('A', 1): _('augmented unison'),
        ('AA', 1): _('doubly augmented unison'),
        ('dd', 2): _('doubly diminished second'),
        ('d', 2): _('diminished second'),
        ('m', 2): _('minor second'),
        ('M', 2): _('major second'),
        ('A', 2): _('augmented second'),
        ('AA', 2): _('doubly augmented second'),
        ('dd', 3): _('doubly diminished third'),
        ('d', 3): _('diminished third'),
        ('m', 3): _('minor third'),
        ('M', 3): _('major third'),
        ('A', 3): _('augmented third'),
        ('AA', 3): _('doubly augmented third'),
        ('dd', 4): _('doubly diminished fourth'),
        ('d', 4): _('diminished fourth'),
        ('P', 4): _('perfect fourth'),
        ('A', 4): _('augmented fourth'),
        ('AA', 4): _('doubly augmented fourth'),
        ('dd', 5): _('doubly diminished fifth'),
        ('d', 5): _('diminished fifth'),
        ('P', 5): _('perfect fifth'),
        ('A', 5): _('augmented fifth'),
        ('AA', 5): _('doubly augmented fifth'),
        ('dd', 6): _('doubly diminished sixth'),
        ('d', 6): _('diminished sixth'),
        ('m', 6): _('minor sixth'),
        ('M', 6): _('major sixth'),
        ('A', 6): _('augmented sixth'),
        ('AA', 6): _('doubly augmented sixth'),
        ('dd', 7): _('doubly diminished seventh'),
        ('d', 7): _('diminished seventh'),
        ('m', 7): _('minor seventh'),
        ('M', 7): _('major seventh'),
        ('A', 7): _('augmented seventh'),
        ('AA', 7): _('doubly augmented seventh'),
        ('dd', 8): _('doubly diminished octave'),
        ('d', 8): _('diminished octave'),
        ('P', 8): _('perfect octave'),
        ('A', 8): _('augmented octave'),
        ('AA', 8): _('doubly augmented octave'),
        ('dd', 9): _('doubly diminished ninth'),
        ('d', 9): _('diminished ninth'),
        ('m', 9): _('minor ninth'),
        ('M', 9): _('major ninth'),
        ('A', 9): _('augmented ninth'),
        ('AA', 9): _('doubly augmented ninth'),
        ('dd', 10): _('doubly diminished tenth'),
        ('d', 10): _('diminished tenth'),
        ('m', 10): _('minor tenth'),
        ('M', 10): _('major tenth'),
        ('A', 10): _('augmented tenth'),
        ('AA', 10): _('doubly augmented tenth'),
        ('dd', 11): _('doubly diminished eleventh'),
        ('d', 11): _('diminished eleventh'),
        ('P', 11): _('perfect eleventh'),
        ('A', 11): _('augmented eleventh'),
        ('AA', 11): _('doubly augmented eleventh'),
        ('dd', 12): _('doubly diminished twelfth'),
        ('d', 12): _('diminished twelfth'),
        ('P', 12): _('perfect twelfth'),
        ('A', 12): _('augmented twelfth'),
        ('AA', 12): _('doubly augmented twelfth'),
        ('dd', 13): _('doubly diminished thirteenth'),
        ('d', 13): _('diminished thirteenth'),
        ('m', 13): _('minor thirteenth'),
        ('M', 13): _('major thirteenth'),
        ('A', 13): _('augmented thirteenth'),
        ('AA', 13): _('doubly augmented thirteenth'),
        ('dd', 14): _('doubly diminished fourteenth'),
        ('d', 14): _('diminished fourteenth'),
        ('m', 14): _('minor fourteenth'),
        ('M', 14): _('major fourteenth'),
        ('A', 14): _('augmented fourteenth'),
        ('AA', 14): _('doubly augmented fourteenth'),
        ('dd', 15): _('doubly diminished fifteenth'),
        ('d', 15): _('diminished fifteenth'),
        ('P', 15): _('perfect fifteenth'),
        ('A', 15): _('augmented fifteenth'),
        ('AA', 15): _('doubly augmented fifteenth'),
    }


def interval_name(interval: Interval) -> str:
    """Full name of an interval up to two octaves: ``'minor sixth'``, ``'major tenth'``.

    Raises :class:`ValueError` beyond a fifteenth (double octave).
    """
    name = _interval_names().get((interval.quality.value, interval.number))
    if name is None:
        raise ValueError(f'no name for intervals wider than a fifteenth: {interval}')
    return name


def chord_quality_name(quality: ChordQuality) -> str:
    """Full name of a chord quality: ``'half-diminished seventh'``."""
    names = {
        ChordQuality.MAJOR: pgettext('chord quality', 'major triad'),
        ChordQuality.MINOR: pgettext('chord quality', 'minor triad'),
        ChordQuality.DIMINISHED: pgettext('chord quality', 'diminished triad'),
        ChordQuality.AUGMENTED: pgettext('chord quality', 'augmented triad'),
        ChordQuality.SUS2: pgettext('chord quality', 'suspended second chord'),
        ChordQuality.SUS4: pgettext('chord quality', 'suspended fourth chord'),
        ChordQuality.DOMINANT_SEVENTH: pgettext('chord quality', 'dominant seventh'),
        ChordQuality.MAJOR_SEVENTH: pgettext('chord quality', 'major seventh'),
        ChordQuality.MINOR_SEVENTH: pgettext('chord quality', 'minor seventh'),
        ChordQuality.HALF_DIMINISHED_SEVENTH: pgettext('chord quality', 'half-diminished seventh'),
        ChordQuality.DIMINISHED_SEVENTH: pgettext('chord quality', 'diminished seventh'),
        ChordQuality.MINOR_MAJOR_SEVENTH: pgettext('chord quality', 'minor-major seventh'),
        ChordQuality.AUGMENTED_MAJOR_SEVENTH: pgettext('chord quality', 'augmented major seventh'),
        ChordQuality.AUGMENTED_SEVENTH: pgettext('chord quality', 'augmented seventh'),
        ChordQuality.MAJOR_SIXTH: pgettext('chord quality', 'major sixth chord'),
        ChordQuality.MINOR_SIXTH: pgettext('chord quality', 'minor sixth chord'),
        ChordQuality.SIX_NINE: pgettext('chord quality', 'six-nine chord'),
        ChordQuality.MINOR_SIX_NINE: pgettext('chord quality', 'minor six-nine chord'),
        ChordQuality.ADD_NINE: pgettext('chord quality', 'added ninth chord'),
        ChordQuality.MINOR_ADD_NINE: pgettext('chord quality', 'minor added ninth chord'),
        ChordQuality.DOMINANT_SEVENTH_FLAT_FIVE: pgettext(
            'chord quality', 'dominant seventh flat five'
        ),
        ChordQuality.DOMINANT_SEVENTH_SUS4: pgettext(
            'chord quality', 'dominant seventh suspended fourth'
        ),
        ChordQuality.DOMINANT_NINTH: pgettext('chord quality', 'dominant ninth'),
        ChordQuality.MAJOR_NINTH: pgettext('chord quality', 'major ninth'),
        ChordQuality.MINOR_NINTH: pgettext('chord quality', 'minor ninth'),
        ChordQuality.MINOR_MAJOR_NINTH: pgettext('chord quality', 'minor-major ninth'),
        ChordQuality.DOMINANT_NINTH_SUS4: pgettext(
            'chord quality', 'dominant ninth suspended fourth'
        ),
        ChordQuality.DOMINANT_FLAT_NINTH: pgettext('chord quality', 'dominant seventh flat nine'),
        ChordQuality.DOMINANT_SHARP_NINTH: pgettext('chord quality', 'dominant seventh sharp nine'),
        ChordQuality.DOMINANT_FLAT_FIVE_FLAT_NINTH: pgettext(
            'chord quality', 'dominant seventh flat five flat nine'
        ),
        ChordQuality.DOMINANT_FLAT_FIVE_SHARP_NINTH: pgettext(
            'chord quality', 'dominant seventh flat five sharp nine'
        ),
        ChordQuality.DOMINANT_SHARP_FIVE_FLAT_NINTH: pgettext(
            'chord quality', 'dominant seventh sharp five flat nine'
        ),
        ChordQuality.DOMINANT_SHARP_FIVE_SHARP_NINTH: pgettext(
            'chord quality', 'dominant seventh sharp five sharp nine'
        ),
        ChordQuality.DOMINANT_ELEVENTH: pgettext('chord quality', 'dominant eleventh'),
        ChordQuality.MINOR_ELEVENTH: pgettext('chord quality', 'minor eleventh'),
        ChordQuality.DOMINANT_SHARP_ELEVENTH: pgettext(
            'chord quality', 'dominant seventh sharp eleven'
        ),
        ChordQuality.DOMINANT_NINTH_SHARP_ELEVENTH: pgettext(
            'chord quality', 'dominant ninth sharp eleven'
        ),
        ChordQuality.MAJOR_SEVENTH_SHARP_ELEVENTH: pgettext(
            'chord quality', 'major seventh sharp eleven'
        ),
        ChordQuality.MAJOR_NINTH_SHARP_ELEVENTH: pgettext(
            'chord quality', 'major ninth sharp eleven'
        ),
        ChordQuality.DOMINANT_THIRTEENTH: pgettext('chord quality', 'dominant thirteenth'),
        ChordQuality.MAJOR_THIRTEENTH: pgettext('chord quality', 'major thirteenth'),
        ChordQuality.MINOR_THIRTEENTH: pgettext('chord quality', 'minor thirteenth'),
        ChordQuality.DOMINANT_THIRTEENTH_FLAT_NINTH: pgettext(
            'chord quality', 'dominant thirteenth flat nine'
        ),
        ChordQuality.DOMINANT_THIRTEENTH_SHARP_ELEVENTH: pgettext(
            'chord quality', 'dominant thirteenth sharp eleven'
        ),
        ChordQuality.DOMINANT_FLAT_THIRTEENTH: pgettext(
            'chord quality', 'dominant seventh flat thirteen'
        ),
        ChordQuality.ALTERED: pgettext('chord quality', 'altered dominant'),
        ChordQuality.ITALIAN_SIXTH: pgettext('chord quality', 'Italian augmented sixth'),
        ChordQuality.FRENCH_SIXTH: pgettext('chord quality', 'French augmented sixth'),
        ChordQuality.GERMAN_SIXTH: pgettext('chord quality', 'German augmented sixth'),
    }
    return names[quality]


def chord_name(chord: Chord, convention: NamingConvention | None = None) -> str:
    """Root and quality, e.g. ``'F♯ half-diminished seventh'`` (inversion is not named)."""
    convention = convention or _default_convention
    # Translators: a chord name. {root} is a note name and {quality} a chord quality
    # such as "minor triad" or "dominant seventh"; reorder them as your language needs.
    template = pgettext('chord name', '{root} {quality}')
    return template.format(
        root=pitch_name(chord.root, convention), quality=chord_quality_name(chord.quality)
    )


def scale_type_name(scale_type: ScaleType) -> str:
    """Name of a scale or mode: ``'harmonic minor'``, ``'Dorian'``."""
    names = {
        ScaleType.MAJOR: pgettext('scale type', 'major'),
        ScaleType.NATURAL_MINOR: pgettext('scale type', 'natural minor'),
        ScaleType.HARMONIC_MINOR: pgettext('scale type', 'harmonic minor'),
        ScaleType.MELODIC_MINOR: pgettext('scale type', 'melodic minor'),
        ScaleType.IONIAN: pgettext('scale type', 'Ionian'),
        ScaleType.DORIAN: pgettext('scale type', 'Dorian'),
        ScaleType.PHRYGIAN: pgettext('scale type', 'Phrygian'),
        ScaleType.LYDIAN: pgettext('scale type', 'Lydian'),
        ScaleType.MIXOLYDIAN: pgettext('scale type', 'Mixolydian'),
        ScaleType.AEOLIAN: pgettext('scale type', 'Aeolian'),
        ScaleType.LOCRIAN: pgettext('scale type', 'Locrian'),
        ScaleType.MAJOR_PENTATONIC: pgettext('scale type', 'major pentatonic'),
        ScaleType.MINOR_PENTATONIC: pgettext('scale type', 'minor pentatonic'),
        ScaleType.BLUES: pgettext('scale type', 'blues'),
        ScaleType.WHOLE_TONE: pgettext('scale type', 'whole-tone'),
        ScaleType.CHROMATIC: pgettext('scale type', 'chromatic'),
        ScaleType.OCTATONIC_HALF_WHOLE: pgettext('scale type', 'octatonic (half-whole)'),
        ScaleType.OCTATONIC_WHOLE_HALF: pgettext('scale type', 'octatonic (whole-half)'),
    }
    return names[scale_type]


def scale_name(scale: Scale, convention: NamingConvention | None = None) -> str:
    """Tonic and scale type, e.g. ``'D Dorian'``."""
    convention = convention or _default_convention
    # Translators: a scale name. {tonic} is a note name and {scale} a scale type
    # such as "harmonic minor" or "Dorian"; reorder them as your language needs.
    template = pgettext('scale name', '{tonic} {scale}')
    return template.format(
        tonic=pitch_name(scale.tonic, convention), scale=scale_type_name(scale.type)
    )


def degree_name(function: DegreeFunction) -> str:
    """Name of a scale degree: ``'Supertonic'``, ``'Leading tone'``."""
    names = {
        DegreeFunction.TONIC: pgettext('scale degree', 'Tonic'),
        DegreeFunction.SUPERTONIC: pgettext('scale degree', 'Supertonic'),
        DegreeFunction.MEDIANT: pgettext('scale degree', 'Mediant'),
        DegreeFunction.SUBDOMINANT: pgettext('scale degree', 'Subdominant'),
        DegreeFunction.DOMINANT: pgettext('scale degree', 'Dominant'),
        DegreeFunction.SUBMEDIANT: pgettext('scale degree', 'Submediant'),
        DegreeFunction.LEADING_TONE: pgettext('scale degree', 'Leading tone'),
        DegreeFunction.SUBTONIC: pgettext('scale degree', 'Subtonic'),
    }
    return names[function]


def degree_short_name(function: DegreeFunction) -> str:
    """Abbreviated degree name for compact buttons: ``'Supert.'``, ``'Leading'``."""
    # Translators: these are abbreviated scale-degree names for narrow buttons.
    ctx = 'scale degree, abbreviated'
    names = {
        DegreeFunction.TONIC: pgettext(ctx, 'Tonic'),
        DegreeFunction.SUPERTONIC: pgettext(ctx, 'Supert.'),
        DegreeFunction.MEDIANT: pgettext(ctx, 'Mediant'),
        DegreeFunction.SUBDOMINANT: pgettext(ctx, 'Subdom.'),
        DegreeFunction.DOMINANT: pgettext(ctx, 'Dominant'),
        DegreeFunction.SUBMEDIANT: pgettext(ctx, 'Submed.'),
        DegreeFunction.LEADING_TONE: pgettext(ctx, 'Leading'),
        DegreeFunction.SUBTONIC: pgettext(ctx, 'Subtonic'),
    }
    return names[function]


# Languages whose music education uses German letter names with H (and
# translations adapt the details), and languages that name notes in solfège.
_GERMAN_NORDIC_LANGUAGES = frozenset(
    {'cs', 'da', 'de', 'et', 'fi', 'hu', 'is', 'nb', 'nl', 'nn', 'no', 'pl', 'sk', 'sl', 'sv'}
)
_FIXED_DO_LANGUAGES = frozenset(
    {'bg', 'ca', 'el', 'es', 'fr', 'gl', 'he', 'it', 'pt', 'ro', 'ru', 'tr', 'uk'}
)


def convention_for_locale(locale: str | None) -> NamingConvention:
    """Default convention for a POSIX or BCP 47 locale such as ``'fi_FI.UTF-8'`` or ``'pt-BR'``.

    Finnish, German, the Scandinavian languages, Dutch and several Central
    European languages get German/Nordic names; French, Italian, Spanish,
    Portuguese, Romanian and other solfège-naming languages get fixed do;
    everything else (including ``'C'`` and ``'POSIX'``) English.
    """
    if not locale:
        return NamingConvention.ENGLISH
    language = locale.split('.')[0].split('@')[0].replace('-', '_').split('_')[0].lower()
    if language in _GERMAN_NORDIC_LANGUAGES:
        return NamingConvention.GERMAN_NORDIC
    if language in _FIXED_DO_LANGUAGES:
        return NamingConvention.FIXED_DO
    return NamingConvention.ENGLISH
