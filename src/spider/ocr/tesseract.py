import time
import logging

logger = logging.getLogger(__name__)

from spider.ocr.engine import OcrEngine
from spider.core.models import OCRResult

class TesseractEngine(OcrEngine):
    def __init__(self):
        self.lang = "eng"

    def load_model(self, lang: str) -> bool:
        logger.info("OCR: Loading language model '%s'", lang)
        self.lang = lang
        return True

    def recognize(self, image) -> OCRResult:
        import pytesseract
        from PIL import Image
        import numpy as np

        logger.info("OCR: Starting Tesseract recognition")
        start_time = time.time()

        if len(image.shape) == 2:
            pil_img = Image.fromarray(image, 'L')
        else:
            pil_img = Image.fromarray(image[:, :, ::-1])

        psm_mode = 3
        logger.info("OCR: Configuration - PSM %d, Lang '%s'", psm_mode, self.lang)

        try:
            data = pytesseract.image_to_data(
                pil_img,
                lang=self.lang,
                config=f'--psm {psm_mode}',
                timeout=30,
                output_type=pytesseract.Output.DICT
            )
        except Exception as e:
            logger.error("OCR: Tesseract failed: %s", e)
            raise

        conf_list = [int(c) for c in data['conf'] if int(c) != -1]
        avg_conf = (sum(conf_list) / len(conf_list)) / 100.0 if conf_list else 0.0

        words = [
            data['text'][i]
            for i in range(len(data['text']))
            if int(data['conf'][i]) > 0 and data['text'][i].strip()
        ]
        text = " ".join(words)

        elapsed = time.time() - start_time
        logger.info("OCR: Finished in %.2fs", elapsed)
        logger.info("OCR: Detected %d words with %.2f%% average confidence", len(words), avg_conf * 100)

        if not text.strip():
            logger.warning("OCR: No text was detected")

        return OCRResult(
            text=text.strip(),
            confidence=avg_conf,
            engine_used="tesseract",
            timestamp=start_time,
            language=self.lang
        )
