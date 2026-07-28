#!/usr/bin/env bash
# ubx2rinex launcher for Linux / macOS.
#   ./convert.sh /path/ke/data
#   ./convert.sh a.ubx b.ubx --outdir /path/hasil

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
py="$here/.venv/bin/python"

if [ ! -x "$py" ]; then
    echo "Virtual environment belum dibuat."
    echo "Jalankan dulu:  ./setup.sh"
    exit 1
fi

if [ $# -eq 0 ]; then
    cat <<'EOF'
ubx2rinex - konversi log mentah u-blox UBX ke RINEX .YYo / .YYn

  ./convert.sh /path/ke/folder      semua .ubx dalam folder, sekali jalan
  ./convert.sh a.ubx b.ubx          beberapa file sekaligus
  ./convert.sh /data --recursive    termasuk subfolder

  ./convert.sh --help               daftar opsi lengkap
EOF
    exit 0
fi

exec "$py" "$here/ubx2rinex.py" "$@"
