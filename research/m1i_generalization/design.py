"""Deterministic, performance-blind selection from the frozen repository."""
import csv
import hashlib
import io
import itertools
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
BASE = "0c3157f41e55afa55670262e267acfb071dfd68f"
M1 = ROOT.parent / "m1_transient_thermal_quota_20261126"
PROFILE = M1 / "frozen/p1"
REG = ROOT / "registration"
METHODS = ("NT", "NC", "ZQ-Beam", "C2")

def sha(body):
    return hashlib.sha256(body).hexdigest()

def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+"\n", encoding="utf8")

def history():
    from profiles import CFG, requests
    names = subprocess.check_output(["git","ls-tree","-r","--name-only",BASE],cwd=REPO).decode().splitlines()
    hist = []
    def record(rows, source, physical):
        count = Counter(int(r["release_tick"])//10000 for r in rows)
        if set(count.values()) <= {60,100}:
            word = "".join({60:"L",100:"H"}[count[j]] for j in range(len(count)))
            normalized = [(str(r["stream"]),str(r["kind"]),str(r["release_tick"]),str(r["deadline_tick"])) for r in rows]
            hist.append(dict(word=word, requests=len(rows), source=source, source_sha256=physical,
                             traffic_sha256=sha(json.dumps(normalized,separators=(",",":")).encode())))
    for name in names:
        if re.search(r"research/m1[^/]*/(?:data/validation_inputs/V\d+_[LH]+|inputs/L\d+)\.csv$",name):
            body = (REPO/name).read_bytes()
            record(list(csv.DictReader(body.decode("utf-8-sig").splitlines())), name, sha(body))
    # Other P1 scenario recipes, including alternating R320/R800 and blocked scenes.
    import preflight
    for label, conf in CFG["instances"].items():
        if set(conf[0]) <= {"L","H"} and conf[1]>=1 and int(conf[1])==conf[1]:
            rows=requests(label)
            record(rows,"frozen P1/preflight recipe "+label,sha(csv_bytes(rows)))
    # Identify any additional explicit V-size_order histories in the full tree.
    archive_words={w for name in names for w in re.findall(r"(?:V\d+_)([LH]{2,})(?![LH])",name)}
    assert archive_words <= {r["word"] for r in hist},archive_words-{r["word"] for r in hist}
    return hist

def main():
    sys.path[:0]=[str(M1/"frozen"),str(PROFILE)]
    from profiles import CFG, requests
    REG.mkdir(exist_ok=True); (REG/"inputs").mkdir(exist_ok=True)
    hist=history()
    (REG/"history.csv").write_bytes(csv_bytes(hist))
    used={r["word"] for r in hist}
    strata=[("A",n//2,n//2,s) for n in (6,8,10) for s in "LH"]
    strata += [("B",5,3,""),("B",3,5,"")]
    strata += [("C",n//2,n//2,s) for n in (12,16) for s in "LH"]
    cases=[]; selection=[]; missing=[]
    def add(group,word,ta,flow):
        label=f"{group}{len(cases)+1:02d}_{word}_T{ta}"
        CFG["instances"][label]=[list(word),1,ta,1]
        rows=requests(label); body=csv_bytes(rows)
        csv_name=flow+".csv"
        dest=REG/"inputs"/csv_name
        if dest.exists():assert dest.read_bytes()==body
        dest.write_bytes(body)
        traffic=[(str(r["stream"]),str(r["kind"]),str(r["release_tick"]),str(r["deadline_tick"])) for r in rows]
        th=sha(json.dumps(traffic,separators=(",",":")).encode())
        assert all(th!=h["traffic_sha256"] for h in hist)
        assert len(rows)==60*word.count("L")+100*word.count("H")
        cases.append(dict(index=len(cases),group=group,case=label,flow=flow,word=word,ambient=ta,
                          requests=len(rows),windows=len(word),horizon_ticks=10000*len(word)+3010,
                          input=csv_name,input_sha256=sha(body),traffic_sha256=th))
    for group,lights,heavies,start in strata:
        n=lights+heavies; pool=[]
        for comb in itertools.combinations(range(n),heavies):
            ids=set(comb); word="".join("H" if i in ids else "L" for i in range(n))
            if word.startswith(start):
                digest=sha(f"M1-i/{BASE}/v1/{lights}/{heavies}/{word}".encode())
                pool.append((digest,word))
        eligible=sorted((h,w) for h,w in pool if w not in used)
        if not eligible:
            missing.append([group,n,start]);continue
        h,word=eligible[0]
        selection.append(dict(group=group,window_count=n,L=lights,H=heavies,start=start or "any",
                              enumerated=len(pool),excluded=len(pool)-len(eligible),eligible=len(eligible),
                              chosen=word,selection_sha256=h,excluded_words="|".join(sorted(w for _,w in pool if w in used))))
        used.add(word);add(group,word,35,f"F{len(cases)+1:02d}_{word}")
    for ref in (("A",8),("C",12)):
        src=next((c for c in cases if (c["group"],c["windows"])==ref and c["word"][0]=="L"),None)
        if src:
            for ta in (25,45):add("D",src["word"],ta,src["flow"])
    (REG/"selection.csv").write_bytes(csv_bytes(selection))
    write_json(REG/"cases.json",dict(base=BASE,cases=cases,missing=missing))
    order=[]
    for c in cases:
        for r in range(3):
            k=(c["index"]+r)%4
            for pos,m in enumerate(METHODS[k:]+METHODS[:k]):
                order.append(dict(case=c["case"],flow=c["flow"],lane=c["index"]%8,repeat=r+1,position=pos+1,method=m))
    (REG/"rotation.csv").write_bytes(csv_bytes(order))
    print([(c["group"],c["word"],c["ambient"],c["requests"]) for c in cases])

if __name__=="__main__":
    main()
