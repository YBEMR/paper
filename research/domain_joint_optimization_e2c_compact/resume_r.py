"""Resume only the four never-started arms after the recorded Windows file-sharing incident."""
import subprocess,sys,time,traceback,shutil,os
from datetime import datetime,timezone
from c1r_assets import ROOT,read,write,digest

def arm_adapter():
    import arm_r
    original=arm_r.read
    def read_retry(path):
        for _ in range(12):
            try:return original(path)
            except PermissionError:time.sleep(.005)
        return original(path)
    arm_r.read=read_retry
    arm_r.main()

def resume():
    from run_r import stop,utc
    state=read(ROOT/"execution.json");assert state["status"]=="STOP" and len(state["groups"])==18
    folder=ROOT/"incident";folder.mkdir(exist_ok=False)
    shutil.copyfile(ROOT/"execution.json",folder/"execution_before_resume.json")
    manifest=read(ROOT/"manifest.json");assert all(digest((ROOT/f).read_bytes())==v for f,v in manifest["sources"].items())
    problematic="D3_103_first"
    for rec in state["groups"]:
        if rec["sample"]==problematic:
            rec["observed_to_controller_exit_s"]=rec["charged_s"]
            # Bound the parent/child shutdown conservatively; no unused allowance
            # is reclaimed for another numerical call on either interrupted arm.
            rec.update(charged_s=30.0,status="INTERRUPTED_NO_RANK",unranked=True)
    state.update(status="REPLAYS",incident="D3_103_first",scope="only four unstarted arms",prior_error=state.pop("error"))
    def update():
        state["replay_s"]=sum(r["charged_s"] for r in state["groups"]);state["ancillary_s"]=sum(state["phases"].values())
        state["numerical_s"]=state["replay_s"]+state["ancillary_s"];write(ROOT/"execution.json",state)
        assert state["replay_s"]<=660 and state["ancillary_s"]<=540 and state["numerical_s"]<=1200
    live=[];begin=time.perf_counter()
    try:
        update()
        for ix,s in enumerate(read(ROOT/"samples.json")["cases"]):
            if s["id"] not in ("D3_103_middle","D3_103_last"):continue
            variants=("Full-Hint","Compact-Hint") if ix%2==0 else ("Compact-Hint","Full-Hint")
            for slot,variant in enumerate(variants):
                dest=ROOT/"runs"/s["id"]/variant;dest.mkdir(parents=True,exist_ok=False)
                cpu=manifest["physical_cores"][slot];tag=s["id"]+"_"+variant
                with (ROOT/"logs"/(tag+".txt")).open("wb") as f:
                    t=time.perf_counter()
                    p=subprocess.Popen([sys.executable,"-B","-u",__file__,"arm",s["id"],variant,str(t),str(cpu)],stdout=f,stderr=subprocess.STDOUT)
                live.append((p,variant,t,dest,cpu))
            while live:
                for item in live.copy():
                    p,variant,t,dest,cpu=item;code=p.poll()
                    if code is None and time.perf_counter()-t<29.81:continue
                    killed=code is None
                    if killed:stop(p)
                    wall=time.perf_counter()-t
                    state["groups"].append(dict(sample=s["id"],method=variant,cpu=cpu,charged_s=wall,hard_stop=killed,code=code))
                    live.remove(item);update()
                    if killed:
                        r=read(dest/"arm.json");r.update(status="TIME_LIMIT",stopped_at_s=wall);write(dest/"arm.json",r)
                    elif code:raise RuntimeError((s["id"],variant,code))
                if live:time.sleep(.015)
            print(s["id"],len(state["groups"]),"/22",flush=True)
        state["status"]="AWAITING_AUDIT"
    except BaseException:
        for p,v,t,d,cpu in live:stop(p)
        state.update(status="STOP",error=traceback.format_exc());raise
    finally:
        state.update(end=utc(),resume_wall_s=time.perf_counter()-begin);update()
if __name__=="__main__":
    if len(sys.argv)>1:arm_adapter()
    else:resume()
