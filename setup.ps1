# One-time setup for ubx2rinex on Windows.
# Creates a private virtual environment and installs pygnssutils into it.
# Re-run this to update the dependency, or to repair a broken .venv.
#
# Every pip call goes through "python -m pip" rather than pip.exe, which some
# application-control policies block.

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $here ".venv"
$py = Join-Path $venv "Scripts\python.exe"

# Native commands are checked with $LASTEXITCODE, never $?. In Windows
# PowerShell 5.1 anything an executable writes to stderr flips $? to False even
# when it exited 0, so a pip upgrade notice would otherwise be read as a broken
# environment and delete a perfectly good .venv.
function Test-VenvOk {
    if (-not (Test-Path $py)) { return $false }
    & $py -m pip --version *> $null
    return ($LASTEXITCODE -eq 0)
}

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.10 or newer is required, and must be on PATH (pygnssutils uses modern type syntax)."
}

# A venv copied from Linux has bin/ instead of Scripts/ and is unusable here.
if ((Test-Path (Join-Path $venv "bin")) -and -not (Test-Path (Join-Path $venv "Scripts"))) {
    Write-Host "Found a Linux-built .venv (has bin/, not Scripts/) - rebuilding." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $venv
}

if (Test-VenvOk) {
    Write-Host "Virtual environment at $venv already exists and works." -ForegroundColor Cyan
} else {
    if (Test-Path $venv) {
        Write-Host "Virtual environment at $venv is broken or has no pip - rebuilding." -ForegroundColor Yellow
        Remove-Item -Recurse -Force $venv
    }
    Write-Host "Creating virtual environment at $venv ..." -ForegroundColor Cyan
    python -m venv $venv
    if (-not (Test-VenvOk)) {
        Write-Host "pip was not installed, trying ensurepip ..." -ForegroundColor Yellow
        & $py -m ensurepip --upgrade *> $null
        if (-not (Test-VenvOk)) {
            throw "Could not create a working virtual environment. Check that Python is on PATH and installed with pip."
        }
    }
}

Write-Host "Installing pygnssutils ..." -ForegroundColor Cyan
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet --upgrade pygnssutils
# $ErrorActionPreference does not apply to native commands, so check explicitly.
if ($LASTEXITCODE -ne 0) {
    throw "pip install failed (exit $LASTEXITCODE). Check your network or proxy settings."
}

$ver = & $py -m pip show pygnssutils | Select-String "^Version:"
if (-not $ver) { throw "pygnssutils did not install correctly." }
Write-Host ""
Write-Host "Done. pygnssutils $($ver.ToString() -replace 'Version:\s*','')" -ForegroundColor Green
Write-Host ""
Write-Host "Usage:"
Write-Host "  - drag .ubx files or a folder onto convert.bat, or"
Write-Host "  - .venv\Scripts\python.exe ubx2rinex.py C:\path\to\data"
