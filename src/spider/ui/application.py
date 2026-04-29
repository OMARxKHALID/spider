import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio
import logging

from spider.ui.window import SpiderWindow

logger = logging.getLogger(__name__)

class SpiderApplication(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.win = None

    def do_activate(self):
        logger.info("Application activated")
        if not self.win:
            logger.info("Creating new SpiderWindow")
            self.win = SpiderWindow(application=self)
        self.win.present()
