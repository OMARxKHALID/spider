import concurrent.futures
import logging
from .engine import OcrEngine
from spider.core.models import OCRResult

logger = logging.getLogger(__name__)

class EnsembleEngine(OcrEngine):
    def __init__(self, engines: list[OcrEngine], strategy: str = "highest_confidence"):
        self.engines = engines
        self.strategy = strategy

    def load_model(self, lang: str) -> bool:
        results = [e.load_model(lang) for e in self.engines]
        return any(results)

    def recognize(self, image) -> OCRResult:
        results = []
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {executor.submit(e.recognize, image): e for e in self.engines}
            for future in concurrent.futures.as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:
                    engine = futures[future]
                    logger.warning("Ensemble: engine %s failed: %s", engine.__class__.__name__, exc)

        if not results:
            raise RuntimeError("All ensemble engines failed")

        if self.strategy == "highest_confidence":
            return max(results, key=lambda r: r.confidence)

        raise ValueError(f"Unknown ensemble strategy: {self.strategy}")
