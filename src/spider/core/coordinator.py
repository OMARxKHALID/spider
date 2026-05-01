import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib
import threading
import logging
import time

logger = logging.getLogger(__name__)

class PipelineCoordinator:
    def __init__(self, app_window):
        self.window = app_window
        from spider.capture.portal import PortalCapture
        from spider.storage.db import DatabaseManager
        self.portal = PortalCapture()
        self.ocr_engine = None
        self.db = DatabaseManager()
        self._pipeline_event = threading.Event()
        self._cancel_event = threading.Event()
        self._timeout_id = 0
        self._worker_thread = None
        self._engine_lock = threading.RLock()
        self._run_generation = 0
        
        GLib.timeout_add_seconds(1, self.warm_up)

    @property
    def is_busy(self):
        return self._pipeline_event.is_set()

    def warm_up(self):
        """Pre-load OCR engine in background to hide init latency."""
        if self.ocr_engine is None:
            logger.info("Core: Warming up OCR engine in background")
            self._warmup_thread = threading.Thread(target=self._init_engine, daemon=True)
            self._warmup_thread.start()
        return False

    def _init_engine(self):
        with self._engine_lock:
            if self.ocr_engine is not None:
                return
            try:
                from spider.ocr.tesseract import TesseractEngine
                engine = TesseractEngine()
                engine.load_model("eng")
                self.ocr_engine = engine
                logger.info("Core: OCR engine warmed up and ready")
            except Exception as e:
                logger.warning("Core: Failed to warm up engine: %s", e)

    def _start_timeout(self):
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)
        self._timeout_id = GLib.timeout_add_seconds(60, self._safety_unlock)

    def start_capture_flow(self):
        if self.is_busy:
            logger.warning("Core: Pipeline busy, ignoring request")
            return

        self._pipeline_event.set()
        self._cancel_event.clear()
        self._run_generation += 1
        logger.info("Core: Starting capture flow (gen %d)", self._run_generation)
        self._start_timeout()
        self.portal.capture_interactive(self._on_capture_complete)

    def _safety_unlock(self):
        self._timeout_id = 0
        if self._pipeline_event.is_set():
            logger.warning("Core: Pipeline timeout reached")
            self._cancel_event.set()
            self._pipeline_event.clear()
            if hasattr(self.window, "add_toast"):
                self.window.add_toast("OCR is taking longer than expected...")
        return False

    def process_image(self, image_bytes: bytes):
        if self.is_busy:
            return
        self._pipeline_event.set()
        self._cancel_event.clear()
        self._run_generation += 1
        self._start_timeout()
        self._on_capture_complete(image_bytes)

    def _on_capture_complete(self, image_bytes):
        if not image_bytes:
            if self._timeout_id:
                GLib.source_remove(self._timeout_id)
                self._timeout_id = 0
            logger.warning("Core: Capture cancelled or failed")
            self._pipeline_event.clear()
            GLib.idle_add(self._reset_ui_state)
            return

        logger.info("Core: Image acquisition complete (%d bytes)", len(image_bytes))
        run_id = self._run_generation
        self._worker_thread = threading.Thread(target=self._run_pipeline, args=(image_bytes, run_id), daemon=False)
        self._worker_thread.start()

    def _run_pipeline(self, image_bytes, run_id):
        logger.info("Core: Starting processing pipeline (gen %d)", run_id)
        from spider.vision.preprocessor import Preprocessor
        
        try:
            if self._cancel_event.is_set():
                raise TimeoutError("Pipeline aborted: timeout")

            processed_img = Preprocessor.process_image(image_bytes)

            if self._cancel_event.is_set():
                raise TimeoutError("Pipeline aborted: timeout")

            with self._engine_lock:
                engine = self.ocr_engine
                if engine is None:
                    self._init_engine()
                    engine = self.ocr_engine

            result = engine.recognize(processed_img)
            result.image_bytes = image_bytes

            if self._cancel_event.is_set():
                raise TimeoutError("Pipeline aborted: timeout")

            if result.text and result.text.strip():
                logger.info("Core: Saving results to database")
                self.db.save_result(result)

            GLib.idle_add(self._on_pipeline_finished, result, run_id)
        except Exception as e:
            logger.error("Core: Pipeline error: %s", e)
            GLib.idle_add(self._on_pipeline_error, str(e), run_id)
        finally:
            self._pipeline_event.clear()

    def _on_pipeline_finished(self, result, run_id):
        if self.window is None or self.window.get_root() is None:
            return GLib.SOURCE_REMOVE
        if run_id != self._run_generation:
            return GLib.SOURCE_REMOVE
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = 0
        logger.info("Core: Pipeline execution complete")
        if hasattr(self.window, "show_result"):
            self.window.show_result(result)
        return GLib.SOURCE_REMOVE

    def _on_pipeline_error(self, error_msg, run_id):
        if self.window is None or self.window.get_root() is None:
            return GLib.SOURCE_REMOVE
        if run_id != self._run_generation:
            return GLib.SOURCE_REMOVE
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = 0
        self._reset_ui_state()
        if hasattr(self.window, "add_toast"):
            self.window.add_toast(f"Error: {error_msg}")
        return GLib.SOURCE_REMOVE

    def _reset_ui_state(self):
        if self.window is None or self.window.get_root() is None:
            return GLib.SOURCE_REMOVE
        if hasattr(self.window, "reset_home_title"):
            self.window.reset_home_title()
        return GLib.SOURCE_REMOVE

    def shutdown(self):
        self._cancel_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            logger.info("Core: Waiting for worker thread...")
            self._worker_thread.join(timeout=5.0)
        self.db.close()
