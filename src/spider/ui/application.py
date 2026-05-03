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
        self._setup_actions()
        self.set_accels_for_action("app.preferences", ["<Control>comma"])
        self.set_accels_for_action("app.about", ["F1"])
        self.set_accels_for_action("win.shortcuts", ["<Control>question"])

    def _setup_actions(self):
        action = Gio.SimpleAction.new("preferences", None)
        action.connect("activate", self._on_preferences_clicked)
        self.add_action(action)

        action = Gio.SimpleAction.new("about", None)
        action.connect("activate", self._on_about_clicked)
        self.add_action(action)

        action = Gio.SimpleAction.new("quit", None)
        action.connect("activate", lambda *_: self.quit())
        self.add_action(action)
        self.set_accels_for_action("app.quit", ["<Control>q"])

    def _on_preferences_clicked(self, *args):
        if self.win:
            self.win._on_preferences_clicked(None)

    def _on_about_clicked(self, *args):
        if self.win:
            self.win._on_about_clicked(None)

    def do_activate(self):
        logger.info("App: Application activated")

        try:
            import pytesseract
            import PIL
            import cv2
        except ImportError as e:
            logger.error("App: Missing dependency: %s", e.name)
            self._show_preflight_error(
                "Missing Dependencies",
                f"Required Python module '{e.name}' is not installed.\n\nPlease install it to continue."
            )
            return

        if not shutil.which('tesseract'):
            logger.error("App: Tesseract binary not found in PATH")
            self._show_preflight_error(
                "Missing Dependency",
                "Tesseract OCR is not installed.\n\nPlease install it (e.g., sudo apt install tesseract-ocr)."
            )
            return

        if not self.win:
            logger.info("App: Creating main window")
            SpiderWindow = get_spider_window()
            self.win = SpiderWindow(application=self)
        self.win.present()

    def _show_preflight_error(self, title, message):
        temp_win = Adw.ApplicationWindow(application=self)
        temp_win.set_default_size(400, 200)
        temp_win.present()

        dialog = Adw.AlertDialog.new(title, message)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.connect("response", lambda *_: self.quit())
        dialog.present(temp_win)

    def do_shutdown(self):
        logger.info("App: Shutting down")
        if self.win and hasattr(self.win, 'coordinator'):
            self.win.coordinator.shutdown()
        Gio.Application.do_shutdown(self)
