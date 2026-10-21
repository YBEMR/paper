"""Data-only K154 archive audit. No optimizer, model builder or heat evaluator."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
REPO=ROOT.parents[1]
sys.path.insert(0,str(ROOT/'p0_batch'))
import run_p0 as p


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_text(encoding='utf-8'))


def audit():
    d=load(OUT/'declaration.json');g=load(OUT/'precheck.json')
    checks=[]
    def check(name,value):checks.append({'name':name,'passed':bool(value)})
    rows=d['slots'];counts=Counter(r['problem_id'] for r in rows)
    check('exact_five_problem_coverage',counts=={f'base__R{i}':8 for i in range(1,6)})
    check('forty_unique_slots',len(rows)==len({r['slot_id'] for r in rows})==40)
    check('consecutive_ordinals',[r['ordinal'] for r in rows]==list(range(1,41)))
    check('total_proposed_budget',sum(r['seconds'] for r in rows)==12000)
    for i in range(5):
        block=rows[i*8:(i+1)*8]
        check(f'R{i+1}_one_per_method_five_SA_seeds',Counter(r['method'] for r in block)==
            {'milp':1,'linked_fixed_unit_opp_start':1,'heft':1,'sa':5}
            and [r['seed'] for r in block if r['method']=='sa']==[101,102,103,104,105])
    check('precheck_139_passed',g['passed'] is True and g['tests_run']==139
          and g['errors']==g['failures']==g['skipped']==0)
    check('no_forbidden_calls',not any(g['blocked_calls'].values()) and
          all(g[k]==0 for k in ('research_calls','native_calls','physical_models','thermal_evaluations')))
    check('unmodified_derived_function_lineage',not p.lineage_issues())
    old=load(ROOT/'results/four_method_comparison01/declaration.json')
    check('178_original_source_files_unchanged',len(old['source_sha256'])==178 and
          all(digest(REPO/n)==h for n,h in old['source_sha256'].items()))
    raw=load(ROOT/'results/four_method_comparison01/analysis01/integrity_checks.json')['before_sha256']
    check('340_K152_raw_artifacts_unchanged',len(raw)==340 and all(digest(REPO/n)==h for n,h in raw.items()))
    check('all_frozen_source_snapshots_match',all(digest(OUT/'source_snapshot'/n)==h for n,h in d['source_sha256'].items()))
    check('five_distinct_input_identities',len({v['input_sha256'] for v in d['inputs'].values()})==5)
    check('R1_input_identical_pilot_not_output_reuse',d['inputs']['base__R1']['input_identities']==old['input_identities'])
    check('execution_is_not_authorized',d['authorised_to_execute'] is False and
          load(OUT/'authorization.example.json')['approved'] is False)
    ledger=load(OUT/'ledger.json')
    check('zero_research_claims_or_consumption',ledger['consumed']==0 and ledger['reserved_method_budget_s']==0
          and ledger['calls']==[] and not (OUT/'claims').exists() and not (OUT/'calls').exists())
    check('current_admission_passes',p.admission(OUT)['prepared'] is True)
    value={'protocol':'K154-data-only-preparation-review-v1','passed':all(c['passed'] for c in checks),
           'count':len(checks),'checks':checks,'research_calls':0,'thermal_evaluations':0,
           'review_origin':'same execution chat; stored-data cross-check, not external independent approval',
           'declaration_sha256':digest(OUT/'declaration.json')}
    print(json.dumps(value,ensure_ascii=False,indent=2))
    return value


if __name__=='__main__':
    result=audit()
    target=Path(sys.argv[1]) if len(sys.argv)>1 else OUT/'preparation_review.json'
    with target.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    raise SystemExit(0 if result['passed'] else 1)
