# Adding an exercise

Exercises are data, not UI code. An exercise is a subclass of
`etude.exercises.base.ExerciseDefinition` in a module under
`src/etude/exercises/families/`. The generic exercise page renders any
question it produces, so a new exercise normally needs no widget code.

The reference exercise is
[`key_signatures.py`](../src/etude/exercises/families/key_signatures.py):
read it alongside this guide.

## 1. Choose items

Decide what the learner should *know*, and give every piece of knowledge
an item id under a prefix that no other exercise uses:

```
keysig.major.0       keysig.major.4s      keysig.minor.3b
interval.ear.melodic.asc.m6               interval.ear.harmonic.A4
```

Items are scheduled individually by FSRS, so make them as fine as the
mistakes learners make (a learner can know major thirds but confuse minor
and major sixths). `items(settings)` returns them in teaching order: the
session builder introduces earlier items first.

## 2. Generate questions

`generate(item_id, settings, rng)` builds a fresh `Question` for an item:

* Vary everything that is not the item (root, register, clef, instrument)
  using only `rng`, so tests can reproduce questions from a seed.
* Put notation in `figure` (a `StaffSpec` or `SystemSpec`) and sound in
  `playback` (a `PlaybackSpec`).
* For ear training set `playback_is_question=True` and provide a
  `written_alternative` figure for learners who cannot rely on hearing.
* Choose an `AnswerSpec`. Give every choice option an accelerator
  (`'1'`–`'9'`, or a mnemonic letter) as the design requires.
* If the figure would give the answer away to a screen reader, set
  `description` on the figure yourself. The automatic description names
  every note ("Treble staff, one note: F4"), so a note-naming question
  must describe the staff without the note.
* Write note, key, chord and interval names with `etude.core.naming`
  (`pitch_name`, `key_name`, `chord_name`, `interval_name` …) and never
  pass a convention: the application sets the learner's convention
  (English, German/Nordic H/B or fixed do) as the default.

## 3. Grade with an explanation

`grade(question, given)` returns `Feedback`. Learning research is clear
that *why* matters more than *whether*, so:

* `title`: "Correct — E major" or "Not quite — the answer is a major
  sixth".
* `detail`: the reasoning, e.g. "G4 to E5 spans six letter names and nine
  semitones."
* For ear training, set `play_expected` and `play_given` so the learner can
  compare.

## 4. Describe it for the UI

Optional hooks with sensible defaults:

* `glyph`: the symbol in the home page's icon tile (`'♯'`, `'♪'` …).
* `play_label`: the play button's label, e.g. "Play chord".
* `describe_settings(settings)`: the header subtitle, e.g. "Treble clef ·
  up to 5 accidentals".
* `item_label(item_id)`: an item's name in "Weakest items", e.g.
  "6 flats — key signature".
* `answer_label(question, value)`: how an answer reads in feedback; the
  default joins option labels.
* `ChipGroup(accidentals=True)` adds a ♯ / ♭ chip to a group of natural
  note letters (design 1f).

## 5. Register

Expose the exercises of the module as `EXERCISES`:

```python
EXERCISES = (KeySignatures(),)
```

The registry discovers the module automatically. Add the file to
`src/etude/exercises/families/meson.build` and to `po/POTFILES.in`
(`tests/test_packaging.py` reminds you).

## 6. Test

`tests/exercises/test_all_exercises.py` checks every registered exercise
automatically, under its default settings and each setting at its
extremes: items are unique and owned by the exercise, questions are
deterministic for a seed, the expected answer is one of the options,
accelerators are unique, `grade(expected)` is correct and every wrong
option is graded wrong, and ear-training questions have a written
alternative.

Add `tests/exercises/test_<family>.py` for what only you can check: the
musical facts behind questions and explanations (see
`test_key_signatures.py`).

## 7. Look at it

Render the exercise as the learner sees it, in light and dark, with a
question, a correct and a wrong answer:

```sh
flatpak run --filesystem=$PWD --socket=wayland --command=python3 \
    org.gnome.Sdk//51 tests/ui/screenshots.py --output build/screenshots --live keysig
```

(The SDK has no `fsrs`; put a copy of it on `PYTHONPATH` inside the
sandbox, for example from your virtual environment.)
