from dataclasses import dataclass, field
from typing import Optional

@dataclass
class OCRResult:
    text: str
    confidence: float
    engine_used: str
    timestamp: float
    language: str = "eng"
    image_bytes: Optional[bytes] = field(default=None, repr=False)
