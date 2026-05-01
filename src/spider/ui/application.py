import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio

import logging
import shutil

logger = logging.getLogger(__name__)

def get_spider_window():
    from spider.ui.window import SpiderWindow
    return SpiderWindow

class SpiderApplication(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.win = None

    def do_activate(self):
        logger.info("App: Application activated")
        
        if not self.win:
            logger.info("App: Creating main window")
            SpiderWindow = get_spider_window()
            self.win = SpiderWindow(application=self)
        self.win.present()

        try:
            import pytesseract
            import PIL
            import cv2
        except ImportError as e:
            logger.error("App: Missing dependency: %s", e.name)
            self.show_error_and_quit(
                "Missing Dependencies",
                f"Required Python module '{e.name}' is not installed.\n\nPlease install it to continue."
            )
            return

        if not shutil.which('tesseract'):
            logger.error("App: Tesseract binary not found in PATH")
            self.show_error_and_quit(
                "Missing Dependency",
                "Tesseract OCR is not installed.\n\nPlease install it (e.g., sudo apt install tesseract-ocr)."
            )
            return

    def show_error_and_quit(self, title, message):
        dialog = Adw.AlertDialog.new(title, message)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.connect("response", lambda *_: self.quit())
        dialog.present()

    def do_shutdown(self):
        logger.info("App: Shutting down")
        if self.win and hasattr(self.win, 'coordinator'):
            self.win.coordinator.shutdown()
        Gio.Application.do_shutdown(self)
