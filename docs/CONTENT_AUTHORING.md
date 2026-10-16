# Writing content

Etude's teaching content lives in `data/content/` as XML: the curriculum,
the theory lessons and the glossary. This guide explains the formats. The
reference lesson
[`lessons/level1/staff.xml`](../data/content/lessons/level1/staff.xml) uses
every element; read it alongside this guide.

Content is licensed CC-BY-SA-4.0; give every file the SPDX header comment
the existing files have.

## Principles

Content follows [docs/PEDAGOGY.md](PEDAGOGY.md):

* **Explain, then let the learner retrieve.** End every section that
  introduces an idea with a `<check>` question. Explanations of checks say
  *why* the answer is right.
* **Worked examples before problems.** Show a problem solved step by step
  (`<worked>`), then ask a similar one.
* **Notation and sound together.** Give examples a `play` attribute when
  hearing them helps.
* **Short and concrete.** A paragraph is two to four sentences. Prefer an
  example to an abstract rule.
* **Correct.** Every musical statement must be true for common-practice
  theory as taught in conservatories; when conventions differ (for example
  the naming of the minor scale's seventh degree), say so. A different
  agent or person fact-checks every lesson before it is merged.

## Writing for translation

The source language is English; translators translate whole paragraphs
with the markup inside. Therefore:

* Write **note names** as `<note>Bb4</note>` or `<note>F#</note>` (letter,
  `#`/`b` or `♯`/`♭`, optional octave), never as plain text. The
  application writes them in the learner's convention: B♭4, B4 or Si♭4.
  English mnemonics built from letters ("Every Good Boy…") do not work in
  other languages or with H/B names; list the letters as `<note>`
  elements instead.
* Mark **glossary terms** with `<term ref="entry-id">text</term>`; the
  text is translated, the ref is not.
* Avoid jokes, idioms and wordplay; keep sentences complete (no sentences
  assembled from pieces).

## The curriculum: `curriculum.xml`

```xml
<level id="level1" number="1">
  <title>Fundamentals</title>
  <description>…</description>
  <unit id="l1.staff" lesson="l1.staff">
    <title>Staff, Clefs and Note Names</title>
    <summary>Read notes in the treble and bass clefs, with ledger lines.</summary>
    <requires unit="l1.other"/>          <!-- optional; default: the previous unit -->
    <practice exercise="note-naming">    <!-- an exercise id from the registry -->
      <setting key="clefs" value="treble bass"/>   <!-- multi-choice: space-separated -->
      <setting key="ledger-lines" value="1"/>
    </practice>
    <vocabulary tags="staff"/>           <!-- glossary entries of this level with these tags -->
  </unit>
  <exam size="30"/>
</level>
```

Unit ids are `l<level>.<name>`. Settings use the keys and option keys of
the exercise's settings (see the exercise module or its setup page);
`tests/exercises/test_curriculum_practices.py` checks them.

## Lessons: `lessons/level<N>/<name>.xml`

```xml
<lesson id="l1.staff">
  <title>Staff, Clefs and Note Names</title>
  <summary>One sentence shown on the curriculum map.</summary>
  <section>
    <title>The staff</title>
    … blocks …
  </section>
</lesson>
```

Blocks inside a section:

| Element | Use |
|---|---|
| `<p>` | A paragraph. Inline: `<em>`, `<term ref>`, `<note>`. |
| `<list>` / `<list ordered="true">` with `<li>` | A list. |
| `<callout kind="tip\|remember\|warning">` with `<p>` | A highlighted box. `remember` for facts to memorise. |
| `<figure>` | A notated example, see below. |
| `<worked>` with `<title>` and `<step>`s | A worked example; each step has `<p>`s and optionally a `<figure>`. |
| `<check id="…">` | A question: `<prompt>`, optional `<figure>`, two to five `<option key="…">` with exactly one `correct="true"`, and an `<explanation>`. |

A check's figure must not reveal its answer to screen readers: give it a
`<description>` that describes the staff without the note asked about
(the automatic description names every note).

## Notated examples: `<figure>`

```xml
<figure play="melodic" tempo="100">
  <staff clef="treble" key="-2" time="3/4">Bb4/q C5/q D5/q | Eb5/h.</staff>
  <caption>The first notes of a B♭ major scale.</caption>
</figure>
```

* `clef`: `treble`, `bass`, `alto`, `tenor`, `treble_8vb`, `percussion`.
* `key`: the key signature as a number of sharps (positive) or flats
  (negative).
* `time`: a time signature such as `4/4`, `6/8` or `7/8`.
* Two or more `<staff>` elements make a system (grand staff, SATB): their
  events line up by onset.
* `play`: `as-written` (rhythm as notated; notes without a duration last
  one beat; staves together), `melodic` (every pitch in turn, chords
  low to high) or `harmonic` (everything together). Omit it for no sound.
* `<description>`: replaces the automatic screen-reader description.

The notation inside `<staff>` is a list of tokens:

| Token | Meaning |
|---|---|
| `C4` | A note without rhythm (a black notehead without a stem). |
| `F#4/q` | A quarter note. Durations: `w h q e s t` (whole … 32nd). |
| `Bb3/h.` | Dots follow the duration. |
| `G4/e3` | A triplet eighth (a digit after the duration: 3, 5 or 6 in the time of 2 or 4). |
| `[C4 E4 G4]/h` | A chord. |
| `r/q` | A rest. |
| `*E4` | Highlighted in the accent colour with a halo. |
| `G4/q{5}` | With a label below the staff (use digits or Roman numerals, not words). |
| `D4/h~` | Tied to the next note. |
| `\|` `\|\|` `\|.` `\|:` `:\|` | Barlines: single, double, final, repeat start, repeat end. |

Accidentals are drawn as needed for the key signature and earlier notes in
the bar.

## The glossary: `glossary/<topic>.xml`

```xml
<glossary tags="performance">
  <entry id="crescendo" level="1" tags="dynamics">
    <term>crescendo</term>                <!-- the term in the learner's language -->
    <foreign lang="it">crescendo</foreign> <!-- an original-language term, never translated -->
    <gloss>gradually louder</gloss>        <!-- a few words: flashcards use it -->
    <def>Getting gradually louder. …</def>  <!-- one to three sentences -->
    <abbr>cresc.</abbr>
    <figure>…</figure>                     <!-- optional example -->
    <see ref="diminuendo"/>
  </entry>
</glossary>
```

* `id`: lower case with hyphens, unique across all files.
* `level`: the curriculum level that introduces the term; unit vocabulary
  is chosen by level and tags.
* Use `<foreign>` for Italian, German or French terms that musicians use
  untranslated (Allegro, crescendo, Lied); flashcards then ask for that
  term.
* A gloss is not a definition: "gradually louder", not "a direction to…".

## Checking your work

```sh
.venv/bin/pytest tests/content tests/exercises/test_curriculum_practices.py
xmllint --noout --relaxng data/content/schema/lesson.rng data/content/lessons/level1/*.xml
```

Add every new file to the `meson.build` of its directory and to
`po/POTFILES.in`; `tests/test_packaging.py` reminds you.

## How translation works

`xgettext` extracts the translatable elements (marked in
`data/content/its/etude.its`) into `po/etude.pot`. At build time
`i18n.itstool_join` merges the translations into the installed XML: each
translated element is followed by its translations with `xml:lang`, and
the application picks the learner's language when it loads the content.
