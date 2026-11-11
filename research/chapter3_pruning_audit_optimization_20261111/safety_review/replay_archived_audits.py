"""Cold audit-helper replay only, never build the original R1 model."""
import ast
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import re
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ARCH = REPO/'research/chapter3_certified_state_pruning_20261111/full_static'
SOURCE = REPO/'research/chapter3_experiments'
UTC = timezone.utc
now = lambda: datetime.now(UTC).isoformat()
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
read = lambda path: json.loads(path.read_text())


def save(name, data):
    with (HERE/name).open('x') as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False); stream.write('\n')


def freeze():
    files = [SOURCE/'milp.py', SOURCE/'joint_state_support.py',
        ARCH/'input_instance.json', ARCH/'execution/on/variable_names.json',
        ARCH/'execution/on/exported_model.npz', ARCH/'execution/on/preprocessing.json',
        ARCH/'execution/on/result.json', ARCH/'comparison.json']
    save('replay_plan.json', dict(frozen_utc=now(), base_commit='fe6216afcd0e8d94742adbc0ff62d70651dd60ba',
        source_sha256={str(p.relative_to(REPO)):sha(p) for p in files},
        script_sha256=sha(Path(__file__)), cooperative_seconds=90, outer_watchdog_seconds=120,
        cold_helper_contexts=1, full_R1_builds=0, solver_calls=0, thermal_calls=0,
        scope='Replay new gate-off audit helper against saved old per-state certificates, not a model-construction performance sample'))


def run():
    begin=time.monotonic();started=now();plan=read(HERE/'replay_plan.json')
    assert sha(Path(__file__))==plan['script_sha256']
    for name,digest in plan['source_sha256'].items():assert sha(REPO/name)==digest,name
    sys.path.insert(0,str(SOURCE))
    import numpy as np
    import milp
    import scipy.optimize as opt
    import thermal
    from thermal import Budget
    def forbidden(*a,**kw):raise AssertionError('PROHIBITED_BUILD_SOLVE_OR_THERMAL_CALL')
    milp.build_model=forbidden;opt.linprog=forbidden;opt.milp=forbidden
    thermal.evaluate_candidate=forbidden;milp.evaluate_candidate=forbidden;milp.evaluate_model_candidate=forbidden
    budget=Budget(seconds=max(0,90-(time.monotonic()-begin)))
    instance=read(ARCH/'input_instance.json')
    names=read(ARCH/'execution/on/variable_names.json');index={name:i for i,name in enumerate(names)}
    with np.load(ARCH/'execution/on/exported_model.npz') as data:
        low=data['lb'].tolist();high=data['ub'].tolist();cost=data['c'].tolist();integers=data['intcon'].tolist()
    context=milp.Model(instance,budget)
    context.names=names;context.lb=low;context.ub=high;context.c=cost;context.integer=integers
    context.bounds=[(F.from_float(a),F.from_float(b)) for a,b in zip(low,high)]
    context.preprocessing={'joint_state_pruning':{}}
    assert not context.rows and not context.options and not hasattr(context,'_joint_state_gate_audit_cache')
    old_result=read(ARCH/'execution/on/result.json')
    events=old_result['events'];del old_result
    removed=read(ARCH/'comparison.json')['removed_names'];groups={}
    for name in removed:
        _,sid,literal,state=name.split(':',3)
        groups.setdefault((sid,int(literal)),[]).append(tuple(ast.literal_eval(state)))
    # Saved dict insertion order is scene/interval order. Independently check
    # every extracted state's identity against the explicit removed-name set.
    text=(ARCH/'execution/on/preprocessing.json').read_text();decoder=json.JSONDecoder()
    old_audits=[]
    for match in re.finditer(r'"gate_off_audit"\s*:\s*',text):
        value,_=decoder.raw_decode(text,match.end());old_audits.append(value)
    del text
    ordered=[(scene['id'],l) for scene in instance['scenarios']
             for l in range(len(events[scene['id']])-1)]
    assert len(old_audits)==len(ordered)==424
    records=[];covered=[];rows=0;fields=['checked_rows','gate_fixed_value','maximum_residual','minimum_slack','exact_binary64_box']
    for (sid,l),old in zip(ordered,old_audits):
        budget.check()
        expected=groups.get((sid,l),[])
        old_states={tuple(row['state']):row for row in old.get('states',[])}
        assert set(expected)==set(old_states),(sid,l)
        sources=[index[f'theta:{sid}:{l}:{node}'] for node in instance['platform']['node_order']]
        sources += [index[f'q:{sid}:{l}:{node}'] for node in instance['platform']['node_order']]
        targets=[index[f'theta:{sid}:{l+1}:{node}'] for node in instance['platform']['node_order']]
        energy=index[f'energy:{sid}:{l}']
        duration=F(events[sid][l+1])-F(events[sid][l])
        new=milp._audit_joint_state_gate_off(context,sources,targets,energy,expected,duration)
        assert new['states_checked']==old['states_checked'] and new['rows_checked']==old['rows_checked']
        for row in new.get('states',[]):
            state=tuple(row['state']);reference=old_states[state]
            assert {k:row[k] for k in fields}=={k:reference[k] for k in fields},(sid,l,state)
            covered.append(f'w:{sid}:{l}:{state}');rows+=row['checked_rows']
        records.append(dict(scene=sid,interval=l,states=len(expected),rows=new['rows_checked'],
                            old_new_scalar_certificates_equal=True,cache_snapshot=new.get('cache_snapshot')))
    assert set(covered)==set(removed) and len(covered)==2938 and rows==29380
    assert not context.rows and not context.options
    assert (context.names,context.lb,context.ub)==(names,low,high)
    budget.check()
    for name,digest in plan['source_sha256'].items():assert sha(REPO/name)==digest,name
    summary=dict(started_utc=started,ended_utc=now(),wall_s=time.monotonic()-begin,
        source_hashes_unchanged=True,intervals=424,deleted_states=2938,represented_rows=29380,
        all_old_new_per_state_exact_scalar_certificates_equal=True,
        cold_start=True,helper_contexts=1,full_model_builds=0,solver_calls=0,thermal_calls=0,
        strict_cache_stats=context._joint_state_gate_audit_cache['stats'],
        cache_templates=len(context._joint_state_gate_audit_cache['entries']),
        old_saved_evidence_used=True,performance_sample=False,
        environment=dict(python=sys.version,numpy=np.__version__,platform=sys.platform))
    save('replay_interval_results.json',records);save('replay_result.json',summary)
    print(json.dumps(summary,indent=2,ensure_ascii=False))


if __name__=='__main__':
    if sys.argv[1:] == ['freeze']:freeze()
    elif sys.argv[1:] == ['run']:run()
    else:raise SystemExit('Use freeze or run')
