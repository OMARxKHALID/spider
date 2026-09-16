import datetime

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw


def icon_button(icon_name, label, on_clicked=None, action_name=None):
    button = Gtk.Button(icon_name=icon_name, tooltip_text=label, action_name=action_name)
    button.update_property([Gtk.AccessibleProperty.LABEL], [label])
    if on_clicked:
        button.connect("clicked", on_clicked)
    return button


def pill_button(label, icon_name, css_class=None, on_clicked=None, action_name=None):
    button = Gtk.Button(
        child=Adw.ButtonContent(label=label, icon_name=icon_name, use_underline=True),
        action_name=action_name,
        css_classes=["pill"] + ([css_class] if css_class else []),
    )
    if on_clicked:
        button.connect("clicked", on_clicked)
    return button


def one_line(text, limit=160):
    return " ".join(text.split())[:limit]


def word_count(text):
    count = len(text.split())
    return f"{count} word" if count == 1 else f"{count} words"


def day_heading(timestamp, today=None):
    day = datetime.date.fromtimestamp(timestamp)
    today = today or datetime.date.today()
    delta = (today - day).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Yesterday"
    if 1 < delta < 7:
        return day.strftime("%A")
    if day.year == today.year:
        return day.strftime("%B %-d")
    return day.strftime("%B %-d, %Y")


def clock_time(timestamp):
    return datetime.datetime.fromtimestamp(timestamp).strftime("%H:%M")
