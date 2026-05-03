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
        
        self.settings = Gio.Settings.new("org.domain.Spider")
        self._engine_change_handler = self.settings.connect(
            "changed::ocr-engine", self._on_engine_setting_changed
        )
        
        GLib.timeout_add_seconds(1, self.warm_up)

    @property
    def is_busy(self):
        return self._pipeline_event.is_set()

    def warm_up(self):
        if self.ocr_engine is None:
            logger.info("Core: Warming up OCR engine in background")
            self._warmup_thread = threading.Thread(target=self._init_engine, daemon=True)
            self._warmup_thread.start()
        return False

    def _init_engine(self):
        with self._engine_lock:
            if self.ocr_engine is not None:
                return

            from spider.ocr.registry import EngineRegistry
            engine_id = self.settings.get_string("ocr-engine")
            
            try:
                descriptor = EngineRegistry.get(engine_id)
            except KeyError:
                logger.warning("Engine '%s' not found, falling back to tesseract", engine_id)
                descriptor = EngineRegistry.get("tesseract")

            available, reason = descriptor.check_available()
            if not available:
                logger.warning("Engine '%s' unavailable: %s", engine_id, reason)
                descriptor = EngineRegistry.get("tesseract")
                ok, why = descriptor.check_available()
                if not ok:
                    raise RuntimeError(f"No OCR engine available. Tried '{engine_id}': {reason}. Tried 'tesseract': {why}.")

            try:
                engine = descriptor.factory()
                lang = self.settings.get_string("language")
                if not engine.load_model(lang):
                    raise RuntimeError(f"Engine '{descriptor.id}' failed to load language '{lang}'")

                if descriptor.id == "tesseract":
                    psm = self.settings.get_int("tesseract-psm")
                    engine.configure({"psm": psm})

                ok, message = engine.health_check()
                if not ok:
                    raise RuntimeError(f"Engine '{descriptor.id}' health check failed: {message}")

                self.ocr_engine = engine
                logger.info("Core: OCR engine ready: %s (lang=%s)", descriptor.id, lang)
            except Exception as e:
                logger.error("Core: Failed to initialize engine: %s", e)

    def _on_engine_setting_changed(self, settings, key):
        if self.is_busy:
            return
        with self._engine_lock:
            self.ocr_engine = None
        self._warmup_thread = threading.Thread(target=self._init_engine, daemon=True)
        self._warmup_thread.start()

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

    def process_image(self, data: bytes | str):
        if self.is_busy:
            return
        self._pipeline_event.set()
        self._cancel_event.clear()
        self._run_generation += 1
        self._start_timeout()
        self._on_capture_complete(data)

    def _on_capture_complete(self, input_data):
        if not input_data:
            if self._timeout_id:
                GLib.source_remove(self._timeout_id)
                self._timeout_id = 0
            logger.warning("Core: Capture cancelled or failed")
            self._pipeline_event.clear()
            GLib.idle_add(self._reset_ui_state)
            return

        logger.info("Core: Image acquisition handoff complete")
        run_id = self._run_generation
        self._worker_thread = threading.Thread(target=self._run_pipeline, args=(input_data, run_id), daemon=True)
        self._worker_thread.start()
        GLib.idle_add(self._update_processing_ui)

    def _run_pipeline(self, input_data, run_id):
        logger.info("Core: Starting processing pipeline (gen %d)", run_id)
        
        try:
            image_bytes = None
            if isinstance(input_data, str):
                try:
                    logger.info("Core: Reading image file: %s", input_data)
                    with open(input_data, "rb") as f:
                        image_bytes = f.read()
                except Exception as e:
                    logger.error("Core: Failed to read input file: %s", e)
                    GLib.idle_add(self._on_pipeline_error, f"Read error: {str(e)}", run_id)
                    return
            else:
                image_bytes = input_data

            from spider.vision.preprocessor import Preprocessor
            
            if self._cancel_event.is_set():
                raise TimeoutError("Pipeline aborted: timeout")

            processed_img = Preprocessor.process_image(image_bytes)

            if self._cancel_event.is_set():
                raise TimeoutError("Pipeline aborted: timeout")

            with self._engine_lock:
                if self.ocr_engine is None:
                    self._init_engine()
                engine = self.ocr_engine

            if engine is None:
                raise RuntimeError("No OCR engine available")

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
        if self.window is None:
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
        if self.window is None:
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

    def _update_processing_ui(self):
        if self.window and hasattr(self.window, "set_processing_state"):
            self.window.set_processing_state()
        return GLib.SOURCE_REMOVE

    def _reset_ui_state(self):
        if self.window is None:
            return GLib.SOURCE_REMOVE
        if hasattr(self.window, "reset_home_title"):
            self.window.reset_home_title()
        return GLib.SOURCE_REMOVE

    def shutdown(self):
        if self._engine_change_handler:
            self.settings.disconnect(self._engine_change_handler)
        self._cancel_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            logger.info("Core: Waiting for worker thread...")
            self._worker_thread.join(timeout=5.0)
        self.db.close()
