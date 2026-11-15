"""Read-only exact-interval analysis of the fixed 12 search slots."""
from collections import Counter
from fractions import Fraction as F
import hashlib,json,sys
from pathlib import Path

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def energy(x):return [F(x['lower']),F(x['upper'])] if x else None
def comparison(x,y):
    # x is proposed arm, y reference. Feasibility is never mixed with a percent.
    if not x['eligible'] or not y['eligible']:
        return {'kind':'FEASIBILITY_ONLY','x_eligible':x['eligible'],'reference_eligible':y['eligible']}
    lo,hi=energy(x['final_energy']);rl,rh=energy(y['final_energy'])
    kind='STRICT_LOWER' if hi<rl else 'STRICT_HIGHER' if lo>rh else 'EXACT_SAME_INTERVAL' if [lo,hi]==[rl,rh] else 'OVERLAP_NO_CERTIFIED_ORDER'
    return {'kind':kind,'saving_fraction_interval':[str(1-hi/rl),str(1-lo/rh)],
      'saving_percent_interval':[float(100*(1-hi/rl)),float(100*(1-lo/rh))],
      'same_final_candidate':x['final_candidate_sha256']==y['final_candidate_sha256'],
      'same_initial_candidate':x['initial_candidate_sha256']==y['initial_candidate_sha256'],
      'same_initial_energy':x['initial_energy']==y['initial_energy']}

def main(root):
    sys.path.insert(0,str(root));from support import paths,verify_sources
    paths();from archive import read_result
    from runtime import digest
    from h02_pair_preflight.receipts import safe_receipt
    original_freeze=read(root/'execution/freeze.json');first_batch=read(root/'execution/batch_summary.json')
    freeze=read(root/'continuation/freeze.json');batch=read(root/'continuation/batch_summary.json')
    assert freeze['slots']==original_freeze['slots'][1:]
    assert batch['retry_count']==0
    for field,path in [('prior_freeze_sha256','execution/freeze.json'),
      ('recovered_A_sha256','repair/recovered_A_evidence.json'),
      ('continuation_launcher_sha256','repair/continue_batch.py'),
      ('memory_fix_sha256','repair/memory_signature.patch'),
      ('sources_manifest_sha256','sources.json'),('interface_checks_sha256','tests/interface.json')]:
        assert freeze[field]==sha(root/path),(field,path)
    for name,h in freeze['code_sha256'].items():assert sha(root/name)==h,name
    for name,h in original_freeze['code_sha256'].items():
        p=root/'versions/v1/support.py' if name=='support.py' else root/name
        assert sha(p)==h,name
    assert sha(root/'PROTOCOL.md')==freeze['protocol_sha256']==original_freeze['protocol_sha256']
    sources=verify_sources();slots=[];raws={};calls={};all_shared={};invariants=[]
    returns={r['slot']['id']:r for r in first_batch['returns']+batch['returns']}
    for slot in original_freeze['slots']:
        recovered=slot['id']=='01_U07__n24_A'
        folder=root/('execution' if recovered else 'continuation')/slot['id'];record=dict(slot)
        this_freeze=original_freeze if recovered else freeze
        if not recovered and not (folder/'summary.json').exists():
            record.update(eligible=False,status='NOT_COMPLETED',process=returns.get(slot['id']));slots.append(record);continue
        raw=read_result(folder/'method/result.json');raws[slot['id']]=raw
        if recovered:
            ev=read(root/'repair/recovered_A_evidence.json');assert ev['status']=='RECOVERED_READ_ONLY' and ev['final_SAFE_contract_valid']
            recs=read(root/'repair/recovered_A_numerical_calls.json')
            journal=[json.loads(x) for x in (folder/'journal.jsonl').read_text(encoding='utf-8').splitlines()]
            assessments=[x for x in journal if x['event']=='ASSESSMENT_END']
            cache={k:sum(x['cache_delta'].get(k,0) for x in assessments) for k in assessments[0]['cache_delta']}
            s={'case':slot['case'],'arm':slot['arm'],'normal_stop':True,'terminal':raw['run_terminal'],'reason':raw['reason'],
              'error':None,'worker_error':'POST_STOP_MEMORY_API_ERROR','final_SAFE':True,
              'usable_as_research_evidence':raw['usable_as_research_evidence'],'final_energy':ev['final_energy'],
              'final_candidate_sha256':ev['final_candidate_sha256'],'final_formed_s':ev['final_formed_at_s'],
              'initial_energy':ev['initial_energy'],'initial_candidate_sha256':ev['initial_candidate_sha256'],
              'first_safe_s':raw['first_safe_at_s'],'initialization':{k:v for k,v in raw['initialization'].items() if k in
                ['admission_limit_s','fallback_used','quality_stages_completed','stop_reason','status','returned_at_s','remaining_method_s','local_accepted']},
              'method_charged_s':ev['method_charged_s'],'timing':raw['timing'],'physical_panels':ev['physical_panels'],
              'extremum_calls':ev['extremum_calls'],'refinements':ev['refinements'],'evaluation_attempts':ev['numeric_calls'],
              'returned_states':ev['returned_states'],'full_hash_hits':ev['full_hash_hits'],
              'strict_search_improvements':ev['strict_search_improvements'],'cache_metrics':cache,
              'cache_accept_callback_s':None,'observer_s':None,'cpu_s':None,'memory':None,
              'recovered_post_stop':True,'missing_irrecoverable':ev['missing_irrecoverable']}
            assert float(raw['root_context']['root_deadline'])-float(raw['root_context']['root_start'])==300
        else:
            s=read(folder/'summary.json');recs=read(folder/'numerical_calls.json')
            assert s['frozen_plan_sha256']==sha(root/'continuation/freeze.json')
            assert s['code_identity']=={('controlled_search/'+k):v for k,v in this_freeze['code_sha256'].items() if k.endswith('.py')}
            assert s['root_unchanged'] and s['input_loads']==1 and s['post_physical_evaluations']==0
        calls[slot['id']]=recs
        actual_code={k:v for k,v in raw['sources_sha256'].items() if k.startswith('controlled_search/')}
        assert actual_code=={('controlled_search/'+k):v for k,v in this_freeze['code_sha256'].items() if k.endswith('.py')}
        assert raw['root_context']['root_seconds']==300 and raw['initialization_version']=='I1'
        assert raw['blocking_edge_adjustment_enabled'] and raw['rule_version']=='ON-P-exact-structural-necessary-conditions-v1'
        assert (raw.get('initialization') or {})['admission_limit_s']==180
        config=read(folder/'method/input_config.json');instance=read(folder/'method/input_instance.json')
        assert digest(instance)==freeze['inputs'][slot['case']]['instance'] and digest(config)==freeze['inputs'][slot['case']]['config']
        numerical=[r for r in raw['evaluations'] if not r.get('cache_hit',False)]
        returned=[r for r in recs if r['state']!='INTERRUPTED']
        assert len(numerical)==len(returned)
        assert [r['candidate_sha256'] for r in numerical]==[r['candidate_sha256'] for r in returned]
        seen={};best=None;current=None;commit_checks=0
        for r in raw['evaluations']:
            assert digest(r['candidate'])==r['candidate_sha256']
            if 'evaluation_admitted_at_s' in r:assert r['evaluation_admitted_at_s']<180
            if not r['accepted_safe']:continue
            interval=energy(r['energy']);assert interval[0]<=interval[1]
            assert r['receipt']['completed_at_elapsed_s']<300
            if r['phase']=='initialization':
                accepted=best is None or interval[1]<best[1]
                if accepted:best=interval
            else:
                if current is None:current=energy(raw['initial_safe_snapshot']['energy'])
                accepted=interval[1]<current[0]
                if accepted:current=interval
            assert accepted==r['incumbent_replaced'];commit_checks+=1
            for source in r['receipt'].get('reuse_provenance',[]):
                assert source['source_candidate'] in seen
                assert source['source_complete_at_s']==seen[source['source_candidate']]
                assert 0<=source['source_complete_at_s']<=source['reused_at_s']<300
            seen[r['candidate_sha256']]=r['receipt']['completed_at_elapsed_s']
        if s['final_SAFE']:
            final=safe_receipt(instance,raw['safe_candidate'],raw['evaluation'],config['accuracy_targets'],300)
            assert final==s['final_energy']
            assert digest(raw['safe_candidate'])==s['final_candidate_sha256'] and s['final_candidate_sha256'] in seen
        for r in recs:
            if r['state']!='SAFE':continue
            key=(slot['case'],r['candidate_sha256'])
            old=all_shared.get(key)
            if old:assert old['semantic']==r['semantic_sha256'],'UNEXPLAINED_COMMON_CANDIDATE_DIFFERENCE'
            else:old=all_shared[key]={'semantic':r['semantic_sha256'],'arms':[]}
            old['arms'].append(slot['arm'])
        phase_counts=Counter(r['phase'] for r in numerical if r['accepted_safe'])
        pref=read(folder/'method/prefilter.json')
        initial=energy(s['initial_energy']);final=energy(s['final_energy'])
        extra={
          'eligible':bool(s['normal_stop'] and s['final_SAFE'] and s['usable_as_research_evidence']),
          'status':s['terminal'],'process_wall_s':returns[slot['id']]['process_wall_s'],
          'accepted_numerical_by_phase':dict(phase_counts),'acceptance_checks':commit_checks,
          'initialization_construction_failures':sum(x.get('candidate') is None and x.get('assessment_state')=='NOT_ASSESSED' and x.get('status')!='COMPLETE_LEGAL_CANDIDATE' for x in (raw.get('initialization') or {}).get('construction_attempts',[])),
          'prefilter_counts':pref['counts'],'initial_interval_J':[str(x) for x in initial] if initial else None,
          'final_interval_J':[str(x) for x in final] if final else None,
          'within_arm_search_saving_percent_lower':float(100*(1-final[1]/initial[0])) if initial and final else None,
          'cache_direct_s':sum(s['cache_metrics'].get(k,0) for k in ['identity_s','query_s','save_s','restore_s','prefix_query_s','prefix_save_s','prefix_restore_s'])}
        record.update(s);record.update(extra)
        # Keep detailed timing once, in the immutable raw archive; this derived
        # table links to it instead of duplicating thousands of phase records.
        record['raw_archive']=folder.relative_to(root).as_posix()
        record['timing']={k:v for k,v in s['timing'].items() if k!='phase_records'}
        slots.append(record)
    pairs=[];common=[]
    for case in ['U07__n24','U08__n24','U09__n24','U10__n24']:
        arms={x['arm']:x for x in slots if x['case']==case}
        for x,y in [('B','A'),('C','A'),('C','B')]:pairs.append({'case':case,'arm':x,'reference':y,**comparison(arms[x],arms[y])})
        sets={arm:{r['candidate_sha256'] for r in calls.get(row['id'],[]) if r['state']=='SAFE'} for arm,row in arms.items()}
        common.append({'case':case,'triple_SAFE_candidates':len(sets['A']&sets['B']&sets['C']),
          'at_least_two_arms':sum(k[0]==case and len(set(v['arms']))>=2 for k,v in all_shared.items()),
          'unique_SAFE_union':len(set.union(*sets.values())),
          'unique_to_arm':{a:len(v-set.union(*(w for b,w in sets.items() if b!=a))) for a,v in sets.items()}})
    report={'scope':'Exactly 12 one-shot ON-P calls; descriptive exact-interval comparison, no statistical or hardware-generalization claim.',
      'batch_stop_reason':batch['stop_reason'],'initial_batch_stop_reason':first_batch['stop_reason'],
      'user_authorized_continuation':True,'completed':len(returns),'retry_count':batch['retry_count'],
      'worker_nonzero_exits':sum(r['exit_code']!=0 for r in returns.values()),
      'eligible_SAFE':sum(x['eligible'] for x in slots),'sources_verified':sources,'slots':slots,'pairs':pairs,
      'common_candidate_exact_semantics':common,'unresolved_total':sum(x.get('returned_states',{}).get('UNRESOLVED',0) for x in slots),
      'interrupted_total':sum(x.get('returned_states',{}).get('INTERRUPTED',0) for x in slots),
      'thermal_violation_total':sum(x.get('returned_states',{}).get('THERMAL_VIOLATION',0) for x in slots),
      'quality_counts':{a:dict(Counter(x['kind'] for x in pairs if x['arm']==a and x['reference']=='A')) for a in ['B','C']},
      'prefix_increment_counts':dict(Counter(x['kind'] for x in pairs if x['arm']=='C' and x['reference']=='B')),
      'prefix_at_least_one_percent_cases':[x['case'] for x in pairs if x['arm']=='C' and x['reference']=='B' and x['kind']=='STRICT_LOWER' and F(x['saving_fraction_interval'][0])>=F(1,100)],
      'certification_limits':'Final full contracts checked read-only. No additional uncached physical reevaluation of unique candidates. Common candidates compared exactly; formal semantics of all possible future inputs not proven.'}
    target=root/'results';target.mkdir(exist_ok=True)
    (target/'analysis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['completed','eligible_SAFE','unresolved_total','interrupted_total','quality_counts','batch_stop_reason']},ensure_ascii=False))
if __name__=='__main__':main(Path(sys.argv[1]).resolve())
