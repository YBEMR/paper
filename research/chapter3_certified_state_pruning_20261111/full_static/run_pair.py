"""One-shot static pair, gated by explicit checked acceptance. Never solve."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ARCHIVE = REPO/'research/chapter3_support_autol_lp_20261111/autol_build/rev02'
BASE = '9d972848adee5db8351d8f3be9638319bf0331d3'


def now(): return datetime.now(timezone.utc).isoformat()
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_text())
def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        stream.write('\n')


def acceptance():
    path = HERE/'acceptance.json'
    doc = read(path)
    assert doc['enabled'] is True and doc['evidence_passed'] is True
    sources = doc['source_sha256']
    assert {'research/chapter3_experiments/milp.py',
            'research/chapter3_experiments/joint_state_support.py'} <= set(sources)
    assert doc['evidence_sha256'], 'Acceptance must bind actual evidence'
    for name, expected in {**sources, **doc['evidence_sha256']}.items():
        assert sha(REPO/name) == expected, ('ACCEPTANCE_DRIFT', name)
    return path, doc


def verify(plan):
    path, accepted = acceptance()
    assert sha(path) == plan['acceptance_sha256']
    assert sha(HERE/'run_pair.py') == plan['runner_sha256']
    assert sha(HERE/'compare_pair.py') == plan['comparator_sha256']
    for name, expected in plan['frozen_sources_sha256'].items():
        assert sha(REPO/name) == expected, ('LIVE_SOURCE_DRIFT',name)
        assert sha(HERE/'frozen'/name) == expected, ('FROZEN_SOURCE_DRIFT',name)
    for name, expected in plan['input_sha256'].items():
        assert sha(HERE/name) == expected, ('INPUT_DRIFT',name)


def freeze():
    path, accepted = acceptance()  # No copying or scientific calls before gate.
    assert not (HERE/'plan.json').exists()
    prior = read(ARCHIVE/'plan.json')
    sources = dict(prior['frozen_source_sha256'])
    changed = []
    for name, old_sha in list(sources.items()):
        current = sha(REPO/name)
        if current != old_sha: changed.append(name)
        assert current == old_sha or name == 'research/chapter3_experiments/milp.py', name
        sources[name] = current
    extra = 'research/chapter3_experiments/joint_state_support.py'
    sources[extra] = sha(REPO/extra)
    for name in sources:
        target = HERE/'frozen'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO/name, target)
    for name, expected in prior['frozen_input_sha256'].items():
        assert sha(ARCHIVE/name) == expected
        shutil.copy2(ARCHIVE/name, HERE/name)
    plan = dict(schema='certified-joint-state-pruning-static-pair-v1', frozen_utc=now(),
        base_commit=BASE, acceptance_sha256=sha(path), acceptance=accepted,
        frozen_sources_sha256=sources, changed_existing_source_paths=changed,
        input_sha256=prior['frozen_input_sha256'], baseline_flags=prior['baseline_flags'],
        runner_sha256=sha(Path(__file__)), comparator_sha256=sha(HERE/'compare_pair.py'),
        propagate_support=True, only_comparison_switch='prune_joint_states',
        order=['off','on'], total_worker_budget_s=300, external_watchdog_s=380,
        starts='original unmodified option domain; no fixture start restriction',
        calls_each=1, retries=False, expected_solver_calls=0,
        expected_initializations=0, expected_candidate_thermal_calls=0,
        expected_counts_are_predictions_only=dict(removed_states=2938, removed_physical_rows=29380),
        budget_note='300s starts at worker entry; imports, source checks, build/export and pure certificate checks consume it. Final evidence writes may finish outside cooperative method timing; full wall and watchdog separately retained.')
    save(HERE/'plan.json', plan)
    print(json.dumps(dict(plan_sha256=sha(HERE/'plan.json'), source_files=len(sources),
                         changed_existing_source_paths=changed), indent=2))


def energy_certificates(model):
    """Exact binary64 box implication, per integral onehot gate, no solver."""
    q = lambda value: F.from_float(float(value))
    results = []
    for certificate in model.energy_bound_certificates:
        model.budget.check()
        gates = certificate['gates']; sources = certificate['sources']
        for idx, sign in zip(certificate['onehot_rows'], [1.0,-1.0]):
            row=model.rows[idx]
            assert row['coef'] == {gate:sign for gate in gates} and row['rhs']==sign
        cut=model.rows[certificate['cut_row']]
        assert cut['tag']=='energy_state_lower_bound'
        assert q(cut['coef'].get(certificate['target'],0)) == -1
        maxima=[]
        for gate,index in zip(gates,certificate['source_rows']):
            old=model.rows[index]
            assert old['tag']=='complete_energy/lower'
            assert q(old['coef'].get(certificate['target'],0)) == -1
            assert set(cut['coef']) <= {certificate['target'],*sources,*gates}
            maximum=q(cut['coef'].get(gate,0))-q(cut['rhs'])-q(old['coef'].get(gate,0))+q(old['rhs'])
            for source in sources:
                delta=q(cut['coef'].get(source,0))-q(old['coef'].get(source,0))
                maximum += max(delta*q(model.lb[source]),delta*q(model.ub[source]))
            assert maximum<=0, ('ENERGY_CUT_NOT_IMPLIED',certificate['scene'],certificate['interval'],gate,str(maximum))
            maxima.append(str(maximum))
        results.append(dict(scene=certificate['scene'],interval=certificate['interval'],
            cut_row=certificate['cut_row'],gates=len(gates),residual_difference_maxima=maxima,passed=True))
    return results


def worker(variant):
    start=time.monotonic(); started=now()
    out=HERE/'execution'/variant; out.mkdir(parents=True,exist_ok=False)
    save(out/'claim.json',dict(started_utc=started,pid=os.getpid(),variant=variant))
    result=dict(variant=variant,started_utc=started,success=False,new_model_build_calls=0,
                solver_calls=0,candidate_thermal_calls=0,initializations=0)
    banned=[];model=None;matrix=None
    try:
        plan=read(HERE/'plan.json');verify(plan)
        sys.path.insert(0,str(HERE/'frozen/research/chapter3_experiments'))
        import numpy as np
        import scipy
        import scipy.optimize as optimize
        import thermal
        import milp
        import joint_state_support
        from build_observer import BuildObserver
        from timing import MethodBudget
        def forbidden(*args,**kwargs):
            banned.append('FORBIDDEN_SOLVER_THERMAL_OR_PROCESS')
            raise RuntimeError(banned[-1])
        optimize.linprog=forbidden;optimize.milp=forbidden
        thermal.evaluate_candidate=forbidden;milp.evaluate_candidate=forbidden
        milp.evaluate_model_candidate=forbidden
        subprocess.Popen=forbidden;subprocess.run=forbidden;os.system=forbidden
        budget=MethodBudget(plan['total_worker_budget_s']-(time.monotonic()-start))
        observer=BuildObserver(budget,out/'build_progress.jsonl')
        instance=read(HERE/'input_instance.json');config=read(HERE/'input_config.json')
        assert {s['id']:len(s['stage_instances']) for s in instance['scenarios']}=={'AB_offset_0ms':6,'AC_offset_0ms':6}
        assert instance['execution_rules']['idle_policy']=='auto_low_immediate_v1'
        result.update(import_and_verification_s=time.monotonic()-start,new_model_build_calls=1)
        build_start=time.monotonic()
        model=milp.build_model(instance,config,budget=budget,progress=observer,
            propagate_support=True,prune_joint_states=variant=='on',**plan['baseline_flags'])
        observer.finish('MODEL_CONSTRUCTED');result['build_s']=time.monotonic()-build_start
        t=time.monotonic();matrix=model.as_solver_dict();result['export_s']=time.monotonic()-t
        t=time.monotonic();checks=energy_certificates(model);result['energy_certificate_check_s']=time.monotonic()-t
        budget.check()
        result.update(success=True,model_summary=model.summary(),construction=observer.snapshot(),
            joint_state_blocks={sid:sum(map(len,meta['states'])) for sid,meta in model.scenes.items()},
            events={sid:[str(v) for v in meta['events']] for sid,meta in model.scenes.items()},
            row_family_counts=dict(Counter(r['tag'].split('/')[0] for r in model.rows)),
            variables=len(model.names),rows=len(model.rows),nonzeros=int(matrix['A'].nnz),
            budget=budget.summary(),energy_certificates_checked=len(checks),
            environment=dict(python=sys.version,numpy=np.__version__,scipy=scipy.__version__,platform=sys.platform))
        save(out/'energy_certificate_checks.json',checks)
        save(out/'energy_bound_certificates.json',model.energy_bound_certificates)
        save(out/'preprocessing.json',getattr(model,'preprocessing',{}))
        save(out/'options.json',model.options);save(out/'variable_names.json',model.names)
        tags=[]
        for idx,row in enumerate(model.rows):
            family=row['tag'].split('/')[0]
            gates=[model.names[j] for j in row['coef'] if model.names[j].startswith('w:')]
            gate=gates[0] if family in ['thermal_propagation','complete_energy'] and len(gates)==1 else None
            tags.append(dict(index=idx,tag=row['tag'],gate_name=gate))
        save(out/'row_tags.json',tags)
        with (out/'exported_model.npz').open('xb') as stream:
            np.savez_compressed(stream,A_data=matrix['A'].data,A_indices=matrix['A'].indices,
                A_indptr=matrix['A'].indptr,A_shape=matrix['A'].shape,b=matrix['b'],c=matrix['c'],
                lb=matrix['lb'],ub=matrix['ub'],intcon=matrix['intcon'])
        verify(plan)
    except BaseException:
        result['error']=traceback.format_exc()
    result.update(ended_utc=now(),worker_elapsed_s=time.monotonic()-start,forbidden_attempts=banned)
    save(out/'result.json',result)
    print(json.dumps({k:result.get(k) for k in ['variant','success','variables','rows','nonzeros','build_s','export_s','worker_elapsed_s','error']},indent=2))
    if not result['success']:raise SystemExit(1)


def run():
    plan=read(HERE/'plan.json');verify(plan)
    save(HERE/'batch_claim.json',dict(started_utc=now(),plan_sha256=sha(HERE/'plan.json'),pid=os.getpid()))
    for variant in plan['order']:
        # Logs live outside worker output so mkdir(exist_ok=False) enforces one shot.
        started=now();t=time.monotonic()
        command=[sys.executable,'-u',str(Path(__file__).resolve()),'worker','--variant',variant]
        with (HERE/f'{variant}.stdout.log').open('xb') as stdout,(HERE/f'{variant}.stderr.log').open('xb') as stderr:
            process=subprocess.Popen(command,stdout=stdout,stderr=stderr)
            try:rc=process.wait(timeout=plan['external_watchdog_s']);expired=False
            except subprocess.TimeoutExpired:process.kill();rc=process.wait();expired=True
        receipt=dict(variant=variant,started_utc=started,ended_utc=now(),wall_s=time.monotonic()-t,
                     argv=command,returncode=rc,watchdog_expired=expired)
        save(HERE/f'{variant}.command_receipt.json',receipt);print(json.dumps(receipt),flush=True)
        if rc or expired:
            save(HERE/'batch_stopped.json',dict(stopped_utc=now(),failed_variant=variant,remaining_not_launched=True))
            raise SystemExit(1)
    save(HERE/'batch_completed.json',dict(ended_utc=now(),static_build_calls=2,retries=0))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','run','worker'])
    parser.add_argument('--variant',choices=['off','on']);args=parser.parse_args()
    {'freeze':freeze,'run':run,'worker':lambda:worker(args.variant)}[args.action]()
