# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""The exercise framework: exercises are data, not UI code.

An exercise definition generates :class:`Question` objects and grades
answers. The generic exercise page renders any question from its
:data:`AnswerSpec`, so adding an exercise means writing one module in
``etude/exercises/families/`` plus tests; no widget code is needed unless
a new kind of answer input is introduced.

Every user-visible string returned from here must be translatable
(``from gettext import gettext as _``).
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from gettext import gettext as _
from typing import ClassVar

from ..audio.spec import PlaybackSpec
from ..core import Duration, KeySignature, Meter, Pitch, PitchName
from ..core.naming import pitch_name
from ..learning.model import ItemId
from ..notation.spec import Clef, Figure


class Family(Enum):
    """Sidebar groups of the practice section."""

    NOTATION = 'notation'
    EAR = 'ear'
    RHYTHM = 'rhythm'
    HARMONY = 'harmony'
    VOCABULARY = 'vocabulary'


class Modality(Enum):
    EYE = 'eye'
    EAR = 'ear'
    TAP = 'tap'


# Answer inputs ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Option:
    key: str
    """Stable identifier; also the answer value of a choice."""
    label: str
    accel: str | None = None
    """Keyboard accelerator shown as a badge, e.g. ``'1'`` or ``'R'``."""
    description: str | None = None
    """Secondary line, e.g. ``'Tonic'`` under degree ``1`` (design 1g)."""


@dataclass(frozen=True, slots=True)
class ChoiceAnswer:
    """Pick one option (design 1b, 1d, 1e, 1g). Value: the option ``key``."""

    options: tuple[Option, ...]
    targets: Mapping[int, str] = field(default_factory=dict, hash=False)
    """Event index on the figure → option key; clicking that note picks the
    option (design 1g, "click the note on the staff")."""


@dataclass(frozen=True, slots=True)
class PianoAnswer:
    """Answer on an on-screen keyboard or with letter keys (design 1c).

    Value: a :class:`~etude.core.Pitch` when ``octave_matters``, otherwise a
    :class:`~etude.core.PitchName`.
    """

    low: Pitch
    high: Pitch
    octave_matters: bool = False
    letter_keys: bool = True
    """Accept a–g (Shift for sharps, per the design hint)."""


@dataclass(frozen=True, slots=True)
class ChipGroup:
    key: str
    label: str
    options: tuple[Option, ...]
    accidentals: bool = False
    """Offer a ♯ / ♭ chip that alters the chosen option (design 1f, "Root").
    Option keys must then be natural note letters, and the value of the group
    is the key with ``'#'`` or ``'b'`` appended when an accidental is chosen."""


@dataclass(frozen=True, slots=True)
class ChipsAnswer:
    """Several independent choices confirmed with Check (design 1f).
    Value: ``Mapping[group key, option key]``."""

    groups: tuple[ChipGroup, ...]


@dataclass(frozen=True, slots=True)
class StaffInputAnswer:
    """Place notes on a staff: construction, dictation, SATB, counterpoint.
    Value: ``tuple[tuple[Pitch, ...], ...]``, one chord (or single note) per slot."""

    clef: Clef
    key_signature: KeySignature | None = None
    slots: int | None = None
    """Number of notes or chords to enter; ``None`` = free length."""
    voices: int = 1
    given: Figure | None = None
    """Notes already printed that the learner adds to (a bass line, a cantus firmus)."""


@dataclass(frozen=True, slots=True)
class RhythmInputAnswer:
    """Build a rhythm from a palette of durations. Value: ``tuple[tuple[Duration, bool], ...]``
    where the flag marks rests."""

    meter: Meter
    bars: int
    palette: tuple[Duration, ...]


@dataclass(frozen=True, slots=True)
class TapAnswer:
    """Tap a rhythm on Space in time with the metronome. Value: ``tuple[float, ...]``,
    tap times in milliseconds relative to beat 0, already latency-compensated."""

    meter: Meter
    tempo: float
    """Quarter notes per minute, as in :attr:`PlaybackSpec.tempo`."""
    count_in: int
    """Metronome beats (felt pulses of ``meter``) before beat 0."""
    bars: int = 1
    """Bars the learner taps in; the take ends after them."""
    click: bool = True
    """Keep the metronome sounding while the learner taps (it is always shown)."""


@dataclass(frozen=True, slots=True)
class TextAnswer:
    """Type an answer (vocabulary recall, set-class names). Value: ``str``."""

    placeholder: str = ''
    suggestions: tuple[str, ...] = ()


AnswerSpec = (
    ChoiceAnswer
    | PianoAnswer
    | ChipsAnswer
    | StaffInputAnswer
    | RhythmInputAnswer
    | TapAnswer
    | TextAnswer
)


# Questions and feedback -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Question:
    exercise_id: str
    item_id: ItemId
    prompt: str
    """E.g. "Which major key is written here?"."""
    answer: AnswerSpec
    expected: object
    """The correct answer, as a value of the type documented on the answer spec."""
    figure: Figure | None = None
    playback: PlaybackSpec | None = None
    playback_is_question: bool = False
    """True for ear training: the sound is the question and the figure is hidden
    until answered (unless the learner turns on "Show staff")."""
    written_alternative: Figure | None = None
    """Required when ``playback_is_question``: notation shown instead of the sound
    for learners who cannot rely on hearing."""
    context: str = ''
    """Short extra facts shown with the question, e.g. "Root: C4" (design 1e)."""
    playback_style_choice: bool = True
    """Offer the ear panel's Melodic/Harmonic toggle. Intervals can be heard
    either way; a chord question's playback style is part of the question."""
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class Feedback:
    correct: bool
    title: str
    """E.g. "Correct — F4" or "Not quite — the answer is a major sixth"."""
    detail: str = ''
    """The explanation, e.g. "G4 to E5 spans six letter names and nine semitones."."""
    expected_label: str = ''
    score: float | None = None
    figure: Figure | None = None
    """Annotated figure that replaces the question figure after answering."""
    play_expected: PlaybackSpec | None = None
    play_given: PlaybackSpec | None = None
    """Lets ear-training learners compare what they chose with the right answer."""


# Settings ---------------------------------------------------------------------
# Exercises declare their "Question pool" settings; the setup page (design 1j)
# is generated from them. Session-wide settings (length, timed mode, reveal
# after mistake, accessibility) belong to the application, not to exercises.


@dataclass(frozen=True, slots=True)
class IntSetting:
    key: str
    title: str
    default: int
    minimum: int
    maximum: int
    subtitle: str = ''


@dataclass(frozen=True, slots=True)
class BoolSetting:
    key: str
    title: str
    default: bool
    subtitle: str = ''


@dataclass(frozen=True, slots=True)
class ChoiceSetting:
    key: str
    title: str
    options: tuple[Option, ...]
    default: str
    subtitle: str = ''


@dataclass(frozen=True, slots=True)
class MultiChoiceSetting:
    key: str
    title: str
    options: tuple[Option, ...]
    default: tuple[str, ...]
    subtitle: str = ''
    minimum: int = 1


Setting = IntSetting | BoolSetting | ChoiceSetting | MultiChoiceSetting


# Definitions ------------------------------------------------------------------


class ExerciseDefinition(ABC):
    """Base class of all exercises. Subclasses are registered in
    :mod:`etude.exercises.registry`."""

    id: ClassVar[str]
    item_prefix: ClassVar[str]
    """Every item id of this exercise starts with this prefix (e.g. ``'keysig.'``);
    prefixes of different exercises never overlap."""
    family: ClassVar[Family]
    modality: ClassVar[Modality]
    level: ClassVar[int]
    """Curriculum level 1–4 where the exercise is introduced."""
    icon_name: ClassVar[str]
    glyph: ClassVar[str] = '♪'
    """Short symbol drawn in the exercise's icon tile on the home page."""
    settings: ClassVar[tuple[Setting, ...]] = ()

    @property
    @abstractmethod
    def title(self) -> str:
        """Translated title, e.g. "Key Signatures"."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Translated one-sentence description for the exercise card."""

    @property
    def play_label(self) -> str:
        """Label of the button that plays a question or answer, e.g. "Play chord"."""
        return _('Play')

    def default_settings(self) -> dict[str, object]:
        return {s.key: s.default for s in self.settings}

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        """Subtitle for the exercise header, e.g. "Treble clef · up to 5 accidentals"."""
        return ''

    @abstractmethod
    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        """Items covered under ``settings``, in teaching order."""

    @abstractmethod
    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        """A fresh concrete question for ``item_id``. Must be deterministic for a given
        ``rng`` state, and the expected answer must be unambiguous among the options."""

    @abstractmethod
    def grade(self, question: Question, given: object) -> Feedback: ...

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        """Items learners easily mistake for ``item_id`` (a minor sixth for a major
        sixth). Sessions place them next to each other so learners compare them."""
        return ()

    def item_label(self, item_id: ItemId) -> str:
        """Translated name of an item for lists such as "Weakest items",
        e.g. "6 flats — key signature". Defaults to the id itself."""
        return str(item_id)

    def answer_label(self, question: Question, value: object) -> str:
        """Display form of an answer value (expected or given), e.g. "E minor, root position".

        The default joins option labels and note names; exercises override it
        when their answers read better as a phrase.
        """
        answer = question.answer
        if isinstance(answer, ChoiceAnswer):
            return next((o.label for o in answer.options if o.key == value), str(value))
        if isinstance(answer, ChipsAnswer) and isinstance(value, Mapping):
            labels = []
            for group in answer.groups:
                key = str(value.get(group.key, ''))
                option = next((o for o in group.options if o.key == key), None)
                if option is not None:
                    labels.append(option.label)
                elif group.accidentals:
                    labels.append(pitch_name(PitchName.parse(key)))
                else:
                    labels.append(key)
            # Translators: separator between the parts of a multi-part answer.
            return _(', ').join(labels)
        if isinstance(value, Pitch):
            return pitch_name(value.name) + str(value.octave)
        if isinstance(value, PitchName):
            return pitch_name(value)
        return str(value)

    def serialize(self, value: object) -> str:
        """Compact text form of an answer value for the attempt log."""
        return str(value)
