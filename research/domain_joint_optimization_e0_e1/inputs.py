import gzip,hashlib,json,platform,subprocess,sys
from importlib.metadata import version
from common import *
from compact import Layout
from model import Problem

BL={'model.py':'738809425d68d7de1d0939d3d37596550820e89f','heat.py':'69bef3c1917b874a9ceacf2ecaabfe14addfbd7e',
    'search.py':'cb3b20dfeb8ea10f3aedba759c5a94c87cff5a7d','config/p1_frozen.json':'1cde1d8142c6253a0deb4f78dbe6960c7c99fb70',
    'config/gpu_profiles.csv':'c77aa183d451e7d8cd15e1d0510e8f8bc21f6f40','config/cpu_npu_profiles.csv':'a6eeae251d0ecd0107601ab8621c3c54ea753aa3'}
def git(*a):return subprocess.check_output(["git",*a],cwd=REPO)
def region_data(p,rows,low,ids):
    lay=Layout(p,rows);norm=lay.normalize(low);envelopes=[];ids=set(ids)
    for i in sorted(ids):
        t=rows[i][2];r=p.req[i//3]
        for u,k in p.options[i]:
            du=p.dur(i,u,k);a=max(r["release_tick"],t-500,0);b=min(t+500,r["deadline_tick"]-du,p.horizon-du)
            if a<=b:envelopes.append([i,u,k,a,b,b+du])
    intervals={d:[(a,end) for i,u,k,a,b,end in envelopes if DOM[u]==d] for d in range(3)}
    prior=[];mask={};boundaries={}
    for key,(sig,left) in lay.gaps.items():
        d,a,b,f,k=sig
        allowed=(key[1] in ids or any(j in ids for j in left) or any(l<=b and a<=r for l,r in intervals[d]))
        prior.append([list(sig),allowed,key in norm,key[1],list(left)])
    for d in range(3):
        if not intervals[d]:mask[d]=None;boundaries[d]=[];continue
        lo=min(a for a,b in intervals[d]);hi=max(b for a,b in intervals[d])
        ranges=[(sig[1],sig[2]) for sig,allowed,_,_,_ in prior if allowed and sig[0]==d]
        lo=min([lo]+[a for a,b in ranges]);hi=max([hi]+[b for a,b in ranges])
        left=max([0]+[e for s,e,k,i in lay.work[d] if i not in ids and e<=lo])
        right=min([p.horizon]+[s for s,e,k,i in lay.work[d] if i not in ids and s>=hi])
        mask[d]=[left,right]
        boundaries[d]=[i for s,e,k,i in lay.work[d] if i not in ids and s<=right+5 and e>=left-5]
    return dict(case=p.case,ids=sorted(ids),tick_ms="1/10",envelopes=envelopes,original_gaps=prior,
                mask=mask,local_fixed_domain_rows=boundaries,fixed_rows_source=archived(p.case)[0],
                external_DAG_neighbors=sorted({n for i in ids for n in ([i-1] if i%3 else [])+([i+1] if i%3!=2 else []) if n not in ids}))
def restore(r):
    return dict(r,prior={tuple(sig):(perm,low) for sig,perm,low,_,_ in r['original_gaps']},
                mask={int(d):v for d,v in r['mask'].items()})
def preflight():
    head=git("rev-parse","HEAD").decode().strip()
    assert git("rev-parse","HEAD^").decode().strip()==BASE
    manifest={}
    def verify(path,base,sig):
        b=path.read_bytes();rel=path.relative_to(REPO).as_posix()
        ident=hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
        assert ident==git("rev-parse",base+":"+rel).decode().strip() and (not sig or sig==sha(b))
        manifest[rel]=dict(commit=base,blob=ident,sha256=sha(b));return ident
    sg=json.loads((OLD/"RESULT_SHA256.json").read_bytes())["files"]
    fg=json.loads((FOLLOW/"results/snapshot.json").read_bytes())["files"]
    verify(OLD/"RESULT_SHA256.json",V1,None);verify(FOLLOW/"results/snapshot.json",BASE,None)
    for path in sorted(OLD.glob("*.py")):verify(path,V1,sg[path.name])
    for path in sorted(FOLLOW.glob("*.py")):verify(path,BASE,None)
    for n,ident in BL.items():assert verify(OLD/n,V1,sg[n])==ident
    for path in sorted(ROOT.glob("*.py")):verify(path,head,None)
    verify(ROOT/"taskbook.md",head,None);verify(FOLLOW/"results/preflight.json",BASE,fg["preflight.json"])
    results={};regions={}
    for c in ("D1","D2","D3"):
        p=Problem(c);k,(rows,low)=archived(c)
        for n in ["g3_thermal/"+c+"_G3.json","instances/"+c+".csv","logs/plans/"+k+".json.gz",
                  "certificates/"+k+"_continuous.json.gz","certificates/"+k+"_schedule.json.gz","certificates/"+k+"_reset.json.gz"]:
            verify(OLD/n,V1,sg[n])
        with (OLD/"instances"/(c+".csv")).open() as f:req=list(csv.DictReader(f))
        assert all(all(str(v)==r[k0] for k0,v in x.items()) for r,x in zip(req,p.req)) and len(req)==len(p.req)
        cert=json.loads(gzip.decompress((OLD/"certificates"/(k+"_continuous.json.gz")).read_bytes()))["metrics"]
        assert cert["status"]=="SAFE" and k.startswith({"D1":"63fb7bdee8e8","D2":"ef0518b03899","D3":"409a58b6369b"}[c])
        results[c]=dict(g3=k,J=cert["E_J"])
        if c!="D3":
            h,_=archived(c,True);results[c]["historical"]=h
            for name in ["summary.csv","plans/"+h+".json.gz","certificates/"+h+".json","certificates/"+h+".npz"]:
                verify(FOLLOW/"results"/name,BASE,fg[name])
            ids=[148,149,133,147,139] if c=="D1" else [289,295,296,310,311]
            regions[c]=region_data(p,rows,low,ids)
        else:
            for name,center,half,u,quota in [("R1",50000,2000,2,[0,0,1,1]),("R2",50000,2000,3,[0,0,1,1]),
                    ("R3",25000,3000,2,[0]*4),("R4",75000,3000,3,[1]*4)]:
                chosen=[]
                for scene in quota:
                    eligible=sorted((i for i in range(1,p.n,3) if i not in chosen and p.req[i//3]["scene"]==scene and
                                    abs(rows[i][2]-center)<=half),key=lambda i:(rows[i][0]!=u,abs(rows[i][2]-center),i))
                    if eligible:chosen.append(eligible[0])
                if len(chosen)!=4:regions[name]=dict(case=c,status="UNCONSTRUCTIBLE",selected=chosen);continue
                rg=region_data(p,rows,low,[j for i in chosen for j in [i-1,i,i+1]])
                regions[name]=dict(rg,center_tick=center,preferred_unit=u,selected_mains=chosen)
    overlap={a+"_"+b:sorted(set(regions[a].get("ids",[]))&set(regions[b].get("ids",[]))) for a in regions for b in regions if a<b and regions[a]["case"]==regions[b]["case"]}
    save("regions.json",dict(regions=regions,overlap=overlap))
    save("manifest.json",dict(identities=manifest,plans=results,freeze=head,
        system=platform.platform(),python=sys.version,packages={x:version(x) for x in ("ortools","protobuf","numpy","numba","scipy","sympy","matplotlib")},
        region_sha256=sha((ROOT/"regions.json").read_bytes()),seed=101,workers=1,tolerance_J=TOL,
        budget_s=dict(input=300,E0=900,per_E1=300,archive=600,total=9000,wall=9600)))
