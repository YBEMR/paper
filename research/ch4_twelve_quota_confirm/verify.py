"""Offline verification of original input, physical evidence, coverage and resource accounting."""
import argparse,gzip,hashlib,json,subprocess,sys
from pathlib import Path
from summary import OUT,HERE,cases,stats,key,indexed

def audit():
    cells=stats.csvrows("cells");certs=indexed(stats.csvrows("certificates"))
    budget=json.loads((OUT/"budget.json").read_bytes())
    assert len(cells)==len({key(r) for r in cells})==180
    assert sum(int(c["cap"]) for c in cells)==budget["nominal_issued_s"]==4320
    assert budget["actual_cpu_s"]<=4500 and budget["preparation_cpu_s"]<=240
    assert budget["cores"]==json.loads((OUT/"accounts/registration.json").read_bytes())["cores"]
    accounts=sum(json.loads(p.read_bytes())["cpu_s"] for p in (OUT/"accounts/formal").glob("*/account.json"))
    assert accounts<=budget["actual_cpu_s"] and budget["actual_cpu_s"]-accounts<12
    for case in cases():
        rs=sorted((c for c in cells if c["case"]==case),key=lambda r:int(r["order"]))
        assert len(rs)==15 and len({c["core"] for c in rs})==1
        assert all(float(a["start"])+float(a["wall"])<=float(b["start"]) for a,b in zip(rs,rs[1:]))
        assert max(int(c["generated"]) for c in rs)>0
    fail={key(r) for r in stats.csvrows("failures")}
    for c in cells:
        ev=certs[key(c)]
        assert all(0<=float(e["t"])<=float(c["cap"]) for e in ev)
        assert len(ev)==int(c["certs"])
        safe=[e for e in ev if e["status"]=="SAFE"]
        assert bool(safe)==bool(int(c["safe"])) and (not safe)==(key(c) in fail)
        if safe:assert float(c["first_s"])==min(float(e["t"]) for e in safe)
        else:assert all(not c[k] for k in ("J","hi","lo","first_s","last_s"))
    for r in stats.csvrows("target_pair_summary"):
        assert sum(int(r[k]) for k in ("both","A_only","B_only","neither"))==int(r["pairs"])
    for r in stats.csvrows("target_stages"):
        assert int(r["hits"])==int(r["first_from_search"])+int(r["first_from_direct"])
        assert sum(int(r[k]) for k in ("hits","no_safe","no_reference","above_target"))==int(r["runs"])
    return cells

def check_git_inputs():
    frozen="a38630d8b9e2a025e13992203e64b760b8e33870"
    tree=subprocess.check_output(["git","ls-tree","-r",frozen,"--","research/m1i_generalization/registration/inputs"],cwd=HERE.parents[1],text=True)
    git_blobs={Path(line.split("\t")[1]).name:line.split()[2] for line in tree.splitlines()}
    proofs=[]
    for code in cases():
        obj=json.loads((OUT/"inputs"/(code+".json")).read_bytes())
        raw=gzip.decompress((OUT/"inputs"/(code+".csv.gz")).read_bytes())
        blob=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
        assert blob==git_blobs[obj["input"]]
        proofs.append(dict(case=code,file=obj["input"],bytes=len(raw),git_blob=blob,sha256=obj["input_sha256"],commit=frozen))
    stats.put("input_identity",proofs)

def main(restore,git_inputs):
    sys.path.insert(0,str(HERE.parent/"ch4_quota_warm_confirm"))
    import check as old
    stats.OUT=OUT;stats.CASES=cases()
    old.OUT=OUT;old.stats=stats;old.audit=audit
    old.check(restore)
    if git_inputs:check_git_inputs()

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--restore",nargs=3,metavar=("CASE","PLAN_SHA","NEW_DIRECTORY"))
    p.add_argument("--git-inputs",action="store_true")
    args=p.parse_args();main(args.restore,args.git_inputs)
