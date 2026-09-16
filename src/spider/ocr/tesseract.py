import logging
import subprocess
import time
from typing import Any

import cv2

from spider.core.exceptions import EngineError, ImageDecodeError
from spider.core.models import OCRResult
from spider.ocr.engine import OcrEngine

logger = logging.getLogger(__name__)

TESSERACT_TIMEOUT_SECONDS = 30
TSV_INT_COLUMNS = ("block_num", "par_num", "line_num", "left", "top", "width", "height")


def run_tesseract(args, stdin=None, timeout=TESSERACT_TIMEOUT_SECONDS) -> str:
    try:
        process = subprocess.run(["tesseract", *args], input=stdin, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        raise EngineError("Tesseract is not installed. Install the tesseract-ocr package.")
    except subprocess.TimeoutExpired:
        raise EngineError("Text recognition took too long")
    except OSError as e:
        raise EngineError(f"Could not run Tesseract: {e.strerror or e}")
    if process.returncode != 0:
        details = [line for line in process.stderr.decode("utf-8", "replace").splitlines() if line.strip()]
        raise EngineError(f"Tesseract failed: {details[-1] if details else f'exit code {process.returncode}'}")
    return process.stdout.decode("utf-8", "replace")


def missing_languages(lang: str) -> list[str]:
    codes = [code for code in lang.split("+") if code]
    if not codes:
        return [lang]
    output = run_tesseract(["--list-langs"], timeout=10)
    installed = {line.strip() for line in output.splitlines() if line.strip() and " " not in line.strip()}
    return [code for code in codes if code not in installed]


def image_to_data(image, lang: str, psm: int) -> dict:
    ok, png = cv2.imencode(".png", image)
    if not ok:
        raise ImageDecodeError()
    output = run_tesseract(["stdin", "stdout", "-l", lang, "--oem", "1", "--psm", str(psm), "tsv"], stdin=png.tobytes())

    rows = [row for row in output.split("\n") if row]
    if not rows or not rows[0].startswith("level"):
        return {}
    header = rows[0].split("\t")
    data = {column: [] for column in header}
    for row in rows[1:]:
        values = row.split("\t", len(header) - 1)
        if len(values) != len(header):
            continue
        for column, value in zip(header, values):
            data[column].append(int(value) if column in TSV_INT_COLUMNS else value)
    return data


def build_text(data) -> tuple[str, list[float]]:
    lines = {}
    confidences = []
    for i, word in enumerate(data.get("text", [])):
        conf = float(data["conf"][i])
        word = word.strip()
        if conf <= 0 or not word:
            continue
        confidences.append(conf)
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        left, top, width = data["left"][i], data["top"][i], data["width"][i]
        line = lines.setdefault(key, {"block": key[0], "words": [], "left": left, "right": 0, "top": top, "bottom": 0})
        line["words"].append(word)
        line["left"] = min(line["left"], left)
        line["right"] = max(line["right"], left + width)
        line["top"] = min(line["top"], top)
        line["bottom"] = max(line["bottom"], top + data["height"][i])
        if len(word) >= 3:
            line.setdefault("char_widths", []).append(width / len(word))

    if not lines:
        return "", confidences

    ordered = [lines[key] for key in sorted(lines)]
    heights = sorted(line["bottom"] - line["top"] for line in ordered)
    line_height = heights[len(heights) // 2]
    char_widths = sorted(w for line in ordered for w in line.get("char_widths", []))
    char_width = char_widths[len(char_widths) // 2] if char_widths else line_height / 2

    blocks = {}
    for line in ordered:
        blocks.setdefault(line["block"], []).append(line)
    block_left = {}
    for block, block_lines in blocks.items():
        lefts = [line["left"] for line in block_lines]
        centers = [(line["left"] + line["right"]) / 2 for line in block_lines]
        centered = max(lefts) - min(lefts) > 2 * char_width and max(centers) - min(centers) <= 2 * char_width
        block_left[block] = None if centered else min(lefts)

    output = []
    previous = None
    for line in ordered:
        if previous is not None:
            gap = line["top"] - previous["bottom"]
            new_column = line["top"] < previous["top"]
            output.append("\n\n" if gap > line_height or new_column else "\n")
        base = block_left[line["block"]]
        indent = round((line["left"] - base) / char_width) if base is not None else 0
        output.append(" " * indent if indent >= 2 else "")
        output.append(" ".join(line["words"]))
        previous = line
    return "".join(output), confidences


class TesseractEngine(OcrEngine):
    def __init__(self):
        self.lang = "eng"
        self.psm = 3

    def load_model(self, lang: str) -> bool:
        logger.info("OCR: Loading language model '%s'", lang)
        missing = missing_languages(lang)
        if missing:
            logger.error("OCR: Missing Tesseract language data: %s", ", ".join(missing))
            return False
        self.lang = lang
        return True

    def configure(self, config: dict[str, Any]) -> None:
        if "psm" in config:
            self.psm = config["psm"]

    def recognize(self, image) -> OCRResult:
        if getattr(image, "size", 0) == 0:
            raise ImageDecodeError()

        start_time = time.time()
        logger.info("OCR: Starting Tesseract recognition (lang=%s, psm=%d)", self.lang, self.psm)
        text, confidences = build_text(image_to_data(image, self.lang, self.psm))
        avg_conf = sum(confidences) / len(confidences) / 100.0 if confidences else 0.0
        logger.info("OCR: %d words in %.2fs, %.1f%% average confidence", len(confidences), time.time() - start_time, avg_conf * 100)

        return OCRResult(
            text=text,
            confidence=avg_conf,
            engine_used="tesseract",
            timestamp=start_time,
            language=self.lang,
        )
