# Desktop file — installed directly since there is no po/ translation directory yet.
# When i18n is added, replace install_data with i18n.merge_file and add a po/ subdir.
install_data('org.domain.Spider.desktop.in',
  rename: 'org.domain.Spider.desktop',
  install_dir: join_paths(get_option('datadir'), 'applications')
)

install_data('org.domain.Spider.gschema.xml',
  install_dir: join_paths(get_option('datadir'), 'glib-2.0/schemas')
)
