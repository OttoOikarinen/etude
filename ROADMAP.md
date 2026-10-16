# Roadmap

Etude is built in waves. Each wave ends with green CI, a review, and an
installable Flatpak bundle from CI for testing. The first public release
(1.0 on Flathub) comes after all four curriculum levels are complete.

## W0 — Foundation

- [x] Python package under `src/etude/`, one `meson.build` per subpackage
- [x] Flatpak manifest on GNOME 51 with FluidSynth, GeneralUser GS and FSRS; no network access
- [x] Desktop file, AppStream metadata and GSettings schema
- [x] Tooling: ruff, mypy, pytest, hypothesis, import-linter, codespell, REUSE, pre-commit
- [x] CI: lint and unit tests; Flatpak build, `meson test` and bundle artifact
- [x] Contracts: core value types, notation spec and display list, audio spec and backend,
      learning model and ports, exercise framework
- [x] Documentation: architecture, pedagogy, adding exercises, contributing
- [x] Spike: FluidSynth builds and renders sound in the GNOME 51 SDK sandbox (SoundFont, PulseAudio);
      Bravura renders with `Gtk.Snapshot`

## W1 — Engines

- [x] Theory core: scales and modes, keys, chords and inversions, Roman numerals, figured bass,
      chord symbols, pitch-class sets, tone rows, note naming conventions
- [x] Notation engine: clefs, key and time signatures, notes, accidentals, ledger lines, stems,
      chords, beams, rests, tuplets, grand staff, hit-testing, accessible descriptions,
      golden tests, `StaffView` widget
- [x] Audio: FluidSynth backend, metronome, latency calibration
- [x] Learning engine and storage: SQLite schema and migrations, FSRS scheduler, session
      builder, mastery, statistics
- [x] UI shell: the design's screens with stub data, all answer widgets, adaptive layouts,
      dark style

## W2 — Integration and the designed exercises

- [x] Generic exercise page wired to the framework, scheduler and storage
- [x] Key signatures, note naming, intervals (staff and ear), chords, scale degrees
- [x] Today review, progress page, session summary, generated setup page
- [x] All 14 design mockups work with real data

## W3 — Level 1 (fundamentals)

- [ ] Rhythm: tapping, timing windows, rhythm engraving
- [ ] Lessons: XML schema, renderer, ITS/gettext pipeline
- [ ] Glossary and flashcards, curriculum map, placement test, level exam
- [ ] Remaining level 1 exercises and all level 1 lessons and vocabulary, fact-checked

## W4 — Level 2 (intermediate)

- [ ] Staff input and SATB voice-leading checker
- [ ] Seventh chords, Roman numeral analysis, cadences, figured bass, modes, transposition
- [ ] Melodic and rhythmic dictation, progressions by ear
- [ ] Level 2 lessons and vocabulary, fact-checked

## W5 — Level 3 (undergraduate)

- [ ] Species counterpoint checker (species 1–5)
- [ ] Chromatic harmony and modulation, harmonic dictation, C clefs, jazz chord symbols and
      voicings, form analysis
- [ ] Level 3 lessons and vocabulary, fact-checked

## W6 — Level 4 (graduate)

- [ ] Pitch-class set analysis, twelve-tone matrices, neo-Riemannian transformations
- [ ] Atonal ear training, polyrhythm and metric modulation
- [ ] Level 4 lessons and vocabulary, level exams for every level

## W7 — Polish

- [ ] Accessibility audit: Orca, keyboard only, contrast, large notation, written alternatives
- [ ] Performance, progress export and import, help, screenshots, release notes
- [ ] Finnish translation complete; `flatpak-builder-lint` clean
- [ ] Beta testing with CI bundles

## W8 — Release 1.0

- [ ] Tag and release notes
- [ ] Flathub submission (app id domain verification for oikarinenotto.fi)
- [ ] Translation platform
