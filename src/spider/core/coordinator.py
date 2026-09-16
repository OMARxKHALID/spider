import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib
import sqlite3
import threading
import logging
import weakref
import os
from spider.core.exceptions import CaptureError, EngineError, ImageDecodeError, ImageTooLargeError, describe_error, log_error

logger = logging.getLogger(__name__)

PIPELINE_TIMEOUT_SECONDS = 60
FAILURE_BANNER_THRESHOLD = 3
MAX_IMAGE_FILE_BYTES = 200 * 1024 * 1024
INPUT_ERRORS = (ImageDecodeError, ImageTooLargeError, OSError)


class PipelineCoordinator:
    def __init__(self, app_window):
        self.window = weakref.ref(app_window)
        from spider.capture.portal import PortalCapture
        from spider.storage.db import DatabaseManager
        self.portal = PortalCapture()
        self.db = DatabaseManager()
        self.ocr_engine = None
        self._engine_error = ""
        self._engine_lock = threading.RLock()
        self._busy = False
        self._run_generation = 0
        self._timeout_id = 0
        self._worker_thread = None
        self._failure_count = 0

        self.settings = Gio.Settings.new("org.domain.Spider")
        self._settings_handler = self.settings.connect("changed", self._on_settings_changed)

        GLib.timeout_add_seconds(1, self.warm_up)

    @property
    def is_busy(self) -> bool:
        return self._busy

    def warm_up(self):
        if self.ocr_engine is None:
            logger.info("Core: Warming up OCR engine in background")
            threading.Thread(target=self._init_engine, daemon=True).start()
        return GLib.SOURCE_REMOVE

    def _init_engine(self):
        with self._engine_lock:
            if self.ocr_engine is not None:
                return

            from spider.ocr.registry import EngineRegistry
            engine_id = self.settings.get_string("ocr-engine")

            try:
                descriptor = EngineRegistry.get(engine_id)

                available, reason = descriptor.check_available()
                if not available:
                    raise EngineError(f"{descriptor.display_name} is unavailable: {reason}")

                engine = descriptor.factory()
                lang = self.settings.get_string("language")
                if not engine.load_model(lang):
                    raise EngineError(f"Language data for “{lang}” is not installed")

                engine.configure({"psm": self.settings.get_int("tesseract-psm")})

                self.ocr_engine = engine
                self._engine_error = ""
                logger.info("Core: OCR engine ready: %s (lang=%s)", descriptor.id, lang)
            except Exception as e:
                self._engine_error = describe_error(e)
                log_error(logger, "Core: Failed to initialize engine", e)
            finally:
                GLib.idle_add(self._update_banner)

    def _on_settings_changed(self, settings, key):
        logger.info("Core: Setting '%s' changed, reloading OCR engine", key)
        with self._engine_lock:
            self.ocr_engine = None
            self._engine_error = ""
        self._failure_count = 0
        self._update_banner()
        self.warm_up()

    def _update_banner(self):
        win = self.window()
        if not win:
            return GLib.SOURCE_REMOVE
        if self.ocr_engine is None and self._engine_error:
            win.show_problem(self._engine_error)
        elif self._failure_count >= FAILURE_BANNER_THRESHOLD:
            win.show_problem("Text extraction failed several times in a row")
        else:
            win.show_problem(None)
        return GLib.SOURCE_REMOVE

    def _clear_timeout(self):
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = 0

    def _begin_run(self) -> bool:
        if self._busy:
            logger.warning("Core: Pipeline busy, ignoring request")
            return False
        self._busy = True
        self._run_generation += 1
        return True

    def _end_run(self):
        self._clear_timeout()
        self._busy = False

    def _is_stale(self, run_id) -> bool:
        return run_id != self._run_generation

    def start_capture_flow(self) -> bool:
        if not self._begin_run():
            return False
        logger.info("Core: Starting capture flow (gen %d)", self._run_generation)
        try:
            self.portal.capture_interactive(self._on_capture_complete)
        except Exception as e:
            log_error(logger, "Core: Could not start screenshot request", e)
            self._on_capture_complete(CaptureError("io_failure", describe_error(e)))
        return True

    def process_image(self, path: str) -> bool:
        if not self._begin_run():
            return False
        self._on_capture_complete(path)
        return True

    def _safety_unlock(self):
        self._timeout_id = 0
        if self._busy:
            logger.warning("Core: Pipeline timeout reached")
            self._run_generation += 1
            self._busy = False
            win = self.window()
            if win:
                win.show_idle()
                win.add_toast("Text extraction timed out")
        return GLib.SOURCE_REMOVE

    def _on_capture_complete(self, input_data):
        win = self.window()

        if isinstance(input_data, CaptureError) or not input_data:
            self._end_run()
            if not win:
                return
            win.show_idle()
            if not isinstance(input_data, CaptureError) or input_data.reason == "cancelled":
                logger.info("Core: Capture cancelled")
                return
            logger.warning("Core: Capture failed: %s", input_data)
            win.add_toast(f"Screenshot failed: {input_data}", "_Retry", lambda: win.activate_action("win.capture", None))
            return

        logger.info("Core: Image acquisition handoff complete")
        run_id = self._run_generation
        self._timeout_id = GLib.timeout_add_seconds(PIPELINE_TIMEOUT_SECONDS, self._safety_unlock)
        self._worker_thread = threading.Thread(target=self._run_pipeline, args=(input_data, run_id), daemon=True)
        self._worker_thread.start()
        if win:
            win.show_processing()

    def _run_pipeline(self, input_data, run_id):
        logger.info("Core: Starting processing pipeline (gen %d)", run_id)
        try:
            if isinstance(input_data, str):
                logger.info("Core: Reading image file: %s", input_data)
                if os.path.getsize(input_data) > MAX_IMAGE_FILE_BYTES:
                    raise ImageTooLargeError()
                with open(input_data, "rb") as f:
                    image_bytes = f.read()
            else:
                image_bytes = input_data

            from spider.vision.preprocessor import Preprocessor
            processed_img = Preprocessor.process_image(image_bytes)
            if self._is_stale(run_id):
                return

            with self._engine_lock:
                if self.ocr_engine is None:
                    self._init_engine()
                engine = self.ocr_engine
            if engine is None:
                raise EngineError(self._engine_error or "No OCR engine available")

            result = engine.recognize(processed_img)
            if self._is_stale(run_id):
                return

            saved = True
            if result.text.strip():
                logger.info("Core: Saving results to database")
                try:
                    self.db.save_result(result)
                except sqlite3.Error:
                    logger.exception("Core: Could not save result to history")
                    saved = False

            GLib.idle_add(self._on_pipeline_finished, result, run_id, saved)
        except Exception as e:
            log_error(logger, "Core: Pipeline error", e)
            GLib.idle_add(self._on_pipeline_error, describe_error(e), isinstance(e, INPUT_ERRORS), run_id)

    def _on_pipeline_finished(self, result, run_id, saved=True):
        if self._is_stale(run_id):
            return GLib.SOURCE_REMOVE
        self._end_run()
        logger.info("Core: Pipeline execution complete")
        self._failure_count = 0
        self._update_banner()
        win = self.window()
        if win:
            win.show_idle()
            win.show_result(result)
            if not saved:
                win.add_toast("Text extracted, but it could not be saved to history")
        return GLib.SOURCE_REMOVE

    def _on_pipeline_error(self, message, input_error, run_id):
        if self._is_stale(run_id):
            return GLib.SOURCE_REMOVE
        self._end_run()
        if not input_error:
            self._failure_count += 1
            if self._failure_count >= FAILURE_BANNER_THRESHOLD:
                with self._engine_lock:
                    self.ocr_engine = None
        self._update_banner()
        win = self.window()
        if win:
            win.show_idle()
            win.add_toast(message)
        return GLib.SOURCE_REMOVE

    def shutdown(self):
        if self._settings_handler:
            self.settings.disconnect(self._settings_handler)
            self._settings_handler = 0
        self._clear_timeout()
        self._run_generation += 1
        if self._worker_thread and self._worker_thread.is_alive():
            logger.info("Core: Waiting for worker thread...")
            self._worker_thread.join(timeout=5.0)
        self.db.close()
