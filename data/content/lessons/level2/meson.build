content_dir_files = [
  'cadences.xml',
  'dictation.xml',
  'figured-bass.xml',
  'modes.xml',
  'nonchord.xml',
  'phrase.xml',
  'rhythm.xml',
  'roman.xml',
  'sevenths.xml',
  'transposition.xml',
  'voice-leading.xml',
]
content_schema = 'lesson'
content_relative_dir = 'lessons' / 'level2'
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
