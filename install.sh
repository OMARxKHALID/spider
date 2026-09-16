#!/usr/bin/env bash
set -euo pipefail

BOLD='\033[1m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

info() { printf "${CYAN}${BOLD}==>${NC} ${BOLD}%s${NC}\n" "$1"; }
success() { printf "${GREEN}${BOLD}==>${NC} ${BOLD}%s${NC}\n" "$1"; }
error() { printf "${RED}${BOLD}Error:${NC} %s\n" "$1"; exit 1; }

info "Spider: Starting Build"

info "Checking for core dependencies..."
deps=(python3 python3-gi meson ninja-build tesseract-ocr tesseract-ocr-eng gir1.2-gtk-4.0 gir1.2-adw-1)
for dep in "${deps[@]}"; do
    if ! dpkg -s "$dep" >/dev/null 2>&1; then
        info "Note: You might need to install '$dep' (sudo apt install $dep)"
    fi
done

if [[ ! -d ".venv" ]]; then
    info "Creating fresh virtual environment..."
    python3 -m venv --system-site-packages .venv
fi

info "Syncing Python dependencies..."
./.venv/bin/python3 -m pip install --upgrade pip
./.venv/bin/python3 -m pip install opencv-python pillow pytest

if [[ -d "builddir" ]]; then
    info "Refreshing build directory..."
    rm -rf builddir
fi

source .venv/bin/activate

info "Configuring project..."
meson setup builddir --prefix=/usr/local

info "Compiling..."
meson compile -C builddir

echo ""
success "Spider is ready!"
printf "  Launch:  ${BOLD}./builddir/org.domain.Spider${NC}\n"
printf "  Install: ${BOLD}sudo meson install -C builddir${NC}\n"
echo "WARNING: Launcher is tied to this build path. Do not move the project directory."
echo ""
