"""Isolated launcher for chapter-4 C/D. No upstream solver modification.
Check/plan is the default. Actual smoke and 24-cell batch require explicit commands.
"""
import os
for k in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS','NUMBA_NUM_THREADS'):
    os.environ[k]='1'
import argparse,csv,hashlib,importlib.metadata,json,platform,subprocess,sys
from pathlib import Path
from time import perf_counter
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent
PIN='e8ebada59faa1f9ad3f5ba4638c7b48a596d8c55'
RESULT_PIN='c585f3461378c3188b4a032991cd875fa5fa4aa4'
LOCK_BLOB='0de3ac756396bdb7b415ec5a2c88a3d56df76a4a'
ENDPOINTS_SHA='163c360abbc67f4150fd1e7c2e5a3bb9e1386b2120ecd77b9c124f924f46f13b'
ACCEPTANCE_BLOB='5ca26eed8b6c0718a9beaa5cf913f54103ea5967'
CASES=('D1','D2','F1','F2'); SEEDS=(101,102,103)

def sha(b):return hashlib.sha256(b).hexdigest()
def blob(b):return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def write(p,o):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(o,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n');tmp.replace(p)
def utc():return datetime.now(timezone.utc).isoformat()
def formal(repo):return Path(repo).resolve()/'research/chapter3_final_evaluation'
def identities():return {(x['case'],x['initial']):x for x in read(HERE/'initial_identities.json')}
def original_payload(case,plan):
    return json.dumps(dict(case=case,rows=plan[0],low=sorted(plan[1])),ensure_ascii=False,separators=(',',':')).encode()
def roster():
    return [dict(case=c,arm=a,method=m,mode='T3',seed=s,id=f'{c}_{m}_T3_{s}',budget_s=900) for c in CASES for s in SEEDS for a,m in [('C','AB'),('D','Proposed')]]
def check_bundle():
    b=read(HERE/'bundle_lock.json')
    for p,h in b['files'].items():
        assert sha((HERE/p).read_bytes())==h, f'Bundle drift: {p}'
    assert len(roster())==24 and sum(x['budget_s'] for x in roster())==21600
    return sha((HERE/'bundle_lock.json').read_bytes())
def package_versions(names):
    vals={}
    for n in names:
        try:vals[n]=importlib.metadata.version(n)
        except importlib.metadata.PackageNotFoundError:vals[n]='NOT_INSTALLED'
    return vals
def check_repo(repo):
    bundle=check_bundle();root=formal(repo);lp=root/'execution_lock.json'; assert blob(lp.read_bytes())==LOCK_BLOB,'Wrong execution lock'
    lock=read(lp)
    for p,h in lock['files'].items():assert sha((root/p).read_bytes())==h,f'Frozen source drift: {p}'
    assert read(root/'publication_freeze.json')['remote_protocol_commit']==PIN
    # Check the original frozen solver runtime (the formal run used an external runtime directory).
    rlock=read(root.parent/'global_config_coordination_g1/input_lock.json')
    runtime=Path(os.environ.get('G1_ORTOOLS',str(Path(repo).resolve().parent/'P1_worktree'/'.runtime-domain-cpsat'))).resolve()
    runtime_errors=[name for name,h in rlock['solver_runtime_files'] if not (runtime/name).is_file() or sha((runtime/name).read_bytes())!=h]
    assert blob((root/'acceptance.json').read_bytes())==ACCEPTANCE_BLOB
    assert sha((root/'results/endpoints.csv').read_bytes())==ENDPOINTS_SHA
    # Verify exact original A/B records from the published results, not an alternative start.
    rows=list(csv.DictReader((root/'results/endpoints.csv').open(encoding='utf-8',newline=''))); ids=identities()
    for case in CASES:
        selected=[x for x in rows if x['case']==case and x['method'] in ('AB','Proposed') and x['mode']=='T3']
        assert len(selected)==6 and {(x['method'],int(x['seed'])) for x in selected}=={(m,s) for m in ('AB','Proposed') for s in SEEDS}
        assert all(x['actual_status']=='SAFE' and x['receipt']=='COMPLETE' and x['initial_plan']==ids[case,'G2']['original_plan_sha256'] and abs(float(x['initial_J'])-ids[case,'G2']['energy_J'])<1e-9 for x in selected)
    sys.path.insert(0,str(runtime))
    try:current=dict(platform=platform.platform(),python=sys.version,packages=package_versions(lock['environment']['packages']))
    finally:sys.path.pop(0)
    comparable=all(current[k]==lock['environment'][k] for k in current) and not runtime_errors
    return dict(bundle_sha256=bundle,formal_protocol=PIN,result_reference=RESULT_PIN,lock_sha256=sha(lp.read_bytes()),checked_files=len(lock['files']),runtime_path=str(runtime),runtime_files=len(rlock['solver_runtime_files']),runtime_errors=runtime_errors,historical_environment=lock['environment'],current_environment=current,versions_match=comparable,roster=roster())
def bind(cpu):
    import psutil
    psutil.Process().cpu_affinity([int(cpu)])
def generate(case,out):
    # Separate process isolates the v1 profiles/module namespace from the chapter-3 solver.
    check_bundle();sys.path.insert(0,str(HERE/'v1'))
    from preflight import Engine,sha as vsha,raw as vraw,blob as vblob,requests,INPUT_PIN
    import io
    s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=requests(case)[0],lineterminator='\n');w.writeheader();w.writerows(requests(case));assert vblob(s.getvalue().encode())==INPUT_PIN[case]
    e=Engine(case,out);cr,meta=e.construct('quota',4);assert cr is not None
    c,r=cr;b=e.build(c,r);payload=dict(case=case,rows=b['rows'],low=sorted(b['low']));expect=identities()[case,'Q4']
    assert vsha(vraw(payload))==expect['v1_plan_sha256']
    assert sha(original_payload(case,(b['rows'],b['low'])))==expect['original_plan_sha256']
    write(Path(out)/'q4_generated.json',dict(plan=payload,construction=meta,expected=expect,E35_exact=b['ref_exact']))
def make_pool(repo,case,folder,cpu):
    bind(cpu); folder=Path(folder)
    subprocess.run([sys.executable,'-B',str(__file__),'_generate','--case',case,'--out',str(folder)],check=True,timeout=150)
    sys.path.insert(0,str(formal(repo)))
    from setup_inputs import checked_problem,g1io
    from assets import write as original_write
    from fifo import Compact
    from construct import assemble,idle_plan
    from model import independent_events,transitions
    p=checked_problem(case);q=read(folder/'q4_generated.json');o=q['plan'];rows=[tuple(x) for x in o['rows']];low=frozenset(map(tuple,o['low']));plan=(rows,low)
    cfg=tuple(x[:2] for x in rows[1::3]);m=Compact(p);st=m.replay(cfg);assert st is not None
    from fractions import Fraction
    assert m.joules(st)==Fraction(q['E35_exact']) and idle_plan(p,assemble(p,cfg))==plan
    transitions(p,*plan);independent_events(p,*plan)
    g1io.OUT=folder/'evidence';key,cert=g1io.assess(p,plan);expect=q['expected'];met=cert['metrics']
    assert key==expect['original_plan_sha256'] and met['status']=='SAFE' and abs(met['E_J']-expect['energy_J'])<1e-9
    original_write(folder/'pool.json',[dict(generator='Q4',width=4,depth=len(cfg),plan=key,in_time=True)])
    original_write(folder/'result.json',dict(case=case,plan=key,status=met['status'],E_J=met['E_J'],E_bounds=met['E_bounds']))
def smoke_worker(repo,case,method,seed,folder,begin,end,budget,charge,cpu):
    bind(cpu);sys.path.insert(0,str(formal(repo)))
    from setup_inputs import checked_problem,ROOT
    from assets import read as original_read
    from fifo import Compact
    from trial import trial
    p=checked_problem(case);m=Compact(p);f=Path(folder)
    trial(p,m,case,method,'T3',int(seed),f,f.parent.parent/'pools'/case,float(begin),float(end)-4,float(budget),float(charge),original_read(ROOT/'execution_lock.json')['parameters'],smoke=True)
def run_child(argv,folder,budget,charge=0):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False);begin=perf_counter();end=begin+budget-charge
    command=[sys.executable,'-B','-u',str(__file__),*argv,'--out',str(folder)]
    if argv[0]=='_smoke':command+=['--begin',str(begin),'--end',str(end),'--budget',str(budget),'--charge',str(charge)]
    write(folder/'start.json',dict(command=command,utc=utc(),budget_s=budget,prior_charge_s=charge))
    code=None;status='ERROR'
    with (folder/'worker.log').open('xb') as log:
        try:
            ret=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=max(.01,end-perf_counter()));code=ret.returncode;status='COMPLETE' if code==0 and (folder/'result.json').is_file() else 'ERROR'
        except subprocess.TimeoutExpired:status='TIME_LIMIT'
    spent=perf_counter()-begin
    if status=='COMPLETE' and charge+spent>budget:status='LATE_OUTPUT'
    info=dict(status=status,exit_code=code,wall_s=spent,charged_s=charge+spent,ended=utc())
    write(folder/'receipt.json',info);return info

def load_original_batch(repo):
    sys.path.insert(0,str(formal(repo)))
    import formal_batch
    assert Path(formal_batch.__file__).resolve()==formal(repo)/'formal_batch.py'
    return formal_batch

def check_destination(path,repo):
    p=Path(path).resolve();r=Path(repo).resolve();assert not p.is_relative_to(r), 'Run output must be outside the original repository'
    assert not p.is_relative_to(HERE), 'Run output must be outside immutable runner bundle'
    assert not p.exists(),'Output already exists; no overwrite or implicit resume'
    return p

def smoke(args,report):
    assert args.confirm_original_environment and report['versions_match'],'Original environment/versions must be verified'
    batch=load_original_batch(args.repo);cpus=batch.physical_cpus();assert cpus
    out=check_destination(args.out,args.repo);out.mkdir(parents=True);write(out/'check.json',report);cpu=cpus[0]
    pool=run_child(['_pool','--repo',str(Path(args.repo).resolve()),'--case','D1','--cpu',str(cpu)],out/'pools/D1',180)
    assert pool['status']=='COMPLETE',pool
    receipts=[]
    for arm,method in [('C','AB'),('D','Proposed')]:
        folder=out/'cells'/f'D1_{method}_T3_101';rec=run_child(['_smoke','--repo',str(Path(args.repo).resolve()),'--case','D1','--method',method,'--seed','101','--cpu',str(cpu)],folder,90,pool['charged_s'])
        result=read(folder/'result.json') if (folder/'result.json').exists() else {}
        good=rec['status']=='COMPLETE' and result.get('status')=='SAFE' and result.get('configuration_details',{}).get('rounds',0)>=1 and result.get('post',{}).get('rounds',0)>=1 and result.get('elapsed_s',1e9)<=90 and result.get('initial',{}).get('plan')==identities()['D1','Q4']['original_plan_sha256']
        receipts.append(dict(arm=arm,passed=good,receipt=rec,case='D1',method=method));write(out/'smoke_progress.json',receipts)
    gate=dict(status='PASS' if all(x['passed'] for x in receipts) and len(receipts)==2 else 'FAIL',bundle_sha256=report['bundle_sha256'],lock_sha256=report['lock_sha256'],environment=report['current_environment'],node=platform.node(),receipts=receipts,utc=utc())
    write(out/'smoke_gate.json',gate);assert gate['status']=='PASS',gate

def execute(args,report):
    assert args.confirm_original_environment and report['versions_match'],'Original environment/versions must be verified'
    gate=read(args.smoke_gate);assert gate['status']=='PASS' and gate['bundle_sha256']==report['bundle_sha256'] and gate['lock_sha256']==report['lock_sha256'] and gate['environment']==report['current_environment'] and gate['node']==platform.node()
    batch=load_original_batch(args.repo);cpus=batch.physical_cpus();assert cpus
    out=check_destination(args.out,args.repo);out.mkdir(parents=True);(out/'cells').mkdir();write(out/'check.json',report);write(out/'batch_start.json',dict(utc=utc(),roster=roster(),physical_cpus=cpus,smoke_gate_sha256=sha(Path(args.smoke_gate).read_bytes())))
    status='INTERRUPTED';pools={};receipts=[]
    try:
        for ix,case in enumerate(CASES):
            pools[case]=run_child(['_pool','--repo',str(Path(args.repo).resolve()),'--case',case,'--cpu',str(cpus[ix%len(cpus)])],out/'pools'/case,180)
            write(out/'pool_receipts.json',pools)
            if pools[case]['status']!='COMPLETE':status='POOL_ERROR';return
        # Original worker and parent budget enforcement. One pair at a time, same core, rotated across pairs.
        for idx,row in enumerate(roster()):
            cpu=cpus[(idx//2)%len(cpus)];charge=pools[row['case']]['charged_s']
            rec=batch.run_process('cell',row,out/'cells'/row['id'],cpu,charge,PIN)
            receipts.append({**rec,'arm':row['arm']});write(out/'batch_progress.json',receipts)
        status='FINISHED'
    finally:
        write(out/'batch_end.json',dict(outcome=status,utc=utc(),completed_receipts=len(receipts),registered=24,receipts=receipts))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['plan','check','smoke','execute','_generate','_pool','_smoke'],nargs='?',default='plan');p.add_argument('--repo',type=Path);p.add_argument('--out',type=Path);p.add_argument('--case',choices=CASES);p.add_argument('--method',choices=['AB','Proposed']);p.add_argument('--seed',type=int,default=101);p.add_argument('--cpu',type=int);p.add_argument('--begin',type=float);p.add_argument('--end',type=float);p.add_argument('--budget',type=float);p.add_argument('--charge',type=float);p.add_argument('--smoke-gate',type=Path);p.add_argument('--confirm-original-environment',action='store_true');a=p.parse_args()
    if a.action=='plan':print(json.dumps(dict(bundle_sha256=check_bundle(),registered=len(roster()),budget_s=sum(r['budget_s'] for r in roster()),roster=roster()),indent=2));return
    if a.action=='_generate':generate(a.case,a.out);return
    if a.action=='_pool':make_pool(a.repo,a.case,a.out,a.cpu);return
    if a.action=='_smoke':smoke_worker(a.repo,a.case,a.method,a.seed,a.out,a.begin,a.end,a.budget,a.charge,a.cpu);return
    assert a.repo is not None,'--repo required';report=check_repo(a.repo)
    if a.action=='check':print(json.dumps(report,indent=2));return
    assert a.out is not None,'--out required';
    if a.action=='smoke':smoke(a,report)
    else:assert a.smoke_gate is not None,'--smoke-gate required';execute(a,report)
if __name__=='__main__':main()
