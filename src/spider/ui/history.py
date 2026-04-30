import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib, Gdk
import datetime
import logging

logger = logging.getLogger(__name__)

class HistoryView(Gtk.Box):
    def __init__(self, db_manager, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12, **kwargs)
        self.db = db_manager
        
        self.search_bar = Gtk.SearchEntry(placeholder_text="Search history...")
        self.search_bar.connect("search-changed", self._on_search_changed)
        
        self._search_timeout_id = 0
        
        self.stack = Gtk.Stack()
        
        self.empty_page = Adw.StatusPage()
        self.empty_page.set_icon_name("document-open-recent-symbolic")
        self.empty_page.set_title("No History Yet")
        self.empty_page.set_description("Your captured text will appear here.")
        
        self.list_box = Gtk.ListBox()
        self.list_box.add_css_class("boxed-list")
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_child(self.list_box)
        
        self.stack.add_named(self.empty_page, "empty")
        self.stack.add_named(scrolled, "list")
        
        self.append(self.stack)
        
        css = b"row .delete-button { opacity: 0; } row:hover .delete-button { opacity: 1; }"
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        
        self.refresh()

    def refresh(self, query=None):
        logger.info("Refreshing history list (query: %s)", query)
        while (child := self.list_box.get_first_child()):
            self.list_box.remove(child)
            
        if query:
            items = self.db.search_history(query)
        else:
            items = self.db.get_history()
            
        if not items:
            self.stack.set_visible_child_name("empty")
            return
            
        self.stack.set_visible_child_name("list")

        for item in items:
            row = Adw.ActionRow()
            escaped_text = GLib.markup_escape_text(item['text'][:100])
            row.set_title(escaped_text + ("..." if len(item['text']) > 100 else ""))
            
            dt = datetime.datetime.fromtimestamp(item['timestamp'])
            row.set_subtitle(self._relative_time(dt))
            
            copy_btn = Gtk.Button(icon_name="edit-copy-symbolic")
            copy_btn.add_css_class("flat")
            copy_btn.set_tooltip_text("Copy Text")
            copy_btn.connect("clicked", self._on_copy_clicked, item['text'])
            row.add_suffix(copy_btn)

            del_btn = Gtk.Button(icon_name="user-trash-symbolic")
            del_btn.add_css_class("flat")
            del_btn.add_css_class("error")
            del_btn.add_css_class("delete-button")
            del_btn.set_tooltip_text("Delete Item")
            del_btn.connect("clicked", self._on_delete_clicked, item['id'])
            row.add_suffix(del_btn)
            
            self.list_box.append(row)

    def _relative_time(self, dt):
        now = datetime.datetime.now()
        diff = now - dt
        seconds = diff.total_seconds()
        if seconds < 60:
            return "Just now"
        elif seconds < 3600:
            return f"{int(seconds // 60)} minutes ago"
        elif seconds < 86400:
            return f"{int(seconds // 3600)} hours ago"
        elif diff.days == 1:
            return "Yesterday"
        elif diff.days < 7:
            return f"{diff.days} days ago"
        else:
            return dt.strftime("%b %d")

    def _on_search_changed(self, entry):
        if self._search_timeout_id:
            GLib.source_remove(self._search_timeout_id)
        
        self._search_timeout_id = GLib.timeout_add(300, self._do_search, entry.get_text())

    def _do_search(self, query):
        self._search_timeout_id = 0
        self.refresh(query)
        return False

    def _on_copy_clicked(self, button, text):
        logger.info("Historical item copy requested")
        self.get_clipboard().set_content(Gdk.ContentProvider.new_for_value(text))

        root = self.get_root()
        if hasattr(root, "add_toast"):
            root.add_toast("Copied to clipboard")

    def _on_delete_clicked(self, button, item_id):
        self.db.delete_result(item_id)
        self.refresh(self.search_bar.get_text())
        
        root = self.get_root()
        if hasattr(root, "add_toast"):
            root.add_toast("Item deleted")
