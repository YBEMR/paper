"""K166 read/hash/AST audit only; never imports scientific modules."""
import argparse
import ast
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
BASE = HERE.parent / 'deadline_numerical_readonly01' / 'before.json'
BASE_HASH = 'bd523781ca021054b13921a461980712776077d242904b476b2422a36ce3de08'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='final_integrity.json')
    args = parser.parse_args()
    target = HERE / args.output
    if target.parent.resolve() != HERE.resolve() or target.exists():
        raise ValueError('Use a new filename in this audit directory')
    baseline = load(BASE)
    checks = {'baseline_identity': sha(BASE) == BASE_HASH}
    counts = {}
    for field in ('source_sha256', 'prior_artifact_sha256', 'target_sha256'):
        items = baseline[field]
        counts[field] = len(items)
        checks[field + '_unchanged'] = all(sha(REPO / name) == digest
                                          for name, digest in items.items())
    ledger = load(HERE.parent / 'deadline_resume01' / 'ledger.json')
    checks['original_ledger_blocked_at16'] = (
        ledger['state'] == 'BLOCKED' and ledger['consumed_total'] == 16
        and ledger['prior_consumed'] == 2 and ledger['consumed_new'] == 14
        and len(ledger['calls']) == ledger['consumed_new'])
    algebra = load(HERE / 'algebra/source_audit.json')
    checks['algebra_source_hashes_unchanged'] = (
        algebra['source_unchanged'] and
        all(sha(REPO / name) == digest
            for name, digest in algebra['source_sha256_before'].items()))
    checks['algebra_report_identity'] = (
        sha(HERE / 'algebra/compatibility.md') == algebra['report_sha256'])
    manifest = load(HERE / 'evidence/manifest.json')
    checks['evidence_sources_unchanged'] = manifest['all_read_sources_unchanged']
    checks['evidence_artifact_identities'] = all(
        sha(HERE / 'evidence' / name) == manifest[field] for name, field in (
            ('facts.json', 'facts_sha256'), ('summary.md', 'summary_sha256'),
            ('audit_compatibility.py', 'script_sha256')))
    review = load(HERE / 'root_review.json')
    checks['review_summary_identity'] = (
        review['subject_sha256_before'] == review['subject_sha256_after']
        == sha(HERE / 'summary.md'))
    checks['root_report_review_passed'] = (
        review['verdict'] == 'PASS_WITH_SCOPE_BOUNDARIES'
        and all(item['passed'] for item in review['checks']))
    checks['audit_scripts_stdlib_only'] = True
    for path in HERE.rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                checks['audit_scripts_stdlib_only'] &= all(
                    item.name.split('.')[0] in {'argparse', 'ast', 'collections',
                        'hashlib', 'json', 'pathlib'} for item in node.names)
            elif isinstance(node, ast.ImportFrom):
                checks['audit_scripts_stdlib_only'] &= (
                    node.module or '').split('.')[0] in {
                        'argparse', 'ast', 'collections', 'hashlib', 'json', 'pathlib'}
    report = {'protocol': 'K166-zero-call-compatibility-integrity-v1',
              'passed': all(checks.values()), 'checks': checks, 'counts': counts,
              'baseline_sha256': sha(BASE),
              'summary_sha256': sha(HERE / 'summary.md'),
              'review_sha256': sha(HERE / 'root_review.json'),
              'scope': 'source/old-evidence integrity and static report audit only',
              'execution_scope_declared': {
                  'new_models': 0, 'archived_payload_transformations': 0,
                  'MATLAB_LP_MILP_calls': 0, 'thermal_post_evaluations': 0,
                  'new_candidates_or_U': 0, 'remaining_batch_started': False},
              'implementation_or_numeric_repair_validated': False}
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'checks': len(checks), 'counts': counts}))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
