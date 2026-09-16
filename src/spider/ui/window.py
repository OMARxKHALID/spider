import logging

from gi.repository import Gtk, Adw, Gio, GLib, Gdk

from spider.core.models import OCRResult
from spider.ui import icon_button, pill_button, word_count

logger = logging.getLogger(__name__)

CAPTURE_HIDE_DELAY_MS = 300
IDLE_TITLE = "Capture Text"
IDLE_DESCRIPTION = "Select an area of the screen or open an image to extract its text"


class SpiderWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(title="Spider", default_width=800, default_height=600, **kwargs)
        self.set_size_request(360, 300)
        logger.info("UI: Initializing main window")

        from spider.core.coordinator import PipelineCoordinator
        self.coordinator = PipelineCoordinator(self)

        self._capture_timeout_id = 0
        self._history_page = None
        self._result_page = None

        for name, callback in (
            ("capture", self._on_capture),
            ("open", self._on_open),
            ("history", self._on_toggle_history),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

        self.toast_overlay = Adw.ToastOverlay()
        self.nav_view = Adw.NavigationView()
        self.toast_overlay.set_child(self.nav_view)
        self.set_content(self.toast_overlay)

        self.home_page = self._create_home_page()
        self.nav_view.push(self.home_page)

    @property
    def history_page(self):
        if self._history_page is None:
            from spider.ui.history import HistoryPage
            self._history_page = HistoryPage(self.coordinator.db, self._on_history_item_selected, self.add_toast)
        return self._history_page

    @property
    def result_page(self):
        if self._result_page is None:
            self._result_page = self._create_result_page()
        return self._result_page

    def _create_home_page(self):
        self.status_page = Adw.StatusPage(icon_name="org.domain.Spider", title=IDLE_TITLE, description=IDLE_DESCRIPTION)

        buttons = Gtk.Box(spacing=12, homogeneous=True, halign=Gtk.Align.CENTER)
        narrow = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 500sp"))
        narrow.add_setter(buttons, "orientation", Gtk.Orientation.VERTICAL)
        self.add_breakpoint(narrow)
        buttons.append(pill_button("_Capture Region", "camera-photo-symbolic", "suggested-action", action_name="win.capture"))
        buttons.append(pill_button("_Open Image", "image-x-generic-symbolic", action_name="win.open"))

        self.spinner = Gtk.Spinner(width_request=32, height_request=32, halign=Gtk.Align.CENTER, visible=False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        box.append(buttons)
        box.append(self.spinner)
        self.status_page.set_child(box)

        menu = Gio.Menu()
        menu.append("_Preferences", "app.preferences")
        menu.append("_About Spider", "app.about")
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, primary=True, tooltip_text="Main Menu")

        header = Adw.HeaderBar()
        header.pack_start(icon_button("document-open-recent-symbolic", "History", action_name="win.history"))
        header.pack_end(menu_button)

        self.problem_banner = Adw.Banner(button_label="_Preferences", action_name="app.preferences", use_markup=False)

        toolbar = Adw.ToolbarView(content=self.status_page)
        toolbar.add_top_bar(header)
        toolbar.add_top_bar(self.problem_banner)
        return Adw.NavigationPage(child=toolbar, title="Spider", tag="home")

    def _create_result_page(self):
        self.text_view = Gtk.TextView(
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            top_margin=18, bottom_margin=18, left_margin=18, right_margin=18,
            css_classes=["card"],
        )
        self.text_view.update_property([Gtk.AccessibleProperty.LABEL], ["Extracted text"])

        scrolled = Gtk.ScrolledWindow(
            child=Adw.Clamp(child=self.text_view, maximum_size=900, margin_top=12, margin_bottom=24, margin_start=12, margin_end=12),
            vexpand=True,
        )

        self.result_title = Adw.WindowTitle(title="Extracted Text")
        header = Adw.HeaderBar(title_widget=self.result_title)
        header.pack_end(icon_button("camera-photo-symbolic", "New Capture", action_name="win.capture"))
        header.pack_end(icon_button("edit-copy-symbolic", "Copy Text", self._on_copy_result))

        toolbar = Adw.ToolbarView(content=scrolled)
        toolbar.add_top_bar(header)
        return Adw.NavigationPage(child=toolbar, title="Extracted Text", tag="result")

    def _on_toggle_history(self, *_):
        if self.nav_view.get_visible_page() == self._history_page:
            self.nav_view.pop()
        else:
            self._show_page(self.history_page)

    def _show_page(self, page):
        stack = self.nav_view.get_navigation_stack()
        if page in (stack.get_item(i) for i in range(stack.get_n_items())):
            self.nav_view.pop_to_page(page)
        else:
            self.nav_view.push(page)

    def _on_capture(self, *_):
        logger.info("UI: Capture requested")
        if self.coordinator.is_busy:
            return
        self.nav_view.pop_to_page(self.home_page)
        self.show_processing()
        self.set_visible(False)

        def start():
            self._capture_timeout_id = 0
            if not self.coordinator.start_capture_flow():
                self.show_idle()
            return GLib.SOURCE_REMOVE

        if self._capture_timeout_id:
            GLib.source_remove(self._capture_timeout_id)
        self._capture_timeout_id = GLib.timeout_add(CAPTURE_HIDE_DELAY_MS, start)

    def _on_open(self, *_):
        logger.info("UI: Open image requested")
        image_filter = Gtk.FileFilter(name="Images", mime_types=["image/png", "image/jpeg", "image/tiff", "image/webp", "image/bmp"])
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(image_filter)
        dialog = Gtk.FileDialog(title="Open Image", filters=filters, default_filter=image_filter)
        dialog.open(self, None, self._on_open_finished)

    def _on_open_finished(self, dialog, result):
        try:
            file = dialog.open_finish(result)
        except GLib.Error as e:
            if not e.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                logger.error("UI: File dialog error: %s", e.message)
                self.add_toast(f"Could not open image: {e.message}")
            return

        path = file.get_path()
        logger.info("UI: Opening local image: %s", path)
        if not path:
            self.add_toast("Only local images can be opened")
        elif not self.coordinator.process_image(path):
            self.add_toast("Still processing the previous image")

    def _on_history_item_selected(self, item):
        logger.info("UI: History item selected: %d", item["id"])
        self.show_result(OCRResult(
            text=item["text"],
            confidence=item["confidence"] or 0.0,
            engine_used=item["engine_used"],
            timestamp=item["timestamp"],
            language=item["language"],
        ))

    def show_result(self, result):
        self._reveal()
        if not result.text.strip():
            self.add_toast("No text found")
            return

        logger.info("UI: Displaying OCR result (%d characters)", len(result.text))
        page = self.result_page
        self.text_view.get_buffer().set_text(result.text, -1)
        self.result_title.set_subtitle(f"{word_count(result.text)} · {result.confidence:.0%} confidence")
        self._show_page(page)

    def _reveal(self):
        if not self.get_visible():
            self.set_visible(True)
            self.present()

    def _set_busy(self, busy):
        for name in ("capture", "open"):
            self.lookup_action(name).set_enabled(not busy)
        self.spinner.set_visible(busy)
        self.spinner.set_spinning(busy)

    def show_processing(self):
        self._set_busy(True)
        self.status_page.set_title("Extracting Text…")
        self.status_page.set_description(None)

    def show_idle(self):
        self._reveal()
        self._set_busy(False)
        self.status_page.set_title(IDLE_TITLE)
        self.status_page.set_description(IDLE_DESCRIPTION)

    def _on_copy_result(self, *_):
        buffer = self.text_view.get_buffer()
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        self.get_clipboard().set_content(Gdk.ContentProvider.new_for_value(text))
        self.add_toast("Copied to clipboard")

    def add_toast(self, title, button_label=None, on_button=None):
        toast = Adw.Toast(title=title, use_markup=False)
        if button_label:
            toast.set_button_label(button_label)
            toast.connect("button-clicked", lambda *_: on_button())
        self.toast_overlay.add_toast(toast)
        return toast

    def show_problem(self, message):
        if message:
            self.problem_banner.set_title(message)
        self.problem_banner.set_revealed(bool(message))
