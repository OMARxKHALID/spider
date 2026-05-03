from .engine import OcrEngine
from spider.core.models import OCRResult
import time

class PaddleEngine(OcrEngine):
    def load_model(self, lang: str) -> bool:
        return True

    def recognize(self, image) -> OCRResult:
        return OCRResult(
            text="PaddleOCR stub result",
            confidence=0.9,
            engine_used="paddleocr",
            timestamp=time.time()
        )
