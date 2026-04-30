import uuid
import os
import urllib.parse
import tempfile
from gi.repository import Gio, GLib
import logging

logger = logging.getLogger(__name__)

class PortalCapture:
    def __init__(self):
        try:
            self.connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception as e:
            logger.error("Failed to connect to Session Bus: %s", e)
            self.connection = None
        
    def capture_interactive(self, callback):
        if not self.connection:
            logger.error("No DBus connection available")
            callback(None)
            return

        token = "spider_" + str(uuid.uuid4()).replace("-", "")
        
        ctx = {
            "sub_id": 0,
            "callback": callback,
            "handle": None,
            "completed": False
        }
        
        logger.info("Initiation: Calling Screenshot portal method...")
        
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

    def _on_call_done(self, conn, result, ctx):
        try:
            res = conn.call_finish(result)
            handle = res.get_child_value(0).get_string()
            ctx["handle"] = handle
            
            ctx["sub_id"] = self.connection.signal_subscribe(
                "org.freedesktop.portal.Desktop",
                "org.freedesktop.portal.Request",
                "Response",
                None,
                None,
                Gio.DBusSignalFlags.NONE,
                self._on_response,
                ctx
            )
            logger.info("Portal call successful. Watching handle: %s", handle)
            
        except Exception as e:
            logger.error("Error calling screenshot portal: %s", e)
            if not ctx["completed"]:
                ctx["completed"] = True
                ctx["callback"](None)

    def _on_response(self, connection, sender_name, object_path, interface_name, signal_name, parameters, ctx):
        if object_path != ctx["handle"]:
            return

        if ctx["completed"]:
            return
        ctx["completed"] = True

        if ctx["sub_id"]:
            try:
                self.connection.signal_unsubscribe(ctx["sub_id"])
            except Exception:
                pass
            ctx["sub_id"] = 0
            
        response_code = parameters.get_child_value(0).get_uint32()
        results = parameters.get_child_value(1)
        
        if response_code == 0:
            uri_var = results.lookup_value("uri", GLib.VariantType("s"))
            if uri_var:
                uri = uri_var.get_string()
                file_path = Gio.File.new_for_uri(uri).get_path()
                if file_path is None:
                    logger.error("Portal returned an unresolvable URI: %s", uri)
                    ctx["callback"](None)
                    return

                def _is_safe_path(base: str, target: str) -> bool:
                    try:
                        return os.path.commonpath([base, target]) == base
                    except ValueError:
                        return False

                real_file_path = os.path.realpath(file_path)
                allowed_prefixes = (
                    GLib.get_tmp_dir(),
                    GLib.get_user_runtime_dir(),
                    os.path.expanduser("~"),
                )
                if not any(_is_safe_path(p, real_file_path) for p in allowed_prefixes):
                    logger.error("Portal returned suspicious path: %s", real_file_path)
                    ctx["callback"](None)
                    return

                try:
                    image_bytes = None
                    try:
                        with open(file_path, "rb") as f:
                            image_bytes = f.read()
                    finally:
                        if os.path.exists(file_path):
                            os.remove(file_path)

                    ctx["callback"](image_bytes)
                except Exception as e:
                    logger.error("Error reading screenshot file: %s", e)
                    ctx["callback"](None)
            else:
                ctx["callback"](None)
        else:
            ctx["callback"](None)
