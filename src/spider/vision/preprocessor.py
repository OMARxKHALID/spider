import logging
import os

import cv2
import numpy as np

from spider.core.exceptions import ImageDecodeError

logger = logging.getLogger(__name__)

TARGET_CHAR_HEIGHT = 40
MAX_UPSCALE = 4.0
MAX_PIXELS = 40_000_000
MAX_SKEW_DEGREES = 10.0
SKEW_STEP_DEGREES = 0.5
BORDER = 16
MIN_SKEW_GAIN = 1.5
MIN_TEXT_FRACTION = 0.002


class Preprocessor:
    DEBUG_DIR = os.environ.get("SPIDER_DEBUG_PREPROCESS_DIR")

    @staticmethod
    def _debug_save(stage, image):
        if Preprocessor.DEBUG_DIR:
            cv2.imwrite(os.path.join(Preprocessor.DEBUG_DIR, f"spider_{stage}.png"), image)

    @staticmethod
    def decode(image_bytes: bytes):
        image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
        if image is None or image.size == 0:
            raise ImageDecodeError()
        if image.dtype != np.uint8:
            image = cv2.convertScaleAbs(image, alpha=255.0 / max(1, int(image.max())))
        if image.ndim == 2:
            return image
        if image.shape[2] == 4:
            alpha = image[:, :, 3:4].astype(np.float32) / 255.0
            white = np.full_like(image[:, :, :3], 255)
            image = (image[:, :, :3] * alpha + white * (1 - alpha)).astype(np.uint8)
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    @staticmethod
    def to_dark_on_light(gray):
        background = int(np.bincount(gray.ravel(), minlength=256).argmax())
        text = gray[np.abs(gray.astype(np.int16) - background) > 60]
        if text.size and text.mean() > background:
            logger.info("Vision: Light text on dark background, inverting")
            gray = cv2.bitwise_not(gray)
        return cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)

    @staticmethod
    def char_height(gray):
        binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        _, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        heights = [h for _, _, w, h, area in stats[1:] if area >= 4 and h >= 3 and w < gray.shape[1] * 0.5]
        return float(np.median(heights)) if heights else None

    @staticmethod
    def deskew(gray):
        h, w = gray.shape[:2]
        scale = min(1.0, 800.0 / w)
        small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray
        binary = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        sh, sw = binary.shape
        if cv2.countNonZero(binary) < sh * sw * MIN_TEXT_FRACTION:
            return gray

        def line_sharpness(angle):
            matrix = cv2.getRotationMatrix2D((sw / 2, sh / 2), angle, 1.0)
            rotated = cv2.warpAffine(binary, matrix, (sw, sh), flags=cv2.INTER_NEAREST, borderValue=0)
            return float(np.diff(rotated.sum(axis=1, dtype=np.float64)).var())

        angles = np.arange(-MAX_SKEW_DEGREES, MAX_SKEW_DEGREES + SKEW_STEP_DEGREES / 2, SKEW_STEP_DEGREES)
        scores = [line_sharpness(a) for a in angles]
        best = float(angles[int(np.argmax(scores))])
        if abs(best) < SKEW_STEP_DEGREES or max(scores) < line_sharpness(0.0) * MIN_SKEW_GAIN:
            return gray

        logger.info("Vision: Deskewing by %.1f degrees", best)
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), best, 1.0)
        return cv2.warpAffine(gray, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    @staticmethod
    def process_image(image_bytes: bytes):
        gray = Preprocessor.decode(image_bytes)
        h, w = gray.shape
        logger.info("Vision: Input dimensions %dx%d", w, h)

        gray = Preprocessor.to_dark_on_light(gray)
        Preprocessor._debug_save("1_normalized", gray)

        gray = Preprocessor.deskew(gray)
        Preprocessor._debug_save("2_deskewed", gray)

        char_height = Preprocessor.char_height(gray)
        if char_height:
            scale = min(MAX_UPSCALE, TARGET_CHAR_HEIGHT / char_height, (MAX_PIXELS / (w * h)) ** 0.5)
            if scale > 1.05:
                gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                logger.info("Vision: Text height %.0fpx, upscaled %.2fx", char_height, scale)
        Preprocessor._debug_save("3_scaled", gray)

        return cv2.copyMakeBorder(gray, BORDER, BORDER, BORDER, BORDER, cv2.BORDER_CONSTANT, value=255)
