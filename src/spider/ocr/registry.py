from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING
if TYPE_CHECKING:
    from .engine import OcrEngine

@dataclass
class EngineDescriptor:
    id: str
    display_name: str
    description: str
    factory: Callable[[], "OcrEngine"]
    check_available: Callable[[], tuple[bool, str]]
    requires_api_key: bool = False
    supports_languages: list[str] = field(default_factory=list)

class EngineRegistry:
    _engines: dict[str, EngineDescriptor] = {}

    @classmethod
    def register(cls, descriptor: EngineDescriptor):
        cls._engines[descriptor.id] = descriptor

    @classmethod
    def get(cls, engine_id: str) -> EngineDescriptor:
        if engine_id not in cls._engines:
            raise KeyError(f"No engine registered with id '{engine_id}'")
        return cls._engines[engine_id]

    @classmethod
    def all(cls) -> list[EngineDescriptor]:
        return list(cls._engines.values())

    @classmethod
    def available(cls) -> list[EngineDescriptor]:
        return [d for d in cls._engines.values()
                if d.check_available()[0]]

def _check_tesseract() -> tuple[bool, str]:
    import shutil
    if shutil.which("tesseract"):
        return True, ""
    return False, "tesseract binary not found — install tesseract-ocr"

def _check_paddleocr() -> tuple[bool, str]:
    try:
        import paddleocr
        return True, ""
    except ImportError:
        return False, "PaddleOCR not installed"

EngineRegistry.register(EngineDescriptor(
    id="tesseract",
    display_name="Tesseract",
    description="Open-source OCR engine. Best for printed text.",
    factory=lambda: __import__(
        'spider.ocr.tesseract', fromlist=['TesseractEngine']
    ).TesseractEngine(),
    check_available=_check_tesseract,
    supports_languages=["eng", "ara", "fra", "deu", "chi_sim"],
))

EngineRegistry.register(EngineDescriptor(
    id="paddleocr",
    display_name="PaddleOCR",
    description="Deep learning OCR. Excellent for CJK and handwriting.",
    factory=lambda: __import__(
        'spider.ocr.paddle', fromlist=['PaddleEngine']
    ).PaddleEngine(),
    check_available=_check_paddleocr,
    supports_languages=["en", "ch", "japan", "korean"],
))

EngineRegistry.register(EngineDescriptor(
    id="google_vision",
    display_name="Google Cloud Vision",
    description="State-of-the-art cloud OCR. Requires API Key and Internet.",
    factory=lambda: [exec("try: from spider.ocr.google import GoogleVisionEngine\nexcept ImportError: raise RuntimeError('Google Vision module not found')"), GoogleVisionEngine()][-1],
    check_available=lambda: (False, "Not yet implemented"),
    requires_api_key=True,
))
