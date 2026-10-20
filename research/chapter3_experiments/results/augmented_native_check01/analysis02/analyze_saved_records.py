"""K133 terminal archive audit only. No heat, model generation or solver."""
from pathlib import Path
import hashlib, importlib.util, json, sys
import numpy as np
from scipy.io import loadmat

REPO=next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').is_file() and (p/'RESEARCH_BRIEF.md').is_file())
HERE=REPO/'research/chapter3_experiments';sys.path.insert(0,str(HERE))
from augmented_payload import validate_projected_vector
import matlab_bridge
ROOT=HERE/'results/augmented_native_check01'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    d=read(ROOT/'declaration.json');ledger=read(ROOT/'ledger.json')
    assert ledger['state'] in ('COMPLETED','STOPPED_UNRESOLVED') and ledger['consumed']==1
    r=read(ROOT/'result.json');wrapper=read(ROOT/'launcher_timing.json')
    native=r.get('native_result') or {};meta=read(ROOT/'mapping.json')
    source_ok=all(sha(REPO/n)==h for n,h in d['source_sha256'].items())
    assert source_ok
    original=loadmat(HERE/'results/fixed_unit_pair02/all_opp_start/matlab/request_000001.mat')
    raw=loadmat(ROOT/'matlab/request_000001.mat')
    def payload(mat):
        p={k:mat[k] for k in ('c','A','b','Aeq','beq','lb','ub')}
        p['intcon']=mat['intcon'].reshape(-1).astype(np.int64)-1
        return p
    op,ap=payload(original),payload(raw)
    observed=[]
    for event in r.get('callback_events',[]):
        if 'vector_check' not in event:continue
        stored=event['vector_check'];path=ROOT/'matlab'/event['file'];data=read(path)
        prefix,check=validate_projected_vector(data['x'],op,ap,meta)
        assert sha(path)==event['file_sha256']
        assert check==stored['report'],event['file']
        observed.append({'source':event['file'],'formed_at_s':stored.get('completed_s'),
            'stored_timely_acceptance':stored['accepted'],'array_report_matches':True,
            'original_inequality':(check.get('original') or {}).get('inequality_violation'),
            'original_equality':(check.get('original') or {}).get('equality_violation'),
            'link':check.get('link_max_abs_residual')})
    final_check=None
    if native.get('x'):
        _,final_check=validate_projected_vector(native['x'],op,ap,meta)
        stored=(r.get('admission') or {}).get('final_check')
        assert stored and final_check==stored['report']
    x0_equal=np.array_equal(raw['x0'].reshape(-1)[:len(original['x0'].reshape(-1))],original['x0'].reshape(-1))
    assert x0_equal
    native_file=ROOT/'matlab/request_000001.native.mat'
    native_initial_equal=None
    if native_file.exists():
        nm=loadmat(native_file)
        native_initial_equal=np.array_equal(nm['initialPoint'].reshape(-1),raw['x0'].reshape(-1))
    initial_report=read(ROOT/'initial_check.json')
    checks={'source_139_match':source_ok and len(d['source_sha256'])==139,
        'one_request':ledger['native_requests_published']==1 and r['requests_attempted']==1,
        'one_startup':r['worker_startups']==1,
        'original_prefix_of_x0_unchanged':x0_equal,
        'native_received_same_initial_point':native_initial_equal is True,
        'within_actual_process_180_s':wrapper['within_total_limit'] and wrapper['complete_python_process_wall_s']<=180,
        'no_thermal_or_quality_claim':r['thermal_evaluations']==0 and r['new_SAFE_upper_bound'] is None and not r['quality_claim'],
        'cleanup_confirmed':bool(r.get('cleanup') and matlab_bridge.cleanup_is_complete(r['cleanup'])),
        'all_saved_numeric_reports_reproduced':True}
    complete=bool(ledger.get('technical_acceptance') and r['technical_acceptance'] and all(checks.values())
        and (r.get('admission') or {}).get('accepted') and final_check and final_check['accepted'])
    facts={'stage':'K133','scope':'saved-array replay only; not retroactive timely acceptance or thermal safety',
        'technical_admission_pass':complete,'checks':checks,'native_status':native.get('status'),
        'native_exitflag':native.get('exitflag'),'native_output':native.get('output'),
        'native_initial_point':native.get('initial_point'),'native_phase_seconds':native.get('phase_seconds'),
        'total_python_process_wall_s':wrapper['complete_python_process_wall_s'],
        'work_stopped_at_s':r['work_stopped_at_s'],'cleanup_completed_at_s':r['cleanup_completed_at_s'],
        'cleanup_status':(r.get('cleanup') or {}).get('cleanup_status'),
        'admission':r.get('admission'),'observed_vector_checks':observed,'final_array_check':final_check,
        'initial_array_check':initial_report,'requests':1,'new_quality_outputs':0,
        'independent_optimality':False,'independent_infeasibility':False,
        'original_SAFE_evidence_unchanged':True,
        'raw_sha256':{str(p.relative_to(ROOT)):sha(p) for p in ROOT.rglob('*') if p.is_file()
            and 'source_snapshot' not in p.parts and 'analysis01' not in p.parts and p.suffix in ('.json','.mat','.log')},
        'replay_script_sha256':sha(Path(__file__))}
    native_wall=(native.get('phase_seconds') or {}).get('intlinprog_call')
    facts['native_timing_audit']={'native_MaxTime_setting_s':(native.get('options') or {}).get('MaxTime'),
        'actual_intlinprog_call_s':native_wall,
        'actual_call_within_60_s':native_wall is not None and native_wall<=60,
        'stop_delay_over_declared_60_s':None if native_wall is None else max(0.,native_wall-60),
        'strict_all_actual_time_limits_met':native_wall is not None and native_wall<=60 and wrapper['within_total_limit'],
        'final_not_credited_as_strict_native_60_s_output':True,
        'note':'numeric admission and total 180s compliance do not imply native call returned within 60s'}
    callback_within=[]
    for event in r.get('callback_events',[]):
        if 'vector_check' not in event:continue
        raw_event=read(ROOT/'matlab'/event['file'])
        callback_within.append({'event':event['number'],
            'native_self_reported_time_s':(raw_event.get('values') or {}).get('time'),
            'request_wall_s':raw_event.get('request_wall_seconds'),
            'python_check_completed_s':event['vector_check'].get('completed_s'),
            'clock_scope':'separate clocks preserved; native time is solver reported'})
    facts['nonempty_callback_times']=callback_within
    out=ROOT/'analysis02';out.mkdir(exist_ok=False)
    (out/'facts.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2,allow_nan=False,default=str)+'\n',encoding='utf-8')
    (out/'analyze_saved_records.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({'technical_admission_pass':complete,'native_exitflag':native.get('exitflag'),
        'actual_process_wall_s':wrapper['complete_python_process_wall_s'],'checks':checks,
        'callback_vectors':len(observed),'final_array_check':final_check},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
