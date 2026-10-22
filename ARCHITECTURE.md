# Architecture

Etude is a GNOME application written in Python with GTK 4 and
libadwaita, built with Meson and distributed as a Flatpak. This document
explains how the code is organised, which rules keep it maintainable, and
where to start when you change something.

## Layers

```
┌───────────────────────────────────────────────────────────────┐
│ etude.main, etude.window, etude.ui        application shell,  │
│ etude.notation.widget (StaffView)         pages, widgets      │  GTK
├───────────────────────────────────────────────────────────────┤
│ etude.exercises   etude.storage                               │
├───────────────────────────────────────────────────────────────┤
│ etude.content     (curriculum, lessons, glossary)             │
├───────────────────────────────────────────────────────────────┤
│ etude.learning  etude.notation  etude.audio  etude.checkers   │  pure
├───────────────────────────────────────────────────────────────┤  Python
│ etude.core        (music theory value types)                  │
└───────────────────────────────────────────────────────────────┘
```

* A layer may import the layers below it, never above. Packages on the
  same layer are independent of each other.
* Only the shell, `etude.ui` and `etude.notation.widget` import `gi`.
  Everything else is plain Python and is tested without a display.
* Both rules are enforced by import-linter (`lint-imports`, configured in
  `pyproject.toml`).

| Package | Responsibility |
|---|---|
| `core` | Spelled pitches, intervals, scales, keys, chords, Roman numerals, rhythm, set theory, note naming conventions. Immutable value types. |
| `notation` | `spec` describes what to engrave; `layout` turns it into a `displaylist` in staff-space units using Bravura (SMuFL) metrics; `a11y` describes it in words; `widget` draws it. |
| `audio` | `spec` describes what to play; `backend` is the interface; FluidSynth plays it, `null` stands in for tests and machines without sound. |
| `learning` | FSRS scheduling, ratings derived from answers, session building (interleaving, new vs. review), mastery, placement, statistics. Talks to storage and exercises only through `learning.ports`. |
| `storage` | SQLite implementation of the `learning.ports` stores, with migrations. |
| `checkers` | Rule checkers for written music: four-part voice leading (W4) and species counterpoint (W5). Pure, on top of `core`. |
| `exercises` | `base` is the framework; `families/` holds the exercises; `registry` discovers them. |
| `content` | Curriculum, theory lessons and glossary loaded from `data/content/` (formats: docs/CONTENT_AUTHORING.md); `music_text` reads the compact notation of examples. Below `exercises`, so exercises such as vocabulary flashcards can use the glossary. |
| `ui` | Pages, widgets and dialogs following the design mockups. |

## Contracts

The modules below are the interfaces between work streams. Change them
deliberately, in their own pull request, and update this document.

* `etude/core/pitch.py`, `interval.py`, `rhythm.py`, `key.py`: the
  value types everything else is built on.
* `etude/notation/spec.py` and `displaylist.py`: what the engraver accepts
  and produces.
* `etude/audio/spec.py` and `backend.py`: what the synthesizer accepts.
* `etude/learning/model.py` and `ports.py`: knowledge items, cards,
  outcomes, sessions, and the storage and catalogue protocols.
* `etude/exercises/base.py`: questions, answer specifications, feedback,
  settings and the `ExerciseDefinition` base class.
* `etude/content/model.py`: curriculum, lessons and glossary as the UI
  renders them; the XML formats in docs/CONTENT_AUTHORING.md and
  `data/content/schema/`.

Contract changes so far (all backwards-compatible):

* W1 audio: `PlaybackNote.percussion` plays a GM drum key on channel 10;
  `PlaybackSpec.meter` makes the metronome count felt pulses with accented
  downbeats.
* W1 learning: `SessionRecord` and `SessionLog.between()` let statistics
  compute time practised, session counts and personal bests.
* W4: `StaffInputAnswer` gained `staves`, `voice_staves`, `given_voices` and `rhythm` (slot durations for dictation)
  for four-part writing on a grand staff (values list one pitch per voice,
  top voice first); new package `etude.checkers` with the voice-leading
  checker's API (`Rule`, `Severity`, `Violation`, `Context`, `check`).
* W4 checker: `check()` is implemented (rule decisions in the module
  docstring of `etude.checkers.voice_leading`); additions: `Violation.slots`
  (the chords involved), `MOTION_RULES`, `scan()` (fast, without messages),
  `errors()`, and the names `voice_name()`, `voice_title()`, `rule_name()`,
  `rule_mark()` and `rule_reason()`. New module `etude.checkers.realize` is
  the only four-part voicer: `realize(numerals or chords, key, rng, bass=,
  soprano=)` returns correct SATB voicings or raises `RealisationError`.
* W4 voicer follow-up: `realize()` doubles as textbooks do (root of root-position
  triads, bass of ii°6/vii°6 and six-fours, third of vi after V), accepts a set of
  pitch names per chord in `soprano=`, takes `complete=True` for every chord tone,
  and keeps half steps in the bass (the Phrygian iv6–V); `scan()` gained `first=`.
* W4 four-part input: `StaffInputAnswer.labels` (text under each slot, the Roman
  numerals of four-part writing). New pure module `etude.notation.parts`
  (`voices_figure`, `event_index`: voices on their staves and their combined
  event numbering). The staff input (`ui.widgets.staff_entry` / `staff_input`)
  writes several voices on a grand staff (1–4 and Tab choose the voice, printed
  `given_voices` cannot be selected) and draws `StaffInputAnswer.rhythm`; an
  answer widget with `show_feedback_figure(figure)` shows `Feedback.figure` on
  its own staff instead of the page's figure (voice-leading mistakes marked
  where they were written; four-part answers only). `harmony.satb_figure` gained
  `inks` and `marks`, and `satb_voices` keeps the voice order of stemmed figures
  even when voices cross.
* W5 counterpoint: new pure modules in `etude.checkers`. `counterpoint` checks
  two-voice species counterpoint (species 1–5) against a cantus firmus in a mode:
  `check(cantus, counterpoint, Context(mode, species, above, rhythm))`, `scan()`,
  `errors()`, `check_cantus()`, `Rule`, `Violation` (with the counterpoint `notes` and
  `cantus` notes involved), `Rhythm` and `species_rhythm()`, and the names
  `voice_name()`, `rule_name()`, `rule_mark()` and `rule_reason()` (rule decisions and
  sources in its docstring; every two-voice solution in Fux's figures passes).
  `cantus` holds Fux's six cantus firmi (`FUX`), `generate()` writes new ones, and
  `modal_keys()` / `signature()` transpose the modes. `species.realize()` and
  `solve()` find model counterpoints (`solve` also chooses the fourth- and
  fifth-species rhythm: `fourth_rhythm()`, `florid_rhythm()`).
* W4 exercises: `Question.details`, exercise-private facts needed again when
  grading (the keys of a transposition); not shown to the learner.
* W4 notation: lines of a `Chord.label` separated by `'\n'` are stacked
  downwards (figured-bass figures); the layout emits one `TextItem` per line.
* W3 content: `etude.content` moved below `etude.exercises` in the layers;
  content model, loaders and XML formats added. W2 follow-up:
  `Question.playback_style_choice` and `ExerciseDefinition.confusables()`.
* W2 exercises: `ChipGroup.accidentals`; `ExerciseDefinition.glyph`,
  `play_label`, `item_label()` and `answer_label()` (all with defaults).
  `etude.core.naming` gained a default convention, set from the
  `note-naming` setting.
* W2 sessions: `SessionRunner.pause()`, `resume()`, `is_open` and
  `is_answered`; `finish()` now refuses to close a session that the engine
  already finished because another one started. `LearningEngine` gained
  `pause_session()`, `resume_session()`, `active_session_id` and
  `new_items()`; `Stats.session_summary()` takes the paused time.
* W3 learning path: `SessionMode.PLACEMENT` and `LEVEL_EXAM` are implemented
  (explicit `SessionRequest.item_ids`: the placement test keeps their order,
  the exam shuffles and interleaves them, neither limits new items), and
  `DAILY_REVIEW` with `item_ids` is restricted to that set (practising one
  curriculum unit; filled with the set's least-recalled known items when
  little is due or new). New pure module `learning.placement`
  (`PASS_FRACTION`, `balanced_sample`, `PlacementWalk`). `SessionRunner` gained
  an optional `title` and `drop_upcoming()`; `ExamRunner` and
  `PlacementRunner` in `exercises.path` subclass it.
* W3 notation: `GlyphFigure(glyphs, description, staff=False, ink)` joins the
  `Figure` union for symbols shown on their own (dynamics, hairpins,
  articulations on a note); `smufl.CODEPOINTS` gained the dynamics,
  articulation, fermata and precomposed-note glyphs it uses. `StaffView`
  gained `display_point()`, `staff_position_at()` and `reserve_positions()`
  for staff input.
* W1 notation: `CurveItem` (ties) joins the display-list `Item` union,
  `GlyphItem.scale` lets a brace span a system, and `StaffSpec.voices`
  adds further voices to a staff (first voice stems up, the rest down).
* W3 rhythm: `PlaybackSpec.duration` gives a playback a least length, so a
  playback of metronome beats alone (the bars a learner taps in) keeps
  counting beats and finishes after them; `TapAnswer.bars` and
  `TapAnswer.click`; `etude.audio.latency.EventClock` maps GDK event stamps
  to the monotonic clock. In the UI, `AppModel.play()` takes `on_beat` and
  `on_finished` and returns the `PlaybackHandle` (old callers are
  unaffected), `AnswerWidget.player` and `AnswerWidget.captures_space` let
  the tap pad time a take and own the Space key.

### Rhythm timing

The tap pad (`etude.ui.widgets.tap_pad`) and the calibration page
(`etude.ui.dialogs.calibration`) share one design:

* A take is a `PlaybackSpec` with a count-in and `duration` bars of
  metronome only. `etude.ui.timing.model_player()` plays it through the
  model's audio, or with `TimerPlayback` (GLib timeouts, same beats) when
  there is no sound, so the beat lights alone can pace the learner.
* `PlaybackHandle.started_at` is beat 0 on `time.monotonic()`
  (`CLOCK_MONOTONIC`, the clock of `GLib.get_monotonic_time()`). Taps are
  put on that clock from the GDK event's own timestamp with `EventClock`,
  so main-loop delays (redrawing beat lights) do not move them; events
  without a stamp use their arrival time.
* A tap's value is `(tap - started_at) * 1000 - audio-latency-ms`. The
  calibration plays sixteen clicks after a count-in and stores the median
  tap-minus-click offset (`estimate_offset`).
* Rhythm tapping is graded with `grade_taps`: ±50 ms is on time and ±100 ms
  a little early or late at 120 BPM and slower (narrower when faster);
  `score` counts on-time taps fully and slightly-off taps half, missed
  notes and extra taps count against it, and the answer passes at
  `PARTIAL_CREDIT_PASS`.

### How a question flows

```
SessionBuilder ──plans──▶ (exercise id, item id)
      │
      ▼
ExerciseDefinition.generate(item, settings, rng) ──▶ Question
      │                                   figure ──▶ layout ──▶ StaffView
      │                                   playback ─▶ AudioBackend
      ▼
ExercisePage renders Question.answer (choice, piano, chips, staff input…)
      │ learner answers
      ▼
ExerciseDefinition.grade(question, given) ──▶ Feedback ──▶ FeedbackBanner
      │
      ▼
Outcome ──derive_rating──▶ Rating ──Scheduler.review──▶ Card ──▶ CardStore
```

### Who runs a session

* `etude.services.Services` owns the long-lived objects: the SQLite
  database, the exercise registry, the `LearningEngine` and the audio
  backend (started on first use).
* `etude.exercises.runner.SessionRunner` runs one session: it asks the
  engine for a plan, generates and grades questions with the exercise
  definitions and records every answer. It has no UI code.
* `etude.ui.model.LiveModel` turns statistics into page data and starts
  runners; `etude.ui.preview.PreviewModel` serves the design mockups' fixed
  data instead, for screenshots and UI tests. The window only sees the
  `AppModel` protocol.
* `etude.ui.controller.ExerciseController` connects an `ExercisePage`, a
  running session and the model's audio, and shows the summary dialog.
* Leaving an exercise page before the end *interrupts* its session:
  `LiveModel.close_session()` pauses the runner (the engine keeps the
  session open, and paused time is not practice) and the home page's
  Continue banner offers it. Resume continues the same runner, so the
  summary covers every answer; dismissing it, starting any other session,
  or quitting finishes it so that its answers and time count. A session
  closed before its first answer is finished empty, and statistics ignore
  sessions without answers. Interrupted sessions live in memory only: the
  engine's open session cannot outlive the process, and persisting it
  would need a storage change.
* The learning path (`etude.exercises.path.LearningPath`) turns curriculum
  units into knowledge items (the union of their practices' items under the
  practice settings, plus vocabulary items `vocab.<entry-id>.<direction>`
  of the unit's glossary entries), and computes mastery and unlocking: a
  unit is complete at 80 % mastered items (`learning.mastery`), when placed
  out or when its level exam was passed; it unlocks when the units it
  requires are complete. Units without items pass on the state of the units
  before them. Unit practice is a `DAILY_REVIEW` restricted to the unit's
  items, run with the unit's practice settings on top of the learner's.
  The Path page (`ui.pages.path`) shows it; Theory (`ui.pages.lessons`)
  lists the lessons, which `ui.pages.lesson` renders with the widgets of
  `ui.content`; the Glossary page searches all entries and opens them in
  `ui.dialogs.glossary_entry`. Passed levels, placed-out units and
  completed lessons are GSettings string lists (`passed-levels`,
  `placed-units`, `completed-lessons`), not database tables. Lesson check
  questions are not scheduled; answering all of them completes the lesson.
* The Today page (`etude.ui.pages.today`) shows `LiveModel.today()`: due
  cards per exercise (`CardStore.due`), the new items daily reviews may
  still introduce (`LearningEngine.new_items`), the daily goal and the
  streak. Its button starts a `DAILY_REVIEW`.

### Knowledge items

The scheduler works on *knowledge items*, not on questions. An item is a
hierarchical string id owned by exactly one exercise, for example
`keysig.major.4s`, `interval.ear.melodic.asc.m6` or `vocab.term.fermata`.
Each exercise declares a unique `item_prefix`. `generate()` produces a new
concrete question for an item every time (different root, register, clef
or instrument), so learners practise the concept and not one memorised
picture or sound.

Ids are stored in learners' databases: never rename an item id without a
storage migration.

## Data and settings

* Read-only data (fonts, SoundFont, content) lives in `data/` in the source
  tree and in `pkgdatadir` once installed; find it with
  `etude.paths.data_file()`.
* Preferences are GSettings keys (`data/fi.oikarinenotto.etude.gschema.xml`).
* Learning data is a SQLite database in the user data directory
  (`~/.var/app/fi.oikarinenotto.etude/data/etude/` under Flatpak).
* The app never uses the network.

## Building and running

The supported way to build is Flatpak, either from GNOME Builder (open
the project and press Run) or on the command line:

```sh
flatpak install flathub org.flatpak.Builder
flatpak run org.flatpak.Builder --user --install --force-clean build-dir fi.oikarinenotto.etude.json
flatpak run fi.oikarinenotto.etude
```

For a quick check of the Meson build without Flatpak packaging, run
Meson from the SDK:

```sh
flatpak run --filesystem="$PWD" --command=sh org.gnome.Sdk//51 \
    -c 'meson setup _build && meson test -C _build'
```

### Notes on dependencies

* FluidSynth is built with `-Denable-signalsmith=OFF`: that optional
  reverb and limiter component downloads sources while configuring, which
  Flatpak builds do not allow. FluidSynth's default reverb is used.
* Bravura is registered at startup with
  `PangoCairo.FontMap.get_default().add_font_file()` and drawn with
  `Gtk.Snapshot.append_layout()`. SMuFL fonts are scaled so that one em
  equals four staff spaces; a glyph's SMuFL origin is the Pango baseline.

## Testing

* `tests/` mirrors the package layout. Domain packages are tested with
  pytest and hypothesis on any Python ≥ 3.13; run `pytest`.
* Notation layout is golden-tested: display lists are compared against
  JSON files in `tests/notation/golden/` (regenerate with
  `ETUDE_UPDATE_GOLDEN=1`). Rendering is reviewed with
  `tools/notation_gallery.py`, which draws the design figures and a stress
  sheet to PNG.
* Every exercise has a property test that generates many questions and
  checks that the expected answer is among the options, the options are
  distinct, and grading the expected answer succeeds.
* `meson test` (also run in the Flatpak CI job) validates the desktop file,
  AppStream metadata and GSettings schema, and runs UI smoke tests.
* `tests/test_packaging.py` checks that every module is listed in Meson,
  every `.ui` file is in the GResource, and translatable files are in
  `po/POTFILES.in`.

## Conventions

* Code style is enforced by ruff (format and lint) and mypy `--strict` for
  the domain packages. Line length is 100.
* Every file starts with SPDX headers (`SPDX-FileCopyrightText` and
  `SPDX-License-Identifier`); files that cannot hold a header are covered by
  `REUSE.toml`. Code is GPL-3.0-or-later, documentation and teaching
  content CC-BY-SA-4.0.
* English is the source language. Every user-visible string goes through
  gettext (`from gettext import gettext as _`), including strings produced
  by exercises.
* Note names are never hard-coded in UI text: use the naming helpers in
  `etude.core` so that learners can choose English (C–B), German/Nordic
  (C–H, with B for B♭) or fixed-do names.
* Colour is never the only signal: states use colour, icon and text, and
  notation inks are semantic (`Ink.SUCCESS`, not green).
