import uuid
import os
import time
from gi.repository import Gio, GLib
import logging
from spider.core.exceptions import CaptureError

logger = logging.getLogger(__name__)

PORTAL_TIMEOUT_SECONDS = 90
FRESH_SCREENSHOT_SECONDS = PORTAL_TIMEOUT_SECONDS + 30
RESPONSE_SUCCESS = 0
RESPONSE_CANCELLED = 1
MISSING_PORTAL_ERRORS = {
    "org.freedesktop.DBus.Error.ServiceUnknown",
    "org.freedesktop.DBus.Error.UnknownMethod",
    "org.freedesktop.DBus.Error.UnknownInterface",
    "org.freedesktop.DBus.Error.UnknownObject",
}


class PortalCapture:
    def __init__(self):
        try:
            self.connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception as e:
            logger.error("Capture: Failed to connect to Session Bus: %s", e)
            self.connection = None

    def request_path(self, token: str) -> str:
        sender = self.connection.get_unique_name().lstrip(":").replace(".", "_")
        return f"/org/freedesktop/portal/desktop/request/{sender}/{token}"

    def capture_interactive(self, callback):
        if not self.connection:
            logger.error("Capture: No DBus connection available")
            callback(CaptureError("io_failure", "No desktop session bus is available"))
            return

        token = "spider_" + uuid.uuid4().hex
        ctx = {
            "sub_id": 0,
            "callback": callback,
            "handle": self.request_path(token),
            "completed": False,
            "timeout_id": 0
        }
        self._subscribe(ctx)

        logger.info("Capture: Initiating screenshot portal request")
        self.connection.call(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Screenshot",
            "Screenshot",
            GLib.Variant("(sa{sv})", (
                "",
                {
                    "handle_token": GLib.Variant("s", token),
                    "interactive": GLib.Variant("b", True)
                }
            )),
            GLib.VariantType("(o)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            self._on_call_done,
            ctx
        )

    def _subscribe(self, ctx):
        ctx["sub_id"] = self.connection.signal_subscribe(
            "org.freedesktop.portal.Desktop",
            "org.freedesktop.portal.Request",
            "Response",
            ctx["handle"],
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_response,
            ctx
        )

    def _unsubscribe(self, ctx):
        if ctx["sub_id"]:
            self.connection.signal_unsubscribe(ctx["sub_id"])
            ctx["sub_id"] = 0
        if ctx["timeout_id"]:
            GLib.source_remove(ctx["timeout_id"])
            ctx["timeout_id"] = 0

    def _finish(self, ctx, value):
        if ctx["completed"]:
            return
        ctx["completed"] = True
        self._unsubscribe(ctx)
        ctx["callback"](value)

    def _on_call_done(self, conn, result, ctx):
        try:
            handle = conn.call_finish(result).get_child_value(0).get_string()
        except GLib.Error as e:
            logger.error("Capture: Portal call failed: %s", e.message)
            self._finish(ctx, CaptureError("io_failure", self._describe_call_error(e)))
            return

        if ctx["completed"]:
            return

        if handle != ctx["handle"]:
            logger.info("Capture: Portal returned unexpected handle, resubscribing")
            self.connection.signal_unsubscribe(ctx["sub_id"])
            ctx["handle"] = handle
            self._subscribe(ctx)

        ctx["timeout_id"] = GLib.timeout_add_seconds(
            PORTAL_TIMEOUT_SECONDS, self._on_portal_timeout, ctx
        )
        logger.info("Capture: Portal request accepted, handle: %s", handle)

    @staticmethod
    def _describe_call_error(error):
        if Gio.DBusError.is_remote_error(error) and Gio.DBusError.get_remote_error(error) in MISSING_PORTAL_ERRORS:
            return "The screenshot portal is not available. Install xdg-desktop-portal for your desktop."
        return "The screenshot request was rejected"

    def _on_portal_timeout(self, ctx):
        ctx["timeout_id"] = 0
        logger.warning("Capture: Portal request timed out after %ds", PORTAL_TIMEOUT_SECONDS)
        self._finish(ctx, CaptureError("timeout", "Screenshot request timed out"))
        return GLib.SOURCE_REMOVE

    def _on_response(self, connection, sender_name, object_path, interface_name, signal_name, parameters, ctx):
        if object_path != ctx["handle"] or ctx["completed"]:
            return

        response_code = parameters.get_child_value(0).get_uint32()
        results = parameters.get_child_value(1)
        self._finish(ctx, self._read_response(response_code, results))

    def _read_response(self, response_code, results):
        if response_code == RESPONSE_CANCELLED:
            logger.info("Capture: User cancelled portal request")
            return CaptureError("cancelled", "User cancelled portal request")
        if response_code != RESPONSE_SUCCESS:
            logger.warning("Capture: Portal interaction ended with code %d", response_code)
            return CaptureError("io_failure", "Screenshot was not taken")

        uri_var = results.lookup_value("uri", GLib.VariantType("s"))
        if not uri_var:
            return CaptureError("io_failure", "Portal returned no screenshot")

        uri = uri_var.get_string()
        file_path = Gio.File.new_for_uri(uri).get_path()
        if file_path is None:
            logger.error("Capture: Portal returned unresolvable URI: %s", uri)
            return CaptureError("io_failure", "The screenshot location is not accessible")

        try:
            logger.info("Capture: Reading portal image from %s", file_path)
            with open(file_path, "rb") as f:
                image_bytes = f.read()
            if not image_bytes:
                raise ValueError("Empty image file")
            return image_bytes
        except (OSError, ValueError):
            logger.exception("Capture: Failed to read screenshot file")
            return CaptureError("io_failure", "Could not read the screenshot")
        finally:
            self._remove_fresh_screenshot(file_path)

    @staticmethod
    def _remove_fresh_screenshot(file_path):
        try:
            if time.time() - os.path.getmtime(file_path) <= FRESH_SCREENSHOT_SECONDS:
                os.remove(file_path)
            else:
                logger.warning("Capture: Keeping %s, it predates this capture", file_path)
        except OSError:
            pass
