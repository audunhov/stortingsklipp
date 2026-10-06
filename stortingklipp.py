#!/usr/bin/env python3
"""Hent klipp fra Stortingets nett-TV direktestrøm (12 timers DVR)."""

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

OSLO = ZoneInfo("Europe/Oslo")
QBRICK = "https://video.qbrick.com/api/v1/public/accounts/AccrjW9C7ikYk2xPM5xJ4Frag/medias/{}"

ROM = {
    "sal": ("f7ad5699-00090415-92a5c5be", "Stortingssalen"),
    "hoering1": ("00adbf51-00090415-962d2f17", "Høringssal 1"),
    "hoering2": ("3f267171-00090415-c42c3d0b", "Høringssal 2"),
    "n202": ("093e7254-00090415-ad91393a", "Høringssal N-202"),
    "arrangement": ("0e817c64-8fce-4a0e-8106-0a49324bcae6", "Arrangementer"),
}


def hent(url):
    req = Request(url, headers={"User-Agent": "stortingklipp/1.0"})
    with urlopen(req, timeout=30) as r:
        return r.read().decode()


def master_url(media_id):
    data = json.loads(hent(QBRICK.format(media_id)))
    for res in data["asset"]["resources"]:
        if res["type"] == "index":
            return res["renditions"][0]["links"][0]["href"]
    raise SystemExit("fant ingen HLS-strøm for dette rommet")


def variant(master, hoyde):
    best, best_h = None, -1
    lines = hent(master).splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF") and i + 1 < len(lines):
            m = re.search(r"RESOLUTION=\d+x(\d+)", line)
            h = int(m.group(1)) if m else 0
            if hoyde and h > hoyde:
                continue
            if h > best_h:
                best, best_h = urljoin(master, lines[i + 1]), h
    if not best:
        raise SystemExit(f"ingen strøm med høyde ≤ {hoyde}")
    return best, best_h


def segmenter(tekst, base):
    segs, pdt = [], None
    lines = tekst.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-PROGRAM-DATE-TIME:"):
            pdt = datetime.fromisoformat(line.split(":", 1)[1].replace("Z", "+00:00"))
        elif line.startswith("#EXTINF:"):
            dur = float(line[8:].split(",")[0])
            segs.append((pdt, dur, urljoin(base, lines[i + 1])))
    return segs


def parse_tid(tekst, naa):
    tekst = tekst.strip()
    if tekst == "nå":
        return naa
    m = re.fullmatch(r"(\d+)([smh])", tekst)
    if m:
        sek = int(m.group(1)) * {"s": 1, "m": 60, "h": 3600}[m.group(2)]
        return naa - timedelta(seconds=sek)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%H:%M:%S", "%H:%M"):
        try:
            dt = datetime.strptime(tekst, fmt)
        except ValueError:
            continue
        if "%Y" not in fmt:
            dt = naa.replace(hour=dt.hour, minute=dt.minute, second=dt.second, microsecond=0)
        return dt.replace(tzinfo=OSLO)
    raise SystemExit(f"forstår ikke tiden: {tekst}")


def velg(segs, start, ende):
    return [s for s in segs if s[0] < ende and s[0] + timedelta(seconds=s[1]) > start]


def fremdrift(linje, varighet):
    """Parse en -progress-linje fra ffmpeg til prosent (0-100), eller None."""
    m = re.fullmatch(r"out_time_(?:us|ms)=(-?\d+)\s*", linje)
    if not m or varighet <= 0:
        return None
    return min(100, max(0, int(m.group(1)) * 100 // int(varighet * 1e6)))


def skriv_lokale(valgt, path):
    with open(path, "w") as f:
        f.write("#EXTM3U\n#EXT-X-VERSION:3\n")
        f.write(f"#EXT-X-TARGETDURATION:{int(max(s[1] for s in valgt)) + 1}\n")
        f.write("#EXT-X-MEDIA-SEQUENCE:0\n#EXT-X-PLAYLIST-TYPE:VOD\n")
        for _, dur, url in valgt:
            f.write(f"#EXTINF:{dur},\n{url}\n")
        f.write("#EXT-X-ENDLIST\n")


def main():
    p = argparse.ArgumentParser(description="Hent klipp fra Stortingets nett-TV direktestrøm.")
    p.add_argument("fra", nargs="?", help="start: HH:MM[:SS], 15m (= for 15 min siden) eller 'YYYY-MM-DD HH:MM'")
    p.add_argument("til", nargs="?", default="nå", help="slutt (standard: nå)")
    p.add_argument("--rom", default="sal", choices=ROM, help="hvilken sending (standard: sal)")
    p.add_argument("--height", type=int, default=0, help="maks høyde i px (standard: best)")
    p.add_argument("-o", "--ut", help="utfilnavn")
    p.add_argument("--list", action="store_true", help="vis rom og avslutt")
    a = p.parse_args()

    if a.list:
        for navn, (_, beskrivelse) in ROM.items():
            print(f"{navn:12} {beskrivelse}")
        return
    if not a.fra:
        p.error("krever starttid, f.eks. 13:05 eller 15m")
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg finnes ikke")

    naa = datetime.now(OSLO)
    start, ende = parse_tid(a.fra, naa), parse_tid(a.til, naa)
    if ende <= start:
        raise SystemExit("slutt må være etter start")

    media_id, beskrivelse = ROM[a.rom]
    url, hoyde = variant(master_url(media_id), a.height)
    segs = segmenter(hent(url), url)
    if not segs:
        raise SystemExit("ingen segmenter i strømmen")

    eldste = segs[0][0].astimezone(OSLO)
    nyeste = (segs[-1][0] + timedelta(seconds=segs[-1][1])).astimezone(OSLO)
    if not eldste <= start < nyeste:
        raise SystemExit(
            f"ingen innhold i dette tidsrommet — strømmen dekker "
            f"{eldste:%d.%m %H:%M} → {nyeste:%H:%M:%S}"
        )
    ende = min(ende, nyeste)
    valgt = velg(segs, start, ende)

    ut = Path(a.ut or f"klipp_{a.rom}_{start:%H-%M-%S}_{ende:%H-%M-%S}.mp4")
    local = tempfile.NamedTemporaryFile("w", suffix=".m3u8", delete=False)
    skriv_lokale(valgt, local.name)
    local.close()

    varighet = (ende - start).total_seconds()
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-protocol_whitelist", "file,https,tcp,tls,crypto",
        "-ss", f"{(start - valgt[0][0]).total_seconds():.3f}",
        "-t", f"{varighet:.3f}",
        "-i", local.name,
        "-c", "copy", "-movflags", "+faststart", "-progress", "pipe:1", str(ut),
    ]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
        siste = -1
        for line in p.stdout or ():
            prosent = fremdrift(line, varighet)
            if prosent is not None and prosent != siste:
                siste = prosent
                print(f"prosent:{prosent}", flush=True)
        if p.wait():
            raise SystemExit(f"ffmpeg feilet ({p.returncode})")
    finally:
        Path(local.name).unlink(missing_ok=True)
    print(f"{ut}  {beskrivelse} {hoyde}p  {start:%H:%M:%S}→{ende:%H:%M:%S} ({varighet:.0f}s)")


if __name__ == "__main__":
    main()
