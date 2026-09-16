import sqlite3

from spider.core.exceptions import CaptureError, EngineError, ImageDecodeError, describe_error


def test_describe_error_messages():
    assert describe_error(ImageDecodeError()) == "The file is not a supported image"
    assert describe_error(EngineError("Language data for “x” is not installed")) == "Language data for “x” is not installed"
    assert describe_error(CaptureError("io_failure", "Could not read the screenshot")) == "Could not read the screenshot"
    assert describe_error(FileNotFoundError(2, "No such file")) == "The image file no longer exists"
    assert describe_error(PermissionError(13, "Permission denied")) == "Permission denied while reading the image"
    assert describe_error(sqlite3.OperationalError("disk I/O error")) == "History database error: disk I/O error"
    assert describe_error(MemoryError()) == "The image is too large to process"
    assert describe_error(KeyError()) == "Unexpected error (KeyError)"


def test_long_messages_are_shortened_to_one_line():
    message = describe_error(EngineError("line one\nline two " + "x" * 500))
    assert "\n" not in message and len(message) <= 140 and message.endswith("…")
