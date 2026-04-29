project('spider',
          version: '0.1.0',
    meson_version: '>= 0.62.0',
  default_options: [ 'warning_level=2' ],
)

gnome = import('gnome')
python = import('python')

py_installation = python.find_installation('python3')

conf = configuration_data()
conf.set('PACKAGE_NAME', meson.project_name())
conf.set('PACKAGE_VERSION', meson.project_version())
conf.set('PREFIX', get_option('prefix'))
conf.set('BINDIR', join_paths(get_option('prefix'), get_option('bindir')))
conf.set('DATADIR', join_paths(get_option('prefix'), get_option('datadir')))
conf.set('PYTHON', py_installation.full_path())

configure_file(
  input: 'spider.in',
  output: 'org.domain.Spider',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir')
)

subdir('data')
subdir('src')

gnome.post_install(
  glib_compile_schemas: true,
  gtk_update_icon_cache: true,
  update_desktop_database: true,
)
