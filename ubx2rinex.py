"""
ubx2rinex - batch converter from u-blox UBX raw logs to RINEX 3.05 / 4.02.

Usage
-----
    python ubx2rinex.py FILE_OR_FOLDER [FILE_OR_FOLDER ...] [options]

Everything that identifies a dataset is read from the file itself:

    marker name        <- input file name
    receiver / version <- UBX MON-VER
    approx position    <- UBX NAV-HPPOSECEF, falling back to NAV-POSLLH
    file year suffix   <- time of first observation

Nothing is hard-coded to a particular receiver or survey.

Requires
--------
u-blox raw messages in the log:
    RXM-RAWX (or legacy RXM-RAW)  -> observation file
    RXM-SFRBX                     -> navigation file
Interleaved NMEA is ignored. Non-u-blox receivers are not supported.

Why this wrapper exists
-----------------------
It drives pygnssutils' RINEX converter (pyrinexconv, still alpha) and works
around four defects in it:

1. Ephemeris emission is gated on a rarely-transmitted almanac page - GPS LNAV
   subframe 4 page 18, BeiDou D1 subframe 5 page 10, QZSS subframe 4/5 page 56.
   Those arrive once per ~12 minutes, so most satellites never produced an
   ephemeris and BeiDou produced none at all. An ephemeris only needs subframes
   1-3; the almanac page carries header corrections and is now optional.
2. Observation records are hard-wrapped at 80 columns with a U+2192 ("->")
   continuation character. Real RINEX 3 keeps one satellite per line, and
   parsers such as RTKLIB reject the wrapped form.
3. Navigation PRNs are space-padded ("E 5") where RINEX 3 requires zero
   padding ("E05").
4. No APPROX POSITION XYZ record, and a stray "END OF FILE ... COMMENT" line
   inside the data block that parsers read as an extra satellite in the last
   epoch.
"""

import argparse
import re
import struct
import sys
from datetime import datetime, timedelta
from math import cos, radians, sin, sqrt
from pathlib import Path
from statistics import median

GPS_EPOCH = datetime(1980, 1, 6)

try:
    from pygnssutils import prog_callback
    from pygnssutils.globals import CLIAPP
    from pygnssutils.rawnav import RawNav
    from pygnssutils.rawnav_subframes_bds import BDS_SUBFRAMEACQ_MAP
    from pygnssutils.rawnav_subframes_gps import GPS_SUBFRAMEACQ_MAP
    from pygnssutils.rawnav_subframes_qzs import QZS_SUBFRAMEACQ_MAP
    from pygnssutils.rinex_conv import RinexConverter
    from pygnssutils.rinex_conv_nav import RinexConverterNavigation
    from pygnssutils.rinex_globals import NAV, OBS, RINEX_OK, START, TARGET
except ImportError:
    _win = sys.platform == "win32"
    sys.exit(
        "pygnssutils tidak ditemukan.\n"
        + (
            "Jalankan setup.ps1 sekali dulu, lalu gunakan convert.bat "
            "(atau .venv\\Scripts\\python.exe ubx2rinex.py ...)."
            if _win
            else "Jalankan ./setup.sh sekali dulu, lalu gunakan ./convert.sh "
            "(atau .venv/bin/python ubx2rinex.py ...)."
        )
    )

CONT = "\u2192"
EPHTAR = "EPHTAR"
GNSSNAME = {
    "G": "GPS",
    "R": "GLONASS",
    "E": "Galileo",
    "C": "BeiDou",
    "J": "QZSS",
    "S": "SBAS",
    "I": "NavIC",
}
UBX_EXTS = (".ubx", ".bin", ".raw", ".log", ".dat")

# --------------------------------------------------------------- patches
GPS_SUBFRAMEACQ_MAP["LNAV"][EPHTAR] = 0b111  # subframes 1,2,3
BDS_SUBFRAMEACQ_MAP["D1"][EPHTAR] = 0b111
QZS_SUBFRAMEACQ_MAP["LNAV"][EPHTAR] = 0b111

_orig_iono = RinexConverterNavigation._format_ionocorr_3
_orig_time = RinexConverterNavigation._format_timecorr_3


def _safe_iono(self, data):
    """Iono parameters live in the almanac page; skip until it arrives."""
    try:
        _orig_iono(self, data)
    except AttributeError:
        pass


def _safe_time(self, data, source=0):
    try:
        _orig_time(self, data, source)
    except AttributeError:
        pass


def _format_rxmsfrbx(self, sfrdata, sfrmap, formatter, **kwargs):
    """
    Emit the ephemeris as soon as subframes 1-3 are collated, but keep the
    frame alive so the almanac page can still contribute header corrections.
    Records are keyed on (svcode, toc), so re-emitting is idempotent.
    """
    gnss = sfrdata["gnss"]
    svid = sfrdata["svid"]
    sigcode = sfrdata["sigcode"]
    subframeid = sfrdata["subframeid"]
    subframepageid = sfrdata.get("subframepageid", 0)
    subframe = sfrdata["subframe"]
    sfrdict, sfracq = sfrmap.get((subframeid, subframepageid), (None, 0))
    target = sfrmap[TARGET]
    ephtarget = sfrmap.get(EPHTAR, target)
    key = (gnss, svid, sigcode)

    if subframeid == sfrmap[START]:
        self._navstart[key] = True
    if not self._navstart.get(key, False) or sfrdict is None:
        return

    self._navframes[key] = self._navframes.get(key, RawNav(gnss, svid, sigcode))
    nav = self._navframes[key]
    nav.parse(subframe, sfrdict, sfracq)

    if nav.subframeacq & target == target:  # complete frame incl. almanac page
        formatter(self._navframes.pop(key), **kwargs)
        self._navstart.pop(key)
    elif nav.subframeacq & ephtarget == ephtarget:  # ephemeris alone
        formatter(nav, **kwargs)


RinexConverterNavigation._format_ionocorr_3 = _safe_iono
RinexConverterNavigation._format_timecorr_3 = _safe_time
RinexConverterNavigation._format_rxmsfrbx = _format_rxmsfrbx


# ------------------------------------------------------------ ubx probing
def iter_ubx(data: bytes):
    """Yield (class, id, payload) for every checksum-valid UBX frame."""
    n = len(data)
    i = 0
    while i < n - 7:
        if data[i] == 0xB5 and data[i + 1] == 0x62:
            ln = struct.unpack("<H", data[i + 4 : i + 6])[0]
            if i + 8 + ln <= n:
                a = b = 0
                for x in data[i + 2 : i + 6 + ln]:
                    a = (a + x) & 0xFF
                    b = (b + a) & 0xFF
                if a == data[i + 6 + ln] and b == data[i + 7 + ln]:
                    yield data[i + 2], data[i + 3], data[i + 6 : i + 6 + ln]
                    i += 8 + ln
                    continue
        i += 1


def llh_to_ecef(lat_deg, lon_deg, h):
    a, f = 6378137.0, 1 / 298.257223563
    e2 = f * (2 - f)
    lat, lon = radians(lat_deg), radians(lon_deg)
    N = a / sqrt(1 - e2 * sin(lat) ** 2)
    return (
        (N + h) * cos(lat) * cos(lon),
        (N + h) * cos(lat) * sin(lon),
        (N * (1 - e2) + h) * sin(lat),
    )


def probe(path: Path) -> dict:
    """Single pass over the log: raw-message census, receiver id, position."""
    data = path.read_bytes()
    info = {
        "rawx": 0,
        "raw": 0,
        "sfrbx": 0,
        "model": "",
        "firmware": "",
        "xyz": None,
        "year": None,
        "size": len(data),
    }
    hp, llh = [], []
    for cls, mid, p in iter_ubx(data):
        if (cls, mid) == (0x02, 0x15):
            info["rawx"] += 1
            if info["year"] is None and len(p) >= 10:
                # GPS time of the first epoch, matching TIME OF FIRST OBS
                tow, week = struct.unpack("<dh", p[0:10])
                info["year"] = (GPS_EPOCH + timedelta(weeks=week, seconds=tow)).year
        elif (cls, mid) == (0x02, 0x10):
            info["raw"] += 1
            if info["year"] is None and len(p) >= 6:  # legacy RXM-RAW
                tow_ms, week = struct.unpack("<ih", p[0:6])
                info["year"] = (
                    GPS_EPOCH + timedelta(weeks=week, milliseconds=tow_ms)
                ).year
        elif (cls, mid) == (0x02, 0x13):
            info["sfrbx"] += 1
        elif (cls, mid) == (0x0A, 0x04) and len(p) >= 40:  # MON-VER
            for k in range((len(p) - 40) // 30):
                ext = p[40 + k * 30 : 70 + k * 30].split(b"\x00")[0].decode(
                    errors="replace"
                )
                if ext.startswith("MOD="):
                    info["model"] = ext[4:]
                elif ext.startswith("FWVER="):
                    info["firmware"] = ext[6:]
        elif (cls, mid) == (0x01, 0x13) and len(p) >= 28:  # NAV-HPPOSECEF
            ex, ey, ez = struct.unpack("<iii", p[8:20])
            hx, hy, hz = struct.unpack("<bbb", p[20:23])
            hp.append(
                (ex * 0.01 + hx * 1e-4, ey * 0.01 + hy * 1e-4, ez * 0.01 + hz * 1e-4)
            )
        elif (cls, mid) == (0x01, 0x02) and len(p) >= 20:  # NAV-POSLLH
            lon, lat, height = struct.unpack("<iii", p[4:16])
            llh.append((lat * 1e-7, lon * 1e-7, height * 1e-3))

    src = hp or [llh_to_ecef(*v) for v in llh]
    if src:
        info["xyz"] = tuple(median(c[k] for c in src) for k in range(3))
    return info


# ---------------------------------------------------------- post-process
def finalise_obs(raw: Path, dest: Path, xyz):
    """Rejoin wrapped lines, drop stray comments, insert APPROX POSITION XYZ."""
    lines = raw.read_text(encoding="utf-8").splitlines()
    he = next(i for i, l in enumerate(lines) if "END OF HEADER" in l)
    header, year = lines[: he + 1], None

    for l in header:
        if l[60:].startswith("TIME OF FIRST OBS"):
            year = int(l[0:6])

    if xyz and not any(l[60:].startswith("APPROX POSITION XYZ") for l in header):
        rec = f"{xyz[0]:14.4f}{xyz[1]:14.4f}{xyz[2]:14.4f}{'':18}APPROX POSITION XYZ"
        idx = next(
            (i for i, l in enumerate(header) if l[60:].startswith("ANT # / TYPE")), None
        )
        header.insert(idx + 1 if idx is not None else he, rec)

    body = []
    for l in lines[he + 1 :]:
        if l.startswith(CONT):
            if body:
                body[-1] += l[1:]
        elif l[60:].strip() == "COMMENT":
            continue  # bare comment in data block reads as an extra satellite
        elif l.strip():
            body.append(l)

    nsat = len({l[0:3] for l in body if re.match(r"^[GRECJSI]\d{2}", l)})
    for i, l in enumerate(header):
        if l[60:].startswith("# OF SATELLITES"):
            header[i] = f"{nsat:6d}{'':54}# OF SATELLITES"

    raw.unlink()
    dest.write_text(
        "\n".join(header + [b.rstrip() for b in body]) + "\n", encoding="utf-8"
    )
    return year, nsat


def finalise_nav(raw: Path, dest: Path):
    """Zero-pad single-digit PRNs on ephemeris record start lines."""
    out, fixed = [], 0
    for l in raw.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([GRECJSI]) (\d) (\d{4})", l)
        if m:
            l = f"{m.group(1)}0{m.group(2)}" + l[3:]
            fixed += 1
        out.append(l.rstrip())
    raw.unlink()
    dest.write_text("\n".join(out) + "\n", encoding="utf-8")
    return fixed


def summarise(obs: Path, nav: Path | None) -> dict:
    """Read back both products and report what a processing package will see."""
    res = {}
    lines = obs.read_text(encoding="utf-8").splitlines()
    he = next(i for i, l in enumerate(lines) if "END OF HEADER" in l)
    epochs, sats, recs, bad = 0, set(), 0, 0
    declared = seen = 0
    for l in lines[he + 1 :]:
        if l.startswith(">"):
            if epochs and seen != declared:
                bad += 1
            epochs += 1
            m = re.match(r">\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+[\d.]+\s+\d+\s+(\d+)", l)
            declared, seen = (int(m.group(1)) if m else -1), 0
        elif l.strip():
            seen += 1
            recs += 1
            sats.add(l[0:3])
    if epochs and seen != declared:
        bad += 1
    res.update(epochs=epochs, obs_sats=sats, obs_recs=recs, mismatch=bad)

    eph = {}
    if nav is not None and nav.exists():
        for l in nav.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^([GRECJSI])(\d{2}) (\d{4}) (\d{2})", l)
            if m:
                eph.setdefault(m.group(1) + m.group(2), 0)
                eph[m.group(1) + m.group(2)] += 1
    res["eph_sats"] = set(eph)
    res["eph_recs"] = sum(eph.values())
    return res


# ------------------------------------------------------------- one file
def convert(path: Path, args) -> bool:
    print(f"\n{'=' * 72}\n{path.name}  ({path.stat().st_size / 1048576:.2f} MB)")
    info = probe(path)

    if not (info["rawx"] or info["raw"]):
        print("  DILEWATI: tidak ada RXM-RAWX/RXM-RAW, file observasi tidak bisa dibuat.")
        return False
    rec = info["model"] or "UNKNOWN"
    print(
        f"  receiver : {rec} {info['firmware']}".rstrip()
        + f"   |  RAWX {info['rawx']:,}  SFRBX {info['sfrbx']:,}"
    )
    if not info["sfrbx"]:
        print("  catatan  : tidak ada RXM-SFRBX, file navigasi akan kosong.")

    marker = args.marker or path.stem.upper()[:60]
    types = (OBS, NAV) if info["sfrbx"] else (OBS,)
    outdir = Path(args.outdir) if args.outdir else path.parent

    # Decide the output names before converting, so a re-run over a folder
    # skips finished files instead of reprocessing them.
    yy = f"{info['year'] % 100:02d}" if info["year"] else "00"
    if not args.longname:
        obs_dest = outdir / f"{path.stem}.{yy}o"
        nav_dest = (outdir / f"{path.stem}.{yy}n") if info["sfrbx"] else None
        if obs_dest.exists() and not args.force:
            print(f"  DILEWATI: {obs_dest.name} sudah ada (pakai --force untuk menimpa).")
            return False

    rc = RinexConverter(
        CLIAPP,
        rinex_version=args.rinex,
        rinex_types=types,
        gnssfilter=tuple(args.gnss.split(",")) if args.gnss else ("",),
        obsfilter=("",),
        svfilter=("",),
        obssource="u-blox",
        navsource="u-blox",
        metsource="nmea",
        starttime="",
        minobs=0,
        marker=(marker, "", args.markertype),
        antenna=("", args.antenna),
        antennahed=(args.height, 0.0, 0.0),
        receiver=("", rec, info["firmware"] or ""),
        observer=args.observer,
        comments=(f"Converted from u-blox raw log {path.name}",),
        doi="",
        license="",
        station="",
        timecorr=True,
        ionocorr=True,
        eopcorr=True,
        verbosity=0,
    )
    if rc.process_input(infile=path, stopevent=None, progcallback=prog_callback) != RINEX_OK:
        print("  GAGAL: konversi tidak menghasilkan record.")
        return False
    print()

    produced = {rt: Path(f) for rt, (f, _) in rc.outputs.items()}
    outdir.mkdir(parents=True, exist_ok=True)
    tmp_obs = produced[OBS]

    if args.longname:  # keep the RINEX 3 long file names the converter chose
        obs_dest = outdir / tmp_obs.name
        nav_dest = outdir / produced[NAV].name if NAV in produced else None
        if obs_dest.exists() and not args.force and obs_dest != tmp_obs:
            print(f"  DILEWATI: {obs_dest.name} sudah ada (pakai --force untuk menimpa).")
            tmp_obs.unlink()
            if NAV in produced:
                produced[NAV].unlink()
            return False
    elif info["year"] is None:
        # week/tow was unreadable; take the year from the header just written
        for l in tmp_obs.read_text(encoding="utf-8").splitlines():
            if l[60:].startswith("TIME OF FIRST OBS"):
                yy = f"{int(l[0:6]) % 100:02d}"
                break
        obs_dest = outdir / f"{path.stem}.{yy}o"
        nav_dest = (outdir / f"{path.stem}.{yy}n") if NAV in produced else None

    finalise_obs(tmp_obs, obs_dest, info["xyz"])
    if nav_dest:
        finalise_nav(produced[NAV], nav_dest)

    s = summarise(obs_dest, nav_dest)
    obs_sys = {}
    for sv in s["obs_sats"]:
        obs_sys[sv[0]] = obs_sys.get(sv[0], 0) + 1
    print(f"  OBS -> {obs_dest.name}   {s['epochs']:,} epoch, {len(s['obs_sats'])} satelit,"
          f" {s['obs_recs']:,} record")
    print("        " + "  ".join(f"{GNSSNAME.get(k, k)} {v}" for k, v in sorted(obs_sys.items())))
    if nav_dest:
        missing = sorted(s["obs_sats"] - s["eph_sats"])
        print(f"  NAV -> {nav_dest.name}   {s['eph_recs']} ephemeris,"
              f" {len(s['eph_sats'])} satelit")
        if missing:
            print(f"        tanpa ephemeris (terlacak terlalu singkat): {' '.join(missing)}")
    if info["xyz"]:
        print("  APPROX POSITION XYZ  %.4f %.4f %.4f" % info["xyz"])
    if s["mismatch"]:
        print(f"  PERINGATAN: {s['mismatch']} epoch dengan jumlah satelit tidak konsisten.")
    return True


# ------------------------------------------------------------------ cli
def collect(targets, recursive):
    files = []
    for t in targets:
        p = Path(t)
        if any(ch in str(t) for ch in "*?"):
            files += sorted(Path().glob(str(t)))
        elif p.is_dir():
            it = p.rglob("*") if recursive else p.glob("*")
            files += sorted(
                f
                for f in it
                if f.suffix.lower() in UBX_EXTS
                # never descend into virtualenvs or dot-directories: they hold
                # .log/.dat/.bin files that are not GNSS logs
                and not any(part.startswith(".") for part in f.parts)
            )
        elif p.is_file():
            files.append(p)
        else:
            print(f"tidak ditemukan: {t}")
    seen, out = set(), []
    for f in files:
        r = f.resolve()
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser(
        prog="ubx2rinex",
        description="Konversi batch log mentah u-blox UBX menjadi RINEX observation (.YYo) dan navigation (.YYn).",
        epilog=(
            "Contoh:  ubx2rinex.py C:\\data  |  ubx2rinex.py a.ubx b.ubx --outdir C:\\hasil"
            if sys.platform == "win32"
            else "Contoh:  ubx2rinex.py ~/data  |  ubx2rinex.py a.ubx b.ubx --outdir ~/hasil"
        ),
    )
    ap.add_argument("targets", nargs="+", help="file .ubx, folder, atau pola wildcard")
    ap.add_argument("--outdir", default="", help="folder keluaran (default: sebelah file input)")
    ap.add_argument("--rinex", default="3.05", choices=("3.05", "4.02"), help="versi RINEX")
    ap.add_argument("--gnss", default="", help="filter konstelasi, mis. G,E,C (default: semua)")
    ap.add_argument("--marker", default="", help="nama marker (default: dari nama file)")
    ap.add_argument("--markertype", default="GEODETIC", help="tipe marker")
    ap.add_argument("--antenna", default="UNKNOWN", help="tipe antena")
    ap.add_argument("--height", type=float, default=0.0, help="tinggi antena/delta H (meter)")
    ap.add_argument("--observer", default="", help="nama observer/agensi")
    ap.add_argument("--longname", action="store_true", help="pakai nama panjang RINEX 3 (.rnx)")
    ap.add_argument("--recursive", action="store_true", help="telusuri subfolder")
    ap.add_argument("--force", action="store_true", help="timpa keluaran yang sudah ada")
    args = ap.parse_args()

    files = collect(args.targets, args.recursive)
    if not files:
        sys.exit("Tidak ada file untuk dikonversi.")

    print(f"{len(files)} file akan diproses.")
    ok = sum(convert(f, args) for f in files)
    print(f"\n{'=' * 72}\nSelesai: {ok} dari {len(files)} file berhasil dikonversi.")


if __name__ == "__main__":
    main()
