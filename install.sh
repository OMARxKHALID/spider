#!/usr/bin/env bash
# Spider OCR - Modern Setup Script
set -euo pipefail

# ANSI color codes
BOLD='\033[1m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

info() { printf "${CYAN}${BOLD}==>${NC} ${BOLD}%s${NC}\n" "$1"; }
success() { printf "${GREEN}${BOLD}==>${NC} ${BOLD}%s${NC}\n" "$1"; }
error() { printf "${RED}${BOLD}Error:${NC} %s\n" "$1"; exit 1; }

info "Spider OCR: Starting Stabilization Sweep"

# 1. System Dependency Check (Debian/Ubuntu)
info "Checking for core dependencies..."
deps=(python3 meson ninja-build tesseract-ocr pkg-config libgirepository1.0-dev libcairo2-dev)
for dep in "${deps[@]}"; do
    if ! dpkg -s "$dep" >/dev/null 2>&1; then
        info "Note: You might need to install '$dep' (sudo apt install $dep)"
    fi
done

# 2. Virtual Environment Setup
if [[ ! -d ".venv" ]]; then
    info "Creating fresh virtual environment..."
    python3 -m venv --system-site-packages .venv
fi

# 3. Dependency Installation
info "Syncing Python dependencies..."
./.venv/bin/python3 -m pip install --upgrade pip
./.venv/bin/python3 -m pip install pytesseract pillow opencv-python

# 4. Meson Build Flow
if [[ -d "builddir" ]]; then
    info "Refreshing build directory..."
    rm -rf builddir
fi

info "Configuring project..."
meson setup builddir --prefix=/usr/local

info "Compiling..."
meson compile -C builddir

echo ""
success "Spider OCR is ready!"
printf "  Launch:  ${BOLD}./builddir/org.domain.Spider${NC}\n"
printf "  Install: ${BOLD}sudo meson install -C builddir${NC}\n"
echo ""
