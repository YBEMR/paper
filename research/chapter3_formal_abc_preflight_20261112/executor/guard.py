"""Frozen identity and single-use arm claims. Preparing/testing never authorizes science."""
import hashlib,json
from pathlib import Path

def environment_snapshot():
    import sys,platform,numpy,scipy,psutil
    return dict(python=sys.version,python_executable=sys.executable,platform=platform.platform(),
                numpy=numpy.__version__,scipy=scipy.__version__,psutil=psutil.__version__)

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def save(path,value):
    with Path(path).open('x',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False,default=str);f.write('\n')
def inside(root,relative):
    root=Path(root).resolve();p=(root/relative).resolve()
    if p==root or not p.is_relative_to(root):raise ValueError('Path escaped declared root')
    return p
def verify_plan(path,workspace,package):
    path=Path(path)
    if sha(path)!=read(path.with_suffix('.identity.json'))['sha256']:raise ValueError('Frozen plan drift')
    plan=read(path)
    required=dict(protocol='full-R1-fresh-ABC-v1',arms=['A','B','C'],maximum_native_calls_per_arm=1,
        total_window_s=600,response_cutoff_s=550,watchdog_s=680,retries=0,execution_authorized=False,
        execution_directory='work/formal_abc_execution_v1',representation='complement_gate_split_constant_v1')
    if any(plan.get(k)!=v for k,v in required.items()):raise ValueError('Unsupported formal scope')
    for k,root in [('workspace_files',workspace),('package_files',package)]:
        for name,expected in plan[k].items():
            if sha(inside(root,name))!=expected:raise ValueError('Frozen source drift: '+name)
    return plan
def verify_approval(approval,identity):
    required=dict(approved=True,plan_sha256=identity,protocol='full-R1-fresh-ABC-v1',arms=['A','B','C'],
                  maximum_native_calls_per_arm=1,total_window_s=600,retries=0)
    if any(approval.get(k)!=v for k,v in required.items()):raise PermissionError('New explicit approval bound to this ABC plan is required')
    if not approval.get('user_decision_reference'):raise PermissionError('Missing actual user decision')
def claim_once(workspace,plan,claim):
    folder=inside(workspace,plan['execution_directory']);folder.mkdir(parents=True,exist_ok=False)
    save(folder/'claim.json',claim);return folder
