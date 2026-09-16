from __future__ import annotations
import shutil
from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING
if TYPE_CHECKING:
    from .engine import OcrEngine


@dataclass
class EngineDescriptor:
    id: str
    display_name: str
    factory: Callable[[], "OcrEngine"]
    check_available: Callable[[], tuple[bool, str]]


DEFAULT_ENGINE = "tesseract"


class EngineRegistry:
    _engines: dict[str, EngineDescriptor] = {}

    @classmethod
    def register(cls, descriptor: EngineDescriptor):
        cls._engines[descriptor.id] = descriptor

    @classmethod
    def get(cls, engine_id: str) -> EngineDescriptor:
        return cls._engines.get(engine_id) or cls._engines[DEFAULT_ENGINE]


def _check_tesseract() -> tuple[bool, str]:
    if shutil.which("tesseract"):
        return True, ""
    return False, "tesseract binary not found — install tesseract-ocr"


def _tesseract_factory() -> "OcrEngine":
    from spider.ocr.tesseract import TesseractEngine
    return TesseractEngine()


EngineRegistry.register(EngineDescriptor(
    id="tesseract",
    display_name="Tesseract",
    factory=_tesseract_factory,
    check_available=_check_tesseract,
))
