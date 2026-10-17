# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Text descriptions of notation for screen readers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from gettext import gettext as _
from gettext import ngettext

from ..core import Duration, KeySignature, NoteValue, Pitch
from .spec import (
    Barline,
    BarStyle,
    Chord,
    Clef,
    Event,
    Figure,
    GlyphFigure,
    Head,
    Ink,
    Rest,
    StaffSpec,
    SystemSpec,
)

PitchNamer = Callable[[Pitch], str]


def describe(figure: Figure, name_pitch: Callable[[Pitch], str] = str) -> str:
    """Describe a figure in words, e.g. "Treble staff, four sharps. Two notes: G4, E5."

    Uses ``figure.description`` when it is set. ``name_pitch`` lets the UI
    apply the user's note naming convention. Must never reveal the answer
    of a question that asks for exactly that information: exercises set
    ``description`` explicitly in such cases.
    """
    if isinstance(figure, GlyphFigure):
        return figure.description
    if figure.description:
        return figure.description
    if isinstance(figure, StaffSpec):
        return _describe_staff(figure, name_pitch)
    return _describe_system(figure, name_pitch)


def _describe_system(system: SystemSpec, name_pitch: PitchNamer) -> str:
    clefs = [staff.clef for staff in system.staves]
    if clefs == [Clef.TREBLE, Clef.BASS] and system.brace:
        header = _('Grand staff.')
    else:
        count = len(system.staves)
        header = ngettext('System of {count} staff.', 'System of {count} staves.', count).format(
            count=count
        )
    parts = [header]
    for index, staff in enumerate(system.staves):
        text = staff.description or _describe_staff(staff, name_pitch)
        if index < len(system.labels) and system.labels[index]:
            # Translators: a staff name such as "S" or "Bass" followed by its description.
            text = _('{label}: {description}').format(label=system.labels[index], description=text)
        parts.append(text)
    return ' '.join(parts)


def _clef_name(staff: StaffSpec) -> str:
    if staff.lines == 1:
        return _('Single-line staff')
    match staff.clef:
        case Clef.TREBLE:
            return _('Treble staff')
        case Clef.BASS:
            return _('Bass staff')
        case Clef.ALTO:
            return _('Alto staff')
        case Clef.TENOR:
            return _('Tenor staff')
        case Clef.TREBLE_8VB:
            return _('Treble staff an octave lower')
        case Clef.PERCUSSION:
            return _('Percussion staff')


def _key_name(key: KeySignature) -> str:
    sharps = (
        _('one sharp'),
        _('two sharps'),
        _('three sharps'),
        _('four sharps'),
        _('five sharps'),
        _('six sharps'),
        _('seven sharps'),
    )
    flats = (
        _('one flat'),
        _('two flats'),
        _('three flats'),
        _('four flats'),
        _('five flats'),
        _('six flats'),
        _('seven flats'),
    )
    if key.fifths == 0:
        return _('no sharps or flats')
    return (sharps if key.fifths > 0 else flats)[key.count - 1]


def _count_word(count: int) -> str:
    """A capitalised number word for the start of a sentence."""
    words = (
        _('One'),
        _('Two'),
        _('Three'),
        _('Four'),
        _('Five'),
        _('Six'),
        _('Seven'),
        _('Eight'),
        _('Nine'),
        _('Ten'),
        _('Eleven'),
        _('Twelve'),
    )
    return words[count - 1] if 1 <= count <= len(words) else str(count)


def _heading(staff: StaffSpec) -> str:
    name = _clef_name(staff)
    key = staff.key_signature
    meter = staff.meter
    if key is not None and meter is not None:
        # Translators: e.g. "Treble staff, four sharps, 3/4 time."
        return _('{staff}, {key}, {meter} time.').format(
            staff=name, key=_key_name(key), meter=meter
        )
    if key is not None:
        # Translators: e.g. "Treble staff, four sharps."
        return _('{staff}, {key}.').format(staff=name, key=_key_name(key))
    if meter is not None:
        # Translators: e.g. "Bass staff, 6/8 time."
        return _('{staff}, {meter} time.').format(staff=name, meter=meter)
    return _('{staff}.').format(staff=name)


def _value_name(value: NoteValue) -> str:
    match value:
        case NoteValue.BREVE:
            return _('breve')
        case NoteValue.WHOLE:
            return _('whole')
        case NoteValue.HALF:
            return _('half')
        case NoteValue.QUARTER:
            return _('quarter')
        case NoteValue.EIGHTH:
            return _('eighth')
        case NoteValue.SIXTEENTH:
            return _('16th')
        case NoteValue.THIRTY_SECOND:
            return _('32nd')
        case NoteValue.SIXTY_FOURTH:
            return _('64th')


def _duration_name(duration: Duration) -> str:
    name = _value_name(duration.value)
    if duration.dots == 1:
        name = _('dotted {value}').format(value=name)
    elif duration.dots >= 2:
        name = _('double-dotted {value}').format(value=name)
    tuplet = duration.tuplet
    if tuplet is not None:
        if (tuplet.actual, tuplet.normal) == (3, 2):
            name = _('{value} triplet').format(value=name)
        else:
            name = _('{value} in a {actual}:{normal} tuplet').format(
                value=name, actual=tuplet.actual, normal=tuplet.normal
            )
    return name


def _pitches(heads: Sequence[Head], name_pitch: PitchNamer) -> str:
    return ' '.join(name_pitch(head.pitch) for head in heads)


def _barline_name(style: BarStyle) -> str:
    match style:
        case BarStyle.SINGLE:
            return _('bar line')
        case BarStyle.DOUBLE:
            return _('double bar line')
        case BarStyle.FINAL:
            return _('final bar line')
        case BarStyle.REPEAT_START:
            return _('start repeat')
        case BarStyle.REPEAT_END:
            return _('end repeat')


def _event_name(event: Event, name_pitch: PitchNamer) -> str:
    match event:
        case Barline():
            return _barline_name(event.style)
        case Rest():
            return _('{duration} rest').format(duration=_duration_name(event.duration))
        case Chord():
            pitches = _pitches(event.heads, name_pitch)
            if len(event.heads) > 1:
                pitches = _('chord {pitches}').format(pitches=pitches)
            if event.duration is not None:
                # Translators: a note or chord and its duration, e.g. "G4 quarter".
                pitches = _('{pitches} {duration}').format(
                    pitches=pitches, duration=_duration_name(event.duration)
                )
            if event.tie_to_next:
                pitches = _('{note}, tied').format(note=pitches)
            return pitches


def _describe_events(events: Sequence[Event], name_pitch: PitchNamer) -> str:
    chords = [e for e in events if isinstance(e, Chord)]
    count = len(events)
    word = _count_word(count)
    simple = len(chords) == count and all(c.duration is None and not c.tie_to_next for c in chords)
    if simple and all(len(c.heads) == 1 for c in chords):
        notes = ', '.join(name_pitch(c.heads[0].pitch) for c in chords)
        return ngettext('{count} note: {notes}.', '{count} notes: {notes}.', count).format(
            count=word, notes=notes
        )
    if simple:
        listed = '; '.join(', '.join(name_pitch(h.pitch) for h in c.heads) for c in chords)
        return ngettext('{count} chord: {chords}.', '{count} chords: {chords}.', count).format(
            count=word, chords=listed
        )
    listed = ', '.join(_event_name(event, name_pitch) for event in events)
    return ngettext('{count} event: {events}.', '{count} events: {events}.', count).format(
        count=word, events=listed
    )


def _marked(staff: StaffSpec, name_pitch: PitchNamer) -> list[str]:
    halos: list[str] = []
    correct: list[str] = []
    wrong: list[str] = []
    for event in (*staff.events, *(e for voice in staff.voices for e in voice)):
        if not isinstance(event, Chord):
            continue
        for head in event.heads:
            name = name_pitch(head.pitch)
            if head.halo:
                halos.append(name)
            if head.ink is Ink.SUCCESS:
                correct.append(name)
            elif head.ink is Ink.ERROR:
                wrong.append(name)
    sentences = []
    if halos:
        sentences.append(_('Highlighted: {notes}.').format(notes=', '.join(halos)))
    if correct:
        sentences.append(_('Marked correct: {notes}.').format(notes=', '.join(correct)))
    if wrong:
        sentences.append(_('Marked wrong: {notes}.').format(notes=', '.join(wrong)))
    return sentences


def _describe_staff(staff: StaffSpec, name_pitch: PitchNamer) -> str:
    sentences = [_heading(staff)]
    if staff.events:
        sentences.append(_describe_events(staff.events, name_pitch))
    for voice in staff.voices:
        if voice:
            # Translators: the notes of a second voice on the same staff.
            sentences.append(
                _('Lower voice: {events}').format(events=_describe_events(voice, name_pitch))
            )
    labels = [e.label for e in staff.events if isinstance(e, Chord) and e.label]
    if labels:
        sentences.append(_('Labels: {labels}.').format(labels=', '.join(labels)))
    sentences.extend(_marked(staff, name_pitch))
    for bracket in staff.brackets:
        if bracket.first == bracket.last:
            text = _('Bracket labelled “{label}” at event {number}.').format(
                label=bracket.label, number=bracket.first + 1
            )
        else:
            text = _('Bracket labelled “{label}” over events {first} to {last}.').format(
                label=bracket.label, first=bracket.first + 1, last=bracket.last + 1
            )
        sentences.append(text)
    return ' '.join(sentences)
