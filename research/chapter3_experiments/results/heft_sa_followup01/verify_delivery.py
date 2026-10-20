"""Static K144 delivery verification; no methods, model or heat imported."""
from pathlib import Path
import hashlib
import json

HERE=Path(__file__).resolve().parent
REPO=next(p for p in HERE.parents if (p/'AGENTS.md').is_file())
CODE=REPO/'research/chapter3_experiments'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def canonical(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def main():
    d=read(HERE/'declaration.json');g=read(HERE/'precheck.json');ledger=read(HERE/'ledger.json')
    old=CODE/'results/fair_comparison_preparation01';base=read(old/'declaration.json')
    prior=read(CODE/'results/budget_end_review01/audit.json')
    first=read(CODE/'results/heuristic_followup_precheck01/checks.json')
    final=CODE/'results/heuristic_followup_precheck02';replay=read(final/'saved_K142_replay.json')
    review=read(HERE/'verification.json');context=read(HERE/'phase_context.json')
    current={n:sha(REPO/n) for n in d['source_sha256']}
    checks={
        'source165_matches_current_and_snapshot':len(current)==165 and current==d['source_sha256'] and all(sha(HERE/'source_snapshot'/n)==h for n,h in current.items()),
        'original159_unchanged':len(base['source_sha256'])==159 and all(current.get(n)==h for n,h in base['source_sha256'].items()),
        'exact_six_additions':len(set(current)-set(base['source_sha256']))==6,
        'precheck02_63_pass_current_source':g['passed'] is True and g['tests_run']==63 and g['source_sha256']==current and g['errors']==g['failures']==g['skipped']==0,
        'precheck02_original_copy_matches':sha(HERE/'precheck.json')==sha(final/'checks.json')==d['precheck_sha256'],
        'no_guarded_calls_attempted':bool(g['blocked_calls']) and not any(g['blocked_calls'].values()),
        'precheck01_retained_but_stale':first['passed'] is True and first['tests_run']==61 and first['source_sha256']!=current,
        'saved_replay10_pass_no_research':replay['passed'] is True and len(replay['checks'])==10 and all(replay['checks'].values()) and replay['research_calls']==replay['native_calls']==replay['thermal_evaluations']==replay['candidate_decodes']==0,
        'independent_review18_pass':review.get('passed') is True and (review.get('check_count')==18 or review.get('checks_count')==18),
        'old301_artifacts_unchanged':len(prior['raw_artifact_sha256'])==301 and all(sha(old/n)==h for n,h in prior['raw_artifact_sha256'].items()),
        'K142_remains_two_blocked_calls':read(old/'ledger.json')['state']=='BLOCKED' and read(old/'ledger.json')['consumed']==2,
        'new_ledger_unconsumed':ledger['state']=='DECLARED' and ledger['consumed']==0 and ledger['calls']==[],
        'new_claims_empty_global_absent':not list((HERE/'claims').iterdir()) and not (CODE/'results/heuristic_followup_claim01.json').exists(),
        'two_methods300_SA101':d['jobs']==[{'id':'heft','method':'heft','seed':None},{'id':'sa101','method':'sa','seed':101}] and d['per_method_budget_s']==300,
        'inputs_match_old_original':d['input_identities']==base['input_identities'] and all(sha(HERE/n)==h for n,h in d['input_file_sha256'].items()),
        'canonical_input_identities_match':all(canonical(read(HERE/n))==d[k] for n,k in [('input_raw.json','raw_config_sha256'),('input_config.json','config_sha256'),('input_instance.json','input_sha256')]),
        'zero_new_research_physics':all(context[k]==0 for k in ['research_calls','native_calls','thermal_evaluations','original_scale_models']),
        'new_execution_authorization_still_required':d['new_execution_authorization_required'] is True,
        'project_records_synced':all('K.144' in (REPO/n).read_text(encoding='utf-8') for n in ['RESEARCH_BRIEF.md','research/03_证据与检索记录.md','research/第三章当前进展与正式实验推进计划_审查稿.md','research/chapter3_experiments/README.md'])}
    report={'stage':'K144','passed':all(checks.values()),'check_count':len(checks),'checks':checks,
        'research_calls':0,'preparation_only':True,'next_methods':['heft','sa101'],
        'scope':'static final delivery check; no optimization, model building, candidate decoding or thermal evaluation'}
    (HERE/'delivery_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    return report['passed']
if __name__=='__main__':raise SystemExit(0 if main() else 1)
