from abc import ABC, abstractmethod
from spider.core.models import OCRResult

class OcrEngine(ABC):
    @abstractmethod
    def load_model(self, lang: str) -> bool:
        ...
        
    @abstractmethod
    def recognize(self, image) -> OCRResult:
        ...
