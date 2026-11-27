"""Verify delivered bytes and FIFO plans independently of the online ranking."""
import csv
import sys
from pathlib import Path
import io
import zipfile
from collections import Counter
from core import OUT,bind,cases,np,read,save,sha
sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit import csv_bytes
from summarize import TABLES

def verify():
    receipt=[]
    changes=[]
    for item in cases():
        c=bind(item)
        folder=OUT/c.label
        z=read(folder/"audit.json.gz")
        seed=read(folder/"seed.json")
        assert seed["archived_array"]==seed["replay_array"] and max(seed["max_abs_by_field"].values())==0
        assert seed["input_sha"]==item["input_sha256"]
        base=z["physical"][z["base"]]
        with zipfile.ZipFile(folder/"traces.zip") as pkg:
            for k in z["traces"]:
                arr=np.load(io.BytesIO(pkg.read(k+"/events_T.npy")),allow_pickle=False).T
                a=z["physical"][k]
                assert sha(arr.tobytes())==a["event_sha256"]
                assert arr.shape[1]==31 and arr[0,0]==0 and arr[-1,1]==c.p.horizon
                assert np.array_equal(arr[1:,0],arr[:-1,1])
                assert np.array_equal(arr[:-1,18:22],arr[1:,14:18])
                assert abs(np.sum(arr[:,26:30])+c.p.horizon*.3/10000-a["certificate"]["metrics"]["E_J"])<1e-8
                occup=list(csv.DictReader(io.TextIOWrapper(pkg.open(k+"/intervals.csv"))))
                for u in range(4):
                    ss=[v for v in occup if int(v["node"])==u]
                    assert int(ss[0]["start_tick"])==0 and int(ss[-1]["end_tick"])==c.p.horizon
                    assert all(x["end_tick"]==y["start_tick"] for x,y in zip(ss,ss[1:]))
        basecfg=bytes.fromhex(base["config_hex"])
        baseline=np.asarray(base["plan"]["rows"])
        counts=Counter()
        for k,a in z["physical"].items():
            cfg=bytes.fromhex(a["config_hex"])
            assert sha(cfg)==k
            starts=[]; ends=[]; posts=[0]*len(cfg)
            last=[0,0]; opp=[0,0]
            for i,code in enumerate(cfg):
                j=int(code>=10); level=code-10*j
                s=max(c.eng.a[i],last[j]+5*(opp[j]!=level))
                end=s+c.p.dur(3*i+1,j+2,level)
                starts.append(s);ends.append(end)
                last[j]=end;opp[j]=level
            post_end=0
            for i in sorted(range(len(cfg)),key=lambda i:(ends[i],i)):
                posts[i]=max(post_end,ends[i])
                post_end=posts[i]+c.eng.q[i]
            slack=min(d-s-dt for d,s,dt in zip(c.eng.D,posts,c.eng.q))
            valid=slack>=0 and post_end<=c.p.horizon and all(f+5*(k!=0)<=c.p.horizon for f,k in zip(last,opp))
            assert a["fifo_ok"]==valid and a["fifo_slack_ticks"]==slack and a["drain_tick"]==post_end
            if valid:
                rows=np.asarray(a["plan"]["rows"])
                assert np.array_equal(rows[::3,2],c.eng.ps) and np.array_equal(rows[1::3,2],starts)
                assert np.array_equal(rows[2::3,2],posts)
                assert list(cfg)==[int(k+10*(u==3)) for u,k,_ in rows[1::3]]
                m=a["certificate"]["metrics"]
                counts[m["status"]]+=1
                if k in z["traces"]:
                    changes.append(dict(case=c.label,cfg=k,
                                  remapped_requests=sum((old>=10)!=(new>=10) for old,new in zip(basecfg,cfg)),
                                  main_start_changed=sum(baseline[1::3,2]!=starts),
                                  post_start_changed=sum(baseline[2::3,2]!=posts),
                                  E35_saving_J=base["certificate"]["E35_J"]-a["certificate"]["E35_J"],
                                  thermal_saving_J=base["certificate"]["metrics"]["temperature_J"]-m["temperature_J"]))
            else:
                assert a["starts"]==starts and a["ends"]==ends and a["posts"]==posts
                counts["TIMING"]+=1
        receipt.append(dict(case=c.label,unique=len(z["physical"]),states=counts,
                            before_after_traces=len(z["traces"]),requests=c.eng.n,
                            seed_event_sha256=seed["replay_array"]))
    (TABLES/"trajectory_changes.csv").write_bytes(csv_bytes(changes))
    save(OUT/"verification.json",dict(cases=receipt,all_passed=True,
         checks=["archived seed event bytes and all metric fields","all feasible and rejected FIFO start and finish ticks",
                 "all deadlines, horizon, tail switch room","winning archive trace SHA256, energy sum and continuity",
                 "winning device timelines cover full horizon"]))
if __name__=="__main__":
    verify()
