"""Independent read-only K164 frozen-gate review; no research or heat calls."""
from contextlib import ExitStack
from datetime import datetime, timedelta
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPO = ROOT.parents[1]
sys.path[:0] = [str(ROOT/'deadline_resume'), str(ROOT/'deadline_execution'),
               str(ROOT/'deadline_batch'), str(ROOT/'p0_batch'), str(ROOT)]
import resume_controller as r


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def inspect():
    out, old, repair = r.OUT, r.OLD, r.REPAIR
    if not (out/'declaration.json').is_file():
        raise RuntimeError('Actual frozen continuation declaration required')
    if (out/'launcher_claim.json').exists() or r.GLOBAL_CLAIM.exists():
        raise RuntimeError('This preparation review is only valid before launch')
    d, original = read(out/'declaration.json'), read(old/'declaration.json')
    original_inventory = {p.relative_to(REPO).as_posix(): digest(p)
                          for p in sorted(old.rglob('*')) if p.is_file()}
    new_sources = dict(d['source_sha256'])
    guards = dict.fromkeys(('whole', 'linked', 'heuristic', 'matlab', 'milp', 'linprog',
        'model', 'heat', 'candidate_heat', 'scene_heat', 'subprocess', 'seed'), 0)
    def forbidden(key):
        def fail(*args, **kw):
            guards[key] += 1
            raise AssertionError('Forbidden preparation-review scientific call: '+key)
        return fail
    import formal_milp, linked_method, heuristic_runner, matlab_bridge, milp
    import thermal, scene_adapter, initial_schedule, scipy.optimize
    with ExitStack() as stack:
        for obj, name, key in (
            (formal_milp, 'execute_formal_milp', 'whole'),
            (linked_method, 'execute_linked_fixed_unit_opp_start', 'linked'),
            (heuristic_runner, 'execute_heuristic', 'heuristic'),
            (matlab_bridge.MatlabSession, '__init__', 'matlab'),
            (scipy.optimize, 'milp', 'milp'), (scipy.optimize, 'linprog', 'linprog'),
            (milp, 'build_model', 'model'), (thermal, 'evaluate_piecewise', 'heat'),
            (thermal, 'evaluate_candidate', 'candidate_heat'),
            (scene_adapter, 'evaluate_piecewise', 'scene_heat'),
            (initial_schedule, 'iter_initial_candidates', 'seed')):
            stack.enter_context(patch.object(obj, name, side_effect=forbidden(key)))
        stack.enter_context(patch('subprocess.Popen', side_effect=forbidden('subprocess')))
        admitted = r.admission()
    checks = {}
    def check(name, value):
        checks[name] = bool(value)
    expected = original['slots'][2:]
    old_launcher = read(old/'launcher_claim.json')
    actual_end = datetime.fromisoformat(old_launcher['calendar_deadline_utc'])
    check('exact_remaining_original_38_slots', d['slots'] == expected == r.slots() and len(expected) == 38)
    check('exact_original_ordinals_3_through_40', [s['ordinal'] for s in expected] == list(range(3, 41)))
    check('no_first_two_or_duplicate_slots', not ({s['slot_id'] for s in expected}
        & {s['slot_id'] for s in original['slots'][:2]}) and len({s['slot_id'] for s in expected}) == 38)
    check('all_remaining_methods_300_seconds', all(s['seconds'] == 300 for s in expected))
    check('prior2_plus_new38_total40', (d['prior_consumed'], d['remaining_calls'], d['campaign_call_limit']) == (2, 38, 40))
    check('prior600_plus_new11400_total12000',
        (d['prior_reserved_method_s'], d['remaining_reserved_method_s'], d['campaign_reserved_method_s']) == (600, 11400, 12000))
    check('original_fixed_calendar_not_reset', d['original_calendar_deadline_utc'] == actual_end.isoformat()
        == '2026-10-22T13:46:38.073713+00:00'
        and actual_end == datetime.fromisoformat(old_launcher['started_utc'])+timedelta(seconds=19200)
        and d['calendar_was_not_reset'] is True)
    check('calendar_still_positive_at_review', r.remaining_calendar() > 0)
    check('420_and_480_are_supervision_only',
        (d['method_return_watchdog_s'], d['slot_watchdog_s'], d['post_seconds']) == (420, 480, 60))
    check('old_240_source_manifest_preserved', len(original['source_sha256']) == 240
        and all(new_sources.get(name) == old_hash for name, old_hash in original['source_sha256'].items()))
    check('all_old_240_live_and_snapshots_match', all(
        digest(REPO/name) == digest(old/'source_snapshot'/name) == old_hash
        for name, old_hash in original['source_sha256'].items()))
    check('new_management_sources_match_live_and_snapshots', all(
        digest(REPO/name) == digest(out/'source_snapshot'/name) == value
        for name, value in new_sources.items() if name not in original['source_sha256']))
    check('old_entire_archive_bound_unchanged', d['prior_artifact_sha256'] == original_inventory)
    check('prior_declaration_explicitly_bound', d['prior_declaration_sha256'] == digest(old/'declaration.json'))
    check('frozen_admission_passed', admitted == d)
    check('no_rerun_or_free_initialization', d['retry_methods'] is False
        and d['restore_old_claims'] is False and d['new_or_reused_initialization'] is False)
    gate = read(out/'precheck.json')
    check('precheck_passed_without_error_or_scientific_calls', gate['passed'] is True
        and gate['tests_run'] > 0 and all(gate[k] == 0 for k in
        ('errors', 'failures', 'skipped', 'research_calls', 'native_calls', 'thermal_evaluations', 'physical_models'))
        and gate['error'] is None and not any(gate['blocked_calls'].values()))
    check('precheck_source_hashes_match_actual_frozen_manifest', gate['source_sha256'] == new_sources)
    check('protocol_hash_binding', digest(out/'protocol.md') == d['protocol_sha256']
        == digest(r.HERE/'protocol.md'))
    check('ledger_declared_zero_new_calls', read(out/'ledger.json') == r.initial_ledger())
    check('new_calls_and_claims_empty', not list((out/'calls').iterdir())
        and not list((out/'claims').iterdir()) and not (out/'launcher_claim.json').exists()
        and not r.GLOBAL_CLAIM.exists())
    check('old_claims_remain_only_first_two', [s for s in original['slots']
        if (old/'claims'/(s['slot_id']+'.json')).is_file()] == original['slots'][:2])
    second = original['slots'][1]
    row = read(old/'claims'/(second['slot_id']+'_result.json'))
    check('original_second_failure_not_overwritten', row['state'] == 'BLOCKED'
        and row['records']['execution']['execution_status'] == 'TECHNICAL_FAILURE_CONFIRMED'
        and row['records']['context']['hard_errors'] == ['MISSING_MATCHING_ROOT_CANCEL_FILE'])
    review, post = read(repair/'repair_review.json'), read(repair/'post_summary.json')
    claim, fresh = read(repair/'post01/postcheck.claim.json'), read(repair/'post01/postcheck.json')
    old_folder = old/'calls'/second['problem_id']/second['id']
    raw = read(old_folder/'wrapper_raw_result.json')
    check('cutoff_proof_exactly_bound', review['passed'] is True
        and d['repair_review_sha256'] == digest(repair/'repair_review.json')
        and review['derived_execution_status'] == 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'
        and review['original_U_J'] == review['derived_U_J'] == row['records']['usable_U_J'])
    check('once_only_external_post_bound_to_original_raw_input_and_candidate',
        post['passed'] is True and post['new_U'] is False and post['research_repeated'] is False
        and post['delayed_original_once_only_post'] is True and post['post_budget_s'] == 60
        and post['original_raw_sha256'] == digest(old_folder/'wrapper_raw_result.json')
        and post['original_declaration_sha256'] == digest(old/'declaration.json')
        and post['postcheck_sha256'] == digest(repair/'post01/postcheck.json')
        and post['postclaim_sha256'] == digest(repair/'post01/postcheck.claim.json')
        and claim['provenance']['raw_result_sha256'] == post['original_raw_sha256']
        and claim['provenance']['input_sha256'] == original['inputs'][second['problem_id']]['input_sha256']
        and claim['provenance']['candidate_sha256'] == r.canonical(raw['safe_candidate'])
        and claim['no_retry'] is True and claim['provenance']['new_U'] is False
        and claim['provenance']['no_search_or_repair'] is True)
    check('external_post_safe_full_window_existing_energy_overlap', fresh['state'] == 'SAFE'
        and fresh['rankable_energy'] is True and all(post['checks'].values())
        and set(fresh['scenes']) == set(raw['safe_candidate']['scenes'])
        and max(Fraction(v[0]) for v in (raw['aggregation']['weighted_energy_J'], fresh['weighted_energy_J']))
          <= min(Fraction(v[1]) for v in (raw['aggregation']['weighted_energy_J'], fresh['weighted_energy_J'])))
    check('old_archive_unchanged_after_independent_admission', original_inventory == {
        p.relative_to(REPO).as_posix(): digest(p) for p in sorted(old.rglob('*')) if p.is_file()})
    check('all_scientific_guards_zero', not any(guards.values()))
    return {'protocol': 'K164-independent-stored-preparation-review-v1',
        'passed': all(checks.values()), 'checks': checks, 'checks_run': len(checks),
        'failed_checks': [name for name, value in checks.items() if not value],
        'declaration_sha256': digest(out/'declaration.json'), 'source_sha256': new_sources,
        'precheck_tests_run': gate['tests_run'], 'original_declaration_sha256': digest(old/'declaration.json'),
        'original_calendar_deadline_utc': actual_end.isoformat(),
        'original_archive_file_count': len(original_inventory),
        'prior_consumed': 2, 'new_consumed_at_review': 0, 'remaining_calls': 38,
        'campaign_method_seconds_limit': 12000, 'blocked_calls': guards,
        'new_research_calls': 0, 'new_thermal_evaluations': 0, 'old_archive_modified': False,
        'review_source_sha256': digest(__file__),
        'scope': 'Internal independent preparation review; no external approval, research call or new budget.'}


if __name__ == '__main__':
    result = inspect()
    with (r.OUT/'prepare_review.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('passed', 'checks_run', 'failed_checks',
        'precheck_tests_run', 'prior_consumed', 'new_consumed_at_review', 'remaining_calls',
        'blocked_calls')}, ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 1)
