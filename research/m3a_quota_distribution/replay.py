"""Reproduce any archived M3-a candidate using its per-request device/OPP configuration."""
import argparse
from pathlib import Path
from core import OUT,bind,cases,e,np,read,sha

p=argparse.ArgumentParser()
p.add_argument("case")
p.add_argument("cfg")
p.add_argument("output",type=Path)
a=p.parse_args()
z=read(OUT/a.case/"audit.json.gz")["physical"][a.cfg]
cfg=bytes.fromhex(z["config_hex"])
assert sha(cfg)==a.cfg
c=bind(next(x for x in cases() if x["case"]==a.case))
c.eng.out=a.output.resolve()
if not z["fifo_ok"]:
    r=c.ledger(cfg,0,c.p.horizon,2500,True,True,True)
    assert not r[0] and np.array_equal(r[4],z["starts"]) and np.array_equal(r[5],z["ends"])
    assert np.array_equal(r[6],z["posts"]) and r[-1]==z["fifo_slack_ticks"]
    print("TIMING",a.cfg,"minimum slack (ticks)",int(r[-1]))
else:
    cert,arr=c.certify(cfg)
    omit_time=lambda x:{k:v for k,v in x.items() if k!="cert_s"}
    assert e.p1.raw(omit_time(cert))==e.p1.raw(omit_time(z["certificate"]))
    assert sha(arr.tobytes())==z["event_sha256"]
    print(cert["metrics"]["status"],cert["plan_sha256"],cert["metrics"]["E_J"],"J")
