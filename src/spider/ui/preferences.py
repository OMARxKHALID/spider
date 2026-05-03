import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio
from spider.ocr.registry import EngineRegistry
from spider.ocr import keystore

class SpiderPreferencesWindow(Adw.PreferencesWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.settings = Gio.Settings.new("org.domain.Spider")
        self._build_engine_page()

    def _build_engine_page(self):
        page = Adw.PreferencesPage(title="OCR Engine", icon_name="brain-augmented-symbolic")
        self.add(page)

        engine_group = Adw.PreferencesGroup(
            title="Engine",
            description="Choose the OCR engine used for text recognition"
        )
        page.add(engine_group)

        all_engines = EngineRegistry.all()
        engine_ids = [e.id for e in all_engines]
        engine_names = [e.display_name for e in all_engines]

        engine_row = Adw.ComboRow(title="OCR Engine")
        string_list = Gtk.StringList.new(engine_names)
        engine_row.set_model(string_list)

        current_id = self.settings.get_string("ocr-engine")
        if current_id in engine_ids:
            engine_row.set_selected(engine_ids.index(current_id))

        engine_group.add(engine_row)

        self._status_row = Adw.ActionRow(title="Status")
        engine_group.add(self._status_row)
        self._update_status_row(current_id)

        engine_row.connect("notify::selected", lambda row, _:
            self._on_engine_selected(row, engine_ids, all_engines))

        lang_group = Adw.PreferencesGroup(title="Language")
        page.add(lang_group)

        lang_row = Adw.EntryRow(title="OCR Language")
        lang_row.set_text(self.settings.get_string("language"))
        lang_row.connect("changed", lambda r:
            self.settings.set_string("language", r.get_text()))
        lang_group.add(lang_row)

        self._advanced_group = Adw.PreferencesGroup(
            title="Tesseract Advanced",
            description="Fine-tune Tesseract page segmentation"
        )
        page.add(self._advanced_group)
        self._advanced_group.set_visible(current_id == "tesseract")

        psm_options = [
            "3 — Fully automatic page segmentation",
            "6 — Assume a single uniform block of text",
            "7 — Treat the image as a single text line",
            "8 — Treat the image as a single word",
            "11 — Sparse text, find as much text as possible",
        ]
        psm_map = {0: 3, 1: 6, 2: 7, 3: 8, 4: 11}
        psm_row = Adw.ComboRow(title="Page Segmentation Mode")
        psm_row.set_model(Gtk.StringList.new(psm_options))
        
        current_psm = self.settings.get_int("tesseract-psm")
        reverse_map = {v: k for k, v in psm_map.items()}
        psm_row.set_selected(reverse_map.get(current_psm, 0))
        
        psm_row.connect("notify::selected", lambda row, _:
            self.settings.set_int("tesseract-psm", psm_map.get(row.get_selected(), 3)))
        
        self._advanced_group.add(psm_row)

        self._api_group = Adw.PreferencesGroup(title="Authentication")
        page.add(self._api_group)
        self._api_group.set_visible(False)

        api_row = Adw.PasswordEntryRow(title="API Key")
        api_row.connect("apply", self._on_api_key_apply)
        self._api_group.add(api_row)

    def _on_engine_selected(self, row, engine_ids, all_engines):
        idx = row.get_selected()
        if idx == Gtk.INVALID_LIST_POSITION:
            return
        engine_id = engine_ids[idx]
        descriptor = all_engines[idx]
        self.settings.set_string("ocr-engine", engine_id)
        self._update_status_row(engine_id)
        self._advanced_group.set_visible(engine_id == "tesseract")
        self._api_group.set_visible(descriptor.requires_api_key)

    def _update_status_row(self, engine_id: str):
        try:
            descriptor = EngineRegistry.get(engine_id)
            available, reason = descriptor.check_available()
        except KeyError:
            available, reason = False, f"Unknown engine: {engine_id}"

        if available:
            self._status_row.set_subtitle("Ready")
            self._status_row.add_css_class("success")
            self._status_row.remove_css_class("error")
        else:
            self._status_row.set_subtitle(reason)
            self._status_row.add_css_class("error")
            self._status_row.remove_css_class("success")

    def _on_api_key_apply(self, row):
        engine_id = self.settings.get_string("ocr-engine")
        keystore.store_api_key(engine_id, row.get_text())
        row.set_text("")
