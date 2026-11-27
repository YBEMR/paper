"""Recover recorded pools, trace proofs and first divergence without rerunning a constructor."""
import gzip
import json
from collections import Counter,defaultdict
from functools import lru_cache

import psutil
from shared import *

def audit(case,stack):
    obj=cases()[case];root=A/"results"/case
    dest=HERE/"offline"/case;dest.mkdir(parents=True,exist_ok=True)
    api,fourth,_,_=stack
    inp=A/"registration/inputs"/obj["input"]
    assert sha(inp.read_bytes())==obj["input_sha256"]
    f=api.Flow(obj["word"],35,obj["case"],RAW,inp)
    e=f.eng;b=Builder(f,e);ends=limits(b)
    base=read(root/"runs/Base.json")
    pools=defaultdict(dict);parents={};layers=[];terminal=[]
    for v in events(root,base):
        if v[:2]==["begin","terminal"]:break
        if v[0]=="parent":parents[v[1]]=bytes.fromhex(v[2])
        if v[0]=="q4_action":
            _,pid,j,pair,q,delta,t=v
            code=parents[pid]+f.extension(b.types[j],*b.counts[j],*pair,*q)
            if not t[-1]:pools[j].setdefault(code,t)
        if v[:2]==["store","base"]:
            layers=v[2]["layers"];terminal=v[2]["terminal"]
    ranks=[];ancestry=[]
    with gzip.open(dest/"legal_pools.jsonl.gz","wt",encoding="utf8") as archive:
        for j,layer in enumerate(layers):
            order=sorted(pools[j],key=lambda c:(pools[j][c][4]+(pools[j][c][5] if j+1==len(ends) else 0),c))
            assert [c.hex() for c in order[:4]]==layer["retained"] and len(order)==layer["distinct"]
            ranks.append({c:i+1 for i,c in enumerate(order)})
            for i,c in enumerate(order,1):
                archive.write(json.dumps([j+1,i,c.hex(),pools[j][c]],separators=(",",":"))+"\n")
    full=list(ranks[-1]) if len(layers)==len(ends) else []
    assert [x.hex() for x in full[:12]]==terminal
    for j,layer in enumerate(layers):
        for c in map(bytes.fromhex,layer["retained"]):
            counts=[sum(bytes.fromhex(t).startswith(c) for t in layer2["retained"]) for layer2 in layers[j:]]
            ancestry.append(dict(window=j+1,retained=c.hex(),descendants=counts,
                                 empty_after=next((j+i+1 for i,n in enumerate(counts) if not n),None),
                                 terminal_descendants=sum(t.startswith(c) for t in full)))
    phys=root/"physical"
    pl={r["certificate"]["plan_sha256"]:r for r in map(json.loads,gzip.decompress((phys/"plans.jsonl.gz").read_bytes()).splitlines())}
    block=trace_reader(phys)
    @lru_cache(maxsize=6)
    def trace(key):
        r=pl[key];data=b"".join(block(h) for h in r["blocks"])
        assert sha(data)==r["trace_sha256"]
        return np.frombuffer(data,"<f8").reshape(r["shape"])
    def code(key):
        return u.encoded(row[:2] for row in pl[key]["plan"]["rows"][1::3])
    safe=read(root/"runs/NT60.json")["delivered"][-1]["plan"]
    assert pl[safe]["certificate"]["metrics"]["status"]=="SAFE"
    target=code(safe);state=b.root;path=[]
    for j,n in enumerate(ends):
        parent=state.code;want=target[:n];ext=want[len(parent):]
        ty=b.types[j];a,bb=b.counts[j];arr=np.frombuffer(ext,np.uint8)
        q=tuple(int(sum((arr>=10)&(ty==k))) for k in (0,1))
        match=[];covered=[False]*3
        for pair in PAIRS:
            if f.extension(ty,a,bb,*pair,*q)!=ext:continue
            center=e.quota(dict(f=state.timing[:2],k=state.timing[2:4]),j,pair,(a,bb))
            dx,dy=q[0]-center[0],q[1]-center[1]
            options=[(dx,dy)==(0,0),(dx,dy) in OFFSETS,q in extra(a,bb,*center)]
            covered=[x or y for x,y in zip(covered,options)]
            match.append([pair,center,[dx,dy]])
        assert match
        pair,_,offset=match[0]
        state=next(b.expand(state,j,[tuple(pair)],[tuple(offset)],False))[0]
        assert state.code==want
        rank=ranks[j].get(want) if j<len(ranks) else None
        active=j==0 or (j<=len(layers) and parent.hex() in layers[j-1]["retained"])
        loss=("missing_ancestor" if not active else "quota" if not covered[0] else "timing" if state.timing[-1] else
              "rank" if rank is not None and rank>(12 if j+1==len(ends) else 4) else "available")
        assert not(active and covered[0] and not state.timing[-1] and rank is None)
        path.append(dict(window=j+1,want=q,pairs_center_delta=match,balance=covered[0],
                         perturb=covered[1],composition=covered[1] or covered[2],late=state.timing[-1],
                         actual_parent=active,rank=rank,loss=loss))
    proofrows=[];phase_rows=[];testkeys=[safe];open_checks=0
    # Method-local caches. Reference and standalone grouping are not online comparators.
    for method in ("Base","Ordinary","Previous","Source","NT10","NT60","Q4"):
        r=read(root/f"runs/{method}.json")
        cache=[];starts={}
        for ev in events(root,r):
            if ev[0]=="cert_start":starts[ev[1]]=ev[3]
        for cert in r["certificates"]:
            key=cert["plan"];tr=trace(key);cfg=code(key)
            # Q4 uses native anticipative idle. Only actual physical byte equality is an admissible test there.
            match=None
            for prefix,proof,source in cache:
                rows=proof["rows"]
                if len(tr)>=rows and sha(tr[:rows,:14].astype("<f8").tobytes())==proof["events_sha256"]:
                    assert np.array_equal(trace(source)[:rows,:14],tr[:rows,:14])
                    match=(source,proof,cfg.startswith(prefix));break
            witness=hot(tr) if cert["status"]=="HOT" else None
            if match:
                i=match[1]["rows"]-1;node=match[1]["node"]
                assert cert["status"]!="SAFE" and tr[i,18+node]-tr[i,30]>80.,(case,key,cert["status"])
            if witness:
                prefix=settled_key(cfg,witness["tick"],b)
                cache.append((prefix,witness,key))
                if key not in testkeys and len(testkeys)<3:testkeys.append(key)
            if method!="Q4":
                for prefix,p,source in cache:
                    if cfg.startswith(prefix):
                        assert np.array_equal(trace(source)[:p["rows"],:14],tr[:p["rows"],:14])
            item=dict(method=method,phase=cert["phase"],n=cert["n"],plan=key,status=cert["status"],
                      kernel_s=cert["kernel_s"],observed_call_s=cert["t"]-starts[cert["n"]] if cert["n"] in starts else None,
                      proof=witness,duplicate_source=match[0] if match else None,
                      same_actions=match[2] if match else False)
            proofrows.append(item)
        seq=[a for a in proofrows if a["method"]==method and a["phase"] in ("terminal","repair")]
        phases=[a for a in seq if a["duplicate_source"]]
        phase_rows.append(dict(method=method,terminal_repair=len(seq),duplicate=len(phases),
                               gross_kernel_s=sum(a["kernel_s"] for a in phases),gross_call_s=sum(a["observed_call_s"] or 0 for a in phases)))
    for key in testkeys:
        tr=trace(key);cfg=code(key)
        for j,n in enumerate(ends[:-1],1):
            cut=j*e.dur-5
            physical=tr[tr[:,0]<cut,:14].copy();physical[-1,1]=cut
            got=open_events(f,cfg[:n],cut)
            assert np.array_equal(got,physical),(case,j,key,got.shape,physical.shape)
            open_checks+=1
    first=next((v for v in path if v["loss"]!="available"),None)
    common=[len({v[:n] for v in full}) for n in ends] if full else []
    hot_epochs=[]
    for item in proofrows:
        if item["method"]!="Base" or item["phase"]!="terminal" or not item["proof"]:continue
        p=item["proof"];cfg=code(item["plan"]);pref=settled_key(cfg,p["tick"],b)
        hot_epochs.append(dict(plan=item["plan"],proof=p,prefix_windows=ends.index(len(pref))+1,
                               shared_by_all_terminal=sum(t.startswith(pref) for t in full),
                               retained_by_layer=[sum(bytes.fromhex(t).startswith(pref) for t in layer["retained"]) for layer in layers]))
    record=dict(case=case,input_sha256=obj["input_sha256"],original_journal=base["journal"],layers=layers,
                terminal_distinct=len(full),terminal_shortlist=terminal,terminal_ancestor_counts=common,
                descendants=ancestry,thermal_convergence=hot_epochs,NT60=safe,path=path,first_loss=first,
                certified_runs=phase_rows,open_equal=open_checks,validated_plans=testkeys)
    put(dest/"audit.json",record);put(dest/"certificates.json",proofrows)
    print(case,"ready",len(full),open_checks,flush=True)

if __name__=="__main__":
    psutil.Process().cpu_affinity([0])
    stack=u.stack()
    for case in FOCUS:
        if not (HERE/"offline"/case/"certificates.json").exists():audit(case,stack)
