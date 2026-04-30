import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio
import logging
import shutil

from spider.ui.window import SpiderWindow

logger = logging.getLogger(__name__)

class SpiderApplication(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.win = None

    def do_activate(self):
        if not shutil.which('tesseract'):
            logger.error("Tesseract binary not found in PATH")
            dialog = Adw.AlertDialog.new(
                "Missing Dependency",
                "Tesseract OCR is not installed.\n\nPlease install it to use Spider OCR:\nsudo apt install tesseract-ocr"
            )
            dialog.add_response("close", "Close")
            dialog.set_default_response("close")
            dialog.connect("response", lambda *_: self.quit())
            dialog.present()
            return

        logger.info("Application activated")
        if not self.win:
            logger.info("Creating new SpiderWindow")
            self.win = SpiderWindow(application=self)
        self.win.present()

    def do_shutdown(self):
        logger.info("Application shutting down...")
        if self.win and hasattr(self.win, 'coordinator'):
            self.win.coordinator.shutdown()
        Gio.Application.do_shutdown(self)

