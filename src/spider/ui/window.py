import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib, Gdk, GObject
import logging
import os

logger = logging.getLogger(__name__)

class SpiderWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        logger.info("UI: Initializing main window")
        
        from spider.core.coordinator import PipelineCoordinator
        self.coordinator = PipelineCoordinator(self)

        self.set_title("Spider")
        self.set_default_size(800, 600)

        self._history_view = None
        self._history_page = None
        self._result_page = None

        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        self.nav_view = Adw.NavigationView()
        self.toast_overlay.set_child(self.nav_view)

        self.home_page = self._create_home_page()
        self.nav_view.push(self.home_page)

        icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        icon_path = os.path.join(base_dir, "data")
        if os.path.exists(os.path.join(icon_path, "org.domain.Spider.png")):
            icon_theme.add_search_path(icon_path)
        
        self._setup_shortcuts()

    @property
    def history_view(self):
        if self._history_view is None:
            from spider.ui.history import HistoryView
            self._history_view = HistoryView(self.coordinator.db, on_item_selected=self._on_history_item_selected)
        return self._history_view

    @property
    def history_page(self):
        if self._history_page is None:
            self._history_page = self._create_history_page()
        return self._history_page

    @property
    def result_page(self):
        if self._result_page is None:
            self._result_page = self._create_result_page()
        return self._result_page

    def _setup_shortcuts(self):
        controller = Gtk.ShortcutController()

        capture_trigger = Gtk.ShortcutTrigger.parse_string("<Control><Shift>C")
        capture_action = Gtk.CallbackAction.new(lambda *_: [self.on_capture_clicked(None), True][-1])
        capture_shortcut = Gtk.Shortcut.new(capture_trigger, capture_action)
        controller.add_shortcut(capture_shortcut)

        history_trigger = Gtk.ShortcutTrigger.parse_string("<Control>H")
        def toggle_history(*_):
            if self.nav_view.get_visible_page() == self.history_page:
                self.nav_view.pop()
            else:
                self.nav_view.push(self.history_page)
            return True
        history_action = Gtk.CallbackAction.new(toggle_history)
        history_shortcut = Gtk.Shortcut.new(history_trigger, history_action)
        controller.add_shortcut(history_shortcut)

        copy_trigger = Gtk.ShortcutTrigger.parse_string("<Control>C")
        def do_copy(*_):
            if self.nav_view.get_visible_page() == self._result_page:
                focus_widget = self.get_focus()
                if focus_widget != self.text_view:
                    self._on_copy_result_clicked(self.copy_btn)
                    return True
            return False
        copy_action = Gtk.CallbackAction.new(do_copy)
        copy_shortcut = Gtk.Shortcut.new(copy_trigger, copy_action)
        controller.add_shortcut(copy_shortcut)

        self.add_controller(controller)

    def _create_home_page(self):
        status_page = Adw.StatusPage()
        status_page.set_title("Ready to Capture")
        status_page.set_description("Press the capture button or use Ctrl+Shift+C")
        status_page.set_icon_name("org.domain.Spider")

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        btn_box.set_halign(Gtk.Align.CENTER)
        btn_box.set_margin_top(24)

        self.capture_btn = Gtk.Button(label="Capture Region")
        self.capture_btn.add_css_class("suggested-action")
        self.capture_btn.add_css_class("pill")
        self.capture_btn.set_size_request(160, 44)
        self.capture_btn.connect("clicked", self.on_capture_clicked)
        btn_box.append(self.capture_btn)

        self.open_btn = Gtk.Button(label="Open Image")
        self.open_btn.add_css_class("pill")
        self.open_btn.set_size_request(160, 44)
        self.open_btn.connect("clicked", self.on_open_clicked)
        btn_box.append(self.open_btn)

        status_page.set_child(btn_box)

        toolbar_view = Adw.ToolbarView()
        header_bar = Adw.HeaderBar()
        self.home_title = Adw.WindowTitle(title="Spider")
        header_bar.set_title_widget(self.home_title)

        history_btn = Gtk.Button(icon_name="document-open-recent-symbolic")
        history_btn.set_tooltip_text("History")
        history_btn.connect("clicked", lambda x: self.nav_view.push(self.history_page))
        header_bar.pack_start(history_btn)

        about_btn = Gtk.Button(icon_name="help-about-symbolic")
        about_btn.set_tooltip_text("About")
        about_btn.connect("clicked", self._on_about_clicked)
        header_bar.pack_end(about_btn)

        toolbar_view.add_top_bar(header_bar)
        toolbar_view.set_content(status_page)

        page = Adw.NavigationPage.new(toolbar_view, "home")
        page.set_title("Spider")
        self._home_status_page = status_page
        return page

    def _create_result_page(self):
        self.text_view = Gtk.TextView()
        self.text_view.set_editable(True)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.text_view.add_css_class("card")
        self.text_view.set_margin_start(12)
        self.text_view.set_margin_end(12)
        self.text_view.set_margin_top(12)
        self.text_view.set_margin_bottom(12)
        self.text_view.set_left_margin(20)
        self.text_view.set_right_margin(20)
        self.text_view.set_top_margin(20)
        self.text_view.set_bottom_margin(20)

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.text_view)
        scroll.set_vexpand(True)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(800)

        self.stats_label = Gtk.Label()
        self.stats_label.add_css_class("dim-label")
        self.stats_label.set_margin_top(8)
        self.stats_label.set_margin_bottom(12)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(scroll)
        box.append(self.stats_label)

        clamp.set_child(box)
        clamp.set_margin_start(24)
        clamp.set_margin_end(24)
        clamp.set_margin_top(24)
        clamp.set_margin_bottom(24)

        toolbar_view = Adw.ToolbarView()
        header_bar = Adw.HeaderBar()
        self.result_title = Adw.WindowTitle(title="OCR Result")
        header_bar.set_title_widget(self.result_title)

        new_cap_btn = Gtk.Button(icon_name="camera-photo-symbolic")
        new_cap_btn.set_tooltip_text("New Capture")
        new_cap_btn.connect("clicked", self.on_capture_clicked)
        header_bar.pack_end(new_cap_btn)

        self.copy_btn = Gtk.Button(icon_name="edit-copy-symbolic")
        self.copy_btn.connect("clicked", self._on_copy_result_clicked)
        header_bar.pack_end(self.copy_btn)

        toolbar_view.add_top_bar(header_bar)
        toolbar_view.set_content(clamp)

        page = Adw.NavigationPage.new(toolbar_view, "result")
        page.set_title("OCR Result")
        return page

    def _create_history_page(self):
        toolbar_view = Adw.ToolbarView()
        header_bar = Adw.HeaderBar()

        self.history_title = Adw.WindowTitle(title="History")
        header_bar.set_title_widget(self.history_title)

        search_btn = Gtk.ToggleButton(icon_name="system-search-symbolic")
        search_btn.set_tooltip_text("Search History")
        header_bar.pack_start(search_btn)

        clear_btn = Gtk.Button(icon_name="edit-clear-all-symbolic")
        clear_btn.set_tooltip_text("Clear All")
        clear_btn.add_css_class("error")
        clear_btn.connect("clicked", self._on_clear_history_clicked)
        header_bar.pack_end(clear_btn)

        search_bar = Gtk.SearchBar()
        search_bar.connect_entry(self.history_view.search_bar)
        search_bar.set_child(self.history_view.search_bar)
        search_btn.bind_property("active", search_bar, "search-mode-enabled", GObject.BindingFlags.BIDIRECTIONAL)

        toolbar_view.add_top_bar(header_bar)
        toolbar_view.add_top_bar(search_bar)

        self.history_view.set_margin_start(24)
        self.history_view.set_margin_end(24)
        self.history_view.set_margin_top(24)
        self.history_view.set_margin_bottom(24)

        toolbar_view.set_content(self.history_view)

        page = Adw.NavigationPage.new(toolbar_view, "history")
        page.set_title("History")
        return page

    def on_capture_clicked(self, button):
        logger.info("UI: Capture requested")
        if self.coordinator.is_busy:
            return

        if self.nav_view.get_visible_page() != self.home_page:
            self.nav_view.pop_to_page(self.home_page)

        self.capture_btn.set_sensitive(False)
        self.open_btn.set_sensitive(False)
        self._home_status_page.set_title("Capturing...")
        self.home_title.set_subtitle("Selecting region...")

        self.set_visible(False)
        GLib.timeout_add(300, self.coordinator.start_capture_flow)

    def on_open_clicked(self, button):
        logger.info("UI: Open image requested")
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Open Image")

        filters = Gio.ListStore.new(Gtk.FileFilter)
        image_filter = Gtk.FileFilter()
        image_filter.set_name("Images")
        image_filter.add_mime_type("image/png")
        image_filter.add_mime_type("image/jpeg")
        image_filter.add_mime_type("image/tiff")
        filters.append(image_filter)
        dialog.set_filters(filters)

        dialog.open(self, None, self._on_file_open_done)

    def _on_file_open_done(self, dialog, result):
        try:
            file = dialog.open_finish(result)
            if file:
                path = file.get_path()
                logger.info("UI: Opening local image: %s", path)
                with open(path, "rb") as f:
                    image_bytes = f.read()

                self.add_toast("Processing Image...")
                self._home_status_page.set_title("Processing...")
                self.coordinator.process_image(image_bytes)
        except Exception as e:
            logger.error("UI: Failed to open image: %s", e)
            self.add_toast(f"Failed to open image: {str(e)}")

    def _on_history_item_selected(self, item):
        logger.info("UI: Historical item selected: %d", item['id'])
        from spider.core.models import OCRResult
        result = OCRResult(
            text=item['text'],
            confidence=item['confidence'] or 0.0,
            engine_used=item['engine_used'],
            timestamp=item['timestamp'],
            language=item['language']
        )
        self.show_result(result)

    def show_result(self, result):
        logger.info("UI: Displaying OCR result (%d characters)", len(result.text))
        self._home_status_page.set_title("Ready to Capture")
        self.home_title.set_subtitle("")
        self.capture_btn.set_sensitive(True)
        self.open_btn.set_sensitive(True)

        self.set_visible(True)
        self.present()

        if not result.text or not result.text.strip():
            self.add_toast("No text detected")
            return

        _ = self.result_page 

        buffer = self.text_view.get_buffer()
        buffer.set_text(result.text, -1)

        word_count = len(result.text.split())
        char_count = len(result.text)
        accuracy = result.confidence * 100
        self.stats_label.set_label(f"{word_count} words · {char_count} characters · {accuracy:.1f}% accuracy")
        self.result_title.set_subtitle(f"{word_count} words extracted ({accuracy:.0f}% confidence)")

        if self.nav_view.get_visible_page() != self.result_page:
            self.nav_view.push(self.result_page)

        if self._history_view:
            self.history_view.refresh()

    def reset_home_title(self):
        self.set_visible(True)
        self.present()
        self._home_status_page.set_title("Ready to Capture")
        self.home_title.set_subtitle("")
        self.capture_btn.set_sensitive(True)
        self.open_btn.set_sensitive(True)

    def _on_copy_result_clicked(self, btn):
        logger.info("UI: Copying result to clipboard")
        buffer = self.text_view.get_buffer()
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        self.get_clipboard().set_content(Gdk.ContentProvider.new_for_value(text))

        btn.set_icon_name("emblem-ok-symbolic")
        GLib.timeout_add(2000, lambda: [btn.set_icon_name("edit-copy-symbolic"), False][1])

    def _on_clear_history_clicked(self, btn):
        logger.info("UI: Clearing history")
        self.coordinator.db.clear_history()
        if self._history_view:
            self.history_view.refresh()
        self.add_toast("History cleared")

    def _on_about_clicked(self, btn):
        about = Adw.AboutDialog.new()
        about.set_application_name("Spider")
        about.set_application_icon("org.domain.Spider")
        about.set_developer_name("omarxkhalid")
        about.set_version("0.1.0")
        about.set_website("https://github.com/omarxkhalid/spider")
        about.set_copyright("© 2026 omarxkhalid")
        about.present(self)

    def add_toast(self, text):
        toast = Adw.Toast.new(text)
        toast.set_timeout(2)
        self.toast_overlay.add_toast(toast)
