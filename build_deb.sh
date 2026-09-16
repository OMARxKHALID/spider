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

info "Spider: Debian Package Builder"

info "Checking for packaging dependencies..."
deps=(ruby ruby-dev rubygems build-essential rpm)
for dep in "${deps[@]}"; do
    if ! dpkg -s "$dep" >/dev/null 2>&1; then
        info "Note: You might need to install '$dep' (sudo apt install $dep)"
    fi
done

if ! command -v fpm &> /dev/null; then
    info "Installing fpm via gem..."
    sudo gem install fpm
fi

info "Clearing build caches..."
rm -rf builddir
rm -rf /tmp/spider-deb
rm -f spider_*.deb

info "Configuring and compiling via Meson..."
meson setup builddir --prefix=/usr
meson compile -C builddir

info "Staging files for packaging..."
find src -type d -name "__pycache__" -exec rm -rf {} +
DESTDIR=/tmp/spider-deb meson install -C builddir

VERSION=$(meson introspect builddir --projectinfo | python3 -c 'import json, sys; print(json.load(sys.stdin)["version"])')

info "Building the .deb package..."
fpm -s dir -t deb \
  -n "spider" \
  -v "$VERSION" \
  --architecture all \
  --description "A fast, lightweight, and modern desktop OCR tool for Linux." \
  --maintainer "omarxkhalid" \
  --license "GPL-3.0-or-later" \
  --category "Utility" \
  --depends "tesseract-ocr" \
  --depends "tesseract-ocr-eng" \
  --depends "python3-gi" \
  --depends "python3-opencv" \
  --depends "python3-numpy" \
  --depends "gir1.2-gtk-4.0" \
  --depends "gir1.2-adw-1 (>= 1.5)" \
  -C /tmp/spider-deb .

echo ""
success "Spider .deb package has been created!"
printf "  Install: ${BOLD}sudo apt install ./spider_${VERSION}_all.deb${NC}\n"
echo ""
