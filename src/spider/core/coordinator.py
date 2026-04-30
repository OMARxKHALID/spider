import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib
import threading
import logging

from spider.capture.portal import PortalCapture
from spider.vision.preprocessor import Preprocessor
from spider.ocr.tesseract import TesseractEngine
from spider.storage.db import DatabaseManager

logger = logging.getLogger(__name__)

class PipelineCoordinator:
    def __init__(self, app_window):
        self.window = app_window
        self.portal = PortalCapture()
        self.ocr_engine = TesseractEngine()
        self.ocr_engine.load_model("eng")
        self.db = DatabaseManager()
        self._pipeline_event = threading.Event()
        self._cancel_event = threading.Event()
        self._timeout_id = 0
        self._worker_thread = None

    @property
    def is_busy(self):
        return self._pipeline_event.is_set()

    def _start_timeout(self):
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)
        self._timeout_id = GLib.timeout_add_seconds(60, self._safety_unlock)

    def start_capture_flow(self):
        if self.is_busy:
            logger.warning("Pipeline already busy; ignoring request")
            return

        self._pipeline_event.set()
        self._cancel_event.clear()
        logger.info("Initiation: Starting capture flow")
        self._start_timeout()
        self.portal.capture_interactive(self._on_capture_complete)

    def _safety_unlock(self):
        self._timeout_id = 0
        if self._pipeline_event.is_set():
            logger.warning("Pipeline timeout: task still running, UI notified")
            self._cancel_event.set()
            if hasattr(self.window, "add_toast"):
                self.window.add_toast("OCR is taking longer than expected...")
        return False

    def process_image(self, image_bytes: bytes):
        if self.is_busy:
            return
        self._pipeline_event.set()
        self._cancel_event.clear()
        self._start_timeout()
        self._on_capture_complete(image_bytes)

    def _on_capture_complete(self, image_bytes):
        if not image_bytes:
            if self._timeout_id:
                GLib.source_remove(self._timeout_id)
                self._timeout_id = 0
            logger.warning("Capture failed or cancelled")
            self._pipeline_event.clear()
            GLib.idle_add(self._reset_ui_state)
            return

        logger.info("Acquisition: Image received (%d bytes)", len(image_bytes))
        self._worker_thread = threading.Thread(target=self._run_pipeline, args=(image_bytes,), daemon=False)
        self._worker_thread.start()

    def _run_pipeline(self, image_bytes):
        logger.info("Pre-Processing: Starting vision pipeline")
        try:
            if self._cancel_event.is_set():
                raise TimeoutError("Pipeline aborted: safety timeout reached")

            processed_img = Preprocessor.process_image(image_bytes)

            if self._cancel_event.is_set():
                raise TimeoutError("Pipeline aborted: safety timeout reached")

            result = self.ocr_engine.recognize(processed_img)
            result.image_bytes = image_bytes

            if self._cancel_event.is_set():
                raise TimeoutError("Pipeline aborted: safety timeout reached")

            if result.text and result.text.strip():
                self.db.save_result(result)

            GLib.idle_add(self._on_pipeline_finished, result)
        except Exception as e:
            logger.error("Pipeline Worker Error: %s", e)
            GLib.idle_add(self._on_pipeline_error, str(e))

    def _on_pipeline_finished(self, result):
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = 0
        self._pipeline_event.clear()
        logger.info("Delivery: Pipeline complete")
        if hasattr(self.window, "show_result"):
            self.window.show_result(result)
        return False

    def _on_pipeline_error(self, error_msg):
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = 0
        self._pipeline_event.clear()
        logger.error("Pipeline failed: %s", error_msg)
        self._reset_ui_state()
        if hasattr(self.window, "add_toast"):
            self.window.add_toast(f"Error: {error_msg}")
        return False

    def _reset_ui_state(self):
        if hasattr(self.window, "reset_home_title"):
            self.window.reset_home_title()
        return False

    def shutdown(self):
        if self._worker_thread and self._worker_thread.is_alive():
            logger.info("Waiting for worker thread to finish...")
            self._worker_thread.join(timeout=5.0)
        self.db.close()
