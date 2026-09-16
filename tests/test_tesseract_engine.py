import shutil
from unittest.mock import patch

import numpy as np
import pytest

from spider.core.exceptions import EngineError, ImageDecodeError
from spider.ocr.tesseract import TesseractEngine, build_text, image_to_data, missing_languages, run_tesseract

needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract not installed")


def make_data(texts, lines, confs=None, blocks=None, pars=None, lefts=None, tops=None, widths=None):
    n = len(texts)
    return {
        "text": texts,
        "conf": [str(c) for c in (confs or [90] * n)],
        "block_num": blocks or [1] * n,
        "par_num": pars or [1] * n,
        "line_num": lines,
        "left": lefts or [10 + 60 * i for i in range(n)],
        "top": tops or [10 + 30 * (line - 1) for line in lines],
        "width": widths or [10 * max(1, len(t)) for t in texts],
        "height": [20] * n,
    }


def recognize_with(data, image=None):
    with patch("spider.ocr.tesseract.image_to_data", return_value=data) as mocked:
        result = TesseractEngine().recognize(np.zeros((10, 10), np.uint8) if image is None else image)
    return result, mocked


class TestLayout:

    def test_words_on_one_line_joined(self):
        assert build_text(make_data(["Hello", "World"], [1, 1]))[0] == "Hello World"

    def test_lines_separated_by_newline(self):
        data = make_data(["Line", "one", "Line", "two"], [1, 1, 2, 2], lefts=[10, 60, 10, 60])
        assert build_text(data)[0] == "Line one\nLine two"

    def test_large_vertical_gap_is_paragraph_break(self):
        data = make_data(["First", "Second"], [1, 1], pars=[1, 2], lefts=[10, 10], tops=[10, 80])
        assert build_text(data)[0] == "First\n\nSecond"

    def test_tesseract_paragraph_ids_without_gap_stay_single_lines(self):
        data = make_data(["Invoice", "Total"], [1, 1], pars=[1, 2], lefts=[10, 10], tops=[10, 38])
        assert build_text(data)[0] == "Invoice\nTotal"

    def test_indentation_from_word_positions(self):
        data = make_data(["def", "run():", "return", "value"], [1, 1, 2, 2], lefts=[10, 50, 50, 120], tops=[10, 10, 38, 38])
        assert build_text(data)[0] == "def run():\n    return value"

    def test_small_left_offsets_do_not_indent_prose(self):
        data = make_data(["Hello", "world"], [1, 2], lefts=[10, 17], tops=[10, 38])
        assert build_text(data)[0] == "Hello\nworld"

    def test_centered_lines_not_indented(self):
        data = make_data(
            ["Discard", "changes?", "Unsaved", "edits", "will", "be", "lost"], [1, 1, 2, 2, 2, 2, 2],
            lefts=[90, 170, 20, 100, 160, 210, 240], tops=[10, 10, 38, 38, 38, 38, 38],
            widths=[70, 80, 70, 50, 40, 20, 40],
        )
        assert build_text(data)[0] == "Discard changes?\nUnsaved edits will be lost"

    def test_zero_and_negative_confidence_excluded(self):
        data = make_data(["", "Good", "noise", "text"], [1, 1, 1, 1], confs=[-1, 90, 0, 88])
        text, confidences = build_text(data)
        assert text == "Good text" and confidences == [90.0, 88.0]

    def test_empty_data(self):
        assert build_text({}) == ("", [])


class TestEngine:

    def test_confidence_is_average_of_kept_words(self):
        result, _ = recognize_with(make_data(["", "Hello", ""], [1, 1, 1], confs=[-1, 90, -1]))
        assert result.text == "Hello" and abs(result.confidence - 0.90) < 0.001

    def test_user_psm_passed_through_unchanged(self):
        engine = TesseractEngine()
        engine.configure({"psm": 6})
        with patch("spider.ocr.tesseract.image_to_data", return_value={}) as mocked:
            engine.recognize(np.zeros((10, 500), np.uint8))
        assert mocked.call_args.args[2] == 6

    def test_empty_image_rejected(self):
        with pytest.raises(ImageDecodeError):
            TesseractEngine().recognize(b"not an image")
        with pytest.raises(ImageDecodeError):
            TesseractEngine().recognize(np.zeros((0, 0), np.uint8))

    def test_missing_binary_reports_engine_error(self):
        with patch("spider.ocr.tesseract.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(EngineError, match="not installed"):
                run_tesseract(["--version"])

    def test_launch_failure_reports_engine_error(self):
        with patch("spider.ocr.tesseract.subprocess.run", side_effect=PermissionError(13, "Permission denied")):
            with pytest.raises(EngineError, match="Could not run Tesseract: Permission denied"):
                run_tesseract(["--version"])

    def test_timeout_reports_engine_error(self):
        import subprocess
        with patch("spider.ocr.tesseract.subprocess.run", side_effect=subprocess.TimeoutExpired("tesseract", 30)):
            with pytest.raises(EngineError, match="too long"):
                run_tesseract(["stdin", "stdout"])

    def test_failure_reports_last_stderr_line(self):
        import subprocess
        failed = subprocess.CompletedProcess([], 1, b"", b"Warning\nError opening data file zzz.traineddata\n")
        with patch("spider.ocr.tesseract.subprocess.run", return_value=failed):
            with pytest.raises(EngineError, match="Error opening data file zzz.traineddata"):
                run_tesseract(["stdin", "stdout"])

    @needs_tesseract
    def test_missing_language_rejected(self):
        engine = TesseractEngine()
        assert engine.load_model("eng")
        assert not engine.load_model("eng+zzz")
        assert missing_languages("eng+zzz") == ["zzz"]

    @needs_tesseract
    def test_real_tsv_parsing(self):
        import cv2
        img = np.full((80, 400), 255, np.uint8)
        cv2.putText(img, "Hello World", (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 1.5, 0, 3)
        data = image_to_data(img, "eng", 7)
        assert {"text", "conf", "left", "top", "width", "height"} <= data.keys()
        assert isinstance(data["left"][0], int)
        assert "Hello" in build_text(data)[0]
