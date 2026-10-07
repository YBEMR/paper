"""Independent numerical audit of the supplied, unmodified MATLAB experiment.

Parameters transcribed from config_default.m; no empirical hardware claim.
Does not run or modify code in the external source directory.
"""
from pathlib import Path
from itertools import product
import json
import numpy as np
from scipy.linalg import expm

OUT = Path(__file__).resolve().parent / 'first_experiment_audit'
OUT.mkdir(exist_ok=True)
G = np.array([[.115,-.02,-.015],[-.02,.115,-.015],[-.015,-.015,.15]])
C = np.diag([.004,.004,.006])
A = -np.linalg.solve(C,G)
GI = np.linalg.inv(G)
idle = np.array([.5,.5,1.])
rows = []
for ma,mb,fa,fb in product(range(2), repeat=4):
    da,db = [6,4][fa],[7,5][fb]
    for sa,sb,na,nb in product(range(20-da-6+1),range(24-db-7+1),range(15),range(18)):
        if na < sa+da or nb < sb+db: continue
        if ma == mb and not(sa+da <= sb or sb+db <= sa): continue
        if not(na+6 <= nb or nb+7 <= na): continue
        rows.append((ma,mb,fa,fb,sa,sb,na,nb))
S = np.array(rows)
P = np.tile(idle, (len(S),24,1))
for i,(ma,mb,fa,fb,sa,sb,na,nb) in enumerate(S):
    P[i,sa:sa+[6,4][fa],ma] = [4,5][fa]
    P[i,sb:sb+[7,5][fb],mb] = [5,6.5][fb]
    P[i,na:na+6,2] = 6
    P[i,nb:nb+7,2] = 7
E = P.sum(axis=(1,2)) # W * ms = mJ
SS = P @ GI.T
ssok = (SS+25 <= 80).all(axis=(1,2))

def transient(sub=4, t0=45):
    D = expm(A*.001/sub)
    x = np.full((len(S),3),t0-25,dtype=float)
    peak = np.full(len(S),t0,dtype=float)
    for k in range(24):
        for _ in range(sub):
            x = SS[:,k,:] + (x-SS[:,k,:]) @ D.T
            peak = np.maximum(peak,(x+25).max(axis=1))
    return peak

peaks = transient()
tr = peaks <= 80
result = dict(base=len(S),steady=int(ssok.sum()),transient=int(tr.sum()),
              transient_only=int((tr & ~ssok).sum()),
              energy_levels_mJ=np.unique(E).tolist(),
              Ess_mJ=float(E[ssok].min()),Etr_mJ=float(E[tr].min()),
              modal_time_constants_ms=sorted((-1000/np.linalg.eigvals(A)).tolist()))
result['relative_gain_percent'] = 100*(result['Ess_mJ']-result['Etr_mJ'])/result['Ess_mJ']
result['optimal_ties'] = {'steady': int((ssok & np.isclose(E,result['Ess_mJ'])).sum()),
                          'transient': int((tr & np.isclose(E,result['Etr_mJ'])).sum())}
result['temperature_check'] = {}
# Replay the exact schedules printed in the supplied MATLAB report;
# a different enumeration order chooses different equally optimal ties.
printed = {'steady': [0,0,1,0,7,0,14,7], 'transient': [0,0,1,1,5,0,12,5]}
for name,row in printed.items():
    i = int(np.flatnonzero((S == row).all(axis=1))[0])
    q = P[i]; D = expm(A*.001); b = np.zeros(3)
    for p in q:
        z = GI@p; b=z+D@(b-z)
    start = np.linalg.solve(np.eye(3)-np.linalg.matrix_power(D,24),b)
    x = start.copy(); pk = float((x+25).max()); Dfine=expm(A*.000025)
    for p in q:
        z=GI@p
        for _ in range(40):
            x=z+Dfine@(x-z); pk=max(pk,float((x+25).max()))
    result['temperature_check'][name] = dict(cold_peak_C=float(peaks[i]),
        periodic_start_C=(start+25).tolist(),periodic_peak_sampled_C=pk,
        periodic_interval_ms=24,sampling_ms=.025)

assert (result['base'],result['steady'],result['transient'],result['transient_only']) == (10898,3094,10898,7804)
assert abs(result['Ess_mJ']-169.5)<1e-9 and abs(result['Etr_mJ']-168)<1e-9
(OUT/'independent_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
