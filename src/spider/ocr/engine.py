from abc import ABC, abstractmethod
from typing import Any
from spider.core.models import OCRResult


class OcrEngine(ABC):
    @abstractmethod
    def load_model(self, lang: str) -> bool:
        ...

    @abstractmethod
    def recognize(self, image) -> OCRResult:
        ...

    def configure(self, config: dict[str, Any]) -> None:
        pass
