# ubx2rinex

Batch converter from raw **u-blox UBX** logs to **RINEX 3.05** — observation (`.YYo`) and navigation (`.YYn`).

Built for repeated use on arbitrary datasets: no station name, receiver type, or year is baked into the code.

Runs on **Windows, Linux, and macOS** — the converter is pure Python, only the launchers differ per platform.

## Prerequisite: install Python first

**Python 3.10 or newer must already be on the machine.** The setup scripts build a virtual environment from it — they do not install Python for you. Check what you have:

```
python --version        # Windows
python3 --version       # Linux / macOS
```

If that reports an error, or a version below 3.10, install Python before going any further.

**Windows** — download from [python.org/downloads](https://www.python.org/downloads/) and, in the installer, tick **"Add python.exe to PATH"** on the first screen. Without it the setup script cannot find Python and stops with *"Python 3.10 or newer is required, and must be on PATH"*. If you have already installed it without that box ticked, re-run the installer and choose **Modify**, or add the folder to PATH by hand.

The Microsoft Store build of Python also works.

Windows 10 and 11 are supported. Windows 8.1 and 7 are not — they cannot run Python 3.10+, which `pygnssutils` requires. Windows PowerShell 5.1 (built into Windows 10/11) is enough; PowerShell 7 is not needed.

**Debian / Ubuntu / WSL:**

```bash
sudo apt update && sudo apt install -y python3 python3-venv
```

`python3-venv` matters: without it `python3 -m venv` produces an environment with no pip, and installation fails with *"No module named pip"*. `setup.sh` detects that case and prints the exact package to install.

**Fedora / RHEL:** `sudo dnf install -y python3`  •  **macOS:** `brew install python` (or python.org installer)

## Install (once)

**Windows** — right-click `setup.ps1` → **Run with PowerShell**.

If your execution policy blocks that, run it from a terminal instead:

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

**Linux / macOS / WSL:**

```bash
chmod +x setup.sh convert.sh
./setup.sh
```

Both create a virtual environment in `.venv/` and install `pygnssutils` into it, leaving your system Python untouched. To pick a specific interpreter: `PYTHON=/path/to/python3.12 ./setup.sh`.

Re-run the setup script any time to update the dependency or repair a broken `.venv`.

## Usage

**Windows, easiest** — drag one or more `.ubx` files, or a whole folder, onto `convert.bat`.

**Linux / macOS:**

```bash
./convert.sh /path/to/data          # every .ubx in the folder, one run
./convert.sh a.ubx b.ubx            # several files at once
./convert.sh /data --recursive      # include subfolders
./convert.sh --help                 # full option list
```

**Windows terminal:**

```powershell
$py   = ".\.venv\Scripts\python.exe"
$tool = ".\ubx2rinex.py"

& $py $tool C:\data\survey             # every .ubx in the folder, one run
& $py $tool a.ubx b.ubx c.ubx          # several files at once
& $py $tool C:\data --recursive        # include subfolders
& $py $tool C:\data --outdir C:\out    # write elsewhere
```

Output is written next to each input file unless `--outdir` is given. Files that have already been converted are skipped, and the check happens *before* conversion, so re-running over a large folder stays fast.

### Options

| Option | Purpose |
|---|---|
| `--outdir DIR` | Output folder |
| `--rinex 3.05\|4.02` | RINEX version (default 3.05) |
| `--gnss G,E,C` | Restrict constellations (default: all) |
| `--marker NAME` | Marker name (default: from the file name) |
| `--markertype TYPE` | Marker type (default `GEODETIC`) |
| `--antenna TYPE` | Antenna type for the header |
| `--height METRES` | Antenna height (`ANTENNA: DELTA H/E/N`) |
| `--observer NAME` | Observer / agency |
| `--longname` | Use RINEX 3 long file names (`.rnx`) |
| `--recursive` | Walk subfolders |
| `--force` | Overwrite existing output |

## Detected automatically

| RINEX header record | Source |
|---|---|
| `MARKER NAME` | input file name |
| `REC # / TYPE / VERS` | UBX `MON-VER` (`MOD=`, `FWVER=`) |
| `APPROX POSITION XYZ` | median of `NAV-HPPOSECEF`, falling back to `NAV-POSLLH` |
| `TIME OF FIRST/LAST OBS`, `INTERVAL` | the observation data |
| `.YYo` year suffix | first `RXM-RAWX` / `RXM-RAW` epoch |

## What the log must contain

Raw u-blox messages:

- **`RXM-RAWX`** (or legacy `RXM-RAW`) → observation file
- **`RXM-SFRBX`** → navigation file

Without `RXM-RAWX`/`RXM-RAW` the file is skipped with a clear message; without `RXM-SFRBX` only the observation file is produced. Interleaved NMEA is ignored.

Enable those messages in u-center (`UBX-CFG-MSG`) or via `UBX-CFG-VALSET` before recording.

**Limitation:** u-blox UBX only. Septentrio, Trimble, and NovAtel receivers are not supported — use the vendor's own converter or RTKLIB `convbin`.

## Technical notes

This tool drives the RINEX converter in [`pygnssutils`](https://github.com/semuconsulting/pygnssutils) (*pyrinexconv*, still alpha) and works around four defects in it:

1. **Ephemerides went missing in bulk.** Ephemeris output was gated on a rarely transmitted almanac page — GPS LNAV subframe 4 page 18, BeiDou D1 subframe 5 page 10, QZSS subframe 4/5 page 56 — which arrives only once every ~12 minutes. On a 27-minute BeiDou-rich log this produced *zero* BeiDou ephemerides and only 5 of 7 available GPS ones. An ephemeris needs subframes 1–3 alone; the almanac page is now optional and still contributes header corrections when it does arrive. Fixing this took the same dataset from 33 to 44 ephemerides, BeiDou from 0 to 9.
2. **Observation records were hard-wrapped at 80 columns** with a U+2192 (`→`) continuation character. RINEX 3 puts one satellite per line, and the wrapped form is rejected by RTKLIB and friends.
3. **Navigation PRNs were space-padded** (`E 5`) where RINEX 3 requires zero padding (`E05`).
4. **No `APPROX POSITION XYZ` record**, plus a stray `END OF FILE ... COMMENT` line inside the data block that parsers read as an extra satellite in the final epoch.

Every conversion is read back and summarised: epoch count, satellites per constellation, ephemeris count, satellites lacking an ephemeris, and a warning if any epoch has an inconsistent satellite count.

Satellites present in the `.YYo` but absent from the `.YYn` are usually normal — those were tracked too briefly to download a complete ephemeris subframe set.

## Files

```
ubx2rinex.py    converter (cross-platform)
setup.ps1       one-time install  - Windows
convert.bat     drag & drop       - Windows
setup.sh        one-time install  - Linux/macOS/WSL
convert.sh      launcher          - Linux/macOS/WSL
README.md
.venv/          created by setup.ps1 / setup.sh, not tracked
```

The virtual environment is platform-specific. If you move this folder between Windows and Linux, delete `.venv` and re-run the setup script for that platform — `setup.sh` detects a Windows-built environment (`Scripts/` instead of `bin/`) and rebuilds it for you.
