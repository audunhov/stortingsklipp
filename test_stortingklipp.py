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

print("ok")
