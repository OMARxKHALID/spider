import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib, Gdk
import logging
import os

logger = logging.getLogger(__name__)

from spider.core.coordinator import PipelineCoordinator
from spider.ui.history import HistoryView

class SpiderWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        logger.info("Initializing SpiderWindow...")
        self.coordinator = PipelineCoordinator(self)
        
        self.set_title("Spider OCR")
        self.set_default_size(800, 600)

        icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        icon_path = os.path.join(base_dir, "data")
        if os.path.exists(os.path.join(icon_path, "org.domain.Spider.png")):
            icon_theme.add_search_path(icon_path)

        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        self.nav_view = Adw.NavigationView()
        self.toast_overlay.set_child(self.nav_view)

        self.home_page = self._create_home_page()
        self.nav_view.push(self.home_page)
        
        self.history_view = HistoryView(self.coordinator.db)
        self.history_page = self._create_history_page()
        
        logger.info("Building result and history pages...")
        self.result_page = self._create_result_page()

    def _create_home_page(self):
        logger.info("Creating home page")
        status_page = Adw.StatusPage()
        status_page.set_title("Ready to Capture")
        status_page.set_description("Press the capture button or use Ctrl+Shift+E")
        status_page.set_icon_name("org.domain.Spider")

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        btn_box.set_halign(Gtk.Align.CENTER)
        btn_box.set_margin_top(24)
        btn_box.set_margin_bottom(24)

        capture_btn = Gtk.Button(label="Capture Region")
        capture_btn.add_css_class("suggested-action")
        capture_btn.add_css_class("pill")
        capture_btn.set_size_request(160, 44)
        capture_btn.connect("clicked", self.on_capture_clicked)
        btn_box.append(capture_btn)

        open_btn = Gtk.Button(label="Open Image")
        open_btn.add_css_class("pill")
        open_btn.set_size_request(160, 44)
        open_btn.connect("clicked", self.on_open_clicked)
        btn_box.append(open_btn)

        status_page.set_child(btn_box)

        toolbar_view = Adw.ToolbarView()
        header_bar = Adw.HeaderBar()
        
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
        page.set_title("Spider OCR")
        self._home_status_page = status_page
        return page

    def _create_result_page(self):
        logger.info("Creating result page")
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
        clamp.set_tightening_threshold(600)
        clamp.set_child(scroll)
        clamp.set_margin_start(24)
        clamp.set_margin_end(24)
        clamp.set_margin_top(24)
        clamp.set_margin_bottom(24)
        
        toolbar_view = Adw.ToolbarView()
        header_bar = Adw.HeaderBar()
        
        new_cap_btn = Gtk.Button(icon_name="camera-photo-symbolic")
        new_cap_btn.set_tooltip_text("New Capture")
        new_cap_btn.connect("clicked", self.on_capture_clicked)
        header_bar.pack_end(new_cap_btn)
        
        copy_btn = Gtk.Button(icon_name="edit-copy-symbolic")
        copy_btn.connect("clicked", self._on_copy_result_clicked)
        header_bar.pack_end(copy_btn)
        
        toolbar_view.add_top_bar(header_bar)
        toolbar_view.set_content(clamp)
        
        page = Adw.NavigationPage.new(toolbar_view, "result")
        page.set_title("OCR Result")
        return page

    def _create_history_page(self):
        logger.info("Creating history page")
        toolbar_view = Adw.ToolbarView()
        header_bar = Adw.HeaderBar()
        
        clear_btn = Gtk.Button(icon_name="edit-clear-all-symbolic")
        clear_btn.set_tooltip_text("Clear All History")
        clear_btn.add_css_class("error")
        clear_btn.connect("clicked", self._on_clear_history_clicked)
        header_bar.pack_end(clear_btn)
        
        toolbar_view.add_top_bar(header_bar)
        
        self.history_view.set_margin_start(24)
        self.history_view.set_margin_end(24)
        self.history_view.set_margin_top(24)
        self.history_view.set_margin_bottom(24)
        
        toolbar_view.set_content(self.history_view)
        
        page = Adw.NavigationPage.new(toolbar_view, "history")
        page.set_title("History")
        return page

    def on_capture_clicked(self, button):
        logger.info("Capture button clicked")
        if self.coordinator._is_busy:
            return
        self.add_toast("Capture Started")
        self._home_status_page.set_title("Capturing...")
        self.coordinator.start_capture_flow()

    def on_open_clicked(self, button):
        logger.info("Open image button clicked")
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
        logger.info("File dialog closed")
        try:
            file = dialog.open_finish(result)
            if file:
                path = file.get_path()
                logger.info("Opening local image: %s", path)
                with open(path, "rb") as f:
                    image_bytes = f.read()

                self.add_toast("Processing Image...")
                self._home_status_page.set_title("Processing...")
                self.coordinator.process_image(image_bytes)
        except Exception as e:
            self.add_toast(f"Failed to open image: {str(e)}")

    def show_result(self, result):
        logger.info("UI: Displaying OCR result")
        self._home_status_page.set_title("Ready to Capture")
        buffer = self.text_view.get_buffer()
        buffer.set_text(result.text, -1)
        
        if self.nav_view.get_visible_page() != self.result_page:
            self.nav_view.push(self.result_page)
            
        self.history_view.refresh()
        self.add_toast("OCR Complete")

    def reset_home_title(self):
        self._home_status_page.set_title("Ready to Capture")

    def _on_copy_result_clicked(self, btn):
        logger.info("Copy result requested")
        buffer = self.text_view.get_buffer()
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        self.get_clipboard().set_content(Gdk.ContentProvider.new_for_value(text))
        self.add_toast("Copied to clipboard")

    def _on_clear_history_clicked(self, btn):
        logger.info("Clear history requested")
        self.coordinator.db.clear_history()
        self.history_view.refresh()
        self.add_toast("History cleared")

    def _on_about_clicked(self, btn):
        about = Adw.AboutWindow(
            transient_for=self,
            application_name="Spider OCR",
            application_icon="org.domain.Spider",
            developer_name="omarxkhalid",
            version="0.1.0",
            website="https://github.com/omarxkhalid/spider",
            issue_url="https://github.com/omarxkhalid/spider/issues",
            copyright="© 2026 omarxkhalid"
        )
        about.present()

    def add_toast(self, text):
        toast = Adw.Toast.new(text)
        self.toast_overlay.add_toast(toast)
