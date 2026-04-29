import sys
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Gio, Adw
from spider.ui.application import SpiderApplication

import logging
logger = logging.getLogger(__name__)

def main():
    logging.basicConfig(
        level=logging.INFO, 
        format='[%(asctime)s] %(levelname)s [%(name)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    logger.info("--- Spider OCR Startup ---")
    logger.info("Python version: %s", sys.version.split()[0])
    logger.info("GTK version: %d.%d.%d", Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version())
    Adw.init()
    
    app = SpiderApplication(application_id="org.domain.Spider", flags=Gio.ApplicationFlags.FLAGS_NONE)
    return app.run(sys.argv)

if __name__ == '__main__':
    sys.exit(main())
