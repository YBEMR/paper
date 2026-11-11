"""Exact binary64-array audit of archived gate-zero rows; never constructs a model."""
from datetime import datetime, timezone
from fractions import Fraction as F
from pathlib import Path
import csv
import hashlib
import json
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ARCH = REPO/'research/chapter3_support_autol_lp_20261111/autol_build/rev02/execution/on'
STATIC = REPO/'research/chapter3_joint_state_static_20261111'
now = lambda: datetime.now(timezone.utc).isoformat()
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text())


def save(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2); stream.write('\n')


def freeze():
    files = [ARCH/'exported_model.npz', ARCH/'variable_names.json',
             STATIC/'reachability/certificates.json', STATIC/'numerics/row_metadata.jsonl']
    save(HERE/'gate_zero_plan.json', dict(frozen_utc=now(), source_sha256={str(p.relative_to(REPO)):sha(p) for p in files},
        script_sha256=sha(Path(__file__)), method='Exact Fraction.from_float audit of actual exported bounds/rows at w=0',
        new_model_builds=0,new_solver_calls=0,new_thermal_calls=0, wall_cap_s=120))


def run():
    started=now();t=time.monotonic();plan=read(HERE/'gate_zero_plan.json')
    assert sha(Path(__file__))==plan['script_sha256']
    for path, expected in plan['source_sha256'].items():assert sha(REPO/path)==expected,path
    names=read(ARCH/'variable_names.json');indices={n:i for i,n in enumerate(names)}
    certs=read(STATIC/'reachability/certificates.json')
    gates={}
    for interval in certs:
        for item in interval['states']:
            if item['status']=='PROVED_UNREACHABLE':
                name=f"w:{interval['scene']}:{interval['interval']}:{tuple(item['state'])}"
                gates[indices[name]]=dict(name=name,scene=interval['scene'],interval=interval['interval'],state=item['state'])
    assert len(gates)==2938
    matrix=np.load(ARCH/'exported_model.npz');a=matrix['A_data'];ind=matrix['A_indices'];ptr=matrix['A_indptr'];b=matrix['b'];lb=matrix['lb'];ub=matrix['ub']
    assert np.all(np.isfinite(lb)) and np.all(np.isfinite(ub))
    low=[F.from_float(float(x)) for x in lb];high=[F.from_float(float(x)) for x in ub]
    all_w={i for i,n in enumerate(names) if n.startswith('w:')}
    cache={};counts={g:0 for g in gates};failures=[];minimum_margin=None;max_violation=F(0);nrows=0
    with (HERE/'gate_zero_rows.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['row_index','tag','gate','gate_name','maximum_lhs_exact','rhs_exact','margin_exact','margin_float','strict_box_redundant'])
        writer.writeheader()
        with (STATIC/'numerics/row_metadata.jsonl').open() as metadata:
            for line in metadata:
                assert time.monotonic()-t<120
                row=json.loads(line);i=row['row_index']
                if row['tag'].split('/')[0] not in ['thermal_propagation','complete_energy']:continue
                ids=ind[ptr[i]:ptr[i+1]];values=a[ptr[i]:ptr[i+1]]
                gs=[int(j) for j in ids if int(j) in all_w];assert len(gs)==1
                g=gs[0]
                if g not in gates:continue
                maximum=F(0)
                for j,value in zip(ids,values):
                    j=int(j)
                    if j==g:continue
                    value=float(value);coefficient=cache.setdefault(value,F.from_float(value))
                    maximum+=coefficient*(high[j] if coefficient>=0 else low[j])
                rhs=F.from_float(float(b[i]));margin=rhs-maximum;counts[g]+=1;nrows+=1
                minimum_margin=margin if minimum_margin is None else min(minimum_margin,margin)
                record=dict(row_index=i,tag=row['tag'],gate=g,gate_name=gates[g]['name'],maximum_lhs_exact=str(maximum),rhs_exact=str(rhs),margin_exact=str(margin),margin_float=float(margin),strict_box_redundant=margin>=0)
                writer.writerow(record)
                if margin<0:
                    max_violation=max(max_violation,-margin)
                    if len(failures)<20:failures.append(record)
    assert nrows==29380 and set(counts.values())=={10}
    # Read back every row so failure count isn't truncated to examples.
    failed=0
    with (HERE/'gate_zero_rows.csv').open() as stream:
        for r in csv.DictReader(stream):failed+=r['strict_box_redundant']=='False'
    result=dict(started_utc=started,ended_utc=now(),wall_s=time.monotonic()-t,
        proposed_deleted_states=len(gates),conditional_rows_audited=nrows,
        strict_box_redundancy_passed=failed==0,failed_rows=failed,
        minimum_margin_exact=str(minimum_margin),minimum_margin_float=float(minimum_margin),
        maximum_violation_exact=str(max_violation),maximum_violation_float=float(max_violation),failure_examples=failures,
        interpretation='Positive margin means actual exported-row RHS covers exact maximization over actual exported binary64 box with w=0. Negative margin fails this strict full-box redundancy check; no tolerance forgiveness.',
        proof_scope='Whole finite binary64 variable box at gate zero; not only physical schedules or solver tolerance acceptance.',
        new_model_builds=0,new_solver_calls=0,new_thermal_calls=0,
        environment=dict(python=sys.version,numpy=np.__version__,platform=sys.platform))
    save(HERE/'gate_zero_result.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    if sys.argv[1:]==['freeze']:freeze()
    else:run()
