# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Two-voice species counterpoint (species 1–5) in the modal style of Fux and Jeppesen.

The checker takes a cantus firmus (one whole note per bar), a counterpoint
above or below it, the species and the mode, and reports every rule the
counterpoint breaks with the notes involved and a translated explanation, as
:mod:`etude.checkers.voice_leading` does for four-part harmony. The sources
are Fux, *The Study of Counterpoint* (Mann's translation of *Gradus ad
Parnassum*, 1725) and Jeppesen, *Counterpoint: The Polyphonic Vocal Style of
the Sixteenth Century*, cross-checked with Salzer–Schachter, *Counterpoint in
Composition*. Every two-voice solution in Fux's own figures 5–88 passes
without an error (``tests/checkers/test_counterpoint.py``), which settles
several of the choices below.

The counterpoint's rhythm is a :class:`Rhythm`: a rest and the length of each
note, bars being one whole note (one cantus note) long. A note longer than
what is left of its bar is tied over the barline (fourth species). Species
1–4 have a standard rhythm (:func:`species_rhythm`); the fifth species is
written in a rhythm chosen per exercise.

Decisions (severity in brackets; an *error* is what both Fux and Jeppesen
forbid and makes an answer wrong, a *warning* is a matter of style, mentioned
but not penalised):

* **Consonances** are the unison, thirds, the perfect fifth, sixths and the
  octave (and their compounds); the fourth is a dissonance in two voices.
* **Dissonance** [error]: every note on a downbeat is consonant except a
  suspension. First species has no dissonance; second species allows a
  passing tone on the weak half; third species a passing tone, a neighbor
  tone, the cambiata (the dissonance on a weak quarter leaps down a third and
  the line turns up by step: Fux, Jeppesen) and the double neighbor
  (Salzer–Schachter) on the weak quarters. Fourth species has consonant weak
  halves only. In the fifth, half notes follow second-species and quarters
  and eighths third-species treatment. Fux and Jeppesen differ on dissonant
  neighbor tones in third species; they are allowed here, as Jeppesen and
  Salzer–Schachter allow them on weak quarters.
* **Suspensions** (fourth and fifth species): the tied note is consonant when
  it is struck and, if dissonant on the downbeat, resolves down by step to a
  consonance [error], directly or (fifth species) through the consonant
  third below the resolution (Jeppesen's ornamented resolution). Above the
  cantus the 7–6, 4–3 and 9–8 are correct and the 2–1 is an error; below it
  the 2–3 (9–10) is correct, the 4–5 a warning (Fux allows it, Jeppesen
  avoids it) and the 7–8 an error (Fux).
* **Parallel fifths and octaves** (and unisons) by similar motion [error];
  by contrary motion [warning: Jeppesen and Salzer–Schachter avoid them,
  Fux's rule only asks for contrary motion between perfect consonances]. On
  successive downbeats (second species) they are an error when only a step
  or a third separates them and a warning when a larger leap does (Fux, Mann
  p. 43); in third and fifth species downbeat parallels are a warning. On
  successive weak halves of the fourth species (a 9–8 or 4–5 chain) they are
  an error, since the suspension does not hide them (Fux), and a warning
  over consonant syncopations.
* **Direct (hidden) fifths and octaves**, similar motion into a perfect
  consonance: an error when the upper voice leaps, a warning when it moves
  by step (Fux forbids them all; Salzer–Schachter accept the step).
* **Beginning** [error]: a perfect consonance; below the cantus only the
  unison or octave, a fifth below would put the line in another mode (Fux).
* **Ending** [error]: the unison or octave, reached by step in contrary
  motion from a major sixth (expanding) or minor third (contracting): the
  clausula vera. The voice that rises to the final does so by a half step:
  the raised leading tone (musica ficta) in Dorian, Mixolydian and Aeolian
  [error when missing]. In Phrygian the cantus falls a half step and the
  counterpoint rises a whole step; a raised second degree would be wrong.
* **Mode** [error]: notes belong to the mode, with the ficta of Fux's
  examples: the lowered sixth degree in Dorian (B♭ in D) and the lowered
  fourth in Lydian (B♭ in F) anywhere, the raised seventh (Dorian,
  Mixolydian, Aeolian) and in Aeolian the raised sixth before it in the
  penultimate bar, and elsewhere a raised seventh that rises to the final
  (Fux, fig. 21).
* **Melodic intervals**: augmented and diminished intervals, including the
  chromatic half step [error]; sevenths, major sixths and leaps beyond an
  octave [error]; the descending minor sixth [warning: Jeppesen allows only
  the ascending one, Fux uses both]. Two leaps in the same direction are a
  warning, an error when they outline a seventh, a ninth or more, or a
  dissonance. After a leap of a fifth or more the line should turn
  [warning]. An outlined augmented fourth between two turning points
  [warning], as are a range above a tenth [warning; above a twelfth an
  error] and a climax reached more than once [warning]. A repeated note is a
  warning in first species (Fux repeats notes there) and an error in the
  others, except a quarter struck again in fifth species (Jeppesen's
  anticipation). Eighth notes move by step [error].
* **Unisons** inside the exercise are an error on downbeats and allowed on
  weak beats (Fux).
* **Voice crossing** and **overlap** [warning]: Fux crosses the voices in
  his own examples (fig. 14, 75); voices more than a twelfth apart
  [warning]. More than three parallel thirds or sixths in a row (on the
  downbeats from the second species on) [warning].
"""

# Messages are passed to _Checker.add() as lambdas that it calls at once (or never, in
# scan()), so the loop variables they use cannot change before the call.
# ruff: noqa: B023

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from fractions import Fraction
from functools import lru_cache
from gettext import gettext as _
from gettext import pgettext

from ..core import Duration, Interval, NoteValue, Pitch, PitchName, Scale, ScaleType
from ..core.naming import interval_name, pitch_name
from .voice_leading import Severity

__all__ = [
    'CANTUS',
    'COUNTERPOINT',
    'MODES',
    'Context',
    'Rhythm',
    'Rule',
    'Severity',
    'Species',
    'Violation',
    'cadence_ficta',
    'check',
    'check_cantus',
    'errors',
    'is_consonant',
    'mode_ficta',
    'rule_mark',
    'rule_name',
    'rule_reason',
    'scan',
    'species_name',
    'species_rhythm',
    'stepper',
    'voice_name',
    'voice_title',
]

COUNTERPOINT, CANTUS = 0, 1
"""Voice roles in :attr:`Violation.voices`."""

MODES = (
    ScaleType.DORIAN,
    ScaleType.PHRYGIAN,
    ScaleType.LYDIAN,
    ScaleType.MIXOLYDIAN,
    ScaleType.AEOLIAN,
    ScaleType.IONIAN,
)
"""The six modes of Fux's examples, in his order (finals D, E, F, G, A, C)."""


class Species(IntEnum):
    FIRST = 1
    """Note against note: whole notes."""
    SECOND = 2
    """Two half notes against each note."""
    THIRD = 3
    """Four quarter notes against each note."""
    FOURTH = 4
    """Syncopation: half notes tied over the barline (suspensions)."""
    FIFTH = 5
    """Florid counterpoint: the other species combined, with eighth notes."""


class Rule(Enum):
    """Every rule the checker knows. The value is a stable id for settings and tests."""

    DISSONANCE = 'dissonance'
    """A dissonance where the species requires a consonance (a downbeat, a weak half
    in fourth species, any note in first species)."""
    DISSONANCE_TREATMENT = 'dissonance-treatment'
    """A weak-beat dissonance that is not a passing tone, neighbor, cambiata or double
    neighbor (as the species allows)."""
    SUSPENSION = 'suspension'
    """A suspension that is not prepared, not resolved down by step, or of a kind the
    style avoids (2–1 above, 7–8 below)."""
    PARALLEL_FIFTHS = 'parallel-fifths'
    PARALLEL_OCTAVES = 'parallel-octaves'
    """Includes parallel unisons."""
    DIRECT_FIFTHS = 'direct-fifths'
    DIRECT_OCTAVES = 'direct-octaves'
    UNISON = 'unison'
    """A unison on a downbeat inside the exercise."""
    BEGINNING = 'beginning'
    """The first interval is not a perfect consonance (below: unison or octave)."""
    ENDING = 'ending'
    """The last interval is not a unison or octave."""
    CADENCE = 'cadence'
    """The final is not reached by step in contrary motion from a sixth or third."""
    LEADING_TONE = 'leading-tone'
    """The cadence lacks its raised leading tone (or raises the Phrygian second)."""
    FOREIGN_NOTE = 'foreign-note'
    """A note outside the mode and its ficta."""
    MELODIC_INTERVAL = 'melodic-interval'
    """An augmented or diminished melodic interval (or a chromatic half step)."""
    LARGE_LEAP = 'large-leap'
    """A seventh, a major sixth, a descending minor sixth or more than an octave."""
    CONSECUTIVE_LEAPS = 'consecutive-leaps'
    """Two leaps in the same direction."""
    LEAP_RECOVERY = 'leap-recovery'
    """The line does not turn after a leap of a fifth or more."""
    OUTLINED_TRITONE = 'outlined-tritone'
    """An augmented fourth between two turning points of the line."""
    RANGE = 'range'
    """The line spans more than a tenth."""
    CLIMAX = 'climax'
    """The highest note is reached more than once."""
    REPEATED_NOTE = 'repeated-note'
    EIGHTH_NOTES = 'eighth-notes'
    """Eighth notes approached or left by leap."""
    CROSSING = 'crossing'
    OVERLAP = 'overlap'
    SPACING = 'spacing'
    """The voices are more than a twelfth apart."""
    PARALLEL_THIRDS = 'parallel-thirds'
    """More than three thirds or sixths in a row."""


@dataclass(frozen=True, slots=True)
class Rhythm:
    """When the counterpoint's notes sound: an optional rest, then one duration per
    note. A bar is a whole note, the length of one cantus note; a note longer than
    what is left of its bar is tied over the barline."""

    notes: tuple[Duration, ...]
    rest: Duration | None = None

    @property
    def onsets(self) -> tuple[Fraction, ...]:
        """When each note starts, in whole notes from the beginning."""
        time = self.rest.length if self.rest is not None else Fraction(0)
        result = []
        for duration in self.notes:
            result.append(time)
            time += duration.length
        return tuple(result)

    @property
    def length(self) -> Fraction:
        rest = self.rest.length if self.rest is not None else Fraction(0)
        return rest + sum((d.length for d in self.notes), Fraction(0))

    def tied(self) -> tuple[bool, ...]:
        """Whether each note is tied over a barline."""
        return tuple(
            start + d.length > int(start) + 1
            for start, d in zip(self.onsets, self.notes, strict=True)
        )


WHOLE = Duration(NoteValue.WHOLE)
HALF = Duration(NoteValue.HALF)
QUARTER = Duration(NoteValue.QUARTER)
EIGHTH = Duration(NoteValue.EIGHTH)


def species_rhythm(species: Species, bars: int) -> Rhythm:
    """The standard rhythm of species 1–4 against ``bars`` cantus notes, as Fux writes
    them: whole notes; a half rest and half notes; quarter notes; a half rest and
    whole notes tied over each barline, the last one a half note (the leading tone).
    Each ends with a whole note. The fifth species has no single rhythm."""
    if bars < 2:
        raise ValueError('a cantus firmus has at least two notes')
    match species:
        case Species.FIRST:
            return Rhythm((WHOLE,) * bars)
        case Species.SECOND:
            return Rhythm((HALF,) * (2 * bars - 3) + (WHOLE,), rest=HALF)
        case Species.THIRD:
            return Rhythm((QUARTER,) * (4 * bars - 4) + (WHOLE,))
        case Species.FOURTH:
            return Rhythm((WHOLE,) * (bars - 2) + (HALF, WHOLE), rest=HALF)
    raise ValueError('the fifth species is written in a rhythm chosen per exercise')


@dataclass(frozen=True, slots=True)
class Context:
    """What the checker needs to know besides the notes."""

    mode: Scale
    """The mode and its final, e.g. ``Scale(PitchName.parse('D'), ScaleType.DORIAN)``."""
    species: Species = Species.FIRST
    above: bool = True
    """The counterpoint is written above the cantus firmus (``False``: below)."""
    rhythm: Rhythm | None = None
    """The counterpoint's rhythm; ``None`` is :func:`species_rhythm` (species 1–4)."""
    rules: frozenset[Rule] = frozenset(Rule)
    """Rules to apply."""

    def rhythm_for(self, bars: int) -> Rhythm:
        return self.rhythm if self.rhythm is not None else species_rhythm(self.species, bars)


@dataclass(frozen=True, slots=True)
class Violation:
    rule: Rule
    severity: Severity
    slot: int
    """The counterpoint note where the problem is heard (for :func:`check_cantus`, the
    cantus note)."""
    voices: tuple[int, ...]
    """:data:`COUNTERPOINT`, :data:`CANTUS` or both."""
    message: str
    """Translated explanation, e.g. "Parallel fifths in bars 3–4"."""
    notes: tuple[int, ...] = ()
    """Counterpoint notes involved (the line checked by :func:`check_cantus`)."""
    cantus: tuple[int, ...] = ()
    """Cantus firmus notes involved (bars)."""

    @property
    def slots(self) -> tuple[int, ...]:
        """The counterpoint notes to mark: :attr:`notes`, or the slot."""
        return self.notes or (self.slot,)


# Names --------------------------------------------------------------------------------


def voice_name(voice: int) -> str:
    """Lower-case name for use inside a sentence: "counterpoint", "cantus firmus"."""
    return (pgettext('voice', 'counterpoint'), pgettext('voice', 'cantus firmus'))[voice]


def voice_title(voice: int) -> str:
    """Capitalised name for labels: "Counterpoint", "Cantus firmus"."""
    return (pgettext('voice', 'Counterpoint'), pgettext('voice', 'Cantus firmus'))[voice]


def species_name(species: Species) -> str:
    """ "First species" … "Fifth species"."""
    names: dict[Species, Callable[[], str]] = {
        Species.FIRST: lambda: _('First species'),
        Species.SECOND: lambda: _('Second species'),
        Species.THIRD: lambda: _('Third species'),
        Species.FOURTH: lambda: _('Fourth species'),
        Species.FIFTH: lambda: _('Fifth species'),
    }
    return names[species]()


def rule_name(rule: Rule) -> str:
    """Name of a rule's violation, e.g. "Parallel fifths" (answer options, lists)."""
    names: dict[Rule, Callable[[], str]] = {
        Rule.DISSONANCE: lambda: _('Dissonance on a strong beat'),
        Rule.DISSONANCE_TREATMENT: lambda: _('Dissonance left by leap'),
        Rule.SUSPENSION: lambda: _('Wrong suspension'),
        Rule.PARALLEL_FIFTHS: lambda: _('Parallel fifths'),
        Rule.PARALLEL_OCTAVES: lambda: _('Parallel octaves'),
        Rule.DIRECT_FIFTHS: lambda: _('Direct fifths'),
        Rule.DIRECT_OCTAVES: lambda: _('Direct octaves'),
        Rule.UNISON: lambda: _('Unison inside the line'),
        Rule.BEGINNING: lambda: _('Wrong first interval'),
        Rule.ENDING: lambda: _('Wrong last interval'),
        Rule.CADENCE: lambda: _('Wrong cadence'),
        Rule.LEADING_TONE: lambda: _('Missing leading tone'),
        Rule.FOREIGN_NOTE: lambda: _('Note outside the mode'),
        Rule.MELODIC_INTERVAL: lambda: _('Augmented or diminished leap'),
        Rule.LARGE_LEAP: lambda: _('Forbidden leap'),
        Rule.CONSECUTIVE_LEAPS: lambda: _('Leaps in one direction'),
        Rule.LEAP_RECOVERY: lambda: _('Leap not recovered'),
        Rule.OUTLINED_TRITONE: lambda: _('Outlined tritone'),
        Rule.RANGE: lambda: _('Range too wide'),
        Rule.CLIMAX: lambda: _('Repeated climax'),
        Rule.REPEATED_NOTE: lambda: _('Repeated note'),
        Rule.EIGHTH_NOTES: lambda: _('Eighth notes by leap'),
        Rule.CROSSING: lambda: _('Voice crossing'),
        Rule.OVERLAP: lambda: _('Voice overlap'),
        Rule.SPACING: lambda: _('Voices too far apart'),
        Rule.PARALLEL_THIRDS: lambda: _('Too many parallel thirds or sixths'),
    }
    return names[rule]()


def rule_mark(rule: Rule) -> str:
    """A short mark written on the staff where the rule is broken, e.g. "∥5"."""
    # Translators: short marks written on the staff under a counterpoint mistake, as a
    # teacher would mark it: dis. dissonance, sus suspension, ∥5 parallel fifths, →8
    # direct octaves, 1 unison, beg/end/cad beginning, ending, cadence, LT leading tone,
    # ♯♭ note outside the mode, A/d augmented or diminished leap, lp. leap, rec leap
    # not recovered, TT outlined tritone, rng range, max climax, rep repeated note,
    # ♪ eighth notes, × crossing, ov. overlap, sp. spacing, ∥3 parallel thirds. Keep
    # them at most three characters.
    ctx = 'counterpoint mark'
    marks: dict[Rule, Callable[[], str]] = {
        Rule.DISSONANCE: lambda: pgettext(ctx, 'dis'),
        Rule.DISSONANCE_TREATMENT: lambda: pgettext(ctx, 'dis'),
        Rule.SUSPENSION: lambda: pgettext(ctx, 'sus'),
        Rule.PARALLEL_FIFTHS: lambda: pgettext(ctx, '∥5'),
        Rule.PARALLEL_OCTAVES: lambda: pgettext(ctx, '∥8'),
        Rule.DIRECT_FIFTHS: lambda: pgettext(ctx, '→5'),
        Rule.DIRECT_OCTAVES: lambda: pgettext(ctx, '→8'),
        Rule.UNISON: lambda: pgettext(ctx, '1'),
        Rule.BEGINNING: lambda: pgettext(ctx, 'beg'),
        Rule.ENDING: lambda: pgettext(ctx, 'end'),
        Rule.CADENCE: lambda: pgettext(ctx, 'cad'),
        Rule.LEADING_TONE: lambda: pgettext(ctx, 'LT'),
        Rule.FOREIGN_NOTE: lambda: pgettext(ctx, '♯♭'),
        Rule.MELODIC_INTERVAL: lambda: pgettext(ctx, 'A/d'),
        Rule.LARGE_LEAP: lambda: pgettext(ctx, 'lp.'),
        Rule.CONSECUTIVE_LEAPS: lambda: pgettext(ctx, 'lp.'),
        Rule.LEAP_RECOVERY: lambda: pgettext(ctx, 'rec'),
        Rule.OUTLINED_TRITONE: lambda: pgettext(ctx, 'TT'),
        Rule.RANGE: lambda: pgettext(ctx, 'rng'),
        Rule.CLIMAX: lambda: pgettext(ctx, 'max'),
        Rule.REPEATED_NOTE: lambda: pgettext(ctx, 'rep'),
        Rule.EIGHTH_NOTES: lambda: pgettext(ctx, '♪'),
        Rule.CROSSING: lambda: pgettext(ctx, '×'),
        Rule.OVERLAP: lambda: pgettext(ctx, 'ov.'),
        Rule.SPACING: lambda: pgettext(ctx, 'sp.'),
        Rule.PARALLEL_THIRDS: lambda: pgettext(ctx, '∥3'),
    }
    return marks[rule]()


def rule_reason(rule: Rule) -> str:
    """Why the rule matters, in a sentence for feedback."""
    reasons: dict[Rule, Callable[[], str]] = {
        Rule.DISSONANCE: lambda: _(
            'Strong beats carry the consonant framework of the two voices; a dissonance '
            'there needs the preparation of a suspension.'
        ),
        Rule.DISSONANCE_TREATMENT: lambda: _(
            'A dissonance on a weak beat is a passing or neighboring note: approached and '
            'left by step (the cambiata leaps down a third and turns up).'
        ),
        Rule.SUSPENSION: lambda: _(
            'A suspension is struck as a consonance, becomes dissonant when the cantus moves, '
            'and resolves down by step to a consonance.'
        ),
        Rule.PARALLEL_FIFTHS: lambda: _(
            'Two voices moving in perfect fifths sound like one thickened voice and lose '
            'their independence.'
        ),
        Rule.PARALLEL_OCTAVES: lambda: _(
            'Two voices moving in octaves or unisons merge into one: two parts become one.'
        ),
        Rule.DIRECT_FIFTHS: lambda: _(
            'Moving into a fifth in similar motion stresses it as if it were a parallel; '
            'approach perfect consonances in contrary or oblique motion.'
        ),
        Rule.DIRECT_OCTAVES: lambda: _(
            'Moving into an octave in similar motion stresses it as if it were a parallel; '
            'approach perfect consonances in contrary or oblique motion.'
        ),
        Rule.UNISON: lambda: _(
            'On a strong beat a unison makes the two voices one; keep it for the beginning '
            'and the end.'
        ),
        Rule.BEGINNING: lambda: _(
            'The first interval establishes the mode: a unison, fifth or octave above the '
            'cantus, a unison or octave below it.'
        ),
        Rule.ENDING: lambda: _('The exercise ends on the final, in a unison or an octave.'),
        Rule.CADENCE: lambda: _(
            'The cadence (clausula vera) reaches the final by step in contrary motion: a '
            'major sixth opens to the octave, or a minor third closes to the unison.'
        ),
        Rule.LEADING_TONE: lambda: _(
            'The voice that rises to the final does so by a half step: raise the seventh '
            'degree in Dorian, Mixolydian and Aeolian. In Phrygian the cantus falls a half '
            'step instead and the counterpoint rises a whole step.'
        ),
        Rule.FOREIGN_NOTE: lambda: _(
            'The line stays in its mode; the only accidentals are the ficta of the style, '
            'such as the raised leading tone at the cadence.'
        ),
        Rule.MELODIC_INTERVAL: lambda: _(
            'Augmented and diminished intervals are hard to sing and foreign to the style.'
        ),
        Rule.LARGE_LEAP: lambda: _(
            'The vocal style leaps by thirds, fourths, fifths, the rising minor sixth and '
            'the octave; larger or dissonant leaps are hard to sing.'
        ),
        Rule.CONSECUTIVE_LEAPS: lambda: _(
            'Leaps in one direction stretch the line; after a leap, turn back, preferably by step.'
        ),
        Rule.LEAP_RECOVERY: lambda: _(
            'A large leap leaves a gap that the line fills by turning back, preferably by step.'
        ),
        Rule.OUTLINED_TRITONE: lambda: _(
            'A line that rises or falls through an augmented fourth and turns there stresses '
            'the tritone (mi contra fa).'
        ),
        Rule.RANGE: lambda: _('A singable line stays within a tenth or so.'),
        Rule.CLIMAX: lambda: _('A well-shaped line reaches its highest note once.'),
        Rule.REPEATED_NOTE: lambda: _(
            'A repeated note stalls the line; in the faster species it also sounds like a '
            'syncopation that is not one.'
        ),
        Rule.EIGHTH_NOTES: lambda: _(
            'Eighth notes are quick ornaments: they come in pairs on weak beats and move by step.'
        ),
        Rule.CROSSING: lambda: _(
            'When the voices cross, the ear may follow the wrong line; do it rarely and briefly.'
        ),
        Rule.OVERLAP: lambda: _(
            'Moving past the note the other voice just sang blurs the two lines.'
        ),
        Rule.SPACING: lambda: _('Voices far apart lose contact; keep within a twelfth.'),
        Rule.PARALLEL_THIRDS: lambda: _(
            'Many thirds or sixths in a row make the voices move as one; vary the motion.'
        ),
    }
    return reasons[rule]()


def _note(pitch: Pitch) -> str:
    return pitch_name(pitch.name) + str(pitch.octave)


def _bars(first: int, second: int) -> str:
    """ "bar 3" or "bars 3–4" (1-based bar numbers)."""
    if first == second:
        return _('bar {bar}').format(bar=first)
    return _('bars {first}–{second}').format(first=first, second=second)


# Intervals ------------------------------------------------------------------------------

_SIMPLE_SEMITONES = (0, 2, 4, 5, 7, 9, 11)
_CONSONANT = frozenset({(0, 0), (2, 0), (2, -1), (4, 0), (5, 0), (5, -1)})
"""(simple steps, offset from major or perfect) of the consonances."""


def _vertical(a: Pitch, b: Pitch) -> tuple[int, int]:
    """(steps, offset): diatonic steps from the lower-spelled to the higher pitch and the
    offset in semitones from the major or perfect interval of that size."""
    low, high = (a, b) if a.diatonic_index <= b.diatonic_index else (b, a)
    steps = high.diatonic_index - low.diatonic_index
    semitones = high.midi - low.midi
    if steps == 0:
        semitones = abs(semitones)
    return steps, semitones - _SIMPLE_SEMITONES[steps % 7] - 12 * (steps // 7)


def is_consonant(a: Pitch, b: Pitch) -> bool:
    """Whether two pitches sound a consonance in two-voice counterpoint (not the fourth)."""
    steps, offset = _vertical(a, b)
    return (steps % 7, offset) in _CONSONANT


def _is_perfect(a: Pitch, b: Pitch, simple: int) -> bool:
    """A perfect unison/octave (``simple`` 0) or fifth (4), compound or not."""
    steps, offset = _vertical(a, b)
    return steps % 7 == simple and offset == 0


def _imperfect(a: Pitch, b: Pitch) -> int | None:
    """3 or 6 for a (compound) third or sixth, else ``None``."""
    steps, offset = _vertical(a, b)
    if (steps % 7, offset) in ((2, 0), (2, -1)):
        return 3
    if (steps % 7, offset) in ((5, 0), (5, -1)):
        return 6
    return None


def _altered(steps: int, semitones: int) -> bool:
    """Whether a melodic interval of ``steps`` and ``semitones`` (signed alike, from the
    first note) is augmented or diminished, including the chromatic half step."""
    if steps < 0 or (steps == 0 and semitones < 0):
        steps, semitones = -steps, -semitones
    offset = semitones - _SIMPLE_SEMITONES[steps % 7] - 12 * (steps // 7)
    if steps % 7 in (0, 3, 4):
        return offset != 0
    return offset not in (0, -1)


def _is_step(a: Pitch, b: Pitch) -> bool:
    return abs(b.diatonic_index - a.diatonic_index) == 1 and 1 <= abs(b.midi - a.midi) <= 2


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


def _interval(a: Pitch, b: Pitch) -> Interval | None:
    """The interval between two pitches in either order (``None`` beyond doubly altered)."""
    low, high = (a, b) if (a.diatonic_index, a.midi) <= (b.diatonic_index, b.midi) else (b, a)
    try:
        return Interval.between(low, high)
    except ValueError:
        return None


def _named(a: Pitch, b: Pitch) -> str:
    interval = _interval(a, b)
    if interval is None:
        return '?'
    try:
        return interval_name(interval)
    except ValueError:
        return str(interval)


# The mode -------------------------------------------------------------------------------


def mode_ficta(mode: Scale) -> frozenset[PitchName]:
    """Accidentals the mode allows anywhere: B♭ in D Dorian (its sixth degree lowered)
    and in F Lydian (its fourth lowered), transposed with the mode."""
    flat = Interval.parse('A1')
    if mode.type is ScaleType.DORIAN:
        return frozenset({mode.degree(6).transpose(flat, down=True)})
    if mode.type is ScaleType.LYDIAN:
        return frozenset({mode.degree(4).transpose(flat, down=True)})
    return frozenset()


def cadence_ficta(mode: Scale) -> tuple[PitchName | None, PitchName | None]:
    """The raised seventh (Dorian, Mixolydian, Aeolian) and the raised sixth (Aeolian)
    allowed at the cadence; ``None`` where the mode has none."""
    sharp = Interval.parse('A1')
    seventh = sixth = None
    if mode.type in (ScaleType.DORIAN, ScaleType.MIXOLYDIAN, ScaleType.AEOLIAN):
        seventh = mode.degree(7).transpose(sharp)
    if mode.type is ScaleType.AEOLIAN:
        sixth = mode.degree(6).transpose(sharp)
    return seventh, sixth


# Checking -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Note:
    """Where a counterpoint note falls: start, end, bar and whether it is tied."""

    start: Fraction
    end: Fraction
    bar: int
    strong: bool
    """Starts on a downbeat."""
    tied: bool
    """Held over the barline into the next bar."""
    length: Fraction
    joined: bool = False
    """Starts where the note before it ends (not after a rest)."""
    downbeat_before: int = -1
    """The note struck on the downbeat of the bar before, if this one is on a downbeat."""
    syncopation: bool = False
    """Struck on the weak half after a note tied over from the weak half before."""

    @property
    def long(self) -> bool:
        return self.length >= _HALF_LENGTH

    @property
    def quick(self) -> bool:
        """A quarter note or shorter."""
        return self.length <= _QUARTER_LENGTH


_HALF_LENGTH = Fraction(1, 2)
_QUARTER_LENGTH = Fraction(1, 4)
_EIGHTH_LENGTH = Fraction(1, 8)


@lru_cache(maxsize=512)
def _layout(rhythm: Rhythm) -> tuple[_Note, ...]:
    """Where the notes of ``rhythm`` fall (searches check thousands of lines in one)."""
    notes: list[_Note] = []
    for start, duration in zip(rhythm.onsets, rhythm.notes, strict=True):
        bar = int(start)
        end = start + duration.length
        if end > bar + 2:
            raise ValueError('a note is tied over more than one barline')
        index = len(notes)
        joined = syncopation = False
        if index:
            before = notes[-1]
            joined = before.end == start
            syncopation = start - bar == _HALF_LENGTH and before.tied and before.start == start - 1
        downbeat_before = -1
        if start == bar:
            downbeat_before = next(
                (
                    k
                    for k in range(index - 1, -1, -1)
                    if notes[k].strong and notes[k].start == start - 1
                ),
                -1,
            )
        notes.append(
            _Note(
                start,
                end,
                bar,
                start == bar,
                end > bar + 1,
                duration.length,
                joined,
                downbeat_before,
                syncopation,
            )
        )
    return tuple(notes)


@dataclass(slots=True)
class _Checker:
    cantus: Sequence[Pitch]
    context: Context
    messages: bool
    rhythm: Rhythm = field(init=False)
    notes: list[_Note] = field(init=False)
    line: list[Pitch] = field(default_factory=list)
    ds: list[int] = field(default_factory=list)
    """Diatonic index of each note of the line."""
    ms: list[int] = field(default_factory=list)
    """MIDI number of each note of the line."""
    spans: list[tuple[int, int]] = field(default_factory=list)
    """Lowest and highest diatonic index up to each note."""
    found: list[Violation] = field(default_factory=list)
    names: frozenset[PitchName] = field(init=False)
    seventh: PitchName | None = field(init=False)
    sixth: PitchName | None = field(init=False)

    def __post_init__(self) -> None:
        bars = len(self.cantus)
        self.rhythm = self.context.rhythm_for(bars)
        if self.rhythm.length != bars:
            raise ValueError(
                f'the rhythm lasts {self.rhythm.length} bars, the cantus firmus {bars}'
            )
        self.notes = list(_layout(self.rhythm))
        mode = self.context.mode
        self.names = frozenset(mode.names()) | mode_ficta(mode)
        self.seventh, self.sixth = cadence_ficta(mode)

    # Recording

    def add(
        self,
        rule: Rule,
        severity: Severity,
        slot: int,
        message: Callable[[], str],
        *,
        notes: tuple[int, ...] = (),
        cantus: tuple[int, ...] = (),
        voices: tuple[int, ...] = (COUNTERPOINT,),
    ) -> None:
        """Record a violation; ``message`` is only called when messages are wanted."""
        if rule in self.context.rules:
            text = message() if self.messages else ''
            self.found.append(
                Violation(rule, severity, slot, voices, text, notes or (slot,), cantus)
            )

    # Helpers

    @property
    def above(self) -> bool:
        return self.context.above

    @property
    def species(self) -> Species:
        return self.context.species

    def bar(self, index: int) -> int:
        """1-based bar of a note, for messages."""
        return self.notes[index].bar + 1

    def under(self, index: int) -> Pitch:
        """The cantus note sounding when note ``index`` is struck."""
        return self.cantus[self.notes[index].bar]

    def contiguous(self, index: int) -> bool:
        return self.notes[index].joined

    # Stepping

    def step(self, pitch: Pitch) -> list[Violation]:
        """Add the next note and return the violations that it settles."""
        before = len(self.found)
        if len(self.line) >= len(self.notes):
            raise ValueError('more notes than the rhythm has')
        self.push(pitch)
        i = len(self.line) - 1
        self.vertical(i)
        if i == 0:
            self.beginning()
        else:
            self.melodic(i)
            if self.notes[i].strong and self.contiguous(i):
                self.motion(i)
        self.accented(i)
        self.dissonances(i)
        self.mode_notes(i)
        self.range(i)
        return self.found[before:]

    def push(self, pitch: Pitch) -> None:
        d = pitch.diatonic_index
        self.line.append(pitch)
        self.ds.append(d)
        self.ms.append(pitch.midi)
        low, high = self.spans[-1] if self.spans else (d, d)
        self.spans.append((min(low, d), max(high, d)))

    def pop(self) -> None:
        """Forget the last note (the caller drops the violations it returned)."""
        self.line.pop()
        self.ds.pop()
        self.ms.pop()
        self.spans.pop()

    def finish(self) -> list[Violation]:
        """Violations only the complete line shows (ending, cadence, climax)."""
        before = len(self.found)
        n = len(self.line)
        if n != len(self.notes):
            raise ValueError(f'the rhythm has {len(self.notes)} notes, the line {n}')
        for d in range(max(0, n - 3), n):
            if self.needs_treatment(d) and self.figures(d, n) is None:
                self.report_dissonance(d)
            if self.resolution(d, n) is None:
                self.unresolved(d)
        self.outline(n, final=True)
        self.ending()
        self.climax()
        return self.found[before:]

    # One note against the cantus -------------------------------------------------------

    def vertical(self, i: int) -> None:
        note, pitch = self.notes[i], self.line[i]
        cantus = self.cantus[note.bar]
        bar = note.bar + 1
        consonant = is_consonant(pitch, cantus)
        last = len(self.notes) - 1
        if not consonant:
            if note.tied:
                self.add(
                    Rule.SUSPENSION,
                    Severity.ERROR,
                    i,
                    # Translators: e.g. "The suspension in bar 4 is not prepared: C5 is a
                    # dissonance (a seventh) when it is struck".
                    lambda: _(
                        'The suspension in bar {bar} is not prepared: {note} is a dissonance '
                        '({interval}) when it is struck'
                    ).format(bar=bar + 1, note=_note(pitch), interval=_named(pitch, cantus)),
                    cantus=(note.bar,),
                    voices=(COUNTERPOINT, CANTUS),
                )
            elif note.strong or self.species in (Species.FIRST, Species.FOURTH):
                if note.strong:
                    # Translators: e.g. "Dissonance (a seventh) on the downbeat of bar 3".
                    text = lambda: _(  # noqa: E731
                        'Dissonance ({interval}) on the downbeat of bar {bar}'
                    ).format(interval=_named(pitch, cantus), bar=bar)
                else:
                    # Translators: e.g. "Dissonance (a fourth) in bar 3: in fourth species
                    # the notes struck on the weak half are consonant".
                    text = lambda: _(  # noqa: E731
                        'Dissonance ({interval}) in bar {bar}: in fourth species the notes '
                        'struck on the weak half are consonant'
                    ).format(interval=_named(pitch, cantus), bar=bar)
                self.add(
                    Rule.DISSONANCE,
                    Severity.ERROR,
                    i,
                    text,
                    cantus=(note.bar,),
                    voices=(COUNTERPOINT, CANTUS),
                )
        if note.strong and 0 < i < last and pitch == cantus:
            self.unison(i, note.bar)
        self.sides(i)
        if note.tied:
            self.tie(i)

    def unison(self, i: int, bar: int) -> None:
        self.add(
            Rule.UNISON,
            Severity.ERROR,
            i,
            # Translators: e.g. "Unison on the downbeat of bar 5".
            lambda: _('Unison on the downbeat of bar {bar}').format(bar=bar + 1),
            cantus=(bar,),
            voices=(COUNTERPOINT, CANTUS),
        )

    def sides(self, i: int) -> None:
        """Crossing and spacing of a note against the cantus, struck and (when tied) on
        the next downbeat; each reported once."""
        note, pitch = self.notes[i], self.line[i]
        bars = [note.bar, note.bar + 1] if note.tied else [note.bar]
        crossed = [
            b
            for b in bars
            if (
                pitch.midi < self.cantus[b].midi if self.above else pitch.midi > self.cantus[b].midi
            )
        ]
        if crossed:
            bar = crossed[0] + 1
            if self.above:
                # Translators: e.g. "The counterpoint crosses below the cantus firmus in
                # bar 6".
                text = lambda: _(  # noqa: E731
                    'The counterpoint crosses below the cantus firmus in bar {bar}'
                ).format(bar=bar)
            else:
                text = lambda: _(  # noqa: E731
                    'The counterpoint crosses above the cantus firmus in bar {bar}'
                ).format(bar=bar)
            self.add(
                Rule.CROSSING,
                Severity.WARNING,
                i,
                text,
                cantus=(crossed[0],),
                voices=(COUNTERPOINT, CANTUS),
            )
        apart = [b for b in bars if abs(pitch.diatonic_index - self.cantus[b].diatonic_index) > 11]
        if apart:
            bar = apart[0] + 1
            self.add(
                Rule.SPACING,
                Severity.WARNING,
                i,
                # Translators: e.g. "The voices are more than a twelfth apart in bar 4".
                lambda: _('The voices are more than a twelfth apart in bar {bar}').format(bar=bar),
                cantus=(apart[0],),
                voices=(COUNTERPOINT, CANTUS),
            )

    def tie(self, i: int) -> None:
        """The vertical of a tied note on the next downbeat: a consonant syncopation or a
        suspension of an allowed kind."""
        note, pitch = self.notes[i], self.line[i]
        bar = note.bar + 1
        cantus = self.cantus[bar]
        if is_consonant(pitch, cantus):
            if pitch == cantus:
                self.unison(i, bar)
            return
        steps, _offset = _vertical(pitch, cantus)
        number = steps % 7 + 1
        severity: Severity | None = None
        if self.above:
            if number == 2 and steps < 7:
                severity = Severity.ERROR  # 2–1: resolution into the unison
            elif number not in (2, 4, 7):
                severity = Severity.ERROR
        elif number == 4:
            severity = Severity.WARNING  # 4–5 below
        elif number != 2:
            severity = Severity.ERROR  # 7–8 below and the rest
        if severity is None:
            return
        size = steps + 1
        while size > 9:
            size -= 7  # a compound fourth is a fourth; the ninth keeps its name
        kind = f'{size}–{size - 1}' if self.above else f'{size}–{size + 1}'
        if self.above:
            # Translators: e.g. "The 2–1 suspension in bar 5 is avoided in this style; above
            # the cantus use 7–6, 4–3 or 9–8".
            text = lambda: _(  # noqa: E731
                'The {kind} suspension in bar {bar} is avoided in this style; above the '
                'cantus use 7–6, 4–3 or 9–8'
            ).format(kind=kind, bar=bar + 1)
        else:
            text = lambda: _(  # noqa: E731
                'The {kind} suspension in bar {bar} is avoided in this style; below the '
                'cantus use 2–3 (or 9–10)'
            ).format(kind=kind, bar=bar + 1)
        self.add(
            Rule.SUSPENSION,
            severity,
            i,
            text,
            cantus=(bar,),
            voices=(COUNTERPOINT, CANTUS),
        )

    def beginning(self) -> None:
        pitch, cantus = self.line[0], self.under(0)
        bar = self.notes[0].bar
        perfect = _is_perfect(pitch, cantus, 0) or (
            self.above and pitch.midi > cantus.midi and _is_perfect(pitch, cantus, 4)
        )
        if perfect:
            return
        if self.above:
            # Translators: e.g. "The first interval is a third; begin with a unison, fifth
            # or octave".
            text = lambda: _(  # noqa: E731
                'The first interval is {interval}; begin with a unison, fifth or octave'
            ).format(interval=_named(pitch, cantus))
        else:
            text = lambda: _(  # noqa: E731
                'The first interval is {interval}; below the cantus begin with a unison or octave'
            ).format(interval=_named(pitch, cantus))
        self.add(
            Rule.BEGINNING,
            Severity.ERROR,
            0,
            text,
            cantus=(bar,),
            voices=(COUNTERPOINT, CANTUS),
        )

    # Dissonance treatment ---------------------------------------------------------------

    def needs_treatment(self, d: int) -> bool:
        """A weak-beat dissonance whose treatment depends on the notes around it (the
        first note is judged by the beginning rule)."""
        note = self.notes[d]
        return (
            d > 0
            and not note.strong
            and not note.tied
            and self.species not in (Species.FIRST, Species.FOURTH)
            and not is_consonant(self.line[d], self.under(d))
        )

    def figures(self, d: int, known: int) -> bool | None:
        """Whether dissonance ``d`` is a passing tone, neighbor, cambiata or double
        neighbor, given the first ``known`` notes; ``None`` while a later note may still
        complete a figure."""
        line = self.line
        if not self.contiguous(d):
            return False
        if d + 1 >= known:
            return None
        if not self.contiguous(d + 1):
            return False
        before, here, after = line[d - 1], line[d], line[d + 1]
        into, out = here.midi - before.midi, after.midi - here.midi
        stepwise = _is_step(before, here) and _is_step(here, after)
        if stepwise and _sign(into) == _sign(out):
            return True  # passing tone
        if not self.notes[d].quick:
            return False  # half notes only pass
        if stepwise and after == before:
            return True  # neighbor tone
        if self.notes[d].length < _QUARTER_LENGTH:
            return False  # eighths pass or neighbor
        # Double neighbor, second note: main, step, third the other way, back to main.
        if (
            d >= 2
            and self.contiguous(d - 1)
            and _is_step(line[d - 2], before)
            and abs(here.diatonic_index - before.diatonic_index) == 2
            and _sign(into) != _sign(before.midi - line[d - 2].midi)
            and _is_step(here, after)
            and after == line[d - 2]
        ):
            return True
        third = abs(after.diatonic_index - here.diatonic_index) == 2
        if not third or not _is_step(before, here):
            return False
        if d + 2 >= known:
            return None
        if not self.contiguous(d + 2):
            return False
        following = line[d + 2]
        # Cambiata: down a step into the dissonance, down a third, up a step.
        if (
            into < 0
            and out < 0
            and is_consonant(after, self.under(d + 1))
            and _is_step(after, following)
            and following.midi > after.midi
        ):
            return True
        # Double neighbor, first note: main, step, third the other way, back to main.
        return _sign(out) != _sign(into) and _is_step(after, following) and following == before

    def resolution(self, j: int, known: int) -> bool | None:
        """Whether tied note ``j``, dissonant on the downbeat, resolves (``True`` also for
        a note that is no suspension); ``None`` while undecided."""
        note, pitch = self.notes[j], self.line[j]
        bar = note.bar + 1
        if not note.tied or bar >= len(self.cantus) or is_consonant(pitch, self.cantus[bar]):
            return True
        if j + 1 >= known:
            return None
        after = self.line[j + 1]
        down = pitch.diatonic_index - after.diatonic_index
        if down == 1 and 1 <= pitch.midi - after.midi <= 2:
            return is_consonant(after, self.under(j + 1))
        if not (
            self.species is Species.FIFTH and down >= 2 and is_consonant(after, self.under(j + 1))
        ):
            return False
        # Ornamented: down to a consonance, then the resolution (Fux, fig. 82–88).
        if j + 2 >= known:
            return None
        resolution = self.line[j + 2]
        return (
            pitch.diatonic_index - resolution.diatonic_index == 1
            and 1 <= pitch.midi - resolution.midi <= 2
            and is_consonant(resolution, self.under(j + 2))
        )

    def dissonances(self, i: int) -> None:
        """Dissonances and suspensions that note ``i`` settles."""
        for d in (i - 1, i - 2):
            if d < 0:
                continue
            if (
                self.needs_treatment(d)
                and self.figures(d, i + 1) is False
                and (d == i - 1 or self.figures(d, i) is None)
            ):
                self.report_dissonance(d)
            if self.resolution(d, i + 1) is False and (d == i - 1 or self.resolution(d, i) is None):
                self.unresolved(d)

    def report_dissonance(self, d: int) -> None:
        pitch, cantus = self.line[d], self.under(d)
        bar = self.notes[d].bar
        if self.notes[d].long:
            # Translators: e.g. "The dissonance (a fourth) in bar 3 is not a passing tone:
            # approach and leave it by step in one direction".
            text = lambda: _(  # noqa: E731
                'The dissonance ({interval}) in bar {bar} is not a passing tone: approach and '
                'leave it by step in one direction'
            ).format(interval=_named(pitch, cantus), bar=bar + 1)
        else:
            # Translators: e.g. "The dissonance (a seventh) in bar 3 is approached or left
            # by leap".
            text = lambda: _(  # noqa: E731
                'The dissonance ({interval}) in bar {bar} is approached or left by leap'
            ).format(interval=_named(pitch, cantus), bar=bar + 1)
        notes = tuple(n for n in (d - 1, d, d + 1) if 0 <= n < len(self.line))
        self.add(
            Rule.DISSONANCE_TREATMENT,
            Severity.ERROR,
            d,
            text,
            notes=notes,
            cantus=(bar,),
            voices=(COUNTERPOINT, CANTUS),
        )

    def unresolved(self, j: int) -> None:
        pitch = self.line[j]
        bar = self.notes[j].bar + 1
        after = self.line[j + 1] if j + 1 < len(self.line) else None
        if after is not None and _is_step(pitch, after) and after.midi > pitch.midi:
            # Translators: e.g. "The suspension (D5) in bar 4 resolves up; it resolves
            # down by step".
            text = lambda: _(  # noqa: E731
                'The suspension ({note}) in bar {bar} resolves up; it resolves down by step'
            ).format(note=_note(pitch), bar=bar + 1)
        else:
            # Translators: e.g. "The suspension (D5) in bar 4 does not resolve down by step
            # to a consonance".
            text = lambda: _(  # noqa: E731
                'The suspension ({note}) in bar {bar} does not resolve down by step to a consonance'
            ).format(note=_note(pitch), bar=bar + 1)
        notes = tuple(n for n in (j, j + 1) if n < len(self.line))
        self.add(
            Rule.SUSPENSION,
            Severity.ERROR,
            j,
            text,
            notes=notes,
            cantus=(bar,),
            voices=(COUNTERPOINT, CANTUS),
        )

    # Motion between the voices ---------------------------------------------------------

    def motion(self, i: int) -> None:
        """Both voices move into note ``i`` (struck on a downbeat)."""
        bar = self.notes[i].bar
        a_cp, b_cp = self.line[i - 1], self.line[i]
        a_cf, b_cf = self.cantus[bar - 1], self.cantus[bar]
        cp_move, cf_move = b_cp.midi - a_cp.midi, b_cf.midi - a_cf.midi
        notes, cantus = (i - 1, i), (bar - 1, bar)
        voices = (COUNTERPOINT, CANTUS)
        bars = {'first': bar, 'second': bar + 1}
        if cp_move and cf_move:
            similar = _sign(cp_move) == _sign(cf_move)
            for simple, rule in ((0, Rule.PARALLEL_OCTAVES), (4, Rule.PARALLEL_FIFTHS)):
                before = _is_perfect(a_cp, a_cf, simple)
                after = _is_perfect(b_cp, b_cf, simple)
                if before and after:
                    self.parallel(rule, i, similar, notes, cantus, bars)
                elif after and similar:
                    self.direct(rule, i, b_cp, b_cf, a_cp, a_cf, notes, cantus, bars)
            upper_before, lower_before = (a_cp, a_cf) if self.above else (a_cf, a_cp)
            upper_after, lower_after = (b_cp, b_cf) if self.above else (b_cf, b_cp)
            if upper_after.midi < lower_before.midi or lower_after.midi > upper_before.midi:
                self.add(
                    Rule.OVERLAP,
                    Severity.WARNING,
                    i,
                    # Translators: e.g. "The voices overlap in bars 3–4: one moves past the
                    # note the other just sang".
                    lambda: _(
                        'The voices overlap in bars {first}–{second}: one moves past the note '
                        'the other just sang'
                    ).format(**bars),
                    notes=notes,
                    cantus=cantus,
                    voices=voices,
                )
        self.thirds(i)

    def parallel(
        self,
        rule: Rule,
        i: int,
        similar: bool,
        notes: tuple[int, ...],
        cantus: tuple[int, ...],
        bars: dict[str, int],
    ) -> None:
        octaves = rule is Rule.PARALLEL_OCTAVES
        if similar:
            if octaves:
                # Translators: e.g. "Parallel octaves in bars 3–4".
                text = lambda: _('Parallel octaves in bars {first}–{second}').format(**bars)  # noqa: E731
            else:
                # Translators: e.g. "Parallel fifths in bars 3–4".
                text = lambda: _('Parallel fifths in bars {first}–{second}').format(**bars)  # noqa: E731
        elif octaves:
            text = lambda: _(  # noqa: E731
                'Octaves by contrary motion in bars {first}–{second}'
            ).format(**bars)
        else:
            text = lambda: _(  # noqa: E731
                'Fifths by contrary motion in bars {first}–{second}'
            ).format(**bars)
        severity = Severity.ERROR if similar else Severity.WARNING
        self.add(rule, severity, i, text, notes=notes, cantus=cantus, voices=(0, 1))

    def direct(
        self,
        rule: Rule,
        i: int,
        b_cp: Pitch,
        b_cf: Pitch,
        a_cp: Pitch,
        a_cf: Pitch,
        notes: tuple[int, ...],
        cantus: tuple[int, ...],
        bars: dict[str, int],
    ) -> None:
        upper_now, upper_then = (b_cp, a_cp) if b_cp.midi >= b_cf.midi else (b_cf, a_cf)
        leap = abs(upper_now.diatonic_index - upper_then.diatonic_index) > 1
        severity = Severity.ERROR if leap else Severity.WARNING
        if rule is Rule.PARALLEL_OCTAVES:
            rule = Rule.DIRECT_OCTAVES
            # Translators: hidden octaves, e.g. "Direct octaves in bars 3–4: both voices
            # move the same way into an octave".
            text = lambda: _(  # noqa: E731
                'Direct octaves in bars {first}–{second}: both voices move the same way into '
                'an octave'
            ).format(**bars)
        else:
            rule = Rule.DIRECT_FIFTHS
            text = lambda: _(  # noqa: E731
                'Direct fifths in bars {first}–{second}: both voices move the same way into a fifth'
            ).format(**bars)
        self.add(rule, severity, i, text, notes=notes, cantus=cantus, voices=(0, 1))

    def accented(self, i: int) -> None:
        """Perfect consonances on successive downbeats (second, third and fifth species)
        and on successive weak halves after a syncopation (fourth and fifth)."""
        note = self.notes[i]
        if self.species is Species.FIRST:
            return
        if note.strong and i >= 2 and self.species is not Species.FOURTH:
            k = note.downbeat_before
            if 0 <= k < i - 1:
                self.strong_parallels(k, i)
        if note.syncopation:
            self.weak_parallels(i - 1, i)

    def strong_parallels(self, k: int, i: int) -> None:
        heard = {v.rule for v in self.found if v.slot == i}
        a_cp, b_cp = self.line[k], self.line[i]
        a_cf, b_cf = self.under(k), self.under(i)
        cp_move, cf_move = b_cp.midi - a_cp.midi, b_cf.midi - a_cf.midi
        if not cp_move or not cf_move or _sign(cp_move) != _sign(cf_move):
            return
        for simple, rule in ((0, Rule.PARALLEL_OCTAVES), (4, Rule.PARALLEL_FIFTHS)):
            if rule in heard or not (
                _is_perfect(a_cp, a_cf, simple) and _is_perfect(b_cp, b_cf, simple)
            ):
                continue  # not parallel, or already parallel from the note before
            between = self.line[k + 1 : i]
            near = all(abs(p.diatonic_index - a_cp.diatonic_index) <= 2 for p in between)
            severity = (
                Severity.ERROR if self.species is Species.SECOND and near else Severity.WARNING
            )
            bars = {'first': self.notes[k].bar + 1, 'second': self.notes[i].bar + 1}
            if rule is Rule.PARALLEL_OCTAVES:
                # Translators: e.g. "Octaves on the downbeats of bars 3 and 4".
                text = lambda: _(  # noqa: E731
                    'Octaves on the downbeats of bars {first} and {second}'
                ).format(**bars)
            else:
                # Translators: e.g. "Fifths on the downbeats of bars 3 and 4".
                text = lambda: _(  # noqa: E731
                    'Fifths on the downbeats of bars {first} and {second}'
                ).format(**bars)
            self.add(
                rule,
                severity,
                i,
                text,
                notes=(k, i),
                cantus=(self.notes[k].bar, self.notes[i].bar),
                voices=(COUNTERPOINT, CANTUS),
            )

    def weak_parallels(self, k: int, i: int) -> None:
        a_cp, b_cp = self.line[k], self.line[i]
        a_cf, b_cf = self.under(k), self.under(i)
        cp_move, cf_move = b_cp.midi - a_cp.midi, b_cf.midi - a_cf.midi
        if not cp_move or not cf_move or _sign(cp_move) != _sign(cf_move):
            return
        suspended = not is_consonant(a_cp, b_cf)
        for simple, rule in ((0, Rule.PARALLEL_OCTAVES), (4, Rule.PARALLEL_FIFTHS)):
            if not (_is_perfect(a_cp, a_cf, simple) and _is_perfect(b_cp, b_cf, simple)):
                continue
            bars = {'first': self.notes[k].bar + 1, 'second': self.notes[i].bar + 1}
            if rule is Rule.PARALLEL_OCTAVES:
                # Translators: e.g. "Octaves on the weak beats of bars 3 and 4: the
                # suspension does not hide them".
                text = lambda: _(  # noqa: E731
                    'Octaves on the weak beats of bars {first} and {second}: the '
                    'syncopation does not hide them'
                ).format(**bars)
            else:
                text = lambda: _(  # noqa: E731
                    'Fifths on the weak beats of bars {first} and {second}: the '
                    'syncopation does not hide them'
                ).format(**bars)
            octaves = rule is Rule.PARALLEL_OCTAVES
            self.add(
                rule,
                Severity.ERROR if suspended and octaves else Severity.WARNING,
                i,
                text,
                notes=(k, i),
                cantus=(self.notes[k].bar, self.notes[i].bar),
                voices=(COUNTERPOINT, CANTUS),
            )

    def thirds(self, i: int) -> None:
        """More than three thirds or sixths in a row on the downbeats (species 1–3)."""
        if self.species > Species.THIRD:
            return
        run: list[int] = []
        kind: int | None = None
        for k in range(i, -1, -1):
            note = self.notes[k]
            if not note.strong:
                continue
            found = _imperfect(self.line[k], self.under(k))
            if found is None or (kind is not None and found != kind):
                break
            kind = found
            run.append(k)
            if len(run) > 4:
                return  # already reported when the run reached four
        if len(run) == 4:
            first, last = self.notes[run[-1]].bar + 1, self.notes[run[0]].bar + 1
            # Translators: e.g. "Four sixths in a row in bars 3–6".
            if kind == 3:
                text = lambda: _('Four thirds in a row in bars {first}–{last}').format(  # noqa: E731
                    first=first, last=last
                )
            else:
                text = lambda: _('Four sixths in a row in bars {first}–{last}').format(  # noqa: E731
                    first=first, last=last
                )
            self.add(
                Rule.PARALLEL_THIRDS,
                Severity.WARNING,
                i,
                text,
                notes=tuple(reversed(run)),
                cantus=tuple(self.notes[k].bar for k in reversed(run)),
                voices=(COUNTERPOINT, CANTUS),
            )

    # The line ---------------------------------------------------------------------------

    def melodic(self, i: int) -> None:
        a, b = self.line[i - 1], self.line[i]
        notes = (i - 1, i)
        steps = self.ds[i] - self.ds[i - 1]
        semitones = self.ms[i] - self.ms[i - 1]

        def where() -> dict[str, object]:
            return {
                'start': _note(a),
                'end': _note(b),
                'second': self.bar(i),
                'bars': _bars(self.bar(i - 1), self.bar(i)),
            }

        if not steps and not semitones:
            self.repeated(i, notes, where)
            return
        if _altered(steps, semitones):
            self.add(
                Rule.MELODIC_INTERVAL,
                Severity.ERROR,
                i,
                # Translators: e.g. "The counterpoint moves by an augmented fourth, F4 to
                # B4 (bars 3–4)". {interval} is an interval name.
                lambda: _('The counterpoint moves by {interval}, {start} to {end} ({bars})').format(
                    interval=_named(a, b), **where()
                ),
                notes=notes,
            )
        size = abs(steps)
        leap_error = size > 7 or (size == 7 and abs(semitones) > 12) or size == 6
        if size == 5 and abs(semitones) >= 9:
            leap_error = True  # major sixth
        if leap_error:
            self.add(
                Rule.LARGE_LEAP,
                Severity.ERROR,
                i,
                # Translators: e.g. "The counterpoint leaps a major sixth, D4 to B4 (bars
                # 2–3)".
                lambda: _('The counterpoint leaps {interval}, {start} to {end} ({bars})').format(
                    interval=_named(a, b), **where()
                ),
                notes=notes,
            )
        elif size == 5 and semitones < 0:
            self.add(
                Rule.LARGE_LEAP,
                Severity.WARNING,
                i,
                # Translators: e.g. "The counterpoint leaps down a minor sixth, C5 to E4
                # (bars 4–5); the style prefers it rising".
                lambda: _(
                    'The counterpoint leaps down a minor sixth, {start} to {end} '
                    '({bars}); the style prefers it rising'
                ).format(**where()),
                notes=notes,
            )
        eighth = _EIGHTH_LENGTH
        if size > 1 and eighth in (self.notes[i].length, self.notes[i - 1].length):
            self.add(
                Rule.EIGHTH_NOTES,
                Severity.ERROR,
                i,
                # Translators: e.g. "Eighth notes move by step: G4 to D5 in bar 6 leaps".
                lambda: _(
                    'Eighth notes move by step: {start} to {end} in bar {second} leaps'
                ).format(**where()),
                notes=notes,
            )
        if i >= 2:
            self.leaps(i)
            self.outline(i + 1)

    def repeated(
        self, i: int, notes: tuple[int, ...], where: Callable[[], dict[str, object]]
    ) -> None:
        if self.species is Species.FIRST:
            severity = Severity.WARNING
        elif self.species is Species.FIFTH and self.notes[i - 1].length == _QUARTER_LENGTH:
            return  # an anticipation
        else:
            severity = Severity.ERROR
        self.add(
            Rule.REPEATED_NOTE,
            severity,
            i,
            # Translators: e.g. "The counterpoint repeats A4 (bars 1–2)".
            lambda: _('The counterpoint repeats {start} ({bars})').format(**where()),
            notes=notes,
        )

    def leaps(self, i: int) -> None:
        a, b, c = self.line[i - 2], self.line[i - 1], self.line[i]
        first = b.diatonic_index - a.diatonic_index
        second = c.diatonic_index - b.diatonic_index
        if not first or not second or _sign(first) != _sign(second):
            return

        def fields() -> dict[str, str]:
            return {
                'bars': _bars(self.bar(i - 2), self.bar(i)),
                'start': _note(a),
                'middle': _note(b),
                'end': _note(c),
            }

        notes = (i - 2, i - 1, i)
        if abs(first) > 1 and abs(second) > 1:
            span = _interval(a, c)
            steps = abs(second + first)
            wide = steps > 7 or (steps == 7 and abs(c.midi - a.midi) > 12)
            dissonant = (
                span is None
                or wide
                or steps % 7 in (1, 6)
                or span.quality.value in ('d', 'dd', 'A', 'AA')
            )
            if dissonant:
                # Translators: e.g. "Two leaps in one direction, D4 F4 C5, span a seventh
                # (bars 2–4)". {interval} is an interval name.
                text = lambda: _(  # noqa: E731
                    'Two leaps in one direction, {start} {middle} {end}, span {interval} ({bars})'
                ).format(interval=_named(a, c), **fields())
            else:
                text = lambda: _(  # noqa: E731
                    'Two leaps in one direction, {start} {middle} {end} '
                    '({bars}); turning back is smoother'
                ).format(**fields())
            self.add(
                Rule.CONSECUTIVE_LEAPS,
                Severity.ERROR if wide else Severity.WARNING,
                i,
                text,
                notes=notes,
            )
        elif abs(first) >= 4 and abs(second) == 1:
            self.add(
                Rule.LEAP_RECOVERY,
                Severity.WARNING,
                i,
                # Translators: e.g. "After the leap D4 A4 the line goes on upwards to B4
                # (bars 2–4); turn back after a large leap".
                lambda: _(
                    'After the leap {start} {middle} the line goes on to {end} '
                    '({bars}); turn back after a large leap'
                ).format(**fields()),
                notes=notes,
            )

    def outline(self, known: int, *, final: bool = False) -> None:
        """An augmented fourth between the turning point at ``known - 2`` (or the end of
        the line) and the turning point before it."""
        line = self.line
        end = known - 1 if final else known - 2
        if end < 1:
            return
        if not final:
            before = line[end].midi - line[end - 1].midi
            after = line[end + 1].midi - line[end].midi
            if not before or not after or _sign(before) == _sign(after):
                return
        direction = _sign(line[end].midi - line[end - 1].midi)
        if not direction:
            return
        start = end - 1
        while start > 0:
            move = _sign(line[start].midi - line[start - 1].midi)
            if move and move != direction:
                break
            start -= 1
        interval = _interval(line[start], line[end])
        if interval is None or str(interval) != 'A4':
            return

        def fields() -> dict[str, str]:
            return {
                'start': _note(line[start]),
                'end': _note(line[end]),
                'bars': _bars(self.bar(start), self.bar(end)),
            }

        self.add(
            Rule.OUTLINED_TRITONE,
            Severity.WARNING,
            end,
            # Translators: e.g. "The line outlines a tritone, F4 to B4 (bars 3–6)".
            lambda: _('The line outlines a tritone, {start} to {end} ({bars})').format(**fields()),
            notes=(start, end),
        )

    def range(self, i: int) -> None:
        low_now, high_now = self.spans[i]
        low_then, high_then = self.spans[i - 1] if i else (low_now, high_now)
        now, before = high_now - low_now, high_then - low_then
        for limit, severity in ((11, Severity.ERROR), (9, Severity.WARNING)):
            if now > limit >= before:
                low = min(self.line, key=lambda p: (p.diatonic_index, p.midi))
                high = max(self.line, key=lambda p: (p.diatonic_index, p.midi))
                notes = {'low': _note(low), 'high': _note(high)}
                if severity is Severity.ERROR:
                    # Translators: e.g. "The counterpoint spans more than a twelfth, D3 to
                    # B4".
                    text = lambda: _(  # noqa: E731
                        'The counterpoint spans more than a twelfth, {low} to {high}'
                    ).format(**notes)
                else:
                    # Translators: e.g. "The counterpoint spans more than a tenth, D4 to G5".
                    text = lambda: _(  # noqa: E731
                        'The counterpoint spans more than a tenth, {low} to {high}'
                    ).format(**notes)
                self.add(
                    Rule.RANGE,
                    severity,
                    i,
                    text,
                    notes=(self.line.index(low), self.line.index(high)),
                )
                return

    def ficta_ok(self, i: int, known: int | None = None) -> bool | None:
        """Whether note ``i`` belongs to the mode or its ficta, given the first ``known``
        notes; ``None`` until the notes after a raised seventh (or Aeolian sixth) outside
        the cadence show whether it leads to the final within two notes."""
        known = len(self.line) if known is None else known
        name = self.line[i].name
        if name in self.names:
            return True
        if name not in (self.seventh, self.sixth):
            return False
        if self.notes[i].bar >= len(self.cantus) - 2:
            return True  # the cadence
        goal = self.context.mode.tonic if name == self.seventh else self.seventh
        for k in (i + 1, i + 2):
            if k >= len(self.notes):
                return False
            if k >= known:
                return None
            if self.line[k].name == goal:
                return True
        return False

    def mode_notes(self, i: int) -> None:
        if self.ficta_ok(i) is False:
            self.foreign(i)
        for previous in (i - 1, i - 2):
            if (
                previous >= 0
                and self.ficta_ok(previous, i + 1) is False
                and self.ficta_ok(previous, i) is None
            ):
                self.foreign(previous)  # a raised note that did not lead up

    def foreign(self, i: int) -> None:
        pitch = self.line[i]
        if pitch.name in (self.seventh, self.sixth):
            # Translators: e.g. "C♯5 in bar 4 is outside the mode: the raised leading tone
            # belongs to the cadence, or leads to the final".
            text = lambda: _(  # noqa: E731
                '{note} in bar {bar} is outside the mode: the raised leading tone belongs to '
                'the cadence, or leads to the final'
            ).format(note=_note(pitch), bar=self.bar(i))
        else:
            # Translators: e.g. "F♯4 in bar 3 is outside the mode".
            text = lambda: _('{note} in bar {bar} is outside the mode').format(  # noqa: E731
                note=_note(pitch), bar=self.bar(i)
            )
        self.add(Rule.FOREIGN_NOTE, Severity.ERROR, i, text)

    # The whole line ---------------------------------------------------------------------

    def ending(self) -> None:
        n = len(self.line)
        last, cantus = self.line[-1], self.cantus[-1]
        final_bar = len(self.cantus) - 1
        voices = (COUNTERPOINT, CANTUS)
        if not _is_perfect(last, cantus, 0):
            self.add(
                Rule.ENDING,
                Severity.ERROR,
                n - 1,
                # Translators: e.g. "The last interval is a fifth; end on a unison or octave".
                lambda: _('The last interval is {interval}; end on a unison or octave').format(
                    interval=_named(last, cantus)
                ),
                cantus=(final_bar,),
                voices=voices,
            )
            return
        if n < 2 or len(self.cantus) < 2:
            return
        before, cantus_before = self.line[-2], self.cantus[-2]
        cp_move = last.midi - before.midi
        cf_move = cantus.midi - cantus_before.midi
        span = _vertical(before, self.under(n - 2))[0]
        closing = _vertical(last, cantus)[0]
        notes, bars = (n - 2, n - 1), (final_bar - 1, final_bar)
        by_step = abs(last.diatonic_index - before.diatonic_index) == 1 and 0 < abs(cp_move) <= 2
        shape = (span % 7 == 5 and closing > span) or (span % 7 == 2 and closing < span)
        if not (by_step and cf_move and _sign(cp_move) != _sign(cf_move) and shape):
            self.add(
                Rule.CADENCE,
                Severity.ERROR,
                n - 1,
                # Translators: the clausula vera, e.g. "The cadence does not reach the final
                # by step in contrary motion from a sixth or a third".
                lambda: _(
                    'The cadence does not reach the final by step in contrary motion from a '
                    'sixth or a third'
                ),
                notes=notes,
                cantus=bars,
                voices=voices,
            )
            return
        if cp_move <= 0:
            return
        phrygian = self.context.mode.type is ScaleType.PHRYGIAN
        if not phrygian and cp_move != 1:
            leading = last.name.transpose(Interval.parse('m2'), down=True)
            self.add(
                Rule.LEADING_TONE,
                Severity.ERROR,
                n - 2,
                # Translators: e.g. "The cadence needs the raised leading tone: C♯5, not C5".
                lambda: _('The cadence needs the raised leading tone: {right}, not {wrong}').format(
                    right=_note(leading.at(before.octave)), wrong=_note(before)
                ),
                notes=notes,
                cantus=bars,
                voices=voices,
            )
        elif phrygian and cp_move == 1:
            self.add(
                Rule.LEADING_TONE,
                Severity.ERROR,
                n - 2,
                # Translators: e.g. "In the Phrygian cadence the counterpoint rises a whole
                # step: D5, not D♯5".
                lambda: _(
                    'In the Phrygian cadence the counterpoint rises a whole step: {right}, '
                    'not {wrong}'
                ).format(
                    right=_note(last.transpose(Interval.parse('M2'), down=True)),
                    wrong=_note(before),
                ),
                notes=notes,
                cantus=bars,
                voices=voices,
            )

    def climax(self) -> None:
        highest = max(p.midi for p in self.line)
        peaks = [i for i, p in enumerate(self.line) if p.midi == highest]
        if len(peaks) < 2:
            return
        note = self.line[peaks[0]]
        self.add(
            Rule.CLIMAX,
            Severity.WARNING,
            peaks[-1],
            # Translators: e.g. "The highest note, D5, comes 2 times; a single climax shapes
            # the line".
            lambda: _(
                'The highest note, {note}, comes {count} times; a single climax shapes the line'
            ).format(note=_note(note), count=len(peaks)),
            notes=tuple(peaks),
        )


def _checker(
    cantus: Sequence[Pitch], counterpoint: Sequence[Pitch], context: Context, messages: bool
) -> list[Violation]:
    checker = _Checker(cantus, context, messages)
    if len(counterpoint) != len(checker.notes):
        raise ValueError(
            f'the rhythm has {len(checker.notes)} notes, the counterpoint {len(counterpoint)}'
        )
    for pitch in counterpoint:
        checker.step(pitch)
    checker.finish()
    order = list(Rule)
    return sorted(checker.found, key=lambda v: (v.slot, order.index(v.rule)))


def check(
    cantus: Sequence[Pitch], counterpoint: Sequence[Pitch], context: Context
) -> list[Violation]:
    """Every violation in ``counterpoint`` against ``cantus``, sorted by note.

    ``cantus`` has one whole note per bar; ``counterpoint`` one pitch per note of the
    context's rhythm. Raises :class:`ValueError` when they do not fit.
    """
    return _checker(cantus, counterpoint, context, messages=True)


def scan(
    cantus: Sequence[Pitch], counterpoint: Sequence[Pitch], context: Context
) -> list[Violation]:
    """Like :func:`check`, with empty messages: fast, for generators."""
    return _checker(cantus, counterpoint, context, messages=False)


def stepper(cantus: Sequence[Pitch], context: Context) -> _Checker:
    """An incremental checker for searches: ``step(pitch)`` adds a note and returns the
    violations it settles, ``pop()`` takes it back, ``finish()`` checks the end. Messages
    are empty."""
    return _Checker(cantus, context, messages=False)


def errors(violations: Sequence[Violation]) -> list[Violation]:
    """The violations that make an answer wrong."""
    return [v for v in violations if v.severity is Severity.ERROR]


# Cantus firmus ------------------------------------------------------------------------


def check_cantus(cantus: Sequence[Pitch], mode: Scale) -> list[Violation]:
    """A cantus firmus's own rules: it begins and ends on the final, ends 2̂–1̂, stays in
    the mode without ficta, and follows the melodic rules of the counterpoint (repeated
    notes are errors). :attr:`Violation.slot` and ``notes`` index the cantus; messages
    are empty (cantus firmi are generated, not written by learners)."""
    if len(cantus) < 3:
        raise ValueError('a cantus firmus has at least three notes')
    rhythm = Rhythm((WHOLE,) * len(cantus))
    checker = _Checker(cantus, Context(mode, Species.SECOND, rhythm=rhythm, rules=_MELODIC), False)
    for i, pitch in enumerate(cantus):
        checker.push(pitch)
        if i:
            checker.melodic(i)
        checker.range(i)
    checker.outline(len(cantus), final=True)
    checker.climax()
    found = [Violation(v.rule, v.severity, v.slot, (CANTUS,), '', v.notes) for v in checker.found]
    names = frozenset(mode.names())
    for i, pitch in enumerate(cantus):
        if pitch.name not in names:
            found.append(Violation(Rule.FOREIGN_NOTE, Severity.ERROR, i, (CANTUS,), '', (i,)))
    if cantus[0].name != mode.tonic:
        found.append(Violation(Rule.BEGINNING, Severity.ERROR, 0, (CANTUS,), '', (0,)))
    last, before = cantus[-1], cantus[-2]
    if last.name != mode.tonic or not (_is_step(before, last) and before.midi > last.midi):
        n = len(cantus)
        found.append(Violation(Rule.CADENCE, Severity.ERROR, n - 1, (CANTUS,), '', (n - 2, n - 1)))
    order = list(Rule)
    return sorted(found, key=lambda v: (v.slot, order.index(v.rule)))


_MELODIC = frozenset(
    {
        Rule.MELODIC_INTERVAL,
        Rule.LARGE_LEAP,
        Rule.CONSECUTIVE_LEAPS,
        Rule.LEAP_RECOVERY,
        Rule.OUTLINED_TRITONE,
        Rule.RANGE,
        Rule.CLIMAX,
        Rule.REPEATED_NOTE,
    }
)
"""The rules :func:`check_cantus` applies to the line."""
