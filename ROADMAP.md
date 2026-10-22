# Roadmap

Etude is built in waves. Each wave ends with green CI, a review, and an
installable Flatpak bundle from CI for testing. The first public release
(1.0 on Flathub) comes after all four curriculum levels and the W8–W9 additions are
complete.

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

- [x] Rhythm: tapping, timing windows, rhythm engraving
- [x] Lessons: XML schema, renderer, ITS/gettext pipeline
- [x] Glossary and flashcards, curriculum map, placement test, level exam
- [x] Remaining level 1 exercises and all level 1 lessons and vocabulary, fact-checked

## W4 — Level 2 (intermediate)

- [x] Staff input and SATB voice-leading checker; one four-part voicer (`checkers.realize`)
      with textbook doubling; four-part writing and spot the error
- [x] Seventh chords, Roman numeral analysis, cadences, figured bass, modes, transposition
- [x] Melodic and rhythmic dictation, cadences, progressions and inversions by ear
- [x] Level 2 lessons and vocabulary (155 glossary entries), fact-checked
- [x] Answer options in random order everywhere (exercises and lesson checks)
- [x] App icon

## W5 — Level 3 (undergraduate)

- [x] Species counterpoint checker (species 1–5), cantus firmi and model solutions;
      counterpoint writing and errors
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

## W8 — Levels 1–2 completed, aural skills without a microphone

- [ ] Nonchord tones on the staff: passing, neighbor, suspension, retardation, appoggiatura,
      escape tone, anticipation, pedal
- [ ] Phrase and period: sentence or period, parallel or contrasting, the cadence of each phrase
- [ ] Figured bass realization: write the upper voices over a figured bass (four-part checker)
- [ ] Melody harmonization: choose the chords for a given soprano and write the inner voices
- [ ] Symbols: ornaments (trill, mordent, turn, appoggiatura) and road map signs (D.C., D.S.,
      coda, first and second endings, 8va)
- [ ] Error detection by ear: a performance differs from the printed score in one pitch or rhythm
- [ ] Two-voice (outer voices) dictation
- [ ] Which notated melody did you hear (inner hearing, in place of sight-singing)
- [ ] Lessons, vocabulary and level exams updated, fact-checked

## W9 — Extended theory and real-instrument sound

- [ ] Twentieth-century techniques: whole-tone, octatonic and blues scales, modes of limited
      transposition, quartal and quintal harmony, polychords, bitonality, planing,
      pandiatonicism, minimalism and aleatory
- [ ] Late-Romantic chromaticism: common-tone diminished sevenths, augmented triads,
      linear chromaticism (the Tristan chord)
- [ ] Acoustics and tuning: the harmonic series, cents, equal, just and meantone temperament;
      tuning discrimination by ear
- [ ] Blues and popular forms: twelve-bar blues, AABA, rhythm changes, verse–chorus, mixture in pop
- [ ] Tonal counterpoint: two-part invention, canon, writing a fugue exposition
- [ ] Schenkerian analysis exercises (choose the reduction, find the Urlinie); hypermeter and
      metric dissonance
- [ ] Instrument recognition and ranges; movable-do solfège as a naming option; tempo and
      dynamics by ear
- [ ] Real-instrument sound: freely licensed sampled piano and orchestral instruments, as an
      optional Flatpak extension so the base download stays small
- [ ] Lessons and vocabulary for every addition, fact-checked

## W10 — Release 1.0

- [ ] Finnish translation complete; `flatpak-builder-lint` clean
- [ ] Beta testing with CI bundles
- [ ] Tag and release notes
- [ ] Flathub submission (app id domain verification for oikarinenotto.fi), only after the
      maintainer confirms
- [ ] Translation platform
