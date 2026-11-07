"""Extract archived K.196 evidence; stdlib only, no search or thermal evaluation.

Run from the repository root. The single argument is a NEW output JSON path.
This is an archive audit, not an executable six-method experiment or approval.
"""
import hashlib
import json
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
RESULTS = 'research/chapter3_experiments/results/'


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode('utf-8')).hexdigest()


def extract():
    prep = RESULTS + 'small_whole_preparation01/'
    actual = RESULTS + 'small_whole_execution01/'
    input_path = RESULTS + 'small_full_chain_precheck02/restricted_input.json'
    config_path = RESULTS + 'whole_long_budget01/method/input_config.json'
    reference_path = RESULTS + 'small_exact_execution01/reference.json'
    plan, instance = read(prep + 'plan.json'), read(input_path)
    analysis, raw = read(actual + 'analysis.json'), read(actual + 'method/wrapper_raw_result.json')
    assert sha(input_path) == '05ce6ba8c889d7d46b488840f1726ec4bdbe63585a98dc4c454228dc6e466926'
    assert sha(config_path) == '132323b4b18dd514b9baa929543d235ff91bb07026a60e7b629e1adb6aaaa5e2'
    assert instance == read(actual + 'method/input_instance.json') == read(prep + 'input_instance.json')
    assert read(config_path) == read(actual + 'method/input_config.json') == read(prep + 'input_config.json')
    assert analysis['passed'] and all(analysis['checks'].values())
    assert sha(reference_path) == '86f59e8ea686830e563d8992ff2c21b7be10cf1750babfa3c82aadd6dd7427d7'
    archived_hashes = analysis['raw_evidence_sha256']
    for path, expected in archived_hashes.items():
        assert sha(actual + path.replace('\\', '/')) == expected, path
    assert raw['evaluation']['state'] == 'SAFE'
    assert raw['safe_upper_bound_J'] == analysis['energy']['final_U_J']
    source_current = {p: sha(p) for p in plan['source_sha256']}
    source_changes = [p for p, h in source_current.items() if h != plan['source_sha256'][p]]
    scenes = raw['evaluation']['scenes']
    components = {}
    with localcontext() as ctx:
        ctx.prec = 90
        for component in next(iter(scenes.values()))['energy_components_J']:
            components[component] = [str(sum(Decimal(s['energy_components_J'][component][i])
                                             for s in scenes.values()) / 2) for i in (0, 1)]
    gap = Fraction(raw['safe_upper_bound_J']) - Fraction(analysis['energy']['reference_L_J'])
    assert gap >= 0 and gap <= Fraction(analysis['energy']['epsilon_J'])
    evidence = [input_path, config_path, reference_path, prep + 'plan.json',
                actual + 'analysis.json', actual + 'method/wrapper_raw_result.json',
                actual + 'postcheck.json', 'AGENTS.md', 'research/agent_loop/PROTOCOL.md',
                'research/agent_loop/config.json', 'research/chapter3_experiments/audit_k196_quality.py']
    jobs = [{'method': 'heft', 'seed': None}] + [{'method': 'sa', 'seed': s} for s in range(101, 106)]
    for job in jobs:
        job.update(state='NOT_RUN', reason='NO_BOUND_INDEPENDENT_APPROVAL_OR_SIX_JOB_ENTRY',
                   method_calls_consumed=0, post_calls_consumed=0,
                   initial_energy_J=None, final_energy_J=None,
                   first_safe_s=None, best_safe_s=None, total_compute_s=None)
    return {
        'schema': 'k196-same-domain-archive-audit-v1',
        'date': '2026-11-02', 'baseline_commit': 'dcaa7fcbeb52452bee59a805c396765073b7e912',
        'state': 'ARCHIVE_AUDITED_NEW_COMPARISON_NOT_RUN',
        'scope': 'Saved JSON, SHA256 and rational/decimal arithmetic only; zero scientific calls.',
        'execution_authorized': False, 'independent_approval_present': False,
        'evidence_sha256': {p: sha(p) for p in evidence},
        'archived_raw_hashes_checked': len(archived_hashes),
        'input_canonical_sha256': canonical(instance),
        'config_canonical_sha256': canonical(read(config_path)),
        'start_domain': instance['start_domain'],
        'source_count': len(source_current), 'source_changes_since_k195': source_changes,
        'source_sha256': source_current,
        'milp': {'source': 'K196_ARCHIVE_REUSED', 'method': analysis['method'],
                 'energy': analysis['energy'], 'initial_candidate': analysis['initialisation'],
                 'final_candidate': raw['safe_candidate'], 'candidate_changes': analysis['candidate_changes'],
                 'evaluation_state': raw['evaluation']['state'],
                 'peaks_degC': {k: s['peaks_degC'] for k, s in scenes.items()},
                 'energy_components_J': {k: s['energy_components_J'] for k, s in scenes.items()},
                 'weighted_energy_components_J': components,
                 'reference_gap_J_exact': str(gap)},
        'new_jobs': jobs,
        'proposed_execution': {
            'implementation_status': 'NEEDS_THIN_ENTRY_BINDING_AND_INDEPENDENT_REVIEW',
            'method_calls': 6, 'method_root_seconds': 300, 'method_total_seconds': 1800,
            'post_calls_at_most': 6, 'post_seconds': 60, 'post_total_seconds_at_most': 360,
            'suggested_per_job_calendar_seconds': 480, 'suggested_batch_calendar_seconds': 2880,
            'all_method_preparation_counted': True, 'fresh_initialization_each_job': True,
            'historical_optimum_read_by_search': False, 'retry_calls': 0,
            'scientific_entry': 'research.chapter3_experiments.heuristic_runner.execute_heuristic',
            'safe_recheck': 'One fresh complete check per eligible final SAFE; no optimization or replacement.',
            'stop': 'Technical/safety/cleanup failure stops batch; normal no-solution/timeout is recorded; no parameter changes.'},
        'limitations': ['No HEFT/SA execution or quality conclusions.',
                        'Internal source audit is not external independent approval.',
                        'K196 method root excluded Python startup/import; new roots must count preparation.',
                        'Enumeration reference may only be read by post-run analysis, not search.']}


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python -B research/chapter3_experiments/audit_k196_quality.py NEW_OUTPUT.json')
    result = extract()
    destination = Path(sys.argv[1])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'state': result['state'], 'output': str(destination),
                      'source_count': result['source_count'],
                      'source_changes': result['source_changes_since_k195'],
                      'new_method_calls': 0}, ensure_ascii=False))
