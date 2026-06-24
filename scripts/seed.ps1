# Seed default roles + admin user + sample masters (Windows / PowerShell)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location "$Root\backend"
& ".\.venv\Scripts\Activate.ps1"
python -m app.services.seed
