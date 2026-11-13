"""Saved C events only: no MATLAB startup, solver, model build or thermal evaluator."""
from pathlib import Path
import json,hashlib,argparse
ROOT=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'work/root_tail_readonly_20261113')
OUT=parser.parse_args().output.resolve();OUT.mkdir(exist_ok=False)
CASES={'saved_C_240':'work/on_budget_candidate_A420_execution_v1',
       'formal_C':'work/formal_abc_execution_v1/C',
       'repeat_C':'work/mechanism_trials_execution_v1/C_repeat',
       'noheur_C':'work/mechanism_trials_execution_v1/C_noheur'}
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
records={};bindings={}
for name,rel in CASES.items():
    folder=ROOT/rel;matlab=folder/'matlab'
    # Archived outputs only. Do not infer absent internal solver counters.
    paths=sorted(matlab.glob('request_000001.event_*.json'))
    events=[read(p) for p in paths]
    response=matlab/'request_000001.response.json'
    n=read(response)
    root=[e for e in events if e.get('values',{}).get('phase')=='rootlp']
    heur=[e for e in events if e.get('values',{}).get('phase')=='heuristics']
    done=[e for e in events if e.get('state')=='done']
    rt=root[0]['values']['time'] if root else None
    ht=heur[-1]['values']['time'] if heur else None
    dt=done[-1]['values']['time'] if done else None
    full_vectors=[e['x'] for e in events if e.get('x')]
    records[name]=dict(source=rel,Heuristics=n['options']['Heuristics'],Display=n['options']['Display'],
        BranchRule=n['options']['BranchRule'],CutGeneration=n['options']['CutGeneration'],
        CutMaxIterations=n['options']['CutMaxIterations'],native_MaxTime=n['options']['MaxTime'],
        root_callback_time_s=rt,last_candidate_callback_time_s=ht,done_callback_time_s=dt,
        post_root_to_done_s=dt-rt if dt is not None and rt is not None else None,
        silent_tail_after_last_candidate_s=dt-ht if dt is not None and ht is not None else None,
        root_objective=root[0]['values']['fval'] if root else None,
        callback_values=[dict(event_number=e['event_number'],state=e.get('state'),values=e.get('values'),
                             vector_length=len(e.get('x',[]))) for e in events],
        final_output=n['output'],exitflag=n['exitflag'],final_vector_length=len(n['x']),
        all_callback_vectors_equal_final=all(x==n['x'] for x in full_vectors) if full_vectors else None,
        matlab_log_bytes=(matlab/'matlab.log').stat().st_size,
        solver_warning_message=n.get('solver_warning_message'),solver_warning_identifier=n.get('solver_warning_identifier'),
        missing=['cut pass start/end/count history','per-subproblem LP iterations/timings','branch scoring probe count',
                 'root LP primal vector/basis','CPU/memory time series','native internal numerical diagnostics'],
        attribution='UNKNOWN; event silence is not a phase timer')
    for p in paths+[response,matlab/'matlab.log']:
        bindings[p.relative_to(ROOT).as_posix()]=sha(p)
install=Path('F:/Matlab2023/Program_Files/MATLAB_R2023b/toolbox/optim')
source_files=[install/'optim/intlinprog.m',install/'+optim/+options/Intlinprog.m',
              install/'+optim/+algorithm/IntlinprogBranchAndCut.p',install/'optim/savemilpsolutions.m',
              ROOT/'work/mechanism_trials_v1/process_monitor.py']
# Protected implementation: metadata/hash only, never decode or modify it.
local_sources=[dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size,
                   inspection='hash only; protected code not decoded or interpreted' if p.suffix=='.p' else 'plain source static reading') for p in source_files]
checks={'four_existing_runs':len(records)==4,
        'all_four_root_callbacks':all(v['root_callback_time_s'] is not None for v in records.values()),
        'all_four_zero_final_nodes':all(v['final_output']['numnodes']==0 for v in records.values()),
        'all_four_display_off_empty_log':all(v['Display']=='off' and v['matlab_log_bytes']==0 for v in records.values()),
        'same_final_and_callback_vectors':all(v['all_callback_vectors_equal_final'] for v in records.values()),
        'existing_files_unchanged':all(sha(ROOT/p)==h for p,h in bindings.items())}
result=dict(base_commit='7eb15d0df119490e006c301c82f4fbc2a141b94c',date='2026-11-13',
    records=records,source_bindings=bindings,local_matlab_static_sources=local_sources,checks=checks,
    scientific_calls=dict(MATLAB_sessions=0,MILP=0,LP=0,full_builds=0,full_thermal_evaluations=0),
    interpretation='Read-only event timeline. Does not create new feasibility or optimality evidence.')
(OUT/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(checks=checks,tail_s={k:round(v['silent_tail_after_last_candidate_s'],6) for k,v in records.items()})))
