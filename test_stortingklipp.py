#!/usr/bin/env python3
"""Selvtest: python3 test_stortingklipp.py"""

import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from stortingklipp import OSLO, parse_tid, segmenter, skriv_lokale, velg

NAA = datetime(2026, 10, 6, 12, 0, tzinfo=OSLO)

# parse_tid
assert parse_tid("13:05", NAA) == datetime(2026, 10, 6, 13, 5, tzinfo=OSLO)
assert parse_tid("07:30:15", NAA) == datetime(2026, 10, 6, 7, 30, 15, tzinfo=OSLO)
assert parse_tid("2026-10-05 09:00", NAA) == datetime(2026, 10, 5, 9, 0, tzinfo=OSLO)
assert parse_tid("2026-10-05 09:00:30", NAA) == datetime(2026, 10, 5, 9, 0, 30, tzinfo=OSLO)
assert parse_tid("nå", NAA) == NAA
assert parse_tid("15m", NAA) == NAA - timedelta(minutes=15)
assert parse_tid("90s", NAA) == NAA - timedelta(seconds=90)
assert parse_tid("2h", NAA) == NAA - timedelta(hours=2)
try:
    parse_tid("halv tolv", NAA)
except SystemExit:
    pass
else:
    raise AssertionError("ugyldig tid skulle feile")

# segmenter
PL = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:6
#EXT-X-MEDIA-SEQUENCE:100
#EXT-X-PROGRAM-DATE-TIME:2026-10-06T10:00:00.000Z
#EXTINF:6,
seg100.ts
#EXT-X-PROGRAM-DATE-TIME:2026-10-06T10:00:06.000Z
#EXTINF:6,
seg101.ts
#EXT-X-PROGRAM-DATE-TIME:2026-10-06T10:00:12.000Z
#EXTINF:5.5,
seg102.ts
"""
BASE = "https://cdn.example/stortingssalen_5505/chunks.m3u8"
segs = segmenter(PL, BASE)
assert len(segs) == 3
assert segs[0][0] == datetime(2026, 10, 6, 10, 0, tzinfo=ZoneInfo("UTC"))
assert segs[2][1] == 5.5
assert segs[1][2] == "https://cdn.example/stortingssalen_5505/seg101.ts"

# velg: segment må overlappe [start, ende)
start = datetime(2026, 10, 6, 10, 0, 7, tzinfo=ZoneInfo("UTC"))
ende = datetime(2026, 10, 6, 10, 0, 13, tzinfo=ZoneInfo("UTC"))
valgt = velg(segs, start, ende)
assert [s[2].rsplit("/", 1)[1] for s in valgt] == ["seg101.ts", "seg102.ts"]
assert velg(segs, ende, ende) == [segs[2]]  # punktet 10:00:13 ligger i seg102
assert velg(segs, datetime(2026, 10, 6, 11, 0, tzinfo=ZoneInfo("UTC")), datetime(2026, 10, 6, 12, 0, tzinfo=ZoneInfo("UTC"))) == []
assert velg(segs, segs[-1][0] + timedelta(seconds=6), ende) == []

# skriv_lokale
tmp = tempfile.NamedTemporaryFile("w", suffix=".m3u8", delete=False)
skriv_lokale(valgt, tmp.name)
tekst = open(tmp.name).read()
assert tekst.startswith("#EXTM3U\n")
assert tekst.rstrip().endswith("#EXT-X-ENDLIST")
assert tekst.count("#EXTINF:") == 2
assert "https://cdn.example/stortingssalen_5505/seg101.ts" in tekst
assert "PROGRAM-DATE-TIME" not in tekst

# web: Range, HEAD
import http.client
import threading
from pathlib import Path

import web

KLIPP_TMP = Path(tempfile.mkdtemp())
(KLIPP_TMP / "x.mp4").write_bytes(b"0123456789")
web.KLIPP = KLIPP_TMP
srv = web.ThreadingHTTPServer(("127.0.0.1", 0), web.H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1])


def be(headers=None):
    conn.request("GET", "/fil/x.mp4", headers=headers or {})
    r = conn.getresponse()
    return r.status, dict(r.getheaders()), r.read()


kode, h, kropp = be()
assert (kode, h["Accept-Ranges"], kropp) == (200, "bytes", b"0123456789")
kode, h, kropp = be({"Range": "bytes=2-5"})
assert (kode, h["Content-Range"], h["Content-Length"], kropp) == (206, "bytes 2-5/10", "4", b"2345")
kode, h, kropp = be({"Range": "bytes=7-"})
assert (kode, h["Content-Range"], kropp) == (206, "bytes 7-9/10", b"789")
kode, h, kropp = be({"Range": "bytes=-3"})
assert (kode, h["Content-Range"], kropp) == (206, "bytes 7-9/10", b"789")
kode, h, kropp = be({"Range": "bytes=0-100"})
assert (kode, h["Content-Range"], kropp) == (206, "bytes 0-9/10", b"0123456789")
kode, h, kropp = be({"Range": "bytes=99-"})
assert (kode, h["Content-Range"], kropp) == (416, "bytes */10", b"")
kode, _, kropp = be({"Range": "bytes=0-1,3-4"})
assert (kode, kropp) == (200, b"0123456789")
conn.request("HEAD", "/fil/x.mp4")
r = conn.getresponse()
assert (r.status, r.getheader("Content-Length"), r.read()) == (200, "10", b"")
conn.request("HEAD", "/fil/gir.zip")
r = conn.getresponse()
assert r.status == 404 and int(r.getheader("Content-Length") or 0) > 0 and not r.read()
conn.close()
srv.shutdown()

# talerliste: stopp ved tids-hoppen, så gårsdagens innlegg (feil datostempel) skjules
import json


def dato(dag, h, m, s=0):
    return "/Date(%d)/" % int(datetime(2026, 10, dag, h, m, s, tzinfo=OSLO).timestamp() * 1000)


web.hent = lambda url: json.dumps({"taler_liste": [
    {"rekkefolge_nummer": 1, "rekkefolge_status": 1, "start_tid": dato(6, 10, 8), "taler_person_id": "GAMMEL1"},
    {"rekkefolge_nummer": 2, "rekkefolge_status": 1, "start_tid": dato(6, 21, 57), "taler_person_id": "GAMMEL2"},
    {"rekkefolge_nummer": 3, "rekkefolge_status": 1, "start_tid": dato(6, 10, 3, 37),
     "taler_person_id": "JGS", "taler_rolle": "Statsminister"},
    {"rekkefolge_nummer": 4, "rekkefolge_status": 1, "start_tid": dato(6, 10, 17), "taler_person_id": "SYL"},
    {"rekkefolge_nummer": 5, "rekkefolge_status": 3, "start_tid": dato(6, 11, 0), "taler_person_id": "IKKE"},
]})
rad = web.talerliste()
assert [t["taler_person_id"] for _, _, t in rad] == ["JGS", "SYL"]
assert rad[0][0] == datetime(2026, 10, 6, 10, 3, 37, tzinfo=OSLO)
assert rad[0][1] == rad[1][0]  # slutt = neste innlegg

print("ok")