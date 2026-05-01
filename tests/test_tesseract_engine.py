import pytest
import numpy as np
import cv2
from unittest.mock import patch, MagicMock

class TestTesseractEngine:

    def _make_mock_data(self, texts, confs, blocks, pars, lines):
        return {
            'text': texts,
            'conf': [str(c) for c in confs],
            'block_num': blocks,
            'par_num': pars,
            'line_num': lines,
        }

    # ── Text structure reconstruction ───────────────────────

    def test_single_line_reconstructed(self):
        data = self._make_mock_data(
            texts=['Hello', 'World'],
            confs=[90, 90],
            blocks=[1, 1],
            pars=[1, 1],
            lines=[1, 1]
        )
        with patch('pytesseract.image_to_data', return_value=data):
            from spider.ocr.tesseract import TesseractEngine
            # Engine needs a mock image for the test, but we are patching image_to_data
            engine = TesseractEngine()
            # To test reconstruction logic easily, we can just run recognize with dummy image
            # Wait, recognize does the reconstruction inside it. Let's just pass dummy image.
            dummy_image = np.zeros((10, 10), dtype=np.uint8)
            result = engine.recognize(dummy_image)
            # block 1, par 1, line 1 has both 'Hello' and 'World'. They should be joined by space.
            assert result.text == "Hello World"

    def test_two_lines_have_newline(self):
        data = self._make_mock_data(
            texts=['Line', 'one', 'Line', 'two'],
            confs=[90, 90, 90, 90],
            blocks=[1, 1, 1, 1],
            pars=[1, 1, 1, 1],
            lines=[1, 1, 2, 2]
        )
        with patch('pytesseract.image_to_data', return_value=data):
            from spider.ocr.tesseract import TesseractEngine
            engine = TesseractEngine()
            result = engine.recognize(np.zeros((10, 10), dtype=np.uint8))
            assert '\n' in result.text, "Two lines must be separated by newline"
            assert 'Line one' in result.text
            assert 'Line two' in result.text

    def test_two_paragraphs_have_double_newline(self):
        data = self._make_mock_data(
            texts=['First', 'paragraph', 'Second', 'paragraph'],
            confs=[90, 90, 90, 90],
            blocks=[1, 1, 1, 1],
            pars=[1, 1, 2, 2],
            lines=[1, 1, 1, 1]
        )
        with patch('pytesseract.image_to_data', return_value=data):
            from spider.ocr.tesseract import TesseractEngine
            engine = TesseractEngine()
            result = engine.recognize(np.zeros((10, 10), dtype=np.uint8))
            assert '\n\n' in result.text, \
                "Two paragraphs must be separated by double newline"

    def test_empty_data_returns_empty_string(self):
        data = self._make_mock_data([], [], [], [], [])
        with patch('pytesseract.image_to_data', return_value=data):
            from spider.ocr.tesseract import TesseractEngine
            engine = TesseractEngine()
            result = engine.recognize(np.zeros((10, 10), dtype=np.uint8))
            assert result.text == "", "Empty input must return empty string"

    def test_low_confidence_words_excluded(self):
        data = self._make_mock_data(
            texts=['Good', 'bad_noise', 'text'],
            confs=[90, 0, 88], # if confidence is > 0 it includes it
            blocks=[1, 1, 1],
            pars=[1, 1, 1],
            lines=[1, 1, 1]
        )
        with patch('pytesseract.image_to_data', return_value=data):
            from spider.ocr.tesseract import TesseractEngine
            engine = TesseractEngine()
            result = engine.recognize(np.zeros((10, 10), dtype=np.uint8))
            assert 'bad_noise' not in result.text, \
                "Low/Zero confidence words must be excluded"

    # ── Config ──────────────────────────────────────────────

    def test_config_contains_oem1(self):
        from spider.ocr import tesseract as t_module
        import inspect
        source = inspect.getsource(t_module)
        assert '--oem 1' in source, "Tesseract config must include --oem 1"

    def test_config_contains_preserve_interword_spaces(self):
        from spider.ocr import tesseract as t_module
        import inspect
        source = inspect.getsource(t_module)
        assert 'preserve_interword_spaces' in source, \
            "Tesseract config must preserve interword spaces"

    # ── Confidence calculation ──────────────────────────────

    def test_confidence_excludes_negative_one(self):
        """conf=-1 means no word — must be excluded from average."""
        data = self._make_mock_data(
            texts=['', 'Hello', ''],
            confs=[-1, 90, -1],
            blocks=[1, 1, 1],
            pars=[1, 1, 1],
            lines=[1, 1, 1]
        )
        with patch('pytesseract.image_to_data', return_value=data):
            from spider.ocr.tesseract import TesseractEngine
            engine = TesseractEngine()
            result = engine.recognize(np.zeros((10, 10), dtype=np.uint8))
            # The average confidence must be 90, not (90 + -1 + -1) / 3 = 29
            # The confidence calculation in tesseract.py:
            # avg_conf = sum / len / 100.0
            assert abs(result.confidence - 0.90) < 0.01, \
                f"Confidence average wrong: {result.confidence} (should be 0.90)"
