"""Final stored-evidence checks for K146; no research code is imported."""
from pathlib import Path
from fractions import Fraction as Q
import ast
import csv
import hashlib
import json

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]
CODE=ROOT/'research/chapter3_experiments'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    facts=read(OUT/'facts.json');review=read(OUT/'verification.json');context=read(OUT/'phase_context.json')
    old=CODE/'results/fair_comparison_preparation01';new=CODE/'results/heft_sa_followup01'
    manifest=read(CODE/'results/budget_end_review01/audit.json')['raw_artifact_sha256']
    source=read(new/'declaration.json')['source_sha256'];last=read(new/'k145_delivery_verification.json')
    with (OUT/'HEFT_domain_membership.csv').open(encoding='utf-8-sig',newline='') as stream:domain=list(csv.DictReader(stream))
    with (OUT/'phase_timing.csv').open(encoding='utf-8-sig',newline='') as stream:phases=list(csv.DictReader(stream))
    tree=ast.parse((OUT/'compare_saved.py').read_text(encoding='utf-8'))
    imports={n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}
    imports|={v.name.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.Import) for v in n.names}
    text=(OUT/'summary.md').read_text(encoding='utf-8')
    checks={
        '165_frozen_sources_unchanged':len(source)==165 and all(sha(ROOT/n)==h for n,h in source.items()),
        'K142_301_raw_artifacts_unchanged':len(manifest)==301 and all(sha(old/n)==h for n,h in manifest.items()),
        'K145_raw_result_hashes_unchanged':all(sha(new/n/'result.json')==h for n,h in last['stored_result_sha256'].items()),
        'all_explicit_input_source_hashes_match':all(sha(ROOT/n)==h for n,h in facts['input_sources'].items()),
        'historical_full_open_results_unchanged':all(sha(ROOT/r['source'])==r['sha256'] for r in facts['historical_full_open']),
        'three_input_files_byte_equal':all(sha(old/n)==h==sha(new/n) for n,h in facts['input_file_sha256'].items()),
        'zero_new_research_model_heat':all(context[k]==0 and facts.get(k,0)==0 for k in ['research_calls','solver_calls','thermal_evaluations','model_builds']),
        'only_stdlib_analysis_imports':imports=={'pathlib','fractions','collections','csv','hashlib','json'},
        'separate_original_call_ledgers_preserved':read(old/'ledger.json')['consumed']==2 and read(old/'ledger.json')['state']=='BLOCKED' and read(new/'ledger.json')['consumed']==2 and read(new/'ledger.json')['state']=='COMPLETED',
        'exact_energy_delta_positive':Q(facts['delta_interval_J'][0])>0 and Q(facts['delta_interval_J'][0])<=Q(facts['delta_interval_J'][1]),
        'HEFT_not_in_either_actual_local_domain':not facts['domain_membership']['HEFT_full_plan_in_phase1'] and not facts['domain_membership']['HEFT_full_plan_in_phase2'],
        'both_phase_membership_rows_present':len(domain)==24 and {r['phase'] for r in domain}=={'1','2'},
        'missing_phase_counts_not_filled_with_zero':all(r['original_evaluation_row_count']=='' and r['original_evaluation_row_count_status']=='NOT_RECORDED_IN_PHASE' for r in phases),
        'saved_log_legality_and_safe_counts':facts['linked_decode_states']=={'LEGAL':10} and facts['linked_evaluation_states']=={'SAFE':6},
        'same_seed_fixed_device_lower_example_retained':facts['historical_K140']['same_seed_units_and_choices'] and facts['historical_K140']['phase2_full_updates']==3 and facts['historical_K140']['U_J']<facts['linked_U_J'],
        'old_all_open_trials_retained':{r['stage'] for r in facts['historical_full_open']}=={'K135','K138'} and all(r['phase2_updates']==0 for r in facts['historical_full_open']),
        'independent_review_passed':review['passed'] and (OUT/'independent_review.md').is_file(),
        'recommendation_not_implemented_or_guaranteed':'本轮没有实现该调整' in text and '不预设取得' in text,
        'not_claiming_complete_causal_explanation_or_same_round_rank':'存档确认了两项限制' in text and '不拼成同轮算法排名' in text and '不是分别改变' in text,
        'four_project_records_synchronized':all('K.146' in (ROOT/n).read_text(encoding='utf-8') for n in ['RESEARCH_BRIEF.md','research/03_证据与检索记录.md','research/第三章当前进展与正式实验推进计划_审查稿.md','research/chapter3_experiments/README.md']),
    }
    result=dict(stage='K146',passed=all(checks.values()),check_count=len(checks),checks=checks,
                research_calls=0,model_builds=0,thermal_evaluations=0,production_source_changes=0,
                scope='saved-artifact verification only; not an experiment or performance gain proof')
    (OUT/'delivery_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    return result['passed']

if __name__=='__main__':raise SystemExit(0 if main() else 1)
