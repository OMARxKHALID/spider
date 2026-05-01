# <img src="data/org.domain.Spider.png" width="48" align="center"> Spider Build & Packaging Guide

This guide outlines the purpose and usage of the utility scripts provided in the Spider codebase to help maintainers easily clear caches, compile natively, or package the application for distribution.

## 1. Native Installation (`./install.sh`)
The `install.sh` script is the quickest way to compile and install Spider directly onto your local system using Meson and Ninja.

**What it does:**
- Verifies all core system dependencies are present (Python 3, Tesseract, GTK4, Libadwaita).
- Automatically sets up a local `.venv` and installs the required Python packages (`pytesseract`, `pillow`, `opencv-python`).
- Initializes a fresh `builddir` via Meson.
- Compiles the application.

**How to use:**
```bash
./install.sh
```
After successful compilation, the script will instruct you to run `sudo meson install -C builddir` to finalize the system-wide installation.

---

## 2. Cache Cleanup (`./clear_cache.sh`)
When switching branches, making deep changes to dependencies, or seeing weird build errors, the codebase caches should be flushed. 

**What it does:**
- Deletes the Meson `builddir/` and Flatpak `.flatpak-builder/` compilation directories.
- Removes any generated `.deb` package files and the `/tmp/spider-deb` staging ground.
- Deletes the local Python `.venv/` to ensure a completely clean slate.
- Recursively purges `__pycache__`, `.pytest_cache`, `.mypy_cache`, and `.egg-info` remnants.

**How to use:**
```bash
./clear_cache.sh
```

---

## 3. Creating a Debian Package (`./build_deb.sh`)
Building a standard `.deb` file allows for easy installation and removal of Spider on Debian/Ubuntu-based distributions.

**What it does:**
- Installs necessary packaging tools (`ruby`, `fpm`, `rpm`).
- Executes a clean Meson compile.
- Uses `DESTDIR` to stage the compiled application in `/tmp/spider-deb`.
- Instructs `fpm` to package the staged files into a versioned `.deb` installer and automatically wires up the package dependencies (like `tesseract-ocr`, `gir1.2-gtk-4.0`, etc.).

**How to use:**
```bash
./build_deb.sh
```
Once complete, the script produces a file named `spider_1.0.0_all.deb`. You can install it natively using:
```bash
sudo apt install ./spider_1.0.0_all.deb
```

---

## 4. Building a Flatpak
Spider comes with a Flatpak manifest out-of-the-box, ensuring it can run securely across all Linux distributions (Fedora, Arch, Ubuntu, etc.).

**What it does:**
- Uses `flatpak-builder` to download the GNOME 46 runtime and compile Spider in an isolated container.
- Embeds required Python dependencies securely.

**How to use:**
You do not need a custom `.sh` script for this, as the standard Flatpak workflow applies:
```bash
# Build the flatpak
flatpak-builder --user --install --force-clean build-dir build-aux/org.domain.Spider.json

# Run the app
flatpak run org.domain.Spider
```

---

## 5. Running the Test Suite
If you are developing new features, always ensure the test suite passes before committing. Spider includes a comprehensive `pytest` suite.

**How to use:**
```bash
# Ensure the virtual environment is set up
./install.sh

# Run the test suite via the local venv
PYTHONPATH=src ./.venv/bin/pytest tests/
```
