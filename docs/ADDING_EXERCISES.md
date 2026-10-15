# Adding an exercise

Exercises are data, not UI code. An exercise is a subclass of
`etude.exercises.base.ExerciseDefinition` in a module under
`src/etude/exercises/families/`. The generic exercise page renders any
question it produces, so a new exercise normally needs no widget code.

## 1. Choose items

Decide what the learner should *know*, and give every piece of knowledge
an item id under a prefix that no other exercise uses:

```
keysig.major.0       keysig.major.4s      keysig.minor.3f
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
  `description` on the figure yourself.

## 3. Grade with an explanation

`grade(question, given)` returns `Feedback`. Learning research is clear
that *why* matters more than *whether*, so:

* `title`: "Correct — E major" or "Not quite — the answer is a major
  sixth".
* `detail`: the reasoning, e.g. "G4 to E5 spans six letter names and nine
  semitones."
* For ear training, set `play_expected` and `play_given` so the learner can
  compare.

## 4. Register

Expose the exercises of the module as `EXERCISES`:

```python
EXERCISES = (KeySignatures(),)
```

The registry discovers the module automatically. Add the file to
`src/etude/exercises/families/meson.build` and to `po/POTFILES.in`
(`tests/test_packaging.py` reminds you).

## 5. Test

Add `tests/exercises/test_<family>.py` with at least:

* a property test over many seeds and every item: the expected answer is
  one of the options, options are distinct, `grade(expected)` is correct
  and a wrong option is graded wrong;
* tests of the musical facts behind the explanations;
* a test that ear-training questions have a written alternative.

## Skeleton

```python
# SPDX-FileCopyrightText: 2026 Your Name
# SPDX-License-Identifier: GPL-3.0-or-later

"""Key signatures: name the key from the accidentals on the staff."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from gettext import gettext as _

from ...learning.model import ItemId
from ..base import ChoiceAnswer, ExerciseDefinition, Family, Feedback, Modality, Question


class KeySignatures(ExerciseDefinition):
    id = 'key-signatures'
    item_prefix = 'keysig.'
    family = Family.NOTATION
    modality = Modality.EYE
    level = 1
    icon_name = 'music-key-signature-symbolic'

    @property
    def title(self) -> str:
        return _('Key Signatures')

    @property
    def description(self) -> str:
        return _('Name the major or minor key from the sharps and flats on the staff.')

    def items(self, settings: Mapping[str, object]) -> Sequence[ItemId]: ...

    def generate(
        self, item_id: ItemId, settings: Mapping[str, object], rng: random.Random
    ) -> Question: ...

    def grade(self, question: Question, given: object) -> Feedback: ...


EXERCISES = (KeySignatures(),)
```
