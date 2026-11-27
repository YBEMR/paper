"""Frozen engine bindings and full-flow quota-preserving neighborhoods."""
import csv
import gzip
import hashlib
import json
import os
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MI = ROOT.parent / "m1i_generalization"
WORK = Path(os.environ.get("M3A_WORK", ROOT / "work")).resolve()
OUT = ROOT / "data"
os.environ["M1G_RAW"] = str(WORK / "warm")
sys.path.insert(0, str(MI))
from adapter import flow, e, np
from design import REG
from mechanism import WINDOW
from model import transitions

CAP = 32
K = 4
LIMIT = 30
CUTS = (.25, .5, 1, 2, 5, 10, 30)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = e.p1.raw(obj) + b"\n"
    path.write_bytes(gzip.compress(data, compresslevel=6, mtime=0) if path.suffix == ".gz" else data)


def read(path):
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes())


def cases():
    return [v for v in read(REG / "cases.json")["cases"] if v["ambient"] == 35]


def seed(case):
    with open(MI / "data/repetitions.csv") as f:
        row, = [r for r in csv.DictReader(f) if r["case"] == case and r["method"] == "NT"
                and r["repeat"] == "1" and r["regime"] == "60s"]
    key = row["plan"]
    folder = MI / "data/evidence" / case
    with gzip.open(folder / "event_index.csv.gz", "rt") as f:
        ix, = [r for r in csv.DictReader(f) if r["plan"] == key]
    with tarfile.open(folder / "physical.tar.xz") as t:
        plan = t.extractfile(key + "/plan.json").read()
        cert = t.extractfile(key + "/certificate.json").read()
    assert sha(plan) == ix["plan_file_sha256"] and sha(cert) == ix["certificate_file_sha256"]
    cfg = bytes(k + 10*(u == 3) for u,k,_ in json.loads(plan)["rows"][1::3])
    return cfg, json.loads(cert), ix


def cells(c, base):
    groups = []
    for j, group in enumerate(c.eng.groups):
        a = np.asarray(group)
        codes = np.frombuffer(base, dtype=np.uint8)[a]
        freqs = [set(int(k) for k in codes if (k >= 10) == npu) for npu in (False, True)]
        assert all(len(s) <= 1 for s in freqs)
        g, n = (next(iter(s), fallback) for s, fallback in zip(freqs, (0,10)))
        t = c.kinds[a]
        quotas = [int(np.count_nonzero(codes[t == v] >= 10)) for v in range(2)]
        assert c.extension(t, *np.bincount(t, minlength=2), g, n-10, *quotas) == codes.tobytes()
        for v,q in enumerate(quotas):
            ids = a[t == v]
            if 0 < q < len(ids):
                groups.append((j, v, ids, q, g, n))
    return groups


def phase(cfg, cell, off):
    _,_,ids,q,g,n = cell
    marks = np.diff((np.arange(len(ids)+1)*q + off) // len(ids))
    for i,k in zip(ids, np.where(marks, n, g)):
        cfg[i] = int(k)


def distribution(c, base):
    groups = cells(c, base)
    seen = {base}
    out = []
    def add(family, action, cfg):
        cfg = bytes(cfg)
        if cfg not in seen:
            out.append((family, action, cfg))
            seen.add(cfg)
    for name,offset in [("half", lambda n:n//2), ("last", lambda n:n-1)]:
        cfg = bytearray(base)
        for cell in groups:
            phase(cfg, cell, offset(len(cell[2])))
        add("phase", ["all",name], cfg)
    def priority(action):
        return sha((c.label + "/" + "/".join(map(str,action))).encode())
    ph, swaps = [], []
    for slot,(_,_,ids,q,g,n) in enumerate(groups):
        for p in sorted({len(ids)//4,len(ids)//2,3*len(ids)//4,len(ids)-1}):
            ph.append((slot, p))
        gpu = [int(i) for i in ids if base[i] == g]
        npu = [int(i) for i in ids if base[i] == n]
        swaps.extend((i,l) for i in gpu for l in npu)
    for slot,p in sorted(ph,key=priority):
        if len(out) >= 16:
            break
        cfg = bytearray(base)
        cell = groups[slot]
        phase(cfg, cell, p)
        add("phase", [cell[0],cell[1],p],cfg)
    count = len(out)
    for i,l in sorted(swaps,key=priority):
        if len(out)-count >= 16:
            break
        cfg = bytearray(base)
        cfg[i],cfg[l] = cfg[l],cfg[i]
        add("swap", [i,l], cfg)
    assert len(out) <= CAP
    return out


def lower(c, base):
    out = []
    for j,group in enumerate(c.eng.groups):
        for u in (2,3):
            ids = [i for i in group if (base[i] >= 10) == (u == 3)]
            if ids and base[ids[0]] not in (0,10):
                cfg = bytearray(base)
                for i in ids:
                    cfg[i] -= 1
                out.append(("lower",[j,u],bytes(cfg)))
    assert len(out) <= CAP
    return out


def evaluate(c,cfg,thermal):
    r = c.ledger(cfg,0,c.p.horizon,2500,True,thermal,True)
    slack,drain = int(r[-1]),int(np.max(r[6]+c.args[4]))
    info = dict(timing=bool(r[0]),slack_ticks=slack,drain_tick=drain)
    if not r[0]:
        return info
    ref = r[1]+c.base*c.p.horizon/WINDOW
    info["E35"] = ref
    if thermal:
        temp = c.p.initial
        peak = max(temp)
        correction = 0.
        for j,m in enumerate(r[8]):
            dt = min(2500,c.p.horizon-2500*j)/WINDOW
            new = c.propagate(temp,m,dt)
            correction += dt*(m[4:]@((new+temp)/2-35))
            peak = max(peak,max(new))
            temp = new
        info.update(pred_E=ref+correction,pred_peak=peak)
    return info


def ranking(rec, thermal):
    a,cfg = rec
    tail = (-a["slack_ticks"], a["drain_tick"],cfg)
    if thermal:
        return (max(0.,a["pred_peak"]-80),round(a["pred_E"],10),a["pred_peak"],*tail)
    return (round(a["E35"],10),*tail)


def improves(a,b):
    return a["metrics"]["status"] == "SAFE" and a["metrics"]["E_bounds"][1] < b["metrics"]["E_bounds"][0]


def bind(item):
    return flow(item,WORK / "native")


def verify_seed(c,cfg,arch,ix):
    cert,arr = c.certify(cfg)
    assert cert["plan_sha256"] == arch["plan_sha256"] and cert["switches"] == [tuple(x) for x in arch["switches"]]
    m,old = cert["metrics"],arch["metrics"]
    assert m["status"] == old["status"] == "SAFE"
    assert cert["E35_exact"] == arch["E35_exact"]
    diff = {}
    for k,v in old.items():
        if k != "status":
            diff[k] = float(np.max(np.abs(np.asarray(m[k])-v)))
    assert max(diff.values()) < 1e-6, diff
    return cert, dict(archived_plan=arch["plan_sha256"],cfg_sha=sha(cfg),archived_array=ix["event_array_sha256"],
                      replay_array=sha(arr.tobytes()),max_abs_by_field=diff)
