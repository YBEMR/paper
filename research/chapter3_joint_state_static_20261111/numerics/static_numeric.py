"""One frozen static ON build, then original-row analysis. No optimization."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction as F
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
ORIGIN=REPO/'research/chapter3_support_autol_lp_20261111/autol_build/rev02'

def now():return datetime.now(timezone.utc).isoformat()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def save(name,obj):
    with (HERE/name).open('x') as f:json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def fp(a):
    import numpy as np
    h=hashlib.sha256();h.update(str((a.dtype.str,a.shape)).encode());h.update(np.ascontiguousarray(a).tobytes());return h.hexdigest()
def verify(plan):
    for p,h in plan['source_sha256'].items():assert sha(ORIGIN/'frozen'/p)==h,p
    for p,h in plan['inputs_sha256'].items():assert sha(ORIGIN/p)==h,p
    assert sha(HERE/'static_numeric.py')==plan['runner_sha256']

def freeze():
    old=read(ORIGIN/'plan.json')
    plan=dict(frozen_utc=now(),base_commit='7631a16d420fbd8711af1e6cb2f35bc03cf9700d',
        archived_plan_sha256=sha(ORIGIN/'plan.json'),source_sha256=old['frozen_source_sha256'],
        inputs_sha256=old['frozen_input_sha256'],flags=old['baseline_flags'],propagate_support=True,
        static_build_calls=1,seconds=300,external_watchdog_seconds=380,
        runner_sha256=sha(HERE/'static_numeric.py'),archive_matrix_sha256=sha(ORIGIN/'execution/on/exported_model.npz'),
        scope='Only static formulation/coefficient construction and row analysis. No solver, candidate evaluator, or thermal trajectory.',
        metadata='Preserve exact Big-M, bound and rounding strings; analyze exported original rows without changing them.')
    verify(plan);save('plan.json',plan);print(json.dumps({'frozen_utc':plan['frozen_utc'],'plan_sha256':sha(HERE/'plan.json')}))

def summary_values(values):
    import numpy as np
    a=np.asarray(values,dtype=float)
    if not a.size:return {'count':0}
    nonzero=np.abs(a[a!=0]);out={'count':int(a.size),'zeros':int(np.sum(a==0)),
        'min':float(a.min()),'max':float(a.max()),'negative_count':int(np.sum(a<0)),
        'quantiles':{str(q):float(np.quantile(a,q)) for q in [0,.01,.1,.5,.9,.99,1]}}
    if nonzero.size:out.update(minimum_abs_nonzero=float(nonzero.min()),maximum_abs=float(nonzero.max()),
        abs_below_1e_9=int(np.sum(nonzero<1e-9)),abs_below_1e_12=int(np.sum(nonzero<1e-12)))
    return out

def worker():
    began=now();start=time.monotonic();plan=read(HERE/'plan.json');verify(plan)
    save('worker_claim.json',dict(started_utc=began,pid=os.getpid(),plan_sha256=sha(HERE/'plan.json')))
    sys.path.insert(0,str(ORIGIN/'frozen/research/chapter3_experiments'))
    import numpy as np,scipy
    import scipy.optimize as optimize
    import thermal,milp
    from timing import MethodBudget
    forbidden=[]
    def banned(*a,**kw):
        forbidden.append('FORBIDDEN_SOLVER_OR_EVALUATOR_ATTEMPT');raise RuntimeError(forbidden[-1])
    optimize.linprog=banned;optimize.milp=banned
    thermal.evaluate_candidate=banned;milp.evaluate_candidate=banned
    subprocess.Popen=banned;subprocess.run=banned;os.system=banned
    instance=read(ORIGIN/'input_instance.json');config=read(ORIGIN/'input_config.json')
    assert {s['id']:len(s['stage_instances']) for s in instance['scenarios']}=={'AB_offset_0ms':6,'AC_offset_0ms':6}
    assert instance['execution_rules']['idle_policy']=='auto_low_immediate_v1'
    budget=MethodBudget(plan['seconds']);build_start=time.monotonic()
    model=milp.build_model(instance,config,budget=budget,propagate_support=True,**plan['flags'])
    build_s=time.monotonic()-build_start
    export_start=time.monotonic();matrix=model.as_solver_dict();export_s=time.monotonic()-export_start
    original=np.load(ORIGIN/'execution/on/exported_model.npz',allow_pickle=False)
    actual={'A_data':matrix['A'].data,'A_indices':matrix['A'].indices,'A_indptr':matrix['A'].indptr,
        'A_shape':np.array(matrix['A'].shape),'b':matrix['b'],'c':matrix['c'],'lb':matrix['lb'],'ub':matrix['ub'],'intcon':matrix['intcon']}
    matches={k:bool(np.array_equal(v,original[k])) for k,v in actual.items()}
    names=read(ORIGIN/'execution/on/variable_names.json');assert names==model.names
    save('matrix_identity.json',dict(matches=matches,all_equal=all(matches.values()),
        fingerprints={k:fp(v) for k,v in actual.items()},old_fingerprints={k:fp(original[k]) for k in actual},
        exact_variable_names_equal=True,shape=list(matrix['A'].shape),nonzeros=int(matrix['A'].nnz),
        build_s=build_s,export_s=export_s,static_budget_elapsed_s=budget.elapsed))
    if not all(matches.values()):raise AssertionError('RECONSTRUCTED_MATRIX_DIFFERS_FROM_ARCHIVE')
    # Preserve row tags/M/error certificates; coefficients remain in old NPZ.
    with (HERE/'row_metadata.jsonl').open('x') as stream:
        for i,row in enumerate(model.rows):
            json.dump(dict(row_index=i,**{k:v for k,v in row.items() if k!='coef'}),stream);stream.write('\n')
    with (HERE/'variable_bounds.csv').open('x',newline='') as stream:
        w=csv.writer(stream);w.writerow(['variable_index','name','lower_exact','upper_exact','lower_export','upper_export','integer'])
        integer=set(model.integer)
        for i,name in enumerate(model.names):w.writerow([i,name,*map(str,model.bounds[i]),model.lb[i],model.ub[i],i in integer])
    families=defaultdict(lambda:dict(rows=0,nnz=0,conditional_rows=0,M=[],allowances=[],rhs=[]))
    pair_records=[];all_m=[];band_values=[];mismatch=0
    for i,row in enumerate(model.rows):
        family=row['tag'].split('/')[0];rec=families[family];rec['rows']+=1;rec['nnz']+=len(row['coef']);rec['rhs'].append(row['rhs']);rec['allowances'].append(float(F(row['rounding_allowance'])))
        if 'big_M' in row:rec['conditional_rows']+=1;v=float(F(row['big_M']));rec['M'].append(v);all_m.append(v)
        if family not in ['thermal_propagation','complete_energy'] or not row['tag'].endswith('/upper'):continue
        lower=model.rows[i+1];assert lower['tag']==family+'/lower'
        gate_indices={j for j in set(row['coef'])|set(lower['coef']) if model.names[j].startswith('w:')};assert len(gate_indices)<=1
        gate=next(iter(gate_indices),None)
        cols=(set(row['coef'])|set(lower['coef']))-gate_indices
        exact_negation=all(row['coef'].get(j,0)==-lower['coef'].get(j,0) for j in cols)
        upgate=0 if gate is None else row['coef'].get(gate,0);logate=0 if gate is None else lower['coef'].get(gate,0)
        width=F.from_float(row['rhs'])-F.from_float(float(upgate))+F.from_float(lower['rhs'])-F.from_float(float(logate))
        if exact_negation:band_values.append(float(width))
        else:mismatch+=1
        pair_records.append(dict(upper_row=i,lower_row=i+1,family=family,gate_variable=gate,
            gate_name=None if gate is None else model.names[gate],non_gate_coefficients_exact_negation=exact_negation,
            upper_M=row.get('big_M'),lower_M=lower.get('big_M'),
            gate1_exported_band_width_exact=str(width) if exact_negation else None,
            gate1_exported_band_width=float(width) if exact_negation else None,
            upper_rounding_allowance=row['rounding_allowance'],lower_rounding_allowance=lower['rounding_allowance']))
    with (HERE/'conditional_pairs.jsonl').open('x') as stream:
        for pair in pair_records:json.dump(pair,stream);stream.write('\n')
    family_stats={k:dict(rows=v['rows'],nnz=v['nnz'],conditional_rows=v['conditional_rows'],
        big_M=summary_values(v['M']),rounding_allowance=summary_values(v['allowances']),rhs=summary_values(v['rhs'])) for k,v in families.items()}
    save('row_family_statistics.json',family_stats)
    with (HERE/'row_family_statistics.csv').open('x',newline='') as stream:
        w=csv.writer(stream);w.writerow(['family','rows','nnz','conditional_rows','M_min','M_max','allowance_max'])
        for k,v in family_stats.items():w.writerow([k,v['rows'],v['nnz'],v['conditional_rows'],v['big_M'].get('min'),v['big_M'].get('max'),v['rounding_allowance']['max']])
    by_var=defaultdict(lambda:dict(lb=[],ub=[],width=[]))
    for i,name in enumerate(model.names):
        v=by_var[name.split(':')[0]];v['lb'].append(model.lb[i]);v['ub'].append(model.ub[i]);v['width'].append(model.ub[i]-model.lb[i])
    variable_stats={k:{j:summary_values(a) for j,a in v.items()} for k,v in by_var.items()}
    # Gate-1 bands are evaluated as exact rationals of the *exported doubles*,
    # not floating-point subtraction of two nearly equal M terms.
    thin_examples=sorted((p for p in pair_records if p['gate1_exported_band_width'] is not None),key=lambda p:p['gate1_exported_band_width'])[:20]
    all_stats=dict(matrix_coefficients=summary_values(matrix['A'].data),rhs=summary_values(matrix['b']),
        objective=summary_values(matrix['c']),lower_bounds=summary_values(matrix['lb']),upper_bounds=summary_values(matrix['ub']),
        variable_families=variable_stats,big_M=summary_values(all_m),
        conditional_pairs=len(pair_records),pair_non_gate_mismatch=mismatch,
        gate1_band_width=summary_values(band_values),gate1_band_negative=sum(v<0 for v in band_values),
        gate1_band_zero=sum(v==0 for v in band_values),thin_pair_examples=thin_examples,
        physical_nodes=len(instance['platform']['node_order']),row_counts={k:v['rows'] for k,v in family_stats.items()})
    save('statistics.json',all_stats)
    verify(plan)
    save('completion.json',dict(started_utc=began,ended_utc=now(),wall_s=time.monotonic()-start,
        build_s=build_s,export_s=export_s,analysis_archive_s=time.monotonic()-start-build_s-export_s,
        environment=dict(python=sys.version,numpy=np.__version__,scipy=scipy.__version__,platform=sys.platform),
        static_build_calls=1,new_LP_calls=0,new_MILP_calls=0,candidate_or_trajectory_evaluations=0,
        forbidden_attempts=forbidden,matrix_all_equal=True,archived_sources_unchanged=True))
    print(json.dumps(dict(build_s=build_s,export_s=export_s,rows=len(model.rows),families={k:v['rows'] for k,v in family_stats.items()},pair_non_gate_mismatch=mismatch),indent=2))

def run():
    plan=read(HERE/'plan.json');verify(plan)
    save('controller_claim.json',dict(started_utc=now(),plan_sha256=sha(HERE/'plan.json')))
    cmd=[sys.executable,'-u',str(HERE/'static_numeric.py'),'worker'];t=time.monotonic();started=now()
    with (HERE/'stdout.log').open('xb') as out,(HERE/'stderr.log').open('xb') as err:
        p=subprocess.Popen(cmd,stdout=out,stderr=err,cwd=REPO)
        try:rc=p.wait(timeout=380);expired=False
        except subprocess.TimeoutExpired:p.kill();rc=p.wait();expired=True
    save('command_receipt.json',dict(argv=cmd,cwd=str(REPO),started_utc=started,ended_utc=now(),wall_s=time.monotonic()-t,returncode=rc,watchdog_expired=expired))
    print(json.dumps(dict(returncode=rc,watchdog_expired=expired)));return rc

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','run','worker']);a=parser.parse_args()
    if a.action=='freeze':freeze()
    elif a.action=='run':raise SystemExit(run())
    else:worker()
