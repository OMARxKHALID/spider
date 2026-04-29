import time
import pytesseract
from PIL import Image
import numpy as np
import logging

logger = logging.getLogger(__name__)

from spider.ocr.engine import OcrEngine
from spider.core.models import OCRResult

# NOTE: pytesseract wraps the Tesseract CLI as a subprocess.
# For production, replace with tesserocr (C-binding) to avoid the subprocess
# overhead on every call. pytesseract is used here for ease of setup.

class TesseractEngine(OcrEngine):
    def __init__(self):
        self.lang = "eng"
        self.is_loaded = False

    def load_model(self, lang: str) -> bool:
        logger.info("Loading Tesseract model for language: %s", lang)
        self.lang = lang
        self.is_loaded = True
        return True

    def recognize(self, image: np.ndarray) -> OCRResult:
        start_time = time.time()

        # Convert OpenCV array (BGR or Grayscale) to PIL Image
        if len(image.shape) == 2:
            pil_img = Image.fromarray(image, 'L')
        else:
            pil_img = Image.fromarray(image[:, :, ::-1])  # BGR → RGB

        # Single tesseract call — get both text and confidence from image_to_data.
        # Previously the code called image_to_data AND image_to_string separately,
        # which ran the tesseract subprocess twice. This is fixed here.
        data = pytesseract.image_to_data(
            pil_img, lang=self.lang, output_type=pytesseract.Output.DICT
        )

        conf_list = [int(c) for c in data['conf'] if int(c) != -1]
        avg_conf = (sum(conf_list) / len(conf_list)) / 100.0 if conf_list else 0.0

        words = [
            data['text'][i]
            for i in range(len(data['text']))
            if int(data['conf'][i]) > 0 and data['text'][i].strip()
        ]
        text = " ".join(words)

        logger.info("[Phase 4/5] Recognition: OCR complete in %.2fs (Words: %d, Confidence: %.2f)", 
                    time.time() - start_time, len(words), avg_conf)

        return OCRResult(
            text=text.strip(),
            confidence=avg_conf,
            engine_used="tesseract",
            timestamp=start_time,
            language=self.lang
        )
