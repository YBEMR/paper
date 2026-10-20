"""K135 read-only terminal audit; no solver, model or thermal propagation."""
from pathlib import Path
from fractions import Fraction
import hashlib
import json

ROOT = Path(__file__).resolve().parent
REPO = next(p for p in ROOT.parents if (p/'AGENTS.md').is_file())
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    target = ROOT/'delivery_verification.json'
    if target.exists():
        raise FileExistsError('Do not overwrite terminal verification.')
    d, l = read(ROOT/'declaration.json'), read(ROOT/'ledger.json')
    a = read(ROOT/'analysis02/facts.json')
    old_a = read(ROOT/'analysis01/facts.json')
    independent = read(ROOT/'independent_final_audit.json')
    context = read(ROOT/'phase_context.json')
    source_errors = [n for n,h in d['source_sha256'].items() if sha(REPO/n)!=h]
    snapshot_errors = [n for n,h in d['source_sha256'].items() if sha(ROOT/'source_snapshot'/n)!=h]
    raw_errors = [n for n,h in a['raw_hashes_before'].items() if sha(ROOT/n)!=h]
    previous = read(ROOT.parent/'augmented_method_precheck01/declaration.json')['historical_artifact_sha256']
    history_errors = [n for n,h in previous.items() if sha(REPO/n)!=h]
    comparison = a['comparison']
    calls = independent['calls']
    c = {x['id']:x for x in calls}
    checks = {
        '144_current_sources_and_snapshots_match': len(d['source_sha256'])==144 and not source_errors and not snapshot_errors,
        '134_historical_artifacts_unchanged': len(previous)==134 and not history_errors,
        'all_analysis02_raw_records_unchanged': not raw_errors,
        'two_calls_consumed_once_and_completed': l['consumed']==2 and l['state']=='COMPLETED' and len(l['calls'])==2 and all(x['state']=='COMPLETED' for x in l['calls']),
        'wrapper19_and_method60_frozen_gates_match': sha(ROOT/'wrapper_checks.json')==d['wrapper_checks_sha256'] and sha(ROOT/'method_checks.json')==d['method_checks_sha256'] and read(ROOT/'wrapper_checks.json')['tests_run']==19 and read(ROOT/'method_checks.json')['count']==60,
        'protocol_and_launcher_frozen': sha(ROOT/'protocol.md')==context['protocol_sha256'] and sha(ROOT/'launcher.py')==context['launcher_sha256'],
        'external_launcher_exited_zero': read(ROOT/'launcher_timing.json')['returncode']==0,
        'same_fresh_seed_and_initial_energy': comparison['identical_fresh_seed_candidate_and_energy'],
        'both_complete_SAFE_audits_pass': all(x['complete_SAFE_receipt_verified'] and x['all_saved_SAFE_receipts_verified'] for x in calls),
        'old_three_new_one_complete_SAFE': c['old_n1']['distinct_full_SAFE_candidates']==3 and c['augmented_all_opp_start']['distinct_full_SAFE_candidates']==1,
        'all_workers_owned_identities_exited': all(x['all_owned_observed_identities_exited'] for x in calls),
        'four_native_calls_all_recorded': len(a['native_call_times'])==4,
        'time_settings_and_actual_duration_separate': all(x['actual_intlinprog_call_s']>x['MaxTime_used_s'] and x['stop_delay_over_MaxTime_s']>0 for x in a['native_call_times']),
        'no_global_optimality_or_infeasibility_claim': all(not x['global_optimality_proved'] and not x['global_infeasibility_proved'] for x in calls),
        'new_not_better_than_old_retained': comparison['strict_new_improvement_over_old_observed'] is False and comparison['strict_old_improvement_over_new_observed'] is True,
        'analysis_correction_preserves_energy_comparison': comparison==old_a['comparison'] and a['supersedes_analysis01']['reason']=='callback_count_schema_correction',
        'no_posthoc_search_or_physical_work': comparison['posthoc_physical_work_or_search'] is False,
        'old_schedule_in_new_declared_subdomain': comparison['old_SAFE_candidate_inside_new_fixed_unit_domain_static'],
    }
    receipt = {'stage':'K135_delivery_verification', 'passed':all(checks.values()),
        'checks':checks, 'mismatches':{'source':source_errors,'snapshot':snapshot_errors,
                                      'raw':raw_errors,'history':history_errors},
        'scope':'stored records only; no new timely evidence, thermal evaluation or optimization',
        'research_calls_consumed':2, 'extra_research_calls':0,
        'primary_energy_success':False, 'technical_pair_completed':True,
        'native_MaxTime_is_hard_time_certificate':False,
        'frozen_declaration_sha256':sha(ROOT/'declaration.json'),
        'independent_audit_sha256':sha(ROOT/'independent_final_audit.json'),
        'analysis02_facts_sha256':sha(ROOT/'analysis02/facts.json'),
        'script_sha256':sha(Path(__file__))}
    target.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':receipt['passed'],'checks':len(checks),'errors':receipt['mismatches']},ensure_ascii=False))
    if not receipt['passed']:raise SystemExit(1)

if __name__=='__main__':
    main()
