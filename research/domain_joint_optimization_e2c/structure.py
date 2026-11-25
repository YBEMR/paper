"""Conditional minimum support on a pinned configuration DAG via maximum antichain."""
import gzip,json
from samples import ROOT,read,write
from support import Problem,pairs,projection
from base import decode,transitions,np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import maximum_bipartite_matching

def check_case(case):
    p=Problem(case["case"]);key=case["source"]
    rows,_=decode(json.loads(gzip.decompress((ROOT/"prestates"/(key+".json.gz")).read_bytes())))
    edits={i:tuple(op) for i,op in case["targets"]}
    projection_result=projection(p,rows,edits)
    assert projection_result["support"]==case["historical_support"] and len(projection_result["support"])==case["projection"]
    levels=[[edits.get(i,r[:2])[1]] for i,r in enumerate(rows)]
    dur=[p.dur(i,r[0],levels[i][0]) for i,r in enumerate(rows)]
    t=np.array([r[2] for r in rows],dtype=np.int32)
    order=sorted(range(p.n),key=lambda i:(rows[i][2],p.finish(i,rows[i]),rows[i][1],i))
    pred=[{} for _ in rows]
    for i in range(p.n):
        if i%3:pred[i][i-1]=dur[i-1]
    for i,j,same in pairs(p,rows,levels):
        pred[j][i]=max(pred[j].get(i,0),dur[i]+5*(levels[i]!=levels[j]))
    lo=np.array([max(s-500,p.req[i//3]["release_tick"],5*(levels[i][0]!=0)) for i,s in enumerate(t)])
    hi=np.array([min(s+500,p.req[i//3]["deadline_tick"]-dur[i],p.horizon-dur[i]-5*(levels[i][0]!=0)) for i,s in enumerate(t)])
    for j in order:
        for i,w in pred[j].items():lo[j]=max(lo[j],lo[i]+w)
    for j in reversed(order):
        for i,w in pred[j].items():hi[i]=min(hi[i],hi[j]-w)
    assert np.all(lo<=hi)
    eligible=[i for i in order if i not in edits and lo[i]<=t[i]<=hi[i]]
    index={i:a for a,i in enumerate(eligible)};n=len(eligible)
    # arrival[j,k] is the lower bound at j implied by pinning eligible k to its original start.
    arrival=np.full((p.n,n),-10**8,dtype=np.int32);left=[];right=[]
    for j in order:
        line=arrival[j]
        for i,w in pred[j].items():np.maximum(line,arrival[i]+w,out=line)
        if j in index:
            b=index[j];a=np.flatnonzero(line>t[j]);left.extend(a.tolist());right.extend([b]*len(a));line[b]=t[j]
    graph=csr_matrix((np.ones(len(left),dtype=bool),(left,right)),shape=(n,n))
    match=maximum_bipartite_matching(graph,perm_type="column")
    mate={int(j):i for i,j in enumerate(match) if j>=0}
    reachable=set(np.flatnonzero(match<0).tolist());reached_right=set();stack=list(reachable)
    while stack:
        i=stack.pop()
        for b in graph.indices[graph.indptr[i]:graph.indptr[i+1]]:
            b=int(b)
            if b==match[i] or b in reached_right:continue
            reached_right.add(b)
            if b in mate and mate[b] not in reachable:
                reachable.add(mate[b]);stack.append(mate[b])
    pins={eligible[k] for k in reachable-reached_right}
    minimum=p.n-n+len(mate)
    assert len(pins)==p.n-minimum
    for i in pins:lo[i]=hi[i]=t[i]
    for j in reversed(order):
        for i,w in pred[j].items():hi[i]=min(hi[i],hi[j]-w)
    starts=np.maximum(lo,np.minimum(t,hi))
    for j in order:
        for i,w in pred[j].items():starts[j]=max(starts[j],starts[i]+w)
    assert np.all(starts<=hi)
    witness=[(r[0],levels[i][0],int(starts[i])) for i,r in enumerate(rows)]
    transitions(p,witness,set())
    support=[i for i,r in enumerate(witness) if r!=rows[i]]
    assert len(support)==minimum
    if case["minimum_expected"] is not None:assert minimum==case["minimum_expected"],(minimum,case)
    return dict(**case,minimum=minimum,eligible=n,incompatible_pairs=len(left),matching_size=len(mate),
                matching=[[eligible[i],eligible[int(j)]] for i,j in enumerate(match) if j>=0],
                support=support,placements=[[i,witness[i]] for i in support])
def run():
    out=[]
    for case in read(ROOT/"samples.json")["structural"]:
        out.append(check_case(case));write(ROOT/"structure.json",out)
