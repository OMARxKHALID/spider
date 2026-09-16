import cv2
import numpy as np
import pytest

from spider.core.exceptions import ImageDecodeError
from spider.vision.preprocessor import Preprocessor, BORDER, MAX_PIXELS


def encode(img):
    return cv2.imencode('.png', img)[1].tobytes()


def text_angle(gray):
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    angle = cv2.minAreaRect(cv2.findNonZero(thresh))[-1]
    return angle + 90 if angle < -45 else angle - 90 if angle > 45 else angle


class TestPreprocessor:

    def test_output_is_grayscale_uint8(self, white_image):
        result = Preprocessor.process_image(encode(white_image))
        assert result.ndim == 2 and result.dtype == np.uint8

    def test_undecodable_bytes_raise(self):
        with pytest.raises(ImageDecodeError):
            Preprocessor.process_image(b"not an image")

    def test_small_text_is_upscaled(self, small_image):
        h, w = small_image.shape[:2]
        result = Preprocessor.process_image(encode(small_image))
        assert result.shape[1] > w * 1.5

    def test_large_text_not_upscaled(self):
        img = np.full((300, 1600, 3), 255, np.uint8)
        cv2.putText(img, "Big Heading", (20, 200), cv2.FONT_HERSHEY_SIMPLEX, 5.0, (0, 0, 0), 12)
        result = Preprocessor.process_image(encode(img))
        assert result.shape[1] == 1600 + 2 * BORDER

    def test_upscale_respects_pixel_budget(self, thin_capture_image):
        result = Preprocessor.process_image(encode(thin_capture_image))
        assert result.shape[0] * result.shape[1] <= MAX_PIXELS * 1.05

    def test_dark_mode_becomes_dark_text_on_light(self, dark_mode_image):
        result = Preprocessor.process_image(encode(dark_mode_image))
        assert np.median(result) > 200

    def test_light_text_on_colored_background_inverted(self):
        img = np.full((80, 400, 3), (228, 132, 53), np.uint8)
        cv2.putText(img, "Download", (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
        result = Preprocessor.process_image(encode(img))
        assert np.median(result) > 200, "Background must end up light"
        assert result.min() < 60, "Text must end up dark"

    def test_light_mode_not_inverted(self, white_image):
        result = Preprocessor.process_image(encode(white_image))
        assert np.median(result) > 200

    def test_low_contrast_is_stretched(self, low_contrast_image):
        result = Preprocessor.process_image(encode(low_contrast_image))
        assert result.min() == 0 and result.max() == 255

    def test_border_padding_added(self, white_image):
        result = Preprocessor.process_image(encode(white_image))
        assert np.all(result[:BORDER, :] == 255)

    def test_transparent_png_composited_on_white(self):
        img = np.zeros((80, 300, 4), np.uint8)
        cv2.putText(img, "Logo", (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0, 255), 3)
        result = Preprocessor.process_image(encode(img))
        assert np.median(result) > 200 and result.min() < 60

    def test_rgba_image_does_not_crash(self, rgba_image):
        assert Preprocessor.process_image(encode(rgba_image)) is not None

    def test_deskew_straightens_both_directions(self, white_image):
        gray = cv2.cvtColor(white_image, cv2.COLOR_BGR2GRAY)
        gray = cv2.copyMakeBorder(gray, 60, 60, 60, 60, cv2.BORDER_CONSTANT, value=255)
        h, w = gray.shape
        for tilt in (4, -4, 8):
            M = cv2.getRotationMatrix2D((w // 2, h // 2), tilt, 1.0)
            skewed = cv2.warpAffine(gray, M, (w, h), borderValue=255)
            assert abs(text_angle(Preprocessor.deskew(skewed))) < 1.5, tilt

    def test_deskew_leaves_straight_text_alone(self, white_image):
        gray = cv2.cvtColor(white_image, cv2.COLOR_BGR2GRAY)
        assert np.array_equal(Preprocessor.deskew(gray), gray)

    def test_deskew_ignores_noise(self):
        rng = np.random.default_rng(3)
        noise = np.where(rng.random((400, 600)) < 0.02, 0, 255).astype(np.uint8)
        assert np.array_equal(Preprocessor.deskew(noise), noise)
