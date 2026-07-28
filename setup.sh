#!/usr/bin/env bash
# One-time setup for ubx2rinex on Linux / macOS / WSL.
# Creates a private virtual environment and installs pygnssutils into it.
# Re-run this to update the dependency, or to repair a broken .venv.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
venv="$here/.venv"
py="$venv/bin/python"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Python 3 tidak ditemukan. Pasang dulu, atau: PYTHON=/path/ke/python3 ./setup.sh" >&2
    exit 1
fi

pyver="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
echo "Python: $("$PYTHON" -c 'import sys; print(sys.executable)') ($pyver)"
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || {
    echo "Butuh Python 3.10 atau lebih baru (pygnssutils memakai sintaks tipe modern)." >&2
    exit 1
}

venv_ok() { [ -x "$py" ] && "$py" -m pip --version >/dev/null 2>&1; }

apt_hint() {
    cat >&2 <<EOF

Virtual environment terbentuk tanpa pip. Di Debian/Ubuntu/WSL, modul ensurepip
dipisah ke paket tersendiri. Pasang dulu:

    sudo apt update && sudo apt install -y python${pyver}-venv

atau kalau nama paket itu tidak ada:

    sudo apt install -y python3-venv

lalu jalankan ./setup.sh lagi.
EOF
}

# A venv copied from Windows has Scripts/ instead of bin/ and is unusable here.
if [ -d "$venv" ] && [ -d "$venv/Scripts" ] && [ ! -d "$venv/bin" ]; then
    echo "Ditemukan .venv bawaan Windows (berisi Scripts/, bukan bin/) - dibuat ulang."
    rm -rf "$venv"
fi

if venv_ok; then
    echo "Virtual environment di $venv sudah ada dan berfungsi."
else
    if [ -d "$venv" ]; then
        echo "Virtual environment di $venv rusak atau tanpa pip - dibuat ulang."
        rm -rf "$venv"
    fi
    echo "Membuat virtual environment di $venv ..."
    if ! "$PYTHON" -m venv "$venv" 2>/dev/null; then
        # Debian refuses outright when python3-venv is absent
        rm -rf "$venv"
        apt_hint
        exit 1
    fi
    if ! venv_ok; then
        # venv built, but ensurepip was unavailable so no pip landed in it
        echo "pip tidak ikut terpasang, mencoba ensurepip ..."
        if ! "$py" -m ensurepip --upgrade >/dev/null 2>&1; then
            rm -rf "$venv"
            apt_hint
            exit 1
        fi
    fi
fi

echo "Memasang pygnssutils ..."
"$py" -m pip install --quiet --upgrade pip
"$py" -m pip install --quiet --upgrade pygnssutils

chmod +x "$here/convert.sh" 2>/dev/null || true

ver="$("$py" -m pip show pygnssutils | sed -n 's/^Version:[[:space:]]*//p')"
echo
echo "Selesai. pygnssutils $ver"
echo
echo "Cara pakai:"
echo "  ./convert.sh /path/ke/data"
echo "  .venv/bin/python ubx2rinex.py /path/ke/data"
