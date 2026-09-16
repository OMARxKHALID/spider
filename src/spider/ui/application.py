import logging
import shutil
import sqlite3
import threading

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gio, GLib, Gtk

from spider import __version__
from spider.core.exceptions import describe_error

logger = logging.getLogger(__name__)

ACCELERATORS = {
    "app.quit": ["<Control>q"],
    "app.preferences": ["<Control>comma"],
    "win.capture": ["<Control><Shift>c"],
    "win.open": ["<Control>o"],
    "win.history": ["<Control>h"],
}


class SpiderApplication(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.win = None

        for name, callback in (
            ("preferences", self._on_preferences),
            ("about", self._on_about),
            ("quit", lambda *_: self.quit()),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

        for action_name, accels in ACCELERATORS.items():
            self.set_accels_for_action(action_name, accels)

    def do_activate(self):
        if not self.win:
            logger.info("App: Creating main window")
            try:
                from spider.ui.window import SpiderWindow
                self.win = SpiderWindow(application=self)
            except Exception as e:
                logger.exception("App: Could not create main window")
                for window in self.get_windows():
                    window.destroy()
                message = describe_error(e)
                if isinstance(e, sqlite3.Error):
                    from spider.storage.db import default_db_path
                    message += f"\n\nThe history file may be damaged: {default_db_path()}"
                self._show_fatal_error(message)
                return
            self.win.show_processing()
            threading.Thread(target=self._check_dependencies, daemon=True).start()
        self.win.present()

    def _check_dependencies(self):
        logger.info("App: Starting background dependency check")
        try:
            import cv2
            import numpy
            if not shutil.which("tesseract"):
                raise RuntimeError("Tesseract OCR is not installed. Install the tesseract-ocr package.")
            GLib.idle_add(self.win.show_idle)
        except ImportError as e:
            logger.exception("App: Missing Python dependency")
            GLib.idle_add(self._show_fatal_error, f"A required Python module is missing: {e.name}")
        except Exception as e:
            logger.exception("App: Initialization failed")
            GLib.idle_add(self._show_fatal_error, str(e))

    def _show_fatal_error(self, message):
        parent = self.win
        if parent is None:
            parent = Adw.ApplicationWindow(application=self, title="Spider", default_width=420, default_height=240)
            parent.present()
        dialog = Adw.AlertDialog(heading="Spider Cannot Start", body=message)
        dialog.add_response("close", "_Close")
        dialog.connect("response", lambda *_: self.quit())
        dialog.present(parent)
        return GLib.SOURCE_REMOVE

    def _on_preferences(self, *_):
        from spider.ui.preferences import SpiderPreferencesDialog
        SpiderPreferencesDialog().present(self.win)

    def _on_about(self, *_):
        Adw.AboutDialog(
            application_name="Spider",
            application_icon="org.domain.Spider",
            developer_name="Omar Khalid",
            version=__version__,
            website="https://github.com/OMARxKHALID/spider",
            issue_url="https://github.com/OMARxKHALID/spider/issues",
            copyright="© 2026 Omar Khalid",
            license_type=Gtk.License.GPL_3_0,
        ).present(self.win)

    def do_shutdown(self):
        logger.info("App: Shutting down")
        if self.win:
            try:
                self.win.coordinator.shutdown()
            except Exception:
                logger.exception("App: Error during shutdown")
        Adw.Application.do_shutdown(self)
