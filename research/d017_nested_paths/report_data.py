"""Derive interpretable paired evidence and same-action idle attribution."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent
d=pd.read_csv(HERE/"action_results.csv",low_memory=False)
nodes=["cpu","gpu","dla0","dla1"]
keys=["load","frames","scope","ambient_C","inlet","path","opp"]
fields=["energy_J","base_J","temperature_leakage_J","total_activity_J","common_J","transfer_J"]
wide=d[d.deadline_ok].pivot(index=keys,columns="mode",values=fields)
attribution=[]
for idx,r in wide.iterrows():
    for mode in ["gpu_idle","gpu_dla_idle"]:
        v=dict(zip(keys,idx));v["mode"]=mode
        for f in fields:v["delta_"+f]=r[f,mode]-r[f,"constant"]
        assert abs(v["delta_total_activity_J"])<1e-8
        assert abs(v["delta_common_J"])<1e-8 and abs(v["delta_transfer_J"])<1e-8
        assert v["delta_energy_J"]<1e-8
        attribution.append(v)
pd.DataFrame(attribution).to_csv(HERE/"same_action_idle_attribution.csv",index=False,float_format="%.12g")
g=d[(d.load=="a123")&(d.frames==62)&(d.ambient_C==25)&d.path.isin(["D019","D018","D017"])]
evidence=[]
for keys,h in g.groupby(["mode","inlet","path"],sort=False):
    safe=h[h.status=="SAFE"].sort_values("energy_J")
    allh=h[h.deadline_ok].sort_values("energy_J")
    for name,p in [("best_SAFE",safe),("lowest_energy_deadline",allh)]:
        if not len(p):continue
        row=p.iloc[0].to_dict();row["selection"]=name;evidence.append(row)
pd.DataFrame(evidence).to_csv(HERE/"mechanism_evidence.csv",index=False,float_format="%.12g")
counts=d.groupby(["scope","mode","status"]).size().unstack(fill_value=0).reset_index()
counts.to_csv(HERE/"status_counts.csv",index=False)
inp=json.loads((HERE/"inputs.json").read_bytes())
path_rows=[]
for path,p in inp["frozen"]["deployments"].items():
    used=[(a,*s) for a,chain in p["stages"].items() for s in chain if s[0].startswith("DLA")]
    path_rows.append(dict(path=path,v2_path=p["paths"][0],v3_path=p["paths"][1],
        resident_stages_held=4,resident_DLA0=2,resident_DLA1=2,used_DLA_stages=len(used),
        physical_stages=json.dumps(p["stages"],separators=(",",":")),
        binding_swapped_from_81_representative=path.endswith("*"),hardware_verified=False))
pd.DataFrame(path_rows).to_csv(HERE/"path_summary.csv",index=False)
print(pd.DataFrame(evidence)[["mode","inlet","path","selection","opp","energy_J","peak_C","min_slack_ms","base_J","temperature_leakage_J"]].to_string(index=False))
print(counts.to_string(index=False))
