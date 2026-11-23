"""Small algebraic regression only. No physical formal case or M2 winner is used."""
from itertools import product
import numpy as np
from scipy.optimize import milp
from master import Kernel, Master

kernels = []
grids = {}
for d in ("p","q"):
    grids[d] = []
    for j in range(4):
        slot = {}
        for f in range(2):
            slot[f] = len(kernels)
            shift = (d=="q") * 0.11
            b = np.array([5.+f+shift+j/4, 2., 1., 0.1])
            F = np.diag([.82,.65,.24,.12])
            w = np.array([.008,.1,.01,.02])
            e = 3. - f/2 + shift
            peak = np.array([74.0+f-2*j-shift, 35., 34., 32.])
            kernels.append(Kernel(b,F,e,w,peak,F,np.ones(4)))
        grids[d].append(slot)

for witnesses, cuts in [(False,[]),(True,[]),(True,[("p",[0,0,0])])]:
    truth = []
    for d,grid in grids.items():
        for seq in product(range(2),repeat=4):
            if any(d==c and list(seq[:len(s)])==s for c,s in cuts):
                continue
            delta, energy, ok = np.zeros(4), 0., True
            for j,f in enumerate(seq):
                k = kernels[grid[j][f]]
                ok &= not witnesses or max(k.peak + k.h @ delta) <= 80.+1e-8
                energy += k.e+k.w@delta
                delta = k.b+k.F@delta
            if ok:
                truth.append((energy,d,seq))
    if not truth:
        raise AssertionError("toy must have a feasible solution")
    expected = min(truth)[0]
    master = Master(grids,kernels,expected+1e-6,witnesses,cuts)
    result = milp(master.obj,integrality=master.integer,bounds=master.bounds,
                  constraints=master.constraint,options={"mip_rel_gap":0.})
    assert result.success and abs(result.fun-expected)<1e-7, (expected,result)
    print("matched enumeration",witnesses,cuts,round(expected,9),master.decode(result.x))
