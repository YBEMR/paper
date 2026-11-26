"""Request-only adapter of P1 profiles.py (generation rule preserved).
The upstream profile-generation code is not executed; original frozen CSVs and JSON are used.
Request CSV blob IDs are independently checked by preflight.py before any scheduling.
"""
import csv, math, json, hashlib
from pathlib import Path
from fractions import Fraction as Q
ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config" / "p1_frozen.json"
CFG = json.loads(CONFIG.read_text(encoding="utf-8"), parse_float=Q)

def ticks(ms):
    return math.ceil(ms * 10)

def requests(case):
    scenes,seconds,ta,c,*variant = CFG["instances"][case]
    length = seconds*1000
    rows = []
    for i,scene in enumerate(scenes):
        for typ in "AB":
            rate = {"light10":10,"light20":20}.get(scene,20 if typ=="A" else {"L":10,"M":20,"H":30}.get(scene))
            period = Q(1000,rate)
            for n in range(1,2 if case=="D0" else 3):
                t = i*length + (n-1)*period/2
                while t<(i+1)*length:
                    rows.append(dict(stream=typ+str(n),scene=i,kind=typ,release_ms=t,deadline_ms=t+(period if case=="H3" else 300),
                                     release_tick=ticks(t),deadline_tick=math.floor(10*(t+(period if case=="H3" else 300)))))
                    t += period
    rows.sort(key=lambda r:(r["release_ms"],r["stream"]))
    return [dict(request=i,**row) for i,row in enumerate(rows)]
