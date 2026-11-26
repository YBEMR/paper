import csv
import hashlib
import io
import os
import sys
from pathlib import Path

for name in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMBA_NUM_THREADS"):
    os.environ[name] = "1"
import psutil
process = psutil.Process()
if hasattr(process, "cpu_affinity"):
    process.cpu_affinity(process.cpu_affinity()[:1])
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/"frozen"))
import preflight as p1
import numpy as np
from scipy.linalg import expm
from ledger import fifo

ORDER = ("L640","L800","L320","L480")
WINDOW = 10000


class Case:
    def __init__(self, label, out):
        self.label = label
        p1.CFG["instances"][label] = [["L","H"],int(label[1:])//160,35,1]
        self.eng = eng = p1.Engine(label,out)
        eng.dur = WINDOW
        self.p = p = eng.p
        for name,h in p1.PIN.items():
            assert p1.blob((ROOT/"frozen/p1"/name).read_bytes())==h
        s = io.StringIO(newline="")
        w = csv.DictWriter(s,fieldnames=p.req[0],lineterminator="\n")
        w.writeheader()
        w.writerows(p.req)
        assert s.getvalue().encode()==(ROOT/"inputs"/(label+".csv")).read_bytes()
        self.release = np.array([r["release_tick"] for r in p.req],np.int64)
        self.kinds = np.array(eng.kindidx,np.int64)
        self.windows = (p.horizon-3010)//WINDOW
        shape = (2,4,10)
        busy,beta = np.zeros(shape),np.zeros(shape)
        dur = np.zeros(shape,np.int64)
        idle,idle_beta = np.zeros((4,10)),np.zeros((4,10))
        for (u,k),(v,b) in p.idle.items():
            idle[u,k],idle_beta[u,k] = v,b
        for (stage,u,k),(dt,v,b) in p.profile.items():
            if u < 2 and stage.split(".")[1] != ("pre","post")[u]:
                continue
            t = int(stage[0]=="B")
            busy[t,u,k],beta[t,u,k],dur[t,u,k] = v,b,dt
        self.args = (self.release,self.kinds,*[np.array(x,np.int64) for x in (eng.ps,eng.a,eng.q,eng.D)],
                     busy,beta,dur,idle,idle_beta,p.horizon)
        self.base = idle[:,0].sum()+.3

    def ledger(self, config, left, right, width, closed, moments=True, causal=True):
        return fifo(np.frombuffer(config,dtype=np.uint8),*self.args,left,right,width,closed,moments,causal)

    def propagate(self, temp, moment, h):
        matrix = np.zeros((5,5))
        matrix[:4,:4] = (np.diag(moment[4:])-self.p.G)/self.p.cap[:,None]
        matrix[:4,4] = moment[:4]/self.p.cap
        step = expm(h*matrix)
        return 35 + step[:4,:4]@(temp-35) + step[:4,4]

    def candidates(self, j, state):
        eng = self.eng
        lo,hi = self.release.searchsorted([j*WINDOW,(j+1)*WINDOW])
        t = self.kinds[lo:hi]
        a,b = np.bincount(t,minlength=2)
        for g,n in p1.PAIRS:
            center = eng.quota({"f":state["f"],"k":state["k"]},j,(g,n),(int(a),int(b)))
            delta = [eng.inc[k,3,n]-eng.inc[k,2,g] for k in "AB"]
            # Reference-energy minimizer: restrict any tied coordinate to the Q4
            # optimum on the restricted face, including a work-balance tie break.
            xs = [0] if delta[0]>0 else [int(a)] if delta[0]<0 else range(a+1)
            ys = [0] if delta[1]>0 else [int(b)] if delta[1]<0 else range(b+1)
            ag,an = eng.length["A",2,g],eng.length["A",3,n]
            bg,bn = eng.length["B",2,g],eng.length["B",3,n]
            av = [max(j*WINDOW,state["f"][i]+5*(state["k"][i]!=v)) for i,v in enumerate((g,n))]
            _,cx,cy = min((max(av[0]+(a-x)*ag+(b-y)*bg,av[1]+x*an+y*bn),x,y) for x in xs for y in ys)
            pool = set()
            for x,y in (center,(cx,cy)):
                for dx,dy in ((0,0),(-1,0),(1,0),(0,-1),(0,1)):
                    pool.add((int(np.clip(x+dx,0,a)),int(np.clip(y+dy,0,b))))
            for x,y in sorted(pool):
                yield (g,n,x,y), self.extension(t,int(a),int(b),g,n,x,y)

    @staticmethod
    def extension(t,a,b,g,n,x,y):
        mapped = np.full(len(t),g,np.uint8)
        for typ,count,quota in ((0,a,x),(1,b,y)):
            idx = np.flatnonzero(t==typ)
            if count:
                seq = np.arange(count+1)*quota//count
                mapped[idx[np.diff(seq)>0]] = 10+n
        return mapped.tobytes()

    def certify(self, config, causal=True):
        eng = self.eng
        code = [(3,k-10) if k>=10 else (2,k) for k in config]
        r = eng.replay(code)
        assert r is not None
        l = self.ledger(config,0,self.p.horizon,WINDOW,True,True,causal)
        assert l[0] and np.array_equal(l[4],r["starts"]) and np.array_equal(l[5],r["ends"]) and np.array_equal(l[6],r["posts"])
        # Replace only early-down decisions on a previously open idle gap.
        low = [(code[i][0]-1,3*i+1) for i in range(len(code)) if l[7][i]]
        low += [(j+1,-1) for j in range(2) if l[7][len(code)+j]]
        removed = set(r["low"])-set(low)
        assert not (set(low)-set(r["low"]))
        last,old = [0,0],[0,0]
        for i,(u,k) in enumerate(code):
            j = u-2
            if (u-1,3*i+1) in removed:
                dt = r["starts"][i]-last[j]
                hold = eng.rate[u,old[j]]*dt+eng.sw*(old[j]!=k)
                r["cost"] += hold-eng.gap(u,old[j],k,dt)[0]
            last[j],old[j] = r["ends"][i],k
        for j in range(2):
            if (j+1,-1) in removed:
                dt = self.p.horizon-last[j]
                r["tail"] += eng.rate[j+2,old[j]]*dt+eng.sw*(old[j]!=0)-eng.gap(j+2,old[j],0,dt)[0]
        r["low"] = low
        cert,trace = eng.cert(code,r)
        assert abs(l[1]+self.base*self.p.horizon/10000-cert["E35_J"])<1.e-8
        return cert,trace


def archive_means(events,left,right):
    weights = np.maximum(0,np.minimum(events[:,1],right)-np.maximum(events[:,0],left))
    assert weights.sum()==right-left
    return weights@events[:,2:10]/(right-left)


def digest(data):
    return hashlib.sha256(data).hexdigest()
