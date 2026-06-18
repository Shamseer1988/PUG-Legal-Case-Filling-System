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

# Backend
echo "==> Setting up backend (Python venv)"
cd "$ROOT/backend"
if [ ! -d ".venv" ]; then
    python3.12 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev,reports]"

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
echo "================================================="
