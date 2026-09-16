import logging
import sqlite3

from gi.repository import Gtk, Adw, GLib, Gdk, GObject

from spider.ui import icon_button, pill_button, one_line, word_count, day_heading, clock_time

logger = logging.getLogger(__name__)

SEARCH_DELAY_MS = 250


class HistoryPage(Adw.NavigationPage):
    def __init__(self, db, on_open_item, add_toast):
        super().__init__(title="History", tag="history")
        self.db = db
        self.on_open_item = on_open_item
        self.add_toast = add_toast
        self._groups = []
        self._search_timeout_id = 0

        search_button = Gtk.ToggleButton(icon_name="edit-find-symbolic", tooltip_text="Search")
        search_button.update_property([Gtk.AccessibleProperty.LABEL], ["Search"])

        header = Adw.HeaderBar()
        header.pack_end(search_button)

        self.search_entry = Gtk.SearchEntry(placeholder_text="Search history", hexpand=True)
        self.search_entry.update_property([Gtk.AccessibleProperty.LABEL], ["Search history"])
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.search_entry.connect("stop-search", lambda *_: search_button.set_active(False))

        self.search_bar = Gtk.SearchBar(child=Adw.Clamp(child=self.search_entry, maximum_size=600))
        self.search_bar.connect_entry(self.search_entry)
        self.search_bar.set_key_capture_widget(self)
        search_button.bind_property(
            "active", self.search_bar, "search-mode-enabled",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
        )

        self.list_page = Adw.PreferencesPage()

        self.clear_group = Adw.PreferencesGroup()
        clear_button = pill_button("_Clear History…", "user-trash-symbolic", on_clicked=self._on_clear_clicked)
        clear_button.set_halign(Gtk.Align.CENTER)
        self.clear_group.add(clear_button)

        empty_page = Adw.StatusPage(
            icon_name="document-open-recent-symbolic",
            title="No History",
            description="Text you capture will be listed here",
        )
        error_page = Adw.StatusPage(
            icon_name="dialog-warning-symbolic",
            title="Could Not Load History",
            description="The history database could not be read",
        )
        no_results_page = Adw.StatusPage(
            icon_name="edit-find-symbolic",
            title="No Results Found",
            description="Try a different search",
        )

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_named(self.list_page, "list")
        self.stack.add_named(empty_page, "empty")
        self.stack.add_named(no_results_page, "no-results")
        self.stack.add_named(error_page, "error")

        toolbar = Adw.ToolbarView(content=self.stack)
        toolbar.add_top_bar(header)
        toolbar.add_top_bar(self.search_bar)
        self.set_child(toolbar)

        shortcuts = Gtk.ShortcutController(scope=Gtk.ShortcutScope.MANAGED)
        shortcuts.add_shortcut(Gtk.Shortcut.new(
            Gtk.ShortcutTrigger.parse_string("<Control>f"),
            Gtk.CallbackAction.new(lambda *_: search_button.set_active(True) or True),
        ))
        self.add_controller(shortcuts)

        self.connect("showing", lambda *_: self.refresh())

    def refresh(self):
        query = self.search_entry.get_text().strip()
        logger.info("UI: Refreshing history list (query: %s)", query)

        for group in self._groups:
            self.list_page.remove(group)
        self._groups.clear()
        if self.clear_group.get_parent():
            self.list_page.remove(self.clear_group)

        try:
            items = self.db.search_history(query) if query else self.db.get_history()
        except sqlite3.Error:
            logger.exception("UI: Could not load history")
            self.stack.set_visible_child_name("error")
            return

        if not items:
            self.stack.set_visible_child_name("no-results" if query else "empty")
            return

        if query:
            self._add_group("Results", items)
        else:
            sections = {}
            for item in items:
                sections.setdefault(day_heading(item["timestamp"]), []).append(item)
            for heading, section_items in sections.items():
                self._add_group(heading, section_items)
            self.list_page.add(self.clear_group)

        self.stack.set_visible_child_name("list")

    def _add_group(self, title, items):
        group = Adw.PreferencesGroup(title=title)
        for item in items:
            group.add(self._build_row(item))
        self.list_page.add(group)
        self._groups.append(group)

    def _build_row(self, item):
        row = Adw.ActionRow(
            title=one_line(item["text"]),
            subtitle=f"{clock_time(item['timestamp'])} · {word_count(item['text'])}",
            title_lines=1,
            subtitle_lines=1,
            use_markup=False,
            activatable=True,
        )
        row.connect("activated", lambda *_: self.on_open_item(item))

        copy_button = icon_button("edit-copy-symbolic", "Copy Text", lambda *_: self._copy(item["text"]))
        delete_button = icon_button("user-trash-symbolic", "Delete", lambda *_: self._delete(item))
        for button in (copy_button, delete_button):
            button.set_valign(Gtk.Align.CENTER)
            button.add_css_class("flat")
            row.add_suffix(button)
        return row

    def _on_search_changed(self, entry):
        if self._search_timeout_id:
            GLib.source_remove(self._search_timeout_id)
        self._search_timeout_id = GLib.timeout_add(SEARCH_DELAY_MS, self._run_search)

    def _run_search(self):
        self._search_timeout_id = 0
        self.refresh()
        return GLib.SOURCE_REMOVE

    def _copy(self, text):
        self.get_clipboard().set_content(Gdk.ContentProvider.new_for_value(text))
        self.add_toast("Copied to clipboard")

    def _delete(self, item):
        logger.info("UI: Deleting history item %d", item["id"])
        if not self._run_db(lambda: self.db.delete_result(item["id"]), "Could not delete capture"):
            return
        self.refresh()

        def undo():
            self._run_db(lambda: self.db.restore_result(item), "Could not restore capture")
            self.refresh()

        self.add_toast("Capture deleted", "_Undo", undo)

    def _on_clear_clicked(self, button):
        dialog = Adw.AlertDialog(
            heading="Clear History?",
            body="All saved captures will be permanently deleted.",
            close_response="cancel",
            default_response="cancel",
        )
        dialog.add_response("cancel", "_Cancel")
        dialog.add_response("clear", "_Clear")
        dialog.set_response_appearance("clear", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_clear_response)
        dialog.present(self)

    def _on_clear_response(self, dialog, response):
        if response != "clear":
            return
        logger.info("UI: Clearing history")
        if self._run_db(self.db.clear_history, "Could not clear history"):
            self.add_toast("History cleared")
        self.refresh()

    def _run_db(self, operation, failure_message):
        try:
            operation()
            return True
        except sqlite3.Error:
            logger.exception("UI: %s", failure_message)
            self.add_toast(failure_message)
            return False
