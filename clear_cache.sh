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

info "Spider: Cleaning Codebase Caches"

# Change to the script's directory
cd "$(dirname "$0")"

if [[ -d "builddir" ]]; then
    info "Removing build directory (builddir/)..."
    rm -rf builddir/
fi

if [[ -d "deb-build" ]]; then
    info "Removing Debian build directory (deb-build/)..."
    rm -rf deb-build/
fi

info "Removing temporary packaging files..."
if [[ -d "/tmp/spider-deb" ]]; then
    rm -rf /tmp/spider-deb
fi
rm -f spider_*.deb

if [[ -d ".venv" ]]; then
    info "Removing virtual environment (.venv/)..."
    rm -rf .venv/
fi

info "Purging Python cache files..."
find . -type d -name "__pycache__" -exec rm -rf {} +
rm -rf .pytest_cache/
rm -rf .mypy_cache/
rm -f .coverage
rm -rf .cache/
find . -type d -name "*.egg-info" -exec rm -rf {} +

info "Removing other build artifacts..."
rm -rf obj-x86_64-linux-gnu/
if [[ -d "debian" ]]; then
    rm -rf debian/.debhelper/
    rm -f debian/files
    rm -f debian/*.substvars
    rm -f debian/*.debhelper
    rm -rf debian/spider/
fi

success "Codebase caches cleared successfully!"
echo "Run ./install.sh to rebuild the environment."
