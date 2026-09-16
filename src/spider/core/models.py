from dataclasses import dataclass


@dataclass
class OCRResult:
    text: str
    confidence: float
    engine_used: str
    timestamp: float
    language: str = "eng"
