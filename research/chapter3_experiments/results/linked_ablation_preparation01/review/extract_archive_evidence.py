"""Extract archived budget, fresh-seed identity and native options only; stdlib."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REPO = HERE.parents[4]
RESULTS = ROOT / 'results'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def main():
    records = []
    files = [RESULTS / 'p0_execution01/calls/base__R1/anchor_linked4/result.json',
        RESULTS / 'p0_resume01/calls/base__R3/anchor_linked4/result.json',
        RESULTS / 'linked_quality_pair01/old_n1/result.json']
    keys = ['AbsoluteGapTolerance', 'RelativeGapTolerance', 'ConstraintTolerance',
        'IntegerTolerance', 'IntegerPreprocess', 'LPPreprocess', 'CutMaxIterations', 'MaxTime', 'Display']
    for path in files:
        raw = path.read_bytes()
        d = json.loads(raw)
        attempts = []
        for index, attempt in enumerate(d.get('seed_attempts', [])):
            agg = attempt.get('aggregation')
            attempts.append({'index': index, 'state': attempt.get('state'), 'reason': attempt.get('reason'),
                'template_rank': attempt.get('construction', {}).get('template_rank'),
                'seed_candidate_sha256': canonical(agg['safe_candidate']) if agg and agg.get('safe_candidate') else None,
                'initial_global_U_J': agg.get('safe_upper_bound_J') if agg else None,
                'complete_aggregate_formed_at_s': agg.get('completed_at_elapsed_s') if agg else None,
                'archived_reference_only_not_new_initialization': True})
        phases = d.get('phases') or [{'phase_index': 1, 'name': 'N1', 'scenes': d['scenes']}]
        searches = []
        for phase in phases:
            for sid, scene in phase['scenes'].items():
                solved = scene.get('solver_result', {})
                searches.append({'phase_index': phase['phase_index'], 'phase_name': phase.get('name'),
                    'scene_id': sid, 'search_started_at_s': scene.get('search_started_at_s'),
                    'search_returned_at_s': scene.get('search_returned_at_s'),
                    'scene_cap_s': scene.get('scene_slice_s', solved.get('scene_slice_s', d.get('scene_slice_s'))),
                    'reason': solved.get('reason'),
                    'native_rounds': [{'request_number': v.get('request_number'),
                        'budget_valid': v.get('budget_valid'),
                        'solver_max_time_s_declared': v.get('solver_max_time_s_declared'),
                        'solver_max_time_s_used': v.get('solver_max_time_s_used'),
                        'native_options': {k: v.get('options', {}).get(k) for k in keys},
                        'x0_provided': v.get('initial_point', {}).get('provided'),
                        'x0_accepted_numerically': v.get('initial_point', {}).get('accepted_numerically'),
                        'x0_thermal_claim': v.get('initial_point', {}).get('thermal_safe_claim')}
                        for v in solved.get('rounds', [])]})
        records.append({'path': path.relative_to(REPO).as_posix(), 'sha256': hashlib.sha256(raw).hexdigest(),
            'problem_id': d['problem_id'], 'method_protocol': d['protocol'], 'historical_state': d['state'],
            'root_limit_s': d['timing']['limit_s'], 'historical_elapsed_s': d['timing']['method_elapsed_s'],
            'clock_origin': d['timing'].get('clock_origin'), 'control_policy': d.get('control_policy'),
            'scene_slice_s': d.get('scene_slice_s'), 'scene_budget_policy': d.get('scene_budget_policy'),
            'shared_deployment': d.get('shared_deployment'), 'seed_attempts': attempts,
            'searches': searches, 'historical_result_not_new_pairing': True})
    source_paths = [ROOT / p for p in ('neighborhood_method.py', 'linked_method.py', 'partial_method.py',
        'solve_model.m', 'p0_batch/dispatch.py', 'p0_execution/protocol.md', 'p0_execution/batch.py')]
    source_paths.append(RESULTS / 'linked_quality_pair01/protocol.md')
    result = {'protocol': 'K172-independent-archived-budget-seed-options-v1',
        'records': records, 'source_sha256': {p.relative_to(REPO).as_posix(): sha(p) for p in source_paths},
        'source_locators': {
            'N1_positive_scene_cap_validation': 'neighborhood_method.py:113-117',
            'N1_root_scope_and_prepare_before_startup': 'neighborhood_method.py:597-621',
            'linked_cap_at_most60': 'linked_method.py:66-68',
            'linked_phase2_remaining_share': 'neighborhood_method.py:675-685',
            'native_cap_clamped_to_root': 'partial_method.py:215-247',
            'fixed_native_options': 'solve_model.m:89-109',
            'original_once60_post': 'p0_execution/protocol.md:10; p0_execution/batch.py:127-155'},
        'interpretation': 'Historical options and seeds are diagnostics only; future invocations must compute fresh seed, never import these candidates or U.',
        'no_solver_or_model_or_heat_or_post_or_candidate_generation': True, 'new_research_calls': 0}
    target = HERE / 'archive_budget_seed_evidence.json'
    with target.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({'records': len(records), 'native_requests': sum(len(s['native_rounds']) for r in records for s in r['searches']),
        'new_research_calls': 0, 'evidence_sha256': sha(target)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
