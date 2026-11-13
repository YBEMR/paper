"""Summarize sealed D285 receipts, no scientific model/evaluator/solver imports.

Decimal interval comparisons use Fraction; percentages are display-only floats.
MAT files are read only to count the stored matrix dimensions and nonzeros.
"""
import hashlib
import json
import re
from collections import Counter
from fractions import Fraction
from pathlib import Path
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUN = ROOT / 'work/cplex_ABC_execution_v2'

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def interval(e):
    return tuple(map(Fraction, e['weighted_energy_J']))

def difference(a, b):
    lo, hi = a[0] - b[1], a[1] - b[0]
    return dict(exact_lower=str(lo), exact_upper=str(hi),
                approximate_J=float((lo + hi) / 2), strictly_positive=lo > 0)

summary = dict(protocol='D285-CPLEX-fresh-ABC-entry-fixed-v1',
    frozen_commit='366169c4c6cec9e15dc9c2076b1fae0794ac63e6',
    plan_sha256=hashlib.sha256((ROOT / 'work/cplex_ABC_v3/plan.json').read_bytes()).hexdigest(),
    host=read(ROOT / 'work/cplex_ABC_D285_launch_v1/host_receipt.json'),
    post_run_solver_calls=0, post_run_model_builds=0, post_run_thermal_evaluations=0,
    arms={}, comparisons={}, interpretation_limits=[
        'One complete R1, one fixed-order A/B/C batch, seed 0: no repeatability/general speedup claim.',
        'Numerical matrix admission is not exact-rational primal certification.',
        'Native bounds/gaps lack an independent exact dual/optimality certificate.',
        'SAFE uses original in-window evaluator, not a second physical implementation.',
        'Callback candidates were not separately thermally evaluated; no early SAFE credit.',
        'No cross-solver or historical saved-matrix acceleration comparison.'])
initials = {}
finals = {}
parameters = {}
schedules = {}
for arm in 'ABC':
    run = RUN / arm
    s = read(run / 'scientific_snapshot.json')
    c = read(run / 'controller_receipt.json')
    dispatch = read(RUN / (arm + '_dispatch_receipt.json'))['record']
    outer = read(RUN / (arm + '_outer_completion.json'))
    original = loadmat(run / 'original_zero_based.mat')
    complement = loadmat(run / 'complement_zero_based.mat')
    counts = {}
    for name, data in [('original', original), ('complement', complement)]:
        counts[name] = dict(variables=int(data['c'].size), integer_variables=int(data['intcon'].size),
            inequalities=int(data['A'].shape[0]), equalities=int(data['Aeq'].shape[0]),
            A_nnz=int(data['A'].nnz), Aeq_nnz=int(data['Aeq'].nnz))
    model = read(run / 'model_summary.json')
    cert = read(run / 'representation_certificate.json')
    init = read(run / 'initial_admission.json')
    final = s['final_admission']
    audit = read(OUT / (arm + '_audit.json'))
    log = (run / 'native.log').read_text(encoding='utf-8')
    log_lines = log.splitlines()
    root = re.search(r'Root relaxation solution time = ([\d.]+) sec\. \(([\d.]+) ticks\)', log)
    tree = re.search(r'Root node processing \(before b&c\):\s*Real time\s*=\s*([\d.]+) sec.*?Sequential b&c:\s*Real time\s*=\s*([\d.]+) sec', log, re.S)
    events = [json.loads(line) for line in (run / 'events.jsonl').read_text().splitlines()]
    a, b = interval(s['initial']), interval(s['final'])
    initials[arm] = a
    finals[arm] = b
    parameters[arm] = read(run / 'parameters_at_solve.json')
    changes = []
    for scene, rows in final['candidate']['scenes'].items():
        old = {r['stage_id']: r for r in init['candidate']['scenes'][scene]}
        for row in rows:
            changed = [key for key in ('unit','opp','start_ms') if row[key] != old[row['stage_id']][key]]
            if changed:
                changes.append(dict(scene=scene, stage=row['stage_id'], changed_fields=changed,
                                    initial=old[row['stage_id']], final=row))
    schedules[arm] = dict(initial_identity=init['schedule_identity'], final_identity=final['schedule_identity'],
        initial=init['candidate'], final=final['candidate'], changed_stages=len(changes), changes=changes)
    phase_durations = {p['stage']: p['end_s'] - p['start_s'] for p in s['phase_records']}
    science_durations = {p['stage']: p['end_s'] - p['start_s'] for p in s['science_phases']}
    response = s['native_response']
    files = [p for p in run.rglob('*') if p.is_file()]
    assert root and tree, 'Expected native timing evidence missing'
    summary['arms'][arm] = dict(
        outcome=s['outcome'], strict_success=s['strict_success'], layers=c['layers'], audit=audit,
        counts=counts, original_options=model['options'], formulation=model['formulation'],
        reduction=read(run/'reduction_verification.json'), projection_checks=cert['checks'],
        readback_passed=read(run/'readback.json')['passed'], runtime=read(run/'runtime.json'),
        initialization_attempts=len(read(run/'initialization.json')['attempts']),
        full_build_attempts=s['full_build_attempts'], solve_attempts=s['solve_attempts'],
        complete_evaluation_attempts=s['complete_evaluation_attempts'],
        event_kind_counts=dict(Counter(e['kind'] for e in events)),
        mip_start=c['observation']['MIP_start_acceptance'],
        log_evidence=[dict(line=i+1,text=line) for i,line in enumerate(log_lines)
            if any(v in line for v in ('MIP start','Reduced MIP','Root relaxation','Root node processing','cuts applied','Total (root'))],
        root_LP_seconds=float(root[1]) if root else None, root_LP_ticks=float(root[2]) if root else None,
        root_node_seconds=float(tree[1]) if tree else None, branch_and_cut_seconds=float(tree[2]) if tree else None,
        native_response=response, allocation=read(run/'allocation.json'), response_ack=s['response_ack'],
        first_native_candidate_note='Use raw callback events for progress only; final vector alone obtained full evaluation.',
        initial_schedule_identity=init['schedule_identity'], final_schedule_identity=final['schedule_identity'],
        different_schedule=not final['same_initial'], changed_stage_count=len(changes),
        final_OPP_counts=dict(Counter(r['opp'] for rows in final['candidate']['scenes'].values() for r in rows)),
        initial_energy_interval_J=s['initial']['weighted_energy_J'], final_energy_interval_J=s['final']['weighted_energy_J'],
        strict_energy_saved=difference(a,b), approximate_saving_percent=100*(1-float((b[0]+b[1])/(a[0]+a[1]))),
        final_scenes={scene:{k:e[k] for k in ('state','complete','energy_accuracy_met','energy_J','peaks_degC','covered_until_s')}
                      for scene,e in s['final']['scenes'].items()},
        numerical_admission={name:final[name] for name in ('original','complement')},
        timing=dict(phase_durations=phase_durations, nested_science_durations=science_durations,
            full_evaluation_archived_s=s['final']['archived_elapsed_s'], seal_s=s['sealed_elapsed_s'],
            controller_completion=read(run/'controller_completion.json'), outer_completion=outer,
            actual_arm_wall_s=dispatch['actual_arm_wall_including_outer_cleanup_s'],
            charged_shared_setup_s=dispatch['shared_setup_charged_s'],
            method_before_dispatch_archive_s=dispatch['method_elapsed_including_shared_setup_s'],
            method_including_final_dispatch_archive_s=outer['after_dispatch_archive_elapsed_s']),
        resources=dict(worker_job=c['owned']['job'],worker_accounting=c['owned']['job_accounting'],
            outer_job=dispatch['outer_job_limits'],outer_accounting=dispatch['outer_job_accounting'],
            sampled_worker_private_peak=c['owned']['peak_sampled_private_bytes'],
            sampled_controller_private_peak=c['owned']['peak_parent_private_bytes'],
            entry_available_bytes=c['owned']['available_at_entry'],
            inner_cleanup_ok=c['owned']['cleanup_ok'],outer_cleanup_ok=dispatch['outer_cleanup_ok']),
        evidence_files=len(files), evidence_bytes=sum(p.stat().st_size for p in files))
    assert audit['audit_passed'] and audit['retained_strict_success']
    assert s['solve_attempts'] == 1 and s['full_build_attempts'] == 1 and s['complete_evaluation_attempts'] == 2
    assert all(cert['checks'].values()) and summary['arms'][arm]['readback_passed']

summary['common_initial_interval_identical'] = initials['A'] == initials['B'] == initials['C']
summary['common_initial_schedule_identical'] = len({v['initial_identity'] for v in schedules.values()}) == 1
summary['parameter_differences'] = {k:{a:parameters[a].get(k) for a in 'ABC'}
    for k in set().union(*(p.keys() for p in parameters.values()))
    if not parameters['A'].get(k) == parameters['B'].get(k) == parameters['C'].get(k)}
assert set(summary['parameter_differences']) == {'parameters.timelimit'}
assert summary['common_initial_interval_identical'] and summary['common_initial_schedule_identical']
for high, low in [('A','B'), ('B','C'), ('A','C')]:
    summary['comparisons'][high+'_minus_'+low] = difference(finals[high],finals[low])
summary['batch'] = {k:v for k,v in read(RUN/'batch_receipt.json').items() if k not in ('arms','records','results')}
save('schedule_changes.json', schedules)
save('summary.json', summary)
for arm,v in summary['arms'].items():
    print(arm,json.dumps({k:v[k] for k in ('counts','root_LP_seconds','root_node_seconds','branch_and_cut_seconds',
        'changed_stage_count','final_OPP_counts','approximate_saving_percent','evidence_bytes')}))
print('PARAMETER_DIFFERENCES',summary['parameter_differences'])
print('ENERGY_ORDER',{k:v['approximate_J'] for k,v in summary['comparisons'].items()})
