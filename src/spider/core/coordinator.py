import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib
import time
import threading
import logging

from spider.capture.portal import PortalCapture
from spider.core.models import OCRResult
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
        self._is_busy = False
        self._timeout_id = 0

    def start_capture_flow(self):
        if self._is_busy:
            logger.warning("Pipeline already running; ignoring new capture request")
            return
            
        logger.info("[Phase 1/5] Initiation: Starting capture flow")
        # Safety timeout: if the portal hangs, unlock after 60 seconds
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)
        self._timeout_id = GLib.timeout_add_seconds(60, self._safety_unlock)
        self.portal.capture_interactive(self._on_capture_complete)

    def _safety_unlock(self):
        self._timeout_id = 0
        if self._is_busy or self.window._home_status_page.get_title() == "Capturing...":
            logger.warning("Pipeline safety timeout reached. Unlocking...")
            self._is_busy = False
            self._reset_ui_state()
        return False

    def process_image(self, image_bytes: bytes):
        """Public entry point for processing an already-loaded image (e.g. file open)."""
        self._on_capture_complete(image_bytes)

    def _on_capture_complete(self, image_bytes):
        # Cancel safety timeout as we have received a response
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = 0

        if not image_bytes:
            logger.warning("Capture failed or cancelled")
            GLib.idle_add(self._reset_ui_state)
            return

        logger.info("[Phase 2/5] Acquisition: Image received (%d bytes)", len(image_bytes))
        self._is_busy = True

        # threading.Thread + GLib.idle_add is the PyGObject-recommended pattern
        # for dispatching CPU work off the main thread and safely returning results.
        thread = threading.Thread(target=self._run_pipeline, args=(image_bytes,), daemon=True)
        thread.start()

    def _run_pipeline(self, image_bytes):
        logger.info("[Phase 3/5] Pre-Processing: Starting vision pipeline")
        try:
            processed_img = Preprocessor.process_image(image_bytes)
            result = self.ocr_engine.recognize(processed_img)
            result.image_bytes = image_bytes
            self.db.save_result(result)
            GLib.idle_add(self._on_pipeline_finished, result)
        except Exception as e:
            logger.error("Pipeline Worker Error: %s", e)
            GLib.idle_add(self._on_pipeline_error, str(e))

    def _on_pipeline_finished(self, result):
        self._is_busy = False
        logger.info("[Phase 5/5] Delivery: Pipeline complete (Text length: %d)", len(result.text))
        if hasattr(self.window, "show_result"):
            self.window.show_result(result)
        return False

    def _on_pipeline_error(self, error_msg):
        self._is_busy = False
        logger.error("Pipeline failed: %s", error_msg)
        # Reset the UI title so it doesn't stay stuck on "Capturing..."
        self._reset_ui_state()
        if hasattr(self.window, "add_toast"):
            self.window.add_toast(f"Error: {error_msg}")
        return False

    def _reset_ui_state(self):
        if hasattr(self.window, "reset_home_title"):
            self.window.reset_home_title()
        return False

