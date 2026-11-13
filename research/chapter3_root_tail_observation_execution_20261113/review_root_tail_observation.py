"""Finite semantic review of already sealed data; no relaxation of the frozen O2 gate."""
from pathlib import Path
from fractions import Fraction
import json,sys,collections,time
import numpy as np
from scipy.io import loadmat
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'work/root_tail_observer_v1'))
from guard import read,save,sha
start=time.monotonic()
folder=ROOT/'work/root_tail_observation_execution_v1/C_noheur_observe'
out=ROOT/'work/root_tail_observation_audit_v1';audit=read(out/'audit.json')
r=read(folder/'receipt.json');manifest=read(folder/'scientific_artifact_manifest.json')
path=folder/'matlab/request_000001.profile.mat'
assert manifest['matlab/request_000001.profile.mat']['sha256']==sha(path)==r['observation']['profile_sha256']
assert r['snapshot']['completed_at_elapsed_s']<600 and r['observation']['profile_read_elapsed_s']<550
p=loadmat(path,simplify_cells=True)['profileData'];h=p['FunctionHistory'];table=list(p['FunctionTable'])
ids={v['FunctionName']:i+1 for i,v in enumerate(table)}
anchors=r['observation']['native_observation']['anchors'];rows=[];base=None
marker_indices={}
for a in anchors:
    index=ids['solve_model>d279_'+a['label']+'_marker']
    hits=np.where((h[1]==index)&(h[0]==0))[0];assert len(hits)==1
    at=int(hits[0]);marker_indices[a['label']]=at
    epoch=Fraction(int(h[2,at]))+Fraction(int(h[3,at]),1000000)
    if base is None: base=epoch
    lo=Fraction(str(a['before_s']))-(epoch-base)-Fraction(1,100000)
    hi=Fraction(str(a['after_s']))-(epoch-base)+Fraction(1,100000)
    rows.append(dict(label=a['label'],history_event_index_zero_based=at,function_index=index,
        profile_seconds=int(h[2,at]),profile_microseconds=int(h[3,at]),
        request_tic_bracket=[a['before_s'],a['after_s']],
        frozen_offset_relative_to_first_marker_epoch_s=[str(lo),str(hi)]))
gap=max(Fraction(x['frozen_offset_relative_to_first_marker_epoch_s'][0]) for x in rows)-min(Fraction(x['frozen_offset_relative_to_first_marker_epoch_s'][1]) for x in rows)
first=marker_indices['root'];last=marker_indices['end']
# Ordinal history only; not an accepted conversion of internal function times to request-tic.
stack=[];ordinal_gaps=[]
for i in range(h.shape[1]-1):
    fid=int(h[1,i]);kind=int(h[0,i])
    if kind==0:stack.append(fid)
    elif stack and stack[-1]==fid:stack.pop()
    else:stack=[]
    own_time=(h[2,i+1]-h[2,i])+(h[3,i+1]-h[3,i])/1e6
    if first<=i<last and own_time>1:
        ordinal_gaps.append(dict(after_history_event_index_zero_based=i,
            after_function=table[fid-1]['FunctionName'],after_kind='entry' if kind==0 else 'exit',
            before_history_event_index_zero_based=i+1,before_function=table[int(h[1,i+1])-1]['FunctionName'],
            profiler_clock_difference_s=float(own_time),
            active_visible_stack=[dict(index=f,name=table[f-1]['FunctionName'],file=table[f-1]['FileName']) for f in stack],
            accepted_request_clock_duration=False,mechanism_inside_protected_function='UNKNOWN'))
top=[dict(index=i+1,name=t['FunctionName'],file=t['FileName'],type=t['Type'],calls=int(t['NumCalls']),
    inclusive_profile_time_s=float(t['TotalTime'])) for i,t in sorted(enumerate(table),key=lambda z:z[1]['TotalTime'],reverse=True)[:20]]
vendor_paths=[Path(t['file']) for t in top if t['file'] and Path(t['file']).suffix.lower()=='.p']
vendor_hashes={str(p):sha(p) for p in vendor_paths}
log=folder/'display_prefix.bin';assert sha(log)==manifest['display_prefix.bin']['sha256']
raw=log.read_bytes()
try:
    decoded=raw.decode('utf-8',errors='strict');encoding='utf-8'
except UnicodeDecodeError:
    decoded=raw.decode('gb18030',errors='strict');encoding='gb18030 compatible with local Chinese console bytes'
worker=read(folder/'worker_claim.json')['pid']
resource=next(v for v in audit['resource_summary'] if v['pid']==worker)
source=ROOT/'work/root_tail_observer_v1/saved_adapter_base.py'
lines=source.read_text(encoding='utf-8').splitlines()
line_poll=next(i+1 for i,v in enumerate(lines) if 'def poll(' in v)
line_read=next(i+1 for i,v in enumerate(lines) if 'try: event = read(path)' in v)
line_seen=next(i+1 for i,v in enumerate(lines) if 'if number in self.seen: return' in v)
rec=dict(protocol='D279-finite-post-run-semantic-review-v1',subject_plan_sha256=audit['plan_sha256'],
    O0=True,O1=True,O2='NOT_ESTABLISHED',concrete_native_bottleneck='UNKNOWN',
    frozen_gate_preserved=True,thresholds_relaxed=False,automatic_or_manual_O2_upgrade=False,
    follow_on_experiment_authorized=False,additional_scientific_calls=0,
    basis_files={'profile':sha(path),'scientific_snapshot':r['snapshot']['sha256'],'resource_capture':sha(folder/'owned_resources.jsonl')},
    timestamp_review=dict(events=h.shape[1],functions=len(table),capacity_reached=False,
        all_microseconds_multiple_of_1000=bool((h[3]%1000==0).all()),microseconds_gcd=int(np.gcd.reduce(h[3].astype(np.int64))),
        reported_ClockPrecision=float(p['ClockPrecision']),marker_offsets=rows,
        nonintersection_gap_seconds_exact=str(gap),nonintersection_gap_seconds=float(gap),
        interpretation='Observed millisecond history granularity does not support treating marker epoch timestamps as exact to 10 microseconds. '
            'This explains the frozen check rejection algebraically; quantization versus clock-rate/recording differences is not causally separated. '
            'Do not equate ClockPrecision of timing statistics with guaranteed history timestamp accuracy; do not widen bounds after seeing data.'),
    visible_function_totals=top,ordinal_history_gaps=ordinal_gaps,
    protected_source_policy=dict(files_sha256=vendor_hashes,decoded=False,modified=False,
        interpretation='Protected client aggregate and visible callbacks do not expose cuts, probing LP, branch scoring, simplex or numerical-repair substeps.'),
    display=dict(archived_bytes=len(raw),sha256=sha(log),decoding=encoding,text=decoded,
        phase_times_inferred_from_arrival=False,no_cut_or_branch_table='No such table in captured prefix; absence does not prove no internal work'),
    python_observation_cost=dict(worker_pid=worker,resource_record=resource,
        total_observed_cpu_delta_s=resource['user_cpu_delta_s']+resource['system_cpu_delta_s'],
        source_sha256=sha(source),poll_line=line_poll,read_line=line_read,deduplicate_line=line_seen,
        finding='poll rereads all matching immutable event JSON files; capture checks seen event number only after read/parsing',
        interpretation='Nontrivial controller cost, inherited polling path; process I/O counters are not physical disk traffic. '
            'No event-read count or counterfactual CPU/solver slowdown measurement exists. Do not attribute all CPU to this loop, '
            'all incremental overhead to Profiler, or native root-tail stagnation to the controller.'),
    decision='Stop parameter scans and repeated native observation. No targeted search-parameter intervention is justified. '
        'The broader goal remains a different legal complete SAFE native schedule with strictly lower full energy.',
    official_source='https://www.mathworks.com/help/releases/R2023b/matlab/ref/profile.html',
    post_run_review_scope='Read-only analysis of already timely sealed evidence; not additional in-window solver progress or an end-to-end comparison',
    post_run_review_wall_s=time.monotonic()-start)
save(out/'semantic_review.json',rec)
print(json.dumps({k:rec[k] for k in ['O0','O1','O2','timestamp_review','ordinal_history_gaps','python_observation_cost']},ensure_ascii=True))
