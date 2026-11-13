"""Identity gates; a frozen candidate is not execution authorization."""
import hashlib,json
from pathlib import Path
PROTOCOL='R1-saved-C-noheur-observer-v1'
ARM='C_noheur_observe'

def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def save(p,v):
    with Path(p).open('x',encoding='utf-8',newline='\n') as f:
        json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False,default=str); f.write('\n')
def inside(root,name):
    root=Path(root).resolve(); p=(root/name).resolve()
    if p==root or not p.is_relative_to(root): raise ValueError('Path outside declared root')
    return p
def environment_snapshot():
    import sys,platform,numpy,scipy,psutil
    return dict(python=sys.version,python_executable=sys.executable,platform=platform.platform(),
                numpy=numpy.__version__,scipy=scipy.__version__,psutil=psutil.__version__)
def verify_plan(path,workspace,package):
    path=Path(path)
    if sha(path)!=read(path.with_suffix('.identity.json'))['sha256']: raise ValueError('Plan drift')
    p=read(path)
    fixed=dict(protocol=PROTOCOL,base_commit='77d6a8e4086931fb73212d2899bd1a0464a10644',
        arms=[ARM],execution_authorized=False,total_window_s=600,response_cutoff_s=550,
        maximum_native_calls=1,maximum_MATLAB_sessions=1,maximum_LP_calls=0,
        maximum_full_builds=0,maximum_complete_evaluations=2,retries=0,
        execution_directory='work/root_tail_observation_execution_v1')
    if any(p.get(k)!=v for k,v in fixed.items()): raise ValueError('Unsupported observation scope')
    for key,root in [('workspace_files',workspace),('package_files',package)]:
        for name,h in p[key].items():
            if sha(inside(root,name))!=h: raise ValueError('Source drift: '+name)
    for name,h in p['vendor_files'].items():
        if sha(name)!=h: raise ValueError('Installed R2023b file drift: '+name)
    if environment_snapshot()!=p['environment']: raise ValueError('Dependency environment drift')
    return p
def verify_approval(a,identity):
    expected=dict(approved=True,protocol=PROTOCOL,plan_sha256=identity,arms=[ARM],
        maximum_native_calls=1,maximum_MATLAB_sessions=1,total_window_s=600,response_cutoff_s=550,retries=0)
    if any(a.get(k)!=v for k,v in expected.items()) or not a.get('user_decision_reference'):
        raise PermissionError('A new explicit user approval bound to this frozen plan is required')
def claim_once(workspace,plan,claim):
    p=inside(workspace,plan['execution_directory']);p.mkdir(exist_ok=False)
    save(p/'claim.json',claim);return p
