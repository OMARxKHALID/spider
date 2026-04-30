#!/usr/bin/env bash
set -euo pipefail

APP_NAME="spider"
VERSION="0.1.0"
DEB_DIR="deb-build"
ARCH=$(dpkg --print-architecture)

echo "Building .deb package for $APP_NAME ($ARCH)..."

rm -rf "$DEB_DIR" builddir
mkdir -p "$DEB_DIR"
meson setup builddir --prefix=/usr
meson install -C builddir --destdir "$(pwd)/$DEB_DIR"

mkdir -p "$DEB_DIR/DEBIAN"
cat <<EOF > "$DEB_DIR/DEBIAN/control"
Package: $APP_NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: python3, python3-gi, python3-pil, python3-opencv, python3-pytesseract, tesseract-ocr, libadwaita-1-0, gir1.2-adw-1, gir1.2-gtk-4.0
Maintainer: Omar Khalid <omarxkhalid@github.com>
Description: Intuitive text extraction tool (OCR) for GNOME.
 Spider OCR captures regions of your screen and instantly extracts text 
 using advanced OCR engines. Built with GTK4 and Libadwaita.
EOF

cat <<EOF > "$DEB_DIR/DEBIAN/postinst"
#!/bin/sh
set -e
if [ "\$1" = "configure" ]; then
    glib-compile-schemas /usr/share/glib-2.0/schemas || true
    update-desktop-database -q /usr/share/applications || true
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
EOF
chmod 755 "$DEB_DIR/DEBIAN/postinst"

dpkg-deb --build "$DEB_DIR" "${APP_NAME}_${VERSION}_${ARCH}.deb"

echo "Done! Generated ${APP_NAME}_${VERSION}_${ARCH}.deb"
rm -rf "$DEB_DIR"
