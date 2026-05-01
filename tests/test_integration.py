import pytest
import numpy as np
import cv2
import os
import time

@pytest.mark.skipif(
    os.system("which tesseract > /dev/null 2>&1") != 0,
    reason="Tesseract not installed"
)
class TestFullPipeline:

    def test_full_pipeline_preprocess_to_text(self, tmp_path):
        """Preprocessor → Tesseract → text output end to end."""
        from spider.vision.preprocessor import Preprocessor
        from spider.ocr.tesseract import TesseractEngine

        img = np.ones((150, 600, 3), dtype=np.uint8) * 255
        cv2.putText(img, "Integration Test", (20, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 0), 3)
        _, buf = cv2.imencode('.png', img)

        preprocessed = Preprocessor.process_image(buf.tobytes())
        assert preprocessed is not None, "Preprocessor returned None"

        engine = TesseractEngine()
        engine.load_model("eng")
        result = engine.recognize(preprocessed)

        assert result is not None
        assert result.text is not None
        assert len(result.text.strip()) > 0, \
            "Pipeline produced empty text"
        assert result.confidence > 0, \
            "Pipeline produced zero confidence"

    def test_pipeline_result_saved_to_db(self, tmp_path):
        """Full pipeline result must be persistable to DB."""
        from spider.storage.db import DatabaseManager
        from spider.core.models import OCRResult
        import time

        db = DatabaseManager(db_path=str(tmp_path / "integration.db"))

        result = OCRResult(
            text="Test OCR Result",
            confidence=0.91,
            engine_used="tesseract",
            timestamp=time.time(),
            language="eng",
            image_bytes=b"fake_image_bytes"
        )

        db.save_result(result)
        items = db.get_history()

        assert len(items) == 1
        assert items[0]['text'] == "Test OCR Result"
        db.close()

    def test_pipeline_dark_mode_end_to_end(self):
        """Dark mode screenshot → readable text."""
        from spider.vision.preprocessor import Preprocessor
        from spider.ocr.tesseract import TesseractEngine

        img = np.ones((150, 600, 3), dtype=np.uint8) * 25
        cv2.putText(img, "Dark Mode OCR", (20, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 2.0, (230, 230, 230), 3)
        _, buf = cv2.imencode('.png', img)

        preprocessed = Preprocessor.process_image(buf.tobytes())

        engine = TesseractEngine()
        engine.load_model("eng")
        result = engine.recognize(preprocessed)

        assert len(result.text.strip()) > 0, \
            "Dark mode pipeline produced empty text"
