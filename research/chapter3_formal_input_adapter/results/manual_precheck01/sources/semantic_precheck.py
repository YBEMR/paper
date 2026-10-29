"""Bounded full-window correctness checks, without optimization or repair.

Prepare immutable inputs first; execute once only after pure adapter tests pass.
These are verification candidates, never initial solutions for formal methods.
"""
import argparse
from copy import deepcopy
from fractions import Fraction as F
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

from .run_checks import digest, protected, save

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BETA = '13/10'  # Explicit precheck candidate, not a final scientific choice.
BASE = ROOT/'research/chapter3_workload_calibration/results/calibration01/C01__base_6/evidence.json.gz'
P2 = ROOT/'research/chapter3_experiments/results/p2_execution01/calls/initial_78__R1/heft'
EXPECTED = {
    BASE: '6f80ec8e944b0753a5a7e73cb8660a0b19c27fd604fba05b6aaf0ce021352d76',
    P2/'input_instance.json': '45b1d587709a8e990679a55d687df42e599f39fa870e051c01eed3e76fc03352',
    P2/'wrapper_raw_result.json': '4982b2db545f00defc5e42fc2adf546ee873bf217cb78a1362b3f271e09c15ff',
}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def canonical(x):
    return hashlib.sha256(json.dumps(x, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), default=str).encode()).hexdigest()


def prepare(out, pure):
    from .core import adapt_bundle
    from research.chapter3_workload_calibration.generator import subset
    from research.chapter3_calibration_adjustment.window_policy import make_window_receipt
    require(not out.exists() and out.is_relative_to((HERE/'results').resolve()), 'NEW_OUTPUT_REQUIRED')
    checks = read(pure/'checks.json')
    require(checks['passed'] and checks['protected_unchanged'], 'PURE_CHECKS_REQUIRED')
    for name, h in checks['source_sha256'].items():
        require(digest(ROOT/name) == h, 'PURE_SOURCE_DRIFT:'+name)
    for p, h in EXPECTED.items():
        require(digest(p) == h, 'ARCHIVE_DRIFT:'+str(p))
    evidence = json.loads(gzip.decompress(BASE.read_bytes()))
    members = {str(n): {'workload': subset(evidence['workload'], n),
                       'deadlines': evidence['S1_projections'][str(n)]['deadlines']}
               for n in (1, 2, 4, 6, 8)}
    window = make_window_receipt('C01-S1-semantic-precheck', 'S1', members,
                                 beta=BETA, baseline=evidence)
    config = read(HERE.parent/'chapter3_experiments/config_v01.json')
    adapted = adapt_bundle(members['2']['workload'], members['2']['deadlines'][BETA], window,
                           member_key='2', config=config, instance_id='precheck_C01_s1_2')
    candidate = {'scenes': {s['id']: [dict(row, stage_id=adapted['receipt']['identity_map'][s['id']]['stages'][row['stage_id']])
                                      for row in evidence['reference']['timetables']['H']['scenes'][s['id']]]
                            for s in adapted['instance']['scenarios']}}
    old_instance = read(P2/'input_instance.json')
    raw = read(P2/'wrapper_raw_result.json')
    old_candidate = raw['evaluations'][1]['candidate']
    require(canonical(old_candidate) == '2d70d425d99b44ff318c89445a486b4aa1a03ab67d3f42108158c7f117617375', 'P2_CANDIDATE_DRIFT')
    require(old_instance['platform'] == config['platform'], 'P2_PHYSICAL_DRIFT')
    out.mkdir(parents=True)
    payload = {'adapted': adapted, 'window_receipt': window, 'candidate': candidate,
               'historical_negative': {'instance': old_instance, 'candidate': old_candidate}}
    save(out/'payload.json', payload)
    src = {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(HERE.glob('*.py'))}
    plan = {'schema': 'formal-input-semantic-precheck-v1',
            'scope': 'correctness only; no optimization or algorithm ranking',
            'source_sha256': src, 'protected_source_sha256': protected(),
            'archive_sha256': {p.relative_to(ROOT).as_posix(): h for p, h in EXPECTED.items()},
            'pure_checks_sha256': digest(pure/'checks.json'),
            'payload_sha256': digest(out/'payload.json'), 'beta': BETA,
            'maximum_temperature_C': '80', 'real_thermal_slots': [
                {'id': 'new_C01_S1_2', 'role': 'new adapter; archived H timetable verification only', 'seconds': 60, 'expected': 'SAFE'},
                {'id': 'old_P2_negative', 'role': 'unchanged historical input regression; not new-DAG evidence', 'seconds': 60, 'expected': 'THERMAL_VIOLATION'}],
            'total_real_thermal_seconds': 120, 'batch_wall_seconds': 300,
            'remaining_checks': ['deadline rejection without integration', 'zero-panel unresolved fixture',
                                 'simulated normal solver cutoff with/without prior SAFE'],
            'optimization_calls': 0, 'MATLAB_starts': 0,
            'stop_rule': 'unexpected actual status, exception or budget cutoff stops; no retry/repair/replacement',
            'no_formal_initialization': True, 'formal_result': False}
    save(out/'plan.json', plan)
    print(json.dumps({'state': 'PREPARED', 'plan_sha256': digest(out/'plan.json'),
                      'window_ms': adapted['instance']['window_ms'], 'scenes': 2}, ensure_ascii=False))


def execute(plan_dir, out):
    # No solver/native process is part of this entry. Repeated execution refused.
    require(not out.exists() and out.is_relative_to((HERE/'results').resolve()), 'NEW_OUTPUT_REQUIRED')
    plan = read(plan_dir/'plan.json')
    require(digest(plan_dir/'payload.json') == plan['payload_sha256'], 'PAYLOAD_DRIFT')
    for name, h in {**plan['source_sha256'], **plan['protected_source_sha256'], **plan['archive_sha256']}.items():
        require(digest(ROOT/name) == h, 'SOURCE_DRIFT:'+name)
    save(plan_dir/'execution_claim.json', {'plan_sha256': digest(plan_dir/'plan.json'), 'output': str(out), 'retry': False})
    out.mkdir(parents=True)
    start = time.monotonic()
    payload = read(plan_dir/'payload.json')
    sys.path.insert(0, str(HERE.parent/'chapter3_experiments'))
    from schedules import validate_schedule
    from thermal import Budget, evaluate_candidate
    from execution_status import classify_execution
    instance, candidate = payload['adapted']['instance'], payload['candidate']
    accuracy = payload['adapted']['config']['accuracy_targets']
    record = {'state': 'RUNNING', 'plan_sha256': digest(plan_dir/'plan.json'),
              'thermal_calls_started': 0, 'actual_results': {}, 'fixture_results': {},
              'optimization_calls': 0, 'MATLAB_starts': 0, 'retry': False,
              'formal_result': False, 'expected_status_does_not_authorize_replacement': True}

    def check_budget():
        require(time.monotonic()-start < plan['batch_wall_seconds'], 'BATCH_WALL_LIMIT')

    try:
        for slot in plan['real_thermal_slots']:
            check_budget()
            pair = (instance, candidate) if slot['id'] == 'new_C01_S1_2' else (
                payload['historical_negative']['instance'], payload['historical_negative']['candidate'])
            require(validate_schedule(*pair)['state'] == 'SCHEDULE_VALID_THERMAL_UNCHECKED', 'ILLEGAL_PREDECLARED_CANDIDATE')
            seconds = min(slot['seconds'], plan['batch_wall_seconds']-(time.monotonic()-start))
            record['thermal_calls_started'] += 1
            result = evaluate_candidate(*pair, accuracy, Budget(seconds=seconds))
            save(out/(slot['id']+'.json'), result)
            record['actual_results'][slot['id']] = {'state': result['state'], 'elapsed_s': result['elapsed_s'],
                    'safe_upper_bound_J': result['safe_upper_bound_J'], 'rankable_energy': result['rankable_energy'],
                    'violations': len(result['violations']), 'role': slot['role']}
            check_budget()
            require(result['state'] == slot['expected'], 'UNEXPECTED_ACTUAL_STATUS:'+slot['id'])
        late = deepcopy(candidate)
        row = next(r for r in late['scenes']['C2'] if r['stage_id'] == 'C2::S2.s0002.r1')
        require(row['start_ms'] == '65', 'DEADLINE_FIXTURE_IDENTITY_DRIFT')
        row['start_ms'] = '100'
        legality = validate_schedule(instance, late)
        require(legality['reason'] == 'REQUEST_DEADLINE_EXCEEDED', 'DEADLINE_REJECTION_CHANGED')
        save(out/'deadline_rejection.json', legality)
        record['fixture_results']['deadline'] = {'state': legality['state'], 'reason': legality['reason'], 'thermal_calls': 0}
        # Resource injection: no numeric panel may be evaluated. This is not a
        # measured runtime timeout and not a third real integration slot.
        unresolved = evaluate_candidate(instance, candidate, accuracy, Budget(seconds=10, panels=0))
        require(unresolved['state'] == 'UNRESOLVED' and not unresolved['rankable_energy']
                and unresolved['safe_upper_bound_J'] is None and unresolved['panels'] == 1,
                'UNRESOLVED_FIXTURE_FAILED')
        save(out/'zero_panel_fixture.json', unresolved)
        record['fixture_results']['thermal_unresolved'] = {'state': 'UNRESOLVED', 'kind': 'zero-panel resource injection, not measured timeout'}
        contexts = []
        for has_safe in (False, True):
            context = {'input_identity_valid': True, 'source_identity_valid': True,
                'current_request_identity_valid': True, 'cutoff_s': 300,
                'hard_errors': [], 'observed_numerical_rejection': False,
                'worker_isolation': 'NOT_APPLICABLE', 'prior_requests_complete': True,
                'completion_verified': False, 'root_deadline_confirmed': True,
                'deadline_causal_trace': True, 'last_request': {'state': 'PENDING',
                    'pending_at_cutoff': True, 'refuses_late_candidate': True,
                    'deadline_causal_trace': True, 'deadline_reasons': ['ROOT_BUDGET_EXHAUSTED']}}
            if has_safe:
                context['safe_receipt'] = {'verified': True, 'identity_valid': True,
                    'complete': True, 'formed_at_s': 1,
                    'energy_upper_J': record['actual_results']['new_C01_S1_2']['safe_upper_bound_J']}
            classified = classify_execution({}, context)
            require(classified['execution_status'] == 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'
                    and classified['safe_witness_preserved'] == has_safe
                    and not classified['new_or_late_candidate_accepted'], 'CUTOFF_FIXTURE_FAILED')
            contexts.append({'simulation_only': True, 'has_prior_safe': has_safe,
                             'context': context, 'result': classified})
        save(out/'solver_cutoff_simulation.json', contexts)
        record['fixture_results']['solver_cutoff'] = {'kind': 'pure simulated evidence; zero native solver calls', 'cases': 2}
        check_budget()
        require(protected() == plan['protected_source_sha256'], 'PROTECTED_SOURCE_CHANGED')
        record['state'] = 'PASS'
    except Exception as error:
        record.update(state='STOPPED', error=type(error).__name__+': '+str(error))
    record['elapsed_s'] = time.monotonic()-start
    save(out/'result.json', record)
    print(json.dumps(record, ensure_ascii=False))
    return 0 if record['state'] == 'PASS' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'execute'))
    parser.add_argument('--output', required=True)
    parser.add_argument('--pure')
    parser.add_argument('--plan')
    args = parser.parse_args()
    out = Path(args.output).resolve()
    if args.mode == 'prepare':
        require(args.pure is not None, 'PURE_CHECK_DIRECTORY_REQUIRED')
        prepare(out, Path(args.pure).resolve())
        return 0
    require(args.plan is not None, 'PLAN_DIRECTORY_REQUIRED')
    return execute(Path(args.plan).resolve(), out)


if __name__ == '__main__':
    raise SystemExit(main())
