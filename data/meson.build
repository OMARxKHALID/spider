desktop_conf = configuration_data()
desktop_file = configure_file(
  input: 'org.domain.Spider.desktop.in',
  output: 'org.domain.Spider.desktop',
  configuration: desktop_conf,
  install: true,
  install_dir: join_paths(get_option('datadir'), 'applications')
)

install_data('org.domain.Spider.gschema.xml',
  install_dir: join_paths(get_option('datadir'), 'glib-2.0/schemas')
)

install_data('org.domain.Spider.png',
  install_dir: join_paths(get_option('datadir'), 'icons/hicolor/512x512/apps')
)

install_data('org.domain.Spider.metainfo.xml',
  install_dir: join_paths(get_option('datadir'), 'metainfo')
)
