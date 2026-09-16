import threading
import weakref
from unittest.mock import Mock, patch

import cv2
import numpy as np
import pytest

from spider.capture.portal import PortalCapture
from spider.core.coordinator import PipelineCoordinator, FAILURE_BANNER_THRESHOLD
from spider.core.exceptions import CaptureError


class FakeWindow:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *args: self.calls.append((name, args))

    def names(self):
        return [name for name, _ in self.calls]


@pytest.fixture
def window():
    return FakeWindow()


@pytest.fixture
def coordinator(window, memory_db, mock_engine):
    c = PipelineCoordinator.__new__(PipelineCoordinator)
    c.window = weakref.ref(window)
    c.db = memory_db
    c.ocr_engine = mock_engine
    c._engine_error = ""
    c._engine_lock = threading.RLock()
    c._busy = False
    c._run_generation = 0
    c._timeout_id = 0
    c._worker_thread = None
    c._failure_count = 0
    return c


@pytest.fixture
def png_bytes(white_image):
    return cv2.imencode('.png', white_image)[1].tobytes()


class TestCoordinator:

    def test_busy_blocks_second_run(self, coordinator):
        assert coordinator._begin_run()
        assert not coordinator._begin_run()

    def test_current_run_saves_and_reports(self, coordinator, png_bytes, memory_db):
        coordinator._begin_run()
        with patch("spider.core.coordinator.GLib.idle_add") as idle_add:
            coordinator._run_pipeline(png_bytes, coordinator._run_generation)
        assert idle_add.call_args[0][0] == coordinator._on_pipeline_finished
        assert len(memory_db.get_history()) == 1

    def test_stale_run_is_discarded(self, coordinator, png_bytes, memory_db):
        coordinator._begin_run()
        run_id = coordinator._run_generation
        with patch("spider.core.coordinator.GLib.source_remove"):
            coordinator._timeout_id = 0
            coordinator._safety_unlock()
        assert not coordinator.is_busy

        coordinator._begin_run()
        with patch("spider.core.coordinator.GLib.idle_add") as idle_add:
            coordinator._run_pipeline(png_bytes, run_id)
        idle_add.assert_not_called()
        assert memory_db.get_history() == []
        assert coordinator.is_busy, "Stale worker must not release the new run"

        coordinator._on_pipeline_error("late failure", False, run_id)
        assert coordinator.is_busy
        assert coordinator._failure_count == 0

    def test_safety_unlock_restores_window(self, coordinator, window):
        coordinator._begin_run()
        coordinator._safety_unlock()
        assert window.names() == ["show_idle", "add_toast"]

    def banner(self, window):
        return [args[0] for name, args in window.calls if name == "show_problem"][-1]

    def test_failure_banner_after_consecutive_errors(self, coordinator, window, mock_ocr_result):
        for _ in range(FAILURE_BANNER_THRESHOLD):
            coordinator._begin_run()
            coordinator._on_pipeline_error("boom", False, coordinator._run_generation)
        assert self.banner(window) == "Text extraction failed several times in a row"
        assert coordinator.ocr_engine is None

        coordinator._begin_run()
        coordinator._on_pipeline_finished(mock_ocr_result, coordinator._run_generation)
        assert coordinator._failure_count == 0
        assert self.banner(window) is None

    def test_bad_input_files_do_not_trip_engine_banner(self, coordinator, window):
        for _ in range(FAILURE_BANNER_THRESHOLD + 1):
            coordinator._begin_run()
            coordinator._on_pipeline_error("not an image", True, coordinator._run_generation)
        assert coordinator._failure_count == 0
        assert coordinator.ocr_engine is not None
        assert self.banner(window) is None

    def test_engine_error_shown_in_banner(self, coordinator, window):
        coordinator.ocr_engine = None
        coordinator._engine_error = "Language data for “zzz” is not installed"
        coordinator._update_banner()
        assert self.banner(window) == coordinator._engine_error

    def test_unreadable_file_reports_friendly_error(self, coordinator, tmp_path):
        coordinator._begin_run()
        with patch("spider.core.coordinator.GLib.idle_add") as idle_add:
            coordinator._run_pipeline(str(tmp_path / "missing.png"), coordinator._run_generation)
        callback, message, input_error, _ = idle_add.call_args[0]
        assert callback == coordinator._on_pipeline_error
        assert message == "The image file no longer exists"
        assert input_error

    def test_save_failure_keeps_ocr_result(self, coordinator, png_bytes):
        import sqlite3
        coordinator.db = Mock()
        coordinator.db.save_result.side_effect = sqlite3.OperationalError("disk I/O error")
        coordinator._begin_run()
        with patch("spider.core.coordinator.GLib.idle_add") as idle_add:
            coordinator._run_pipeline(png_bytes, coordinator._run_generation)
        callback, result, _, saved = idle_add.call_args[0]
        assert callback == coordinator._on_pipeline_finished
        assert result.text == "Hello World" and saved is False

    def test_capture_start_exception_releases_ui(self, coordinator, window):
        coordinator.portal = Mock()
        coordinator.portal.capture_interactive.side_effect = RuntimeError("bus closed")
        assert coordinator.start_capture_flow()
        assert not coordinator.is_busy
        assert window.names() == ["show_idle", "add_toast"]
        assert window.calls[-1][1][0].startswith("Screenshot failed:")

    def test_cancelled_capture_releases_busy_silently(self, coordinator, window):
        coordinator._begin_run()
        coordinator._on_capture_complete(CaptureError("cancelled", "User cancelled"))
        assert not coordinator.is_busy
        assert window.names() == ["show_idle"]


class TestPortal:

    @pytest.fixture
    def portal(self):
        p = PortalCapture.__new__(PortalCapture)
        p.connection = Mock()
        p.connection.get_unique_name.return_value = ":1.42"
        return p

    def test_request_path_matches_spec(self, portal):
        assert portal.request_path("spider_abc") == \
            "/org/freedesktop/portal/desktop/request/1_42/spider_abc"

    def test_missing_portal_message(self, portal):
        from gi.repository import Gio, GLib
        error = GLib.Error.new_literal(Gio.dbus_error_quark(), "GDBus.Error:org.freedesktop.DBus.Error.ServiceUnknown: gone", Gio.DBusError.SERVICE_UNKNOWN)
        Gio.DBusError.register_error(Gio.dbus_error_quark(), Gio.DBusError.SERVICE_UNKNOWN, "org.freedesktop.DBus.Error.ServiceUnknown")
        assert "not available" in PortalCapture._describe_call_error(error)

    def test_response_codes(self, portal):
        assert portal._read_response(1, None).reason == "cancelled"
        assert portal._read_response(2, None).reason == "io_failure"

    def test_only_fresh_screenshots_are_deleted(self, tmp_path):
        import os, time
        fresh, old = tmp_path / "fresh.png", tmp_path / "old.png"
        fresh.write_bytes(b"x")
        old.write_bytes(b"x")
        long_ago = time.time() - 3600
        os.utime(old, (long_ago, long_ago))
        PortalCapture._remove_fresh_screenshot(str(fresh))
        PortalCapture._remove_fresh_screenshot(str(old))
        PortalCapture._remove_fresh_screenshot(str(tmp_path / "missing.png"))
        assert not fresh.exists() and old.exists()

    def test_finish_fires_callback_once(self, portal):
        received = []
        ctx = {"completed": False, "sub_id": 7, "timeout_id": 0, "callback": received.append}
        portal._finish(ctx, b"first")
        portal._finish(ctx, b"second")
        assert received == [b"first"]
        portal.connection.signal_unsubscribe.assert_called_once_with(7)
