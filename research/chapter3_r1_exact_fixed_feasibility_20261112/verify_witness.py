"""Independent integer-arithmetic verifier for the archived dyadic witness.

No solver, model builder, evaluator, witness construction or cached residuals.
Every binary64 coefficient and rational witness entry is represented as n/2**e.
Each row is reduced to one integer inequality after a common power-of-two shift.
"""
from pathlib import Path
from fractions import Fraction
import argparse,hashlib,json,time
from scipy.io import loadmat

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def dyadic(n,d):
    assert d>0 and d&(d-1)==0
    return n,d.bit_length()-1
def binary(v):return dyadic(*float(v).as_integer_ratio())
def minus(a,b):
    e=max(a[1],b[1]);return (a[0]<<(e-a[1]))-(b[0]<<(e-b[1]))
def verify(root):
    start=time.monotonic();wpath=root/'rational_witness/witness_fraction_lines.txt'
    x=[]
    for line in wpath.read_text(encoding='ascii').splitlines():
        v=Fraction(line);x.append(dyadic(v.numerator,v.denominator))
    results={}
    for representation in ['original','equalities']:
        path=root/'prepared'/(representation+'.mat');p=loadmat(path)
        assert len(x)==p['c'].size
        bounds=[];integers=[]
        for j,(lower,upper) in enumerate(zip(p['lb'].ravel(),p['ub'].ravel())):
            if minus(x[j],binary(lower))<0 or minus(x[j],binary(upper))>0:bounds.append(j)
        for value in p['intcon'].ravel():
            assert float(value).is_integer();j=int(value)-1
            if x[j][0]%(1<<x[j][1]):integers.append(j)
        matrices={}
        for key,rhskey in [('A','b'),('Aeq','beq')]:
            a=p[key].tocsr();b=p[rhskey].ravel();bad=[]
            for i in range(a.shape[0]):
                terms=[]
                for k in range(a.indptr[i],a.indptr[i+1]):
                    coefficient=binary(a.data[k]);value=x[int(a.indices[k])]
                    terms.append((coefficient[0]*value[0],coefficient[1]+value[1]))
                rhs=binary(b[i]);e=max([rhs[1]]+[v[1] for v in terms])
                residue=sum(n<<(e-t) for n,t in terms)-(rhs[0]<<(e-rhs[1]))
                if (residue>0 if key=='A' else residue!=0):bad.append(i)
            matrices[key]=dict(rows_checked=a.shape[0],strict_violations=bad)
        results[representation]=dict(matrix_sha256=sha(path),variables_checked=len(x),integer_columns_checked=p['intcon'].size,
            bound_violations=bounds,integer_violations=integers,rows=matrices,
            passed=not bounds and not integers and all(not v['strict_violations'] for v in matrices.values()))
    return dict(passed=all(v['passed'] for v in results.values()),witness_sha256=sha(wpath),representations=results,
        arithmetic='Independent integer shifts and products; no Fraction row summation or tolerance comparison',elapsed_s=time.monotonic()-start,
        solver_calls=0,model_builds=0,thermal_evaluations=0)
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    assert not args.out.exists();result=verify(args.root)
    with args.out.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False));raise SystemExit(not result['passed'])
