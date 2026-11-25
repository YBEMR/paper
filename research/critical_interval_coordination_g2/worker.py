"""One budgeted job; parent charges process startup and retained common initialization."""
import sys,time
from pathlib import Path
start=time.perf_counter()
from assets import ROOT,G1,g1io,read,write,utc,problem,assess,assemble,idle_plan
from fifo import Compact
from algorithm import summary,automatic,run,load_at
from thermal_bound import simple_bound,proof

def work(action,name,method,seed,folder,start,deadline,budget,charged):
    p=problem(name);m=Compact(p);g1io.OUT=folder/"evidence"
    if action=="init":
        result=automatic(p,m,deadline-1,folder)
        write(folder/"result.json",dict(case=name,initial=result,status="SAFE" if result else "NO_CONSTRUCTION"))
        return
    if action=="smoke":
        if name in ("S16","S80"):source=ROOT/"evidence";key=read(ROOT/"witness_gate.json")["witnesses"][name]["plan"]
        else:source=G1/"results";key=read(G1/"results/seeds"/(name+".json"))["plan"]
    elif action=="strong":
        if name=="S80":source=ROOT/"evidence";key=read(ROOT/"witness_gate.json")["witnesses"][name]["plan"]
        else:
            source=G1/"results"
            import json
            keys=[json.loads(l)["plan"] for l in (source/"suffix.jsonl").read_bytes().splitlines()]
            keys.append(read(source/"seeds/D3.json")["plan"])
            key=min(keys,key=lambda h:read(source/"certificates"/(h+".json"))["metrics"]["E_bounds"][1])
        auto=ROOT/"runs"/("init_"+name)
        ar=read(auto/"result.json")["initial"]
        if ar and ar["bounds"][1]<read(source/"certificates"/(key+".json"))["metrics"]["E_bounds"][0]:
            source=auto/"evidence";key=ar["plan"]
    else:
        init=ROOT/"runs"/("init_"+name)
        result=read(init/"result.json")["initial"]
        if not result:
            write(folder/"result.json",dict(case=name,method=method,seed=seed,status="NO_CONSTRUCTION"));return
        source=init/"evidence";key=result["plan"]
    plan=load_at(source,key);assert assemble(p,[row[:2] for row in plan[0][1::3]])==plan[0]
    h,c=assess(p,plan);assert h==key and c["metrics"]["status"]=="SAFE"
    lower=str(simple_bound(p,"C1")) if proof(p)["passed"] else None
    result=run(p,m,plan,summary(c),method,seed,folder,start,deadline-1.2,budget,charged,smoke=action=="smoke")
    write(folder/"result.json",dict(case=name,method=method,seed=seed,status="COMPLETE",lower_J=lower,**result))

if __name__=="__main__":
    action,name,method,seed,directory,begin,end,budget,charged=sys.argv[1:]
    work(action,name,method,int(seed),Path(directory),float(begin),float(end),float(budget),float(charged))
