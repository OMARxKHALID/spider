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
        laplacian_var = cv2.Laplacian(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
        logger.info("Pre-Processing: %dx%d (Sharpness: %.2f)", w, h, laplacian_var)
            
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        if Preprocessor.is_high_quality(gray):
            logger.info("High quality image detected. Skipping heavy processing.")
            return gray

        std_val = gray.std()
        if std_val < 40:
            logger.info("Low contrast detected (std: %.2f). Applying CLAHE.", std_val)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
            
        mean_val = gray.mean()
        if mean_val > 128:
            logger.info("Dark background detected (mean: %.2f). Inverting.", mean_val)
            gray = cv2.bitwise_not(gray)
            
        gray = Preprocessor.deskew(gray)
        return gray

    @staticmethod
    def is_high_quality(img: np.ndarray) -> bool:
        laplacian_var = cv2.Laplacian(img, cv2.CV_64F).var()
        rms_contrast = img.std()
        return laplacian_var > 200 and rms_contrast > 60

    @staticmethod
    def deskew(image: np.ndarray) -> np.ndarray:
        inv = cv2.bitwise_not(image)
        coords = np.column_stack(np.where(inv > 0))
        if len(coords) == 0:
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
