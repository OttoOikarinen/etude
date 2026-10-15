## What and why

<!-- What does this change, and which issue or roadmap item does it address? -->

## How it was tested

<!-- Tests added or run, and manual checks (light, dark and narrow layouts for UI changes). -->

## Checklist

- [ ] `pytest`, `ruff check`, `ruff format --check`, `mypy`, `lint-imports`, `codespell` and `reuse lint` pass
- [ ] New Python files are listed in their directory's `meson.build`; new `.ui` files in `etude.gresource.xml`
- [ ] New user-visible strings are translatable and their files are in `po/POTFILES.in`
- [ ] Musical content was checked for correctness (theory, spelling, terminology)
- [ ] Docs updated (`ARCHITECTURE.md`, `docs/`) if behaviour or contracts changed
