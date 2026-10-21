"""Terminal-only stored-record audit; never solve, search, or evaluate heat."""
from fractions import Fraction as F
from pathlib import Path
import sys
REPO=next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').is_file())
sys.path.insert(0,str(REPO/'research/chapter3_experiments/p1_batch'))
import p1_controller as r


def main(name='record_review01.json'):
    terminal=r.read(r.OUT/'process_terminal.json')
    worker=r.read(r.OUT/'worker_terminal.json') if (r.OUT/'worker_terminal.json').exists() else {}
    d=r.admission();ledger=r.read(r.OUT/'ledger.json');prep=d
    checks={};rows=[]
    checks['process_completed']=terminal['state']=='COMPLETED'
    checks['worker_completed_40']=worker.get('state')=='COMPLETED' and worker.get('consumed_new')==40
    checks['ledger_40_total_12000_reserved']=(ledger['state']=='COMPLETED'
        and ledger['consumed_new']==40 and ledger['consumed_total']==40 and ledger['reserved_total_method_s']==12000
        and ledger['active'] is None)
    checks['new_prefix_exact']=[v['slot_id'] for v in ledger['calls']]==[s['slot_id'] for s in r.slots()]
    actual=[s['slot_id'] for s in r.slots() if (r.OUT/'claims'/(s['slot_id']+'.json')).exists()]
    checks['40_exclusive_claims']=actual==[s['slot_id'] for s in r.slots()]
    checks['P1_only_claims']=all(s['problem_id'].startswith('response_R__') for s in r.slots())
    checks['211_frozen_sources']=len(d['source_sha256'])==211 and d['source_sha256']==r.sources()
    checks['P0_critical_unchanged']=all(r.sha(REPO/name)==h for name,h in r.read(r.OUT/'precheck.json')['P0_critical_sha256'].items())
    original_deadline=r.deadline_utc()
    ended=__import__('datetime').datetime.fromisoformat(terminal['ended_utc'])
    checks['original_calendar_not_extended']=ended<=original_deadline
    from schedules import validate_schedule
    for slot,row in zip(r.slots(),ledger['calls']):
        sid=slot['slot_id'];folder=r.OUT/'calls'/slot['problem_id']/slot['id']
        raw=r.read(folder/'wrapper_raw_result.json')
        job=next(j for j in r.p.jobs(slot['problem_id']) if j['id']==slot['id'])
        again=r.p.result_records(job,raw,prep['inputs'][slot['problem_id']],folder,
            input_valid=True,source_valid=True,errors=[])
        method=r.read(r.OUT/'claims'/(sid+'_method_return.json'))
        final=r.read(r.OUT/'claims'/(sid+'_result.json'))
        checks[sid+'/records_reproduced']=again==row['records']==method['records']==final['records']
        checks[sid+'/normal_or_verified_deadline']=again['execution']['execution_status'] in r.p.NORMAL
        checks[sid+'/300_second_root']=(raw.get('timing') or {}).get('limit_s')==300
        checks[sid+'/no_new_or_late_candidate_accepted']=again['execution'].get('new_or_late_candidate_accepted') is False
        if again.get('usable_U_J') is not None:
            raw_cfg,config,instance=r.p.fresh_input(slot['problem_id'])
            checks[sid+'/fresh_exact_input']=r.canonical(instance)==prep['inputs'][slot['problem_id']]['input_sha256']
            checks[sid+'/exact_legality']=validate_schedule(instance,raw['safe_candidate'])['state']=='SCHEDULE_VALID_THERMAL_UNCHECKED'
            post=r.read(folder/'postcheck.json');claim=r.read(folder/'postcheck.claim.json')
            checks[sid+'/post_once_and_provenance']=(len(list(folder.glob('postcheck*.claim.json')))==1
                and claim['provenance']==post['post_provenance']
                and post['post_provenance']['raw_result_sha256']==r.sha(folder/'wrapper_raw_result.json')
                and post['post_provenance']['candidate_sha256']==r.canonical(raw['safe_candidate'])
                and post['post_provenance']['input_sha256']==r.canonical(instance)
                and post['post_provenance']['post_seconds']==60)
            checks[sid+'/post_full_SAFE']=(post.get('state')=='SAFE' and post.get('rankable_energy') is True
                and set(post['scenes'])==set(raw['safe_candidate']['scenes'])
                and all(s.get('complete') is True and F(s['covered_until_s'])==F(instance['window_ms'])/1000
                        for s in post['scenes'].values()))
            receipt=raw['aggregation'] if slot['method']=='linked_fixed_unit_opp_start' else raw['evaluation']
            lo,hi=map(F,receipt['weighted_energy_J']);fresh_lo,fresh_hi=map(F,post['weighted_energy_J'])
            checks[sid+'/energy_overlap']=max(lo,fresh_lo)<=min(hi,fresh_hi)
            checks[sid+'/U_is_original_upper']=F(again['usable_U_J'])==hi
            checks[sid+'/formed_in_budget']=0<=receipt['completed_at_elapsed_s']<300
        manifest=r.read(r.OUT/'claims'/(sid+'_artifact_sha256.json'))
        checks[sid+'/method_artifacts_unchanged']=all(r.sha(folder/name)==h for name,h in manifest.items())
        rows.append({'slot':sid,'status':again['execution']['execution_status'],'U_J':again.get('usable_U_J')})
    result={'protocol':'K158-terminal-pure-record-review-v1','passed':all(checks.values()),
        'count':len(checks),'checks':checks,'rows':rows,'research_calls':0,'new_thermal_evaluations':0,
        'review_origin':'same chat stored-evidence verification; not external independent approval',
        'cohort_scope':'exactly 40 independent P1 response_R calls'}
    r.write_new(r.OUT/name,result)
    print({'passed':result['passed'],'checks':len(checks),'failed':[k for k,v in checks.items() if not v]})
    return result['passed']


if __name__=='__main__':raise SystemExit(0 if main(sys.argv[1] if len(sys.argv)>1 else 'record_review01.json') else 1)
