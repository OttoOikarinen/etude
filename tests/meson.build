# UI smoke test without pytest; exits with 77 (skipped) when there is no display.
test('UI smoke test',
  python.find_installation('python3'),
  args: [
    files('ui/smoke.py'),
    '--source-root', meson.project_source_root(),
  ],
  timeout: 120,
)
