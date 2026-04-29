from typing import Protocol
from spider.core.models import OCRResult

class OcrEngine(Protocol):
    def load_model(self, lang: str) -> bool:
        ...
        
    def recognize(self, image) -> OCRResult:
        ...
