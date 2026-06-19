# PUG Legal Case Control System - one-time local dev setup (Windows / PowerShell)
# Direct (PugFin-style) setup: no Docker required.
#
# Run from the repository root:
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $Root
Write-Host "==> Repository: $Root" -ForegroundColor Cyan

# Local folders
New-Item -ItemType Directory -Force -Path storage, backups, logs | Out-Null
Write-Host "==> storage\, backups\, logs\ ready"

# ---------- Backend ----------
Write-Host "==> Setting up backend (Python venv)" -ForegroundColor Cyan
Set-Location "$Root\backend"

if (-not (Test-Path ".venv")) {
    try {
        py -3.12 -m venv .venv
    } catch {
        python -m venv .venv
    }
}

& ".\.venv\Scripts\Activate.ps1"
python -m pip install --upgrade pip
pip install -e ".[dev,reports]"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "==> Created backend\.env (edit with your local Postgres/Redis details)"
}

Write-Host "==> Running Alembic migrations"
try {
    alembic upgrade head
} catch {
    Write-Host "!! Alembic failed - confirm Postgres is running and DATABASE_URL is correct." -ForegroundColor Yellow
}

deactivate

# ---------- Frontend ----------
Write-Host "==> Setting up frontend (Node)" -ForegroundColor Cyan
Set-Location "$Root\frontend"

if (-not (Test-Path ".env.local")) {
    Copy-Item ".env.example" ".env.local"
    Write-Host "==> Created frontend\.env.local"
}

if (Get-Command pnpm -ErrorAction SilentlyContinue) {
    pnpm install
} else {
    npm install
}

Set-Location $Root

Write-Host ""
Write-Host "=================================================" -ForegroundColor Green
Write-Host " Setup complete." -ForegroundColor Green
Write-Host " Next:"
Write-Host "   .\scripts\dev-backend.ps1   # http://127.0.0.1:8000"
Write-Host "   .\scripts\dev-frontend.ps1  # http://127.0.0.1:3000"
Write-Host "=================================================" -ForegroundColor Green
