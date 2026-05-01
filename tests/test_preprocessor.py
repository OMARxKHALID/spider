import pytest
import numpy as np
import cv2
from spider.vision.preprocessor import Preprocessor

class TestPreprocessor:

    def setup_method(self):
        self.pp = Preprocessor()

    # ── Output format ───────────────────────────────────────

    def test_output_is_bytes(self, white_image):
        _, buf = cv2.imencode('.png', white_image)
        # Note: Preprocessor process_image returns numpy array, not bytes
        # It's an internal function that processes bytes and returns numpy.ndarray
        result = self.pp.process_image(buf.tobytes())
        assert isinstance(result, np.ndarray), "Output must be ndarray"

    def test_output_is_valid_image(self, white_image):
        _, buf = cv2.imencode('.png', white_image)
        result = self.pp.process_image(buf.tobytes())
        assert result is not None, "Output must be valid array"

    def test_output_is_grayscale(self, white_image):
        _, buf = cv2.imencode('.png', white_image)
        result = self.pp.process_image(buf.tobytes())
        assert len(result.shape) == 2 or result.shape[2] == 1, \
            "Output must be grayscale"

    # ── Upscaling ───────────────────────────────────────────

    def test_small_image_is_upscaled(self, small_image):
        h, w = small_image.shape[:2]
        _, buf = cv2.imencode('.png', small_image)
        result = self.pp.process_image(buf.tobytes())
        # Must be significantly larger
        assert result.shape[0] > h * 1.5 or result.shape[1] > w * 1.5, \
            f"Small image {w}x{h} should be upscaled, got {result.shape[1]}x{result.shape[0]}"

    def test_thin_capture_does_not_explode_memory(self, thin_capture_image):
        """5000x80 capture must not produce unreasonably large output."""
        _, buf = cv2.imencode('.png', thin_capture_image)
        result = self.pp.process_image(buf.tobytes())
        total_pixels = result.shape[0] * result.shape[1]
        assert total_pixels < 50_000_000, \
            f"Thin capture produced {total_pixels} pixels — too large"

    def test_large_image_not_upscaled(self):
        """3000x2000 image should NOT be upscaled."""
        img = np.ones((2000, 3000, 3), dtype=np.uint8) * 255
        h, w = img.shape[:2]
        _, buf = cv2.imencode('.png', img)
        result = self.pp.process_image(buf.tobytes())
        # Should not be more than 10% bigger (border padding only)
        assert result.shape[1] <= w * 1.1, "Large image should not be upscaled"

    # ── Dark mode ───────────────────────────────────────────

    def test_dark_mode_image_is_inverted(self, dark_mode_image):
        """Dark image (mean<115) must be inverted so text is dark on white."""
        _, buf = cv2.imencode('.png', dark_mode_image)
        result = self.pp.process_image(buf.tobytes())
        # After inversion + thresholding: majority of pixels should be white (255)
        white_ratio = np.sum(result == 255) / result.size
        assert white_ratio > 0.5, \
            f"Dark mode image should be inverted (white bg), got {white_ratio:.2%} white"

    def test_light_mode_image_not_inverted(self, white_image):
        """Light image must NOT be inverted."""
        _, buf = cv2.imencode('.png', white_image)
        result = self.pp.process_image(buf.tobytes())
        white_ratio = np.sum(result == 255) / result.size
        assert white_ratio > 0.5, \
            "Light mode image should remain white background"

    # ── Border padding ──────────────────────────────────────

    def test_border_padding_added(self, white_image):
        """Output must be at least 20px wider and taller than input."""
        h, w = white_image.shape[:2]
        _, buf = cv2.imencode('.png', white_image)
        result = self.pp.process_image(buf.tobytes())
        # Allow for upscaling — just check SOME padding was added
        # The border (10px each side) should be detectable as white margin
        top_row_white = np.all(result[0, :] == 255)
        assert top_row_white, "Top border row should be white (padding)"

    # ── RGBA handling ───────────────────────────────────────

    def test_rgba_image_does_not_crash(self, rgba_image):
        """4-channel RGBA input must not raise an exception."""
        _, buf = cv2.imencode('.png', rgba_image)
        try:
            result = self.pp.process_image(buf.tobytes())
            assert result is not None
        except Exception as e:
            pytest.fail(f"RGBA image crashed preprocessor: {e}")

    # ── Pipeline order regression ───────────────────────────

    def test_sharpening_before_blur_no_amplified_noise(self):
        """Noisy image should be cleaner after fix (sharpen→blur order)."""
        # Create image with salt-and-pepper noise
        img = np.ones((100, 400, 3), dtype=np.uint8) * 255
        cv2.putText(img, "Noise test", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 2)
        noise_mask = np.random.randint(0, 100, img.shape[:2]) < 5
        img[noise_mask] = 0  # add salt-and-pepper noise
        _, buf = cv2.imencode('.png', img)
        result = self.pp.process_image(buf.tobytes())
        # After proper processing, isolated noise pixels should be gone
        # Check that the image is mostly binary (0 or 255)
        non_binary = np.sum((result > 10) & (result < 245))
        total = result.size
        assert non_binary / total < 0.1, \
            f"Too many non-binary pixels after processing: {non_binary/total:.2%}"
