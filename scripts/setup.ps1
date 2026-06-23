# PUG Legal Case Control System - one-time local dev setup (Windows / PowerShell)
# Direct (PugFin-style) setup: no Docker required.
#
# Run from the repository root:
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

$ErrorActionPreference = "Stop"

function Assert-LastExit($Msg) {
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "!! $Msg (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

$Root = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $Root
Write-Host "==> Repository: $Root" -ForegroundColor Cyan

# Local folders
New-Item -ItemType Directory -Force -Path storage, backups, logs | Out-Null
Write-Host "==> storage\, backups\, logs\ ready"

# ---------- System packages for cheque OCR (Phase 38) ----------
# Tesseract drives the offline cheque-copy OCR pipeline. If it
# isn't installed the API still runs - uploads land but auto-fill
# returns "no engine" and the operator types the row by hand.
Write-Host "==> Cheque OCR system packages (tesseract + poppler)" -ForegroundColor Cyan

function Install-OcrSystemPackages {
    if (Get-Command tesseract -ErrorAction SilentlyContinue) {
        $ver = (tesseract --version 2>&1 | Select-Object -First 1)
        Write-Host "    tesseract already installed: $ver"
        return
    }

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "    Installing Tesseract via winget (UB-Mannheim build)..."
        winget install --silent --accept-source-agreements --accept-package-agreements `
            -e --id UB-Mannheim.TesseractOCR
        Write-Host "    Installing Poppler via winget..."
        winget install --silent --accept-source-agreements --accept-package-agreements `
            -e --id oschwartz10612.Poppler 2>$null
    } elseif (Get-Command choco -ErrorAction SilentlyContinue) {
        Write-Host "    Installing Tesseract + Poppler via Chocolatey..."
        choco install -y tesseract poppler
    } else {
        Write-Host "    !! No package manager found (winget or choco)." -ForegroundColor Yellow
        Write-Host "       Install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki" -ForegroundColor Yellow
        Write-Host "       and Poppler from https://github.com/oschwartz10612/poppler-windows/releases/" -ForegroundColor Yellow
        Write-Host "       Or set OCR_VISION_API_KEY in backend\.env to use a hosted vision LLM instead." -ForegroundColor Yellow
        return
    }

    # winget / choco usually add Tesseract to PATH automatically, but
    # the running shell may not have refreshed - pull the new PATH so
    # the rest of this script (and the pip install below) can see it.
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path","Machine")
    $userPath    = [System.Environment]::GetEnvironmentVariable("Path","User")
    $env:Path = "$machinePath;$userPath"

    if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) {
        Write-Host "    !! Tesseract install ran but the binary still isn't on PATH." -ForegroundColor Yellow
        Write-Host "       Open a NEW PowerShell window and re-run this script, or add the install" -ForegroundColor Yellow
        Write-Host "       folder (default: C:\Program Files\Tesseract-OCR) to your PATH manually." -ForegroundColor Yellow
        return
    }
    Write-Host "    tesseract installed: $(tesseract --version 2>&1 | Select-Object -First 1)"

    # Tesseract on Windows ships English by default. Grab the
    # Arabic traineddata so bilingual GCC cheques OCR correctly.
    $tessDir   = (Split-Path -Parent (Get-Command tesseract).Source)
    $tessData  = Join-Path $tessDir "tessdata"
    $araFile   = Join-Path $tessData "ara.traineddata"
    if ((Test-Path $tessData) -and -not (Test-Path $araFile)) {
        Write-Host "    Downloading Arabic language pack (ara.traineddata)..."
        try {
            Invoke-WebRequest `
                -Uri "https://github.com/tesseract-ocr/tessdata/raw/main/ara.traineddata" `
                -OutFile $araFile -UseBasicParsing
            Write-Host "    Arabic traineddata installed at $araFile"
        } catch {
            Write-Host "    !! Could not download Arabic traineddata: $_" -ForegroundColor Yellow
            Write-Host "       Bilingual cheques will OCR in English only." -ForegroundColor Yellow
        }
    }
}

try {
    Install-OcrSystemPackages
} catch {
    Write-Host "    !! OCR system-package install hit an error: $_" -ForegroundColor Yellow
    Write-Host "       Cheque auto-fill will be unavailable until tesseract is on PATH." -ForegroundColor Yellow
}

# ---------- Backend ----------
Write-Host "==> Setting up backend (Python venv)" -ForegroundColor Cyan
Set-Location "$Root\backend"

if (-not (Test-Path ".venv")) {
    $created = $false
    try {
        py -3.12 -m venv .venv
        if ($LASTEXITCODE -eq 0) { $created = $true }
    } catch { }
    if (-not $created) {
        try {
            py -3.11 -m venv .venv
            if ($LASTEXITCODE -eq 0) { $created = $true }
        } catch { }
    }
    if (-not $created) {
        python -m venv .venv
        Assert-LastExit "Failed to create Python venv"
    }
}

& ".\.venv\Scripts\Activate.ps1"

python -m pip install --upgrade pip
Assert-LastExit "pip self-upgrade failed"

pip install -e ".[dev,reports,ocr]"
Assert-LastExit "pip install of backend dependencies failed"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "==> Created backend\.env (edit with your local Postgres/Redis details)"
}

Write-Host "==> Running Alembic migrations"
alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Write-Host "!! Alembic failed - confirm Postgres is running and DATABASE_URL in backend\.env is correct." -ForegroundColor Yellow
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
Assert-LastExit "Frontend dependency install failed"

Set-Location $Root

Write-Host ""
Write-Host "=================================================" -ForegroundColor Green
Write-Host " Setup complete." -ForegroundColor Green
Write-Host " Next:"
Write-Host "   .\scripts\dev-backend.ps1   # http://127.0.0.1:8000"
Write-Host "   .\scripts\dev-frontend.ps1  # http://127.0.0.1:3000"
Write-Host ""
Write-Host " Cheque OCR (Phase 38):"
if (Get-Command tesseract -ErrorAction SilentlyContinue) {
    Write-Host "   Tesseract is installed - cheque-copy auto-fill is ready." -ForegroundColor Green
} else {
    Write-Host "   Tesseract is NOT on PATH; auto-fill will return 'no engine'." -ForegroundColor Yellow
    Write-Host "   To enable, either install tesseract above, OR set in backend\.env:"
    Write-Host "     OCR_VISION_API_KEY=<your-key>"
    Write-Host "     OCR_VISION_PROVIDER=anthropic   # or openai"
}
Write-Host "=================================================" -ForegroundColor Green
