"""Frozen, one-shot old-ON/new-ON/OFF static performance comparison. Never solve."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
PRIOR=REPO/'research/chapter3_certified_state_pruning_20261111/full_static'
ARMS=['old_on','optimized_on','off']
BASE='fe6216afcd0e8d94742adbc0ff62d70651dd60ba'
NOW=lambda:datetime.now(timezone.utc).isoformat()


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def save(path,value):
    with path.open('x') as stream:json.dump(value,stream,ensure_ascii=False,indent=2,default=str,allow_nan=False);stream.write('\n')
def rss():
    # Linux ru_maxrss is KiB, process-lifetime peak, not an incremental phase peak.
    if not sys.platform.startswith('linux'):return dict(available=False,reason='Linux-only ru_maxrss unit contract')
    return dict(available=True,bytes=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*1024,
                source='getrusage(RUSAGE_SELF).ru_maxrss',scope='current worker process lifetime peak, including imports and all prior phases')


def acceptance():
    path=HERE/'acceptance.json';doc=read(path)
    assert doc['enabled'] is True and doc['evidence_passed'] is True
    assert {'research/chapter3_experiments/milp.py','research/chapter3_experiments/joint_state_support.py'}<=set(doc['source_sha256'])
    assert doc['evidence_sha256']
    for name,value in {**doc['source_sha256'],**doc['evidence_sha256']}.items():assert sha(REPO/name)==value,('ACCEPTANCE_DRIFT',name)
    return path,doc


def verify(plan):
    accepted,_=acceptance();assert sha(accepted)==plan['acceptance_sha256']
    assert sha(Path(__file__))==plan['runner_sha256']
    assert sha(HERE/'compare_pair.py')==plan['comparator_sha256']
    for label,sources in plan['source_sha256'].items():
        for name,value in sources.items():assert sha(HERE/'frozen'/label/name)==value,(label,name)
    for name,value in plan['source_sha256']['optimized'].items():assert sha(REPO/name)==value,('LIVE_DRIFT',name)
    for name,value in plan['input_sha256'].items():assert sha(HERE/name)==value,name


def freeze():
    accepted,doc=acceptance();assert not (HERE/'plan.json').exists()
    prior=read(PRIOR/'plan.json');old=prior['frozen_sources_sha256'];new={};changed=[]
    assert len(old)==217
    for name,value in old.items():
        assert sha(PRIOR/'frozen'/name)==value,('OLD_SOURCE_DRIFT',name)
        current=sha(REPO/name);new[name]=current
        if current!=value:changed.append(name)
        assert current==value or name in {'research/chapter3_experiments/milp.py','research/chapter3_experiments/joint_state_support.py'},name
    # Verify the pre-optimization entry points against the published baseline.
    gitrepo=REPO.parent/'paper_publish_autol_lp_20261111'
    for name in ['research/chapter3_experiments/milp.py','research/chapter3_experiments/joint_state_support.py']:
        content=subprocess.check_output(['git','show',BASE+':'+name],cwd=gitrepo)
        assert hashlib.sha256(content).hexdigest()==old[name],name
    for label,sources in [('original',old),('optimized',new)]:
        for name in sources:
            src=PRIOR/'frozen'/name if label=='original' else REPO/name
            dst=HERE/'frozen'/label/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    for name,value in prior['input_sha256'].items():
        assert sha(PRIOR/name)==value;shutil.copy2(PRIOR/name,HERE/name)
    plan=dict(schema='strict-audit-optimization-three-arm-static-v1',frozen_utc=NOW(),
        base_commit=BASE,acceptance_sha256=sha(accepted),acceptance=doc,
        source_sha256={'original':old,'optimized':new},changed_existing_source_paths=changed,
        input_sha256=prior['input_sha256'],baseline_flags=prior['baseline_flags'],
        runner_sha256=sha(Path(__file__)),comparator_sha256=sha(HERE/'compare_pair.py'),
        order=ARMS,arm_config={'old_on':dict(source='original',prune_joint_states=True),
            'optimized_on':dict(source='optimized',prune_joint_states=True),'off':dict(source='optimized',prune_joint_states=False)},
        propagate_support=True,total_worker_budget_s=300,external_watchdog_s=380,calls_each=1,retries=False,
        expected_solver_calls=0,expected_candidate_thermal_calls=0,expected_initializations=0,
        cold_cache_contract='New worker process and Model per arm; no persistent or prefilled cache loaded; all cache/source identity preparation charged to build',
        timing_note='Budget starts at worker entry and covers imports/verification/build/export/certificate checks. Archive is recorded separately within worker wall; 380s watchdog is recovery protection.',
        memory_contract='Linux process-lifetime ru_maxrss, not an isolated build incremental peak; snapshots before imports, after build/export and after archive')
    save(HERE/'plan.json',plan);verify(plan)
    print(json.dumps(dict(plan_sha256=sha(HERE/'plan.json'),order=ARMS,changed=changed),indent=2))


def energy_certificates(model):
    q=lambda x:F.from_float(float(x));results=[]
    for certificate in model.energy_bound_certificates:
        model.budget.check();gates=certificate['gates'];sources=certificate['sources']
        for index,sign in zip(certificate['onehot_rows'],[1.,-1.]):
            row=model.rows[index];assert row['coef']=={g:sign for g in gates} and row['rhs']==sign
        cut=model.rows[certificate['cut_row']];assert cut['tag']=='energy_state_lower_bound'
        assert q(cut['coef'].get(certificate['target'],0))==-1
        maxima=[]
        for gate,index in zip(gates,certificate['source_rows']):
            old=model.rows[index];assert old['tag']=='complete_energy/lower'
            assert q(old['coef'].get(certificate['target'],0))==-1
            maximum=q(cut['coef'].get(gate,0))-q(cut['rhs'])-q(old['coef'].get(gate,0))+q(old['rhs'])
            for source in sources:
                delta=q(cut['coef'].get(source,0))-q(old['coef'].get(source,0))
                maximum+=max(delta*q(model.lb[source]),delta*q(model.ub[source]))
            assert maximum<=0,('ENERGY_CUT_NOT_IMPLIED',certificate['scene'],certificate['interval'],gate,str(maximum))
            maxima.append(str(maximum))
        results.append(dict(scene=certificate['scene'],interval=certificate['interval'],gates=len(gates),
            exact_residual_difference_maxima=maxima,passed=True))
    return results


def worker(arm):
    started=NOW();start=time.monotonic();out=HERE/'execution'/arm;out.mkdir(parents=True,exist_ok=False)
    save(out/'claim.json',dict(arm=arm,started_utc=started,pid=os.getpid()))
    result=dict(arm=arm,started_utc=started,success=False,new_model_build_calls=0,
        solver_calls=0,candidate_thermal_calls=0,initializations=0,peak_memory={'before_imports':rss()})
    banned=[]
    try:
        plan=read(HERE/'plan.json');verify(plan);config=plan['arm_config'][arm]
        sys.path.insert(0,str(HERE/'frozen'/config['source']/'research/chapter3_experiments'))
        import numpy as np
        import scipy
        import scipy.optimize as optimize
        import thermal,milp,joint_state_support
        from timing import MethodBudget
        from build_observer import BuildObserver
        def forbidden(*a,**kw):banned.append('FORBIDDEN_SOLVER_THERMAL_OR_PROCESS');raise RuntimeError(banned[-1])
        optimize.linprog=forbidden;optimize.milp=forbidden
        thermal.evaluate_candidate=forbidden;milp.evaluate_candidate=forbidden;milp.evaluate_model_candidate=forbidden
        subprocess.Popen=forbidden;subprocess.run=forbidden;os.system=forbidden
        budget=MethodBudget(max(0,plan['total_worker_budget_s']-(time.monotonic()-start)))
        observer=BuildObserver(budget,out/'build_progress.jsonl')
        instance=read(HERE/'input_instance.json');input_config=read(HERE/'input_config.json')
        assert {s['id']:len(s['stage_instances']) for s in instance['scenarios']}=={'AB_offset_0ms':6,'AC_offset_0ms':6}
        assert instance['execution_rules']['idle_policy']=='auto_low_immediate_v1'
        result.update(import_and_verification_s=time.monotonic()-start,new_model_build_calls=1)
        t=time.monotonic();model=milp.build_model(instance,input_config,budget=budget,progress=observer,
            propagate_support=True,prune_joint_states=config['prune_joint_states'],**plan['baseline_flags'])
        result['build_s']=time.monotonic()-t;observer.finish('MODEL_CONSTRUCTED');result['peak_memory']['after_build']=rss()
        t=time.monotonic();matrix=model.as_solver_dict();result['export_s']=time.monotonic()-t
        result['build_plus_export_s']=result['build_s']+result['export_s'];result['peak_memory']['after_export']=rss()
        t=time.monotonic();checks=energy_certificates(model);result['energy_certificate_check_s']=time.monotonic()-t;budget.check()
        result.update(success=True,variables=len(model.names),rows=len(model.rows),nonzeros=int(matrix['A'].nnz),
            joint_state_blocks={sid:sum(map(len,m['states'])) for sid,m in model.scenes.items()},
            events={sid:list(map(str,m['events'])) for sid,m in model.scenes.items()},
            row_family_counts=dict(Counter(r['tag'].split('/')[0] for r in model.rows)),
            construction=observer.snapshot(),energy_certificates_checked=len(checks),
            scientific_work_completed_at_s=time.monotonic()-start,
            environment=dict(python=sys.version,numpy=np.__version__,scipy=scipy.__version__,platform=sys.platform))
        t=time.monotonic();save(out/'energy_certificate_checks.json',checks)
        save(out/'energy_bound_certificates.json',model.energy_bound_certificates)
        save(out/'preprocessing.json',getattr(model,'preprocessing',{}))
        save(out/'options.json',model.options);save(out/'variable_names.json',model.names)
        metadata_hash=hashlib.sha256();conditional_count=0
        with (out/'row_metadata.jsonl').open('x') as stream:
            for index,row in enumerate(model.rows):
                value={k:v for k,v in row.items() if k!='coef'};value['index']=index
                value['gate_name']=None
                if row['tag'].split('/')[0] in ['thermal_propagation','complete_energy']:
                    gates=[model.names[j] for j in row['coef'] if model.names[j].startswith('w:')]
                    assert len(gates)==1;value['gate_name']=gates[0];conditional_count+=1
                line=json.dumps(value,sort_keys=True,separators=(',',':'),default=str)+'\n'
                stream.write(line);metadata_hash.update(line.encode())
        result['row_metadata_sha256']=metadata_hash.hexdigest();result['conditional_rows']=conditional_count
        with (out/'exported_model.npz').open('xb') as stream:
            np.savez_compressed(stream,A_data=matrix['A'].data,A_indices=matrix['A'].indices,A_indptr=matrix['A'].indptr,
                A_shape=matrix['A'].shape,b=matrix['b'],c=matrix['c'],lb=matrix['lb'],ub=matrix['ub'],intcon=matrix['intcon'])
        result['archive_s']=time.monotonic()-t;result['peak_memory']['after_archive']=rss();verify(plan)
    except BaseException:result['error']=traceback.format_exc()
    result.update(ended_utc=NOW(),worker_elapsed_s=time.monotonic()-start,forbidden_attempts=banned)
    save(out/'result.json',result)
    print(json.dumps({k:result.get(k) for k in ['arm','success','variables','rows','nonzeros','build_s','export_s','build_plus_export_s','worker_elapsed_s','error']},indent=2))
    if not result['success']:raise SystemExit(1)


def run():
    plan=read(HERE/'plan.json');verify(plan)
    save(HERE/'batch_claim.json',dict(started_utc=NOW(),plan_sha256=sha(HERE/'plan.json'),pid=os.getpid()))
    for arm in plan['order']:
        started=NOW();t=time.monotonic();command=[sys.executable,'-u',str(Path(__file__).resolve()),'worker','--arm',arm]
        with (HERE/f'{arm}.stdout.log').open('xb') as stdout,(HERE/f'{arm}.stderr.log').open('xb') as stderr:
            child=subprocess.Popen(command,stdout=stdout,stderr=stderr)
            try:code=child.wait(timeout=plan['external_watchdog_s']);expired=False
            except subprocess.TimeoutExpired:child.kill();code=child.wait();expired=True
        save(HERE/f'{arm}.command_receipt.json',dict(arm=arm,started_utc=started,ended_utc=NOW(),wall_s=time.monotonic()-t,
            argv=command,returncode=code,watchdog_expired=expired))
        print(json.dumps(dict(arm=arm,returncode=code,watchdog_expired=expired)),flush=True)
        if code or expired:
            save(HERE/'batch_stopped.json',dict(stopped_utc=NOW(),failed_arm=arm,remaining_not_launched=True));raise SystemExit(1)
    save(HERE/'batch_completed.json',dict(ended_utc=NOW(),static_build_calls=3,retries=0))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','run','worker']);parser.add_argument('--arm',choices=ARMS)
    args=parser.parse_args();{'freeze':freeze,'run':run,'worker':lambda:worker(args.arm)}[args.action]()
