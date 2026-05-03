from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from spider.core.models import OCRResult

@dataclass
class EngineCapabilities:
    supports_confidence: bool = True
    supports_layout: bool = True
    supports_bounding_boxes: bool = False
    max_image_bytes: int | None = None
    needs_internet: bool = False

class OcrEngine(ABC):
    @abstractmethod
    def load_model(self, lang: str) -> bool:
        ...

    @abstractmethod
    def recognize(self, image) -> OCRResult:
        ...

    def configure(self, config: dict[str, Any]) -> None:
        pass

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities()

    def health_check(self) -> tuple[bool, str]:
        return True, ""
