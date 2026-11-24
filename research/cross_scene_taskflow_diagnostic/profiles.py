"""Freeze exact profile inputs using JSON decimal lexemes and Git blob identities."""
import argparse
import csv
import hashlib
import json
import math
import statistics
import subprocess
from collections import defaultdict
from fractions import Fraction as Q
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config" / "p1_frozen.json"
CFG = json.loads(CONFIG.read_text(encoding="utf-8"), parse_float=Q)
IDS = tuple(CFG["instances"])


def dump(path, data):
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def table(path, rows):
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]),lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def blob(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def ticks(ms):
    return math.ceil(ms * 10)


def generate(cache):
    gpu = CFG["gpu"]
    groups = defaultdict(list)
    sources = []
    for path, expected in CFG["edge_files"].items():
        data = (cache / Path(path).name).read_bytes()
        actual = blob(data)
        if actual != expected:
            raise ValueError((path, expected, actual))
        rows = json.loads(data, parse_float=Q)
        selected = []
        net, temp, _ = path.split("/")
        for index, row in enumerate(rows):
            if all((row | row["dvfs_config"]).get(k) == v for k,v in gpu["filters"].items()):
                assert row["benchmark"] == net
                f = Q(row["dvfs_config"]["gpu_freq"], 1000000)
                assert f in gpu["freq_MHz"]
                groups[net,temp,f].append(row)
                selected.append([index,str(f)])
        sources.append(dict(path=path,expected=expected,actual=actual,bytes=len(data),selected=selected))
    history = []
    for path, ident in CFG["history"].items():
        data = git("cat-file","blob",ident)
        actual = blob(data)
        assert actual == ident
        tree = git("ls-tree","--full-tree",CFG["base"],path).decode().strip().split()
        if "cloud_mechanism" not in path:
            assert tree and tree[2]==ident
        history.append(dict(path=path,expected=ident,actual=actual,at_code_base=bool(tree and tree[2]==ident)))
    gr = []
    for ni,net in enumerate(("resnet","mobilenetv2")):
        part = []
        for k,f in enumerate(gpu["freq_MHz"]):
            lo,hi = (groups[net,t,f] for t in ("25","70"))
            assert len(lo) == len(hi) == 1
            lo,hi = lo[0],hi[0]
            def paired(row):
                t = row["temperature"]
                temp = (Q(t["before"]["gpu"])+t["after"]["gpu"])/2
                return temp, statistics.mean(row["power_readings"]["p_gpu"][4:-1])
            tl,pl = paired(lo)
            th,ph = paired(hi)
            slope = (ph-pl)/(th-tl)
            part.append(dict(stage="AB"[ni]+".main",k=k,MHz=f,median_low_ms=statistics.median(lo["runtime_ms"]),
                             observed_max_ms=max(lo["runtime_ms"]+hi["runtime_ms"]),T_low=tl,T_high=th,
                             P_low=pl,P_high=ph,secant=slope,P35=pl+(35-tl)*slope))
        for row in part:
            f = row["MHz"]
            x = (f-gpu["freq_MHz"][0])/(gpu["freq_MHz"][-1]-gpu["freq_MHz"][0])
            idle = Q("0.4")+Q("0.5")*x
            slope = Q(".004")*(1+x)
            norm = gpu["ref_W"][ni]/part[-1]["P35"]
            denom = part[-1]["median_low_ms"]
            d = gpu["ref_ms"][ni]*row["median_low_ms"]/denom
            dm = gpu["ref_ms"][ni]*row["observed_max_ms"]/denom
            row.update(compute_ms=d,max_compute_ms=dm,ticks=ticks(d+Q(".4")),max_ticks=ticks(dm+Q(".4")),
                       idle_W=idle,idle_slope=slope,busy_W=row["P35"]*norm,busy_slope=row["secant"]*norm)
        gr.extend(part)
    assert len(groups)==40
    cn = []
    for key in ("cpu","npu"):
        dom = CFG[key]
        for stage,(dh,alpha,qh) in dom["stages"].items():
            for k,(f,v) in enumerate(zip(dom["f"],dom["v"])):
                d = dh*(1-alpha+alpha*dom["f"][-1]/f)
                q = qh*(v/dom["v"][-1])**2*f/dom["f"][-1]
                base = Q(dom["base"][k])/(2 if key=="cpu" else 1)
                slope = dom["slope"][k]
                cn.append(dict(stage=stage,domain=key,k=k,GHz=f,compute_ms=d,ticks=ticks(d+(Q(".4") if key=="npu" else 0)),
                               idle_W=base,idle_slope=slope,activity_W=q,busy_W=base+q,busy_slope=slope))
    dump("config/profile_sources.json",dict(repository=CFG["edge_repo"],commit=CFG["edge_commit"],files=sources,history=history))
    table("config/gpu_profiles.csv",gr)
    table("config/cpu_npu_profiles.csv",cn)


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


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("cache",type=Path)
    generate(parser.parse_args().cache)
