import logging
import time
import os

logger = logging.getLogger(__name__)

class Preprocessor:
    DEBUG_PREPROCESSOR = os.environ.get('SPIDER_DEBUG_PREPROCESS') == '1'

    @staticmethod
    def _debug_save(stage: str, image):
        if not Preprocessor.DEBUG_PREPROCESSOR:
            return
        import tempfile
        import cv2
        path = os.path.join(tempfile.gettempdir(), f"spider_preprocess_{stage}.png")
        cv2.imwrite(path, image)
        logger.debug("Preprocessor stage '%s' saved to %s", stage, path)

    @staticmethod
    def _binarize(gray, std=None):
        import cv2
        if std is None:
            std = gray.std()
        
        if std > 80:
            _, binary = cv2.threshold(
                gray, 0, 255,
                cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
            return binary
        
        elif std > 30:
            h, w = gray.shape[:2]
            block = max(11, (w // 20) | 1)
            block = min(block, 51)
            binary = cv2.adaptiveThreshold(
                gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                blockSize=block,
                C=2
            )
            return binary
        
        else:
            _, binary = cv2.threshold(
                gray, 0, 255,
                cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
            return binary

    @staticmethod
    def process_image(image_bytes: bytes):
        import cv2
        import numpy as np

        logger.info("Vision: Starting preprocessing pipeline")
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if image is None:
            logger.error("Vision: Failed to decode image bytes")
            raise ValueError("Could not decode image bytes")

        h, w = image.shape[:2]
        logger.info("Vision: Input dimensions %dx%d", w, h)

        SCREEN_DPI = 96
        TARGET_DPI = 300
        scale_factor = TARGET_DPI / SCREEN_DPI

        min_dim = min(h, w)
        if min_dim < 300:
            scale = max(scale_factor, 600.0 / min_dim)
            scale = min(scale, 4.0)
        elif w < 2000 or h < 2000:
            scale = scale_factor
        else:
            scale = 1.0

        if scale > 1.0:
            image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            new_h, new_w = image.shape[:2]
            logger.info("Vision: Upscaled image to %dx%d (factor: %.2f)", new_w, new_h, scale)

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        Preprocessor._debug_save("01_grayscale", gray)
        
        gray = Preprocessor.deskew(gray)
        Preprocessor._debug_save("02_deskewed", gray)

        kernel = np.array([[0,-1,0], [-1,5,-1], [0,-1,0]])
        gray = cv2.filter2D(gray, -1, kernel)
        Preprocessor._debug_save("03_sharpened", gray)

        gray = cv2.medianBlur(gray, 3)
        Preprocessor._debug_save("04_denoised", gray)

        std_val = gray.std()
        if std_val < 50:
            logger.info("Vision: Low contrast detected, applying CLAHE")
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
        Preprocessor._debug_save("05_clahe", gray)

        if gray.mean() < 115:
            logger.info("Vision: Dark background detected, inverting colors")
            gray = cv2.bitwise_not(gray)
        Preprocessor._debug_save("06_inverted", gray)

        gray = Preprocessor._binarize(gray, std_val)
        Preprocessor._debug_save("07_binarized", gray)

        gray = cv2.copyMakeBorder(
            gray, 10, 10, 10, 10,
            cv2.BORDER_CONSTANT, value=255
        )
        Preprocessor._debug_save("08_padded", gray)

        logger.info("Vision: Preprocessing complete")
        return gray

    @staticmethod
    def deskew(image):
        import cv2
        import numpy as np

        try:
            h, w = image.shape[:2]
            if w > 800:
                scale = 800.0 / w
                small = cv2.resize(image, (0,0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            else:
                small = image

            blur = cv2.GaussianBlur(small, (5, 5), 0)
            thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

            coords = cv2.findNonZero(thresh)
            if coords is None:
                return image

            angle = cv2.minAreaRect(coords)[-1]

            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle

            if 0.5 < abs(angle) < 20:
                logger.info("Vision: Deskewing detected tilt of %.2f degrees", angle)
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC,
                                        borderMode=cv2.BORDER_CONSTANT, borderValue=255)
                return rotated
            else:
                return image
        except Exception as e:
            logger.warning("Vision: Deskewing failed: %s", e)
            return image
