# Etude

Learn music theory by eye and by ear.

Etude is a GNOME application for learning music theory and aural skills,
from reading your first notes to the harmony, counterpoint and post-tonal
analysis taught in university music programmes. Every topic is practised
on the staff and by ear, and spaced repetition schedules reviews so that
what you learn stays learned.

> **Status:** early development. See the [roadmap](ROADMAP.md).

## Features (planned for 1.0)

* Notes, key signatures, intervals, scales, scale degrees, chords and
  rhythms, recognised on the staff and by ear
* Ear training from intervals to harmonic dictation, and rhythm tapping
  in time with a metronome
* Short theory lessons with playable examples, and a music glossary
* Four levels, from fundamentals to graduate-level theory
* Spaced repetition (FSRS), interleaved review and immediate, explained
  feedback; see [how Etude teaches](docs/PEDAGOGY.md)
* Accessible: keyboard shortcuts for every answer, screen reader
  feedback, large notation and written alternatives to audio tasks
* Offline, no accounts, no tracking

## Building

Open the project in [GNOME Builder](https://apps.gnome.org/Builder/) and
press Run, or build the Flatpak from the command line:

```sh
flatpak install flathub org.flatpak.Builder
flatpak run org.flatpak.Builder --user --install --force-clean build-dir fi.oikarinenotto.etude.json
flatpak run fi.oikarinenotto.etude
```

## Contributing

Contributions of code, music content, translations and bug reports are
welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) and
[ARCHITECTURE.md](ARCHITECTURE.md) to get started. Everyone taking part
follows the [GNOME Code of Conduct](CODE_OF_CONDUCT.md).

## License

Etude is free software: the code is licensed under the
[GNU General Public License v3.0 or later](LICENSES/GPL-3.0-or-later.txt),
documentation and teaching content under
[CC BY-SA 4.0](LICENSES/CC-BY-SA-4.0.txt). Notation uses the
[Bravura](https://github.com/steinbergmedia/bravura) font (SIL Open Font
License 1.1) and playback uses [FluidSynth](https://www.fluidsynth.org/)
with the [GeneralUser GS](https://github.com/mrbumpy409/GeneralUser-GS)
SoundFont. The project follows the [REUSE](https://reuse.software/)
specification.
