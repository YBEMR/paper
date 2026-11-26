"""Bind frozen FIFO, search and continuous P1 to arbitrary full L/H windows."""
import os
import sys
from functools import lru_cache
from pathlib import Path
from design import ROOT, REG, METHODS, csv_bytes, sha

sys.path.insert(0,str(ROOT.parent/"m1h_common_beam"))
import framework as h
from common import Case, np
from mechanism import WINDOW
from scipy.linalg import expm

e = h.e

@lru_cache(maxsize=1)
def template():
    # Native P1 device arrays are independent of request counts and ambient.
    return e.case_for("L320")

class Flow(Case):
    def __init__(self, word, ambient, label, out, csv_file=None):
        old=template()
        e.p1.CFG["instances"][label]=[list(word),1,ambient,1]
        self.eng=eng=e.p1.Engine(label,out)
        self.label=label
        self.p=p=eng.p
        self.windows=len(word)
        self.release=np.array([r["release_tick"] for r in p.req],np.int64)
        self.kinds=np.asarray(eng.kindidx,np.int64)
        self.args=(self.release,self.kinds,*[np.asarray(a,np.int64) for a in (eng.ps,eng.a,eng.q,eng.D)],
                   *old.args[6:11],p.horizon)
        self.base=old.base
        assert p.profile==old.p.profile and p.idle==old.p.idle
        assert np.array_equal(p.cap,old.p.cap) and np.array_equal(p.G,old.p.G)
        assert p.horizon==WINDOW*self.windows+3010 and p.boundaries==list(range(WINDOW,WINDOW*self.windows,WINDOW))
        assert [len(group) for group in eng.groups]==[60 if x=="L" else 100 for x in word]
        assert p.n==3*eng.n and all(r["deadline_ms"]-r["release_ms"]==300 for r in p.req)
        if csv_file is not None:
            assert csv_bytes(p.req).splitlines()==Path(csv_file).read_bytes().splitlines()
        if ambient!=35:
            self.external_drive=p.G@np.full(4,float(ambient-35))
            self.propagate=self.propagate_ambient

    def propagate_ambient(self, temp, moment, seconds):
        # In x=T-35 coordinates the forcing is b35 + G*(Ta-35).
        matrix=np.zeros((5,5))
        matrix[:4,:4]=(np.diag(moment[4:])-self.p.G)/self.p.cap[:,None]
        matrix[:4,4]=(moment[:4]+self.external_drive)/self.p.cap
        step=expm(seconds*matrix)
        return 35+step[:4,:4]@(temp-35)+step[:4,4]

def flow(item,out):
    file=REG/"inputs"/item["input"]
    assert sha(file.read_bytes())==item["input_sha256"]
    return Flow(item["word"],item["ambient"],item["case"],out,file)

def builder(method):
    expansion=h.LiteratureRisk().expand if method=="ZQ-Beam" else e.expand
    receipt={}
    def observe(c,j,parents,arm,start,deadline,stage):
        pool,complete=expansion(c,j,parents,arm,start,deadline,stage)
        receipt.update(window=j+1,complete=complete,size=len(pool))
        return pool,complete
    return h.with_binding(e.build,expand=observe),receipt
