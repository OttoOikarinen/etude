# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Cadences on the staff: name the cadence that ends a short four-part phrase.

A phrase of three to five chords in a named key is written for four voices
on a grand staff; the learner names the cadence formed by its last two
chords. Items are cadence types per mode, ``cadence.staff.major.pac`` or
``cadence.staff.minor.phrygian``; the key, the chords before the cadence
and the voicing vary per question.

Definitions follow Kostka & Payne, *Tonal Harmony* (ch. 8):

* **Perfect authentic (PAC)**: V(7)–I with both chords in root position and
  the tonic in the soprano over the final chord.
* **Imperfect authentic (IAC)**: any other authentic cadence: V–I with the
  third or fifth in the soprano, or with an inverted dominant (V6–I,
  vii°6–I). Kostka–Payne count the inverted forms as IACs; Aldwell–Schachter
  and Caplin treat an inverted dominant as too weak to close a phrase, so
  "Inverted dominants" is a setting.
* **Half (HC)**: the phrase stops on V, however it is approached.
* **Phrygian half**: iv6–V in minor, the bass falling a half step from ♭6̂
  to 5̂ while the soprano rises a step from 4̂ to 5̂ — a special half cadence.
* **Plagal (PC)**: IV–I (iv–i in minor).
* **Deceptive (DC)**: V(7)–vi (V–VI in minor), the bass rising a step where
  the ear expects the tonic.

The four-part writing follows the conventions in :mod:`.harmony`.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from functools import cache
from gettext import gettext as _
from gettext import ngettext, pgettext
from typing import cast

from ...audio.spec import PlaybackSpec
from ...core import Chord, Duration, NoteValue, PitchName
from ...core.naming import key_name, pitch_name
from ...core.roman import RomanNumeral
from ...core.scale import Key, Mode
from ...learning.model import ItemId
from ...notation.spec import Chord as StaffChord
from ...notation.spec import Event, Figure, Head, Ink, StaffSpec, SystemSpec
from ..base import (
    BoolSetting,
    ChoiceAnswer,
    ChoiceSetting,
    ExerciseDefinition,
    Family,
    Feedback,
    IntSetting,
    Modality,
    MultiChoiceSetting,
    Option,
    Question,
)
from .harmony import (
    MAX_ACCIDENTALS,
    Satb,
    Voicing,
    chord_of,
    key_from_signature,
    keys_within,
    limit_setting,
    modes_setting,
    progression_playback,
    roman_label,
    satb_figure,
    satb_voices,
    voice_progression,
)

TYPES = ('pac', 'iac', 'half', 'plagal', 'deceptive', 'phrygian')
"""Item segments and answer keys, in the order options are listed."""
_COMMON = TYPES[:5]
_TEACHING_ORDER = ('pac', 'half', 'iac', 'deceptive', 'plagal', 'phrygian')
_MODES = {'major': Mode.MAJOR, 'minor': Mode.MINOR}

# Phrases: the chords before the cadence, then the cadence itself.
_LEAD_INS = {
    Mode.MAJOR: {
        'authentic': (('I', 'IV'), ('I', 'ii6'), ('I', 'vi', 'ii6'), ('I', 'I6', 'IV'), ('I',)),
        'half': (('I', 'IV'), ('I', 'ii6'), ('I', 'vi', 'IV'), ('I', 'I6', 'ii6'), ('I',)),
        'plagal': (('I', 'V'), ('I', 'vi'), ('I', 'V6', 'I'), ('I', 'V', 'I')),
    },
    Mode.MINOR: {
        'authentic': (('i', 'iv'), ('i', 'iio6'), ('i', 'VI', 'iio6'), ('i', 'i6', 'iv'), ('i',)),
        'half': (('i', 'iv'), ('i', 'iio6'), ('i', 'VI', 'iv'), ('i', 'i6', 'iio6'), ('i',)),
        'plagal': (('i', 'V'), ('i', 'VI'), ('i', 'V6', 'i'), ('i', 'V', 'i')),
        'phrygian': (('i', 'iv'), ('i', 'VI'), ('i', 'i6'), ('i', 'VI', 'iv')),
    },
}


@dataclass(frozen=True, slots=True)
class _Plan:
    numerals: tuple[str, ...]
    soprano_degrees: Mapping[int, tuple[int, ...]]
    """Chord index (negative from the end) → allowed soprano scale degrees."""
    inverted: bool = False


def _plan(kind: str, mode: Mode, inverted_iac: bool, rng: random.Random) -> _Plan:
    tonic, sub, sub6 = ('I', 'IV', 'ii6') if mode is Mode.MAJOR else ('i', 'iv', 'iio6')
    plain_sub = (tonic, sub)
    six = 'vi' if mode is Mode.MAJOR else 'VI'
    leads = _LEAD_INS[mode]
    dominant = rng.choice(('V', 'V', 'V7'))
    if kind == 'pac':
        lead = rng.choice(leads['authentic'])
        return _Plan((*lead, dominant, tonic), {-1: (1,)})
    if kind == 'iac':
        if inverted_iac and rng.random() < 0.4:
            lead = rng.choice((plain_sub, (tonic, sub6)))
            return _Plan((*lead, rng.choice(('V6', 'viio6')), tonic), {}, inverted=True)
        lead = rng.choice(leads['authentic'])
        return _Plan((*lead, dominant, tonic), {-1: (3, 5)})
    if kind == 'half':
        return _Plan((*rng.choice(leads['half']), 'V'), {})
    if kind == 'phrygian':
        return _Plan((*rng.choice(leads['phrygian']), 'iv6', 'V'), {-2: (4,), -1: (5,)})
    if kind == 'plagal':
        return _Plan((*rng.choice(leads['plagal']), sub, tonic), {})
    lead = rng.choice(leads['authentic'])
    return _Plan((*lead, dominant, six), {})


def item_id(mode: Mode, kind: str) -> ItemId:
    """``cadence.staff.major.pac`` or ``cadence.staff.minor.phrygian``."""
    return ItemId(f'cadence.staff.{mode.value}.{kind}')


_item = item_id


@cache
def parse_item(item: str) -> tuple[Mode, str]:
    parts = item.split('.')
    if (
        len(parts) != 4
        or parts[:2] != ['cadence', 'staff']
        or parts[2] not in _MODES
        or parts[3] not in TYPES
        or (parts[3] == 'phrygian' and parts[2] != 'minor')
    ):
        raise ValueError(f'not a cadence item: {item!r}')
    return _MODES[parts[2]], parts[3]


def _names() -> dict[str, str]:
    ctx = 'cadence'
    return {
        'pac': pgettext(ctx, 'Perfect authentic'),
        'iac': pgettext(ctx, 'Imperfect authentic'),
        'half': pgettext(ctx, 'Half'),
        'plagal': pgettext(ctx, 'Plagal'),
        'deceptive': pgettext(ctx, 'Deceptive'),
        'phrygian': pgettext(ctx, 'Phrygian half'),
    }


def _phrases() -> dict[str, str]:
    # Translators: cadence names inside a sentence, "the answer is a half cadence".
    ctx = 'cadence with article'
    return {
        'pac': pgettext(ctx, 'a perfect authentic cadence'),
        'iac': pgettext(ctx, 'an imperfect authentic cadence'),
        'half': pgettext(ctx, 'a half cadence'),
        'plagal': pgettext(ctx, 'a plagal cadence'),
        'deceptive': pgettext(ctx, 'a deceptive cadence'),
        'phrygian': pgettext(ctx, 'a Phrygian half cadence'),
    }


def _rules() -> dict[str, str]:
    """What makes each cadence, for contrasting a wrong answer with the right one."""
    return {
        'pac': _(
            'A perfect authentic cadence is V–I with both chords in root position and the '
            'tonic in the soprano.'
        ),
        'iac': _(
            'An imperfect authentic cadence is V–I with the third or fifth in the soprano, or '
            'with an inverted dominant.'
        ),
        'half': _('A half cadence stops on V.'),
        'plagal': _('A plagal cadence is IV–I.'),
        'deceptive': _('A deceptive cadence is V–vi: the dominant does not go to the tonic.'),
        'phrygian': _(
            'A Phrygian half cadence is iv6–V in minor, the bass falling a half step to the '
            'dominant.'
        ),
    }


_SETTING_NAMES: dict[str, Callable[[], str]] = {
    'pac': lambda: _('Perfect authentic'),
    'iac': lambda: _('Imperfect authentic'),
    'half': lambda: _('Half'),
    'plagal': lambda: _('Plagal'),
    'deceptive': lambda: _('Deceptive'),
}

_QUARTER = Duration(NoteValue.QUARTER)
_HALF = Duration(NoteValue.HALF)


def _types(settings: Mapping[str, object]) -> list[str]:
    chosen = settings.get('types', _COMMON)
    keys = set(cast(Sequence[str], chosen)) if isinstance(chosen, list | tuple) else set(_COMMON)
    pool = [t for t in _COMMON if t in keys] or list(_COMMON)
    if settings.get('phrygian', False):
        pool.append('phrygian')
    return pool


def _degree(key: Key, name: PitchName) -> int | None:
    function = key.function_of(name)
    return function.degree if function is not None else None


class CadencesStaff(ExerciseDefinition):
    id = 'cadences-staff'
    item_prefix = 'cadence.staff.'
    family = Family.HARMONY
    modality = Modality.EYE
    level = 2
    icon_name = 'cadence-symbolic'
    glyph = '𝄂'
    settings = (
        ChoiceSetting(
            'mode',
            _('Keys'),
            (
                Option('major', _('Major')),
                Option('minor', _('Minor')),
                Option('both', _('Major and minor')),
            ),
            'both',
        ),
        MultiChoiceSetting(
            'types',
            _('Cadences'),
            tuple(Option(key, _SETTING_NAMES[key]()) for key in _COMMON),
            _COMMON,
        ),
        BoolSetting(
            'phrygian',
            _('Phrygian half cadence'),
            False,
            subtitle=_('iv6–V in minor keys'),
        ),
        BoolSetting(
            'inverted-iac',
            _('Inverted dominants'),
            True,
            subtitle=_('Count V6–I and vii°6–I as imperfect authentic cadences (Kostka–Payne)'),
        ),
        IntSetting(
            'max-accidentals',
            _('Most accidentals'),
            4,
            0,
            MAX_ACCIDENTALS,
            subtitle=_('Largest number of sharps or flats in the key signature'),
        ),
    )

    @property
    def title(self) -> str:
        return _('Cadences — Staff')

    @property
    def description(self) -> str:
        return _('Name the cadence that ends a four-part phrase.')

    @property
    def play_label(self) -> str:
        return _('Play phrase')

    def describe_settings(self, settings: Mapping[str, object]) -> str:
        modes = modes_setting(settings, 'both')
        if modes == (Mode.MAJOR,):
            keys = _('Major keys')
        elif modes == (Mode.MINOR,):
            keys = _('Minor keys')
        else:
            keys = _('Major and minor keys')
        count = len(self._pool(settings))
        cadences = ngettext('{n} cadence', '{n} cadences', count).format(n=count)
        # Translators: separator between the parts of an exercise subtitle.
        return _(' · ').join((keys, cadences))

    def item_label(self, item_id: ItemId) -> str:
        mode, kind = parse_item(item_id)
        name = _names()[kind]
        if mode is Mode.MAJOR:
            # Translators: an item in "Weakest items", e.g. "Half cadence in major".
            return _('{cadence} cadence in major').format(cadence=name)
        # Translators: an item in "Weakest items", e.g. "Deceptive cadence in minor".
        return _('{cadence} cadence in minor').format(cadence=name)

    @staticmethod
    def _pool(settings: Mapping[str, object]) -> list[tuple[Mode, str]]:
        types = _types(settings)
        return [
            (mode, kind)
            for kind in _TEACHING_ORDER
            if kind in types
            for mode in modes_setting(settings, 'both')
            if kind != 'phrygian' or mode is Mode.MINOR
        ]

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]:
        """Perfect authentic and half cadences first, then imperfect authentic,
        deceptive, plagal and Phrygian, each in major and minor."""
        return [item_id(mode, kind) for mode, kind in self._pool(settings)]

    def confusables(self, item_id: ItemId) -> Sequence[ItemId]:
        """PAC and IAC, half and Phrygian half, authentic and deceptive."""
        mode, kind = parse_item(item_id)
        partners = {
            'pac': ('iac', 'deceptive'),
            'iac': ('pac',),
            'half': ('phrygian',) if mode is Mode.MINOR else ('pac',),
            'phrygian': ('half',),
            'plagal': ('pac',),
            'deceptive': ('pac',),
        }[kind]
        return [_item(mode, p) for p in partners]

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question:
        mode, kind = parse_item(item_id)
        key = rng.choice(keys_within(limit_setting(settings), (mode,)))
        plan = _plan(kind, mode, bool(settings.get('inverted-iac', True)), rng)
        chords = [RomanNumeral.parse(n).realize(key) for n in plan.numerals]
        count = len(chords)
        soprano = {
            count + index: tuple(key.scale.degree(d) for d in degrees)
            for index, degrees in plan.soprano_degrees.items()
        }
        extra = {}
        if kind == 'deceptive':
            extra[count - 1] = {1: 0.0}  # double the third of vi after V
        voices = voice_progression(chords, key, rng, soprano=soprano, extra_doublings=extra)
        durations = (*([_QUARTER] * (count - 1)), _HALF)
        figure = satb_figure(Satb(tuple(voices), key.signature, durations), final_bar=True)

        pool = _types(settings)
        if kind not in pool:
            pool.append(kind)
        names = _names()
        options = tuple(
            Option(t, names[t], str(i + 1)) for i, t in enumerate(t for t in TYPES if t in pool)
        )
        return Question(
            exercise_id=self.id,
            item_id=item_id,
            prompt=_('Which cadence ends this phrase?'),
            answer=ChoiceAnswer(options),
            expected=kind,
            figure=figure,
            playback=self._playback(voices),
            # Translators: context of a cadence question, e.g. "Key: D major".
            context=_('Key: {key}').format(key=key_name(key)),
            hint=_(
                'Find the Roman numerals of the last two chords, then check the bass and the '
                'soprano of the final chord.'
            ),
        )

    @staticmethod
    def _playback(voices: Sequence[Voicing]) -> PlaybackSpec:
        lengths = [Fraction(1)] * (len(voices) - 1) + [Fraction(2)]
        return progression_playback(voices, lengths)

    def grade(self, question: Question, given: object) -> Feedback:
        mode, kind = parse_item(question.item_id)
        key = self._key(question.figure, mode)
        voices = satb_voices(question.figure)
        chords = [chord_of(sorted(v)) for v in voices]
        numerals = [self._numeral(c, key) for c in chords]
        correct = str(given) == kind
        label = _names()[kind]
        phrase = _phrases()[kind]
        if correct:
            # Translators: e.g. "Correct — half cadence"; {answer} is a cadence name.
            title = _('Correct — {answer}').format(answer=phrase)
        else:
            # Translators: e.g. "Not quite — the answer is a half cadence".
            title = _('Not quite — the answer is {answer}').format(answer=phrase)
        detail = [self._explanation(kind, key, voices, chords, numerals)]
        if not correct and str(given) in _rules():
            detail.append(_rules()[str(given)])
        return Feedback(
            correct=correct,
            title=title,
            detail=' '.join(detail),
            expected_label=label,
            figure=self._annotated(question.figure, voices, numerals),
            play_expected=question.playback,
        )

    def answer_label(self, question: Question, value: object) -> str:
        return _names().get(str(value), str(value))

    @staticmethod
    def _key(figure: Figure | None, mode: Mode) -> Key:
        signature = figure.staves[0].key_signature if isinstance(figure, SystemSpec) else None
        return key_from_signature(signature, mode)

    @staticmethod
    def _numeral(chord: Chord, key: Key) -> str:
        numeral = RomanNumeral.analyze(chord, key)
        return roman_label(numeral) if numeral is not None else '?'

    @staticmethod
    def _explanation(
        kind: str,
        key: Key,
        voices: Sequence[Voicing],
        chords: Sequence[Chord],
        numerals: Sequence[str],
    ) -> str:
        last, penult = chords[-1], chords[-2]
        pair = _('{first}–{second}').format(first=numerals[-2], second=numerals[-1])
        soprano = voices[-1][0].name
        tonic = pitch_name(key.tonic)
        if kind == 'pac':
            # Translators: e.g. "The phrase ends V–I, both chords in root position, with the
            # tonic, D, in the soprano: a perfect authentic cadence."
            return _(
                'The phrase ends {pair}, both chords in root position, with the tonic, {tonic}, '
                'in the soprano: a perfect authentic cadence.'
            ).format(pair=pair, tonic=tonic)
        if kind == 'iac':
            if penult.root == key.leading_tone:
                return _(
                    'The phrase ends {pair}: the leading-tone chord stands in for V, so the '
                    'cadence is authentic but imperfect. Kostka–Payne call this an imperfect '
                    'authentic cadence; Aldwell–Schachter and Caplin consider it too weak to end '
                    'a phrase.'
                ).format(pair=pair)
            if penult.inversion:
                return _(
                    'The phrase ends {pair}: an authentic cadence with an inverted dominant, so '
                    'it is imperfect. Kostka–Payne call this an imperfect authentic cadence; '
                    'Aldwell–Schachter and Caplin consider an inverted dominant too weak to '
                    'end a phrase.'
                ).format(pair=pair)
            member = _('the third') if soprano == last.names()[1] else _('the fifth')
            # Translators: e.g. "The phrase ends V–I, but the soprano ends on F♯, the third of
            # the tonic chord, not on the tonic: an imperfect authentic cadence."
            return _(
                'The phrase ends {pair}, but the soprano ends on {note}, {member} of the tonic '
                'chord, not on the tonic: an imperfect authentic cadence.'
            ).format(pair=pair, note=pitch_name(soprano), member=member)
        if kind == 'half':
            return _(
                'The phrase stops on the dominant, {pair}: a half cadence. Whatever comes '
                'before it, a pause on V is a half cadence.'
            ).format(pair=pair)
        if kind == 'phrygian':
            return _(
                'The phrase ends {pair} in minor: the bass falls a half step from {upper} to '
                '{lower} while the soprano rises a step to the dominant. This is a Phrygian '
                'half cadence, named after the half step of the Phrygian mode.'
            ).format(
                pair=pair,
                upper=pitch_name(penult.bass),
                lower=pitch_name(last.bass),
            )
        if kind == 'plagal':
            return _(
                'The phrase ends {pair}, the subdominant moving to the tonic: a plagal cadence, '
                'the “Amen” cadence.'
            ).format(pair=pair)
        return _(
            'The phrase ends {pair}: the dominant moves to the submediant instead of the tonic. '
            'The bass rises a step where the ear expects it to fall to {tonic}: a deceptive '
            'cadence.'
        ).format(pair=pair, tonic=tonic)

    @staticmethod
    def _annotated(
        figure: Figure | None, voices: Sequence[Voicing], numerals: Sequence[str]
    ) -> Figure | None:
        """Roman numerals under the bass; the cadence's two chords in the accent colour."""
        if not isinstance(figure, SystemSpec):
            return figure
        count = len(voices)

        def mark(staff: StaffSpec, labelled: bool) -> StaffSpec:
            def recolour(events: tuple[Event, ...], with_labels: bool) -> tuple[Event, ...]:
                result: list[Event] = []
                index = 0
                for event in events:
                    if not isinstance(event, StaffChord):
                        result.append(event)
                        continue
                    cadence = index >= count - 2
                    ink = Ink.ACCENT if cadence else Ink.FOREGROUND
                    result.append(
                        StaffChord(
                            tuple(Head(h.pitch, ink=ink) for h in event.heads),
                            event.duration,
                            label=numerals[index] if with_labels else None,
                            ink=ink,
                        )
                    )
                    index += 1
                return tuple(result)

            return StaffSpec(
                clef=staff.clef,
                key_signature=staff.key_signature,
                events=recolour(staff.events, False),
                voices=tuple(recolour(v, labelled) for v in staff.voices),
            )

        treble, low = figure.staves
        return SystemSpec(staves=(mark(treble, False), mark(low, True)))


EXERCISES: tuple[ExerciseDefinition, ...] = (CadencesStaff(),)
