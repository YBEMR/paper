"""Bounded offline reconstruction, using archived reference suffixes only in this module."""
import gzip
import json
from collections import Counter
from time import perf_counter
import psutil
from foundation import *

CLAIMS={"I03":[(8,10,3)],"I07":[(3,4,2),(5,5,37),(8,8,6),(9,9,2)],"I11":[(6,8,2),(8,10,2),(10,11,2),(14,16,4)]}
EVD=HOME_C/"offline"
def coded_state(f,c):
    l=ledger(f,c)
    return State(c,(*map(int,l[2]),*map(int,l[3]),0,0,0,0,0,0),())
def extension(b,j,pair,q):
    return b.flow.extension(b.types[j],*b.counts[j],*pair,*q)
def center(b,j,par,pair):
    return b.e.quota(dict(f=par.timing[:2],k=par.timing[2:4]),j,pair,b.counts[j])
class Audit:
    def __init__(self,k,stack):
        self.k=k;self.dest=EVD/k;self.dest.mkdir(parents=True,exist_ok=True)
        o=cases()[k];self.obj=o;inp=frozen.A/"registration/inputs"/o["input"]
        assert sha(inp.read_bytes())==o["input_sha256"]
        self.f=stack[0].Flow(o["word"],35,o["case"],self.dest,inp);self.e=self.f.eng;self.b=Builder(self.f,self.e)
        ref=read(B_SRC/"offline"/k/"safe_reference.json");self.ref=ref["plan"];self.cfg=bytes.fromhex(ref["config"])
        self.pairs=[tuple(a["pairs_center_delta"][0][0]) for a in ref["windows"]]
        self.n=[0,*limits(self.b)];self.causal=stack[3];self.known={}
        for root in (frozen.A/"results"/k,B_SRC/"results"/k,B_SRC/"offline"/k):
            file=root/"physical/plans.jsonl.gz"
            if file.exists():
                for line in gzip.decompress(file.read_bytes()).splitlines():
                    self.known[json.loads(line)["certificate"]["plan_sha256"]]=True
    def cert(self,c):
        state=self.causal(self.f,c);assert state is not None
        built=self.e.build(src.genes(c),state)
        key=sha(u.raw(dict(case=self.obj["case"],rows=built["rows"],low=sorted(built["low"]))))
        path=self.dest/"evidence"/self.obj["case"]/key
        if (path/"trace.npz").exists():d=read(path/"certificate.json")
        else:d,_=self.e.cert(src.genes(c),state,built)
        assert d["plan_sha256"]==key
        m=d["metrics"]
        return dict(plan=key,status=m["status"],energy=m["E_J"],bounds=m["E_bounds"],peak=max(m["peak_hi"]),
                    slack_ms=m["min_deadline_slack_ms"],previously_archived=key in self.known,reference=self.ref==key)
    def retained(self):
        b=self.b;st=b.root;layers=[]
        for j,pair in enumerate(self.pairs):
            st,q,_=next(b.expand(st,j,[pair],[(0,0)],False));assert not st.timing[-1]
            layers.append(dict(window=j+1,quota=q,frequency=pair,code=st.code.hex()))
        full=self.cert(st.code);assert full["status"]=="SAFE"
        root=B_SRC/"results"/self.k
        parents={};attempts=[];old=[];stage=None
        for a in events(root,read(root/"runs/C.json")):
            if a[0]=="begin":stage=a[1]
            if a[0]=="parent":parents[a[1]]=bytes.fromhex(a[2])
            if a[0]=="selection" and a[1]==0:old=list(map(bytes.fromhex,a[4]))
            if a[0]=="q4_action" and a[2]==1 and stage=="construct":
                _,idx,j,pair,q,_,t=a
                c=parents[idx]+extension(b,j,pair,q)
                attempts.append((c,parents[idx],t,pair,q))
            if a[0]=="selection" and a[1]==1:
                observed=a[4];break
        by={x[0]:x for x in attempts if not x[2][-1]}
        ordered=sorted(by.values(),key=lambda v:(v[2][4],v[0]))
        assert [x[0].hex() for x in ordered[:4]]==observed
        pool=[]
        for rank,(c,p,t,pair,q) in enumerate(ordered,1):
            m=margins(self.f,c,1,self.n[1])
            assert m["all"]==t[6] and m["backlog"]==t[7]
            pool.append(dict(rank=rank,code=c.hex(),parent=p.hex(),parent_rank=old.index(p)+1,frequency=pair,quota=q,
                             reference_cost_int=t[4],reference_J=t[4]/self.e.scale,**m))
        target=next(z for z in pool if z["code"]==layers[1]["code"])
        chosen_parent=next(z for z in pool[3:] if z["parent"]!=pool[0]["parent"])
        chosen_margin=min(pool[3:],key=lambda z:(priority(z),z["rank"]))
        tails={}
        for tag,z in (("original",pool[3]),("parent",chosen_parent),("margin",chosen_margin),("known",target)):
            state=coded_state(self.f,bytes.fromhex(z["code"]))
            for j in range(2,len(self.pairs)):
                state,_,_=next(b.expand(state,j,[self.pairs[j]],[(0,0)],False))
                if state.timing[-1]:break
            tails[tag]=dict(rank=z["rank"],window=j+1,cert=self.cert(state.code) if not state.timing[-1] else None)
        put(self.dest/"retention.json",dict(input=self.obj["input_sha256"],reference=self.ref,cert=full,path=layers,real_pool=pool,
            original_parents=[z["parent_rank"] for z in pool[:4]],target_rank=target["rank"],fixed_frequency_continuations=tails))
        print("retention",full["energy"],target["rank"],flush=True)
    def contrast(self,w,expect,dist):
        stime=perf_counter();j=w-1;n=self.n;c=self.cfg;b=self.b;f=self.f
        before=c[:n[j]];pair=self.pairs[j];par=coded_state(f,before);xy=center(b,j,par,pair)
        base=before+extension(b,j,pair,xy)+c[n[j+1]:];assert base!=c
        for h in range(j,len(self.pairs)):
            prefix=base[:n[h+1]];l=ledger(f,prefix);bad=conflict(f,prefix,l)
            if bad:break
        assert bad
        idx=bad["i"];full_bad=conflict(f,base);assert full_bad
        a,bb=b.counts[j];timed=[];nearest=[];trials=0
        # Increasing distance proves minimality and retains all ties at the first legal distance.
        for radius in range(a+bb+1):
            for x in range(a+1):
                dy=radius-abs(x-xy[0])
                if dy<0:continue
                for y in sorted({xy[1]-dy,xy[1]+dy}):
                    if not 0<=y<=bb:continue
                    cfg=before+extension(b,j,pair,(x,y))+c[n[j+1]:]
                    l=ledger(f,cfg);trials+=1
                    timed.append([x,y,int(l[9]),bool(l[0])])
                    if l[0]:
                        nearest.append(dict(quota=[x,y],cert=self.cert(cfg),request_after=detail(f,cfg,idx,l)))
            if nearest:break
        assert nearest
        look=[];rollback=[]
        if h>j:
            front=[coded_state(f,base[:n[j+1]])]
            for t in range(j+1,min(j+3,len(self.pairs))):
                tick=perf_counter();children={};nt=0
                for p in front:
                    for v,_,_ in b.expand(p,t,PAIRS,[(0,0)],False):
                        nt+=1
                        if v.timing[-1]==0:children.setdefault(v.code,v)
                look.append(dict(depth=t-j,trials=nt,distinct_legal=len(children),wall_s=perf_counter()-tick))
                front=list(children.values())
            for t in range(h,max(-1,h-3),-1):
                tick=perf_counter();p=coded_state(f,base[:n[t]]);fp=self.pairs[t];solutions=[]
                for v,q,_ in b.expand(p,t,[fp],finite_offsets(b,p,t,fp),False):
                    candidate=v.code+base[n[t+1]:];ll=ledger(f,candidate)
                    solutions.append(dict(quota=q,full_legal=bool(ll[0]),slack=int(ll[9])))
                rollback.append(dict(back=h-t,window=t+1,trials=len(solutions),full_legal=sum(s["full_legal"] for s in solutions),
                                     attempts=solutions,wall_s=perf_counter()-tick))
        put(self.dest/f"window_{w:02}.json",dict(reference=self.ref,window=w,pair=pair,center=xy,
            first_failure=h+1,reported_failure=expect,min_L1=radius,reported_min=dist,minimum_candidates=nearest,
            blocked_request=bad,full_first_overdue=full_bad,reference_request=detail(f,c,idx,ledger(f,c)),
            known_balanced_config=base.hex(),tested=timed,trials=trials,lookahead=look,rollback=rollback,wall_s=perf_counter()-stime))
        print(self.k,w,h+1,radius,Counter(x["cert"]["status"] for x in nearest),flush=True)
if __name__=="__main__":
    psutil.Process().cpu_affinity([8]);stack=u.stack()
    for k in FOUR:
        a=Audit(k,stack)
        if k=="I06":
            if not (a.dest/"retention.json").exists():a.retained()
        else:
            for w,h,d in CLAIMS[k]:
                if not (a.dest/f"window_{w:02}.json").exists():a.contrast(w,h,d)
