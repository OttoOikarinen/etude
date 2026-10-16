# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""A minimal, typed ctypes binding to FluidSynth 2 (``libfluidsynth.so.3``).

Only what Etude needs is bound: settings, the synthesizer, SoundFont
loading, an audio driver, offline rendering and the sequencer. Every
foreign function has explicit ``argtypes`` and ``restype``.

ctypes releases the GIL while a foreign function runs, and FluidSynth's
sequencer and synthesizer APIs are thread-safe, so the wrappers can be
called from any thread while the audio thread renders.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import os
from array import array
from collections.abc import Callable
from ctypes import (
    CFUNCTYPE,
    POINTER,
    c_char_p,
    c_double,
    c_float,
    c_int,
    c_short,
    c_uint,
    c_void_p,
)
from pathlib import Path
from typing import Any, Final

log = logging.getLogger(__name__)

FLUID_OK: Final = 0
FLUID_FAILED: Final = -1

# enum fluid_log_level
FLUID_PANIC: Final = 0
FLUID_ERR: Final = 1
FLUID_WARN: Final = 2
FLUID_INFO: Final = 3
FLUID_DBG: Final = 4

# enum fluid_seq_event_type (only the ones used here)
FLUID_SEQ_NOTEON: Final = 1
FLUID_SEQ_NOTEOFF: Final = 2
FLUID_SEQ_TIMER: Final = 17
FLUID_SEQ_UNREGISTERING: Final = 21

DEFAULT_LIBRARY: Final = 'libfluidsynth.so.3'

# typedef void (*fluid_event_callback_t)(unsigned int time, fluid_event_t *event,
#                                        fluid_sequencer_t *seq, void *data);
EVENT_CALLBACK = CFUNCTYPE(None, c_uint, c_void_p, c_void_p, c_void_p)
# typedef void (*fluid_log_function_t)(int level, const char *message, void *data);
LOG_FUNCTION = CFUNCTYPE(None, c_int, c_char_p, c_void_p)

EventCallback = Callable[[int, int], None]
"""Python-side sequencer callback: ``(time_in_ticks, event_pointer)``."""


class FluidSynthError(RuntimeError):
    """FluidSynth could not be loaded or refused a request."""


class LibraryNotFoundError(FluidSynthError):
    """``libfluidsynth`` is not installed or could not be loaded."""


class SoundFontError(FluidSynthError):
    """The SoundFont is missing or could not be loaded."""


# name: (restype, argtypes)
_PROTOTYPES: Final[dict[str, tuple[Any, list[Any]]]] = {
    'fluid_version_str': (c_char_p, []),
    'fluid_set_log_function': (c_void_p, [c_int, c_void_p, c_void_p]),
    # settings
    'new_fluid_settings': (c_void_p, []),
    'delete_fluid_settings': (None, [c_void_p]),
    'fluid_settings_setint': (c_int, [c_void_p, c_char_p, c_int]),
    'fluid_settings_setnum': (c_int, [c_void_p, c_char_p, c_double]),
    'fluid_settings_setstr': (c_int, [c_void_p, c_char_p, c_char_p]),
    'fluid_settings_getint': (c_int, [c_void_p, c_char_p, POINTER(c_int)]),
    'fluid_settings_getnum': (c_int, [c_void_p, c_char_p, POINTER(c_double)]),
    # synth
    'new_fluid_synth': (c_void_p, [c_void_p]),
    'delete_fluid_synth': (None, [c_void_p]),
    'fluid_synth_sfload': (c_int, [c_void_p, c_char_p, c_int]),
    'fluid_synth_program_select': (c_int, [c_void_p, c_int, c_int, c_int, c_int]),
    'fluid_synth_program_change': (c_int, [c_void_p, c_int, c_int]),
    'fluid_synth_bank_select': (c_int, [c_void_p, c_int, c_int]),
    'fluid_synth_noteon': (c_int, [c_void_p, c_int, c_int, c_int]),
    'fluid_synth_noteoff': (c_int, [c_void_p, c_int, c_int]),
    'fluid_synth_all_notes_off': (c_int, [c_void_p, c_int]),
    'fluid_synth_all_sounds_off': (c_int, [c_void_p, c_int]),
    'fluid_synth_set_gain': (None, [c_void_p, c_float]),
    'fluid_synth_get_gain': (c_float, [c_void_p]),
    'fluid_synth_write_float': (
        c_int,
        [c_void_p, c_int, c_void_p, c_int, c_int, c_void_p, c_int, c_int],
    ),
    # audio driver
    'new_fluid_audio_driver': (c_void_p, [c_void_p, c_void_p]),
    'delete_fluid_audio_driver': (None, [c_void_p]),
    # sequencer
    'new_fluid_sequencer2': (c_void_p, [c_int]),
    'delete_fluid_sequencer': (None, [c_void_p]),
    'fluid_sequencer_register_fluidsynth': (c_short, [c_void_p, c_void_p]),
    'fluid_sequencer_register_client': (c_short, [c_void_p, c_char_p, EVENT_CALLBACK, c_void_p]),
    'fluid_sequencer_unregister_client': (None, [c_void_p, c_short]),
    'fluid_sequencer_send_at': (c_int, [c_void_p, c_void_p, c_uint, c_int]),
    'fluid_sequencer_remove_events': (None, [c_void_p, c_short, c_short, c_int]),
    'fluid_sequencer_get_tick': (c_uint, [c_void_p]),
    'fluid_sequencer_set_time_scale': (None, [c_void_p, c_double]),
    'fluid_sequencer_get_time_scale': (c_double, [c_void_p]),
    # events
    'new_fluid_event': (c_void_p, []),
    'delete_fluid_event': (None, [c_void_p]),
    'fluid_event_set_source': (None, [c_void_p, c_short]),
    'fluid_event_set_dest': (None, [c_void_p, c_short]),
    'fluid_event_timer': (None, [c_void_p, c_void_p]),
    'fluid_event_noteon': (None, [c_void_p, c_int, c_short, c_short]),
    'fluid_event_noteoff': (None, [c_void_p, c_int, c_short]),
    'fluid_event_all_notes_off': (None, [c_void_p, c_int]),
    'fluid_event_program_change': (None, [c_void_p, c_int, c_int]),
    'fluid_event_get_type': (c_int, [c_void_p]),
    'fluid_event_get_data': (c_void_p, [c_void_p]),
}


def find_library(path: str | os.PathLike[str] | None = None) -> str:
    """The library to load: ``path`` if given, else what the dynamic linker finds."""
    if path is not None:
        return os.fspath(path)
    return ctypes.util.find_library('fluidsynth') or DEFAULT_LIBRARY


class Library:
    """``libfluidsynth`` with prototypes declared for every function used."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        name = find_library(path)
        try:
            self._dll = ctypes.CDLL(name)
        except OSError as error:
            raise LibraryNotFoundError(f'cannot load FluidSynth ({name}): {error}') from error
        for function, (restype, argtypes) in _PROTOTYPES.items():
            try:
                pointer = getattr(self._dll, function)
            except AttributeError as error:
                raise LibraryNotFoundError(
                    f'{name} lacks {function}; FluidSynth 2.2 or newer is required'
                ) from error
            pointer.restype = restype
            pointer.argtypes = argtypes
        self.path = name
        self._log_function: Any = None

    def __getattr__(self, name: str) -> Any:
        if name not in _PROTOTYPES:
            raise AttributeError(name)
        return getattr(self._dll, name)

    @property
    def version(self) -> str:
        raw: bytes = self._dll.fluid_version_str()
        return raw.decode()

    def route_logging(self, logger: logging.Logger = log) -> None:
        """Send FluidSynth's panic, error and warning messages to ``logger``
        and drop its info and debug chatter (logging is process-wide)."""

        def forward(level: int, message: bytes | None, _data: int | None) -> None:
            text = (message or b'').decode(errors='replace')
            logger.log(logging.ERROR if level <= FLUID_ERR else logging.WARNING, '%s', text)

        self._log_function = LOG_FUNCTION(forward)
        for level in (FLUID_PANIC, FLUID_ERR, FLUID_WARN):
            self._dll.fluid_set_log_function(level, self._log_function, None)
        for level in (FLUID_INFO, FLUID_DBG):
            self._dll.fluid_set_log_function(level, None, None)


def _check(result: int, what: str) -> None:
    if result == FLUID_FAILED:
        raise FluidSynthError(f'FluidSynth failed to {what}')


class Settings:
    def __init__(self, lib: Library) -> None:
        self._lib = lib
        pointer: int | None = lib.new_fluid_settings()
        if not pointer:
            raise FluidSynthError('cannot create FluidSynth settings')
        self.pointer = pointer

    def set_int(self, name: str, value: int) -> None:
        _check(self._lib.fluid_settings_setint(self.pointer, name.encode(), value), f'set {name}')

    def set_num(self, name: str, value: float) -> None:
        _check(self._lib.fluid_settings_setnum(self.pointer, name.encode(), value), f'set {name}')

    def set_str(self, name: str, value: str) -> None:
        _check(
            self._lib.fluid_settings_setstr(self.pointer, name.encode(), value.encode()),
            f'set {name}',
        )

    def get_int(self, name: str) -> int:
        value = c_int()
        _check(
            self._lib.fluid_settings_getint(self.pointer, name.encode(), ctypes.byref(value)),
            f'read {name}',
        )
        return value.value

    def get_num(self, name: str) -> float:
        value = c_double()
        _check(
            self._lib.fluid_settings_getnum(self.pointer, name.encode(), ctypes.byref(value)),
            f'read {name}',
        )
        return value.value

    def delete(self) -> None:
        if self.pointer:
            self._lib.delete_fluid_settings(self.pointer)
            self.pointer = 0


class Synth:
    def __init__(self, lib: Library, settings: Settings) -> None:
        self._lib = lib
        pointer: int | None = lib.new_fluid_synth(settings.pointer)
        if not pointer:
            raise FluidSynthError('cannot create the FluidSynth synthesizer')
        self.pointer = pointer

    def sfload(self, path: str | os.PathLike[str], *, reset_presets: bool = True) -> int:
        """Load a SoundFont and return its id."""
        file = Path(path)
        if not file.is_file():
            raise SoundFontError(f'SoundFont not found: {file}')
        sfont_id: int = self._lib.fluid_synth_sfload(
            self.pointer, os.fsencode(file), int(reset_presets)
        )
        if sfont_id == FLUID_FAILED:
            raise SoundFontError(f'FluidSynth cannot load the SoundFont {file}')
        return sfont_id

    def program_select(self, channel: int, sfont_id: int, bank: int, preset: int) -> None:
        _check(
            self._lib.fluid_synth_program_select(self.pointer, channel, sfont_id, bank, preset),
            f'select bank {bank} preset {preset} on channel {channel}',
        )

    def program_change(self, channel: int, program: int) -> None:
        _check(
            self._lib.fluid_synth_program_change(self.pointer, channel, program),
            f'change channel {channel} to program {program}',
        )

    def bank_select(self, channel: int, bank: int) -> None:
        _check(self._lib.fluid_synth_bank_select(self.pointer, channel, bank), 'select bank')

    def noteon(self, channel: int, key: int, velocity: int) -> None:
        _check(self._lib.fluid_synth_noteon(self.pointer, channel, key, velocity), 'play a note')

    def noteoff(self, channel: int, key: int) -> None:
        # Fails harmlessly when the note is not sounding.
        self._lib.fluid_synth_noteoff(self.pointer, channel, key)

    def all_notes_off(self, channel: int = -1) -> None:
        """Release every note on ``channel`` (-1: all channels)."""
        self._lib.fluid_synth_all_notes_off(self.pointer, channel)

    def all_sounds_off(self, channel: int = -1) -> None:
        """Cut every voice on ``channel`` immediately, without release."""
        self._lib.fluid_synth_all_sounds_off(self.pointer, channel)

    @property
    def gain(self) -> float:
        value: float = self._lib.fluid_synth_get_gain(self.pointer)
        return value

    @gain.setter
    def gain(self, value: float) -> None:
        self._lib.fluid_synth_set_gain(self.pointer, value)

    def write_float(self, frames: int) -> tuple[array[float], array[float]]:
        """Render ``frames`` stereo frames offline (only without an audio driver)."""
        left = (c_float * frames)()
        right = (c_float * frames)()
        _check(
            self._lib.fluid_synth_write_float(self.pointer, frames, left, 0, 1, right, 0, 1),
            'render audio',
        )
        return array('f', bytes(left)), array('f', bytes(right))

    def delete(self) -> None:
        if self.pointer:
            self._lib.delete_fluid_synth(self.pointer)
            self.pointer = 0


class AudioDriver:
    """Renders ``synth`` to the sound server on FluidSynth's own audio thread."""

    def __init__(self, lib: Library, settings: Settings, synth: Synth) -> None:
        self._lib = lib
        pointer: int | None = lib.new_fluid_audio_driver(settings.pointer, synth.pointer)
        if not pointer:
            raise FluidSynthError('cannot open the FluidSynth audio driver')
        self.pointer = pointer

    def delete(self) -> None:
        if self.pointer:
            self._lib.delete_fluid_audio_driver(self.pointer)
            self.pointer = 0


class Sequencer:
    """A sequencer driven by the synthesizer's sample clock (sample-accurate).

    Ticks are milliseconds unless the time scale is changed.
    """

    def __init__(self, lib: Library) -> None:
        self._lib = lib
        pointer: int | None = lib.new_fluid_sequencer2(0)
        if not pointer:
            raise FluidSynthError('cannot create the FluidSynth sequencer')
        self.pointer = pointer
        # ctypes callbacks must outlive their registration.
        self._callbacks: dict[int, Any] = {}

    def register_fluidsynth(self, synth: Synth) -> int:
        client: int = self._lib.fluid_sequencer_register_fluidsynth(self.pointer, synth.pointer)
        _check(client, 'register the synthesizer with the sequencer')
        return client

    def register_client(self, name: str, callback: EventCallback) -> int:
        """Register a client whose events invoke ``callback(time, event_pointer)``
        on the thread that advances the sequencer (the audio thread)."""

        def trampoline(time: int, event: int | None, _seq: int | None, _data: int | None) -> None:
            try:
                callback(time, event or 0)
            except Exception:
                log.exception('error in sequencer callback')

        c_callback = EVENT_CALLBACK(trampoline)
        client: int = self._lib.fluid_sequencer_register_client(
            self.pointer, name.encode(), c_callback, None
        )
        _check(client, f'register sequencer client {name}')
        self._callbacks[client] = c_callback
        return client

    def unregister_client(self, client: int) -> None:
        self._lib.fluid_sequencer_unregister_client(self.pointer, client)
        self._callbacks.pop(client, None)

    def send_at(self, event: Event, tick: int, *, absolute: bool = True) -> None:
        _check(
            self._lib.fluid_sequencer_send_at(self.pointer, event.pointer, tick, int(absolute)),
            'schedule an event',
        )

    def remove_events(self, source: int = -1, dest: int = -1, kind: int = -1) -> None:
        """Drop pending events matching ``source``, ``dest`` and ``kind`` (-1: any)."""
        self._lib.fluid_sequencer_remove_events(self.pointer, source, dest, kind)

    @property
    def tick(self) -> int:
        value: int = self._lib.fluid_sequencer_get_tick(self.pointer)
        return value

    @property
    def time_scale(self) -> float:
        """Ticks per second."""
        value: float = self._lib.fluid_sequencer_get_time_scale(self.pointer)
        return value

    @time_scale.setter
    def time_scale(self, ticks_per_second: float) -> None:
        self._lib.fluid_sequencer_set_time_scale(self.pointer, ticks_per_second)

    def delete(self) -> None:
        if self.pointer:
            self._lib.delete_fluid_sequencer(self.pointer)
            self.pointer = 0
            self._callbacks.clear()


class Event:
    """A reusable event; the sequencer copies it when it is sent."""

    def __init__(self, lib: Library) -> None:
        self._lib = lib
        pointer: int | None = lib.new_fluid_event()
        if not pointer:
            raise FluidSynthError('cannot create a sequencer event')
        self.pointer = pointer

    def route(self, source: int, dest: int) -> Event:
        self._lib.fluid_event_set_source(self.pointer, source)
        self._lib.fluid_event_set_dest(self.pointer, dest)
        return self

    def noteon(self, channel: int, key: int, velocity: int) -> Event:
        self._lib.fluid_event_noteon(self.pointer, channel, key, velocity)
        return self

    def noteoff(self, channel: int, key: int) -> Event:
        self._lib.fluid_event_noteoff(self.pointer, channel, key)
        return self

    def all_notes_off(self, channel: int) -> Event:
        self._lib.fluid_event_all_notes_off(self.pointer, channel)
        return self

    def program_change(self, channel: int, program: int) -> Event:
        self._lib.fluid_event_program_change(self.pointer, channel, program)
        return self

    def timer(self, data: int) -> Event:
        """A timer event; ``data`` (non-zero) comes back through :func:`event_data`."""
        self._lib.fluid_event_timer(self.pointer, data)
        return self

    def delete(self) -> None:
        if self.pointer:
            self._lib.delete_fluid_event(self.pointer)
            self.pointer = 0


def event_type(lib: Library, event: int) -> int:
    kind: int = lib.fluid_event_get_type(event)
    return kind


def event_data(lib: Library, event: int) -> int:
    data: int | None = lib.fluid_event_get_data(event)
    return data or 0
