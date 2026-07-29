#!/usr/bin/env bash
# One-time setup for ubx2rinex on Linux / macOS / WSL.
# Creates a private virtual environment and installs pygnssutils into it.
# Re-run this to update the dependency, or to repair a broken .venv.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
venv="$here/.venv"
py="$venv/bin/python"

install_hint() {
    cat >&2 <<'EOF'
Install Python 3.10 or newer, then run this script again:

    Debian/Ubuntu/WSL  sudo apt update && sudo apt install -y python3 python3-venv
    Fedora/RHEL        sudo dnf install -y python3
    macOS              brew install python

Already have a suitable interpreter elsewhere? Point at it:

    PYTHON=/path/to/python3.12 ./setup.sh
EOF
}

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Python 3 not found on PATH." >&2
    install_hint
    exit 1
fi

pyver="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
echo "Python: $("$PYTHON" -c 'import sys; print(sys.executable)') ($pyver)"
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "Python $pyver found, but 3.10 or newer is required (pygnssutils uses modern type syntax)." >&2
    install_hint
    exit 1
fi

venv_ok() { [ -x "$py" ] && "$py" -m pip --version >/dev/null 2>&1; }

apt_hint() {
    cat >&2 <<EOF

The virtual environment was created without pip. On Debian, Ubuntu and WSL the
ensurepip module ships in a separate package. Install it first:

    sudo apt update && sudo apt install -y python${pyver}-venv

or, if that package name does not exist:

    sudo apt install -y python3-venv

then run ./setup.sh again.
EOF
}

# A venv copied from Windows has Scripts/ instead of bin/ and is unusable here.
if [ -d "$venv" ] && [ -d "$venv/Scripts" ] && [ ! -d "$venv/bin" ]; then
    echo "Found a Windows-built .venv (has Scripts/, not bin/) - rebuilding."
    rm -rf "$venv"
fi

if venv_ok; then
    echo "Virtual environment at $venv already exists and works."
else
    if [ -d "$venv" ]; then
        echo "Virtual environment at $venv is broken or has no pip - rebuilding."
        rm -rf "$venv"
    fi
    echo "Creating virtual environment at $venv ..."
    if ! "$PYTHON" -m venv "$venv" 2>/dev/null; then
        # Debian refuses outright when python3-venv is absent
        rm -rf "$venv"
        apt_hint
        exit 1
    fi
    if ! venv_ok; then
        # venv built, but ensurepip was unavailable so no pip landed in it
        echo "pip was not installed, trying ensurepip ..."
        if ! "$py" -m ensurepip --upgrade >/dev/null 2>&1; then
            rm -rf "$venv"
            apt_hint
            exit 1
        fi
    fi
fi

echo "Installing pygnssutils ..."
"$py" -m pip install --quiet --upgrade pip
"$py" -m pip install --quiet --upgrade pygnssutils

chmod +x "$here/convert.sh" 2>/dev/null || true

ver="$("$py" -m pip show pygnssutils | sed -n 's/^Version:[[:space:]]*//p')"
echo
echo "Done. pygnssutils $ver"
echo
echo "Usage:"
echo "  ./convert.sh /path/to/data"
echo "  .venv/bin/python ubx2rinex.py /path/to/data"
