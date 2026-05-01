# <img src="data/org.domain.Spider.png" width="48" align="center"> Spider 🕷️

![Screenshot](data/screenshot.png)

A fast, lightweight, and modern desktop OCR tool for Linux built with Python, GTK4, Libadwaita, and Tesseract. Spider enables you to instantly extract text from screen regions or image files with offline processing and high accuracy.

## Features

- **Region Capture:** Instantly grab a portion of your screen (X11 & Wayland supported via XDG Desktop Portals).
- **Offline OCR:** Powered entirely by Tesseract OCR — all processing happens locally. No internet connection required.
- **Image Preprocessing:** Smart OpenCV pipelines automatically upscale small text, deskew, enhance contrast, and detect dark mode to achieve >95% accuracy.
- **Searchable History:** All captured text is saved locally into a blazing-fast SQLite FTS5 database, capped at 500 records to preserve storage.
- **Accessibility & HIG Compliant:** Full GTK4/Libadwaita integration ensuring dark mode support, Wayland safety, and screen reader compatibility.

---

## Installation

### Dependencies

Ensure you have the following system dependencies installed:

- `tesseract-ocr` and English language data (`tesseract-ocr-eng`)
- `python3` (>=3.10)
- `libgtk-4-dev`, `libadwaita-1-dev`
- OpenCV Python and PyGObject (`python3-gi`, `python3-opencv`)

### Installing from Source (Meson)

```bash
git clone https://github.com/omar/spider-ocr.git
cd spider-ocr
meson setup build
meson compile -C build
sudo meson install -C build
```

### Flatpak

A Flatpak manifest is provided in `build-aux/org.domain.Spider.json`.

```bash
flatpak-builder --user --install --force-clean build-dir build-aux/org.domain.Spider.json
flatpak run org.domain.Spider
```

_Note: For production Flatpak builds, it is highly recommended to run `flatpak-pip-generator` to pin Python dependencies into a deterministic `python3-deps.json` module._

---

## Technical Details

### Smart Preprocessing

Spider doesn't just pass images to Tesseract. It runs an intelligent pipeline:

1. Adaptive DPI upscaling.
2. Deskewing to fix angled captures.
3. Sharpening and Denoising.
4. Intelligent Binarization: Adaptive Gaussian thresholding for gradients, or Otsu's method depending on the image's standard deviation.

### Storage & Security

Data is stored locally under `~/.local/share/spider/history.db` with strict `0700` permissions. The UI performs non-blocking asynchronous reads/writes and maintains a generation-counter to safely ignore stale Wayland UI callbacks.

---

## License

Spider is released under the MIT License.
