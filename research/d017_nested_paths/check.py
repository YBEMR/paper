"""Small correctness checks only; no diagnostic selection or tuning."""
from physical import *
from dataclasses import asdict
frozen,loads=definitions()
s=schedule(frozen,loads["a0"],"D017","HHH")
assert s.deadline_feasible
errors=[]
for mode in MODES:
    initial=[40.02694115509108,73.82896057497442,37.571727578256485,37.57034559465566]
    got=certificate(integrate(*arguments(s,"HHH",mode,30,initial,2))[-1])
    T=initial;energy=0.;peak=np.array(T)+thermal.ROUND_GUARD
    # Independent reference: unchanged public evaluator on every frequency block.
    ls=levels(s,"HHH",mode)
    for _ in range(2):
        for i,o in enumerate(ls):
            kw=thermal_kwargs(PLATFORM,o,30,True,"base");kw["initial_C"]=T
            p=thermal.evaluate_thermal(s.duration_ns[i:i+1]*1e-9,s.active_w[i:i+1],
                transfer_W=s.transfer_w[i:i+1],**kw)
            T=p["final_C"];energy+=p["energy_J"];peak=np.maximum(peak,p["peak_upper_C"])
    err=dict(mode=mode,energy_J=abs(energy-got["energy_J"]),
        final_C=float(np.max(np.abs(np.array(T)-got["final_C"]))),
        peak_C=float(np.max(np.abs(peak-got["peak_upper_C"]))))
    assert max(err[k] for k in ["energy_J","final_C","peak_C"])<1e-8,err
    errors.append(err)
# Period tiling is exact only for deadline-feasible work; check independently.
s2=schedule(frozen,loads["a0"],"D017","HHH",2)
expected=[dict(asdict(r),request=f"f{f:04d}"+r.request[5:],
    start_ns=r.start_ns+f*PERIOD,end_ns=r.end_ns+f*PERIOD) for f in range(2) for r in s.rows]
assert expected==[asdict(r) for r in s2.rows]
save(HERE/"checks.json",dict(status="PASS",errors=errors,
    periodic_schedule="2-frame dispatcher equals translated complete first-frame trace",
    scope="one legal path/load, three PM modes, two periods; not a performance pilot"))
print(errors)
