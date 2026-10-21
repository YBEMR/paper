"""Read-only scientific review of stopped K155 prefix; no new method or heat."""
import csv
from fractions import Fraction as F
import json
from pathlib import Path
import sys
REPO=next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').is_file())
sys.path.insert(0,str(REPO/'research/chapter3_experiments/p0_execution'))
import batch as b


def main():
    out=Path(__file__).resolve().parent
    ledger=b.read(b.OUT/'ledger.json');pending=b.read(b.OUT/'ledger.json.pending')
    launcher=b.read(b.OUT/'launcher_result.json');d=b.admission()
    before=b.read(out/'before_artifact_sha256.json')
    rows=[];checks={}
    checks['supervisor_terminated_nonzero_no_watchdog']=launcher['returncode']==1 and launcher['watchdog_stop'] is None
    checks['three_claims_consumed_nine_hundred_reserved']=ledger['consumed']==3 and ledger['reserved_method_budget_s']==900
    checks['same_original_and_pending_prefix']=pending['calls'][:2]==ledger['calls'][:2] and pending['consumed']==ledger['consumed']
    checks['prefix_is_first_three_frozen_slots']=[r['slot_id'] for r in pending['calls']]==[s['slot_id'] for s in d['slots'][:3]]
    claims=sorted(p.name for p in (b.OUT/'claims').glob('*.json') if not p.name.endswith(('_result.json','_artifact_sha256.json')))
    checks['exactly_three_research_claims']=claims==sorted(s['slot_id']+'.json' for s in d['slots'][:3])
    checks['no_SA_or_R2_R5_method_started']=sorted(p.name for p in (b.OUT/'calls').iterdir())==['base__R1'] and len(list((b.OUT/'calls/base__R1').iterdir()))==3
    checks['all_before_files_unchanged']=all(b.sha(REPO/n)==h for n,h in before.items())
    checks['all_197_sources_unchanged']=b.sources()==d['source_sha256']
    checks['file_error_at_post_method_ledger_replace']=('PermissionError: [WinError 5]' in (b.OUT/'launcher.log').read_text(encoding='utf-8')
        and "save(OUT/'ledger.json',ledger)" in (b.OUT/'launcher.log').read_text(encoding='utf-8'))
    prep=b.read(b.PREP/'declaration.json')
    for index,row in enumerate(pending['calls']):
        slot=d['slots'][index];folder=b.OUT/'calls'/slot['problem_id']/slot['id']
        raw=b.read(folder/'wrapper_raw_result.json')
        job=next(j for j in b.p.jobs(slot['problem_id']) if j['id']==slot['id'])
        saved=b.p.result_records(job,raw,prep['inputs'][slot['problem_id']],folder,
                                input_valid=True,source_valid=True,errors=[])
        checks[slot['id']+'/saved_records_reproduced']=saved==row['records']
        checks[slot['id']+'/raw_equals_core_result']=raw==b.read(folder/'result.json')
        post=b.read(folder/'postcheck.json')
        checks[slot['id']+'/post_SAFE_full']=post.get('state')=='SAFE' and post.get('rankable_energy') is True
        checks[slot['id']+'/single_post_claim']=b.read(folder/'postcheck.claim.json')['provenance']==post['post_provenance']
        receipt=raw['aggregation'] if slot['id']=='anchor_linked4' else raw['evaluation']
        old=tuple(map(F,receipt['weighted_energy_J']));fresh=tuple(map(F,post['weighted_energy_J']))
        checks[slot['id']+'/energy_overlap']=max(old[0],fresh[0])<=min(old[1],fresh[1])
        checks[slot['id']+'/receipt_before_300']=0<=receipt['completed_at_elapsed_s']<300
        m=saved['completion_metrics']
        lower=raw.get('certified_lower_bound_J')
        if lower is None:lower=((raw.get('deployment_bounds') or {}).get('L0') or {}).get('lower_bound_J')
        if (folder/'independent_bounds.json').exists():lower=b.read(folder/'independent_bounds.json')['L0']['lower_bound_J']
        phase_U={phase:next((v['safe_upper_bound_J'] for v in reversed(raw.get('global_updates') or [])
            if v.get('phase_index')==phase),None) for phase in (1,2)}
        phases=[{'phase_index':ph['phase_index'],'started_at_s':ph['started_at_s'],
                 'completed_at_s':ph.get('completed_at_s'),'U_J':phase_U[ph['phase_index']]}
                for ph in raw.get('phases') or []]
        record={'slot_id':slot['slot_id'],'method':slot['id'],'problem_id':slot['problem_id'],
            'method_execution_status':saved['execution']['execution_status'],
            'batch_wrapper_failure':index==2,'safe_U_J':saved['usable_U_J'],
            'energy_interval_J':receipt['weighted_energy_J'],'independent_L0_J':lower,
            'first_complete_SAFE_s':m['first_complete_SAFE_at_s'],
            'first_strict_improvement_s':m['first_strict_improvement_at_s'],
            'root_stop_s':raw['timing']['method_elapsed_s'],
            'inclusive_return_s':row['method_return_inclusive_wall_s'],
            'matlab_startup_s':m['matlab_startup'].get('wall_s'),
            'post_SAFE':post['state']=='SAFE','post_s':post.get('elapsed_s'),
            'phases':phases,'whole_feedback_rows':len(raw.get('feedback') or []),
            'saved_violation_rows':len(raw.get('violations') or []),
            'independently_proven_optimal':saved['execution']['independently_proven_optimal']}
        rows.append(record)
    heft=rows[2];linked=rows[1]
    strict=F(linked['safe_U_J'])<F(heft['energy_interval_J'][0])
    reduction=(F(heft['safe_U_J'])-F(linked['safe_U_J']))/F(heft['safe_U_J'])
    review={'protocol':'K155-stopped-prefix-review-v1','passed':all(checks.values()),'checks':checks,
        'batch_state':'STOPPED_TECHNICAL_ARCHIVE_FAILURE','consumed_calls':3,'unstarted_calls':37,
        'reserved_method_budget_s':900,'actual_root_method_sum_s':sum(r['root_stop_s'] for r in rows),
        'active_supervisor_wall_s':launcher['wall_s'],'rows':rows,
        'HEFT_single_prescribed_post_after_archive_failure':True,
        'linked_strictly_lower_than_HEFT_this_R1':strict,
        'linked_vs_HEFT_reduction_fraction':str(reduction),
        'scope':'stopped first-three prefix, not complete 40-run study or four-method ranking',
        'review_origin':'same chat evidence cross-check, not external approval',
        'old_ledger_and_pending_preserved':True,'new_research_calls_during_review':0}
    b.write_new(out/'review.json',review)
    with (out/'results_prefix.csv').open('x',encoding='utf-8-sig',newline='') as stream:
        columns=[k for k in rows[0] if k not in ('phases','energy_interval_J')]
        w=csv.DictWriter(stream,fieldnames=columns,extrasaction='ignore');w.writeheader();w.writerows(rows)
    print({'review_passed':review['passed'],'checks':len(checks),'calls':3,'unstarted':37,
           'root_seconds':review['actual_root_method_sum_s'],'reduction_pct':float(reduction*100)})
    return review['passed']


if __name__=='__main__':raise SystemExit(0 if main() else 1)
