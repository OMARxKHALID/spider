import logging
import time

logger = logging.getLogger(__name__)

class Preprocessor:
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

        if w < 1000 or h < 1000:
            scale = 2.0
            image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            new_h, new_w = image.shape[:2]
            logger.info("Vision: Upscaled image to %dx%d (factor: %.2f)", new_w, new_h, scale)

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = Preprocessor.deskew(gray)

        std_val = gray.std()
        mean_val = gray.mean()

        if std_val < 50:
            logger.info("Vision: Low contrast detected, applying CLAHE")
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)

        if mean_val < 115:
            logger.info("Vision: Dark background detected, inverting colors")
            gray = cv2.bitwise_not(gray)

        gray = cv2.medianBlur(gray, 3)

        kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
        gray = cv2.filter2D(gray, -1, kernel)

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
