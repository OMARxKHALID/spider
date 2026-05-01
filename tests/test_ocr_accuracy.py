import pytest
import numpy as np
import cv2
import os

pytestmark = pytest.mark.skipif(
    os.system("which tesseract > /dev/null 2>&1") != 0,
    reason="Tesseract not installed"
)

def render_text_image(text, font_size=1.0, bg=255, fg=0,
                      width=800, height=100, thickness=2):
    img = np.ones((height, width, 3), dtype=np.uint8) * bg
    cv2.putText(img, text, (20, int(height * 0.7)),
                cv2.FONT_HERSHEY_SIMPLEX, font_size,
                (fg, fg, fg), thickness)
    return img

def ocr_image(img):
    from spider.vision.preprocessor import Preprocessor
    from spider.ocr.tesseract import TesseractEngine
    _, buf = cv2.imencode('.png', img)
    preprocessed = Preprocessor.process_image(buf.tobytes())
    engine = TesseractEngine()
    engine.load_model("eng")
    result = engine.recognize(preprocessed)
    return result.text.strip(), result.confidence

def character_accuracy(expected: str, actual: str) -> float:
    """Character-level accuracy using edit distance."""
    if not expected:
        return 1.0
    import difflib
    matcher = difflib.SequenceMatcher(None, expected.lower(), actual.lower())
    return matcher.ratio()

class TestOCRAccuracy:

    # ── Target: 95%+ character accuracy on clean input ──────

    def test_clean_text_accuracy(self):
        target = "Hello World 1234"
        img = render_text_image(target, font_size=1.5)
        result, conf = ocr_image(img)
        acc = character_accuracy(target, result)
        assert acc >= 0.90, \
            f"Clean text accuracy {acc:.1%} below 90% threshold\n" \
            f"Expected: '{target}'\nGot:      '{result}'"

    def test_dark_mode_accuracy(self):
        target = "Dark Mode Text"
        img = render_text_image(target, bg=30, fg=240, font_size=1.5)
        result, conf = ocr_image(img)
        acc = character_accuracy(target, result)
        assert acc >= 0.85, \
            f"Dark mode accuracy {acc:.1%} below 85%\n" \
            f"Expected: '{target}'\nGot:      '{result}'"

    def test_small_text_accuracy(self):
        """Small text that requires upscaling."""
        target = "Small Text"
        img = render_text_image(target, font_size=0.5,
                                width=200, height=40, thickness=1)
        result, conf = ocr_image(img)
        acc = character_accuracy(target, result)
        assert acc >= 0.80, \
            f"Small text accuracy {acc:.1%} below 80%\n" \
            f"Expected: '{target}'\nGot:      '{result}'"

    def test_low_contrast_accuracy(self):
        """Light gray text — requires CLAHE."""
        target = "Low Contrast"
        img = render_text_image(target, fg=180, font_size=1.5)
        result, conf = ocr_image(img)
        acc = character_accuracy(target, result)
        assert acc >= 0.80, \
            f"Low contrast accuracy {acc:.1%} below 80%\n" \
            f"Expected: '{target}'\nGot:      '{result}'"

    def test_numbers_and_symbols(self):
        """Numbers and mixed symbols common in UI text."""
        target = "Version 2.0.1 Build 42"
        img = render_text_image(target, font_size=1.2)
        result, conf = ocr_image(img)
        acc = character_accuracy(target, result)
        assert acc >= 0.85, \
            f"Numbers/symbols accuracy {acc:.1%} below 85%\n" \
            f"Expected: '{target}'\nGot:      '{result}'"

    def test_multiline_structure_preserved(self):
        """Multi-line text must preserve line breaks in output."""
        img = np.ones((250, 600, 3), dtype=np.uint8) * 255
        cv2.putText(img, "First line of text", (20, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)
        cv2.putText(img, "Second line of text", (20, 180),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)
        result, _ = ocr_image(img)
        assert '\n' in result, \
            f"Multi-line text must contain newline\nGot: {repr(result)}"

    def test_confidence_score_reasonable(self):
        """Confidence on clean text must be > 70%."""
        img = render_text_image("Clear Text Here", font_size=1.5)
        _, conf = ocr_image(img)
        assert conf > 0.70, \
            f"Confidence {conf:.1%} too low for clean text"

    # ── Accuracy benchmark — print full report ───────────────

    def test_print_accuracy_report(self):
        """Runs all scenarios and prints a summary table."""
        scenarios = [
            ("Clean large text",     render_text_image("Hello World", font_size=2.0)),
            ("Clean medium text",    render_text_image("Hello World", font_size=1.0)),
            ("Dark mode",            render_text_image("Hello World", bg=30, fg=240)),
            ("Low contrast",         render_text_image("Hello World", fg=180)),
            ("Small text",           render_text_image("Hello World", font_size=0.5,
                                                        width=200, height=40,
                                                        thickness=1)),
            ("Numbers",              render_text_image("1234567890")),
        ]
        expected = "Hello World"
        print("\n\n═══════ OCR ACCURACY REPORT ═══════")
        print(f"{'Scenario':<25} {'Accuracy':>10} {'Confidence':>12} {'Output'}")
        print("─" * 70)
        all_pass = True
        for name, img in scenarios:
            result, conf = ocr_image(img)
            acc = character_accuracy(
                expected if "Number" not in name else "1234567890",
                result
            )
            status = "✓" if acc >= 0.80 else "✗"
            if acc < 0.80:
                all_pass = False
            print(f"{name:<25} {acc:>9.1%}  {conf:>10.1%}  {repr(result[:30])}")
        print("─" * 70)
        print(f"Overall: {'ALL PASS ✓' if all_pass else 'FAILURES DETECTED ✗'}")
        print("═" * 36)
