import pytest
import numpy as np
import cv2
import sqlite3
import threading
import time
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

# ── Image generators ──────────────────────────────────────────

@pytest.fixture
def white_image():
    """Clean 400x100 white image with black text."""
    img = np.ones((100, 400, 3), dtype=np.uint8) * 255
    cv2.putText(img, "Hello World", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 2)
    return img

@pytest.fixture
def dark_mode_image():
    """Dark background white text — simulates dark terminal."""
    img = np.ones((100, 400, 3), dtype=np.uint8) * 30
    cv2.putText(img, "Hello World", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (240, 240, 240), 2)
    return img

@pytest.fixture
def low_contrast_image():
    """Light gray text on white — low std deviation."""
    img = np.ones((100, 400, 3), dtype=np.uint8) * 255
    cv2.putText(img, "Hello World", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (200, 200, 200), 2)
    return img

@pytest.fixture
def small_image():
    """Sub-300px image — should trigger upscaling."""
    img = np.ones((40, 200, 3), dtype=np.uint8) * 255
    cv2.putText(img, "Hi", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 1)
    return img

@pytest.fixture
def thin_capture_image():
    """5000x80 thin horizontal capture — pathological case."""
    img = np.ones((80, 5000, 3), dtype=np.uint8) * 255
    cv2.putText(img, "Thin line of text across a very wide capture",
                (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    return img

@pytest.fixture
def rgba_image():
    """4-channel RGBA image from portal screenshot."""
    img = np.ones((100, 400, 4), dtype=np.uint8) * 255
    img[:, :, 3] = 255  # full alpha
    cv2.putText(img, "RGBA test", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0, 255), 2)
    return img

@pytest.fixture
def multi_paragraph_image():
    """Image with two clear paragraphs."""
    img = np.ones((250, 500, 3), dtype=np.uint8) * 255
    cv2.putText(img, "First paragraph text", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    cv2.putText(img, "Second paragraph text", (10, 180),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    return img

@pytest.fixture
def skewed_image(white_image):
    """Rotated 5 degrees to test deskew."""
    h, w = white_image.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), 5, 1.0)
    return cv2.warpAffine(white_image, M, (w, h),
                          borderValue=(255, 255, 255))

@pytest.fixture
def memory_db(tmp_path):
    """Real SQLite DB in temp dir."""
    from spider.storage.db import DatabaseManager
    db = DatabaseManager(db_path=str(tmp_path / "test.db"))
    yield db
    db.close()

@pytest.fixture
def mock_ocr_result():
    from spider.core.models import OCRResult
    return OCRResult(
        text="Hello World",
        confidence=0.92,
        engine_used="mock",
        timestamp=time.time(),
        language="eng"
    )

@pytest.fixture
def mock_engine(mock_ocr_result):
    from spider.ocr.engine import OcrEngine
    engine = Mock(spec=OcrEngine)
    engine.recognize.return_value = mock_ocr_result
    engine.load_model.return_value = True
    return engine
