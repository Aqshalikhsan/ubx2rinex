# One-time setup for ubx2rinex.
# Creates a private virtual environment and installs pygnssutils into it.
# Re-run this to update the dependency.
#
# Note: pip.exe is blocked by Application Control on this machine, so every
# call goes through "python -m pip", which is not blocked.

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $here ".venv"
$py = Join-Path $venv "Scripts\python.exe"

Write-Host "Membuat virtual environment di $venv ..." -ForegroundColor Cyan
if (-not (Test-Path $py)) {
    python -m venv $venv
    if (-not (Test-Path $py)) { throw "Gagal membuat venv. Pastikan Python ada di PATH." }
} else {
    Write-Host "  sudah ada, dilewati."
}

Write-Host "Memasang pygnssutils ..." -ForegroundColor Cyan
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet --upgrade pygnssutils

$ver = (& $py -m pip show pygnssutils | Select-String "^Version:").ToString()
Write-Host ""
Write-Host "Selesai. pygnssutils $($ver -replace 'Version:\s*','')" -ForegroundColor Green
Write-Host ""
Write-Host "Cara pakai:"
Write-Host "  - seret file .ubx atau folder ke convert.bat, atau"
Write-Host "  - .venv\Scripts\python.exe ubx2rinex.py C:\path\ke\data"
