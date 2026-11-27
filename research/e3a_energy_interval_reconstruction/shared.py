import csv, hashlib, io, json, os, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
DATA=HERE/'inputs'
RUN=Path(os.environ.get('E3_RUN',HERE/'runs')).resolve()
THREE=Path(os.environ.get('E3_THREE',HERE.parents[1])).resolve()
NT=Path(os.environ.get('E3_NT',THREE.parent/'nt')).resolve()
P1PATH=Path('research/cross_scene_taskflow_diagnostic')
NTPATH=Path('research/m1_transient_thermal_quota_20261126/frozen/p1')
def sha(b): return hashlib.sha256(b).hexdigest()
def read(p): return json.loads(p.read_bytes())
def put(p,o):
    p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_suffix(p.suffix+'.tmp')
    t.write_text(json.dumps(o,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n')
    t.replace(p)
def configure(name,mod):
    if name=='C10':
        mod.CFG['instances']['C10_HHHHLLHHLLLL_T35']=[list('HHHHLLHHLLLL'),1,35,1]
        return 'C10_HHHHLLHHLLLL_T35'
    return name
def request_bytes(p):
    b=io.StringIO(newline='');w=csv.DictWriter(b,fieldnames=p.req[0],lineterminator='\n')
    w.writeheader();w.writerows(p.req);return b.getvalue().encode()
def load_native(case,side='chapter3'):
    if side=='chapter3':
        sys.path.insert(0,str(THREE/'research/chapter3_final_evaluation'))
        import setup_inputs as api
        p=api.problem(configure(case,api))
    else:
        sys.path.insert(0,str(NT/NTPATH))
        import model,profiles
        p=model.Problem(configure(case,profiles))
    assert request_bytes(p)==(DATA/case/'requests.csv').read_bytes()
    assert all(r['deadline_ms']-r['release_ms']==300 for r in p.req)
    obj=read(DATA/case/'original.json'); assert obj['case']==p.case
    return p,([tuple(r) for r in obj['rows']],frozenset(map(tuple,obj['low'])))
