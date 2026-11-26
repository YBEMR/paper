"""Sealed, composition-matched evaluation on two untouched orderings per length."""
from itertools import combinations
import io
from study import *
from decisions import BUDGETS,freeze_choice
from prefix import cost_policy

def sequences(n):
    patterns=[]
    for idx in combinations(range(n),n//2):
        word="".join("H" if i in idx else "L" for i in range(n))
        switches=sum(a!=b for a,b in zip(word,word[1:]))
        if 1<switches<n-1:patterns.append(word)
    def key(w):return digest(("M1d-44f8d7e2-order-v1/"+w).encode())
    return [min((w for w in patterns if w.startswith(start)),key=key) for start in ("L","H")]

def reordered(c,baseline,word):
    label="V"+baseline[1:]+"_"+word
    assert word.count("L")==word.count("H") and len(word)==c.windows
    p1.CFG["instances"][label]=[list(word),1,35,1]
    eng=p1.Engine(label,OUT/"physical")
    eng.dur=WINDOW
    prior=c.p;p=eng.p
    for prop in ("cap","G","initial"):
        assert np.array_equal(getattr(p,prop),getattr(prior,prop))
    assert p.profile==prior.profile and p.idle==prior.idle and p.horizon==prior.horizon
    def pattern(rows,j):
        local=[r for r in rows if j*WINDOW<=r["release_tick"]<(j+1)*WINDOW]
        return [(r["stream"],r["kind"],r["release_ms"]-1000*j,r["deadline_ms"]-1000*j,
                 r["release_tick"]-j*WINDOW,r["deadline_tick"]-j*WINDOW) for r in local]
    for j,k in enumerate(word):
        assert pattern(p.req,j)==pattern(prior.req,0 if k=="L" else c.windows//2)
    assert len(p.req)==int(baseline[1:]) and all(r["deadline_ms"]-r["release_ms"]==300 for r in p.req)
    c.label=label;c.eng=eng;c.p=p
    c.release=np.array([r["release_tick"] for r in p.req],np.int64)
    c.kinds=np.array(eng.kindidx,np.int64)
    c.args=(c.release,c.kinds,*[np.array(x,np.int64) for x in (eng.ps,eng.a,eng.q,eng.D)],*c.args[6:])
    write_rows(OUT/"validation_inputs"/(label+".csv"),p.req)
    return c

def lockfiles():
    return {f:digest((ROOT/f).read_bytes()) for f in ("协议.md","study.py","decisions.py","prefix.py","validation.py")}

def freeze():
    rule=freeze_choice()
    obj=dict(fixed_commit="44f8d7e2cb79c97391681406e7c03988a983d72e",generator="H",prefix=rule,
             terminal="safe_energy",budget=4,code=lockfiles(),holdout_enabled=rule is not None)
    dest=OUT/"algorithm_freeze.json"
    if dest.exists():assert load(dest)==obj
    else:save(dest,obj)
    return obj

def evaluate():
    frozen=load(OUT/"algorithm_freeze.json")
    assert frozen["code"]==lockfiles() and frozen["holdout_enabled"]
    rule=frozen["prefix"]
    result=[]
    for label in CASES:
        for word in sequences(int(label[1:])//80):
            c=reordered(case_for(label),label,word)
            dest=OUT/"validation"/c.label
            data=dest/"trajectories.json"
            if data.exists():
                tracks=load(data)
            else:
                ordinary,oi,raw=build(c,"O","original")
                octrack=certify_order(c,ordinary,"legacy",oi["build_s"])
                raw_pool(dest/"ordinary",ordinary,oi,raw)
                pool,info,raw=build(c,"H","original")
                legacy=certify_order(c,pool,"legacy",info["build_s"])
                raw_pool(dest/"H_original",pool,info,raw)
                if rule!="original":
                    pool,info,raw=build(c,"H",rule,cost_policy)
                    raw_pool(dest/("H_"+rule),pool,info,raw)
                selected=certify_order(c,pool,"safe_energy",info["build_s"])
                tracks=dict(C2=octrack,H_legacy=legacy,frozen=selected)
                save(data,tracks)
            for k in BUDGETS:
                cutoff=tracks["H_legacy"]["records"][k-1]["total_s"]
                for name,trajectory in tracks.items():
                    rr=trajectory["records"]
                    for mode,records in (("count",rr[:k]),("time",[r for r in rr[:16] if r["total_s"]<=cutoff])):
                        result.append(dict(case=label,order=word,method=name,budget=k,comparison=mode,limit=cutoff,
                                  build_s=trajectory["build_s"],sorting_s=trajectory["rank_s"],**outcome(records)))
            print("sealed",label,word,[winner(v["records"][:4]).get("E") for v in tracks.values()],flush=True)
    write_rows(OUT/"validation_ablation.csv",result)

if __name__=="__main__":
    if freeze()["holdout_enabled"]:evaluate()
