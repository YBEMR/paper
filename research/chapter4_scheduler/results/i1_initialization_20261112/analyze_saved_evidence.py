"""Read saved I1 first-wave evidence only; no scientific imports or calls."""
from collections import Counter
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import statistics
import subprocess

ROOT=next(p for ancestor in Path(__file__).resolve().parents for p in (ancestor,ancestor/'paper')
          if (p/'research/chapter4_scheduler/i1').is_dir())
OUT=ROOT/'research/chapter4_scheduler/results/i1_initialization_20261112'
P3=OUT.parent/'p3_unseen_ablation_20261112'
OLD=OUT.parent/'unseen_scaling_20261112/execution'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
digest=lambda v:hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
save=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    plan,summary,batch=[read(OUT/n) for n in ('plan.json','summary.json','batch_return.json')]
    checks={}
    def check(name,condition):
        checks[name]=bool(condition)
    check('five_fixed_slots',[s['id'] for s in plan['slots']]==[
        '01_U02__n12_I1','02_U01__n12_I0','03_U01__n12_I1','04_U01__n6_I1','05_U02__n6_I1'])
    check('all_planned_returned_no_retries',batch['all_planned_method_slots_returned'] and not batch['stop_reason'] and batch['retry_count']==0)
    check('source_snapshot_and_live_identity',all(sha(ROOT/p)==h and sha(OUT/'source_snapshot'/p)==h for p,h in plan['source_sha256'].items()))
    check('inputs_frozen',all(sha(OUT/p)==h for p,h in plan['input_file_sha256'].items()))
    check('no_reference_input_files',len(plan['input_file_sha256'])==8 and all(p.endswith(('/instance.json','/config.json')) for p in plan['input_file_sha256']))
    audit_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    check('frozen_subject_ancestor_of_audit_head',subprocess.run(['git','merge-base','--is-ancestor',plan['subject_commit'],audit_head],cwd=ROOT).returncode==0)
    original=read(OLD/'plan.json')
    unchanged=[p for p,h in original['source_sha256'].items() if sha(ROOT/p)==h]
    check('exactly_499_original_sources_byte_identical',len(unchanged)==499)
    check('I0_and_thermal_unchanged',all(any(p.endswith('/'+n) for p in unchanged) for n in ('heft_method.py','thermal.py','timing.py')))
    details=[]
    raws={}
    for row in summary['rows']:
        key=row['id'];folder=OUT/'calls'/key
        if not (folder/'method/result.json').exists():
            details.append({'id':key,'not_returned':True});continue
        raw=read(folder/'method/result.json');raws[key]=raw
        ret=read(folder/'method_return.json');post=read(folder/'post_return.json') if (folder/'post_return.json').exists() else {}
        meta=raw.get('initialization') or {}
        physical=[e for e in raw.get('evaluations',[]) if not e.get('cache_hit')]
        journal=ret['evaluation_attempts_journal']
        calls=[a for a in journal if a['state']=='RETURNED']
        times=[a['returned_at_s']-a['started_at_s'] for a in journal if 'returned_at_s' in a]
        first=next((e for e in physical if e.get('accepted_safe')),None)
        check(key+':accounting',len(physical)==len(calls) and [e['candidate_sha256'] for e in physical]==[e['candidate_sha256'] for e in calls])
        check(key+':no_graph_search',not raw.get('graph_proposals') and not raw.get('reconstruction_attempts') and all(e['phase']=='initialization' for e in physical))
        check(key+':root300',raw['timing']['limit_s']==300)
        check(key+':timely_SAFE',all(e['receipt']['completed_at_elapsed_s']<=300 for e in physical if e.get('accepted_safe')))
        check(key+':normal_SAFE_post',ret.get('normal_stop') and ret.get('has_SAFE_archive') and post.get('passed') and post['timing']['limit_s']==60)
        if row['arm']=='I1':
            check(key+':I1_status',meta.get('status')=='SAFE_INIT_READY' and raw['initialization_version']=='I1')
            check(key+':construction_admission',all(e['admitted_at_s']<180 for e in meta.get('construction_attempts',[])+meta.get('local_attempts',[])))
            check(key+':physical_admission',all(e.get('evaluation_admitted_at_s',180)<180 for e in physical))
            check(key+':no_delays',all(e['kind']!='one-start-delay' for e in meta.get('local_attempts',[])))
            check(key+':at_most_one_initial_fallback',sum(e.get('priority_policy')=='deadline_scarcity' for e in meta.get('construction_attempts',[]))<=1)
            check(key+':active_priority_retained',all(e['priority_policy']==meta['active_priority'] for e in meta.get('local_attempts',[])))
        stages=[]
        for kind in ('shared-unit','execution-opp','one-start-delay'):
            attempts=[e for e in meta.get('local_attempts',[]) if e['kind']==kind]
            evaluations=[e for e in physical if e['source'].endswith('energy-pass:'+kind)]
            eval_ids={e['candidate_sha256'] for e in evaluations}
            costs=[a['returned_at_s']-a['started_at_s'] for a in calls if a['candidate_sha256'] in eval_ids]
            stages.append({'kind':kind,'constructed':len(attempts),
                'construction_states':dict(Counter(e['construction_status'] for e in attempts)),
                'structure_rejected':sum(e['construction_status']!='COMPLETE_LEGAL_CANDIDATE' for e in attempts),
                'assessment_states':dict(Counter(e.get('assessment_state','NOT_ASSESSED') for e in attempts)),
                'physical_evaluations':len(evaluations),'accepted':sum(e['accepted'] for e in attempts),
                'evaluation_wall_s':sum(costs)})
        cross=[{'source':e['source'],'admitted_at_s':e.get('evaluation_admitted_at_s'),
                'completed_at_s':e['receipt'].get('completed_at_elapsed_s'),'returned_at_s':e['returned_at_s'],
                'incumbent_replaced':e['incumbent_replaced'],'energy_J':e['receipt'].get('weighted_energy_J')}
               for e in physical if row['arm']=='I1' and e['returned_at_s']>=180]
        details.append({'id':key,'first_SAFE_energy_J':first['receipt']['weighted_energy_J'] if first else None,
            'first_SAFE_candidate_sha256':first['candidate_sha256'] if first else None,
            'initial_constructions':meta.get('construction_attempts',[]),'quality_stages':stages,
            'quality_stages_completed':meta.get('quality_stages_completed'),'admission_stop':meta.get('admission_stop'),
            'crossing_admission_evaluations':cross,
            'complete_evaluation_wall_s':sum(times),'mean_evaluation_wall_s':statistics.mean(times) if times else None,
            'median_evaluation_wall_s':statistics.median(times) if times else None,'max_evaluation_wall_s':max(times) if times else None,
            'evaluation_share_of_initialization_percent':100*sum(times)/row['initialization_s'] if row['initialization_s'] else None,
            'post_wall_s':post.get('worker_body_wall_s'),'physical_receipt_states':dict(Counter(e['receipt']['state'] for e in physical)),
            'original_input_identity':plan['input_identities'][row['case_id']]})
    comparisons=[]
    old_fail=read(OLD/'calls/07_U02__n12_HEFT/method/result.json')['initialization']['construction_attempts']
    new_attempts=raws.get('01_U02__n12_I1',{}).get('initialization',{}).get('construction_attempts',[])
    check('U02_original_four_failures_reproduced',len(new_attempts)>=4 and
          all({k:new.get(k) for k in old}==old for old,new in zip(old_fail,new_attempts[:4])) and len(old_fail)==4)
    for row in summary['rows']:
        if row['arm']!='I1' or row['case_id']=='U02__n12':continue
        raw=raws[row['id']]
        if row['case_id']=='U01__n12':
            base=raws['02_U01__n12_I0'];source='same_batch_I0'
        else:
            base=read(next((P3/'calls').glob('*'+row['case_id']+'_ON/method/result.json')));source='historical_P3_I0_initialization'
        b=[e for e in base['evaluations'] if e['phase']=='initialization' and not e.get('cache_hit')]
        pre=[e for e in b if not e['source'].endswith('one-start-delay')]
        new=[e for e in raw['evaluations'] if not e.get('cache_hit')]
        old_energy=base['initial_safe_snapshot']['receipt']['weighted_energy_J']
        energy=raw['evaluation']['weighted_energy_J']
        comparisons.append({'case_id':row['case_id'],'baseline':source,'baseline_energy_J':old_energy,'I1_energy_J':energy,
            'energy_increase_percent':float((F(energy[1])-F(old_energy[1]))/F(old_energy[1])*100),
            'same_initial_candidate':b[0]['candidate_sha256']==new[0]['candidate_sha256'],
            'pre_delay_path_same_prefix':[(e['candidate_sha256'],e['receipt']['weighted_energy_J']) for e in new]==[(e['candidate_sha256'],e['receipt']['weighted_energy_J']) for e in pre[:len(new)]],
            'I0_pre_delay_evaluations':len(pre),'I0_delay_evaluations':len(b)-len(pre),'I1_evaluations':len(new),
            'same_full_pre_delay_path':len(new)==len(pre) and [e['candidate_sha256'] for e in new]==[e['candidate_sha256'] for e in pre]})
    result={'checks':checks,'passed':all(checks.values()),'check_count':len(checks),'details':details,'comparisons':comparisons,
        'audit_head':audit_head,'subject_match_at_audit':audit_head==plan['subject_commit'],
        'scope':'Read-only audit, no construction/replay/electrothermal evaluation; no independence claim for same thermal post.'}
    save(OUT/'analysis.json',result)
    print(json.dumps({'passed':result['passed'],'failed':[k for k,v in checks.items() if not v],'comparisons':comparisons},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
