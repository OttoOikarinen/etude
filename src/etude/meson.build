conf = configuration_data()
conf.set('PYTHON', python.find_installation('python3').full_path())
conf.set('VERSION', meson.project_version())
conf.set('localedir', get_option('prefix') / get_option('localedir'))
conf.set('pkgdatadir', pkgdatadir)

configure_file(
  input: 'etude.in',
  output: 'etude',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x'
)

gnome.compile_resources('etude',
  'etude.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
)

install_data(
  [
    '__init__.py',
    'main.py',
    'paths.py',
    'services.py',
    'window.py',
  ],
  install_dir: moduledir,
)

# Each subpackage owns its meson.build and lists its own sources.
# tests/test_packaging.py fails if a .py file is not listed anywhere.
foreach package : [
  'audio',
  'content',
  'core',
  'exercises',
  'learning',
  'notation',
  'storage',
  'ui',
]
  subdir(package)
endforeach
