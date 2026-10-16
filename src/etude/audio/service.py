# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

"""Choose the audio backend for the application."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path

from .. import paths
from .backend import AudioBackend
from .fluid_backend import FluidSynthBackend
from .fluidsynth import FluidSynthError
from .null import NullBackend

log = logging.getLogger(__name__)

LIBRARY_ENV = 'ETUDE_FLUIDSYNTH_LIB'
SOUNDFONT_ENV = 'ETUDE_SOUNDFONT'
SOUNDFONT = ('soundfonts', 'GeneralUser-GS.sf2')


def soundfont_path(environ: Mapping[str, str] = os.environ) -> Path:
    """The SoundFont to load: ``$ETUDE_SOUNDFONT`` or the bundled GeneralUser GS."""
    override = environ.get(SOUNDFONT_ENV)
    return Path(override) if override else paths.data_file(*SOUNDFONT)


def create_backend(environ: Mapping[str, str] = os.environ) -> AudioBackend:
    """FluidSynth with the bundled SoundFont, or a silent backend if that fails.

    ``$ETUDE_FLUIDSYNTH_LIB`` overrides the FluidSynth library to load.
    """
    soundfont = soundfont_path(environ)
    library = environ.get(LIBRARY_ENV) or None
    try:
        return FluidSynthBackend(soundfont, library=library)
    except FluidSynthError as error:
        log.warning('Sound is off: %s', error)
    except Exception:
        log.exception('Sound is off: the FluidSynth backend failed to start')
    return NullBackend()
