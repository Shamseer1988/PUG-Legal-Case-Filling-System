#!/usr/bin/env bash
# PUG Legal Case Control System — one-time local dev setup.
# Direct (PugFin-style) setup: no Docker required.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Repository: $ROOT"

# Local folders
mkdir -p storage backups logs
echo "==> storage/, backups/, logs/ ready"

# ---------- System packages for cheque OCR (Phase 38) ----------
# Tesseract drives the offline cheque-copy OCR pipeline. If
# unavailable, the API still runs - uploads land but auto-fill
# returns "no engine" and the operator types the row by hand.
echo "==> Cheque OCR system packages (tesseract + poppler)"
install_ocr_system_packages() {
    if command -v tesseract >/dev/null 2>&1; then
        echo "    tesseract already installed: $(tesseract --version 2>&1 | head -1)"
        return 0
    fi
    if command -v apt-get >/dev/null 2>&1; then
        # Debian / Ubuntu
        if [ "$(id -u)" -eq 0 ]; then
            apt-get update -y && \
            apt-get install -y tesseract-ocr tesseract-ocr-ara poppler-utils
        else
            sudo apt-get update -y && \
            sudo apt-get install -y tesseract-ocr tesseract-ocr-ara poppler-utils
        fi
    elif command -v dnf >/dev/null 2>&1; then
        # Fedora / RHEL 9+
        sudo dnf install -y tesseract tesseract-langpack-ara poppler-utils
    elif command -v yum >/dev/null 2>&1; then
        # CentOS / RHEL 7-8
        sudo yum install -y tesseract tesseract-langpack-ara poppler-utils
    elif command -v pacman >/dev/null 2>&1; then
        # Arch
        sudo pacman -S --noconfirm tesseract tesseract-data-ara poppler
    elif command -v brew >/dev/null 2>&1; then
        # macOS
        brew install tesseract tesseract-lang poppler
    else
        echo "    !! No supported package manager detected (apt/dnf/yum/pacman/brew)."
        echo "       Install 'tesseract-ocr' + Arabic language pack + 'poppler-utils'"
        echo "       by hand, or set OCR_VISION_API_KEY in backend/.env to use a"
        echo "       hosted vision LLM instead."
        return 0
    fi
}
install_ocr_system_packages || \
    echo "    !! OCR system packages skipped - cheque auto-fill will be unavailable."

# Backend
echo "==> Setting up backend (Python venv)"
cd "$ROOT/backend"
if [ ! -d ".venv" ]; then
    python3.12 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev,reports,ocr]"

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "==> Created backend/.env (edit with your local Postgres/Redis details)"
fi

echo "==> Running Alembic migrations"
alembic upgrade head || echo "!! Alembic failed — confirm Postgres is running and DATABASE_URL is correct."

deactivate

# Frontend
echo "==> Setting up frontend (Node)"
cd "$ROOT/frontend"
if [ ! -f ".env.local" ]; then
    cp .env.example .env.local
    echo "==> Created frontend/.env.local"
fi
if command -v pnpm >/dev/null 2>&1; then
    pnpm install
else
    npm install
fi

echo ""
echo "================================================="
echo " Setup complete."
echo " Next:"
echo "   ./scripts/dev-backend.sh   # http://127.0.0.1:8000"
echo "   ./scripts/dev-frontend.sh  # http://127.0.0.1:3000"
echo ""
echo " Cheque OCR (Phase 38):"
if command -v tesseract >/dev/null 2>&1; then
    echo "   Tesseract is installed - cheque-copy auto-fill is ready."
else
    echo "   Tesseract is NOT on PATH; auto-fill will return 'no engine'."
    echo "   To enable, either install tesseract above, OR set in backend/.env:"
    echo "     OCR_VISION_API_KEY=<your-key>"
    echo "     OCR_VISION_PROVIDER=anthropic   # or openai"
fi
echo "================================================="
