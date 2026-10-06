#!/usr/bin/env python3
"""Webgrensesnitt for stortingklipp: python3 web.py [--host H] [--port P]"""

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote
from zoneinfo import ZoneInfo

from stortingklipp import OSLO, ROM, hent, parse_tid

BOK = Path(__file__).resolve().parent
KLIPP = BOK / "klipp"
LEVETID = 300
MAKS_SEK = 2 * 3600
TALERLISTE = "https://data.stortinget.no/eksport/talerliste?format=JSON"
DAGENS = "https://data.stortinget.no/eksport/dagensrepresentanter?format=JSON"
PERSON = "https://data.stortinget.no/eksport/person?personid={}&format=JSON"


def epos(tekst):
    m = re.match(r"/Date\((-?\d+)", tekst or "")
    if not m:
        return None
    return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=ZoneInfo("UTC"))


_dagens = None
_ekstra = {}


def personnavn(pid):
    global _dagens
    if _dagens is None:
        try:
            data = json.loads(hent(DAGENS))
            _dagens = {r["id"]: f'{r["fornavn"]} {r["etternavn"]}' for r in data["dagensrepresentanter_liste"]}
        except Exception:
            _dagens = {}
    if pid in _dagens:
        return _dagens[pid]
    if pid not in _ekstra:
        try:
            r = json.loads(hent(PERSON.format(pid)))
            _ekstra[pid] = f'{r["fornavn"]} {r["etternavn"]}' if r.get("fornavn") else pid
        except Exception:
            _ekstra[pid] = pid
    return _ekstra[pid]


def talerliste():
    """Startede innlegg i Stortingssalen i dag, nyest først. Slutt = neste innlegg."""
    data = json.loads(hent(TALERLISTE))
    naa = datetime.now(OSLO)
    rad = []
    for t in data.get("taler_liste") or []:
        if t.get("rekkefolge_status") == 3:
            continue
        st = epos(t.get("start_tid"))
        if not st:
            continue
        st = st.astimezone(OSLO)
        if st > naa:
            continue
        rad.append((st, t))
    rad.sort(key=lambda r: r[0])
    ut = []
    for i, (st, t) in enumerate(rad):
        slutt = rad[i + 1][0] if i + 1 < len(rad) else naa
        if slutt <= st:
            slutt = st + timedelta(seconds=60)
        ut.append((st, slutt, t))
    return ut


def forside():
    romvalg = "".join(
        f'<option value="{k}"{" selected" if k == "sal" else ""}>{html.escape(v[1])}</option>'
        for k, v in ROM.items()
    )
    try:
        rader = talerliste()
    except Exception as e:
        rader = []
        innlegg = f"<p><em>Talerlisten er utilgjengelig: {html.escape(str(e))}</em></p>"
    else:
        innlegg = "" if rader else "<p><em>Ingen startede innlegg i Stortingssalen.</em></p>"
    rader = list(reversed(rader))
    for st, slutt, t in rader:
        dur = int((slutt - st).total_seconds())
        meta = " · ".join(x for x in [t.get("taler_parti_id") or "", t.get("taler_rolle") or ""] if x)
        etikett = f"{st:%H:%M} {html.escape(personnavn(t['taler_person_id']))}"
        if meta:
            etikett += f" ({html.escape(meta)})"
        etikett += f" {dur // 60}:{dur % 60:02d}"
        innlegg += f"""<form method="post" action="/klipp">
<input type="hidden" name="rom" value="sal">
<input type="hidden" name="fra" value="{st:%Y-%m-%d %H:%M:%S}">
<input type="hidden" name="til" value="{slutt:%Y-%m-%d %H:%M:%S}">
<button>{etikett}</button>
</form>
"""
    return f"""<!doctype html>
<html lang="no"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stortingklipp</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:44rem;margin:1.5rem auto;padding:0 1rem}}
form.innlegg{{margin:.2rem 0}}
button{{width:100%;text-align:left;padding:.5rem;font:inherit;cursor:pointer}}
video{{width:100%;margin-top:1rem}}
input,select{{font:inherit;padding:.4rem}}
label{{display:block;margin:.6rem 0 .2rem}}
</style></head><body>
<h1>Stortingklipp</h1>
<h2>Tidligere innlegg i Stortingssalen</h2>
{innlegg}
<h2>Manuelt</h2>
<form method="post" action="/klipp">
<label>Sending</label><select name="rom">{romvalg}</select>
<label>Fra</label><input name="fra" placeholder="13:05, 15m eller 2026-10-05 09:00" required>
<label>Til</label><input name="til" value="nå">
<label>Maks høyde i px (valgfri)</label><input name="height" type="number" min="1">
<p><button>Lag klipp</button></p>
</form>
</body></html>"""


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def gjor(self, kode, innhold, ctype="text/html; charset=utf-8"):
        self.send_response(kode)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(innhold)))
        self.end_headers()
        self.wfile.write(innhold)

    def side(self, kode, tittel, kropp):
        doc = f"""<!doctype html>
<html lang="no"><head><meta charset="utf-8"><title>{html.escape(tittel)}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:44rem;margin:1.5rem auto;padding:0 1rem}}
video{{width:100%}}</style></head><body>{kropp}<p><a href="/">Tilbake</a></p></body></html>"""
        self.gjor(kode, doc.encode())

    def feil(self, melding):
        self.side(400, "Feil", f"<h1>Klipp feilet</h1><pre>{html.escape(melding)}</pre>")

    def do_GET(self):
        sti = unquote(self.path.split("?")[0])
        if sti == "/":
            self.gjor(200, forside().encode())
        elif sti.startswith("/fil/"):
            self.fil(sti[5:])
        else:
            self.side(404, "Ikke funnet", "<h1>404</h1>")

    def fil(self, navn):
        p = (KLIPP / navn).resolve()
        if not navn or "/" in navn or p.parent != KLIPP.resolve() or not p.is_file():
            self.side(404, "Ikke funnet",
                      "<h1>Filen finnes ikke</h1><p>Klipp slettes 5 minutter etter generering.</p>")
            return
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(p.stat().st_size))
        self.end_headers()
        with open(p, "rb") as f:
            shutil.copyfileobj(f, self.wfile)

    def do_POST(self):
        if self.path.split("?")[0] != "/klipp":
            self.side(404, "Ikke funnet", "<h1>404</h1>")
            return
        skjema = parse_qs(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode())

        def f(n, d=""):
            return skjema.get(n, [d])[0].strip()

        rom, fra, til, height = f("rom", "sal"), f("fra"), f("til", "nå"), f("height")
        if rom not in ROM:
            self.feil(f"ukjent rom: {rom}")
            return
        if not fra:
            self.feil("starttid mangler")
            return
        if height and not height.isdigit():
            self.feil("høyde må være et tall")
            return
        naa = datetime.now(OSLO)
        try:
            start, ende = parse_tid(fra, naa), parse_tid(til, naa)
        except SystemExit as e:
            self.feil(str(e))
            return
        if ende <= start:
            self.feil("slutt må være etter start")
            return
        if (ende - start).total_seconds() > MAKS_SEK:
            self.feil("maks 2 timer per klipp")
            return

        navn = f"klipp_{rom}_{start:%Y%m%d-%H%M%S}_{uuid.uuid4().hex[:6]}.mp4"
        cmd = [sys.executable, str(BOK / "stortingklipp.py"), fra, til, "--rom", rom, "-o", str(KLIPP / navn)]
        if height:
            cmd += ["--height", height]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=BOK)
        if r.returncode != 0:
            self.feil((r.stderr or r.stdout).strip())
            return
        threading.Timer(LEVETID, lambda: (KLIPP / navn).unlink(missing_ok=True)).start()
        melding = html.escape((r.stdout or "").strip())
        self.side(200, "Klipp klart", f"""<h1>Klipp klart</h1>
<p>{melding}</p>
<video controls src="/fil/{navn}"></video>
<p><a href="/fil/{navn}" download>Last ned</a> — slettes om 5 minutter</p>""")


def main():
    p = argparse.ArgumentParser(description="Webgrensesnitt for stortingklipp.")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    a = p.parse_args()
    KLIPP.mkdir(exist_ok=True)
    for f in KLIPP.iterdir():
        if f.is_file():
            f.unlink(missing_ok=True)
    srv = ThreadingHTTPServer((a.host, a.port), H)
    print(f"http://{a.host}:{a.port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
