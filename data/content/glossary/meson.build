content_dir_files = [
  'chords.xml',
  'dictation.xml',
  'harmony-l2.xml',
  'intervals.xml',
  'modes-transposition.xml',
  'nonchord.xml',
  'notation.xml',
  'performance.xml',
  'pitch.xml',
  'rhythm-form-l2.xml',
  'rhythm-meter.xml',
  'scales-keys.xml',
  'voice-leading.xml',
]
content_schema = 'glossary'
content_relative_dir = 'glossary'
foreach file : content_dir_files
  if content_translated
    i18n.itstool_join(
      input: file,
      output: file,
      mo_targets: etude_gettext[0],
      its_files: content_its,
      install: true,
      install_dir: content_install_dir / content_relative_dir,
    )
  else
    install_data(file, install_dir: content_install_dir / content_relative_dir)
  endif
  test('Validate content/' + content_relative_dir / file, xmllint,
    args: ['--noout', '--relaxng', content_schemas[content_schema], files(file)],
    suite: 'content',
  )
endforeach
