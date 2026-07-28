#!/usr/bin/env bash
# ubx2rinex launcher for Linux / macOS / WSL.
#   ./convert.sh /path/to/data
#   ./convert.sh a.ubx b.ubx --outdir /path/out

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
py="$here/.venv/bin/python"

if [ ! -x "$py" ]; then
    echo "Virtual environment not found."
    echo "Run this first:  ./setup.sh"
    exit 1
fi

if [ $# -eq 0 ]; then
    cat <<'EOF'
ubx2rinex - convert raw u-blox UBX logs to RINEX .YYo / .YYn

  ./convert.sh /path/to/folder      every .ubx in the folder, one run
  ./convert.sh a.ubx b.ubx          several files at once
  ./convert.sh /data --recursive    include subfolders

  ./convert.sh --help               full option list
EOF
    exit 0
fi

exec "$py" "$here/ubx2rinex.py" "$@"
