from gi.repository import Gtk, Adw, Gio

from spider.core.exceptions import describe_error
from spider.ocr.registry import EngineRegistry
from spider.ocr.tesseract import missing_languages

PSM_OPTIONS = [
    (3, "Automatic"),
    (6, "Single Block"),
    (7, "Single Line"),
    (8, "Single Word"),
    (11, "Sparse Text"),
]


class SpiderPreferencesDialog(Adw.PreferencesDialog):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.settings = Gio.Settings.new("org.domain.Spider")

        engine_group = Adw.PreferencesGroup(title="Engine")
        engine_group.add(self._build_engine_row())
        engine_group.add(self._build_psm_row())

        language_group = Adw.PreferencesGroup(
            title="Language",
            description="Tesseract language codes, such as eng or eng+ara",
        )
        language_row = Adw.EntryRow(title="Languages", text=self.settings.get_string("language"), show_apply_button=True)
        language_row.connect("apply", self._on_language_apply)
        language_group.add(language_row)

        page = Adw.PreferencesPage(title="General", icon_name="preferences-system-symbolic")
        page.add(engine_group)
        page.add(language_group)
        self.add(page)

    def _build_engine_row(self):
        descriptor = EngineRegistry.get(self.settings.get_string("ocr-engine"))
        available, reason = descriptor.check_available()
        row = Adw.ActionRow(title="OCR Engine", subtitle=f"{descriptor.display_name} · Ready" if available else reason, use_markup=False)
        if not available:
            row.add_css_class("error")
        return row

    def _build_psm_row(self):
        values = [value for value, _ in PSM_OPTIONS]
        row = Adw.ComboRow(title="Page Layout", model=Gtk.StringList.new([label for _, label in PSM_OPTIONS]))
        current = self.settings.get_int("tesseract-psm")
        row.set_selected(values.index(current) if current in values else 0)
        row.connect("notify::selected", lambda r, _: self.settings.set_int("tesseract-psm", values[r.get_selected()]))
        return row

    def _on_language_apply(self, row):
        language = row.get_text().strip()
        if not language:
            row.set_text(self.settings.get_string("language"))
            return

        try:
            missing = missing_languages(language)
        except Exception as e:
            self._reject_language(row, describe_error(e))
            return
        if missing:
            self._reject_language(row, f"Language data not installed: {', '.join(missing)}")
            return

        row.remove_css_class("error")
        self.settings.set_string("language", language)

    def _reject_language(self, row, message):
        row.add_css_class("error")
        self.add_toast(Adw.Toast(title=message, use_markup=False))
