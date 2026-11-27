"""One initialized single-core process. Online worker reads only frozen code, model and input."""
import os
import sys
from pathlib import Path
from time import perf_counter,process_time

HERE=Path(__file__).resolve().parent
INPUTS=Path(os.environ["U3A_INPUTS"]).resolve()
for name in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMBA_NUM_THREADS","NUMEXPR_NUM_THREADS"):
    os.environ[name]="1"
os.environ.update(U1_NT=str(INPUTS/"nt"),U1_FOUR=str(INPUTS/"four"),U1_THREE=str(INPUTS/"p1"),
                  U1_OUT=str(Path(os.environ["U3B_RUNS"]).resolve()),M1G_RAW=str(INPUTS/"work/warm"))
sys.path.insert(0,str(INPUTS/"u2/research/u2_adaptive_groups"))
import common_u2 as u
import numpy as np
import psutil
from fifo import Builder, timing
from guidance import work
from local_search import backlog,thermal_block,key

def warm(stack):
    flow=stack[0].template()
    b=Builder(flow,flow.eng)
    sample=np.frombuffer(bytes([0,10,0]),np.uint8)
    timing(sample,*b.args,10000)
    work(sample,flow.kinds,b.args[1],b.args[4],flow.args[6],flow.args[9],10000,len(b.types)+1)
    flow.ledger(sample.tobytes(),0,flow.p.horizon,10000,True,True,True)
    from heat import integrate
    ev=np.zeros((1,14))
    ev[0,1]=1
    integrate(ev,flow.p.initial,flow.p.G,flow.p.cap,35.,np.array([],np.int64),True)

class Route:
    def __init__(self,case,method,out,start):
        self.case=case
        self.method=method
        self.out=out
        self.start=start
        self.seen=set()
        self.attempts=[]
        self.stages=[]
    def store(self,name,data):
        u.save(self.out/(name+".json"),data)
    def checkpoint(self):
        self.store("progress",dict(attempts=self.attempts,stages=self.stages,local_replays=self.b.replays,
                   t=perf_counter()-self.start))
    def certify(self,state,stage,rank,pred=None):
        assert state.code not in self.seen
        self.seen.add(state.code)
        r=self.causal(self.flow,state.code)
        assert r is not None and r["slack"]==state.timing[6]
        cfg=tuple((3,v-10) if v>=10 else (2,v) for v in state.code)
        d,tr=self.e.cert(cfg,r)
        m=d["metrics"]
        self.attempts.append(dict(stage=stage,rank=rank,config=key(state.code),plan=d["plan_sha256"],
            status=m["status"],J=m["E_J"],bounds=m["E_bounds"],peak_hi=max(m["peak_hi"]),peak_lo=max(m["peak_lo"]),
            slack_ms=m["min_deadline_slack_ms"],kernel_s=d["cert_s"],prediction=pred,
            error_C=None if pred is None else pred-max(m["peak_hi"]),evidence_s=perf_counter()-self.start))
        self.checkpoint()
        return d,tr
    def run(self,stack):
        obj=next(x for x in u.CASES if x["case"].startswith(self.case+"_"))
        self.flow=u.make_flow(stack[0],obj,self.out)
        self.e=stack[1].Engine(obj["case"],self.out)
        self.causal=stack[3]
        assert u.table(self.e.p.req)==(u.REG/"inputs"/obj["input"]).read_bytes()
        self.b=Builder(self.flow,self.e)
        top=self.b.base()
        self.store("base",dict(input_sha256=obj["input_sha256"],top=[v.code.hex() for v in top],
                    layers=self.b.base_attempts,t=perf_counter()-self.start))
        self.checkpoint()
        for rank,v in enumerate(top[:1] if self.method=="first" else top,1):
            cert,tr=self.certify(v,"terminal",rank)
            if rank==1:
                anchor_cert,anchor_trace=cert,tr
            if cert["metrics"]["status"]=="SAFE":
                return "SAFE"
        if self.method in ("b1","b2") and not top:
            safe=backlog(self,self.method=="b2")
        elif self.method in ("oo","oh","ho","hh") and top:
            safe=thermal_block(self,self.method,top[0],anchor_cert,anchor_trace)
        else:
            return "HOT" if top else "EMPTY"
        if safe:
            return "SAFE"
        if self.b.closed:
            return "REPLAY_CAP"
        if not self.attempts:
            return "TIMING_OR_COVERAGE"
        return "HOT_WITHIN_POOL" if all(r["status"]=="HOT" for r in self.attempts) else "NO_CERTIFIED_SAFE"

def main():
    out=Path(sys.argv[1])
    case,method=sys.argv[2:4]
    process=psutil.Process()
    process.cpu_affinity(process.cpu_affinity()[:1])
    setup=perf_counter()
    stack=u.stack()
    warm(stack)
    u.save(out/"ready.json",dict(warm_s=perf_counter()-setup,affinity=process.cpu_affinity(),pid=os.getpid()))
    # The supervisor starts its deadline from this monotonic clock, shared on Windows.
    start=perf_counter()
    u.save(out/"start.json",dict(clock=start))
    cpu=process_time()
    ctx=Route(case,method,out,start)
    status=ctx.run(stack)
    ctx.store("delivery",dict(status=status,attempts=ctx.attempts,stages=ctx.stages,
              local_replays=ctx.b.replays,cpu_s=process_time()-cpu))
    finished=perf_counter()
    ctx.store("finish",dict(wall_s=finished-start,clock=finished))
if __name__=="__main__":
    main()
