import time
import logging
from typing import Any

logger = logging.getLogger(__name__)

from spider.ocr.engine import OcrEngine
from spider.core.models import OCRResult

class TesseractEngine(OcrEngine):
    def __init__(self):
        self.lang = "eng"
        self.psm = 3

    def load_model(self, lang: str) -> bool:
        logger.info("OCR: Loading language model '%s'", lang)
        self.lang = lang
        return True

    def configure(self, config: dict[str, Any]) -> None:
        if "psm" in config:
            self.psm = config["psm"]

    def recognize(self, image) -> OCRResult:
        import pytesseract
        from PIL import Image
        import numpy as np

        logger.info("OCR: Starting Tesseract recognition (PSM %d)", self.psm)
        start_time = time.time()

        if len(image.shape) == 2:
            pil_img = Image.fromarray(image, 'L')
        else:
            pil_img = Image.fromarray(image[:, :, ::-1])

        config = f'--oem 1 --psm {self.psm} -c preserve_interword_spaces=1'
        logger.info("OCR: Configuration - %s, Lang '%s'", config, self.lang)

        try:
            data = pytesseract.image_to_data(
                pil_img,
                lang=self.lang,
                config=config,
                timeout=30,
                output_type=pytesseract.Output.DICT
            )
        except Exception as e:
            logger.error("OCR: Tesseract failed: %s", e)
            raise

        conf_list = [int(v) for v in data['conf'] if int(v) != -1]
        avg_conf = (sum(conf_list) / len(conf_list)) / 100.0 if conf_list else 0.0

        lines = {}
        for i in range(len(data['text'])):
            conf = int(data['conf'][i])
            word = data['text'][i]
            if conf > 0 and word.strip():
                key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
                lines.setdefault(key, []).append(word)

        paragraphs = {}
        for (block, par, line), words in sorted(lines.items()):
            paragraphs.setdefault((block, par), []).append(" ".join(words))

        text = "\n\n".join(
            "\n".join(par_lines)
            for _, par_lines in sorted(paragraphs.items())
        ).strip()

        word_count = sum(len(ws) for ws in lines.values())
        elapsed = time.time() - start_time
        logger.info("OCR: Finished in %.2fs", elapsed)
        logger.info("OCR: Detected %d words with %.2f%% average confidence", word_count, avg_conf * 100)

        if not text:
            logger.warning("OCR: No text was detected")

        return OCRResult(
            text=text,
            confidence=avg_conf,
            engine_used="tesseract",
            timestamp=start_time,
            language=self.lang
        )
