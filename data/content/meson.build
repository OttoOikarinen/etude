# Curriculum, lessons and glossary, installed with their translations merged in:
# each translatable element is followed by its translations, marked with xml:lang.
# Every file is listed in the meson.build of its directory and in po/POTFILES.in
# (tests/test_packaging.py checks both), and is validated against its schema.

content_install_dir = get_option('datadir') / meson.project_name() / 'content'
content_its = [meson.current_source_dir() / 'its' / 'etude.its']
content_schemas = {
  'curriculum': files('schema/curriculum.rng'),
  'glossary': files('schema/glossary.rng'),
  'lesson': files('schema/lesson.rng'),
}
# itstool needs at least one translation (po/LINGUAS); until then files install as is.
content_translated = etude_gettext[0].length() > 0
xmllint = find_program('xmllint', required: false, disabler: true)

# Installs and validates the files of one directory; used by the subdirectories.
# (Meson has no functions, so each directory repeats this loop over its files.)
content_dir_files = ['curriculum.xml']
content_schema = 'curriculum'
content_relative_dir = ''
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

subdir('glossary')
subdir('lessons')
