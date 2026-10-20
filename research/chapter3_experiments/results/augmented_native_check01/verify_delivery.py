"""Read-only evidence checks; no model build, solver, or thermal evaluation."""
from pathlib import Path
import ast
import hashlib
import json

REPO = next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').is_file())
ROOT = Path(__file__).resolve().parent
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    out = ROOT/'delivery_verification.json'
    if out.exists():
        raise FileExistsError('Preserve the existing receipt; do not overwrite.')
    d = read(ROOT/'declaration.json')
    old = read(ROOT.parent/'numerical_conflict_audit01/declaration.json')
    f = read(ROOT/'analysis02/facts.json')
    r = read(ROOT/'result.json')
    ledger = read(ROOT/'ledger.json')
    snap = ROOT/'source_snapshot'
    snapshots = [p for p in snap.rglob('*') if p.is_file()]
    source_mismatches = [n for n,h in d['source_sha256'].items() if sha(REPO/n)!=h]
    old_mismatches = [n for n,h in old['K131_artifact_sha256'].items() if sha(REPO/n)!=h]
    raw_mismatches = [n for n,h in f['raw_sha256'].items() if sha(ROOT/n)!=h]
    prechecks = [read(REPO/n) for n in d['prechecks']]
    for p in snapshots:
        ast.parse(p.read_text(encoding='utf-8-sig'), filename=str(p))
    checks = {
        '139_frozen_sources_match': len(d['source_sha256'])==139 and not source_mismatches,
        '4_byte_identical_snapshots': len(snapshots)==4 and all(sha(p)==sha(REPO/p.relative_to(snap)) for p in snapshots),
        '96_original_K131_artifacts_match': len(old['K131_artifact_sha256'])==96 and not old_mismatches,
        'raw_records_in_analysis02_unchanged': not raw_mismatches,
        'frozen_prechecks_match': all(sha(REPO/n)==h for n,h in d['prechecks'].items()),
        '34_and_19_prechecks_passed': [p['check_count'] for p in prechecks]==[34,19] and all(p['passed'] for p in prechecks),
        'one_worker_one_native_request': r['worker_startups']==1 and r['requests_attempted']==1 and ledger['consumed']==1 and ledger['native_requests_published']==1,
        'callback_and_final_reports_reproduced': f['checks']['all_saved_numeric_reports_reproduced'] and f['final_array_check']['accepted'],
        'total_process_within_180_s': f['total_python_process_wall_s']<=180,
        'native_overrun_explicitly_retained': f['native_timing_audit']['actual_call_within_60_s'] is False and f['native_timing_audit']['strict_all_actual_time_limits_met'] is False,
        'cleanup_complete': f['checks']['cleanup_confirmed'],
        'no_new_thermal_or_quality_evidence': r['thermal_evaluations']==0 and r['new_SAFE_upper_bound'] is None and not r['quality_claim'],
        'analysis_script_identity': sha(ROOT/'analysis02/analyze_saved_records.py')==f['replay_script_sha256'],
        'terminal_summary_and_independent_review_present': (ROOT/'summary.md').is_file() and (ROOT/'independent_review.md').is_file(),
    }
    receipt = {
        'stage': 'K133_delivery_archive_verification',
        'scope': 'stored records and SHA only; no additional native/thermal/research call',
        'record_checks_passed': all(checks.values()),
        'checks': checks,
        'mismatches': {'source': source_mismatches, 'old_K131': old_mismatches, 'raw': raw_mismatches},
        'numeric_admission_pass': f['technical_admission_pass'],
        'total_180_s_compliant': f['total_python_process_wall_s']<=180,
        'actual_native_60_s_compliant': False,
        'native_stop_delay_s': f['native_timing_audit']['stop_delay_over_declared_60_s'],
        'all_original_actual_time_limits_met': False,
        'raw_technical_PASS_is_quality_gate': False,
        'quality_or_new_SAFE_claim': False,
        'next_stage_requires_method_integration_and_small_domain_checks': True,
        'verification_script_sha256': sha(Path(__file__)),
    }
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('checks','mismatches')}, ensure_ascii=False))
    if not receipt['record_checks_passed']:
        raise SystemExit(1)

if __name__=='__main__':
    main()
