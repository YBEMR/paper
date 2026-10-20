"""Stored-record audit only; no native, model, or thermal execution."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = next(p for p in ROOT.parents if (p/'AGENTS.md').is_file())
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    output = ROOT/'delivery_verification.json'
    if output.exists():
        raise FileExistsError('Preserve the existing delivery receipt.')
    d, c = read(ROOT/'declaration.json'), read(ROOT/'checks.json')
    f = read(ROOT/'fixture_records.json')['test_augmented_method']
    archive = read(ROOT/'fixture_archive_manifest.json')
    source_errors = [n for n,h in d['source_sha256'].items() if sha(REPO/n)!=h]
    history_errors = [n for n,h in d['historical_artifact_sha256'].items() if sha(REPO/n)!=h]
    archive_errors = [x['archive'] for x in archive['files'] if sha(ROOT/x['archive'])!=x['sha256']]
    snaps = [p for p in (ROOT/'source_snapshot').rglob('*') if p.is_file()]
    real = f['real_small_two_scene_echo']
    r = real['result']
    checks = {
        '142_source_files_match': len(d['source_sha256'])==142 and not source_errors,
        '4_source_snapshots_match': len(snaps)==4 and all(sha(p)==sha(REPO/p.relative_to(ROOT/'source_snapshot')) for p in snaps),
        '134_historical_records_match': len(d['historical_artifact_sha256'])==134 and not history_errors,
        'archived_fixtures_and_development_logs_match': not archive_errors,
        '60_checks_passed': c['passed'] and c['count']==60 and c['source_unchanged'],
        'old_fixed_entry_and_138_base_files_unchanged': c['unchanged_base']['old_fixed_unit_entry_AST_equal'] and c['unchanged_base']['unchanged_base_count']==138 and not c['unchanged_base']['mismatches'],
        'saved_AB_eight_arrays_equal_strict': f['K133_saved_AB_compatibility']['eight_arrays_equal'],
        'selected_rows_eliminate_to_original': f['selected_exact_row_equivalence']['selected_row_Fraction_elimination_equal'],
        'unselected_row_original_rhs_preserved': f['selected_exact_row_equivalence']['original_rhs_bits_unchanged'],
        'real_tiny_two_scene_echo_complete': r['state']=='SAFE' and r['reason']=='SCENE_SEARCH_SEQUENCE_COMPLETE' and len(real['calls'])==2,
        'no_echo_energy_improvement_claim': not r['strict_improvement_over_initial_certified'] and r['weighted_energy_J']==r['initial_global_weighted_energy_J'],
        'no_native_or_original_scale_call': c['native_calls']==c['research_calls']==c['original_scale_models']==0,
        'independent_review_present': (ROOT/'independent_review.md').is_file(),
    }
    receipt = {
        'stage':'K134_delivery_verification', 'passed':all(checks.values()),
        'scope':'stored records only; not a research performance result',
        'checks':checks, 'source_errors':source_errors, 'history_errors':history_errors,
        'archive_errors':archive_errors, 'new_research_safe_or_energy_improvement':False,
        'native_calls':0, 'frozen_precheck_sha256':sha(ROOT/'checks.json'),
        'verification_script_sha256':sha(Path(__file__)),
        'next_action':'freeze independent original-scale quality pair; no call performed in K134',
    }
    output.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':receipt['passed'],'checks':len(checks),'native_calls':0}))
    if not receipt['passed']: raise SystemExit(1)

if __name__=='__main__':
    main()
