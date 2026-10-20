"""Static K142 delivery audit: stored receipts and bytes only, no experiment."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
REPO = next(p for p in HERE.parents if (p/'AGENTS.md').is_file())
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    d, a = read(OUT/'declaration.json'), read(HERE/'execution_authorization.json')
    ledger, facts = read(OUT/'ledger.json'), read(HERE/'analysis01/facts.json')
    terminal, cross = read(HERE/'verification.json'), read(HERE/'analysis_crosscheck.json')
    expected = ['whole_milp', 'linked_n1']
    checks = {
        'source159_unchanged': len(d['source_sha256']) == 159 and all(sha(REPO/n) == h for n,h in d['source_sha256'].items()),
        'frozen_protocol_unchanged': sha(OUT/'protocol.md') == a['protocol_sha256'],
        'frozen_launcher_unchanged': sha(OUT/'launcher.py') == a['launcher_sha256'],
        'frozen_declaration_unchanged': sha(OUT/'declaration.json') == a['declaration_sha256'],
        'K141_context_remains_historical': sha(OUT/'phase_context.json') == a['K141_context_sha256'],
        'terminal_blocked_prefix_only': ledger['state'] == 'BLOCKED' and ledger['consumed'] == 2 and [c['id'] for c in ledger['calls']] == expected,
        'two_claims_no_HEFT_SA': all((OUT/'claims'/(n+'.json')).is_file() for n in expected) and all(not (OUT/'claims'/(n+'.json')).exists() for n in ['heft','sa101']),
        'native_cleanup_confirmed': all(c['cleanup']['observed_tree_verified_terminated'] is True for c in ledger['calls']),
        'two_saved_SAFE_consistent': facts['all_saved_SAFE_consistent'] is True,
        'four_method_comparison_remains_incomplete': facts['all_four_calls_executed_once'] is False and facts['all_four_comparison_valid'] is False,
        'saved_original_archives_unchanged': facts['raw_archives_unchanged'] is True and all(sha(OUT/n) == h for n,h in facts['raw_hashes_after'].items()),
        'terminal_independent_audit_passed': terminal['passed'] is True and terminal['check_count'] == 37,
        'analysis_crosscheck_passed': cross.get('passed') is True,
        'analysis_created_no_new_evidence': facts['new_native_model_decode_heat_calls'] == 0 and facts['historical_candidate_or_U_used'] is False,
        'execution_summary_and_index_present': (HERE/'summary.md').is_file() and (OUT/'execution_index.md').is_file(),
        'project_status_and_evidence_registered': all('K.142' in (REPO/n).read_text(encoding='utf-8') for n in ['RESEARCH_BRIEF.md','research/03_证据与检索记录.md','research/第三章当前进展与正式实验推进计划_审查稿.md','research/chapter3_experiments/README.md'])
    }
    report = {'stage':'K142', 'passed': all(checks.values()), 'check_count': len(checks), 'checks':checks,
        'research_calls_consumed': 2, 'unstarted_methods':['heft','sa101'],
        'four_method_research_completed':False, 'new_physical_or_solver_calls':0,
        'scope':'Static final delivery audit; no changes to frozen preparation, methods or raw results.'}
    (HERE/'delivery_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    return report['passed']

if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
