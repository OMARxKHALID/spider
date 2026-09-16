import datetime

from spider.ui import day_heading, one_line, word_count


def test_day_heading():
    today = datetime.date(2026, 9, 16)
    ts = lambda d: datetime.datetime.combine(d, datetime.time(12)).timestamp()
    assert day_heading(ts(today), today) == "Today"
    assert day_heading(ts(today - datetime.timedelta(days=1)), today) == "Yesterday"
    assert day_heading(ts(datetime.date(2026, 9, 12)), today) == "Saturday"
    assert day_heading(ts(datetime.date(2026, 3, 5)), today) == "March 5"
    assert day_heading(ts(datetime.date(2025, 3, 5)), today) == "March 5, 2025"


def test_one_line_preview_is_single_line_and_bounded():
    text = "Invoice #1\n\n  Total:\t$5  " + "x" * 1000
    preview = one_line(text)
    assert "\n" not in preview and "\t" not in preview and "  " not in preview
    assert len(preview) == 160


def test_word_count_plural():
    assert word_count("hello") == "1 word"
    assert word_count("hello there") == "2 words"
