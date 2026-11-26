"""Separate window quota placement from GPU/NPU frequencies using archived actions."""
import base64
from trace import OUT,DIAG,BASE,HOLD,arm_sources,dumpcsv,inputs,e,W
import json
import os
from pathlib import Path

def main():
    output=[];actions=[]
    for phase,f in inputs():
        root=Path(os.environ.get("M1F_DEV_SOURCE",BASE) if phase=="development8" else os.environ.get("M1F_HOLD_SOURCE",HOLD))
        checks={v["file"]:v["sha256"] for v in json.loads((root/"evidence/manifest.json").read_bytes())}
        case=f.stem; label,word=case.split("_")
        arms=arm_sources(root/"evidence",case,checks)
        c=e.reordered(e.case_for("L"+label[1:]),"L"+label[1:],word);c.eng.out=DIAG/"factor_checks"
        for m,d in arms.items():
            valid={r[6]:r for r in d["log"]["actions"] if r[9]=="valid"}
            d["actions"]=[]
            for j in range(c.windows):
                hi=int(c.release.searchsorted((j+1)*W))
                r=valid[e.digest(d["cfg"][:hi])]
                act=tuple(r[2:6]); d["actions"].append(act)
                actions.append(dict(case=case,method=m,window=j+1,load=word[j],g=act[0],n=act[1],A_to_NPU=act[2],B_to_NPU=act[3],selected_cfg=r[6]))
        for placement in arms:
            for opp in arms:
                cfg=b"".join(c.extension(*e.window_types(c,j),*arms[opp]["actions"][j][:2],*arms[placement]["actions"][j][2:]) for j in range(c.windows))
                v=c.ledger(cfg,0,c.p.horizon,W,True,False)
                if v[0]:
                    cert,_=c.certify(cfg)
                    m=cert["metrics"];plan=cert["plan_sha256"]
                    status=m["status"];energy=m["E_J"];ref=cert["E35_J"];peak=max(m["peak_hi"]);slack=m["min_deadline_slack_ms"]
                    if opp==placement:assert plan==arms[opp]["plan"] and cfg==arms[opp]["cfg"]
                else:
                    status="TIMING";plan=energy=ref=peak=None;slack=int(v[-1])/10
                output.append(dict(case=case,mapping_from=placement,frequency_from=opp,status=status,E_J=energy,
                    E35_J=ref,peak_C=peak,min_deadline_slack_ms=slack,plan=plan,config_b64=base64.b64encode(cfg).decode()))
    dumpcsv(OUT/"mapping_frequency.csv",output);dumpcsv(OUT/"winning_actions.csv",actions)
if __name__=="__main__":main()
