# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Four-part (SATB) voice-leading rules of common-practice harmony.

The checker reports every rule a progression of four-voice chords breaks,
with the chords and voices involved and a translated explanation, so the
exercise page can mark the problem on the staff and say why it matters.
The rules and their defaults follow the conventions of Kostka–Payne
(*Tonal Harmony*, ch. 5–6, 13) and Aldwell–Schachter (*Harmony and Voice
Leading*, ch. 4–5); where textbooks differ the stricter common reading is
used and documented here.

Voices are numbered from the top: 0 soprano, 1 alto, 2 tenor, 3 bass. A
progression is a sequence of chords, one per slot, each a tuple of four
pitches in that order.

Decisions (severity in brackets; an *error* makes an answer wrong, a
*warning* is mentioned but not penalised):

* **Parallel fifths and octaves** [error] between any two voices,
  including unisons and compound intervals. Consecutive fifths or octaves
  by *contrary* motion (P5 → P12, P8 → P15) are errors too: both books
  ask students to avoid them in four-part exercises. Repeating the same
  two pitch classes (an octave leap in one voice) is not a parallel.
* **Unequal fifths**: P5 → d5 is allowed in the upper voices and a
  warning when it involves the bass; d5 → P5 is an error when it involves
  the bass and a warning otherwise (Kostka–Payne, ch. 6).
* **Direct (hidden) octaves** between the outer voices, approached by
  similar motion with a leap in the soprano [error]; **direct fifths** in
  the same situation [warning], as Aldwell–Schachter treat them as less
  objectionable. Inner voices are free.
* **Crossing** [error]; **overlap** [warning] (Aldwell–Schachter call it
  less serious than crossing).
* **Spacing**: more than an octave between soprano and alto or alto and
  tenor [error]; tenor and bass are free.
* **Range** [error], with the ranges of :class:`Ranges` (Kostka–Payne).
* **Doubling**: the leading tone of a dominant-function chord (V, vii°
  and their sevenths) and any chordal seventh are never doubled [error].
  A doubled third in a root-position major triad is a warning, except
  after a root a step below (V–vi, V–VI), where it is the rule.
* **Incomplete chords**: a missing root, third or seventh is an error. The
  omitted fifth of a root-position seventh chord is normal; of a
  root-position triad a warning, except right after a dominant seventh,
  whose complete form resolves to an incomplete tonic. An inverted triad
  without its fifth is a warning, an inverted seventh chord an error.
* **Leading tone**: in V(7)–I and vii°(7)–I the leading tone in an outer
  voice rises to the tonic [error]; in an inner voice it may drop a third
  to the fifth of the tonic (the "frustrated" leading tone), other
  motions are a warning. In V–vi (V–VI) it rises in every voice [error].
* **Chordal seventh** resolves down by step [error] when the harmony
  changes. In V4/3–I6 it may rise by step [warning] (Kostka–Payne).
* **Augmented melodic intervals** (A2, A4, A5 …; not chromatic semitones)
  in any voice [error].
* **Large leaps**: more than an octave in any voice [error]; more than a
  fourth in an inner voice [warning].
"""

# Messages are passed to _Checker.add() as lambdas that it calls at once (or never, in
# scan()), so the loop variables they use cannot change before the call.
# ruff: noqa: B023

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from gettext import gettext as _
from gettext import ngettext, pgettext

from ..core import Pitch
from ..core.chord import Chord, ChordKind, ChordQuality
from ..core.interval import Interval, Quality
from ..core.naming import chord_name, interval_name, pitch_name
from ..core.pitch import PitchName
from ..core.scale import Key

SOPRANO, ALTO, TENOR, BASS = 0, 1, 2, 3
VOICES = (SOPRANO, ALTO, TENOR, BASS)


class Severity(Enum):
    ERROR = 'error'
    """Breaks the style: the answer is wrong."""
    WARNING = 'warning'
    """Allowed but weak, or allowed only in particular contexts: mentioned, not penalised."""


class Rule(Enum):
    """Every rule the checker knows. The value is a stable id for settings and tests."""

    WRONG_CHORD = 'wrong-chord'
    """The pitches do not form the chord asked for (``harmony``)."""
    INCOMPLETE_CHORD = 'incomplete-chord'
    """A chord tone is missing (see the module documentation for the omitted fifth)."""
    WRONG_DOUBLING = 'wrong-doubling'
    """A tendency tone (leading tone, chordal seventh) is doubled."""
    RANGE = 'range'
    """A voice leaves its range (:class:`Ranges`)."""
    SPACING = 'spacing'
    """More than an octave between adjacent upper voices (S–A, A–T)."""
    CROSSING = 'crossing'
    """A lower voice sounds above a higher one."""
    OVERLAP = 'overlap'
    """A voice moves past the previous note of an adjacent voice."""
    PARALLEL_FIFTHS = 'parallel-fifths'
    PARALLEL_OCTAVES = 'parallel-octaves'
    """Includes parallel unisons and compound octaves."""
    DIRECT_FIFTHS = 'direct-fifths'
    """Hidden fifths between the outer voices with a leap in the soprano."""
    DIRECT_OCTAVES = 'direct-octaves'
    """Hidden octaves between the outer voices with a leap in the soprano."""
    LEADING_TONE = 'leading-tone'
    """The leading tone in an outer voice of V–I does not rise to the tonic."""
    CHORDAL_SEVENTH = 'chordal-seventh'
    """A chordal seventh does not resolve down by step."""
    AUGMENTED_SECOND = 'augmented-second'
    """A voice moves by an augmented second (or another augmented interval)."""
    LARGE_LEAP = 'large-leap'
    """An inner voice leaps more than a fourth, or any voice more than an octave."""


MOTION_RULES = frozenset(
    {
        Rule.OVERLAP,
        Rule.PARALLEL_FIFTHS,
        Rule.PARALLEL_OCTAVES,
        Rule.DIRECT_FIFTHS,
        Rule.DIRECT_OCTAVES,
        Rule.LEADING_TONE,
        Rule.CHORDAL_SEVENTH,
        Rule.AUGMENTED_SECOND,
        Rule.LARGE_LEAP,
    }
)
"""Rules about the motion from one chord to the next: their violations involve the
chord before :attr:`Violation.slot` as well."""


@dataclass(frozen=True, slots=True)
class Ranges:
    """Lowest and highest pitch of each voice, soprano first (Kostka–Payne)."""

    soprano: tuple[Pitch, Pitch] = (Pitch.parse('C4'), Pitch.parse('G5'))
    alto: tuple[Pitch, Pitch] = (Pitch.parse('G3'), Pitch.parse('C5'))
    tenor: tuple[Pitch, Pitch] = (Pitch.parse('C3'), Pitch.parse('G4'))
    bass: tuple[Pitch, Pitch] = (Pitch.parse('E2'), Pitch.parse('C4'))

    def of(self, voice: int) -> tuple[Pitch, Pitch]:
        return (self.soprano, self.alto, self.tenor, self.bass)[voice]


@dataclass(frozen=True, slots=True)
class Violation:
    rule: Rule
    severity: Severity
    slot: int
    """The chord where the problem is heard (the second chord of a motion)."""
    voices: tuple[int, ...]
    """Voices involved, e.g. ``(SOPRANO, BASS)`` for parallel octaves."""
    message: str
    """Translated explanation, e.g. "Parallel fifths between alto and bass (chords 2–3)"."""

    @property
    def slots(self) -> tuple[int, ...]:
        """Chords involved: the slot, and for motion rules the chord before it."""
        if self.rule in MOTION_RULES and self.slot > 0:
            return (self.slot - 1, self.slot)
        return (self.slot,)


@dataclass(frozen=True, slots=True)
class Context:
    """What the checker needs to know besides the notes."""

    key: Key | None = None
    """Needed for leading-tone and seventh resolution rules."""
    harmony: Sequence[Chord | None] = field(default=())
    """The chord each slot should be (from a Roman numeral or figured bass); ``None``
    or a shorter sequence skips chord-membership checks for those slots."""
    ranges: Ranges = field(default_factory=Ranges)
    rules: frozenset[Rule] = frozenset(Rule)
    """Rules to apply; exercises switch some off for earlier stages."""


# Names --------------------------------------------------------------------------------


def voice_name(voice: int) -> str:
    """Lower-case voice name for use inside a sentence: "soprano", "alto" …"""
    return (
        pgettext('voice', 'soprano'),
        pgettext('voice', 'alto'),
        pgettext('voice', 'tenor'),
        pgettext('voice', 'bass'),
    )[voice]


def voice_title(voice: int) -> str:
    """Capitalised voice name for labels: "Soprano", "Alto" …"""
    return (
        pgettext('voice', 'Soprano'),
        pgettext('voice', 'Alto'),
        pgettext('voice', 'Tenor'),
        pgettext('voice', 'Bass'),
    )[voice]


def rule_name(rule: Rule) -> str:
    """Name of a rule's violation, e.g. "Parallel fifths" (answer options, lists)."""
    names: dict[Rule, Callable[[], str]] = {
        Rule.WRONG_CHORD: lambda: _('Wrong chord'),
        Rule.INCOMPLETE_CHORD: lambda: _('Incomplete chord'),
        Rule.WRONG_DOUBLING: lambda: _('Wrong doubling'),
        Rule.RANGE: lambda: _('Out of range'),
        Rule.SPACING: lambda: _('Spacing'),
        Rule.CROSSING: lambda: _('Voice crossing'),
        Rule.OVERLAP: lambda: _('Voice overlap'),
        Rule.PARALLEL_FIFTHS: lambda: _('Parallel fifths'),
        Rule.PARALLEL_OCTAVES: lambda: _('Parallel octaves'),
        Rule.DIRECT_FIFTHS: lambda: _('Direct fifths'),
        Rule.DIRECT_OCTAVES: lambda: _('Direct octaves'),
        Rule.LEADING_TONE: lambda: _('Unresolved leading tone'),
        Rule.CHORDAL_SEVENTH: lambda: _('Unresolved seventh'),
        Rule.AUGMENTED_SECOND: lambda: _('Augmented leap'),
        Rule.LARGE_LEAP: lambda: _('Large leap'),
    }
    return names[rule]()


def rule_mark(rule: Rule) -> str:
    """A short mark written under the staff where the rule is broken, e.g. "∥5"."""
    # Translators: short marks written on the staff under a voice-leading mistake, as a
    # teacher would mark it. Keep them very short (a few characters).
    ctx = 'voice-leading mark'
    marks: dict[Rule, Callable[[], str]] = {
        Rule.WRONG_CHORD: lambda: pgettext(ctx, 'chord'),
        Rule.INCOMPLETE_CHORD: lambda: pgettext(ctx, 'missing'),
        Rule.WRONG_DOUBLING: lambda: pgettext(ctx, 'double'),
        Rule.RANGE: lambda: pgettext(ctx, 'range'),
        Rule.SPACING: lambda: pgettext(ctx, 'space'),
        Rule.CROSSING: lambda: pgettext(ctx, 'cross'),
        Rule.OVERLAP: lambda: pgettext(ctx, 'overlap'),
        Rule.PARALLEL_FIFTHS: lambda: pgettext(ctx, '∥5'),
        Rule.PARALLEL_OCTAVES: lambda: pgettext(ctx, '∥8'),
        Rule.DIRECT_FIFTHS: lambda: pgettext(ctx, '→5'),
        Rule.DIRECT_OCTAVES: lambda: pgettext(ctx, '→8'),
        Rule.LEADING_TONE: lambda: pgettext(ctx, 'LT'),
        Rule.CHORDAL_SEVENTH: lambda: pgettext(ctx, '7th'),
        Rule.AUGMENTED_SECOND: lambda: pgettext(ctx, 'aug'),
        Rule.LARGE_LEAP: lambda: pgettext(ctx, 'leap'),
    }
    return marks[rule]()


def rule_reason(rule: Rule) -> str:
    """Why the rule matters, in a sentence for feedback."""
    reasons: dict[Rule, Callable[[], str]] = {
        Rule.WRONG_CHORD: lambda: _('Every note must belong to the chord the numeral asks for.'),
        Rule.INCOMPLETE_CHORD: lambda: _(
            'Without its third (or root, or seventh) a chord loses its quality and function.'
        ),
        Rule.WRONG_DOUBLING: lambda: _(
            'The leading tone and a chordal seventh each have one way to resolve; doubled, '
            'they resolve into parallel octaves or one of them goes astray.'
        ),
        Rule.RANGE: lambda: _('Singers cannot reach notes far outside their range comfortably.'),
        Rule.SPACING: lambda: _(
            'More than an octave between upper voices leaves a hole in the chord; keep '
            'soprano, alto and tenor within an octave of their neighbours.'
        ),
        Rule.CROSSING: lambda: _(
            'When a lower voice sounds above a higher one, the ear loses track of who sings '
            'which line.'
        ),
        Rule.OVERLAP: lambda: _(
            'Moving past the note a neighbouring voice just sang blurs the two lines.'
        ),
        Rule.PARALLEL_FIFTHS: lambda: _(
            'Two voices moving in perfect fifths sound like one thickened voice and break the '
            'independence of the parts.'
        ),
        Rule.PARALLEL_OCTAVES: lambda: _(
            'Two voices moving in octaves or unisons merge into one, so four parts become three.'
        ),
        Rule.DIRECT_FIFTHS: lambda: _(
            'Leaping into a fifth with the bass in similar motion makes the outer voices sound '
            'hollow.'
        ),
        Rule.DIRECT_OCTAVES: lambda: _(
            'Leaping into an octave with the bass in similar motion stresses the octave as if '
            'it were a parallel.'
        ),
        Rule.LEADING_TONE: lambda: _(
            'The leading tone is a semitone below the tonic and pulls up to it; in an outer '
            'voice the ear expects that resolution.'
        ),
        Rule.CHORDAL_SEVENTH: lambda: _(
            'A chordal seventh is a dissonance; it resolves down by step into the next chord.'
        ),
        Rule.AUGMENTED_SECOND: lambda: _(
            'Augmented intervals are awkward to sing; move by step or choose another chord tone.'
        ),
        Rule.LARGE_LEAP: lambda: _(
            'Inner voices move smoothly; large leaps make them hard to sing and to follow.'
        ),
    }
    return reasons[rule]()


def _missing(role: int) -> str:
    return (
        _('Chord {n} has no root ({note})'),
        _('Chord {n} has no third ({note})'),
        _('Chord {n} has no fifth ({note})'),
        _('Chord {n} has no seventh ({note})'),
    )[role]


def _note(pitch: Pitch) -> str:
    return pitch_name(pitch.name) + str(pitch.octave)


def _names(pitches: Sequence[PitchName]) -> str:
    # Translators: separator between note names in a list such as "F♯, A".
    return _(', ').join(pitch_name(p) for p in pitches)


# Checking -----------------------------------------------------------------------------


@lru_cache(maxsize=1024)
def _tones(chord: Chord) -> tuple[PitchName, ...]:
    return chord.names()


@lru_cache(maxsize=256)
def _leading(key: Key) -> PitchName:
    return key.leading_tone


@lru_cache(maxsize=1024)
def _degree(key: Key, degree: int) -> PitchName:
    return key.degree(degree)


@dataclass(frozen=True, slots=True)
class _Harmony:
    chord: Chord
    given: bool
    """Taken from :attr:`Context.harmony` (``False``: identified from the notes)."""

    def role(self, pitch: Pitch) -> int | None:
        """0 root, 1 third, 2 fifth, 3 seventh; ``None`` for a note outside the chord."""
        names = _tones(self.chord)
        return names.index(pitch.name) if pitch.name in names else None

    @property
    def seventh(self) -> PitchName | None:
        if self.chord.quality.kind is ChordKind.SEVENTH:
            return _tones(self.chord)[3]
        return None


def _harmony(slot: int, chord: Sequence[Pitch], context: Context) -> _Harmony | None:
    if slot < len(context.harmony):
        given = context.harmony[slot]
        if given is not None:
            return _Harmony(given, True)
    bass = min(chord).name
    found = _identify((bass, *sorted({p.name for p in chord} - {bass}, key=str)))
    return None if found is None else _Harmony(found, False)


@lru_cache(maxsize=1024)
def _identify(names: tuple[PitchName, ...]) -> Chord | None:
    """The triad or seventh chord of ``names`` (bass first), if they spell one."""
    for candidate in Chord.identify(names):
        if candidate.quality.is_tertian:
            return candidate
    return None


def _is_perfect_fifth(low: Pitch, high: Pitch) -> bool:
    steps, semitones = _span(low, high)
    return steps % 7 == 4 and semitones % 12 == 7


def _is_diminished_fifth(low: Pitch, high: Pitch) -> bool:
    steps, semitones = _span(low, high)
    return steps % 7 == 4 and semitones % 12 == 6


def _is_octave(low: Pitch, high: Pitch) -> bool:
    steps, semitones = _span(low, high)
    return steps % 7 == 0 and semitones % 12 == 0


def _span(a: Pitch, b: Pitch) -> tuple[int, int]:
    """Diatonic steps and semitones between two pitches, regardless of order."""
    return abs(b.diatonic_index - a.diatonic_index), abs(b.midi - a.midi)


_FIFTHS_AND_OCTAVES = frozenset({(0, 0), (7, 7), (7, 6), (6, 7)})
"""Semitone classes (mod 12) of two successive intervals that may form parallels."""


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


class _Checker:
    def __init__(
        self,
        chords: Sequence[tuple[Pitch, ...]],
        context: Context,
        messages: bool,
        first: int = 0,
    ) -> None:
        self.chords = chords
        self.messages = messages
        self.first = first
        self.context = context
        self.harmonies = [_harmony(i, c, context) for i, c in enumerate(chords)]
        self.midi = [tuple(p.midi for p in chord) for chord in chords]
        self.found: list[Violation] = []

    def add(
        self,
        rule: Rule,
        severity: Severity,
        slot: int,
        voices: tuple[int, ...],
        message: Callable[[], str],
    ) -> None:
        """Record a violation; ``message`` is only called when messages are wanted
        (gettext is slow, and generators check thousands of voicings)."""
        if rule in self.context.rules:
            text = message() if self.messages else ''
            self.found.append(Violation(rule, severity, slot, voices, text))

    def run(self) -> list[Violation]:
        for slot, chord in enumerate(self.chords):
            if slot < self.first:
                continue
            self.chord(slot, chord)
            if slot:
                self.motion(slot, self.chords[slot - 1], chord)
        order = list(Rule)
        self.found.sort(key=lambda v: (v.slot, order.index(v.rule), v.voices))
        return self.found

    # One chord -------------------------------------------------------------------------

    def chord(self, slot: int, chord: Sequence[Pitch]) -> None:
        n = slot + 1
        ranges = self.context.ranges
        for voice, pitch in enumerate(chord):
            low, high = ranges.of(voice)
            if pitch.midi < low.midi:
                self.add(
                    Rule.RANGE,
                    Severity.ERROR,
                    slot,
                    (voice,),
                    # Translators: e.g. "The bass's D2 is below its range (lowest E2) in chord 3".
                    lambda: _(
                        "The {voice}'s {note} is below its range (lowest {limit}) in chord {n}"
                    ).format(voice=voice_name(voice), note=_note(pitch), limit=_note(low), n=n),
                )
            elif pitch.midi > high.midi:
                self.add(
                    Rule.RANGE,
                    Severity.ERROR,
                    slot,
                    (voice,),
                    # Translators: e.g. "The soprano's A5 is above its range (highest G5) in
                    # chord 2".
                    lambda: _(
                        "The {voice}'s {note} is above its range (highest {limit}) in chord {n}"
                    ).format(voice=voice_name(voice), note=_note(pitch), limit=_note(high), n=n),
                )
        for upper in (SOPRANO, ALTO, TENOR):
            lower = upper + 1
            if chord[upper].midi < chord[lower].midi:
                self.add(
                    Rule.CROSSING,
                    Severity.ERROR,
                    slot,
                    (upper, lower),
                    # Translators: e.g. "Voice crossing: the tenor is above the alto in chord 2".
                    lambda: _(
                        'Voice crossing: the {lower} is above the {upper} in chord {n}'
                    ).format(lower=voice_name(lower), upper=voice_name(upper), n=n),
                )
        for upper in (SOPRANO, ALTO):
            lower = upper + 1
            if chord[upper].midi - chord[lower].midi > 12:
                self.add(
                    Rule.SPACING,
                    Severity.ERROR,
                    slot,
                    (upper, lower),
                    # Translators: e.g. "More than an octave between soprano and alto in chord 3".
                    lambda: _(
                        'More than an octave between {upper} and {lower} in chord {n}'
                    ).format(upper=voice_name(upper), lower=voice_name(lower), n=n),
                )
        harmony = self.harmonies[slot]
        if harmony is None:
            return
        if harmony.given:
            self.membership(slot, chord, harmony)
        self.doubling(slot, chord, harmony)

    def membership(self, slot: int, chord: Sequence[Pitch], harmony: _Harmony) -> None:
        if Rule.WRONG_CHORD in self.context.rules:
            self.foreign(slot, chord, harmony)
        if Rule.INCOMPLETE_CHORD in self.context.rules:
            self.incomplete(slot, chord, harmony)

    def foreign(self, slot: int, chord: Sequence[Pitch], harmony: _Harmony) -> None:
        """Notes outside the chord, and a bass that is not the chord's bass."""
        n = slot + 1
        expected = harmony.chord
        outside = [v for v, p in enumerate(chord) if harmony.role(p) is None]
        if outside:
            notes = list(dict.fromkeys(chord[v].name for v in outside))
            self.add(
                Rule.WRONG_CHORD,
                Severity.ERROR,
                slot,
                tuple(outside),
                # Translators: e.g. "Chord 2 should be G major triad: F♯ is not in it".
                lambda: ngettext(
                    'Chord {n} should be {chord}: {notes} is not in it',
                    'Chord {n} should be {chord}: {notes} are not in it',
                    len(notes),
                ).format(n=n, chord=chord_name(expected), notes=_names(notes)),
            )
        bass = chord[BASS]
        if harmony.role(bass) is not None and bass.name != expected.bass:
            self.add(
                Rule.WRONG_CHORD,
                Severity.ERROR,
                slot,
                (BASS,),
                # Translators: e.g. "The bass of chord 3 should be B for this inversion".
                lambda: _('The bass of chord {n} should be {note} for this inversion').format(
                    n=n, note=pitch_name(expected.bass)
                ),
            )

    def incomplete(self, slot: int, chord: Sequence[Pitch], harmony: _Harmony) -> None:
        n = slot + 1
        expected = harmony.chord
        present = {p.name for p in chord}
        tones = _tones(expected)
        if expected.quality.kind not in (ChordKind.TRIAD, ChordKind.SEVENTH):
            return
        for role, tone in enumerate(tones):
            if tone in present:
                continue
            severity: Severity | None = Severity.ERROR
            if role == 2:
                severity = self.omitted_fifth(slot, expected)
            if severity is None:
                continue
            self.add(
                Rule.INCOMPLETE_CHORD,
                severity,
                slot,
                (),
                lambda: _missing(role).format(n=n, note=pitch_name(tone)),
            )

    def omitted_fifth(self, slot: int, chord: Chord) -> Severity | None:
        seventh = chord.quality.kind is ChordKind.SEVENTH
        if chord.inversion:
            return Severity.ERROR if seventh else Severity.WARNING
        if seventh:
            return None
        previous = self.harmonies[slot - 1] if slot else None
        if previous is not None and previous.seventh is not None:
            return None  # a complete V7 resolves to an incomplete tonic
        return Severity.WARNING

    def doubling(self, slot: int, chord: Sequence[Pitch], harmony: _Harmony) -> None:
        n = slot + 1
        counts: dict[PitchName, list[int]] = {}
        for voice, pitch in enumerate(chord):
            counts.setdefault(pitch.name, []).append(voice)
        key = self.context.key
        if key is not None and self.is_dominant(harmony):
            voices = counts.get(_leading(key), [])
            if len(voices) > 1:
                self.add(
                    Rule.WRONG_DOUBLING,
                    Severity.ERROR,
                    slot,
                    tuple(voices),
                    # Translators: e.g. "The leading tone (B) is doubled in chord 2".
                    lambda: _('The leading tone ({note}) is doubled in chord {n}').format(
                        note=pitch_name(_leading(key)), n=n
                    ),
                )
        seventh = harmony.seventh
        if seventh is not None and len(counts.get(seventh, [])) > 1:
            self.add(
                Rule.WRONG_DOUBLING,
                Severity.ERROR,
                slot,
                tuple(counts[seventh]),
                # Translators: e.g. "The chordal seventh (F) is doubled in chord 3".
                lambda: _('The chordal seventh ({note}) is doubled in chord {n}').format(
                    note=pitch_name(seventh), n=n
                ),
            )
        chord_ = harmony.chord
        if chord_.quality is ChordQuality.MAJOR and chord_.inversion == 0:
            third = _tones(chord_)[1]
            voices = counts.get(third, [])
            if (
                len(voices) > 1
                and not self.after_step_below(slot, chord_)
                and (key is None or third != _leading(key))
            ):
                self.add(
                    Rule.WRONG_DOUBLING,
                    Severity.WARNING,
                    slot,
                    tuple(voices),
                    # Translators: e.g. "The third (E) of a root-position major triad is
                    # doubled in chord 1; double the root instead".
                    lambda: _(
                        'The third ({note}) of a root-position major triad is doubled in '
                        'chord {n}; double the root instead'
                    ).format(note=pitch_name(third), n=n),
                )

    def after_step_below(self, slot: int, chord: Chord) -> bool:
        """The previous chord's root is a step below (V–vi): doubling the third is right."""
        previous = self.harmonies[slot - 1] if slot else None
        if previous is None:
            return False
        return (chord.root.letter - previous.chord.root.letter) % 7 == 1

    def is_dominant(self, harmony: _Harmony) -> bool:
        """V, vii° and their sevenths in the context key."""
        key = self.context.key
        if key is None:
            return False
        chord = harmony.chord
        return _leading(key) in _tones(chord) and chord.root in (
            _degree(key, 5),
            _leading(key),
        )

    # Motion ---------------------------------------------------------------------------

    def motion(self, slot: int, before: Sequence[Pitch], after: Sequence[Pitch]) -> None:
        first, second = slot, slot + 1
        for upper in VOICES:
            for lower in VOICES[upper + 1 :]:
                self.parallels(slot, before, after, upper, lower)
        self.direct(slot, before, after)
        for upper in (SOPRANO, ALTO, TENOR):
            lower = upper + 1
            if after[lower].midi > before[upper].midi or after[upper].midi < before[lower].midi:
                self.add(
                    Rule.OVERLAP,
                    Severity.WARNING,
                    slot,
                    (upper, lower),
                    # Translators: e.g. "The alto and tenor overlap (chords 2–3)".
                    lambda: _('The {upper} and {lower} overlap (chords {first}–{second})').format(
                        upper=voice_name(upper), lower=voice_name(lower), first=first, second=second
                    ),
                )
        for voice in VOICES:
            self.melodic(slot, voice, before[voice], after[voice])
        self.leading_tone(slot, before, after)
        self.seventh(slot, before, after)

    def parallels(
        self,
        slot: int,
        before: Sequence[Pitch],
        after: Sequence[Pitch],
        upper: int,
        lower: int,
    ) -> None:
        a_midi, b_midi = self.midi[slot - 1], self.midi[slot]
        intervals = (
            abs(a_midi[upper] - a_midi[lower]) % 12,
            abs(b_midi[upper] - b_midi[lower]) % 12,
        )
        if intervals not in _FIFTHS_AND_OCTAVES:
            return  # quick test by sound; spelling is checked below
        a_up, a_low, b_up, b_low = before[upper], before[lower], after[upper], after[lower]
        if a_up == b_up or a_low == b_low:
            return  # one voice holds its note: oblique motion
        if a_up.name == b_up.name and a_low.name == b_low.name:
            return  # the same two pitch classes, displaced by an octave
        contrary = _sign(b_up.midi - a_up.midi) != _sign(b_low.midi - a_low.midi)

        def message(template: Callable[[], str]) -> Callable[[], str]:
            return lambda: template().format(
                upper=voice_name(upper), lower=voice_name(lower), first=slot, second=slot + 1
            )

        if _is_octave(a_low, a_up) and _is_octave(b_low, b_up):
            unison = a_up.midi == a_low.midi and b_up.midi == b_low.midi
            if contrary:
                # Translators: e.g. "Octaves by contrary motion between soprano and bass
                # (chords 3–4)".
                text = message(
                    lambda: _(
                        'Octaves by contrary motion between {upper} and {lower} '
                        '(chords {first}–{second})'
                    )
                )
            elif unison:
                text = message(
                    lambda: _(
                        'Parallel unisons between {upper} and {lower} (chords {first}–{second})'
                    )
                )
            else:
                # Translators: e.g. "Parallel octaves between soprano and bass (chords 1–2)".
                text = message(
                    lambda: _(
                        'Parallel octaves between {upper} and {lower} (chords {first}–{second})'
                    )
                )
            self.add(Rule.PARALLEL_OCTAVES, Severity.ERROR, slot, (upper, lower), text)
            return
        fifth_before = _is_perfect_fifth(a_low, a_up)
        fifth_after = _is_perfect_fifth(b_low, b_up)
        if fifth_before and fifth_after:
            if contrary:
                text = message(
                    lambda: _(
                        'Fifths by contrary motion between {upper} and {lower} '
                        '(chords {first}–{second})'
                    )
                )
            else:
                # Translators: e.g. "Parallel fifths between alto and bass (chords 2–3)".
                text = message(
                    lambda: _(
                        'Parallel fifths between {upper} and {lower} (chords {first}–{second})'
                    )
                )
            self.add(Rule.PARALLEL_FIFTHS, Severity.ERROR, slot, (upper, lower), text)
        elif fifth_before and _is_diminished_fifth(b_low, b_up):
            if lower == BASS:
                self.add(
                    Rule.PARALLEL_FIFTHS,
                    Severity.WARNING,
                    slot,
                    (upper, lower),
                    message(
                        # Translators: unequal fifths: a perfect fifth followed by a diminished
                        # one.
                        lambda: _(
                            'Unequal fifths (perfect to diminished) between {upper} and {lower} '
                            '(chords {first}–{second}) involve the bass'
                        )
                    ),
                )
        elif _is_diminished_fifth(a_low, a_up) and fifth_after:
            self.add(
                Rule.PARALLEL_FIFTHS,
                Severity.ERROR if lower == BASS else Severity.WARNING,
                slot,
                (upper, lower),
                message(
                    # Translators: unequal fifths: a diminished fifth followed by a perfect one.
                    lambda: _(
                        'Unequal fifths (diminished to perfect) between {upper} and {lower} '
                        '(chords {first}–{second})'
                    )
                ),
            )

    def direct(self, slot: int, before: Sequence[Pitch], after: Sequence[Pitch]) -> None:
        a_up, a_low, b_up, b_low = before[SOPRANO], before[BASS], after[SOPRANO], after[BASS]
        up_motion, low_motion = b_up.midi - a_up.midi, b_low.midi - a_low.midi
        if not up_motion or not low_motion or _sign(up_motion) != _sign(low_motion):
            return
        if abs(b_up.diatonic_index - a_up.diatonic_index) <= 1:
            return  # the soprano moves by step
        fields = {'first': slot, 'second': slot + 1}
        if _is_octave(b_low, b_up) and not _is_octave(a_low, a_up):
            self.add(
                Rule.DIRECT_OCTAVES,
                Severity.ERROR,
                slot,
                (SOPRANO, BASS),
                # Translators: hidden octaves; e.g. "Direct octaves between soprano and bass:
                # both move the same way and the soprano leaps (chords 3–4)".
                lambda: _(
                    'Direct octaves between soprano and bass: both move the same way and the '
                    'soprano leaps (chords {first}–{second})'
                ).format(**fields),
            )
        elif _is_perfect_fifth(b_low, b_up) and not _is_perfect_fifth(a_low, a_up):
            self.add(
                Rule.DIRECT_FIFTHS,
                Severity.WARNING,
                slot,
                (SOPRANO, BASS),
                lambda: _(
                    'Direct fifths between soprano and bass: both move the same way and the '
                    'soprano leaps (chords {first}–{second})'
                ).format(**fields),
            )

    def melodic(self, slot: int, voice: int, before: Pitch, after: Pitch) -> None:
        if before.diatonic_index == after.diatonic_index:
            return  # repeated note or chromatic semitone
        low, high = (
            (before, after) if before.diatonic_index < after.diatonic_index else (after, before)
        )

        def fields() -> dict[str, object]:
            return {
                'voice': voice_name(voice),
                'first': slot,
                'second': slot + 1,
                'start': _note(before),
                'end': _note(after),
            }

        try:
            interval: Interval | None = Interval.between(low, high)
        except ValueError:
            interval = None
        if interval is not None and interval.quality in (
            Quality.AUGMENTED,
            Quality.DOUBLY_AUGMENTED,
        ):
            leap = interval

            def named() -> str:
                try:
                    return interval_name(leap)
                except ValueError:
                    return str(leap)

            self.add(
                Rule.AUGMENTED_SECOND,
                Severity.ERROR,
                slot,
                (voice,),
                # Translators: e.g. "The alto moves by an augmented second, A♭4 to B4
                # (chords 2–3)". {interval} is an interval name.
                lambda: _(
                    'The {voice} moves by an {interval}, {start} to {end} (chords {first}–{second})'
                ).format(interval=named(), **fields()),
            )
        semitones = abs(after.midi - before.midi)
        steps = abs(after.diatonic_index - before.diatonic_index)
        if semitones > 12:
            self.add(
                Rule.LARGE_LEAP,
                Severity.ERROR,
                slot,
                (voice,),
                # Translators: e.g. "The bass leaps more than an octave, C3 to E4 (chords 1–2)".
                lambda: _(
                    'The {voice} leaps more than an octave, {start} to {end} '
                    '(chords {first}–{second})'
                ).format(**fields()),
            )
        elif voice in (ALTO, TENOR) and steps > 3:
            self.add(
                Rule.LARGE_LEAP,
                Severity.WARNING,
                slot,
                (voice,),
                # Translators: e.g. "The tenor leaps more than a fourth, G3 to E4 (chords 1–2)".
                lambda: _(
                    'The {voice} leaps more than a fourth, {start} to {end} '
                    '(chords {first}–{second})'
                ).format(**fields()),
            )

    def leading_tone(self, slot: int, before: Sequence[Pitch], after: Sequence[Pitch]) -> None:
        key = self.context.key
        first, second = self.harmonies[slot - 1], self.harmonies[slot]
        if key is None or first is None or second is None or not self.is_dominant(first):
            return
        tonic = second.chord.root == key.tonic
        deceptive = second.chord.root == _degree(key, 6) and first.chord.root == _degree(key, 5)
        if not (tonic or deceptive):
            return
        for voice in VOICES:
            pitch = before[voice]
            if pitch.name != _leading(key):
                continue
            target = after[voice]
            if target.name == key.tonic and target.midi - pitch.midi == 1:
                continue
            severity = Severity.ERROR
            if tonic and voice in (ALTO, TENOR):
                frustrated = target.name == _degree(key, 5) and 0 < pitch.midi - target.midi <= 4
                if frustrated:
                    continue
                severity = Severity.WARNING
            self.add(
                Rule.LEADING_TONE,
                severity,
                slot,
                (voice,),
                # Translators: e.g. "The leading tone (B) in the soprano does not rise to the
                # tonic (chords 3–4)".
                lambda: _(
                    'The leading tone ({note}) in the {voice} does not rise to the tonic '
                    '(chords {first}–{second})'
                ).format(
                    note=pitch_name(_leading(key)),
                    voice=voice_name(voice),
                    first=slot,
                    second=slot + 1,
                ),
            )

    def seventh(self, slot: int, before: Sequence[Pitch], after: Sequence[Pitch]) -> None:
        first, second = self.harmonies[slot - 1], self.harmonies[slot]
        if first is None or second is None or first.seventh is None:
            return
        if (first.chord.root, first.chord.quality) == (second.chord.root, second.chord.quality):
            return  # the same harmony continues: the resolution may come later
        key = self.context.key
        seventh = first.seventh
        for voice in VOICES:
            pitch = before[voice]
            if pitch.name != seventh:
                continue
            target = after[voice]
            down = (
                pitch.diatonic_index - target.diatonic_index == 1
                and 1 <= pitch.midi - target.midi <= 2
            )
            if down:
                continue
            up = (
                target.diatonic_index - pitch.diatonic_index == 1
                and 1 <= target.midi - pitch.midi <= 2
            )
            severity = Severity.ERROR
            if (
                up
                and voice != BASS
                and first.chord.inversion == 2
                and second.chord.inversion == 1
                and key is not None
                and second.chord.root == key.tonic
            ):
                severity = Severity.WARNING  # V4/3–I6, Kostka–Payne
            self.add(
                Rule.CHORDAL_SEVENTH,
                severity,
                slot,
                (voice,),
                # Translators: e.g. "The seventh (F) in the alto does not resolve down by step
                # (chords 2–3)".
                lambda: _(
                    'The seventh ({note}) in the {voice} does not resolve down by step '
                    '(chords {first}–{second})'
                ).format(
                    note=pitch_name(seventh),
                    voice=voice_name(voice),
                    first=slot,
                    second=slot + 1,
                ),
            )


def check(chords: Sequence[tuple[Pitch, ...]], context: Context | None = None) -> list[Violation]:
    """Every violation in ``chords`` (four pitches each, soprano first), sorted by slot.

    Raises :class:`ValueError` when a chord does not have four pitches.
    """
    for chord in chords:
        if len(chord) != len(VOICES):
            raise ValueError(f'four-part chords have four pitches, not {len(chord)}')
    return _Checker(chords, context or Context(), messages=True).run()


def scan(
    chords: Sequence[tuple[Pitch, ...]], context: Context | None = None, *, first: int = 0
) -> list[Violation]:
    """Like :func:`check`, with empty messages: fast, for generators that try many voicings.

    With ``first`` only the chords from that slot on are checked (with the motion into
    the first of them): a generator that extends a passage checks the new chord only.
    """
    for chord in chords:
        if len(chord) != len(VOICES):
            raise ValueError(f'four-part chords have four pitches, not {len(chord)}')
    return _Checker(chords, context or Context(), messages=False, first=first).run()


def errors(violations: Sequence[Violation]) -> list[Violation]:
    """The violations that make an answer wrong."""
    return [v for v in violations if v.severity is Severity.ERROR]
