import difflib
import io
import shutil
import subprocess

import cv2
import numpy as np
import pytest

pytestmark = pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract not installed")

PARAGRAPHS = (
    "Optical character recognition converts images of typed or printed text\n"
    "into machine-encoded text, from a scanned document or a photo.\n"
    "\n"
    "Widely used as a form of data entry from printed paper data records,\n"
    "it is a common method of digitizing printed texts."
)
CODE = (
    "def search_history(self, query):\n"
    "    terms = query.split()\n"
    "    if not terms:\n"
    "        return self.get_history()"
)


def font_file(pattern):
    try:
        path = subprocess.run(["fc-match", "-f", "%{file}", pattern], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return path if path.endswith((".ttf", ".otf")) else None


def render(text, font_pattern, size, fg, bg):
    from PIL import Image, ImageDraw, ImageFont
    path = font_file(font_pattern)
    if not path:
        pytest.skip(f"No font for {font_pattern}")
    font = ImageFont.truetype(path, size)
    spacing = round(size * 0.45)
    left, top, right, bottom = ImageDraw.Draw(Image.new("RGB", (1, 1))).multiline_textbbox((0, 0), text, font=font, spacing=spacing)
    margin = max(12, size)
    img = Image.new("RGB", (right - left + 2 * margin, bottom - top + 2 * margin), bg)
    ImageDraw.Draw(img).multiline_text((margin - left, margin - top), text, font=font, fill=fg, spacing=spacing)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def ocr(png):
    from spider.vision.preprocessor import Preprocessor
    from spider.ocr.tesseract import TesseractEngine
    engine = TesseractEngine()
    assert engine.load_model("eng")
    return engine.recognize(Preprocessor.process_image(png)).text


def accuracy(expected, actual):
    return difflib.SequenceMatcher(None, " ".join(expected.split()), " ".join(actual.split())).ratio()


@pytest.mark.parametrize("name, text, font, size, fg, bg", [
    ("ui-light", "Settings Wi-Fi Bluetooth Displays Sound", "sans-serif", 13, (30, 30, 30), (250, 250, 250)),
    ("ui-dark", "Settings Wi-Fi Bluetooth Displays Sound", "sans-serif", 13, (255, 255, 255), (36, 36, 36)),
    ("white-on-blue-button", "Download Update", "sans-serif:bold", 14, (255, 255, 255), (53, 132, 228)),
    ("red-error", "Error: the file could not be saved", "sans-serif", 13, (224, 27, 36), (255, 255, 255)),
    ("dim-caption-dark", "Last updated 5 minutes ago", "sans-serif", 11, (160, 160, 160), (30, 30, 30)),
    ("invoice-symbols", "Invoice #4821 Due: 2026-09-30\nTotal: $1,249.00 (VAT 20%)\nbilling@example.com", "sans-serif", 14, (0, 0, 0), (255, 255, 255)),
])
def test_screen_text_accuracy(name, text, font, size, fg, bg):
    result = ocr(render(text, font, size, fg, bg))
    assert accuracy(text, result) >= 0.97, f"{name}: {result!r}"


def test_paragraph_breaks_preserved():
    result = ocr(render(PARAGRAPHS, "sans-serif", 14, (40, 40, 40), (255, 255, 255)))
    assert accuracy(PARAGRAPHS, result) >= 0.97, result
    assert result.count("\n\n") == 1, repr(result)
    assert len([l for l in result.split("\n") if l.strip()]) == 4, repr(result)


def test_code_indentation_preserved():
    result = ocr(render(CODE, "monospace", 13, (212, 212, 212), (30, 30, 30)))
    indents = [len(line) - len(line.lstrip()) for line in result.split("\n") if line.strip()]
    assert indents == [0, 4, 4, 8], repr(result)


def test_jpeg_photo_of_text():
    png = render(PARAGRAPHS, "sans-serif", 15, (30, 30, 30), (240, 240, 240))
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    jpeg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 35])[1].tobytes()
    assert accuracy(PARAGRAPHS, ocr(jpeg)) >= 0.97


def test_noisy_skewed_scan():
    png = render(PARAGRAPHS, "serif", 18, (20, 20, 20), (240, 238, 230))
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    img = cv2.copyMakeBorder(img, 60, 60, 60, 60, cv2.BORDER_CONSTANT, value=(240, 238, 230))
    h, w = img.shape[:2]
    img = cv2.warpAffine(img, cv2.getRotationMatrix2D((w / 2, h / 2), 3, 1.0), (w, h), borderValue=(240, 238, 230))
    rng = np.random.default_rng(7)
    img = np.clip(img.astype(np.int16) + rng.normal(0, 18, img.shape), 0, 255).astype(np.uint8)
    assert accuracy(PARAGRAPHS, ocr(cv2.imencode(".png", img)[1].tobytes())) >= 0.95


def test_blank_image_gives_no_text():
    blank = cv2.imencode(".png", np.full((200, 400, 3), 255, np.uint8))[1].tobytes()
    assert ocr(blank).strip() == ""
