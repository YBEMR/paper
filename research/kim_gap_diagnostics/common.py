"""Frozen four-YOLO model and historical load adapters; no model changes."""
from collections import Counter
from functools import lru_cache
import ast
import gzip
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
HISTORY=ROOT/"research/ch3_algorithm_selection"
sys.path[:0]=[str(ROOT/"research/ch3_cooperative_cuts"),str(ROOT/"research/ch3_final_experiments/p2"),str(HISTORY)]
from catalog_ext import make_domain
from physical import Physical
import search
import loads

def encoded(x):return json.dumps(x,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()
def save(p,x):
    data=encoded(x)+b"\n"
    p.write_bytes(gzip.compress(data,compresslevel=6,mtime=0) if p.suffix==".gz" else data)
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify_freeze():
    for name,digest in read(HERE/"execution_manifest.json").items():assert sha(ROOT/name)==digest,name

class Evaluator(Physical):
    def __init__(self,case,domain,emit):
        self.seconds=Counter();self.log=emit
        super().__init__(ROOT,f"forward_flat_{case['ambient_c']}C",domain.stages)
        loads.install(self,case["load"])
        self.emit=self.physical_record
    def _make_schedule(self,j,signature,opp):
        t=perf_counter()
        try:
            out=super()._make_schedule(j,signature,opp)
            self.counters["deadline_pass" if out.deadline_feasible else "deadline_fail"]+=1
            return out
        finally:self.seconds["schedule_s"]+=perf_counter()-t
    def physical_record(self,kind,data):
        self.log(kind,{**data,"indices":list(data["indices"]),"physical":self._physical[data["dep"],tuple(data["indices"])]})
    def replay(self,dep,indices):
        t=perf_counter()
        try:return super().replay(dep,indices)
        finally:self.seconds["replay_inclusive_s"]+=perf_counter()-t
    def evidence(self,dep,indices):
        t=perf_counter()
        try:return super().evidence(dep,indices)
        finally:self.seconds["ledger_inclusive_s"]+=perf_counter()-t

def bind_energy_search(ev):
    """Reuse the exact original function AST, without executing its module's global model bindings."""
    import numpy as np
    path=ROOT/"research/kim_multidnn_search_trial/solver.py"
    tree=ast.parse(path.read_text(encoding="utf-8"))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="energy_search")
    namespace=dict(np=np,joint=ev.unit.joint,OPPS=ev.opps,SIZE=27**4)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),"exec"),namespace)
    return namespace["energy_search"]
