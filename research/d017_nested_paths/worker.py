"""One complete deterministic finite action diagnosis; no adaptive conditions."""
import os
for k in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS"):
    os.environ[k]="1"
from time import perf_counter
START=float(os.environ["NESTED_START"])
import json,gzip,sys
from pathlib import Path
from dataclasses import asdict
from physical import *
CFG=json.loads(CONFIG_PATH.read_bytes())
OUT=HERE/"raw"
LOG=(OUT/"events.jsonl").open("x",encoding="utf-8")
def emit(kind,**kw):
    LOG.write(json.dumps(dict(t_s=perf_counter()-START,kind=kind,**kw))+"\n");LOG.flush()
def put(f,x):f.write((json.dumps(x,separators=(",",":"),allow_nan=False)+"\n").encode())
class Budget(Exception):pass
def guard():
    if perf_counter()-START>=CFG["admission_stop_s"]:raise Budget()

def main():
    manifest=json.loads((HERE/"execution_manifest.json").read_bytes())
    for name,h in manifest.items():assert sha(ROOT/name)==h,name
    inp=json.loads((HERE/"inputs.json").read_bytes())
    frozen,loads=inp["frozen"],inp["loads"]
    emit("start",source_hashes=len(manifest),planned_actions=1701,planned_rows=43740,config=CFG)
    counts=dict(scheduled=0,deadline_feasible=0,thermal_trajectories=0,certificate_rows=0)
    with gzip.open(OUT/"schedules.jsonl.gz","xb") as schedlog,gzip.open(OUT/"certificates.jsonl.gz","xb") as certlog:
        for load,data in loads.items():
            traces=[];tracekeys=[]
            for path in frozen["deployments"]:
                for opp in CFG["opps"]:
                    guard();sid=f"{load}_{path}_{opp}";s=schedule(frozen,data,path,opp)
                    counts["scheduled"]+=1
                    put(schedlog,dict(id=sid,load=load,path=path,opp=opp,deadline_ok=s.deadline_feasible,
                        requests=[asdict(r) for r in s.requests],completions_ns=s.completions_ns,
                        late_ids=s.late_ids,rows=[asdict(r) for r in s.rows],busy_ns=s.busy_ns,
                        idle_ns=s.idle_ns,start_ns=s.start_ns.tolist(),duration_ns=s.duration_ns.tolist(),
                        activity_W=s.active_w.tolist(),transfer_W=s.transfer_w.tolist(),
                        replication="For deadline-feasible schedules only: translate complete rows/jobs by frame*40000000 ns; change f0000 to frame ID. No queue or temperature reset."))
                    if s.deadline_feasible:counts["deadline_feasible"]+=1
                    for mode in CFG["modes"]:
                        ls=levels(s,opp,mode)
                        low_gpu=sum(int(t) for o,t in zip(ls,s.duration_ns) if o[1]=="L")
                        low_dla=sum(int(t) for o,t in zip(ls,s.duration_ns) if o[2]=="L")
                        for amb in CFG["ambient_C"]:
                            for inlet,T0 in CFG["initial_C"].items():
                                guard()
                                common=dict(schedule_id=sid,load=load,path=path,opp=opp,mode=mode,
                                    ambient_C=amb,inlet=inlet,initial_C=T0,deadline_ok=s.deadline_feasible,
                                    min_slack_ms=s.min_slack_ns/1e6,active_apps=data["active"])
                                if s.deadline_feasible:
                                    a=integrate(*arguments(s,opp,mode,amb,T0,max(data["frames"])))
                                    assert np.all(np.isfinite(a)) and np.min(a[:,12:16])>=-1e-9
                                    counts["thermal_trajectories"]+=1
                                    traces.append(a[:,:12]);tracekeys.append([sid,mode,amb,inlet])
                                for n in [1]+data["frames"]:
                                    scope="cycle" if n==1 else "dwell"
                                    result=dict(common,frames=n,scope=scope,required=n*len(data["active"]),
                                        duration_s=n*0.04,busy_ns={r:b*n for r,b in s.busy_ns.items()},
                                        gpu_L_ns=low_gpu*n,dla_L_ns=low_dla*n)
                                    if s.deadline_feasible:
                                        result.update(certificate(a[n-1]))
                                        result["status"]=result["thermal_status"]
                                    else:
                                        result.update(status="VIOLATION",thermal_status="NOT_EVALUATED",
                                            energy_J=None,reason="deadline_failure; no thermal comparison")
                                    put(certlog,result);counts["certificate_rows"]+=1
                    if counts["scheduled"]%27==0:emit("progress",load=load,path=path,**counts)
            np.savez_compressed(OUT/(load+"_cycle_states.npz"),states=np.array(traces),keys=np.array(tracekeys,dtype=str))
            emit("load_complete",load=load,**counts)
    emit("finished",**counts)
try:main()
except Budget:emit("UNRESOLVED",reason="frozen_budget")
except BaseException as e:emit("ERROR",type=type(e).__name__,detail=str(e));raise
finally:LOG.close()
