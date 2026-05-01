# Spider

> Intuitive and high-performance text extraction tool (OCR) for GNOME.

<div align="center">
<figure>
<img src="data/org.domain.Spider.png" width="128" alt="Spider logo" />
</figure>
</div>

Quickly extract text from almost any source: YouTube, screencasts, PDFs, webpages, photos, etc.
Grab the image and get the text.

Spider OCR is a premium desktop application for Linux designed to capture regions of your screen and instantly extract text using an optimized vision pipeline. Built with **GTK4** and **Libadwaita**, it offers a native, modern experience with a focus on speed and stability.

## ✨ Features

- **Interactive Capture**: Grab any part of your screen using standard GNOME Portals.
- **Smart Pre-processing**: Built-in vision pipeline (Upscaling, CLAHE, Sharpness) to improve accuracy on small or complex text.
- **History Management**: Automatically save your captures with a searchable, high-performance local history (FTS5).
- **Modern UI**: Sleek interface that respects your system theme and auto-hides during capture.
- **Instant Startup**: Optimized architecture for a premium, lag-free feel.

## 📦 Installation (Ubuntu / Zorin / Debian)

1. Download the `spider_0.1.0_amd64.deb` from the latest release assets.
2. Open your terminal in the download folder and run:
   ```bash
   sudo dpkg -i spider_0.1.0_amd64.deb
   ```
3. If dependencies are missing, run:
   ```bash
   sudo apt install -f
   ```

### 🐍 Troubleshooting Dependencies

If you encounter missing Python modules on startup, ensure the core libraries are installed:

```bash
sudo apt install tesseract-ocr python3-pytesseract python3-pil python3-opencv
```

## 🛠️ Manual Build

```bash
git clone https://github.com/OMARxKHALID/spider.git
cd spider
chmod +x install.sh
./install.sh
```

### Launch

```bash
./builddir/org.domain.Spider
```

## 🏗️ Packaging

You can package Spider into various installer formats:

### Flatpak

```bash
flatpak-builder --user --install --force-clean build-dir build-aux/org.domain.Spider.json
```

### Debian Package (.deb)

To build a policy-compliant Debian package:

```bash
# Install build tools
sudo apt install debhelper dh-python devscripts build-essential

# Build the package
dpkg-buildpackage -us -uc -b
```

## :tada: Support

If you like Spider and you want to support its development, you can support me on GitHub:

<a href="https://github.com/OMARxKHALID/spider" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Support" style="height: 60px !important;width: 217px !important;" ></a>

## Thanks

Special thanks to the open-source community for the powerful tools (Tesseract, OpenCV, Libadwaita) that make this project possible.
