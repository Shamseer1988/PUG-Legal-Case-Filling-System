# Run the Next.js frontend in dev mode (Windows / PowerShell)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location "$Root\frontend"

if (Get-Command pnpm -ErrorAction SilentlyContinue) {
    pnpm dev
} else {
    npm run dev
}
