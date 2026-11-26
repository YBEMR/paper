"""Check frozen file identities, generated input equality and legacy W4 plan outcomes."""
import hashlib
import json
from pathlib import Path
from summarize import DATA,ROOT,rows,write
from batch import RAW
from framework import inputs

def sha(blob):
    return hashlib.sha256(blob).hexdigest()

def main():
    upstream=ROOT.parent
    legacy=upstream/"m1f_trace_energy_quality/data/trace"
    ref={r["case"]:r for r in rows(legacy/"summary.csv")}
    winners={(r["case"],r["method"]):r["selected_cfg"] for r in sorted(rows(legacy/"winning_actions.csv"),key=lambda r:int(r["window"]))}
    matched=[];manifest=[]
    for i,(phase,p) in enumerate(inputs()):
        lane=RAW/f"lane{i%7}/engine"
        source=p.read_bytes();copy=(lane/"validation_inputs"/p.name).read_bytes()
        assert source.splitlines()==copy.splitlines()
        manifest.append(dict(phase=phase,case=p.stem,source=str(p.relative_to(upstream)),source_sha256=sha(source),actual_file_sha256=sha(copy),
                        rows=len(copy.splitlines())-1))
        for m in ("NT","NC"):
            r=json.loads((lane/"runs"/p.stem/m/"run.json").read_bytes())["records"][:4]
            safe=[v for v in r if v["cert"]["metrics"]["status"]=="SAFE"]
            picked=min(safe,key=lambda v:v["cert"]["metrics"]["E_J"]) if safe else min(r,key=lambda v:max(v["cert"]["metrics"]["peak_hi"]))
            s=picked["cert"]["metrics"];key=p.stem,m
            assert s["status"]==ref[p.stem][m+"_status"] and abs(s["E_J"]-float(ref[p.stem][m+"_E_J"]))<1e-9
            assert picked["id"]==winners[key]
            matched.append(dict(case=p.stem,method=m,status=s["status"],E_J=s["E_J"],config=picked["id"],same_frozen_config=True))
    write(DATA/"fixed_frozen_check.csv",matched);write(DATA/"inputs.csv",manifest)
    print("Matched frozen W4 configurations",len(matched))

if __name__=="__main__":
    main()
