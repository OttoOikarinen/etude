# Contributing to Etude

Thank you for helping! This guide covers code, music content and
translations. Please also read [ARCHITECTURE.md](ARCHITECTURE.md).

## Development setup

```sh
git clone https://github.com/OttoOikarinen/etude.git
cd etude
python3 -m venv .venv
.venv/bin/pip install --group dev
.venv/bin/pre-commit install
```

The virtual environment holds the linters and test tools. The application
itself runs as a Flatpak, so you also need Flatpak Builder (or GNOME
Builder):

```sh
flatpak install flathub org.flatpak.Builder
flatpak run org.flatpak.Builder --user --install --force-clean build-dir fi.oikarinenotto.etude.json
flatpak run fi.oikarinenotto.etude
```

## Before you open a pull request

Run the same checks as CI:

```sh
source .venv/bin/activate
ruff check && ruff format --check
mypy
lint-imports
codespell
reuse lint
pytest
```

The pre-commit hooks run most of these automatically.

* Keep pull requests focused on one change. Large features are split
  along the contracts described in ARCHITECTURE.md.
* Add tests with every change. Domain packages aim for at least 90 %
  coverage.
* New Python files go into their directory's `meson.build`; new `.ui`
  files into `src/etude/etude.gresource.xml`; files with translatable
  strings into `po/POTFILES.in`. `tests/test_packaging.py` checks this.
* Start new files with SPDX headers:

  ```python
  # SPDX-FileCopyrightText: 2026 Your Name
  # SPDX-License-Identifier: GPL-3.0-or-later
  ```

* Write commit messages in the imperative mood ("Add interval exercise"),
  with a short summary line and an explanation of *why* in the body when
  it is not obvious.

## Music content

Correctness matters more than quantity. When you add or change lessons,
glossary entries or exercises:

* Cite a reference (textbook and page, or an open source such as
  [Open Music Theory](https://viva.pressbooks.pub/openmusictheory/)) in
  the pull request.
* Write musical examples semantically (pitches, chords, Roman numerals)
  so that they are generated and checked by the theory core instead of
  being typed by hand.
* Content is licensed CC BY-SA 4.0. Material adapted from other CC BY-SA
  sources must be attributed.

Found a wrong answer or explanation? Please open a "Music content error"
issue.

## Translations

User-visible strings are translated with gettext. Translation will move
to a translation platform before the first release; until then, open a
pull request that adds `po/<language>.po` and the language to
`po/LINGUAS`.

## Design

UI work follows the GNOME Human Interface Guidelines and the project's
design mockups: libadwaita widgets, keyboard accelerators on every answer
control, and states signalled by colour, icon *and* text.

## Code of Conduct

Everyone taking part follows the [GNOME Code of Conduct](CODE_OF_CONDUCT.md).
