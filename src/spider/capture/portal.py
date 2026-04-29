import uuid
import os
import urllib.parse
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
        
        # Context to share between signal and call
        ctx = {
            "sub_id": 0,
            "callback": callback,
            "handle": None
        }
        
        logger.info("[Phase 1/5] Initiation: Calling Screenshot portal method...")
        
        # Call Screenshot method
        self.connection.call(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Screenshot",
            "Screenshot",
            GLib.Variant("(sa{sv})", (
                "", # Parent window
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
            # The call returns the object path of the Request object
            handle = res.get_child_value(0).get_string()
            ctx["handle"] = handle
            logger.info("Portal call successful. Request handle: %s", handle)
            
            # Subscribe to ALL Response signals on this interface and filter manually.
            # Some portal implementations use slightly different object paths for the signal.
            ctx["sub_id"] = self.connection.signal_subscribe(
                "org.freedesktop.portal.Desktop", # Sender (Portal)
                "org.freedesktop.portal.Request", # Interface
                "Response",                       # Signal
                None,                             # Object Path (None = any)
                None,
                Gio.DBusSignalFlags.NONE,
                self._on_response,
                ctx
            )
            logger.info("Subscribed to Response signals. Watching for handle: %s", handle)
            
        except Exception as e:
            logger.error("Error calling screenshot portal: %s", e)
            ctx["callback"](None)

    def _on_response(self, connection, sender_name, object_path, interface_name, signal_name, parameters, ctx):
        # Ignore signals that aren't for our specific request handle
        if object_path != ctx["handle"]:
            return

        logger.info("Matched response signal on %s", object_path)
        
        # Unsubscribe immediately
        if ctx["sub_id"]:
            try:
                self.connection.signal_unsubscribe(ctx["sub_id"])
            except:
                pass
            ctx["sub_id"] = 0
            
        response_code = parameters.get_child_value(0).get_uint32()
        results = parameters.get_child_value(1)
        
        if response_code == 0: # Success
            uri_var = results.lookup_value("uri", GLib.VariantType("s"))
            if uri_var:
                uri = uri_var.get_string()
                # Decode URL-encoded characters (like %20 for spaces)
                parsed_uri = urllib.parse.urlparse(uri)
                file_path = urllib.parse.unquote(parsed_uri.path)
                
                try:
                    logger.info("Reading captured image from: %s", file_path)
                    with open(file_path, "rb") as f:
                        image_bytes = f.read()
                    
                    os.remove(file_path)
                    ctx["callback"](image_bytes)
                except Exception as e:
                    logger.error("Error reading screenshot file: %s", e)
                    ctx["callback"](None)
            else:
                logger.error("Portal response missing 'uri' key")
                ctx["callback"](None)
        else:
            logger.warning("Portal reported failure or cancellation (code: %d)", response_code)
            ctx["callback"](None)
