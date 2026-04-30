import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)

class Preprocessor:
    @staticmethod
    def process_image(image_bytes: bytes) -> np.ndarray:
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            raise ValueError("Could not decode image bytes")
            
        h, w = image.shape[:2]
        if w < 400 or h < 400:
            scale = 400.0 / min(w, h)
            image = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
            logger.info("Upscaling small image for better OCR (factor: %.2f)", scale)

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        h, w = gray.shape[:2]
        if w > 1000:
            scale = 1000.0 / w
            check_img = cv2.resize(gray, (1000, int(h * scale)))
        else:
            check_img = gray
            
        laplacian_var = cv2.Laplacian(check_img, cv2.CV_64F).var()
        logger.info("Pre-Processing: %dx%d (Sharpness: %.2f)", w, h, laplacian_var)
            
        if Preprocessor.is_high_quality(gray, laplacian_var):
            logger.info("High quality image detected. Skipping heavy processing.")
            return gray

        std_val = gray.std()
        if std_val < 40:
            logger.info("Low contrast detected (std: %.2f). Applying CLAHE.", std_val)
            h_g, w_g = gray.shape[:2]
            tile_size = max(1, min(8, h_g // 2, w_g // 2))
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(tile_size, tile_size))
            gray = clahe.apply(gray)
            
        mean_val = gray.mean()
        if mean_val < 128:  # dark background — invert for Tesseract
            logger.info("Dark background detected. Inverting for OCR.")
            gray = cv2.bitwise_not(gray)
            
        gray = Preprocessor.deskew(gray)
        return gray

    @staticmethod
    def is_high_quality(img: np.ndarray, laplacian_var: float) -> bool:
        rms_contrast = img.std()
        return laplacian_var > 200 and rms_contrast > 60

    @staticmethod
    def deskew(image: np.ndarray) -> np.ndarray:
        inv = cv2.bitwise_not(image)
        coords = cv2.findNonZero(inv)
        
        if coords is None or len(coords) == 0:
            return image
            
        angle = cv2.minAreaRect(coords)[-1]
        
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
            
        if abs(angle) < 0.5:
            return image
            
        logger.info("Deskewing by %.2f degrees", angle)
        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=255)
        return rotated
