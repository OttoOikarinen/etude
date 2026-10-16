install_data(
  [
    '__init__.py',
    'common.py',
    'controller.py',
    'figure.py',
    'preview.py',
  ],
  install_dir: moduledir / 'ui',
)

foreach package : [
  'dialogs',
  'pages',
  'widgets',
]
  subdir(package)
endforeach
